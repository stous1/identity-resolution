"""Auditoría 5: ablación, quitando una comparación a la vez.

Tres mediciones:

A. **Pesos extremos** de cada modelo congelado: log2(m/u) por nivel. Un nivel con
   |peso| > 20 bits decide solo (veto o pase directo) sin importar el resto de campos.
B. **Quitar del modelo congelado** la contribución de una comparación (sin reentrenar, mismo
   umbral y bloqueo) en cada prueba: mide cuánto carga cada campo en la decisión publicada.
C. **Reentrenar sin la comparación** con el procedimiento completo (bloqueo y umbral
   elegidos en desarrollo) para el esquema v2 (desarrollo del hito 2b, 8.952 registros) y
   el del hito 1; medir en las pruebas. Todos los conjuntos tienen menos de 10 mil registros.

Uso: ``python audit/a5_ablacion.py [A|B|C ...]``.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from identidades import flujo, flujo_hito2b, modelo
from identidades.escenario_hito3 import generar_escenario
from identidades.modelo_co_v2 import ESQUEMA_V2
from identidades.modelo_febrl import ESQUEMA_FEBRL

import _comun as c

SALIDA = c.RESULTADOS / "a5_ablacion.json"
VETO_BITS = 20.0


# ---------------------------------------------------------------------- A. pesos extremos


def pesos_extremos(cfg: dict) -> list[dict[str, Any]]:
    filas = []
    for comp in cfg["comparisons"]:
        for lvl in comp["comparison_levels"]:
            if lvl.get("is_null_level"):
                continue
            m, u = lvl.get("m_probability"), lvl.get("u_probability")
            peso = math.log2(m / u) if m and u else None
            filas.append({"comparacion": comp["output_column_name"],
                          "nivel": lvl.get("label_for_charts"), "m": m, "u": u, "peso": peso,
                          "sin_entrenar": m is None or u is None,
                          "extremo": peso is not None and abs(peso) > VETO_BITS})  # fmt: skip
    return filas


def parte_a() -> dict[str, Any]:
    modelos = {"v1 (hito2-congelado-r1)": c.modelo_v1()[0], "v2 (hito2b-congelado)": c.modelo_v2()[0],
               "hito 1": c.modelo_desarrollado("hito1")[0], "FEBRL": c.modelo_desarrollado("febrl")[0]}  # fmt: skip
    resultado = {}
    for nombre, cfg in modelos.items():
        filas = pesos_extremos(cfg)
        resultado[nombre] = {
            "extremos": [f for f in filas if f["extremo"]],
            "sin_entrenar": [f for f in filas if f["sin_entrenar"]],
            "todos": filas,
        }
        for f in resultado[nombre]["extremos"] + resultado[nombre]["sin_entrenar"]:
            print(f"A {nombre:24s} {f['comparacion']:18s} {str(f['nivel'])[:40]:40s} "
                  f"peso={f['peso']} sin_entrenar={f['sin_entrenar']}")  # fmt: skip
    return resultado


# ---------------------------------------------------------------- B. quitar sin reentrenar


def _aportes(pares: pd.DataFrame) -> pd.DataFrame:
    """Peso (bits) que aporta cada comparación a cada par, con ajuste por frecuencia."""
    aportes = {}
    for col in pares.columns:
        if col.startswith("bf_") and not col.startswith("bf_tf_adj_"):
            k = col[3:]
            bf = pares[col].astype(float)
            tf = (
                pares[f"bf_tf_adj_{k}"].astype(float).fillna(1.0)
                if f"bf_tf_adj_{k}" in pares
                else 1.0
            )
            aportes[k] = np.log2(bf * tf)
    return pd.DataFrame(aportes, index=pares.index)


def quitar_congelado(ev: c.Evaluado) -> dict[str, Any]:
    pares = ev.pares
    aportes = _aportes(pares)
    marcadas = c.pares_marcados(ev)
    clave = pd.MultiIndex.from_arrays([
        pares[["unique_id_l", "unique_id_r"]].min(axis=1), pares[["unique_id_l", "unique_id_r"]].max(axis=1)
    ])  # fmt: skip
    es_match = marcadas.set_index(["id_l", "id_r"])["es_match"].reindex(clave).to_numpy()
    ids = ev.registros["unique_id"].to_numpy()
    completo = c.resumen(c.metricas_cluster(ev.clusters, ev.registros))
    filas = {"(modelo completo)": completo}
    grupos = [[k] for k in aportes.columns]
    if {"domicilio", "municipio"} <= set(aportes.columns):
        grupos.append(["domicilio", "municipio"])
    for grupo in grupos:
        k = " y ".join(grupo)
        peso = pares["match_weight"].to_numpy() - aportes[grupo].sum(axis=1).to_numpy()
        p = 1 / (1 + np.exp2(-peso))
        cl = c.clusters_de_pares(ids, pares.assign(match_probability=p), ev.umbral)
        m = c.resumen(c.metricas_cluster(cl, ev.registros))
        verdaderos = aportes.loc[es_match, grupo].min(axis=1)
        filas[f"sin {k}"] = {
            **m,
            "delta_f1": m["f1"] - completo["f1"],
            "delta_precision": m["precision"] - completo["precision"],
            "delta_recall": m["recall"] - completo["recall"],
            "frac_verdaderos_con_veto": float((verdaderos < -VETO_BITS).mean()),
            "frac_verdaderos_con_menos_10_bits": float((verdaderos < -10).mean()),
        }
    return filas


def parte_b() -> dict[str, Any]:
    (cfg1, u1), (cfg2, u2) = c.modelo_v1(), c.modelo_v2()
    cfg_h1, u_h1 = c.modelo_desarrollado("hito1")
    cfg_f, u_f = c.modelo_desarrollado("febrl")
    esc_v1 = c.modelo_co.esquema(True)
    prueba_h2 = c.prueba_hito2()
    ciega1, ciega2 = c.ciega_1()[0], c.ciega_2()[0]
    casos = {
        "hito 1 · prueba": (cfg_h1, c.prueba_hito1()[1], modelo.ESQUEMA_FAKE_1000, u_h1),
        "FEBRL3 · prueba": (cfg_f, c.prueba_febrl()[1], ESQUEMA_FEBRL, u_f),
        "v1 · hito 2 normal": (cfg1, prueba_h2, esc_v1, u1),
        "v1 · ciega 1": (cfg1, ciega1, esc_v1, u1),
        "v1 · ciega 2": (cfg1, ciega2, esc_v1, u1),
        "v2 · hito 2 normal": (cfg2, prueba_h2, ESQUEMA_V2, u2),
        "v2 · ciega 2": (cfg2, ciega2, ESQUEMA_V2, u2),
        "v2 · hito 3 prueba": (cfg2, generar_escenario(2000, 3131)[0], ESQUEMA_V2, u2),
    }
    resultado = {}
    for nombre, (cfg, reg, esquema, u) in casos.items():
        resultado[nombre] = quitar_congelado(c.aplicar_congelado(cfg, reg, esquema, u))
        for k, f in resultado[nombre].items():
            print(f"B {nombre:20s} {k:22s} P={f['precision']:.4f} R={f['recall']:.4f} "
                  f"F1={f['f1']:.4f} veto={f.get('frac_verdaderos_con_veto', 0):.3f}", flush=True)  # fmt: skip
    return resultado


# ------------------------------------------------------------------ C. reentrenar sin ella


def sin_comparacion(esquema: modelo.Esquema, indice: int) -> modelo.Esquema:
    def comparaciones():
        return [comp for i, comp in enumerate(esquema.comparaciones()) if i != indice]

    return replace(esquema, nombre=f"{esquema.nombre}-sin{indice}", comparaciones=comparaciones)


def _nombre_comparacion(comp) -> str:
    return comp.get_comparison("duckdb").output_column_name


def reentrenar(esquema: modelo.Esquema, dev: pd.DataFrame, pruebas: dict[str, pd.DataFrame]):
    resultado = {}
    nombres = ["(completo)"] + [f"sin {_nombre_comparacion(x)}" for x in esquema.comparaciones()]
    for i, etiqueta in enumerate(nombres):
        e = esquema if i == 0 else sin_comparacion(esquema, i - 1)
        d = flujo.desarrollar(dev, esquema=e)
        cfg = d.linker.misc.save_model_to_json()
        fila = {"umbral": d.umbral,
                "bloqueos": [" & ".join(b) for b in d.bloqueos[len(e.bloqueos_exactos):]]}  # fmt: skip
        for prueba, reg in pruebas.items():
            fila[prueba] = c.resumen(c.metricas_cluster(
                c.aplicar_congelado(cfg, reg, e, d.umbral).clusters, reg))  # fmt: skip
        resultado[etiqueta] = fila
        print(f"C {esquema.nombre} {etiqueta:22s} umbral={d.umbral} " + " ".join(
            f"{p}: P={fila[p]['precision']:.4f} R={fila[p]['recall']:.4f} F1={fila[p]['f1']:.4f}"
            for p in pruebas), flush=True)  # fmt: skip
    return resultado


def parte_c() -> dict[str, Any]:
    dev_h1, prueba_h1 = c.prueba_hito1()
    dev_v2, prueba_h2 = flujo_hito2b.datos_desarrollo()
    return {
        "hito1": reentrenar(modelo.ESQUEMA_FAKE_1000, dev_h1, {"prueba": prueba_h1}),
        "v2": reentrenar(
            ESQUEMA_V2, dev_v2, {"ciega 2": c.ciega_2()[0], "hito 2 normal": prueba_h2}
        ),
    }


# ------------------------------------------- D. equidad en la ciega 1 sin los dos vetos


def parte_d() -> dict[str, Any]:
    """Brechas de la ciega 1 (v1) con y sin los aportes de domicilio y municipio.

    Solo diagnóstico: la ciega 1 ya es desarrollo del hito 2b, así que esto no elige nada.
    """
    from identidades import errores_ciegos, evaluacion, flujo_validacion, sinteticos

    _, personas = sinteticos.generar(2000, 2024)
    reg, condiciones = errores_ciegos.capturar(personas, semilla=2024)
    cfg, u = c.modelo_v1()
    ev = c.aplicar_congelado(cfg, reg, c.modelo_co.esquema(True), u)
    peso = (
        ev.pares["match_weight"].to_numpy()
        - _aportes(ev.pares)[["domicilio", "municipio"]].sum(axis=1).to_numpy()
    )
    sin_vetos = c.clusters_de_pares(
        reg["unique_id"].to_numpy(), ev.pares.assign(match_probability=1 / (1 + np.exp2(-peso))), u
    )
    grupos = flujo_validacion.grupos_de_personas(personas, condiciones)
    resultado = {}
    for nombre, clusters in (("publicado", ev.clusters), ("sin domicilio ni municipio", sin_vetos)):
        contrib = c.contribuciones_cluster(clusters, reg)
        resultado[nombre] = {"metricas": c.resumen(c.metricas_cluster(clusters, reg))}
        for atributo in ("apellido_casada", "con_apodo"):
            r = evaluacion.bootstrap_por_grupo(*contrib, grupos[atributo], n=1000)
            resultado[nombre][atributo] = {
                "grupos": {g: v["pct_clusters_exactos"] for g, v in r["grupos"].items()},
                "diferencia": r["diferencias"],
            }
    print("D", json.dumps(resultado, ensure_ascii=False, default=str)[:600])
    return resultado


def main() -> None:
    partes = {"A": parte_a, "B": parte_b, "C": parte_c, "D": parte_d}
    pedidas = sys.argv[1:] or list(partes)
    resultado = c.json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    for p in pedidas:
        resultado[p] = partes[p]()
        c.guardar_json(resultado, SALIDA)


if __name__ == "__main__":
    main()
