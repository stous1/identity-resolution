"""Evaluación del emparejamiento contra la verdad conocida (columna de grupo).

Todas las funciones trabajan con DataFrames de pandas y calculan con DuckDB, de modo
que se pueden probar sin Splink. Las predicciones son pares
``(unique_id_l, unique_id_r, match_probability)`` en cualquier orden; internamente se
normalizan para que el identificador menor quede a la izquierda.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import duckdb
import numpy as np
import pandas as pd

# Umbrales de las curvas: cada centésima y, cerca de 1, donde se concentran las
# probabilidades de un modelo con mucha evidencia, también de 0,995 a 0,9999999 (pesos
# de coincidencia de ~7,6 a ~23).
UMBRALES: np.ndarray = np.concatenate(
    [
        np.round(np.arange(0.01, 1.0, 0.01), 2),
        [0.995, 0.999, 0.9999, 0.99999, 0.999999, 0.9999999],
    ]
)


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
        umbrales = UMBRALES
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


def agregar_costo(
    curva: pd.DataFrame, costo_fp: float = 10.0, costo_fn: float = 1.0
) -> pd.DataFrame:
    """Agrega la columna ``costo = costo_fp * fp + costo_fn * fn`` a una curva por umbral.

    Sirve para cualquier curva con columnas ``fp`` y ``fn`` (por par o por clúster).
    """
    return curva.assign(costo=costo_fp * curva["fp"] + costo_fn * curva["fn"])


def umbral_min_costo(curva: pd.DataFrame, costo_fp: float = 10.0, costo_fn: float = 1.0) -> float:
    """Umbral que minimiza el costo total de errores en una curva.

    Por defecto un falso positivo (unir a dos personas distintas) cuesta 10 veces más
    que un falso negativo (dejar un duplicado sin unir). Si hay empate, devuelve el
    umbral más alto, que es el más conservador.
    """
    con_costo = agregar_costo(curva, costo_fp, costo_fn)
    minimo = con_costo["costo"].min()
    return float(con_costo.loc[con_costo["costo"] == minimo, "umbral"].max())


def pares_inducidos(clusters: pd.DataFrame) -> pd.DataFrame:
    """Todos los pares de registros que quedan en el mismo clúster predicho."""
    return pares_verdaderos(clusters, col_id="unique_id", col_grupo="cluster_id")


def contribuciones_por_persona(
    positivos: pd.DataFrame,
    df: pd.DataFrame,
    clusters: pd.DataFrame | None = None,
    col_id: str = "unique_id",
    col_grupo: str = "cluster",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Descompone los aciertos y errores de ``positivos`` por persona verdadera.

    ``positivos`` son los pares que el modelo declara iguales (columnas ``id_l``,
    ``id_r``): los que superan el umbral, o los inducidos por los clústeres. Devuelve:

    - ``por_persona``: ``persona``, ``tp`` (pares de la persona encontrados) y ``fn``
      (pares de la persona no encontrados). Si se dan ``clusters``, también ``exacto``:
      1 si la persona quedó reconstruida exactamente en un solo clúster.
    - ``cruzados``: ``persona_a``, ``persona_b``, ``fp``: falsos positivos entre dos
      personas distintas.

    Sumando las contribuciones se recuperan TP, FN y FP totales, lo que permite
    remuestrear personas sin volver a correr el modelo.
    """
    persona = df.set_index(col_id)[col_grupo]
    pos = positivos[["id_l", "id_r"]].assign(
        persona_a=lambda d: d["id_l"].map(persona).to_numpy(),
        persona_b=lambda d: d["id_r"].map(persona).to_numpy(),
    )
    mismos = pos[pos["persona_a"] == pos["persona_b"]]
    tp = mismos.groupby("persona_a").size()
    tamano = df.groupby(col_grupo).size()
    por_persona = pd.DataFrame({"persona": tamano.index, "pares": tamano * (tamano - 1) // 2})
    por_persona["tp"] = por_persona["persona"].map(tp).fillna(0).astype(int)
    por_persona["fn"] = por_persona["pares"] - por_persona["tp"]

    if clusters is not None:
        asignacion = df[[col_id, col_grupo]].merge(
            clusters[["unique_id", "cluster_id"]], left_on=col_id, right_on="unique_id"
        )
        tamano_pred = asignacion.groupby("cluster_id").size()
        por_cluster = asignacion.groupby(col_grupo).agg(
            n_pred=("cluster_id", "nunique"), cluster_id=("cluster_id", "first")
        )
        exacto = (por_cluster["n_pred"] == 1) & (
            por_cluster["cluster_id"].map(tamano_pred).to_numpy() == tamano.loc[por_cluster.index]
        )
        por_persona["exacto"] = por_persona["persona"].map(exacto).astype(int)

    distintos = pos[pos["persona_a"] != pos["persona_b"]]
    a = distintos[["persona_a", "persona_b"]].min(axis=1)
    b = distintos[["persona_a", "persona_b"]].max(axis=1)
    cruzados = (
        pd.DataFrame({"persona_a": a, "persona_b": b})
        .groupby(["persona_a", "persona_b"])
        .size()
        .rename("fp")
        .reset_index()
    )
    return por_persona.drop(columns="pares").reset_index(drop=True), cruzados


def _pesos_bootstrap(n_personas: int, n: int, semilla: int) -> np.ndarray:
    """Pesos multinomiales por réplica; la fila 0 es la muestra original (todos 1)."""
    rng = np.random.default_rng(semilla)
    pesos = rng.multinomial(n_personas, np.full(n_personas, 1 / n_personas), size=n)
    return np.vstack([np.ones(n_personas, dtype=int), pesos])


def _series_bootstrap(
    por_persona: pd.DataFrame,
    cruzados: pd.DataFrame,
    pesos: np.ndarray,
    personas: np.ndarray,
    mascara: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Métricas en cada réplica de ``pesos`` (columnas en el orden de ``personas``).

    Con ``mascara`` (booleana por persona) se miden solo las personas del grupo: sus
    aciertos y faltantes, y los falsos positivos en que participa al menos una de ellas.
    """
    alineado = por_persona.set_index("persona").loc[personas]
    m = np.ones(len(personas), dtype=bool) if mascara is None else mascara
    indice = {p: i for i, p in enumerate(personas)}

    tp = pesos @ (alineado["tp"].to_numpy() * m)
    fn = pesos @ (alineado["fn"].to_numpy() * m)
    if len(cruzados):
        ia = cruzados["persona_a"].map(indice).to_numpy(dtype=int)
        ib = cruzados["persona_b"].map(indice).to_numpy(dtype=int)
        cuenta = cruzados["fp"].to_numpy() * (m[ia] | m[ib])
        fp = (pesos[:, ia] * pesos[:, ib]) @ cuenta
    else:
        fp = np.zeros(len(pesos))

    # Misma convención que ``_metricas``: 0.0 cuando el denominador es cero (así el valor
    # observado coincide con las métricas puntuales y el JSON nunca lleva NaN).
    with np.errstate(divide="ignore", invalid="ignore"):
        precision = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
        recall = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
        f1 = np.where(precision + recall > 0, 2 * precision * recall / (precision + recall), 0.0)
        series = {"precision": precision, "recall": recall, "f1": f1}
        if "exacto" in alineado:
            en_grupo = pesos @ m
            exactos = pesos @ (alineado["exacto"].to_numpy() * m)
            series["pct_clusters_exactos"] = np.where(en_grupo > 0, exactos / en_grupo, 0.0)
    return series


def _intervalos(series: dict[str, np.ndarray], nivel: float) -> dict[str, dict[str, float]]:
    """Valor observado (fila 0) e intervalo percentil de las réplicas."""
    alfa = (1 - nivel) / 2
    return {
        nombre: {
            "valor": float(valores[0]),
            "ic_inf": float(np.quantile(valores[1:], alfa)),
            "ic_sup": float(np.quantile(valores[1:], 1 - alfa)),
        }
        for nombre, valores in series.items()
    }


def bootstrap_por_persona(
    por_persona: pd.DataFrame,
    cruzados: pd.DataFrame,
    n: int = 1000,
    semilla: int = 0,
    nivel: float = 0.95,
) -> dict[str, dict[str, float]]:
    """Intervalos de confianza por bootstrap remuestreando personas con reemplazo.

    Cada réplica sortea tantas personas como hay, con reemplazo, y les da un peso
    igual a las veces que salieron. TP y FN de una persona se multiplican por su peso;
    un falso positivo entre dos personas cuenta el producto de sus pesos (existe solo si
    ambas están en la réplica). Devuelve, por métrica, el valor observado y el
    intervalo percentil.
    """
    personas = por_persona["persona"].to_numpy()
    pesos = _pesos_bootstrap(len(personas), n, semilla)
    return _intervalos(_series_bootstrap(por_persona, cruzados, pesos, personas), nivel)


def bootstrap_por_grupo(
    por_persona: pd.DataFrame,
    cruzados: pd.DataFrame,
    grupos: pd.Series,
    n: int = 1000,
    semilla: int = 0,
    nivel: float = 0.95,
) -> dict[str, Any]:
    """Métricas por grupo de personas y diferencias entre grupos, con intervalos.

    ``grupos`` asigna a cada persona una etiqueta (índice: persona). Todas las réplicas
    usan los mismos pesos, así que las diferencias son pareadas. Una diferencia es
    ``significativa`` si su intervalo no incluye el cero.
    """
    personas = por_persona["persona"].to_numpy()
    etiquetas = grupos.reindex(personas).to_numpy()
    pesos = _pesos_bootstrap(len(personas), n, semilla)
    series = {
        g: _series_bootstrap(por_persona, cruzados, pesos, personas, etiquetas == g)
        for g in pd.unique(etiquetas)
    }
    resultado: dict[str, Any] = {
        "grupos": {
            str(g): {"personas": int((etiquetas == g).sum()), **_intervalos(s, nivel)}
            for g, s in series.items()
        },
        "diferencias": {},
    }
    nombres = list(series)
    for i, a in enumerate(nombres):
        for b in nombres[i + 1 :]:
            diferencia = _intervalos({k: series[a][k] - series[b][k] for k in series[a]}, nivel)
            for d in diferencia.values():
                d["significativa"] = bool(d["ic_inf"] > 0 or d["ic_sup"] < 0)
            resultado["diferencias"][f"{a} - {b}"] = diferencia
    return resultado


def bootstrap_diferencia(
    contribuciones_a: tuple[pd.DataFrame, pd.DataFrame],
    contribuciones_b: tuple[pd.DataFrame, pd.DataFrame],
    n: int = 1000,
    semilla: int = 0,
    nivel: float = 0.95,
) -> dict[str, dict[str, float]]:
    """Diferencia pareada ``b - a`` entre dos modelos medidos sobre las mismas personas.

    Ambos juegos de contribuciones (de ``contribuciones_por_persona``) deben venir de las
    mismas personas; cada réplica usa los mismos pesos para los dos modelos.
    """
    personas = contribuciones_a[0]["persona"].to_numpy()
    if set(personas) != set(contribuciones_b[0]["persona"]):
        raise ValueError("Los dos modelos deben medirse sobre las mismas personas")
    pesos = _pesos_bootstrap(len(personas), n, semilla)
    serie_a = _series_bootstrap(*contribuciones_a, pesos, personas)
    serie_b = _series_bootstrap(*contribuciones_b, pesos, personas)
    diferencia = _intervalos({k: serie_b[k] - serie_a[k] for k in serie_a}, nivel)
    for d in diferencia.values():
        d["significativa"] = bool(d["ic_inf"] > 0 or d["ic_sup"] < 0)
    return diferencia
