"""Evaluación del emparejamiento contra la verdad conocida (columna de grupo).

Todas las funciones trabajan con DataFrames de pandas y calculan con DuckDB, de modo
que se pueden probar sin Splink. Las predicciones son pares
``(unique_id_l, unique_id_r, match_probability)`` en cualquier orden; internamente se
normalizan para que el identificador menor quede a la izquierda.
"""

from __future__ import annotations

from collections.abc import Sequence

import duckdb
import numpy as np
import pandas as pd


def _proporcion(numerador: int, denominador: int) -> float:
    """Divide devolviendo 0.0 si el denominador es cero."""
    return numerador / denominador if denominador else 0.0


def _f1(precision: float, recall: float) -> float:
    return _proporcion(2 * precision * recall, precision + recall) if precision + recall else 0.0


def _metricas(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = _proporcion(tp, tp + fp)
    recall = _proporcion(tp, tp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
    }


def _sql(consulta: str, **tablas: pd.DataFrame) -> duckdb.DuckDBPyRelation:
    """Ejecuta ``consulta`` en una conexión nueva con ``tablas`` registradas por nombre."""
    con = duckdb.connect()
    for nombre, tabla in tablas.items():
        con.register(nombre, tabla)
    return con.sql(consulta)


def _normalizar_pares(pred: pd.DataFrame) -> pd.DataFrame:
    """Ordena cada par (id menor a la izquierda) y quita duplicados."""
    return _sql(
        """
        select least(unique_id_l, unique_id_r) as id_l,
               greatest(unique_id_l, unique_id_r) as id_r,
               max(match_probability) as match_probability
        from pred
        group by 1, 2
        """,
        pred=pred,
    ).df()


def pares_verdaderos(
    df: pd.DataFrame, col_id: str = "unique_id", col_grupo: str = "cluster"
) -> pd.DataFrame:
    """Todos los pares de registros que pertenecen al mismo grupo verdadero."""
    return _sql(
        f"""
        select a.{col_id} as id_l, b.{col_id} as id_r
        from df a join df b
          on a.{col_grupo} = b.{col_grupo} and a.{col_id} < b.{col_id}
        """,
        df=df,
    ).df()


def marcar_verdaderos(pred: pd.DataFrame, verdaderos: pd.DataFrame) -> pd.DataFrame:
    """Agrega a las predicciones normalizadas la columna booleana ``es_match``."""
    return _sql(
        """
        select p.*, v.id_l is not null as es_match
        from normalizadas p
        left join verdaderos v on p.id_l = v.id_l and p.id_r = v.id_r
        """,
        normalizadas=_normalizar_pares(pred),
        verdaderos=verdaderos,
    ).df()


def metricas_pares(
    pred: pd.DataFrame, verdaderos: pd.DataFrame, umbral: float
) -> dict[str, float | int]:
    """Precisión, recall y F1 por par a un umbral de ``match_probability``.

    Los falsos negativos incluyen los pares verdaderos que el bloqueo nunca comparó.
    """
    marcadas = marcar_verdaderos(pred, verdaderos)
    positivos = marcadas[marcadas["match_probability"] >= umbral]
    tp = int(positivos["es_match"].sum())
    fp = len(positivos) - tp
    fn = len(verdaderos) - tp
    return {"umbral": umbral, **_metricas(tp, fp, fn)}


def recall_bloqueo(pred: pd.DataFrame, verdaderos: pd.DataFrame) -> dict[str, float | int]:
    """Qué parte de los pares verdaderos llegó a compararse tras el bloqueo."""
    marcadas = marcar_verdaderos(pred, verdaderos)
    en_bloqueo = int(marcadas["es_match"].sum())
    return {
        "pares_comparados": len(marcadas),
        "pares_verdaderos": len(verdaderos),
        "pares_verdaderos_comparados": en_bloqueo,
        "recall_bloqueo": _proporcion(en_bloqueo, len(verdaderos)),
        "recall_perdido_por_bloqueo": 1 - _proporcion(en_bloqueo, len(verdaderos)),
    }


def curva_umbral(
    pred: pd.DataFrame,
    verdaderos: pd.DataFrame,
    umbrales: Sequence[float] | None = None,
) -> pd.DataFrame:
    """Precisión, recall y F1 por par para una serie de umbrales."""
    if umbrales is None:
        umbrales = np.round(np.arange(0.01, 1.0, 0.01), 2)
    marcadas = marcar_verdaderos(pred, verdaderos)
    filas = []
    for umbral in umbrales:
        positivos = marcadas[marcadas["match_probability"] >= umbral]
        tp = int(positivos["es_match"].sum())
        fp = len(positivos) - tp
        filas.append({"umbral": float(umbral), **_metricas(tp, fp, len(verdaderos) - tp)})
    return pd.DataFrame(filas)


def metricas_cluster(
    clusters: pd.DataFrame,
    df: pd.DataFrame,
    col_id: str = "unique_id",
    col_grupo: str = "cluster",
) -> dict[str, float | int]:
    """Compara los clústeres predichos con los grupos verdaderos.

    ``clusters`` tiene columnas ``unique_id`` y ``cluster_id``. Las métricas por par
    se calculan sobre todos los pares que inducen los clústeres (dos registros en el
    mismo clúster cuentan como emparejados, aunque no se hayan comparado
    directamente). Además se reporta cuántos grupos verdaderos se reconstruyeron
    exactamente (mismos miembros, ni más ni menos).
    """
    asignacion = _sql(
        f"""
        select d.{col_id} as id, d.{col_grupo} as real, c.cluster_id as pred
        from df d join clusters c on d.{col_id} = c.unique_id
        """,
        df=df,
        clusters=clusters,
    ).df()

    inducidos = pares_verdaderos(asignacion, col_id="id", col_grupo="pred")
    verdaderos = pares_verdaderos(asignacion, col_id="id", col_grupo="real")
    tp = int(
        _sql(
            "select count(*) from inducidos join verdaderos using (id_l, id_r)",
            inducidos=inducidos,
            verdaderos=verdaderos,
        ).fetchone()[0]
    )

    exactos = int(
        _sql(
            """
            with miembros_real as (
                select real, list_sort(list(id)) as m from asignacion group by real
            ), miembros_pred as (
                select pred, list_sort(list(id)) as m from asignacion group by pred
            )
            select count(*) from miembros_real r join miembros_pred p on r.m = p.m
            """,
            asignacion=asignacion,
        ).fetchone()[0]
    )
    n_real = int(asignacion["real"].nunique())

    return {
        **_metricas(tp, len(inducidos) - tp, len(verdaderos) - tp),
        "clusters_predichos": int(asignacion["pred"].nunique()),
        "clusters_reales": n_real,
        "clusters_exactos": exactos,
        "pct_clusters_exactos": _proporcion(exactos, n_real),
    }


def umbral_max_f1(curva: pd.DataFrame) -> float:
    """Umbral con mayor F1 en una curva (el menor, si hay empate)."""
    return float(curva.loc[curva["f1"].idxmax(), "umbral"])
