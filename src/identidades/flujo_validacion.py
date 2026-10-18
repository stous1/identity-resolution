"""Validación del hito 2: prueba ciega con el modelo congelado y validación externa.

- **Prueba ciega.** El modelo del hito 2 (estandarización, esquema y parámetros
  entrenados, congelados en el tag ``hito2-congelado``) se aplica sin ajustar nada a
  personas nuevas cuyos registros se capturaron con un generador de errores escrito
  aparte, sin conocer la estandarización (``errores_ciegos``).
- **FEBRL3.** El mismo procedimiento del hito 2 (bloqueo y umbral elegidos en
  desarrollo, métricas en prueba con bootstrap) sobre un dataset externo.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from identidades import (
    datos,
    errores_ciegos,
    evaluacion,
    flujo,
    flujo_hito2,
    modelo,
    modelo_co,
    rutas,
    sinteticos,
    tableros,
)
from identidades.modelo_febrl import ESQUEMA_FEBRL

TAG_CONGELADO_ORIGINAL: str = "hito2-congelado"
# Revisión con una sola corrección de robustez (apellidos vacíos), hallada al correr la
# prueba ciega: con el tag original el modelo se caía. No cambia ningún resultado del
# hito 2 (métricas idénticas).
TAG_CONGELADO: str = "hito2-congelado-r1"
ARCHIVOS_CONGELADOS: list[str] = [
    "src/identidades/estandarizacion.py",
    "src/identidades/modelo_co.py",
    "docs/resultados/hito2/modelo.json",
]

ARCHIVOS_PUBLICABLES: list[str] = [
    "metricas.json",
    "tres_cifras.html",
    "tres_cifras.png",
    "ciega_muestra_registros.csv",
    "ciega_equidad.html",
    "ciega_equidad.png",
    "ciega_cascada.html",
    "ciega_cluster_studio.html",
    "ciega_cluster_studio.png",
    "febrl_seleccion_bloqueos.csv",
    "febrl_costo_umbral.html",
    "febrl_costo_umbral.png",
]

# Condiciones de persona del generador ciego -> (etiqueta si es verdadera, si es falsa).
# Equidad: grupos de población (atributos de la persona), además de los del hito 2.
GRUPOS_POBLACION: dict[str, tuple[str, str]] = {
    "rural": ("dirección rural", "dirección urbana"),
    "con_apodo": ("con apodo", "sin apodo"),
    "apellido_casada": ("apellido de casada", "sin apellido de casada"),
}

# Diagnóstico: personas a las que el generador ciego les aplicó un error concreto. No son
# grupos de población: dicen dónde falla el modelo, no a quién perjudica. Se excluye
# "un_solo_registro": quien tiene un solo registro no tiene pares que encontrar.
GRUPOS_DIAGNOSTICO: dict[str, tuple[str, str]] = {
    "documento_alterado": ("documento alterado", "documento sin alterar"),
    "celular_fijo": ("celular cambiado por fijo", "con celular"),
    "nombres_cruzados": ("nombres en otro campo", "nombres en su campo"),
}

# Umbrales para el diagnóstico de la prueba ciega (no se usan para la cifra principal).
UMBRALES_DIAGNOSTICO: list[float] = [0.5, 0.9, 0.99, 0.999, 0.9999, 0.99999]

NIVELES: tuple[str, ...] = ("clusters", "pares")


def verificar_congelado(tag: str = TAG_CONGELADO) -> dict[str, Any]:
    """Comprueba que la estandarización, el esquema y el modelo no cambiaron desde ``tag``.

    Falla si alguno de ``ARCHIVOS_CONGELADOS`` difiere del tag: la prueba ciega solo
    vale si el modelo es exactamente el congelado.
    """
    commit = subprocess.run(
        ["git", "rev-list", "-n", "1", tag],
        cwd=rutas.RAIZ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    cambios = subprocess.run(
        ["git", "diff", "--quiet", tag, "--", *ARCHIVOS_CONGELADOS], cwd=rutas.RAIZ
    ).returncode
    if cambios:
        raise RuntimeError(f"El modelo congelado cambió desde {tag}: {ARCHIVOS_CONGELADOS}")
    return {
        "tag": tag,
        "commit": commit,
        "tag_original": TAG_CONGELADO_ORIGINAL,
        "cambio_respecto_al_original": (
            "Corrección de robustez en estandarizacion.py para valores nulos: con el tag "
            "original el modelo fallaba con 66 de 6.032 registros de la prueba ciega "
            "(apellidos vacíos). Métricas del hito 2 idénticas."
        ),
        "archivos": ARCHIVOS_CONGELADOS,
        "sin_cambios": True,
    }


def cargar_congelado(directorio: Path | None = None) -> tuple[dict[str, Any], float]:
    """Modelo entrenado del hito 2 y su umbral de operación (elegido en desarrollo)."""
    directorio = directorio or rutas.DOCS_RESULTADOS_HITO2
    configuracion = json.loads((directorio / "modelo.json").read_text(encoding="utf-8"))
    metricas = json.loads((directorio / "metricas.json").read_text(encoding="utf-8"))
    return configuracion, metricas["variantes"]["estandarizado"]["umbral"]["valor"]


def grupos_de_personas(
    personas: pd.DataFrame,
    condiciones: pd.DataFrame,
    etiquetas: dict[str, tuple[str, str]] | None = None,
) -> dict[str, pd.Series]:
    """Etiqueta de grupo por persona para cada atributo (índice: persona).

    Por defecto, los grupos de equidad: los del hito 2 más ``GRUPOS_POBLACION``.
    """
    tabla = personas.set_index("cluster").join(condiciones.set_index("cluster"))
    etiquetas = etiquetas or {**flujo_hito2.GRUPOS_EQUIDAD, **GRUPOS_POBLACION}
    return {
        atributo: tabla[atributo].astype(bool).map({True: si, False: no})
        for atributo, (si, no) in etiquetas.items()
        if atributo in tabla
    }


def _por_grupo(
    ev: flujo.Evaluacion,
    registros: pd.DataFrame,
    grupos: dict[str, pd.Series],
    n_bootstrap: int,
    semilla: int,
) -> dict[str, Any]:
    return {
        atributo: {
            nivel: evaluacion.bootstrap_por_grupo(
                *flujo_hito2._contribuciones(ev, registros, nivel),
                serie,
                n=n_bootstrap,
                semilla=semilla,
            )
            for nivel in NIVELES
        }
        for atributo, serie in grupos.items()
    }


def ejecutar_prueba_ciega(
    directorio: Path,
    n_personas: int = 2000,
    semilla: int = 2024,
    n_bootstrap: int = 1000,
    configuracion: dict[str, Any] | None = None,
    umbral: float | None = None,
    capturas: bool = True,
) -> dict[str, Any]:
    """Aplica el modelo congelado, sin ajustes, a registros del generador ciego."""
    if configuracion is None or umbral is None:
        configuracion, umbral = cargar_congelado()
    _, personas = sinteticos.generar(n_personas, semilla)
    registros, condiciones = errores_ciegos.capturar(personas, semilla=semilla)
    registros.sample(40, random_state=semilla).sort_values(["cluster", "unique_id"]).to_csv(
        directorio / "ciega_muestra_registros.csv", index=False, lineterminator="\n"
    )

    esquema = modelo_co.esquema(True)
    linker = flujo.aplicar_configuracion(configuracion, registros, esquema)
    ev = flujo.evaluar(linker, registros, umbral, n_bootstrap, semilla)

    equidad = _por_grupo(
        ev, registros, grupos_de_personas(personas, condiciones), n_bootstrap, semilla
    )
    diagnostico = _por_grupo(
        ev,
        registros,
        grupos_de_personas(personas, condiciones, GRUPOS_DIAGNOSTICO),
        n_bootstrap,
        semilla,
    )
    otros_umbrales = []
    for valor in UMBRALES_DIAGNOSTICO:
        clusters = modelo.agrupar(linker, ev.df_pred, valor).as_pandas_dataframe()
        otros_umbrales.append({"umbral": valor, **evaluacion.metricas_cluster(clusters, registros)})

    filas = {
        grupo: valores
        for atributo in equidad
        for grupo, valores in equidad[atributo]["clusters"]["grupos"].items()
    }
    tableros.guardar_intervalos(
        flujo_hito2._tabla_intervalos(filas),
        "Prueba ciega: métricas por clúster por grupo de personas",
        directorio / "ciega_equidad.html",
    )
    ejemplos = tableros.seleccionar_ejemplos_cascada(ev.pred, ev.verdaderos, umbral)
    tableros.guardar_cascada(linker, ejemplos, directorio / "ciega_cascada.html")
    ids, nombres = tableros.seleccionar_clusters(ev.clusters, registros)
    tableros.guardar_cluster_studio(
        linker, ev.df_pred, ev.df_clusters, ids, nombres, directorio / "ciega_cluster_studio.html"
    )
    if capturas:
        error = "mezcla personas" if any("mezcla" in n for n in nombres) else "dividida"
        tableros.capturar_png(
            directorio / "ciega_cluster_studio.html",
            directorio / "ciega_cluster_studio.png",
            seleccionar=error,
        )

    return {
        "descripcion": (
            "Modelo del hito 2 congelado, aplicado sin ajustes a personas nuevas con errores "
            "de un generador independiente (errores_ciegos)."
        ),
        "datos": {
            "personas": n_personas,
            "semilla": semilla,
            "registros": len(registros),
            "tasas_error": asdict(errores_ciegos.TasasCiegas()),
            "condiciones": {
                c: int(condiciones[c].sum()) for c in condiciones.columns if c != "cluster"
            },
        },
        "umbral": umbral,
        "lambda_reestimada": linker.misc.save_model_to_json()[
            "probability_two_random_records_match"
        ],
        "prueba": ev.metricas,
        "equidad": equidad,
        "diferencias_significativas": flujo_hito2.resumir_equidad(equidad),
        "diagnostico_por_error": {
            "nota": "Personas con un error concreto del generador ciego; no son grupos de "
            "población.",
            "detalle": diagnostico,
            "diferencias_significativas": flujo_hito2.resumir_equidad(diagnostico),
        },
        "diagnostico_otros_umbrales": {
            "nota": "Solo diagnóstico: el umbral congelado es el único que se usa para la "
            "cifra principal. Elegir otro mirando estos datos sería ajustar el modelo.",
            "clusters": otros_umbrales,
        },
    }


def ejecutar_febrl(
    directorio: Path,
    frac_desarrollo: float = 0.6,
    semilla: int = 42,
    costo_fp: float = 10.0,
    costo_fn: float = 1.0,
    n_bootstrap: int = 1000,
    df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """El procedimiento del hito 2 sobre FEBRL3: desarrollo para elegir, prueba para medir."""
    df = datos.cargar_febrl3() if df is None else df
    df_dev, df_prueba = datos.dividir_por_persona(df, frac_desarrollo, semilla)
    dev = flujo.desarrollar(df_dev, costo_fp, costo_fn, esquema=ESQUEMA_FEBRL)
    linker = flujo.aplicar_modelo(dev.linker, df_prueba, ESQUEMA_FEBRL)
    ev = flujo.evaluar(linker, df_prueba, dev.umbral, n_bootstrap, semilla)

    dev.historial_bloqueos.to_csv(
        directorio / "febrl_seleccion_bloqueos.csv", index=False, lineterminator="\n"
    )
    tableros.guardar_costo(
        {"par": dev.curva, "clúster": dev.curva_clusters},
        {flujo.CRITERIOS_UMBRAL[c]: u for c, u in dev.umbrales.items()},
        costo_fp,
        costo_fn,
        directorio / "febrl_costo_umbral.html",
    )
    return {
        "descripcion": "FEBRL3: bloqueo y umbral elegidos en desarrollo, métricas en prueba.",
        "particion": {
            "desarrollo": {"registros": len(df_dev), "personas": int(df_dev["cluster"].nunique())},
            "prueba": {
                "registros": len(df_prueba),
                "personas": int(df_prueba["cluster"].nunique()),
            },
        },
        "bloqueos_prediccion": [list(b) for b in dev.bloqueos],
        "umbral": {"criterio": dev.criterio, "valor": dev.umbral},
        "desarrollo": {"umbrales": dev.comparacion_umbrales},
        "prueba": ev.metricas,
    }


def tres_cifras(
    hito2: dict[str, Any], ciega: dict[str, Any], febrl: dict[str, Any]
) -> dict[str, dict[str, dict[str, float]]]:
    """Métricas por clúster de prueba (con intervalos) de las tres evaluaciones."""
    return {
        "prueba normal (hito 2)": hito2["variantes"]["estandarizado"]["prueba"]["intervalos"][
            "clusters"
        ],
        "prueba ciega": ciega["prueba"]["intervalos"]["clusters"],
        "FEBRL3": febrl["prueba"]["intervalos"]["clusters"],
    }


def ejecutar_validacion(
    directorio: Path, n_bootstrap: int = 1000, capturas: bool = True
) -> dict[str, Any]:
    """Prueba ciega + FEBRL, comparadas con la prueba normal del hito 2."""
    directorio.mkdir(parents=True, exist_ok=True)
    congelado = verificar_congelado()
    hito2 = json.loads((rutas.DOCS_RESULTADOS_HITO2 / "metricas.json").read_text(encoding="utf-8"))
    ciega = ejecutar_prueba_ciega(directorio, n_bootstrap=n_bootstrap, capturas=capturas)
    febrl = ejecutar_febrl(directorio, n_bootstrap=n_bootstrap)
    resumen = tres_cifras(hito2, ciega, febrl)

    tableros.guardar_intervalos(
        flujo_hito2._tabla_intervalos(resumen),
        "Prueba normal, prueba ciega y FEBRL3 (por clúster, IC 95 %)",
        directorio / "tres_cifras.html",
    )
    metricas = {
        "modelo_congelado": congelado,
        "tres_cifras_clusters": resumen,
        "prueba_ciega": ciega,
        "febrl3": febrl,
    }
    (directorio / "metricas.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    return metricas
