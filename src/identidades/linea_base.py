"""Línea base determinística, enfoque híbrido y dónde aporta Splink.

La auditoría (hallazgo M1) mostró que en estos datos el documento es casi una llave
perfecta: una regla de una línea compite con el modelo. Aquí se comparan, sobre la misma
estandarización que usa el modelo y con unión transitiva (igual que la agrupación de
Splink):

- ``documento``: mismo documento estandarizado.
- ``documento_o_nombre_fecha``: mismo documento, o mismo nombre completo y misma fecha.
- ``splink``: el modelo a su umbral.
- ``hibrido``: las reglas primero (``documento_o_nombre_fecha`` une sin modelo) y Splink
  para el resto (pares que las reglas no unen).
- ``hibrido_estricto``: como el híbrido, pero Splink no puede unir dos registros que
  tienen documento y es distinto (las reglas mandan cuando aplican).

Y por segmento de personas: documento siempre igual, algún registro sin documento, o
documento alterado (dos o más documentos distintos), que es donde se ve si Splink aporta.
"""

from __future__ import annotations

from typing import Any

import duckdb
import numpy as np
import pandas as pd

from identidades import evaluacion

METODOS: dict[str, str] = {
    "documento": "Regla: mismo documento",
    "documento_o_nombre_fecha": "Regla: documento o nombre+fecha",
    "splink": "Splink",
    "hibrido": "Híbrido: reglas y Splink para el resto",
    "hibrido_estricto": "Híbrido estricto: documento distinto nunca se une",
}

SEGMENTOS: dict[str, str] = {
    "documento_igual": "documento siempre igual",
    "sin_documento": "algún registro sin documento",
    "documento_alterado": "documento alterado",
}


def pares_regla(preparado: pd.DataFrame, con_nombre_fecha: bool = True) -> pd.DataFrame:
    """Pares (``id_l`` < ``id_r``) que une la regla determinística."""
    t = preparado[["unique_id", "documento", "nombre_completo", "fecha_nacimiento"]]
    condicion = "l.documento = r.documento"
    if con_nombre_fecha:
        condicion += (
            " or (l.nombre_completo = r.nombre_completo"
            " and l.fecha_nacimiento = r.fecha_nacimiento)"
        )
    con = duckdb.connect()
    con.register("t", t)
    return con.sql(
        f"""
        select distinct l.unique_id as id_l, r.unique_id as id_r
        from t l join t r on l.unique_id < r.unique_id and ({condicion})
        """
    ).df()


def agrupar(ids: pd.Series, pares: pd.DataFrame) -> pd.DataFrame:
    """Componentes conectadas (unión transitiva): ``unique_id``, ``cluster_id``."""
    ids_arr = np.asarray(ids)
    posicion = pd.Series(np.arange(len(ids_arr)), index=ids_arr)
    padre = np.arange(len(ids_arr))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    izq = posicion.loc[pares["id_l"].to_numpy()].to_numpy() if len(pares) else []
    der = posicion.loc[pares["id_r"].to_numpy()].to_numpy() if len(pares) else []
    for a, b in zip(izq, der, strict=True):
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[max(ra, rb)] = min(ra, rb)
    raices = np.array([raiz(i) for i in range(len(ids_arr))])
    return pd.DataFrame({"unique_id": ids_arr, "cluster_id": ids_arr[raices]})


def _pares_splink(pred: pd.DataFrame, umbral: float) -> pd.DataFrame:
    sobre = pred[pred["match_probability"] >= umbral]
    a, b = sobre["unique_id_l"].to_numpy(), sobre["unique_id_r"].to_numpy()
    return pd.DataFrame({"id_l": np.minimum(a, b), "id_r": np.maximum(a, b)})


def _sin_choque_de_documento(pares: pd.DataFrame, preparado: pd.DataFrame) -> pd.DataFrame:
    documento = preparado.set_index("unique_id")["documento"]
    dl = pares["id_l"].map(documento)
    dr = pares["id_r"].map(documento)
    choque = dl.notna() & dr.notna() & (dl != dr)
    return pares[~choque.to_numpy()]


def clusters_por_metodo(
    preparado: pd.DataFrame, pred: pd.DataFrame, umbral: float
) -> dict[str, pd.DataFrame]:
    """Clústeres de cada método de ``METODOS`` sobre los mismos registros."""
    ids = preparado["unique_id"]
    solo_documento = pares_regla(preparado, con_nombre_fecha=False)
    reglas = pares_regla(preparado)
    splink = _pares_splink(pred, umbral)
    return {
        "documento": agrupar(ids, solo_documento),
        "documento_o_nombre_fecha": agrupar(ids, reglas),
        "splink": agrupar(ids, splink),
        "hibrido": agrupar(ids, pd.concat([reglas, splink]).drop_duplicates()),
        "hibrido_estricto": agrupar(
            ids,
            pd.concat([reglas, _sin_choque_de_documento(splink, preparado)]).drop_duplicates(),
        ),
    }


def segmentos(preparado: pd.DataFrame, registros: pd.DataFrame) -> pd.Series:
    """Segmento de cada persona según sus documentos estandarizados (índice: persona)."""
    t = preparado[["unique_id", "documento"]].merge(registros[["unique_id", "cluster"]])
    por_persona = t.groupby("cluster")["documento"].agg(
        faltantes=lambda s: s.isna().sum(), distintos=lambda s: s.dropna().nunique()
    )
    return pd.Series(
        np.select(
            [por_persona["distintos"] > 1, por_persona["faltantes"] > 0],
            [SEGMENTOS["documento_alterado"], SEGMENTOS["sin_documento"]],
            SEGMENTOS["documento_igual"],
        ),
        index=por_persona.index,
    )


def comparar(
    preparado: pd.DataFrame,
    registros: pd.DataFrame,
    pred: pd.DataFrame,
    umbral: float,
    n_bootstrap: int = 1000,
    semilla: int = 0,
) -> dict[str, Any]:
    """Métricas por clúster de cada método, diferencias pareadas y aporte por segmento.

    Con ``n_bootstrap`` = 0 solo se dan los valores puntuales (para tamaños grandes).
    """
    clusters = clusters_por_metodo(preparado, pred, umbral)
    resultado: dict[str, Any] = {
        "umbral_splink": umbral,
        "metodos": {
            m: {"descripcion": METODOS[m], **evaluacion.metricas_cluster(c, registros)}
            for m, c in clusters.items()
        },
    }
    if not n_bootstrap:
        return resultado

    contribuciones = {
        m: evaluacion.contribuciones_por_persona(evaluacion.pares_inducidos(c), registros, c)
        for m, c in clusters.items()
    }
    for m in clusters:
        resultado["metodos"][m]["intervalos"] = evaluacion.bootstrap_por_persona(
            *contribuciones[m], n=n_bootstrap, semilla=semilla
        )
    resultado["diferencias"] = {
        f"{b} - {a}": evaluacion.bootstrap_diferencia(
            contribuciones[a], contribuciones[b], n=n_bootstrap, semilla=semilla
        )
        for a, b in (
            ("documento", "splink"),
            ("documento_o_nombre_fecha", "splink"),
            ("splink", "hibrido"),
            ("splink", "hibrido_estricto"),
        )
    }
    grupos = segmentos(preparado, registros)
    resultado["segmentos"] = {
        "personas": grupos.value_counts().to_dict(),
        "por_metodo": {
            m: evaluacion.bootstrap_por_grupo(
                *contribuciones[m], grupos, n=n_bootstrap, semilla=semilla
            )["grupos"]
            for m in clusters
        },
    }
    return resultado


def tabla(resultado: dict[str, Any]) -> pd.DataFrame:
    """Resumen legible: precisión, recall, F1 y personas exactas por método."""
    return pd.DataFrame(
        [
            {
                "metodo": v["descripcion"],
                **{k: v[k] for k in ("precision", "recall", "f1", "pct_clusters_exactos")},
            }
            for v in resultado["metodos"].values()
        ]
    )
