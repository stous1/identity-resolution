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
    "comparacion_bloqueos.csv",
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

# Reglas aproximadas probadas y descartadas por redundantes (ver ``comparar_bloqueos``).
BLOQUEOS_DESCARTADOS: list[tuple[str, ...]] = [
    ("surname_metaphone",),
    ("substr(first_name, 1, 3)",),
]


def candidatos_bloqueo() -> dict[str, list[tuple[str, ...]]]:
    """Conjuntos de reglas de bloqueo a comparar.

    Las exactas solas, las exactas más cada regla aproximada por separado, la selección
    final (``modelo.BLOQUEOS_PREDICCION``) y todas las reglas probadas.
    """
    exactos = modelo.BLOQUEOS_EXACTOS
    aproximados = modelo.BLOQUEOS_APROXIMADOS + BLOQUEOS_DESCARTADOS
    candidatos = {"exactas": exactos}
    for regla in aproximados:
        candidatos["exactas + " + " & ".join(regla)] = exactos + [regla]
    candidatos["selección"] = modelo.BLOQUEOS_PREDICCION
    candidatos["todas"] = exactos + aproximados
    return candidatos


def comparar_bloqueos(
    df: pd.DataFrame,
    candidatos: dict[str, list[tuple[str, ...]]],
    umbral: float,
) -> pd.DataFrame:
    """Entrena y evalúa el modelo con cada conjunto de reglas de bloqueo.

    El entrenamiento no depende del bloqueo de predicción, pero se repite por
    candidato para que cada fila sea independiente. Devuelve una fila por candidato
    con comparaciones, recall del bloqueo y métricas por par y por clúster a ``umbral``.
    """
    verdaderos = evaluacion.pares_verdaderos(df)
    filas = []
    for nombre, bloqueos in candidatos.items():
        linker = modelo.crear_linker(df, modelo.crear_settings(bloqueos))
        modelo.entrenar(linker)
        df_pred = modelo.predecir(linker)
        pred = df_pred.as_pandas_dataframe()
        bloqueo = evaluacion.recall_bloqueo(pred, verdaderos)
        pares = evaluacion.metricas_pares(pred, verdaderos, umbral)
        clusters = evaluacion.metricas_cluster(
            modelo.agrupar(linker, df_pred, umbral).as_pandas_dataframe(), df
        )
        filas.append(
            {
                "candidato": nombre,
                "reglas": len(bloqueos),
                "pares_comparados": bloqueo["pares_comparados"],
                "recall_bloqueo": bloqueo["recall_bloqueo"],
                "precision_par": pares["precision"],
                "recall_par": pares["recall"],
                "precision_cluster": clusters["precision"],
                "recall_cluster": clusters["recall"],
                "clusters_exactos": clusters["clusters_exactos"],
            }
        )
    return pd.DataFrame(filas)


def ejecutar_hito1(
    df: pd.DataFrame,
    directorio: Path,
    umbral: float = 0.9,
    capturas: bool = True,
    comparar: bool = True,
) -> dict[str, Any]:
    """Entrena el modelo sobre ``df``, lo evalúa contra ``cluster`` y genera los tableros.

    Escribe en ``directorio``: ``modelo.json``, ``metricas.json``, ``curva_umbral.csv``,
    los tableros HTML y sus PNG. Si ``capturas`` es falso, omite las capturas con
    Playwright de los tableros interactivos (los PNG de Altair se generan siempre).
    Si ``comparar`` es verdadero, escribe también ``comparacion_bloqueos.csv``.
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
    curva.to_csv(directorio / "curva_umbral.csv", index=False, lineterminator="\n")
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
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )

    if comparar:
        comparar_bloqueos(df, candidatos_bloqueo(), umbral).to_csv(
            directorio / "comparacion_bloqueos.csv", index=False, lineterminator="\n"
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
