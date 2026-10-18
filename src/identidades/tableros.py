"""Tableros HTML de Splink y capturas PNG para el README."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
from splink import Linker
from splink.internals.splink_dataframe import SplinkDataFrame

from identidades import evaluacion

# Paleta neutra para la curva por umbral (legible en fondo claro y oscuro).
COLORES_METRICAS: dict[str, str] = {
    "precision": "#2563eb",
    "recall": "#d97706",
    "f1": "#059669",
}


def _guardar_grafico(grafico: alt.TopLevelMixin, ruta_html: Path, png: bool = True) -> None:
    """Guarda un gráfico Altair como HTML y, opcionalmente, como PNG al lado."""
    ruta_html.parent.mkdir(parents=True, exist_ok=True)
    grafico.save(str(ruta_html))
    if png:
        grafico.save(str(ruta_html.with_suffix(".png")), scale_factor=2)


def _limpiar_nulos(registro: dict[str, Any]) -> dict[str, Any]:
    """Cambia NaN por None, que es lo que espera el gráfico de cascada."""
    return {k: None if isinstance(v, float) and math.isnan(v) else v for k, v in registro.items()}


def seleccionar_ejemplos_cascada(
    pred: pd.DataFrame, verdaderos: pd.DataFrame, umbral: float, n_por_tipo: int = 2
) -> list[dict[str, Any]]:
    """Elige pares de ejemplo para la cascada: aciertos, falsos positivos y falsos negativos.

    - Acierto: par verdadero con la mayor probabilidad.
    - Falso positivo: par no verdadero con la mayor probabilidad. Si ninguno supera el
      umbral, se muestra el "casi falso positivo" (el no verdadero mejor puntuado).
    - Falso negativo: par verdadero, comparado, con la menor probabilidad bajo el umbral.

    Cada registro conserva todas las columnas de ``pred`` y agrega ``tipo_ejemplo``.
    """
    marcadas = evaluacion.marcar_verdaderos(pred, verdaderos)[["id_l", "id_r", "es_match"]]
    pred = pred.assign(
        id_l=pred[["unique_id_l", "unique_id_r"]].min(axis=1),
        id_r=pred[["unique_id_l", "unique_id_r"]].max(axis=1),
    ).merge(marcadas, on=["id_l", "id_r"])

    aciertos = pred[pred["es_match"]].nlargest(n_por_tipo, "match_probability")
    falsos_pos = pred[~pred["es_match"]].nlargest(n_por_tipo, "match_probability")
    falsos_neg = pred[pred["es_match"] & (pred["match_probability"] < umbral)].nsmallest(
        n_por_tipo, "match_probability"
    )

    ejemplos = []
    for tipo, filas in [
        ("acierto", aciertos),
        ("falso_positivo", falsos_pos),
        ("falso_negativo", falsos_neg),
    ]:
        for registro in filas.drop(columns=["id_l", "id_r", "es_match"]).to_dict("records"):
            ejemplos.append(_limpiar_nulos({**registro, "tipo_ejemplo": tipo}))
    return ejemplos


def guardar_cascada(linker: Linker, ejemplos: list[dict[str, Any]], ruta_html: Path) -> None:
    """Gráfico de cascada: cómo cada campo suma o resta peso en cada par de ejemplo."""
    _guardar_grafico(linker.visualisations.waterfall_chart(ejemplos), ruta_html)


def guardar_parametros(linker: Linker, directorio: Path) -> None:
    """Gráficos de pesos de coincidencia y de parámetros m/u del modelo entrenado."""
    _guardar_grafico(linker.visualisations.match_weights_chart(), directorio / "pesos.html")
    _guardar_grafico(
        linker.visualisations.m_u_parameters_chart(), directorio / "parametros_mu.html"
    )


def _marcas_umbral(marcas: dict[str, float], tope: float = 1.0) -> alt.LayerChart:
    """Líneas verticales punteadas con etiqueta para cada umbral de ``marcas``.

    Las etiquetas se ubican en la parte baja del eje Y, cuyo máximo es ``tope``.
    """
    datos = pd.DataFrame(
        {
            "criterio": list(marcas),
            "umbral": list(marcas.values()),
            # Etiquetas escalonadas para que no se encimen si dos umbrales coinciden.
            "y": [tope * (0.04 + 0.07 * i) for i in range(len(marcas))],
        }
    )
    base = alt.Chart(datos)
    reglas = base.mark_rule(strokeDash=[4, 4], color="#6b7280").encode(
        x="umbral:Q", tooltip=["criterio:N", "umbral:Q"]
    )
    textos = base.mark_text(align="right", dx=-4, fontSize=11, color="#374151").encode(
        x="umbral:Q", y="y:Q", text="criterio:N"
    )
    return reglas + textos


def grafico_curva_umbral(
    curva: pd.DataFrame, marcas: dict[str, float], titulo: str
) -> alt.LayerChart:
    """Precisión, recall y F1 según el umbral, con los umbrales de ``marcas`` señalados."""
    largo = curva.melt(
        id_vars="umbral",
        value_vars=list(COLORES_METRICAS),
        var_name="metrica",
        value_name="valor",
    )
    escala = alt.Scale(domain=list(COLORES_METRICAS), range=list(COLORES_METRICAS.values()))
    lineas = (
        alt.Chart(largo)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("umbral:Q", title="Umbral de match_probability"),
            y=alt.Y("valor:Q", title="Valor", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color("metrica:N", title="Métrica", scale=escala),
            tooltip=["umbral:Q", "metrica:N", alt.Tooltip("valor:Q", format=".3f")],
        )
    )
    return (lineas + _marcas_umbral(marcas)).properties(title=titulo, width=560, height=320)


def grafico_costo(
    curvas: dict[str, pd.DataFrame], marcas: dict[str, float], costo_fp: float, costo_fn: float
) -> alt.LayerChart:
    """Costo total de errores según el umbral, una línea por nivel (par, clúster)."""
    largo = pd.concat([c[["umbral", "costo"]].assign(nivel=nivel) for nivel, c in curvas.items()])
    tope = float(largo["costo"].max())
    lineas = (
        alt.Chart(largo)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("umbral:Q", title="Umbral de match_probability"),
            y=alt.Y("costo:Q", title="Costo total", scale=alt.Scale(domain=[0, tope])),
            color=alt.Color(
                "nivel:N",
                title="Nivel",
                scale=alt.Scale(range=[COLORES_METRICAS["precision"], COLORES_METRICAS["f1"]]),
            ),
            tooltip=["umbral:Q", "nivel:N", "costo:Q"],
        )
    )
    titulo = f"Costo de errores según el umbral (FP = {costo_fp:g}, FN = {costo_fn:g})"
    return (lineas + _marcas_umbral(marcas, tope)).properties(title=titulo, width=560, height=320)


def guardar_curva_umbral(
    curva: pd.DataFrame, marcas: dict[str, float], titulo: str, ruta_html: Path
) -> None:
    _guardar_grafico(grafico_curva_umbral(curva, marcas, titulo), ruta_html)


def guardar_costo(
    curvas: dict[str, pd.DataFrame],
    marcas: dict[str, float],
    costo_fp: float,
    costo_fn: float,
    ruta_html: Path,
) -> None:
    _guardar_grafico(grafico_costo(curvas, marcas, costo_fp, costo_fn), ruta_html)


def guardar_comparison_viewer(linker: Linker, df_pred: SplinkDataFrame, ruta_html: Path) -> None:
    """Comparison viewer: ejemplos de pares agrupados por vector de comparación."""
    ruta_html.parent.mkdir(parents=True, exist_ok=True)
    linker.visualisations.comparison_viewer_dashboard(
        df_pred, str(ruta_html), overwrite=True, num_example_rows=2
    )


def seleccionar_clusters(
    clusters: pd.DataFrame, df: pd.DataFrame, n_errores: int = 6, n_correctos: int = 4
) -> tuple[list[Any], list[str]]:
    """Elige clústeres para Cluster Studio: primero los que tienen errores.

    Un clúster predicho tiene error si mezcla registros de más de una persona real
    (unión de más) o si su persona real quedó repartida en varios clústeres (unión de
    menos). Devuelve ``(ids, nombres)`` para el tablero.
    """
    asignacion = df[["unique_id", "cluster"]].merge(clusters[["unique_id", "cluster_id"]])
    reales_por_pred = asignacion.groupby("cluster_id")["cluster"].nunique()
    preds_por_real = asignacion.groupby("cluster")["cluster_id"].nunique()
    asignacion["dividido"] = asignacion["cluster"].map(preds_por_real) > 1
    tamano = asignacion.groupby("cluster_id").size()

    mezclados = reales_por_pred[reales_por_pred > 1].index.tolist()
    divididos = (
        asignacion[asignacion["dividido"]]
        .assign(tamano=lambda d: d["cluster_id"].map(tamano))
        .sort_values(["tamano", "cluster_id"], ascending=[False, True])["cluster_id"]
        .drop_duplicates()
        .tolist()
    )
    correctos = [
        c
        for c in tamano.sort_values(ascending=False).index
        if c not in mezclados and c not in divididos
    ]

    seleccion: list[tuple[Any, str]] = []
    for ids, etiqueta in [(mezclados, "mezcla personas"), (divididos, "persona dividida")]:
        for c in ids:
            if len(seleccion) < n_errores and c not in [s[0] for s in seleccion]:
                seleccion.append((c, f"{c} ({etiqueta})"))
    seleccion += [(c, f"{c} (correcto)") for c in correctos[:n_correctos]]
    return [s[0] for s in seleccion], [s[1] for s in seleccion]


def guardar_cluster_studio(
    linker: Linker,
    df_pred: SplinkDataFrame,
    df_clusters: SplinkDataFrame,
    cluster_ids: list[Any],
    nombres: list[str],
    ruta_html: Path,
) -> None:
    """Cluster Studio: grafo de cada clúster con sus registros y pares puntuados."""
    ruta_html.parent.mkdir(parents=True, exist_ok=True)
    linker.visualisations.cluster_studio_dashboard(
        df_pred,
        df_clusters,
        str(ruta_html),
        cluster_ids=cluster_ids,
        cluster_names=nombres,
        overwrite=True,
    )


def capturar_png(
    ruta_html: Path,
    ruta_png: Path,
    ancho: int = 1400,
    alto: int = 900,
    espera_ms: int = 3000,
    seleccionar: str | None = None,
) -> None:
    """Abre un HTML local en Chromium sin interfaz y guarda una captura PNG.

    Si se da ``seleccionar``, antes de la captura elige en el primer desplegable de la
    página la primera opción cuyo texto lo contenga (por ejemplo, un clúster con error
    en Cluster Studio).
    """
    from playwright.sync_api import sync_playwright

    ruta_png.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": ancho, "height": alto})
        pagina.goto(ruta_html.resolve().as_uri())
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(espera_ms)
        if seleccionar is not None:
            desplegable = pagina.locator("select").first
            opciones = desplegable.locator("option").all_inner_texts()
            elegida = next((o for o in opciones if seleccionar in o), None)
            if elegida is not None:
                desplegable.select_option(label=elegida)
                pagina.wait_for_timeout(espera_ms)
        pagina.screenshot(path=str(ruta_png))
        navegador.close()
