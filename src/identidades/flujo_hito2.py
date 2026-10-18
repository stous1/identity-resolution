"""Flujo del hito 2: clientes sintéticos colombianos, estandarización y equidad.

1. Se generan personas y registros sintéticos con errores (``sinteticos.generar``).
2. Se dividen las personas en desarrollo y prueba.
3. Con cada preparación (estandarizada y cruda, mismo modelo) se eligen bloqueo y
   umbral en desarrollo y se mide una sola vez en prueba, con intervalos por bootstrap.
4. Se mide el aporte de la estandarización (diferencia pareada en prueba) y la equidad
   del modelo estandarizado entre grupos de personas.
5. Se generan los tableros del modelo estandarizado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from identidades import datos, evaluacion, flujo, modelo, modelo_co, sinteticos, tableros

ARCHIVOS_PUBLICABLES: list[str] = [
    "metricas.json",
    "muestra_registros.csv",
    "seleccion_bloqueos.csv",
    "comparacion_bloqueos.csv",
    "equidad.html",
    "equidad.png",
    "estandarizacion.html",
    "estandarizacion.png",
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
    "modelo.json",
]

# Atributo de la persona -> (etiqueta si es verdadero, etiqueta si es falso).
GRUPOS_EQUIDAD: dict[str, tuple[str, str]] = {
    "nombre_compuesto": ("nombre compuesto", "nombre simple"),
    "dos_apellidos": ("dos apellidos", "un apellido"),
    "con_tilde": ("con tilde o ñ", "sin tilde"),
}

# Métricas que se grafican con intervalo, con su nombre legible.
METRICAS_INTERVALO: dict[str, str] = {
    "precision": "Precisión",
    "recall": "Recall",
    "f1": "F1",
    "pct_clusters_exactos": "Personas exactas",
}


def _contribuciones(ev: flujo.Evaluacion, df: pd.DataFrame, nivel: str):
    """Contribuciones por persona por par (umbral) o por clúster (pares inducidos)."""
    if nivel == "pares":
        marcadas = evaluacion.marcar_verdaderos(ev.pred, ev.verdaderos)
        positivos = marcadas[marcadas["match_probability"] >= ev.metricas["pares"]["umbral"]]
        return evaluacion.contribuciones_por_persona(positivos, df)
    positivos = evaluacion.pares_inducidos(ev.clusters)
    return evaluacion.contribuciones_por_persona(positivos, df, ev.clusters)


def evaluar_equidad(
    ev: flujo.Evaluacion,
    df: pd.DataFrame,
    personas: pd.DataFrame,
    n_bootstrap: int,
    semilla: int,
) -> dict[str, Any]:
    """Precisión, recall y reconstrucción exacta por grupo, con diferencias e intervalos.

    Los grupos salen de los atributos verdaderos de cada persona (``GRUPOS_EQUIDAD``).
    """
    atributos = personas.set_index("cluster")
    resultado: dict[str, Any] = {}
    for atributo, (si, no) in GRUPOS_EQUIDAD.items():
        grupos = atributos[atributo].map({True: si, False: no})
        resultado[atributo] = {
            nivel: evaluacion.bootstrap_por_grupo(
                *_contribuciones(ev, df, nivel), grupos, n=n_bootstrap, semilla=semilla
            )
            for nivel in ("clusters", "pares")
        }
    return resultado


def resumir_equidad(equidad: dict[str, Any], nivel: str = "clusters") -> list[dict[str, Any]]:
    """Diferencias significativas entre grupos: dónde falla más el modelo."""
    hallazgos = []
    for atributo, por_nivel in equidad.items():
        for comparacion, metricas in por_nivel[nivel]["diferencias"].items():
            for metrica, d in metricas.items():
                if d["significativa"]:
                    peor = comparacion.split(" - ")[1 if d["valor"] > 0 else 0]
                    hallazgos.append(
                        {
                            "atributo": atributo,
                            "metrica": metrica,
                            "diferencia": comparacion,
                            "valor": d["valor"],
                            "falla_mas_con": peor,
                        }
                    )
    return hallazgos


def _tabla_intervalos(filas: dict[str, dict[str, dict[str, float]]]) -> pd.DataFrame:
    """De {grupo: {métrica: {valor, ic_inf, ic_sup}}} a tabla larga para graficar."""
    return pd.DataFrame(
        [
            {
                "grupo": grupo,
                "metrica": METRICAS_INTERVALO[metrica],
                **{k: v[k] for k in ("valor", "ic_inf", "ic_sup")},
            }
            for grupo, metricas in filas.items()
            for metrica, v in metricas.items()
            if metrica in METRICAS_INTERVALO
        ]
    )


def ejecutar_hito2(
    directorio: Path,
    n_personas: int = 2000,
    semilla: int = 42,
    frac_desarrollo: float = 0.6,
    umbral: float | None = None,
    costo_fp: float = 10.0,
    costo_fn: float = 1.0,
    min_ganancia: float = 0.005,
    n_bootstrap: int = 1000,
    tasas: sinteticos.TasasError | None = None,
    capturas: bool = True,
    comparar: bool = True,
) -> dict[str, Any]:
    """Corre el hito 2 completo y escribe métricas y tableros en ``directorio``."""
    directorio.mkdir(parents=True, exist_ok=True)
    registros, personas = sinteticos.generar(n_personas, semilla, tasas)
    df_dev, df_prueba = datos.dividir_por_persona(registros, frac_desarrollo, semilla)
    registros.sample(40, random_state=semilla).sort_values(["cluster", "unique_id"]).to_csv(
        directorio / "muestra_registros.csv", index=False, lineterminator="\n"
    )

    variantes: dict[str, tuple[flujo.Desarrollo, Any, flujo.Evaluacion]] = {}
    for nombre, estandarizado in (("estandarizado", True), ("crudo", False)):
        esquema = modelo_co.esquema(estandarizado)
        dev = flujo.desarrollar(df_dev, costo_fp, costo_fn, min_ganancia, umbral, esquema)
        linker_prueba = flujo.aplicar_modelo(dev.linker, df_prueba, esquema)
        ev = flujo.evaluar(linker_prueba, df_prueba, dev.umbral, n_bootstrap, semilla)
        variantes[nombre] = (dev, linker_prueba, ev)

    dev, linker_prueba, ev = variantes["estandarizado"]
    _, _, ev_crudo = variantes["crudo"]
    aporte = {
        nivel: evaluacion.bootstrap_diferencia(
            _contribuciones(ev_crudo, df_prueba, nivel),
            _contribuciones(ev, df_prueba, nivel),
            n=n_bootstrap,
            semilla=semilla,
        )
        for nivel in ("clusters", "pares")
    }
    equidad = {
        nombre: evaluar_equidad(e, df_prueba, personas, n_bootstrap, semilla)
        for nombre, (_, _, e) in variantes.items()
    }

    personas_prueba = personas[personas["cluster"].isin(df_prueba["cluster"])]
    metricas: dict[str, Any] = {
        "datos": {
            "generador": "sinteticos.generar (Faker es_CO)",
            "semilla": semilla,
            "personas": n_personas,
            "registros": len(registros),
            "familiares": float(personas["familiar_de"].notna().mean()),
            "tasas_error": sinteticos.describir_tasas(tasas),
        },
        "particion": {
            "frac_desarrollo": frac_desarrollo,
            "desarrollo": {"registros": len(df_dev), "personas": int(df_dev["cluster"].nunique())},
            "prueba": {
                "registros": len(df_prueba),
                "personas": int(df_prueba["cluster"].nunique()),
                **{a: int(personas_prueba[a].sum()) for a in GRUPOS_EQUIDAD},
            },
        },
        "umbral": {"costo_fp": costo_fp, "costo_fn": costo_fn, "elegido_en": "desarrollo"},
        "variantes": {
            nombre: {
                "bloqueos_prediccion": [list(b) for b in d.bloqueos],
                "umbral": {"criterio": d.criterio, "valor": d.umbral},
                "desarrollo": {
                    "seleccion_bloqueos": d.historial_bloqueos.to_dict("records"),
                    "umbrales": d.comparacion_umbrales,
                },
                "prueba": e.metricas,
            }
            for nombre, (d, _, e) in variantes.items()
        },
        "aporte_estandarizacion": {
            "descripcion": "estandarizado - crudo, en prueba, bootstrap pareado por persona",
            **aporte,
        },
        "equidad": {
            "grupos": {k: list(v) for k, v in GRUPOS_EQUIDAD.items()},
            "detalle": equidad,
            "diferencias_significativas": {
                nombre: resumir_equidad(e) for nombre, e in equidad.items()
            },
        },
    }
    (directorio / "metricas.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )

    pd.DataFrame(dev.historial_bloqueos).to_csv(
        directorio / "seleccion_bloqueos.csv", index=False, lineterminator="\n"
    )
    if comparar:
        esquema = modelo_co.esquema(True)
        flujo.comparar_bloqueos(
            df_dev, flujo.candidatos_bloqueo(dev.bloqueos, esquema), dev.umbral, esquema
        ).to_csv(directorio / "comparacion_bloqueos.csv", index=False, lineterminator="\n")

    # Equidad y aporte de la estandarización (prueba, por clúster).
    filas_equidad = {}
    for nombre, etiqueta in (("estandarizado", "estandarizado"), ("crudo", "sin estandarizar")):
        for atributo in GRUPOS_EQUIDAD:
            for grupo, valores in equidad[nombre][atributo]["clusters"]["grupos"].items():
                filas_equidad[f"{grupo} · {etiqueta}"] = valores
    tableros.guardar_intervalos(
        _tabla_intervalos(filas_equidad),
        "Equidad en prueba: métricas por clúster por grupo de personas",
        directorio / "equidad.html",
    )
    tableros.guardar_intervalos(
        _tabla_intervalos(
            {
                "estandarizado": ev.metricas["intervalos"]["clusters"],
                "sin estandarizar": ev_crudo.metricas["intervalos"]["clusters"],
            }
        ),
        "Aporte de la estandarización en prueba (por clúster)",
        directorio / "estandarizacion.html",
    )

    # Curvas de desarrollo y tableros de prueba, del modelo estandarizado.
    marcas = {flujo.CRITERIOS_UMBRAL[c]: u for c, u in dev.umbrales.items()}
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
    modelo.guardar_modelo(dev.linker, directorio / "modelo.json")

    ejemplos = tableros.seleccionar_ejemplos_cascada(ev.pred, ev.verdaderos, dev.umbral)
    tableros.guardar_cascada(linker_prueba, ejemplos, directorio / "cascada.html")
    tableros.guardar_comparison_viewer(
        linker_prueba, ev.df_pred, directorio / "comparison_viewer.html"
    )
    ids, nombres = tableros.seleccionar_clusters(ev.clusters, df_prueba)
    tableros.guardar_cluster_studio(
        linker_prueba, ev.df_pred, ev.df_clusters, ids, nombres, directorio / "cluster_studio.html"
    )
    if capturas:
        error = "mezcla personas" if any("mezcla" in n for n in nombres) else "dividida"
        tableros.capturar_png(
            directorio / "cluster_studio.html", directorio / "cluster_studio.png", seleccionar=error
        )
        tableros.capturar_png(
            directorio / "comparison_viewer.html", directorio / "comparison_viewer.png"
        )
    return metricas
