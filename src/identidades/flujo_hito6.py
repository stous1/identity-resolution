"""Flujo del hito 6: correcciones post-auditoría.

1. **Desarrollar el v3** (``desarrollar_v3``). Desarrollo = el del hito 2 (60 % de las
   personas de la semilla 42), ahora con mudanzas y apellidos de casada reales
   (``sinteticos.agregar_historia``), más las pruebas ciegas 1 y 2 completas, que ya se
   vieron y solo sirven como desarrollo. Ahí se eligen el bloqueo, el piso de las m
   (cuántos bits puede restar como máximo un campo), el umbral y la calibración. El
   modelo se congela en el tag ``hito6-congelado``.
2. **Evaluar el v3 congelado** (``evaluar_congelado_v3``) en la prueba normal con historia
   y en una **prueba ciega 3** escrita por un subagente nuevo después de congelar, con
   equidad, línea base determinística, enfoque híbrido, vetos y calibración.
3. **Tiempo real con prevalencias** (``tiempo_real_prevalencias``), **escala con el
   modelo congelado** (``escala_congelada``) y **hito 3 con varias semillas**
   (``estabilidad_hito3``).
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from splink import DuckDBAPI, Linker

from identidades import (
    bloqueo,
    calibracion,
    datos,
    errores_ciegos,
    errores_ciegos_2,
    evaluacion,
    flujo,
    modelo,
    rutas,
    sinteticos,
)
from identidades.modelo_co_v3 import CANDIDATOS_MAX_BITS, ESQUEMA_V3

TAG_CONGELADO: str = "hito6-congelado"
ARCHIVOS_CONGELADOS: list[str] = [
    "src/identidades/modelo_co_v3.py",
    "docs/resultados/hito6/modelo.json",
    "docs/resultados/hito6/desarrollo.json",
    "docs/resultados/hito6/calibracion.json",
]
SEMILLA_HITO2: int = 42
SEMILLA_CIEGA_1: int = 2024
SEMILLA_CIEGA_2: int = 7777
SEMILLA_CIEGA_3: int = 9191
DESPLAZAMIENTOS: dict[str, int] = {"ciega_1": 100_000, "ciega_2": 200_000}

# Umbrales de desarrollo: los de siempre más 1 - 10^-8 ... 1 - 10^-11, porque la auditoría
# encontró el umbral de menor costo en el borde de la grilla anterior.
UMBRALES: np.ndarray = np.concatenate([evaluacion.UMBRALES, 1 - 10.0 ** -np.arange(8, 12)])


def _escribir(datos_json: dict, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(datos_json, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="\n",
    )


def _desplazar(registros: pd.DataFrame, desplazamiento: int) -> pd.DataFrame:
    return registros.assign(
        unique_id=registros["unique_id"] + desplazamiento,
        cluster=registros["cluster"] + desplazamiento,
    )


def datos_hito2_con_historia(
    semilla: int = SEMILLA_HITO2,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """``(desarrollo, prueba, personas)`` del hito 2 con mudanzas y apellidos de casada."""
    registros, personas = sinteticos.generar(2000, semilla)
    registros, personas = sinteticos.agregar_historia(registros, personas, semilla)
    dev, prueba = datos.dividir_por_persona(registros, 0.6, semilla)
    return dev, prueba, personas


def datos_desarrollo() -> pd.DataFrame:
    """Hito 2 con historia (desarrollo) + ciega 1 + ciega 2, con ids desplazados."""
    dev, _, _ = datos_hito2_con_historia()
    _, personas_1 = sinteticos.generar(2000, SEMILLA_CIEGA_1)
    ciega_1, _ = errores_ciegos.capturar(personas_1, semilla=SEMILLA_CIEGA_1)
    _, personas_2 = sinteticos.generar(2000, SEMILLA_CIEGA_2)
    ciega_2, _ = errores_ciegos_2.capturar(personas_2, semilla=SEMILLA_CIEGA_2)
    return pd.concat(
        [
            dev,
            _desplazar(ciega_1, DESPLAZAMIENTOS["ciega_1"]),
            _desplazar(ciega_2, DESPLAZAMIENTOS["ciega_2"]),
        ],
        ignore_index=True,
    )


def peso_de(probabilidad: float) -> float:
    """Peso de coincidencia (log2 de las odds) de una probabilidad."""
    return math.log2(probabilidad / (1 - probabilidad))


def marcar(pred: pd.DataFrame, verdaderos: pd.DataFrame) -> pd.DataFrame:
    """Predicciones con todas sus columnas más ``es_match`` (cada par aparece una vez)."""
    a, b = pred["unique_id_l"].to_numpy(), pred["unique_id_r"].to_numpy()
    llaves = pd.MultiIndex.from_arrays([np.minimum(a, b), np.maximum(a, b)])
    reales = pd.MultiIndex.from_frame(verdaderos[["id_l", "id_r"]])
    return pred.assign(es_match=llaves.isin(reales))


def pares_vetados(pred: pd.DataFrame, verdaderos: pd.DataFrame, umbral: float) -> dict[str, Any]:
    """Pares verdaderos bajo el umbral que lo superarían si su peor campo fuera neutral.

    Es la definición operativa de veto: un solo campo decide en contra de todos los demás.
    """
    marcadas = marcar(pred, verdaderos)
    columnas = [c for c in marcadas.columns if c.startswith("bf_") and not c.startswith("bf_tf")]
    aportes = np.log2(marcadas[columnas].astype(float).clip(lower=1e-300))
    peor = aportes.min(axis=1)
    campo = aportes.idxmin(axis=1).str.removeprefix("bf_")
    w = peso_de(umbral)
    vetado = (
        marcadas["es_match"]
        & (marcadas["match_weight"] < w)
        & (marcadas["match_weight"] - peor.clip(upper=0) >= w)
    )
    return {
        "pares_verdaderos": int(len(verdaderos)),
        "vetados": int(vetado.sum()),
        "por_campo": campo[vetado].value_counts().to_dict(),
        "peor_aporte_en_verdaderos": float(peor[marcadas["es_match"]].min())
        if marcadas["es_match"].any()
        else None,
    }


def _evaluar_configuracion(
    configuracion: dict, preparado: pd.DataFrame, df: pd.DataFrame, costo_fp: float, costo_fn: float
) -> dict[str, Any]:
    """Umbral de menor costo por clúster y sus métricas, con λ ya fijada en la configuración."""
    linker = Linker(preparado, configuracion, db_api=DuckDBAPI())
    df_pred = modelo.predecir(linker)
    curva = evaluacion.agregar_costo(
        flujo.curva_umbral_clusters(linker, df_pred, df, UMBRALES), costo_fp, costo_fn
    )
    umbral = evaluacion.umbral_min_costo(curva, costo_fp, costo_fn)
    fila = curva[curva["umbral"] == umbral].iloc[0]
    pred = df_pred.as_pandas_dataframe()
    return {
        "umbral": umbral,
        "costo": float(fila["costo"]),
        "clusters": {k: float(fila[k]) for k in ("precision", "recall", "f1", "fp", "fn")},
        "vetos": pares_vetados(pred, evaluacion.pares_verdaderos(df), umbral),
        "pred": pred,
        "curva": curva,
    }


def desarrollar_v3(
    directorio: Path, costo_fp: float = 10.0, costo_fn: float = 1.0
) -> dict[str, Any]:
    """Elige bloqueo, piso de las m, umbral y calibración del v3 en desarrollo."""
    directorio.mkdir(parents=True, exist_ok=True)
    df = datos_desarrollo()
    bloqueos, historial = bloqueo.seleccionar_reglas(
        df, ESQUEMA_V3.bloqueos_exactos, ESQUEMA_V3.bloqueos_candidatos, 0.005, ESQUEMA_V3.preparar
    )
    linker = modelo.crear_linker(df, modelo.crear_settings(bloqueos, ESQUEMA_V3), ESQUEMA_V3)
    modelo.entrenar(linker, ESQUEMA_V3)
    sin_piso = linker.misc.save_model_to_json()
    preparado = ESQUEMA_V3.preparar(df)

    candidatos: dict[str, dict[str, Any]] = {}
    for bits in (None, *CANDIDATOS_MAX_BITS):
        configuracion = sin_piso if bits is None else modelo.aplicar_piso_m(sin_piso, bits)
        r = _evaluar_configuracion(configuracion, preparado, df, costo_fp, costo_fn)
        r["configuracion"] = configuracion
        candidatos["sin piso" if bits is None else str(bits)] = r
    # El piso es obligatorio (ningún campo veta solo); entre los candidatos gana el de menor
    # costo y, si empatan, el más estricto (menos bits en contra).
    elegido = min(CANDIDATOS_MAX_BITS, key=lambda b: (candidatos[str(b)]["costo"], b))
    final = candidatos[str(elegido)]
    _escribir(final["configuracion"], directorio / "modelo.json")

    marcadas = marcar(final["pred"], evaluacion.pares_verdaderos(df))
    cal = calibracion.ajustar(marcadas["match_weight"], marcadas["es_match"])
    limites = calibracion.bandas(cal, peso_umbral=peso_de(final["umbral"]))
    _escribir({**cal.a_dict(), "bandas": limites}, directorio / "calibracion.json")
    final["curva"].to_csv(
        directorio / "curva_costo_desarrollo.csv", index=False, lineterminator="\n"
    )

    resumen = {
        "desarrollo": {
            "descripcion": (
                "Hito 2 con mudanzas y apellidos de casada (60 % de las personas de la semilla"
                " 42) + prueba ciega 1 + prueba ciega 2"
            ),
            "registros": len(df),
            "personas": int(df["cluster"].nunique()),
            "historia": sinteticos.Historia().__dict__,
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
        "umbral": {
            "criterio": "min_costo_cluster",
            "valor": final["umbral"],
            "peso": peso_de(final["umbral"]),
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


def cargar_congelado_v3(
    directorio: Path | None = None,
) -> tuple[dict[str, Any], float, calibracion.Calibracion, dict]:
    """Modelo v3, umbral, calibración y bandas de zona gris congelados."""
    directorio = directorio or rutas.DOCS_RESULTADOS_HITO6
    configuracion = json.loads((directorio / "modelo.json").read_text(encoding="utf-8"))
    desarrollo = json.loads((directorio / "desarrollo.json").read_text(encoding="utf-8"))
    cal = json.loads((directorio / "calibracion.json").read_text(encoding="utf-8"))
    bandas = cal.pop("bandas")
    return configuracion, desarrollo["umbral"]["valor"], calibracion.Calibracion(**cal), bandas


def verificar_congelado(tag: str = TAG_CONGELADO) -> None:
    """Falla si el esquema o el modelo v3 cambiaron desde ``tag``."""
    cambios = subprocess.run(
        ["git", "diff", "--quiet", tag, "--", *ARCHIVOS_CONGELADOS], cwd=rutas.RAIZ
    ).returncode
    if cambios:
        raise RuntimeError(f"El modelo v3 congelado cambió desde {tag}: {ARCHIVOS_CONGELADOS}")


# ---------------------------------------------------------------------------
# Evaluación del v3 congelado
# ---------------------------------------------------------------------------

GRUPOS_EQUIDAD_HITO6: dict[str, tuple[str, str]] = {
    "mujer_aparente": ("mujer", "hombre"),
    "apellido_casada": ("apellido de casada", "sin apellido de casada"),
    "con_apodo": ("con apodo", "sin apodo"),
    "rural": ("dirección rural", "dirección urbana"),
    "mudanza": ("con mudanza", "sin mudanza"),
    "nombre_compuesto": ("nombre compuesto", "nombre simple"),
    "dos_apellidos": ("dos apellidos", "un apellido"),
    "con_tilde": ("con tilde o ñ", "sin tilde"),
}
# Diagnóstico: dicen dónde falla el modelo, no a quién perjudica.
GRUPOS_DIAGNOSTICO_HITO6: dict[str, tuple[str, str]] = {
    "sin_documento": ("algún registro sin documento", "con documento"),
    "documento_alterado": ("documento alterado", "documento sin alterar"),
}

ARCHIVOS_PUBLICABLES: list[str] = [
    "modelo.json",
    "desarrollo.json",
    "calibracion.json",
    "metricas.json",
    "evolucion.html",
    "evolucion.png",
    "equidad_ciega3.html",
    "equidad_ciega3.png",
    "linea_base.html",
    "linea_base.png",
    "confiabilidad.html",
    "confiabilidad.png",
    "ciega3_muestra_registros.csv",
    "tiempo_real.json",
    "escala.json",
    "hito3_semillas.json",
]


def modelos_congelados() -> dict[str, tuple[dict, float, modelo.Esquema]]:
    """v1, v2 y v3 congelados con su umbral y esquema."""
    from identidades import flujo_hito2b, flujo_validacion, modelo_co
    from identidades.modelo_co_v2 import ESQUEMA_V2

    configuracion_3, umbral_3, _, _ = cargar_congelado_v3()
    configuracion_2, umbral_2 = flujo_hito2b.cargar_congelado_v2()
    configuracion_1, umbral_1 = flujo_validacion.cargar_congelado()
    return {
        "v3": (configuracion_3, umbral_3, ESQUEMA_V3),
        "v2": (configuracion_2, umbral_2, ESQUEMA_V2),
        "v1": (configuracion_1, umbral_1, modelo_co.esquema(True)),
    }


def registros_ciega_3(
    semilla: int = SEMILLA_CIEGA_3, n_personas: int = 2000
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """``(registros, personas, condiciones)`` de la prueba ciega 3."""
    # Se importa aquí: el generador ciego 3 se escribió para evaluar el v3 ya congelado.
    from identidades import errores_ciegos_3

    _, personas = sinteticos.generar(n_personas, semilla)
    registros, condiciones = errores_ciegos_3.capturar(personas, semilla=semilla)
    return registros, personas, condiciones


def _grupos(
    personas: pd.DataFrame, condiciones: pd.DataFrame, etiquetas: dict[str, tuple[str, str]]
) -> dict[str, pd.Series]:
    tabla = personas.set_index("cluster")
    tabla = tabla.drop(columns=[c for c in condiciones.columns if c in tabla.columns])
    tabla = tabla.join(condiciones.set_index("cluster"))
    return {
        atributo: tabla[atributo].astype(bool).map({True: si, False: no})
        for atributo, (si, no) in etiquetas.items()
        if atributo in tabla
    }


def _equidad(
    ev: flujo.Evaluacion,
    registros: pd.DataFrame,
    grupos: dict[str, pd.Series],
    n_bootstrap: int,
    semilla: int,
) -> dict[str, Any]:
    from identidades import flujo_hito2

    contribuciones = flujo_hito2._contribuciones(ev, registros, "clusters")
    return {
        atributo: evaluacion.bootstrap_por_grupo(
            *contribuciones, serie, n=n_bootstrap, semilla=semilla
        )
        for atributo, serie in grupos.items()
    }


def _brechas(equidad: dict[str, Any]) -> dict[str, Any]:
    """Diferencia de personas exactas, recall y precisión entre los dos grupos de cada atributo."""
    salida = {}
    for atributo, r in equidad.items():
        ((comparacion, d),) = r["diferencias"].items()
        salida[atributo] = {
            "diferencia": comparacion,
            "grupos": {
                g: {
                    "personas": v["personas"],
                    **{m: v[m]["valor"] for m in ("pct_clusters_exactos", "recall", "precision")},
                }
                for g, v in r["grupos"].items()
            },
            **{m: d[m] for m in ("pct_clusters_exactos", "recall", "precision")},
        }
    return salida


def evaluar_congelado_v3(directorio: Path, n_bootstrap: int = 1000) -> dict[str, Any]:
    """v3 congelado (y v2 y v1 como control) en la prueba normal con historia y la ciega 3."""
    from identidades import flujo_hito2, linea_base, tableros

    verificar_congelado()
    directorio.mkdir(parents=True, exist_ok=True)
    modelos = modelos_congelados()
    _, _, cal, bandas = cargar_congelado_v3()

    _, prueba, personas_hito2 = datos_hito2_con_historia()
    condiciones_normal = personas_hito2[["cluster", "mudanza", "apellido_casada", "mujer"]].rename(
        columns={"mujer": "mujer_aparente"}
    )
    registros_3, personas_3, condiciones_3 = registros_ciega_3()
    registros_3.sample(40, random_state=SEMILLA_CIEGA_3).sort_values(
        ["cluster", "unique_id"]
    ).to_csv(directorio / "ciega3_muestra_registros.csv", index=False, lineterminator="\n")
    conjuntos = {
        "prueba_normal": (prueba, personas_hito2, condiciones_normal, SEMILLA_HITO2),
        "ciega_3": (registros_3, personas_3, condiciones_3, SEMILLA_CIEGA_3),
    }

    metricas: dict[str, Any] = {
        "modelo_congelado": {
            "tag": TAG_CONGELADO,
            "umbral": modelos["v3"][1],
            "bandas_zona_gris": bandas,
        },
        "pesos_extremos": {k: modelo.pesos_extremos(v[0])[:3] for k, v in modelos.items()},
    }
    evolucion: dict[str, Any] = {}
    filas_base: dict[str, Any] = {}
    filas_conf: list[dict[str, Any]] = []
    for nombre, (registros, personas, condiciones, semilla) in conjuntos.items():
        evs = {}
        resultado: dict[str, Any] = {
            "datos": {"registros": len(registros), "personas": int(registros["cluster"].nunique())}
        }
        if nombre == "ciega_3":
            resultado["datos"]["condiciones"] = {
                c: int(condiciones[c].sum())
                for c in condiciones.columns
                if c != "cluster" and condiciones[c].dtype == bool
            }
        for version, (configuracion, umbral, esquema) in modelos.items():
            linker = flujo.aplicar_configuracion(configuracion, registros, esquema)
            ev = flujo.evaluar(linker, registros, umbral, n_bootstrap, semilla)
            evs[version] = ev
            resultado[version] = {
                "umbral": umbral,
                **ev.metricas,
                "vetos": pares_vetados(ev.pred, ev.verdaderos, umbral),
            }
            evolucion[f"{nombre.replace('_', ' ')} · {version}"] = ev.metricas["intervalos"][
                "clusters"
            ]
        contribuciones = {
            v: flujo_hito2._contribuciones(ev, registros, "clusters") for v, ev in evs.items()
        }
        resultado["diferencias_pareadas"] = {
            f"v3 - {v}": evaluacion.bootstrap_diferencia(
                contribuciones[v], contribuciones["v3"], n=n_bootstrap, semilla=semilla
            )
            for v in ("v2", "v1")
        }

        grupos = _grupos(personas, condiciones, GRUPOS_EQUIDAD_HITO6)
        diagnostico = _grupos(personas, condiciones, GRUPOS_DIAGNOSTICO_HITO6)
        equidad = {v: _equidad(evs[v], registros, grupos, n_bootstrap, semilla) for v in modelos}
        resultado["equidad"] = {v: _brechas(e) for v, e in equidad.items()}
        resultado["diagnostico"] = {
            v: _brechas(_equidad(evs[v], registros, diagnostico, n_bootstrap, semilla))
            for v in modelos
        }
        if nombre == "ciega_3":
            filas_eq = {
                g: {m: v[m] for m in ("recall", "pct_clusters_exactos", "precision")}
                for r in equidad["v3"].values()
                for g, v in r["grupos"].items()
            }
            tableros.guardar_intervalos(
                flujo_hito2._tabla_intervalos(filas_eq),
                "Prueba ciega 3, modelo v3: métricas por clúster por grupo de personas",
                directorio / "equidad_ciega3.html",
            )

        preparado = ESQUEMA_V3.preparar(registros)
        base = linea_base.comparar(
            preparado, registros, evs["v3"].pred, modelos["v3"][1], n_bootstrap, semilla
        )
        resultado["linea_base"] = base
        for metodo, v in base["metodos"].items():
            filas_base[f"{nombre.replace('_', ' ')} · {linea_base.METODOS[metodo]}"] = v[
                "intervalos"
            ]

        marcadas = marcar(evs["v3"].pred, evs["v3"].verdaderos)
        resultado["calibracion"] = calibracion.resumen(
            marcadas["match_weight"],
            marcadas["match_probability"],
            marcadas["es_match"],
            cal,
            bandas,
        )
        for version in ("sin_calibrar", "calibrada"):
            for fila in resultado["calibracion"][version]:
                filas_conf.append(
                    {
                        **fila,
                        "version": version.replace("_", " "),
                        "conjunto": nombre.replace("_", " "),
                    }
                )
        metricas[nombre] = resultado

    tableros.guardar_intervalos(
        flujo_hito2._tabla_intervalos(evolucion),
        "Modelos v1, v2 y v3 congelados, por clúster (IC 95 %)",
        directorio / "evolucion.html",
    )
    tableros.guardar_intervalos(
        flujo_hito2._tabla_intervalos(filas_base),
        "Reglas determinísticas, Splink v3 e híbrido, por clúster (IC 95 %)",
        directorio / "linea_base.html",
    )
    tableros.guardar_confiabilidad(
        pd.DataFrame(filas_conf),
        "Confiabilidad del v3 fuera de muestra (calibración ajustada en desarrollo)",
        directorio / "confiabilidad.html",
    )

    metricas["resumen"] = {
        nombre: {
            **{
                v: {
                    k: round(metricas[nombre][v]["clusters"][k], 4)
                    for k in ("precision", "recall", "f1", "pct_clusters_exactos")
                }
                for v in modelos
            },
            "vetados": {v: metricas[nombre][v]["vetos"]["vetados"] for v in modelos},
            "linea_base_f1": {
                m: round(r["f1"], 4) for m, r in metricas[nombre]["linea_base"]["metodos"].items()
            },
        }
        for nombre in conjuntos
    }
    _escribir(metricas, directorio / "metricas.json")
    return metricas


# ---------------------------------------------------------------------------
# Tiempo real, escala y hito 3 con varias semillas
# ---------------------------------------------------------------------------


def tiempo_real_prevalencias(
    directorio: Path,
    n_bootstrap: int = 1000,
    n_personas: int = 6000,
    max_consultas: int = 1500,
) -> dict[str, Any]:
    """Tiempo real con el v3 congelado y precisión con 1 %, 10 % y 50 % de clientes.

    Dos poblaciones: la del generador del hito 2 (como la prueba normal) y la del generador
    de la ciega 3 (otras personas y otra semilla que las de la ciega 3 por lotes).
    """
    from identidades import tiempo_real

    configuracion, umbral, _, _ = cargar_congelado_v3()
    registros_3, _, _ = registros_ciega_3(SEMILLA_CIEGA_3 + 1, n_personas)
    poblaciones = {"normal": None, "ciega_3": registros_3}
    resultado: dict[str, Any] = {"modelo": {"tag": TAG_CONGELADO, "umbral": umbral}}
    for nombre, registros in poblaciones.items():
        base_registros, consultas, _ = tiempo_real.preparar_evaluacion(
            n_personas, max_consultas=max_consultas, registros=registros
        )
        base = tiempo_real.construir_base(base_registros, configuracion, umbral)
        vinculador = tiempo_real.Vinculador(
            base, configuracion, umbral, relleno=tiempo_real.telefonos_de_relleno(base_registros)
        )
        t = tiempo_real.resultados_por_consulta(vinculador, consultas)
        tp, fp, fn = int(t["tp"].sum()), int(t["fp"].sum()), int(t["fn"].sum())
        resultado[nombre] = {
            "base": {"clientes": len(base), "registros_usados": len(base_registros)},
            "consultas": {
                "existentes": int(t["existe"].sum()),
                "nuevas": int((~t["existe"]).sum()),
            },
            "mezcla_evaluada": {
                "precision": tp / (tp + fp) if tp + fp else 0.0,
                "recall": tp / (tp + fn) if tp + fn else 0.0,
            },
            "decisiones": {
                "existentes": t[t["existe"]]["decision"].value_counts().to_dict(),
                "nuevas": t[~t["existe"]]["decision"].value_counts().to_dict(),
            },
            **tiempo_real.precision_por_prevalencia(t, n_bootstrap=n_bootstrap),
            "latencia_ms": {
                "mediana": float(t["milisegundos"].median()),
                "p95": float(t["milisegundos"].quantile(0.95)),
            },
        }
    resultado["resumen"] = {
        n: {
            "recall": round(resultado[n]["mezcla_evaluada"]["recall"], 4),
            **{
                f"precision_{float(pi):.0%}": round(v["valor"], 4)
                for pi, v in resultado[n]["precision"].items()
            },
        }
        for n in poblaciones
    }
    _escribir(resultado, directorio / "tiempo_real.json")
    return resultado


def escala_congelada(directorio: Path, tamano: int | None = None) -> dict[str, Any]:
    """100 mil y 1 millón de registros con el v3 congelado; cada tamaño en su proceso."""
    import sys
    from dataclasses import asdict

    from identidades import escala

    ruta = directorio / "escala.json"
    if tamano is None:
        script = str(rutas.RAIZ / "scripts" / "hito6.py")
        for n in escala.TAMANOS:
            subprocess.run([sys.executable, script, "escala", "--tamano", str(n)], check=True)
        return json.loads(ruta.read_text(encoding="utf-8"))
    configuracion, umbral, _, _ = cargar_congelado_v3()
    mediciones, artefactos = escala.correr_congelado(tamano, configuracion, umbral)
    previo = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    publicado = pd.read_csv(rutas.DOCS_RESULTADOS_HITO5 / "escala.csv")
    reentrenado = publicado[publicado["registros"].between(tamano * 0.95, tamano * 1.05)]
    previo[str(tamano)] = {
        "modelo": {"tag": TAG_CONGELADO, "umbral": umbral},
        "mediciones": [asdict(m) for m in mediciones],
        "congelado": artefactos["calidad"],
        "reentrenado_hito5": (
            {
                "precision": float(reentrenado["precision_cluster"].iloc[0]),
                "recall": float(reentrenado["recall_cluster"].iloc[0]),
            }
            if len(reentrenado)
            else None
        ),
        "linea_base": artefactos["linea_base"],
    }
    _escribir(previo, ruta)
    return {
        str(tamano): {
            "congelado": {k: artefactos["calidad"][k] for k in ("precision", "recall", "f1")},
            "reentrenado_hito5": previo[str(tamano)]["reentrenado_hito5"],
        }
    }


SEMILLAS_HITO3: list[tuple[int, int]] = [(3030, 3131)] + [
    (3000 + s, 3100 + s) for s in (11, 22, 33, 44, 55, 66, 77)
]


def _resumen_hito3(m: dict[str, Any]) -> dict[str, Any]:
    oro = m["registro_oro"]
    techo = oro["prueba_techo_alcanzable"]
    aciertos = {k: v["valor"] for k, v in oro["prueba_con_reglas_elegidas"].items()}
    puentes = m["puentes"]
    antes = puentes["0.9"]["prueba"]["mezclados_antes"]
    despues = puentes["0.9"]["prueba"]["mezclados_despues"]
    return {
        "reglas": oro["reglas_elegidas_en_desarrollo"],
        "union_precision": m["calidad_union"]["prueba"]["precision"],
        "union_recall": m["calidad_union"]["prueba"]["recall"],
        "oro_max_brecha_al_techo": max(techo[k] - v for k, v in aciertos.items()),
        "grafo_exactitud": m["grafo_compartido"]["prueba"]["exactitud"],
        "grafo_grupos": m["grafo_compartido"]["prueba"]["grupos"],
        "mezclados_umbral_congelado": puentes[str(m["modelo"]["umbral"])]["prueba"][
            "mezclados_antes"
        ],
        "mezclados_0_9": antes,
        "evitados_0_9": antes - despues,
        "fraccion_evitada_0_9": (antes - despues) / antes if antes else None,
    }


def estabilidad_hito3(
    directorio: Path, semillas: list[tuple[int, int]] | None = None, n_bootstrap: int = 50
) -> dict[str, Any]:
    """El hito 3 repetido con varios pares de escenarios, con el v2 (publicado) y el v3."""
    import tempfile

    from identidades import flujo_hito2b, flujo_hito3

    semillas = semillas or SEMILLAS_HITO3
    configuracion_3, umbral_3, _, _ = cargar_congelado_v3()
    modelos = {"v2": flujo_hito2b.cargar_congelado_v2(), "v3": (configuracion_3, umbral_3)}
    corridas: dict[str, list[dict[str, Any]]] = {}
    for version, congelado in modelos.items():
        corridas[version] = []
        for par in semillas:
            with tempfile.TemporaryDirectory() as tmp:
                m = flujo_hito3.ejecutar_hito3(
                    Path(tmp),
                    n_bootstrap=n_bootstrap,
                    semillas=par,
                    modelo_congelado=congelado,
                    completo=False,
                )
            corridas[version].append({"semillas": list(par), **_resumen_hito3(m)})

    def estadisticas(valores: list[float | None]) -> dict[str, float]:
        v = np.array([x for x in valores if x is not None], float)
        return {
            "media": float(v.mean()),
            "de": float(v.std(ddof=1)),
            "min": float(v.min()),
            "max": float(v.max()),
        }

    resumen: dict[str, Any] = {}
    for version, filas in corridas.items():
        numericas = [k for k, v in filas[0].items() if isinstance(v, int | float)]
        resumen[version] = {k: estadisticas([f[k] for f in filas]) for k in numericas}
        resumen[version]["reglas"] = {
            campo: pd.Series([f["reglas"][campo] for f in filas]).value_counts().to_dict()
            for campo in filas[0]["reglas"]
        }
    resultado = {"semillas": semillas, "corridas": corridas, "resumen": resumen}
    _escribir(resultado, directorio / "hito3_semillas.json")
    return resultado
