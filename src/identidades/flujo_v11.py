"""Flujo de la v1.1: realidad residencial y familiar colombiana.

1. **Desarrollar el v4** (``desarrollar_v4``). Desarrollo = el del v3 (hito 2 con historia,
   ciegas 1 y 2) más un escenario residencial de desarrollo (semilla 4040). Ahí se eligen
   el bloqueo, el piso de las m, el umbral y la calibración, como en el hito 6. El modelo se
   congela en el tag ``v4-congelado``.
2. **Grafo residencial** (``grafo_semillas``): el clasificador nuevo se ajusta en el
   escenario de desarrollo y se mide en el de prueba, con 8 pares de semillas, frente al
   clasificador del hito 3.
3. **Evaluar los congelados** (``evaluar_congelados``): v3 y v4 en la prueba normal, la
   ciega 3 (ya mirada, solo como referencia), los escenarios residenciales de prueba y la
   **prueba ciega 4**.

La ciega 3 no entra en el desarrollo del v4 y no se mira mientras se desarrolla.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pandas as pd

from identidades import bloqueo, calibracion, evaluacion, flujo_hito6, modelo, rutas
from identidades.escenario_residencial import generar_escenario_residencial
from identidades.modelo_co_v4 import CANDIDATOS_MAX_BITS, ESQUEMA_V4

TAG_CONGELADO: str = "v4-congelado"
ARCHIVOS_CONGELADOS: list[str] = [
    "src/identidades/modelo_co_v4.py",
    "src/identidades/estandarizacion_v4.py",
    "docs/resultados/v11/modelo.json",
    "docs/resultados/v11/desarrollo.json",
    "docs/resultados/v11/calibracion.json",
]
SEMILLA_RESIDENCIAL_DESARROLLO: int = 4040
DESPLAZAMIENTO_RESIDENCIAL: int = 300_000


def _escribir(datos_json: dict, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(datos_json, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="\n",
    )


def datos_desarrollo_v4() -> pd.DataFrame:
    """Desarrollo del v3 más el escenario residencial de desarrollo (ids desplazados)."""
    base = flujo_hito6.datos_desarrollo()
    residencial, _, _ = generar_escenario_residencial(2000, SEMILLA_RESIDENCIAL_DESARROLLO)
    residencial = flujo_hito6._desplazar(residencial, DESPLAZAMIENTO_RESIDENCIAL)
    columnas = list(base.columns)
    return pd.concat([base, residencial[columnas]], ignore_index=True)


def desarrollar_v4(
    directorio: Path, costo_fp: float = 10.0, costo_fn: float = 1.0
) -> dict[str, Any]:
    """Elige bloqueo, piso de las m, umbral y calibración del v4 en desarrollo."""
    directorio.mkdir(parents=True, exist_ok=True)
    df = datos_desarrollo_v4()
    esquema = ESQUEMA_V4
    bloqueos, historial = bloqueo.seleccionar_reglas(
        df, esquema.bloqueos_exactos, esquema.bloqueos_candidatos, 0.005, esquema.preparar
    )
    linker = modelo.crear_linker(df, modelo.crear_settings(bloqueos, esquema), esquema)
    modelo.entrenar(linker, esquema)
    sin_piso = linker.misc.save_model_to_json()
    preparado = esquema.preparar(df)

    candidatos: dict[str, dict[str, Any]] = {}
    for bits in (None, *CANDIDATOS_MAX_BITS):
        configuracion = sin_piso if bits is None else modelo.aplicar_piso_m(sin_piso, bits)
        r = flujo_hito6._evaluar_configuracion(configuracion, preparado, df, costo_fp, costo_fn)
        r["configuracion"] = configuracion
        candidatos["sin piso" if bits is None else str(bits)] = r
    # Como en el v3: el piso es obligatorio; gana el de menor costo y, si empatan, el más
    # estricto.
    elegido = min(CANDIDATOS_MAX_BITS, key=lambda b: (candidatos[str(b)]["costo"], b))
    final = candidatos[str(elegido)]
    _escribir(final["configuracion"], directorio / "modelo.json")

    marcadas = flujo_hito6.marcar(final["pred"], evaluacion.pares_verdaderos(df))
    cal = calibracion.ajustar(marcadas["match_weight"], marcadas["es_match"])
    limites = calibracion.bandas(cal, peso_umbral=flujo_hito6.peso_de(final["umbral"]))
    _escribir({**cal.a_dict(), "bandas": limites}, directorio / "calibracion.json")
    final["curva"].to_csv(
        directorio / "curva_costo_desarrollo.csv", index=False, lineterminator="\n"
    )

    resumen = {
        "desarrollo": {
            "descripcion": (
                "Desarrollo del v3 (hito 2 con historia, ciega 1 y ciega 2) + escenario "
                f"residencial de desarrollo (semilla {SEMILLA_RESIDENCIAL_DESARROLLO})"
            ),
            "registros": len(df),
            "personas": int(df["cluster"].nunique()),
        },
        "bloqueos_prediccion": [list(b) for b in bloqueos],
        "seleccion_bloqueos": historial.to_dict("records"),
        "piso_m": {
            "max_bits_en_contra": elegido,
            "criterio": "menor costo por clúster en desarrollo (10·FP + FN); empate: más estricto",
            "candidatos": {
                k: {kk: v[kk] for kk in ("umbral", "costo", "clusters", "vetos")}
                for k, v in candidatos.items()
            },
        },
        "pesos_extremos": {
            "sin_piso": modelo.pesos_extremos(sin_piso),
            "con_piso": modelo.pesos_extremos(final["configuracion"]),
        },
        "pesos_domicilio": pesos_niveles(final["configuracion"], "domicilio"),
        "umbral": {
            "criterio": "min_costo_cluster",
            "valor": final["umbral"],
            "peso": flujo_hito6.peso_de(final["umbral"]),
            "costo_fp": costo_fp,
            "costo_fn": costo_fn,
        },
        "calibracion": {
            "metodo": "isotónica de la verdad sobre match_weight, pares del bloqueo en desarrollo",
            "pares": cal.pares,
            "bandas": limites,
        },
    }
    _escribir(resumen, directorio / "desarrollo.json")
    return resumen


def pesos_niveles(configuracion: dict, comparacion: str) -> list[dict[str, Any]]:
    """Peso (log2 m/u) de cada nivel de una comparación del modelo guardado."""
    import math

    (comp,) = [c for c in configuracion["comparisons"] if c["output_column_name"] == comparacion]
    return [
        {
            "nivel": n.get("label_for_charts", n["sql_condition"]),
            "bits": round(math.log2(n["m_probability"] / n["u_probability"]), 2),
            "frecuencia": n.get("tf_adjustment_column"),
        }
        for n in comp["comparison_levels"]
        if not n.get("is_null_level")
    ]


def cargar_congelado_v4(
    directorio: Path | None = None,
) -> tuple[dict[str, Any], float, calibracion.Calibracion, dict]:
    """Modelo v4, umbral, calibración y bandas de zona gris congelados."""
    directorio = directorio or rutas.DOCS_RESULTADOS_V11
    configuracion = json.loads((directorio / "modelo.json").read_text(encoding="utf-8"))
    desarrollo = json.loads((directorio / "desarrollo.json").read_text(encoding="utf-8"))
    cal = json.loads((directorio / "calibracion.json").read_text(encoding="utf-8"))
    bandas = cal.pop("bandas")
    return configuracion, desarrollo["umbral"]["valor"], calibracion.Calibracion(**cal), bandas


def verificar_congelado(tag: str = TAG_CONGELADO) -> None:
    """Falla si el esquema, la estandarización o el modelo v4 cambiaron desde ``tag``."""
    cambios = subprocess.run(
        ["git", "diff", "--quiet", tag, "--", *ARCHIVOS_CONGELADOS], cwd=rutas.RAIZ
    ).returncode
    if cambios:
        raise RuntimeError(f"El modelo v4 congelado cambió desde {tag}: {ARCHIVOS_CONGELADOS}")


# ---------------------------------------------------------------------------
# Diagnóstico previo (tarea 0)
# ---------------------------------------------------------------------------


def diagnostico(directorio: Path) -> dict[str, Any]:
    """Diagnóstico previo de la v1.1 en JSON (ver ``docs/v11_diagnostico.md``)."""
    from identidades import diagnostico_v11

    resultado = {
        "parametros_grafo_hito3": asdict(diagnostico_v11.PARAMETROS_PUBLICADOS),
        "casos": diagnostico_v11.resumen_por_caso(),
        "direcciones_v1": diagnostico_v11.direcciones_v1(),
        "niveles_direccion_v3": diagnostico_v11.niveles_direccion_v3(),
        "caso_esther": diagnostico_v11.caso_esther(),
        "ajuste_frecuencia_v3": pesos_niveles(flujo_hito6.cargar_congelado_v3()[0], "domicilio"),
    }
    _escribir(resultado, directorio / "diagnostico.json")
    return {c["caso"]: [g["clase"] for g in c["grupos"]] for c in resultado["casos"]}


# ---------------------------------------------------------------------------
# Grafo residencial con varias semillas (tarea 3)
# ---------------------------------------------------------------------------

SEMILLAS_GRAFO: list[tuple[int, int]] = [(4040, 4141)] + [
    (4000 + s, 4100 + s) for s in (11, 22, 33, 44, 55, 66, 77)
]
PARAMETROS_GRAFO_HITO3: tuple[int, float] = (15, 0.5)  # docs/resultados/hito3/metricas.json


def preparar_v4_tipado(df: pd.DataFrame) -> pd.DataFrame:
    """``modelo_co_v4.preparar`` con ``unidad_partes`` tipada como lista de texto.

    Si ningún registro trae unidad (por ejemplo, la prueba normal del hito 2), la columna
    queda toda en nulos y DuckDB la lee como entero, y la comparación de dirección falla.
    Solo cambia el tipo de la columna: los valores y el modelo congelado son los mismos.
    """
    import pyarrow as pa

    from identidades import modelo_co_v4

    modelo = modelo_co_v4.preparar(df)
    partes = pd.Series(
        modelo["unidad_partes"].tolist(),
        index=modelo.index,
        dtype=pd.ArrowDtype(pa.list_(pa.string())),
    )
    return modelo.assign(unidad_partes=partes)


def modelos_congelados() -> dict[str, tuple[dict, float, Any]]:
    """v3 y v4 congelados con su umbral y esquema."""
    from identidades.modelo_co_v3 import ESQUEMA_V3

    configuracion_3, umbral_3, _, _ = flujo_hito6.cargar_congelado_v3()
    configuracion_4, umbral_4, _, _ = cargar_congelado_v4()
    return {
        "v3": (configuracion_3, umbral_3, ESQUEMA_V3),
        "v4": (configuracion_4, umbral_4, replace(ESQUEMA_V4, preparar=preparar_v4_tipado)),
    }


def _resumen_union(ev: Any) -> dict[str, float]:
    m = ev.metricas["clusters"]
    return {k: float(m[k]) for k in ("precision", "recall", "f1", "pct_clusters_exactos")}


def grupos_de_los_grafos(
    registros: pd.DataFrame,
    clusters: dict[str, pd.DataFrame],
    verdad_anterior: pd.DataFrame,
    verdad_nueva: pd.DataFrame,
    personas: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Grupos con su etiqueta verdadera: grafo del hito 3 con los clústeres del v3 y grafo
    residencial con los del v3 y del v4."""
    from identidades import grafo_compartido
    from identidades import grafo_residencial as gr

    grupos = {
        "anterior_v3": grafo_compartido.unir_verdad(
            grafo_compartido.grupos_compartidos(registros, clusters["v3"]), verdad_anterior
        ),
        "residencial_v3": gr.unir_verdad(
            gr.grupos_residenciales(registros, clusters["v3"]), verdad_nueva
        ),
        "residencial_v4": gr.unir_verdad(
            gr.grupos_residenciales(registros, clusters["v4"]), verdad_nueva
        ),
    }
    if personas is not None and "tipo_predio" in personas:
        g = grupos["residencial_v4"]
        grupos["residencial_v4"] = g.assign(
            tipo_predio_verdadero=gr.tipo_predio_verdadero(g, registros, personas)
        )
    return grupos


def escenario_aplicado(
    semilla: int, modelos: dict[str, tuple[dict, float, Any]], n_personas: int = 2000
) -> dict[str, Any]:
    """Un escenario residencial con los modelos aplicados y los grupos de los dos grafos."""
    from identidades import flujo
    from identidades import grafo_residencial as gr
    from identidades.escenario_residencial import (
        EscenarioResidencial,
        verdad_compartidos_residencial,
    )

    escenario = EscenarioResidencial(n_personas, semilla)
    registros, personas, verdad_anterior = escenario.generar()
    verdad_nueva = verdad_compartidos_residencial(
        registros, personas, escenario.sospechosos, gr.normalizar_residencial
    )
    evaluaciones = {}
    for version, (configuracion, umbral, esquema) in modelos.items():
        linker = flujo.aplicar_configuracion(configuracion, registros, esquema)
        evaluaciones[version] = flujo.evaluar(linker, registros, umbral)
    clusters = {v: ev.clusters for v, ev in evaluaciones.items()}
    return {
        "semilla": semilla,
        "registros": registros,
        "personas": personas,
        "evaluaciones": evaluaciones,
        "union": {v: _resumen_union(ev) for v, ev in evaluaciones.items()},
        "grupos": grupos_de_los_grafos(
            registros, clusters, verdad_anterior, verdad_nueva, personas
        ),
        "verdad_anterior": verdad_anterior,
        "verdad": verdad_nueva,
    }


def medir_grafo(
    clasificados: pd.DataFrame, clusters: pd.DataFrame, registros: pd.DataFrame
) -> dict[str, Any]:
    """Métricas de un clasificador ya aplicado (grupos con ``prediccion`` y ``etiqueta``)."""
    from identidades import grafo_residencial as gr

    m = gr.metricas(clasificados)
    return {
        **{k: m[k] for k in ("grupos", "exactitud", "exactitud_balanceada")},
        "sospechoso": m["sospechoso"],
        "falsa_sospecha": m["falsa_sospecha"],
        "por_etiqueta": m["por_etiqueta"],
        "confusion": m["confusion"],
        "personas": gr.personas_marcadas(clasificados, clusters, registros),
    }


def medir_tipo_predio(clasificados: pd.DataFrame) -> dict[str, Any]:
    """Acierto del tipo de predio estimado en los grupos de dirección."""
    d = clasificados[clasificados["tipo"] == "direccion"]
    d = d.dropna(subset=["tipo_predio_verdadero", "tipo_predio"])
    return {
        "grupos": len(d),
        "acierto": float((d["tipo_predio"] == d["tipo_predio_verdadero"]).mean())
        if len(d)
        else 0.0,
        "confusion": pd.crosstab(d["tipo_predio_verdadero"], d["tipo_predio"]).to_dict("index"),
    }


def grafo_semillas(
    directorio: Path, semillas: list[tuple[int, int]] | None = None, n_bootstrap: int = 1000
) -> dict[str, Any]:
    """Clasificador del hito 3 contra el residencial con 8 pares de escenarios.

    En cada par, cada clasificador elige sus parámetros en el escenario de desarrollo y se
    mide una vez en el de prueba: el del hito 3 con su propio procedimiento
    (``grafo_compartido.elegir_parametros``) y los clústeres del v3; el residencial con
    los clústeres del v4 (y, para aislar el efecto del clasificador, con los del v3). Al
    final, el clasificador residencial se congela con los parámetros elegidos en los 8
    escenarios de desarrollo juntos (``clasificador.json``).
    """
    from identidades import grafo_compartido
    from identidades import grafo_residencial as gr

    verificar_congelado()
    directorio.mkdir(parents=True, exist_ok=True)
    semillas = semillas or SEMILLAS_GRAFO
    modelos = modelos_congelados()
    desarrollos_v4: list[pd.DataFrame] = []
    corridas: list[dict[str, Any]] = []
    primera: dict[str, Any] = {}
    for dev, prueba in semillas:
        a_dev = escenario_aplicado(dev, modelos)
        a_prueba = escenario_aplicado(prueba, modelos)
        desarrollos_v4.append(a_dev["grupos"]["residencial_v4"])

        p_anterior, _ = grafo_compartido.elegir_parametros(
            a_dev["grupos"]["anterior_v3"].drop(columns="etiqueta"), a_dev["verdad_anterior"]
        )
        p_v3, _ = gr.elegir_parametros([a_dev["grupos"]["residencial_v3"]])
        p_v4, _ = gr.elegir_parametros([a_dev["grupos"]["residencial_v4"]])
        g = a_prueba["grupos"]
        clasificados = {
            "anterior_v3": g["anterior_v3"].assign(
                prediccion=grafo_compartido.clasificar(g["anterior_v3"], p_anterior)
            ),
            "residencial_v3": g["residencial_v3"].assign(
                prediccion=gr.clasificar(g["residencial_v3"], p_v3)
            ),
            "residencial_v4": g["residencial_v4"].assign(
                prediccion=gr.clasificar(g["residencial_v4"], p_v4)
            ),
        }
        corrida: dict[str, Any] = {
            "semillas": [dev, prueba],
            "union_prueba": a_prueba["union"],
            "parametros": {
                "anterior": asdict(p_anterior),
                "residencial_v3": asdict(p_v3),
                "residencial_v4": asdict(p_v4),
            },
            "tipo_predio": medir_tipo_predio(clasificados["residencial_v4"]),
            "verdad_prueba": a_prueba["verdad"]
            .groupby(["tipo", "etiqueta"])
            .size()
            .unstack(fill_value=0)
            .to_dict("index"),
        }
        for nombre, c in clasificados.items():
            version = nombre.rsplit("_", 1)[1]
            corrida[nombre] = medir_grafo(
                c, a_prueba["evaluaciones"][version].clusters, a_prueba["registros"]
            )
        if not primera:
            corrida["intervalos"] = {
                k: gr.intervalos(clasificados[k], n_bootstrap)
                for k in ("anterior_v3", "residencial_v4")
            }
            primera = clasificados
        corridas.append(corrida)

    congelados, tabla = gr.elegir_parametros(desarrollos_v4)
    tabla.head(50).to_csv(directorio / "grafo_busqueda.csv", index=False, lineterminator="\n")
    _escribir(
        {
            "parametros": asdict(congelados),
            "criterio": "mayor exactitud balanceada media en los 8 escenarios de desarrollo "
            "(clústeres del v4 congelado); empate: menor falsa sospecha",
            "semillas_desarrollo": [d for d, _ in semillas],
            "parametros_grafo_hito3": dict(
                zip(("max_clientes", "min_apellido"), PARAMETROS_GRAFO_HITO3, strict=True)
            ),
        },
        directorio / "clasificador.json",
    )
    resultado = {
        "semillas": semillas,
        "corridas": corridas,
        "resumen": _resumen_semillas(corridas),
        "clasificador_congelado": asdict(congelados),
    }
    _escribir(resultado, directorio / "grafo_semillas.json")
    for nombre in ("anterior_v3", "residencial_v4"):
        primera[nombre].drop(columns=["ids_registros"]).to_csv(
            directorio / f"grafo_prueba_{nombre}.csv", index=False, lineterminator="\n"
        )
    return resultado


def _estadisticas(valores: list[float]) -> dict[str, float]:
    import numpy as np

    v = np.array(valores, float)
    return {
        "media": float(v.mean()),
        "de": float(v.std(ddof=1)) if len(v) > 1 else 0.0,
        "min": float(v.min()),
        "max": float(v.max()),
    }


def _resumen_semillas(corridas: list[dict[str, Any]]) -> dict[str, Any]:
    """Media y desviación estándar entre pares de semillas de las cifras principales."""
    resumen: dict[str, Any] = {}
    for nombre in ("anterior_v3", "residencial_v3", "residencial_v4"):
        filas = [c[nombre] for c in corridas]
        resumen[nombre] = {
            "exactitud_balanceada": _estadisticas([f["exactitud_balanceada"] for f in filas]),
            "recall_sospechoso": _estadisticas([f["sospechoso"]["recall"] for f in filas]),
            "precision_sospechoso": _estadisticas([f["sospechoso"]["precision"] for f in filas]),
            "falsa_sospecha": _estadisticas([f["falsa_sospecha"]["tasa"] for f in filas]),
            "inocentes_marcadas": _estadisticas(
                [f["personas"]["tasa_inocentes_marcadas"] for f in filas]
            ),
        }
        etiquetas = sorted({e for f in filas for e in f["falsa_sospecha"]["por_etiqueta"]})
        resumen[nombre]["falsa_sospecha_por_etiqueta"] = {
            e: _estadisticas(
                [
                    f["falsa_sospecha"]["por_etiqueta"][e]
                    for f in filas
                    if e in f["falsa_sospecha"]["por_etiqueta"]
                ]
            )
            for e in etiquetas
        }
    resumen["union"] = {
        v: {
            m: _estadisticas([c["union_prueba"][v][m] for c in corridas])
            for m in ("precision", "recall", "f1")
        }
        for v in corridas[0]["union_prueba"]
    }
    resumen["tipo_predio_acierto"] = _estadisticas([c["tipo_predio"]["acierto"] for c in corridas])
    return resumen


# ---------------------------------------------------------------------------
# Evaluación de los congelados y prueba ciega 4 (tarea 4)
# ---------------------------------------------------------------------------

TAG_GRAFO: str = "grafo-v11-congelado"
ARCHIVOS_GRAFO_CONGELADOS: list[str] = [
    "src/identidades/grafo_residencial.py",
    "docs/resultados/v11/clasificador.json",
]
SEMILLA_CIEGA_4: int = 4444
SEMILLA_RESIDENCIAL_PRUEBA: int = SEMILLAS_GRAFO[0][1]

GRUPOS_EQUIDAD_V11: dict[str, tuple[str, str]] = {
    "mujer": ("mujer", "hombre"),
    "usa_apellido_casada": ("usa apellido de casada", "no lo usa"),
    "vive_en_apartamento": ("edificio o conjunto", "casa"),
    "casa_varios_pisos": ("casa de varios pisos", "otro predio"),
    "convive_sin_parentesco": ("conviviente", "no conviviente"),
}


def verificar_grafo_congelado(tag: str = TAG_GRAFO) -> None:
    """Falla si el clasificador residencial o sus parámetros cambiaron desde ``tag``."""
    cambios = subprocess.run(
        ["git", "diff", "--quiet", tag, "--", *ARCHIVOS_GRAFO_CONGELADOS], cwd=rutas.RAIZ
    ).returncode
    if cambios:
        raise RuntimeError(f"El grafo residencial cambió desde {tag}: {ARCHIVOS_GRAFO_CONGELADOS}")


def cargar_clasificador(directorio: Path | None = None) -> Any:
    from identidades import grafo_residencial as gr

    directorio = directorio or rutas.DOCS_RESULTADOS_V11
    datos = json.loads((directorio / "clasificador.json").read_text(encoding="utf-8"))
    return gr.ParametrosGrafo(**datos["parametros"])


def registros_ciega_4(
    semilla: int = SEMILLA_CIEGA_4, n_personas: int = 2000
) -> tuple[pd.DataFrame, pd.DataFrame, dict[tuple[str, str], set[int]]]:
    """``(registros, personas, sospechosos)`` de la prueba ciega 4."""
    # Se importa aquí: el generador ciego 4 se escribió después de congelar el v4 y el grafo.
    from identidades import errores_ciegos_4

    registros, personas, sospechosos = errores_ciegos_4.generar(n_personas, semilla)
    inyectados = {(f.tipo, f.valor): set(f.personas) for f in sospechosos.itertuples(index=False)}
    return registros, personas, inyectados


def _grupos_equidad(personas: pd.DataFrame) -> dict[str, pd.Series]:
    p = personas.set_index("cluster")
    columnas = {
        "mujer": p["mujer"].astype(bool),
        "usa_apellido_casada": p["usa_apellido_casada"].astype(bool),
        "vive_en_apartamento": p["tipo_predio"].isin(["edificio", "conjunto"]),
        "casa_varios_pisos": p["tipo_predio"].eq("casa_pisos"),
        "convive_sin_parentesco": p["rol"].eq("conviviente"),
    }
    return {
        k: v.map({True: GRUPOS_EQUIDAD_V11[k][0], False: GRUPOS_EQUIDAD_V11[k][1]})
        for k, v in columnas.items()
        if v.any() and not v.all()
    }


def _diferencia_pareada_personas(
    marcadas_a: set, marcadas_b: set, poblacion: list, n: int, semilla: int
) -> dict[str, float]:
    """Diferencia pareada (b - a) de la tasa de personas marcadas, bootstrap de personas."""
    import numpy as np

    if not poblacion:
        return {"valor": 0.0, "ic_inf": 0.0, "ic_sup": 0.0}
    a = np.array([p in marcadas_a for p in poblacion], float)
    b = np.array([p in marcadas_b for p in poblacion], float)
    rng = np.random.default_rng(semilla)
    muestras = rng.integers(0, len(poblacion), size=(n, len(poblacion)))
    dif = b[muestras].mean(1) - a[muestras].mean(1)
    return {
        "valor": float(b.mean() - a.mean()),
        "ic_inf": float(np.quantile(dif, 0.025)),
        "ic_sup": float(np.quantile(dif, 0.975)),
    }


def _personas_por_estado(clasificados: pd.DataFrame, registros: pd.DataFrame) -> dict[str, set]:
    from identidades import grafo_residencial as gr

    persona_de = registros.set_index("unique_id")["cluster"]

    def personas(tabla: pd.DataFrame) -> set:
        return {persona_de[i] for ids in tabla["ids_registros"] for i in ids}

    en_patron = personas(clasificados[clasificados["etiqueta"] == "sospechoso"])
    benignas = personas(clasificados[clasificados["etiqueta"].isin(gr.BENIGNAS)]) - en_patron
    marcadas = personas(clasificados[clasificados["prediccion"] == "sospechoso"])
    return {"benignas": benignas, "en_patron": en_patron, "marcadas": marcadas}


def _falsa_sospecha_por_grupo(
    estado: dict[str, set], personas: pd.DataFrame, columna: str
) -> dict[str, dict[str, float]]:
    """Tasa de personas inocentes marcadas, por valor de una columna de personas."""
    valor_de = personas.set_index("cluster")[columna]
    salida = {}
    for valor in sorted(valor_de.dropna().unique()):
        poblacion = {p for p in estado["benignas"] if valor_de.get(p) == valor}
        if poblacion:
            salida[str(valor)] = {
                "personas": len(poblacion),
                "tasa": len(poblacion & estado["marcadas"]) / len(poblacion),
            }
    return salida


def evaluar_grafos(
    registros: pd.DataFrame,
    personas: pd.DataFrame,
    sospechosos: dict[tuple[str, str], set[int]],
    evaluaciones: dict[str, Any],
    n_bootstrap: int,
    semilla: int,
) -> dict[str, Any]:
    """Clasificador del hito 3 (parámetros publicados, clústeres del v3) contra el
    residencial congelado (clústeres del v4 y del v3) en un conjunto de prueba."""
    from identidades import grafo_compartido, grafo_residencial
    from identidades.escenario_hito3 import normalizar
    from identidades.escenario_residencial import verdad_compartidos_residencial

    verdad_anterior = verdad_compartidos_residencial(registros, personas, sospechosos, normalizar)
    verdad_nueva = verdad_compartidos_residencial(
        registros, personas, sospechosos, grafo_residencial.normalizar_residencial
    )
    clusters = {v: ev.clusters for v, ev in evaluaciones.items()}
    grupos = grupos_de_los_grafos(registros, clusters, verdad_anterior, verdad_nueva, personas)
    anterior = grafo_compartido.ParametrosClasificacion(*PARAMETROS_GRAFO_HITO3)
    nuevo = cargar_clasificador()
    clasificados = {
        "anterior_v3": grupos["anterior_v3"].assign(
            prediccion=grafo_compartido.clasificar(grupos["anterior_v3"], anterior)
        ),
        "residencial_v3": grupos["residencial_v3"].assign(
            prediccion=grafo_residencial.clasificar(grupos["residencial_v3"], nuevo)
        ),
        "residencial_v4": grupos["residencial_v4"].assign(
            prediccion=grafo_residencial.clasificar(grupos["residencial_v4"], nuevo)
        ),
    }
    resultado: dict[str, Any] = {
        "verdad": verdad_nueva.groupby(["tipo", "etiqueta"])
        .size()
        .unstack(fill_value=0)
        .to_dict("index"),
    }
    estados = {}
    for nombre, c in clasificados.items():
        version = nombre.rsplit("_", 1)[1]
        resultado[nombre] = {
            **medir_grafo(c, clusters[version], registros),
            "intervalos": grafo_residencial.intervalos(c, n_bootstrap, semilla),
        }
        estados[nombre] = _personas_por_estado(c, registros)
        resultado[nombre]["falsa_sospecha_por_tipo_hogar"] = _falsa_sospecha_por_grupo(
            estados[nombre], personas, "tipo_hogar"
        )
        resultado[nombre]["falsa_sospecha_por_tipo_predio"] = _falsa_sospecha_por_grupo(
            estados[nombre], personas, "tipo_predio"
        )
    if "tipo_predio_verdadero" in clasificados["residencial_v4"]:
        resultado["tipo_predio"] = medir_tipo_predio(clasificados["residencial_v4"])
    # Comparación pareada por persona: inocentes marcadas y personas de patrones detectadas.
    a, b = estados["anterior_v3"], estados["residencial_v4"]
    resultado["pareada_personas"] = {
        "inocentes_marcadas (residencial_v4 - anterior_v3)": _diferencia_pareada_personas(
            a["marcadas"], b["marcadas"], sorted(a["benignas"] & b["benignas"]), n_bootstrap,
            semilla,
        ),
        "personas_de_patrones_detectadas (residencial_v4 - anterior_v3)": (
            _diferencia_pareada_personas(
                a["marcadas"], b["marcadas"], sorted(a["en_patron"] | b["en_patron"]),
                n_bootstrap, semilla,
            )
        ),
    }  # fmt: skip
    resultado["clasificados"] = clasificados
    return resultado


def evaluar_conjunto(
    nombre: str,
    registros: pd.DataFrame,
    modelos: dict[str, tuple[dict, float, Any]],
    n_bootstrap: int,
    semilla: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """v3 y v4 congelados en un conjunto: métricas por clúster, vetos y diferencia pareada."""
    from identidades import flujo, flujo_hito2

    evs = {}
    resultado: dict[str, Any] = {
        "datos": {"registros": len(registros), "personas": int(registros["cluster"].nunique())}
    }
    for version, (configuracion, umbral, esquema) in modelos.items():
        linker = flujo.aplicar_configuracion(configuracion, registros, esquema)
        ev = flujo.evaluar(linker, registros, umbral, n_bootstrap, semilla)
        evs[version] = ev
        resultado[version] = {
            "umbral": umbral,
            **ev.metricas,
            "vetos": flujo_hito6.pares_vetados(ev.pred, ev.verdaderos, umbral),
        }
    contribuciones = {
        v: flujo_hito2._contribuciones(ev, registros, "clusters") for v, ev in evs.items()
    }
    resultado["diferencia_pareada"] = {
        "v4 - v3": evaluacion.bootstrap_diferencia(
            contribuciones["v3"], contribuciones["v4"], n=n_bootstrap, semilla=semilla
        )
    }
    return resultado, evs


def evaluar_congelados(directorio: Path, n_bootstrap: int = 1000) -> dict[str, Any]:
    """v3 y v4 congelados, y los dos grafos, en las pruebas de la v1.1.

    Conjuntos: prueba normal del hito 6, ciega 3 (ya mirada; referencia), escenario
    residencial de prueba (semilla 4141) y **prueba ciega 4**. En los dos últimos también
    se comparan el grafo del hito 3 y el residencial; en la ciega 4, la equidad.
    """
    from identidades import flujo_hito2, tableros

    flujo_hito6.verificar_congelado()
    verificar_congelado()
    verificar_grafo_congelado()
    directorio.mkdir(parents=True, exist_ok=True)
    modelos = modelos_congelados()

    _, prueba_normal, _ = flujo_hito6.datos_hito2_con_historia()
    ciega_3, _, _ = flujo_hito6.registros_ciega_3()
    from identidades.escenario_residencial import EscenarioResidencial

    escenario = EscenarioResidencial(2000, SEMILLA_RESIDENCIAL_PRUEBA)
    residencial, personas_res, _ = escenario.generar()
    ciega_4, personas_4, sospechosos_4 = registros_ciega_4()
    ciega_4.sample(40, random_state=SEMILLA_CIEGA_4).sort_values(["cluster", "unique_id"]).to_csv(
        directorio / "ciega4_muestra_registros.csv", index=False, lineterminator="\n"
    )
    conjuntos = {
        "prueba_normal": (prueba_normal, flujo_hito6.SEMILLA_HITO2),
        "ciega_3": (ciega_3, flujo_hito6.SEMILLA_CIEGA_3),
        "residencial_prueba": (residencial, SEMILLA_RESIDENCIAL_PRUEBA),
        "ciega_4": (ciega_4, SEMILLA_CIEGA_4),
    }
    metricas: dict[str, Any] = {
        "modelos": {
            "v3": {"tag": flujo_hito6.TAG_CONGELADO, "umbral": modelos["v3"][1]},
            "v4": {"tag": TAG_CONGELADO, "umbral": modelos["v4"][1]},
        },
        "grafos": {
            "anterior": {
                "parametros": dict(
                    zip(("max_clientes", "min_apellido"), PARAMETROS_GRAFO_HITO3, strict=True)
                )
            },
            "residencial": {"tag": TAG_GRAFO, "parametros": asdict(cargar_clasificador())},
        },  # fmt: skip
    }
    evolucion: dict[str, Any] = {}
    filas_grafo: dict[str, Any] = {}
    for nombre, (registros, semilla) in conjuntos.items():
        resultado, evs = evaluar_conjunto(nombre, registros, modelos, n_bootstrap, semilla)
        for version in modelos:
            evolucion[f"{nombre.replace('_', ' ')} · {version}"] = evs[version].metricas[
                "intervalos"
            ]["clusters"]
        extra = {
            "residencial_prueba": (personas_res, escenario.sospechosos),
            "ciega_4": (personas_4, sospechosos_4),
        }
        if nombre in extra:
            personas, sospechosos = extra[nombre]
            grafos = evaluar_grafos(registros, personas, sospechosos, evs, n_bootstrap, semilla)
            clasificados = grafos.pop("clasificados")
            resultado["grafos"] = grafos
            for k in ("anterior_v3", "residencial_v4"):
                ic = grafos[k]["intervalos"]
                filas_grafo[f"{nombre.replace('_', ' ')} · {k.replace('_', ' ')}"] = {
                    "exactitud": {"valor": grafos[k]["exactitud"], **ic["exactitud"]},
                    "recall_sospechoso": {
                        "valor": grafos[k]["sospechoso"]["recall"],
                        **ic["recall_sospechoso"],
                    },
                    "falsa_sospecha": {
                        "valor": grafos[k]["falsa_sospecha"]["tasa"],
                        **ic["falsa_sospecha"],
                    },
                }
            if nombre == "ciega_4":
                grupos = _grupos_equidad(personas)
                resultado["equidad"] = {
                    v: flujo_hito6._brechas(
                        flujo_hito6._equidad(evs[v], registros, grupos, n_bootstrap, semilla)
                    )
                    for v in modelos
                }
                clasificados["residencial_v4"].drop(columns=["ids_registros"]).to_csv(
                    directorio / "ciega4_grafo_residencial.csv", index=False, lineterminator="\n"
                )
        metricas[nombre] = resultado

    tableros.guardar_intervalos(
        flujo_hito2._tabla_intervalos(evolucion),
        "Modelos v3 y v4 congelados, por clúster (IC 95 %)",
        directorio / "v3_v4.html",
    )
    tabla_grafo = pd.DataFrame(
        [
            {"grupo": grupo, "metrica": ETIQUETAS_GRAFO[m],
             **{k: v[k] for k in ("valor", "ic_inf", "ic_sup")}}
            for grupo, ms in filas_grafo.items()
            for m, v in ms.items()
        ]
    )  # fmt: skip
    tableros.guardar_intervalos(
        tabla_grafo,
        "Grafo del hito 3 contra el residencial, por grupo compartido (IC 95 %)",
        directorio / "grafos.html",
    )
    metricas["resumen"] = _resumen_evaluacion(metricas, conjuntos)
    _escribir(metricas, directorio / "metricas.json")
    return metricas


ETIQUETAS_GRAFO: dict[str, str] = {
    "exactitud": "Exactitud",
    "recall_sospechoso": "Recall de sospechosos",
    "falsa_sospecha": "Falsa sospecha",
}


def _resumen_evaluacion(metricas: dict[str, Any], conjuntos: dict) -> dict[str, Any]:
    resumen: dict[str, Any] = {}
    for nombre in conjuntos:
        m = metricas[nombre]
        fila: dict[str, Any] = {
            v: {k: round(m[v]["clusters"][k], 4) for k in ("precision", "recall", "f1")}
            for v in ("v3", "v4")
        }
        fila["f1 v4 - v3"] = {
            k: round(m["diferencia_pareada"]["v4 - v3"]["f1"][k], 4)
            for k in ("valor", "ic_inf", "ic_sup")
        }
        if "grafos" in m:
            fila["grafo"] = {
                k: {
                    "exactitud": round(m["grafos"][k]["exactitud"], 3),
                    "recall_sospechoso": round(m["grafos"][k]["sospechoso"]["recall"], 3),
                    "falsa_sospecha": round(m["grafos"][k]["falsa_sospecha"]["tasa"], 3),
                    "inocentes_marcadas": m["grafos"][k]["personas"]["inocentes_marcadas"],
                }
                for k in ("anterior_v3", "residencial_v3", "residencial_v4")
            }
        resumen[nombre] = fila
    return resumen


# ---------------------------------------------------------------------------
# Universo de Cosmograph con las categorías nuevas (tarea 5)
# ---------------------------------------------------------------------------

COLORES_UNIVERSO: dict[str, str] = {
    "registro": "#94a3b8",
    "registro_sospechoso": "#dc2626",
    "registro_suplantador": "#dc2626",
    "registro_victima": "#f59e0b",
    "valor_relleno": "#7c3aed",
    "valor_hogar": "#16a34a",
    "valor_convivencia": "#06b6d4",
    "valor_multifamiliar": "#3b82f6",
    "valor_sospechoso": "#dc2626",
    "enlace_fuerte": "#64748b",
    "enlace_debil": "#cbd5e1",
    "enlace_relleno": "#a78bfa",
    "enlace_hogar": "#86efac",
    "enlace_convivencia": "#67e8f9",
    "enlace_multifamiliar": "#93c5fd",
    "enlace_sospechoso": "#f87171",
}


def duenos_de_documentos(clasificados: pd.DataFrame, registros: pd.DataFrame) -> dict[str, int]:
    """Cliente dueño probable de cada documento compartido: el que más registros validados
    tiene con ese documento y, a igualdad, más registros y el más antiguo."""
    duenos = {}
    base = registros.set_index("unique_id")
    for f in clasificados[clasificados["tipo"] == "documento"].itertuples():
        filas = base.loc[list(f.ids_registros)].assign(
            cliente=[f.cliente_de[i] for i in f.ids_registros]
        )
        puntaje = filas.groupby("cliente").agg(
            validados=("validado", "sum"),
            registros=("validado", "size"),
            primera=("fecha_actualizacion", "min"),
        )
        puntaje = puntaje.assign(primera=puntaje["primera"].map(lambda s: -int(s.replace("-", ""))))
        duenos[f.valor] = int(puntaje.sort_values(["validados", "registros", "primera"]).index[-1])
    return duenos


def exportar_universo_v11(
    registros: pd.DataFrame,
    clusters: pd.DataFrame,
    pred: pd.DataFrame,
    umbral: float,
    clasificados: pd.DataFrame,
    directorio: Path,
) -> dict[str, int]:
    """Puntos y enlaces para Cosmograph: registros, enlaces del modelo y valores compartidos
    con la clase del grafo residencial. En un documento compartido, los registros del
    dueño probable son "víctima" (ámbar) y los del otro cliente, "suplantador" (rojo)."""
    cliente_de = clusters.set_index("unique_id")["cluster_id"]
    clasificados = clasificados.assign(
        cliente_de=[{i: cliente_de[i] for i in ids} for ids in clasificados["ids_registros"]]
    )
    duenos = duenos_de_documentos(clasificados, registros)
    categoria: dict[int, str] = {}
    for f in clasificados[clasificados["prediccion"] == "sospechoso"].itertuples():
        for i in f.ids_registros:
            if f.tipo == "documento":
                es_dueno = f.cliente_de[i] == duenos[f.valor]
                nueva = "registro_victima" if es_dueno else "registro_suplantador"
                if categoria.get(i) != "registro_suplantador":
                    categoria[i] = nueva
            else:
                categoria.setdefault(i, "registro_sospechoso")
    puntos = [
        {
            "id": f"r{f.unique_id}",
            "categoria": categoria.get(f.unique_id, "registro"),
            "tamano": 2,
            "etiqueta": f"{f.nombres} {f.apellidos}",
        }
        for f in registros.itertuples()
    ]
    misma = pred["unique_id_l"].map(cliente_de) == pred["unique_id_r"].map(cliente_de)
    enlaces = [
        {
            "origen": f"r{int(f.unique_id_l)}",
            "destino": f"r{int(f.unique_id_r)}",
            "categoria": "enlace_fuerte" if f.match_probability >= umbral else "enlace_debil",
        }
        for f in pred[misma & (pred["match_probability"] >= 0.9)].itertuples()
    ]
    for f in clasificados.itertuples():
        id_valor = f"v:{f.tipo}:{f.valor}"
        extra = f", {f.tipo_predio}" if isinstance(f.tipo_predio, str) else ""
        puntos.append(
            {
                "id": id_valor,
                "categoria": f"valor_{f.prediccion}",
                "tamano": 4 + 2 * min(f.clientes, 20),
                "etiqueta": f"{f.tipo}: {f.valor} ({f.clientes} clientes{extra}; {f.prediccion})",
            }
        )
        enlaces += [
            {"origen": f"r{i}", "destino": id_valor, "categoria": f"enlace_{f.prediccion}"}
            for i in f.ids_registros
        ]
    for nombre, datos in (("universo_puntos.json", puntos), ("universo_enlaces.json", enlaces)):
        (directorio / nombre).write_text(
            json.dumps(datos, ensure_ascii=False), encoding="utf-8", newline="\n"
        )
    conteo = pd.Series([p["categoria"] for p in puntos]).value_counts().to_dict()
    return {"puntos": len(puntos), "enlaces": len(enlaces), **conteo}


def universo(directorio: Path) -> dict[str, Any]:
    """Universo del escenario residencial de prueba (semilla 4141) con el v4 y el grafo
    residencial congelados."""
    from identidades import flujo
    from identidades import grafo_residencial as gr
    from identidades.escenario_residencial import (
        EscenarioResidencial,
        verdad_compartidos_residencial,
    )

    verificar_congelado()
    verificar_grafo_congelado()
    directorio.mkdir(parents=True, exist_ok=True)
    configuracion, umbral, esquema = modelos_congelados()["v4"]
    escenario = EscenarioResidencial(2000, SEMILLA_RESIDENCIAL_PRUEBA)
    registros, personas, _ = escenario.generar()
    linker = flujo.aplicar_configuracion(configuracion, registros, esquema)
    ev = flujo.evaluar(linker, registros, umbral)
    verdad = verdad_compartidos_residencial(
        registros, personas, escenario.sospechosos, gr.normalizar_residencial
    )
    grupos = gr.unir_verdad(gr.grupos_residenciales(registros, ev.clusters), verdad)
    clasificados = grupos.assign(prediccion=gr.clasificar(grupos, cargar_clasificador()))
    return exportar_universo_v11(registros, ev.clusters, ev.pred, umbral, clasificados, directorio)


ARCHIVOS_PUBLICABLES: list[str] = [
    "diagnostico.json",
    "grafo_semillas.json",
    "grafo_busqueda.csv",
    "grafo_prueba_anterior_v3.csv",
    "grafo_prueba_residencial_v4.csv",
    "metricas.json",
    "v3_v4.html",
    "v3_v4.png",
    "grafos.html",
    "grafos.png",
    "ciega4_muestra_registros.csv",
    "ciega4_grafo_residencial.csv",
    "universo_puntos.json",
    "universo_enlaces.json",
]
