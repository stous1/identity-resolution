"""Flujo completo del hito 1: desarrollar en un conjunto, medir en otro y publicar.

1. Se dividen las personas en desarrollo y prueba (``datos.dividir_por_persona``).
2. En desarrollo, mirando la verdad conocida, se eligen las reglas de bloqueo, se entrena
   el modelo y se elige el umbral por costo.
3. El modelo se aplica a prueba, deduplicando dentro de prueba, y se mide una sola vez,
   con intervalos de confianza por bootstrap de personas.
4. Como referencia (optimista), el mismo procedimiento se repite sobre todo el dataset y
   se mide sobre los mismos datos con que se eligió todo.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from splink import DuckDBAPI, Linker
from splink.internals.splink_dataframe import SplinkDataFrame

from identidades import bloqueo, datos, evaluacion, modelo, tableros

Regla = tuple[str, ...]

# Salidas del hito 1 que se versionan en docs/resultados/ para GitHub Pages.
ARCHIVOS_PUBLICABLES: list[str] = [
    "metricas.json",
    "seleccion_bloqueos.csv",
    "comparacion_bloqueos.csv",
    "cascada.html",
    "cascada.png",
    "cluster_studio.html",
    "cluster_studio.png",
    "comparison_viewer.html",
    "comparison_viewer.png",
    "curva_umbral.html",
    "curva_umbral.png",
    "curva_umbral_clusters.html",
    "curva_umbral_clusters.png",
    "costo_umbral.html",
    "costo_umbral.png",
    "parametros_mu.html",
    "parametros_mu.png",
    "pesos.html",
    "pesos.png",
]

UMBRAL_FIJO: float = 0.9

# Etiquetas legibles de cada criterio de umbral (para métricas y gráficos).
CRITERIOS_UMBRAL: dict[str, str] = {
    "fijo": "fijo 0,9",
    "max_f1_par": "mejor F1 por par",
    "min_costo_par": "mín. costo por par",
    "min_costo_cluster": "mín. costo por clúster",
}

ADVERTENCIA_REFERENCIA: str = (
    "Optimista: las reglas de bloqueo, el modelo y el umbral se eligieron con la verdad "
    "conocida de los mismos datos con que se mide."
)


def candidatos_bloqueo(
    seleccion: list[Regla], esquema: modelo.Esquema = modelo.ESQUEMA_FAKE_1000
) -> dict[str, list[Regla]]:
    """Conjuntos de reglas de bloqueo a comparar.

    Las exactas solas, las exactas más cada candidata por separado, la ``seleccion``
    hecha en desarrollo y todas las reglas.
    """
    exactas = esquema.bloqueos_exactos
    candidatos = {"exactas": exactas}
    for regla in esquema.bloqueos_candidatos:
        candidatos["exactas + " + " & ".join(regla)] = exactas + [regla]
    candidatos["selección"] = seleccion
    candidatos["todas"] = exactas + esquema.bloqueos_candidatos
    return candidatos


def comparar_bloqueos(
    df: pd.DataFrame,
    candidatos: dict[str, list[Regla]],
    umbral: float,
    esquema: modelo.Esquema = modelo.ESQUEMA_FAKE_1000,
) -> pd.DataFrame:
    """Entrena y evalúa el modelo con cada conjunto de reglas de bloqueo.

    El entrenamiento no depende del bloqueo de predicción, pero se repite por
    candidato para que cada fila sea independiente. Devuelve una fila por candidato
    con comparaciones, recall del bloqueo y métricas por par y por clúster a ``umbral``.
    """
    verdaderos = evaluacion.pares_verdaderos(df)
    filas = []
    for nombre, bloqueos in candidatos.items():
        linker = modelo.crear_linker(df, modelo.crear_settings(bloqueos, esquema), esquema)
        modelo.entrenar(linker, esquema)
        df_pred = modelo.predecir(linker)
        pred = df_pred.as_pandas_dataframe()
        recall_bloqueo = evaluacion.recall_bloqueo(pred, verdaderos)
        pares = evaluacion.metricas_pares(pred, verdaderos, umbral)
        clusters = evaluacion.metricas_cluster(
            modelo.agrupar(linker, df_pred, umbral).as_pandas_dataframe(), df
        )
        filas.append(
            {
                "candidato": nombre,
                "reglas": len(bloqueos),
                "pares_comparados": recall_bloqueo["pares_comparados"],
                "recall_bloqueo": recall_bloqueo["recall_bloqueo"],
                "precision_par": pares["precision"],
                "recall_par": pares["recall"],
                "precision_cluster": clusters["precision"],
                "recall_cluster": clusters["recall"],
                "clusters_exactos": clusters["clusters_exactos"],
            }
        )
    return pd.DataFrame(filas)


def curva_umbral_clusters(
    linker: Linker,
    df_pred: SplinkDataFrame,
    df: pd.DataFrame,
    umbrales: Sequence[float] | None = None,
) -> pd.DataFrame:
    """Métricas por clúster para una serie de umbrales (agrupa una vez por umbral)."""
    if umbrales is None:
        umbrales = np.round(np.arange(0.01, 1.0, 0.01), 2)
    filas = []
    for umbral in umbrales:
        clusters = modelo.agrupar(linker, df_pred, float(umbral)).as_pandas_dataframe()
        filas.append({"umbral": float(umbral), **evaluacion.metricas_cluster(clusters, df)})
    return pd.DataFrame(filas)


def _resumen(metricas: dict[str, Any], claves: Sequence[str]) -> dict[str, Any]:
    return {k: metricas[k] for k in claves}


@dataclass
class Desarrollo:
    """Todo lo que se decide mirando la verdad conocida de un conjunto."""

    bloqueos: list[Regla]
    historial_bloqueos: pd.DataFrame
    linker: Linker
    curva: pd.DataFrame
    curva_clusters: pd.DataFrame
    umbrales: dict[str, float]
    criterio: str
    umbral: float
    comparacion_umbrales: list[dict[str, Any]] = field(default_factory=list)


def desarrollar(
    df: pd.DataFrame,
    costo_fp: float = 10.0,
    costo_fn: float = 1.0,
    min_ganancia: float = 0.005,
    umbral: float | None = None,
    esquema: modelo.Esquema = modelo.ESQUEMA_FAKE_1000,
) -> Desarrollo:
    """Elige bloqueo, entrena y elige umbral usando la verdad conocida de ``df``.

    El umbral es ``umbral`` si se da; si no, el que minimiza el costo de errores por
    clúster. También se calculan el fijo de 0,9, el de mejor F1 por par y el de menor
    costo por par, para compararlos.
    """
    bloqueos, historial = bloqueo.seleccionar_reglas(
        df,
        esquema.bloqueos_exactos,
        esquema.bloqueos_candidatos,
        min_ganancia,
        esquema.preparar,
    )
    linker = modelo.crear_linker(df, modelo.crear_settings(bloqueos, esquema), esquema)
    modelo.entrenar(linker, esquema)

    df_pred = modelo.predecir(linker)
    pred = df_pred.as_pandas_dataframe()
    verdaderos = evaluacion.pares_verdaderos(df)
    curva = evaluacion.agregar_costo(evaluacion.curva_umbral(pred, verdaderos), costo_fp, costo_fn)
    curva_cl = evaluacion.agregar_costo(
        curva_umbral_clusters(linker, df_pred, df), costo_fp, costo_fn
    )

    umbrales = {
        "fijo": UMBRAL_FIJO,
        "max_f1_par": evaluacion.umbral_max_f1(curva),
        "min_costo_par": evaluacion.umbral_min_costo(curva, costo_fp, costo_fn),
        "min_costo_cluster": evaluacion.umbral_min_costo(curva_cl, costo_fp, costo_fn),
    }
    if umbral is None:
        criterio, umbral = "min_costo_cluster", umbrales["min_costo_cluster"]
    else:
        criterio = next((c for c, u in umbrales.items() if u == umbral), "manual")

    comparacion = []
    for nombre, valor in umbrales.items():
        pares = evaluacion.metricas_pares(pred, verdaderos, valor)
        cl = evaluacion.metricas_cluster(
            modelo.agrupar(linker, df_pred, valor).as_pandas_dataframe(), df
        )
        comparacion.append(
            {
                "criterio": nombre,
                "umbral": valor,
                "pares": _resumen(pares, ("tp", "fp", "fn", "precision", "recall", "f1")),
                "costo_pares": costo_fp * pares["fp"] + costo_fn * pares["fn"],
                "clusters": _resumen(
                    cl, ("tp", "fp", "fn", "precision", "recall", "f1", "clusters_exactos")
                ),
                "costo_clusters": costo_fp * cl["fp"] + costo_fn * cl["fn"],
            }
        )

    return Desarrollo(
        bloqueos=bloqueos,
        historial_bloqueos=historial,
        linker=linker,
        curva=curva,
        curva_clusters=curva_cl,
        umbrales=umbrales,
        criterio=criterio,
        umbral=umbral,
        comparacion_umbrales=comparacion,
    )


def aplicar_modelo(
    linker_entrenado: Linker,
    df: pd.DataFrame,
    esquema: modelo.Esquema = modelo.ESQUEMA_FAKE_1000,
) -> Linker:
    """Aplica un modelo entrenado a otro conjunto, deduplicando dentro de ``df``.

    Conserva las comparaciones, el bloqueo y los parámetros m y u. La probabilidad a
    priori (lambda) depende del tamaño del conjunto, así que se vuelve a estimar en
    ``df`` con las mismas reglas determinísticas, que no usan etiquetas.
    """
    configuracion = linker_entrenado.misc.save_model_to_json()
    linker = Linker(esquema.preparar(df), configuracion, db_api=DuckDBAPI())
    linker.training.estimate_probability_two_random_records_match(
        esquema.reglas_deterministicas, recall=modelo.RECALL_DETERMINISTICO
    )
    return linker


@dataclass
class Evaluacion:
    """Predicciones, clústeres y métricas de un modelo sobre un conjunto."""

    df_pred: SplinkDataFrame
    pred: pd.DataFrame
    verdaderos: pd.DataFrame
    df_clusters: SplinkDataFrame
    clusters: pd.DataFrame
    metricas: dict[str, Any]


def evaluar(
    linker: Linker,
    df: pd.DataFrame,
    umbral: float,
    n_bootstrap: int = 0,
    semilla: int = 0,
) -> Evaluacion:
    """Predice, agrupa a ``umbral`` y mide contra la verdad conocida de ``df``.

    Con ``n_bootstrap`` > 0 agrega intervalos de confianza del 95 % remuestreando
    personas, por par y por clúster.
    """
    df_pred = modelo.predecir(linker)
    pred = df_pred.as_pandas_dataframe()
    verdaderos = evaluacion.pares_verdaderos(df)
    df_clusters = modelo.agrupar(linker, df_pred, umbral)
    clusters = df_clusters.as_pandas_dataframe()

    metricas: dict[str, Any] = {
        "bloqueo": evaluacion.recall_bloqueo(pred, verdaderos),
        "pares": evaluacion.metricas_pares(pred, verdaderos, umbral),
        "clusters": {"umbral": umbral, **evaluacion.metricas_cluster(clusters, df)},
    }
    if n_bootstrap:
        marcadas = evaluacion.marcar_verdaderos(pred, verdaderos)
        positivos_par = marcadas[marcadas["match_probability"] >= umbral]
        positivos_cl = evaluacion.pares_inducidos(clusters)
        metricas["intervalos"] = {
            "metodo": "bootstrap percentil remuestreando personas",
            "nivel": 0.95,
            "replicas": n_bootstrap,
            "personas": int(df["cluster"].nunique()),
            "pares": evaluacion.bootstrap_por_persona(
                *evaluacion.contribuciones_por_persona(positivos_par, df),
                n=n_bootstrap,
                semilla=semilla,
            ),
            "clusters": evaluacion.bootstrap_por_persona(
                *evaluacion.contribuciones_por_persona(positivos_cl, df, clusters),
                n=n_bootstrap,
                semilla=semilla,
            ),
        }
    return Evaluacion(df_pred, pred, verdaderos, df_clusters, clusters, metricas)


def _describir(df: pd.DataFrame) -> dict[str, int]:
    return {"registros": len(df), "personas": int(df["cluster"].nunique())}


def _lambda(linker: Linker) -> float:
    return linker.misc.save_model_to_json()["probability_two_random_records_match"]


def _escribir_csv(tabla: pd.DataFrame, ruta: Path) -> None:
    tabla.to_csv(ruta, index=False, lineterminator="\n")


def ejecutar_hito1(
    df: pd.DataFrame,
    directorio: Path,
    frac_desarrollo: float = 0.6,
    semilla: int = 42,
    umbral: float | None = None,
    costo_fp: float = 10.0,
    costo_fn: float = 1.0,
    min_ganancia: float = 0.005,
    n_bootstrap: int = 1000,
    capturas: bool = True,
    comparar: bool = True,
    referencia: bool = True,
) -> dict[str, Any]:
    """Desarrolla en una parte de las personas, mide en el resto y genera los tableros.

    Escribe en ``directorio``: ``modelo.json`` (entrenado en desarrollo),
    ``metricas.json``, la selección de bloqueo y las curvas de desarrollo (CSV), los
    tableros HTML y sus PNG. Las curvas y el gráfico de costo son de desarrollo; la
    cascada, Cluster Studio y el comparison viewer son de prueba.

    Si ``capturas`` es falso, omite las capturas con Playwright de los tableros
    interactivos. Si ``comparar`` es verdadero, escribe ``comparacion_bloqueos.csv``
    (en desarrollo). Si ``referencia`` es verdadero, repite el procedimiento sobre todo
    el dataset como referencia optimista. Devuelve el diccionario de métricas.
    """
    directorio.mkdir(parents=True, exist_ok=True)
    df_dev, df_prueba = datos.dividir_por_persona(df, frac_desarrollo, semilla)

    # Desarrollo: todo lo que mira etiquetas.
    dev = desarrollar(df_dev, costo_fp, costo_fn, min_ganancia, umbral)
    modelo.guardar_modelo(dev.linker, directorio / "modelo.json")
    _escribir_csv(dev.historial_bloqueos, directorio / "seleccion_bloqueos.csv")
    _escribir_csv(dev.curva, directorio / "curva_umbral.csv")
    _escribir_csv(dev.curva_clusters, directorio / "curva_umbral_clusters.csv")
    ev_dev = evaluar(dev.linker, df_dev, dev.umbral)

    # Prueba: se mide una sola vez, con el modelo y el umbral de desarrollo.
    linker_prueba = aplicar_modelo(dev.linker, df_prueba)
    ev_prueba = evaluar(linker_prueba, df_prueba, dev.umbral, n_bootstrap, semilla)

    metricas: dict[str, Any] = {
        "dataset": _describir(df),
        "particion": {
            "frac_desarrollo": frac_desarrollo,
            "semilla": semilla,
            "desarrollo": _describir(df_dev),
            "prueba": _describir(df_prueba),
        },
        "modelo": {
            "entrenado_en": "desarrollo",
            "lambda_desarrollo": _lambda(dev.linker),
            "lambda_prueba": _lambda(linker_prueba),
            "bloqueos_prediccion": [list(b) for b in dev.bloqueos],
            "bloqueos_em": [list(b) for b in modelo.BLOQUEOS_EM],
        },
        "umbral": {
            "criterio": dev.criterio,
            "valor": dev.umbral,
            "elegido_en": "desarrollo",
            "costo_fp": costo_fp,
            "costo_fn": costo_fn,
        },
        "prueba": ev_prueba.metricas,
        "desarrollo": {
            **ev_dev.metricas,
            "seleccion_bloqueos": dev.historial_bloqueos.to_dict("records"),
            "umbrales": dev.comparacion_umbrales,
        },
    }

    if referencia:
        ref = desarrollar(df, costo_fp, costo_fn, min_ganancia, umbral)
        ev_ref = evaluar(ref.linker, df, ref.umbral)
        metricas["referencia_todo_el_dataset"] = {
            "advertencia": ADVERTENCIA_REFERENCIA,
            "bloqueos_prediccion": [list(b) for b in ref.bloqueos],
            "umbral": {"criterio": ref.criterio, "valor": ref.umbral},
            **ev_ref.metricas,
        }

    (directorio / "metricas.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )

    if comparar:
        _escribir_csv(
            comparar_bloqueos(df_dev, candidatos_bloqueo(dev.bloqueos), dev.umbral),
            directorio / "comparacion_bloqueos.csv",
        )

    # Gráficos de desarrollo (elección del umbral) y del modelo entrenado.
    marcas = {CRITERIOS_UMBRAL[c]: u for c, u in dev.umbrales.items()}
    tableros.guardar_curva_umbral(
        dev.curva,
        marcas,
        "Precisión, recall y F1 por par (desarrollo)",
        directorio / "curva_umbral.html",
    )
    tableros.guardar_curva_umbral(
        dev.curva_clusters,
        marcas,
        "Precisión, recall y F1 por clúster (desarrollo)",
        directorio / "curva_umbral_clusters.html",
    )
    tableros.guardar_costo(
        {"par": dev.curva, "clúster": dev.curva_clusters},
        marcas,
        costo_fp,
        costo_fn,
        directorio / "costo_umbral.html",
    )
    tableros.guardar_parametros(dev.linker, directorio)

    # Tableros de prueba.
    ejemplos = tableros.seleccionar_ejemplos_cascada(
        ev_prueba.pred, ev_prueba.verdaderos, dev.umbral
    )
    tableros.guardar_cascada(linker_prueba, ejemplos, directorio / "cascada.html")
    tableros.guardar_comparison_viewer(
        linker_prueba, ev_prueba.df_pred, directorio / "comparison_viewer.html"
    )
    ids, nombres = tableros.seleccionar_clusters(ev_prueba.clusters, df_prueba)
    tableros.guardar_cluster_studio(
        linker_prueba,
        ev_prueba.df_pred,
        ev_prueba.df_clusters,
        ids,
        nombres,
        directorio / "cluster_studio.html",
    )

    if capturas:
        # La captura muestra el error más grave disponible: una mezcla de personas.
        error = "mezcla personas" if any("mezcla" in n for n in nombres) else "dividida"
        tableros.capturar_png(
            directorio / "cluster_studio.html",
            directorio / "cluster_studio.png",
            seleccionar=error,
        )
        tableros.capturar_png(
            directorio / "comparison_viewer.html", directorio / "comparison_viewer.png"
        )

    return metricas


def publicar_resultados(origen: Path, destino: Path) -> list[Path]:
    """Copia las salidas publicables de ``origen`` a ``destino``.

    Falla si falta alguna, para no publicar un conjunto incompleto.
    """
    faltantes = [n for n in ARCHIVOS_PUBLICABLES if not (origen / n).exists()]
    if faltantes:
        raise FileNotFoundError(f"Faltan salidas en {origen}: {faltantes}")
    destino.mkdir(parents=True, exist_ok=True)
    return [Path(shutil.copy2(origen / n, destino / n)) for n in ARCHIVOS_PUBLICABLES]
