"""Flujo completo del hito 1: entrenar, evaluar y generar tableros."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from identidades import evaluacion, modelo, tableros

# Salidas del hito 1 que se versionan en docs/resultados/ para GitHub Pages.
ARCHIVOS_PUBLICABLES: list[str] = [
    "metricas.json",
    "cascada.html",
    "cascada.png",
    "cluster_studio.html",
    "cluster_studio.png",
    "comparison_viewer.html",
    "comparison_viewer.png",
    "curva_umbral.html",
    "curva_umbral.png",
    "parametros_mu.html",
    "parametros_mu.png",
    "pesos.html",
    "pesos.png",
]


def ejecutar_hito1(
    df: pd.DataFrame,
    directorio: Path,
    umbral: float = 0.9,
    capturas: bool = True,
) -> dict[str, Any]:
    """Entrena el modelo sobre ``df``, lo evalúa contra ``cluster`` y genera los tableros.

    Escribe en ``directorio``: ``modelo.json``, ``metricas.json``, ``curva_umbral.csv``,
    los tableros HTML y sus PNG. Si ``capturas`` es falso, omite las capturas con
    Playwright de los tableros interactivos (los PNG de Altair se generan siempre).
    Devuelve el diccionario de métricas.
    """
    directorio.mkdir(parents=True, exist_ok=True)

    linker = modelo.crear_linker(df)
    modelo.entrenar(linker)
    modelo.guardar_modelo(linker, directorio / "modelo.json")

    df_pred = modelo.predecir(linker)
    pred = df_pred.as_pandas_dataframe()
    verdaderos = evaluacion.pares_verdaderos(df)

    curva = evaluacion.curva_umbral(pred, verdaderos)
    curva.to_csv(directorio / "curva_umbral.csv", index=False)
    umbral_f1 = evaluacion.umbral_max_f1(curva)

    df_clusters = modelo.agrupar(linker, df_pred, umbral)
    clusters = df_clusters.as_pandas_dataframe()

    metricas = {
        "dataset": {
            "registros": len(df),
            "personas": int(df["cluster"].nunique()),
        },
        "modelo": {
            "probability_two_random_records_match": linker.misc.save_model_to_json()[
                "probability_two_random_records_match"
            ],
            "bloqueos_prediccion": [list(b) for b in modelo.BLOQUEOS_PREDICCION],
            "bloqueos_em": [list(b) for b in modelo.BLOQUEOS_EM],
        },
        "bloqueo": evaluacion.recall_bloqueo(pred, verdaderos),
        "pares": evaluacion.metricas_pares(pred, verdaderos, umbral),
        "pares_umbral_max_f1": evaluacion.metricas_pares(pred, verdaderos, umbral_f1),
        "clusters": {"umbral": umbral, **evaluacion.metricas_cluster(clusters, df)},
    }
    (directorio / "metricas.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    ejemplos = tableros.seleccionar_ejemplos_cascada(pred, verdaderos, umbral)
    tableros.guardar_cascada(linker, ejemplos, directorio / "cascada.html")
    tableros.guardar_parametros(linker, directorio)
    tableros.guardar_curva_umbral(curva, umbral, directorio / "curva_umbral.html")
    tableros.guardar_comparison_viewer(linker, df_pred, directorio / "comparison_viewer.html")

    ids, nombres = tableros.seleccionar_clusters(clusters, df)
    tableros.guardar_cluster_studio(
        linker, df_pred, df_clusters, ids, nombres, directorio / "cluster_studio.html"
    )

    if capturas:
        tableros.capturar_png(
            directorio / "cluster_studio.html",
            directorio / "cluster_studio.png",
            seleccionar="dividida",
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
