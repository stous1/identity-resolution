"""Flujo del hito 2b: corregir con la prueba ciega 1 y volver a medir a ciegas.

1. **Desarrollar** (``desarrollar_v2``): desarrollo = el de hito 2 (60 % de las personas
   de la semilla 42) + toda la prueba ciega 1 (que ya no es ciega). Ahí se eligen bloqueo
   y umbral del esquema v2 y se guarda el modelo para congelarlo (tag
   ``hito2b-congelado``).
2. **Evaluar el modelo congelado** (``evaluar_congelado_v2``), sin ajustes:
   - prueba normal del hito 2 (las mismas 800 personas), para ver si algo empeoró;
   - prueba ciega 1, solo como referencia (es desarrollo: optimista);
   - prueba ciega 2, con un generador escrito por otro subagente sin acceso a nada de
     esto: la cifra honesta.
   Con equidad por grupo y la brecha antes (modelo v1 en ciega 1) y después (v2 en ciega 2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from identidades import (
    datos,
    errores_ciegos,
    evaluacion,
    flujo,
    flujo_hito2,
    flujo_validacion,
    modelo,
    modelo_co,
    rutas,
    sinteticos,
    tableros,
)
from identidades.modelo_co_v2 import ESQUEMA_V2

TAG_CONGELADO: str = "hito2b-congelado"
DESPLAZAMIENTO_CIEGA_1: int = 100_000  # para que ids y personas no choquen con hito 2

ARCHIVOS_PUBLICABLES: list[str] = [
    "modelo.json",
    "desarrollo.json",
    "metricas.json",
    "evolucion.html",
    "evolucion.png",
    "brecha_equidad.html",
    "brecha_equidad.png",
    "ciega2_equidad.html",
    "ciega2_equidad.png",
    "ciega2_muestra_registros.csv",
    "ciega2_cluster_studio.html",
    "ciega2_cluster_studio.png",
]


def datos_desarrollo(
    semilla_hito2: int = 42, semilla_ciega_1: int = 2024, frac: float = 0.6
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Desarrollo del hito 2b y prueba normal del hito 2 (sin cambios).

    Devuelve ``(desarrollo, prueba_hito2)``. Al desarrollo se le suma la prueba ciega 1
    completa, con ids y personas desplazados para no chocar.
    """
    registros, _ = sinteticos.generar(2000, semilla_hito2)
    dev, prueba = datos.dividir_por_persona(registros, frac, semilla_hito2)
    ciega_1 = registros_ciega_1(semilla_ciega_1)
    ciega_1 = ciega_1.assign(
        unique_id=ciega_1["unique_id"] + DESPLAZAMIENTO_CIEGA_1,
        cluster=ciega_1["cluster"] + DESPLAZAMIENTO_CIEGA_1,
    )
    return pd.concat([dev, ciega_1], ignore_index=True), prueba


def registros_ciega_1(semilla: int = 2024) -> pd.DataFrame:
    _, personas = sinteticos.generar(2000, semilla)
    return errores_ciegos.capturar(personas, semilla=semilla)[0]


def desarrollar_v2(
    directorio: Path, costo_fp: float = 10.0, costo_fn: float = 1.0
) -> dict[str, Any]:
    """Elige bloqueo y umbral del esquema v2 en desarrollo y guarda el modelo a congelar."""
    directorio.mkdir(parents=True, exist_ok=True)
    df_dev, _ = datos_desarrollo()
    dev = flujo.desarrollar(df_dev, costo_fp, costo_fn, esquema=ESQUEMA_V2)
    modelo.guardar_modelo(dev.linker, directorio / "modelo.json")
    resumen = {
        "desarrollo": {
            "descripcion": "Desarrollo del hito 2 (semilla 42) + prueba ciega 1 completa",
            "registros": len(df_dev),
            "personas": int(df_dev["cluster"].nunique()),
        },
        "bloqueos_prediccion": [list(b) for b in dev.bloqueos],
        "seleccion_bloqueos": dev.historial_bloqueos.to_dict("records"),
        "umbral": {
            "criterio": dev.criterio,
            "valor": dev.umbral,
            "costo_fp": costo_fp,
            "costo_fn": costo_fn,
        },
        "umbrales": dev.comparacion_umbrales,
    }
    (directorio / "desarrollo.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    return resumen


def cargar_congelado_v2(directorio: Path | None = None) -> tuple[dict[str, Any], float]:
    directorio = directorio or rutas.DOCS_RESULTADOS_HITO2B
    configuracion = json.loads((directorio / "modelo.json").read_text(encoding="utf-8"))
    desarrollo = json.loads((directorio / "desarrollo.json").read_text(encoding="utf-8"))
    return configuracion, desarrollo["umbral"]["valor"]


def _equidad(
    ev: flujo.Evaluacion,
    registros: pd.DataFrame,
    personas: pd.DataFrame,
    condiciones: pd.DataFrame,
    n_bootstrap: int,
    semilla: int,
) -> dict[str, Any]:
    grupos = flujo_validacion.grupos_de_personas(personas, condiciones)
    return flujo_validacion._por_grupo(ev, registros, grupos, n_bootstrap, semilla)


def brecha(equidad: dict[str, Any], atributo: str) -> dict[str, Any]:
    """Personas exactas por grupo y la diferencia (con intervalo) de un atributo."""
    clusters = equidad[atributo]["clusters"]
    ((comparacion, diferencias),) = clusters["diferencias"].items()
    return {
        "grupos": {
            g: {
                "personas": v["personas"],
                **{m: v[m] for m in ("recall", "pct_clusters_exactos", "precision")},
            }
            for g, v in clusters["grupos"].items()
        },
        "diferencia": comparacion,
        "pct_clusters_exactos": diferencias["pct_clusters_exactos"],
        "recall": diferencias["recall"],
    }


def evaluar_congelado_v2(
    directorio: Path,
    n_bootstrap: int = 1000,
    semilla_ciega_2: int = 7777,
    capturas: bool = True,
) -> dict[str, Any]:
    """Aplica el modelo v2 congelado, sin ajustes, a la prueba normal y a las dos ciegas."""
    # Se importa aquí: el generador ciego 2 se escribió después de congelar el modelo.
    from identidades import errores_ciegos_2

    directorio.mkdir(parents=True, exist_ok=True)
    configuracion, umbral = cargar_congelado_v2()

    def aplicar(registros: pd.DataFrame, semilla: int) -> flujo.Evaluacion:
        linker = flujo.aplicar_configuracion(configuracion, registros, ESQUEMA_V2)
        return flujo.evaluar(linker, registros, umbral, n_bootstrap, semilla)

    _, prueba_hito2 = datos_desarrollo()
    ev_hito2 = aplicar(prueba_hito2, 42)

    _, personas_1 = sinteticos.generar(2000, 2024)
    registros_1, condiciones_1 = errores_ciegos.capturar(personas_1, semilla=2024)
    ev_1 = aplicar(registros_1, 2024)
    equidad_1 = _equidad(ev_1, registros_1, personas_1, condiciones_1, n_bootstrap, 2024)

    _, personas_2 = sinteticos.generar(2000, semilla_ciega_2)
    registros_2, condiciones_2 = errores_ciegos_2.capturar(personas_2, semilla=semilla_ciega_2)
    registros_2.sample(40, random_state=semilla_ciega_2).sort_values(
        ["cluster", "unique_id"]
    ).to_csv(directorio / "ciega2_muestra_registros.csv", index=False, lineterminator="\n")
    linker_2 = flujo.aplicar_configuracion(configuracion, registros_2, ESQUEMA_V2)
    ev_2 = flujo.evaluar(linker_2, registros_2, umbral, n_bootstrap, semilla_ciega_2)
    equidad_2 = _equidad(ev_2, registros_2, personas_2, condiciones_2, n_bootstrap, semilla_ciega_2)

    # Control: el modelo v1 congelado sobre la misma ciega 2. Separa cuánto mejoró el
    # modelo de cuánto más fácil (o difícil) es el generador nuevo.
    flujo_validacion.verificar_congelado()
    configuracion_v1, umbral_v1 = flujo_validacion.cargar_congelado()
    linker_2_v1 = flujo.aplicar_configuracion(
        configuracion_v1, registros_2, modelo_co.esquema(True)
    )
    ev_2_v1 = flujo.evaluar(linker_2_v1, registros_2, umbral_v1, n_bootstrap, semilla_ciega_2)
    equidad_2_v1 = _equidad(
        ev_2_v1, registros_2, personas_2, condiciones_2, n_bootstrap, semilla_ciega_2
    )
    mejora_v2 = {
        nivel: evaluacion.bootstrap_diferencia(
            flujo_hito2._contribuciones(ev_2_v1, registros_2, nivel),
            flujo_hito2._contribuciones(ev_2, registros_2, nivel),
            n=n_bootstrap,
            semilla=semilla_ciega_2,
        )
        for nivel in ("clusters", "pares")
    }

    anterior = json.loads(
        (rutas.DOCS_RESULTADOS_VALIDACION / "metricas.json").read_text(encoding="utf-8")
    )
    hito2 = json.loads((rutas.DOCS_RESULTADOS_HITO2 / "metricas.json").read_text(encoding="utf-8"))
    equidad_antes = anterior["prueba_ciega"]["equidad"]

    evolucion = {
        "prueba normal · modelo v1": hito2["variantes"]["estandarizado"]["prueba"]["intervalos"][
            "clusters"
        ],
        "prueba normal · modelo v2": ev_hito2.metricas["intervalos"]["clusters"],
        "ciega 1 · modelo v1": anterior["prueba_ciega"]["prueba"]["intervalos"]["clusters"],
        "ciega 1 · modelo v2 (desarrollo)": ev_1.metricas["intervalos"]["clusters"],
        "ciega 2 · modelo v1 (control)": ev_2_v1.metricas["intervalos"]["clusters"],
        "ciega 2 · modelo v2": ev_2.metricas["intervalos"]["clusters"],
    }
    brechas = {
        atributo: {
            "antes (ciega 1, modelo v1)": brecha(equidad_antes, atributo),
            "control (ciega 2, modelo v1)": brecha(equidad_2_v1, atributo),
            "después (ciega 2, modelo v2)": brecha(equidad_2, atributo),
        }
        for atributo in ("apellido_casada", "con_apodo", *flujo_hito2.GRUPOS_EQUIDAD, "rural")
        if atributo in equidad_2 and atributo in equidad_antes
    }

    tableros.guardar_intervalos(
        flujo_hito2._tabla_intervalos(evolucion),
        "Evolución por clúster (IC 95 %)",
        directorio / "evolucion.html",
    )
    filas_brecha = {}
    for momentos in brechas.values():
        for momento, b in momentos.items():
            etiqueta = momento.split(" (")[0]
            for grupo, v in b["grupos"].items():
                filas_brecha[f"{grupo} · {etiqueta}"] = {
                    "pct_clusters_exactos": v["pct_clusters_exactos"],
                    "recall": v["recall"],
                }
    tableros.guardar_intervalos(
        flujo_hito2._tabla_intervalos(filas_brecha),
        "Brecha de equidad antes (ciega 1, v1) y después (ciega 2, v2)",
        directorio / "brecha_equidad.html",
    )
    filas_2 = {
        g: v for atributo in equidad_2 for g, v in equidad_2[atributo]["clusters"]["grupos"].items()
    }
    tableros.guardar_intervalos(
        flujo_hito2._tabla_intervalos(filas_2),
        "Prueba ciega 2: métricas por clúster por grupo de personas",
        directorio / "ciega2_equidad.html",
    )
    ids, nombres = tableros.seleccionar_clusters(ev_2.clusters, registros_2)
    tableros.guardar_cluster_studio(
        linker_2,
        ev_2.df_pred,
        ev_2.df_clusters,
        ids,
        nombres,
        directorio / "ciega2_cluster_studio.html",
    )
    if capturas:
        error = "mezcla personas" if any("mezcla" in n for n in nombres) else "dividida"
        tableros.capturar_png(
            directorio / "ciega2_cluster_studio.html",
            directorio / "ciega2_cluster_studio.png",
            seleccionar=error,
        )

    metricas = {
        "modelo_congelado": {"tag": TAG_CONGELADO, "umbral": umbral},
        "evolucion_clusters": evolucion,
        "brechas": brechas,
        "prueba_normal_hito2": ev_hito2.metricas,
        "ciega_1_desarrollo": {
            "nota": "Desarrollo del modelo v2: optimista, solo referencia.",
            **ev_1.metricas,
            "equidad": equidad_1,
        },
        "ciega_2_control_v1": {
            "nota": "Modelo v1 congelado (hito2-congelado-r1) sobre la misma ciega 2.",
            "umbral": umbral_v1,
            **ev_2_v1.metricas,
            "equidad": equidad_2_v1,
        },
        "mejora_v2_sobre_v1_en_ciega_2": {
            "descripcion": "v2 - v1 sobre las mismas personas de la ciega 2 (pareado)",
            **mejora_v2,
        },
        "ciega_2": {
            "datos": {
                "personas": 2000,
                "semilla": semilla_ciega_2,
                "registros": len(registros_2),
                "condiciones": {
                    c: int(condiciones_2[c].sum())
                    for c in condiciones_2.columns
                    if c != "cluster" and condiciones_2[c].dtype == bool
                },
            },
            **ev_2.metricas,
            "equidad": equidad_2,
            "diferencias_significativas": flujo_hito2.resumir_equidad(equidad_2),
        },
    }
    (directorio / "metricas.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    return metricas
