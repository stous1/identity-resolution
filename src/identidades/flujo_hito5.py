"""Flujo del hito 5: vinculación en tiempo real y escala.

- ``ejecutar_tiempo_real``: base de clientes sintéticos (registros de oro) y consultas de
  personas existentes y nuevas, evaluadas con el modelo v2 congelado sin ajustes.
- ``agregar_escala``: junta las mediciones de ``scripts/escala.py`` en una tabla y dos
  gráficos (tiempo y memoria por etapa según el número de registros).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd

from identidades import flujo_hito2b, rutas, tableros, tiempo_real

DIRECTORIO: Path = rutas.REPORTS_HITO5
ARCHIVOS_PUBLICABLES: list[str] = [
    "tiempo_real.json",
    "escala.csv",
    "escala_tiempo.html",
    "escala_tiempo.png",
    "escala_memoria.html",
    "escala_memoria.png",
    "universo_grande_puntos.parquet",
    "universo_grande_enlaces.parquet",
    "universo_grande_puntos_liviano.parquet",
    "universo_grande_enlaces_liviano.parquet",
    "universo_grande.png",
]
ETAPAS: dict[str, str] = {
    "preparacion": "Preparación",
    "entrenamiento": "Entrenamiento",
    "prediccion": "Predicción",
    "agrupacion": "Agrupación",
}


def ejecutar_tiempo_real(
    directorio: Path = DIRECTORIO,
    n_personas: int = 3000,
    max_consultas: int = 1000,
    n_bootstrap: int = 1000,
) -> dict[str, Any]:
    configuracion, umbral = flujo_hito2b.cargar_congelado_v2()
    registros_base, consultas, _ = tiempo_real.preparar_evaluacion(
        n_personas, max_consultas=max_consultas
    )
    base = tiempo_real.construir_base(registros_base, configuracion, umbral)
    vinculador = tiempo_real.Vinculador(
        base, configuracion, umbral, relleno=tiempo_real.telefonos_de_relleno(registros_base)
    )
    resultado = {
        "modelo": {"tag": flujo_hito2b.TAG_CONGELADO, "umbral": umbral},
        "zona_gris_desde": tiempo_real.ZONA_GRIS,
        "base": {"clientes": len(base), "registros_usados": len(registros_base)},
        **tiempo_real.evaluar(vinculador, consultas, n_bootstrap),
    }
    tiempo_real.guardar(resultado, directorio / "tiempo_real.json")
    return resultado


def tabla_escala(directorio: Path = DIRECTORIO) -> pd.DataFrame:
    filas = []
    for ruta in sorted(directorio.glob("escala_*.json")):
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        registros = datos["mediciones"][0]["detalle"]["registros"]
        for m in datos["mediciones"]:
            filas.append(
                {
                    "registros": registros,
                    "etapa": ETAPAS[m["etapa"]],
                    "segundos": round(m["segundos"], 1),
                    "memoria_pico_gb": round(m["memoria_pico_gb"], 2),
                    "precision_cluster": round(datos["calidad"]["precision"], 4),
                    "recall_cluster": round(datos["calidad"]["recall"], 4),
                }
            )
    tabla = pd.DataFrame(filas)
    orden = tabla["etapa"].map({e: i for i, e in enumerate(ETAPAS.values())})
    return tabla.assign(_orden=orden).sort_values(["registros", "_orden"]).drop(columns="_orden")


def _grafico(tabla: pd.DataFrame, campo: str, titulo: str, eje: str) -> alt.Chart:
    colores = alt.Scale(
        domain=list(ETAPAS.values()), range=["#2563eb", "#d97706", "#059669", "#7c3aed"]
    )
    return (
        alt.Chart(tabla)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X("registros:Q", title="Registros", scale=alt.Scale(type="log")),
            y=alt.Y(f"{campo}:Q", title=eje, scale=alt.Scale(type="log")),
            color=alt.Color("etapa:N", title="Etapa", scale=colores, sort=list(ETAPAS.values())),
            tooltip=["registros:Q", "etapa:N", f"{campo}:Q"],
        )
        .properties(title=titulo, width=520, height=300)
    )


def agregar_escala(directorio: Path = DIRECTORIO) -> pd.DataFrame:
    tabla = tabla_escala(directorio)
    tabla.to_csv(directorio / "escala.csv", index=False, lineterminator="\n")
    tableros._guardar_grafico(
        _grafico(tabla, "segundos", "Tiempo por etapa (DuckDB, una máquina)", "Segundos (log)"),
        directorio / "escala_tiempo.html",
    )
    tableros._guardar_grafico(
        _grafico(tabla, "memoria_pico_gb", "Memoria pico del proceso por etapa", "GB (log)"),
        directorio / "escala_memoria.html",
    )
    return tabla
