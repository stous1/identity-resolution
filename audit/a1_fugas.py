"""Auditoría 1: fugas de etiquetas.

Tres tipos de verificación:

1. **Estática:** dónde aparece la verdad (``cluster``, ``familiar_de``, condiciones del
   generador, ``verdad``) en ``src/identidades``, función por función.
2. **Dinámica:** invariancia de lo que no debe mirar etiquetas.
   - Entrenar el modelo (λ, u, m) con la columna ``cluster`` verdadera, barajada o
     ausente debe dar exactamente los mismos parámetros.
   - Aplicar un modelo congelado a prueba con ``cluster`` barajada debe dar exactamente
     los mismos pesos por par.
   - Renumerar ``unique_id`` al azar y barajar filas no debe cambiar las métricas: en los
     generadores los registros de una persona tienen ids consecutivos, así que cualquier
     dependencia del orden sería una fuga.
3. **Tiempo real (hito 5):** solapamiento entre base y consultas.

Uso: ``python audit/a1_fugas.py`` (desde la raíz, con el entorno del proyecto).
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

import numpy as np
import pandas as pd

from identidades import (
    escala,
    escenario_hito3,
    grafo_compartido,
    modelo,
    registro_oro,
    rutas,
    sinteticos,
    tiempo_real,
)
from identidades.modelo_co_v2 import ESQUEMA_V2

import _comun as c

SALIDA = c.RESULTADOS / "a1_fugas.json"
VERDAD = re.compile(
    r"""["'](cluster|familiar_de|familia|etiqueta|existe)["']|\bverdad\b|\bpersonas\b"""
)


# ----------------------------------------------------------------------------------------
# 1. Estática
# ----------------------------------------------------------------------------------------


def referencias_a_la_verdad() -> pd.DataFrame:
    """Funciones de ``src/identidades`` que nombran columnas o tablas de verdad."""
    filas = []
    for ruta in sorted((rutas.RAIZ / "src" / "identidades").glob("*.py")):
        texto = ruta.read_text(encoding="utf-8")
        arbol = ast.parse(texto)
        lineas = texto.splitlines()
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.FunctionDef):
                continue
            for n in range(nodo.lineno, (nodo.end_lineno or nodo.lineno) + 1):
                linea = lineas[n - 1]
                if VERDAD.search(linea) and not linea.strip().startswith("#"):
                    filas.append(
                        {
                            "modulo": ruta.stem,
                            "funcion": nodo.name,
                            "linea": n,
                            "codigo": linea.strip()[:140],
                        }  # fmt: skip
                    )
    tabla = pd.DataFrame(filas).drop_duplicates(["modulo", "funcion", "linea"])
    # Una función anidada aparece también en la exterior: se conserva la más interna.
    return tabla.sort_values(["modulo", "linea", "funcion"]).drop_duplicates(
        ["modulo", "linea"], keep="last"
    )


# ----------------------------------------------------------------------------------------
# 2. Dinámica
# ----------------------------------------------------------------------------------------


def _parametros(linker) -> dict[str, Any]:
    cfg = linker.misc.save_model_to_json()
    return {
        "lambda": cfg["probability_two_random_records_match"],
        "niveles": [
            (
                comp["output_column_name"],
                lvl.get("label_for_charts"),
                lvl.get("m_probability"),
                lvl.get("u_probability"),
            )  # fmt: skip
            for comp in cfg["comparisons"]
            for lvl in comp["comparison_levels"]
        ],
    }


def entrenar(df: pd.DataFrame, esquema: modelo.Esquema) -> dict[str, Any]:
    linker = modelo.crear_linker(df, modelo.crear_settings(esquema=esquema), esquema)
    modelo.entrenar(linker, esquema)
    return _parametros(linker)


def _max_dif(a: dict, b: dict) -> float:
    dif = abs(a["lambda"] - b["lambda"])
    for x, y in zip(a["niveles"], b["niveles"], strict=True):
        for p, q in zip(x[2:], y[2:], strict=True):
            if p is not None and q is not None:
                dif = max(dif, abs(p - q))
    return dif


def entrenamiento_no_mira_etiquetas(rng: np.random.Generator) -> dict[str, Any]:
    """λ, u y m con la verdad, con la verdad barajada y sin ella (esquemas v1, v2 y escala)."""
    df = c.desarrollo_hito2()
    barajada = df.assign(cluster=rng.permutation(df["cluster"].to_numpy()))
    sin = df.drop(columns="cluster")
    resultado = {}
    for nombre, esquema in (("v1", c.modelo_co.esquema(True)), ("v2", ESQUEMA_V2)):
        real = entrenar(df, esquema)
        resultado[nombre] = {
            "max_dif_barajada": _max_dif(real, entrenar(barajada, esquema)),
            "max_dif_sin_columna": _max_dif(real, entrenar(sin, esquema)),
        }
    return resultado


def _pesos(ev: c.Evaluado, mapa: dict[int, int] | None = None) -> pd.Series:
    p = ev.pares[["unique_id_l", "unique_id_r", "match_weight"]].copy()
    if mapa is not None:
        p["unique_id_l"] = p["unique_id_l"].map(mapa)
        p["unique_id_r"] = p["unique_id_r"].map(mapa)
    a = p[["unique_id_l", "unique_id_r"]].min(axis=1)
    b = p[["unique_id_l", "unique_id_r"]].max(axis=1)
    return pd.Series(
        p["match_weight"].to_numpy(), index=pd.MultiIndex.from_arrays([a, b])
    ).sort_index()


def aplicacion_no_mira_etiquetas_ni_orden(rng: np.random.Generator) -> dict[str, Any]:
    """Modelos congelados en prueba: verdad barajada y ids renumerados con filas barajadas."""
    resultado = {}
    casos = {
        "v1 en prueba normal hito 2": (c.prueba_hito2(), c.modelo_v1(), c.modelo_co.esquema(True)),
        "v2 en ciega 2": (c.ciega_2()[0], c.modelo_v2(), ESQUEMA_V2),
    }
    for nombre, (reg, (cfg, umbral), esquema) in casos.items():
        base = c.aplicar_congelado(cfg, reg, esquema, umbral)
        m_base = c.resumen(c.metricas_cluster(base.clusters, reg))

        barajada = reg.assign(cluster=rng.permutation(reg["cluster"].to_numpy()))
        ev_b = c.aplicar_congelado(cfg, barajada, esquema, umbral)
        dif_b = float((_pesos(base) - _pesos(ev_b)).abs().max())

        nuevos = rng.permutation(len(reg)) + 500_000
        mapa_inv = dict(zip(nuevos, reg["unique_id"], strict=True))
        renumerada = (
            reg.assign(unique_id=nuevos).sample(frac=1, random_state=1).reset_index(drop=True)
        )
        ev_r = c.aplicar_congelado(cfg, renumerada, esquema, umbral)
        w_r = _pesos(ev_r, mapa_inv)
        w_0 = _pesos(base)
        clusters_r = ev_r.clusters.assign(unique_id=ev_r.clusters["unique_id"].map(mapa_inv))
        m_r = c.resumen(c.metricas_cluster(clusters_r, reg))
        resultado[nombre] = {
            "pares": len(base.pares),
            "max_dif_peso_verdad_barajada": dif_b,
            "mismos_pares_renumerado": bool(w_r.index.equals(w_0.index)),
            "max_dif_peso_renumerado": float((w_0 - w_r.reindex(w_0.index)).abs().max()),
            "metricas_original": m_base,
            "metricas_renumerado": m_r,
        }
    return resultado


def escala_no_mira_etiquetas(rng: np.random.Generator) -> dict[str, Any]:
    """El reentrenamiento de ``escala.correr`` (sin etiquetas) en 10 mil registros."""
    registros, _ = sinteticos.generar(round(10_000 / escala.REGISTROS_POR_PERSONA), 7000)

    def parametros(df: pd.DataFrame) -> dict[str, Any]:
        from splink import DuckDBAPI, Linker, block_on

        preparado = escala.preparar(df)
        linker = Linker(
            preparado, modelo.crear_settings(ESQUEMA_V2.bloqueos_exactos, ESQUEMA_V2),
            db_api=DuckDBAPI(),
        )  # fmt: skip
        linker.training.estimate_probability_two_random_records_match(
            ESQUEMA_V2.reglas_deterministicas, recall=modelo.RECALL_DETERMINISTICO
        )
        linker.training.estimate_u_using_random_sampling(max_pairs=1e6, seed=42)
        for cols in escala.BLOQUEOS_EM_ESCALA:
            linker.training.estimate_parameters_using_expectation_maximisation(block_on(*cols))
        return _parametros(linker)

    real = parametros(registros)
    barajada = parametros(
        registros.assign(cluster=rng.permutation(registros["cluster"].to_numpy()))
    )
    return {"registros": len(registros), "max_dif_barajada": _max_dif(real, barajada)}


# ----------------------------------------------------------------------------------------
# 3. Diseño a la medida del generador (no es fuga de etiquetas, pero es circular)
# ----------------------------------------------------------------------------------------


def diseno_a_la_medida() -> dict[str, Any]:
    """¿Las reglas del hito 3 codifican directamente parámetros del generador?"""
    orden_banco = sorted(registro_oro.RANGO_CANAL, key=registro_oro.RANGO_CANAL.get, reverse=True)
    orden_generador = sorted(
        escenario_hito3.CONFIABILIDAD, key=escenario_hito3.CONFIABILIDAD.get, reverse=True
    )
    marcados = {
        "celular": [
            grafo_compartido.es_generico("celular", escenario_hito3.normalizar("celular", v))
            for v in sinteticos.TELEFONOS_RELLENO
        ],
        "correo": [
            grafo_compartido.es_generico("correo", escenario_hito3.normalizar("correo", v))
            for v in sinteticos.CORREOS_RELLENO
        ],
        "direccion": [
            grafo_compartido.es_generico("direccion", escenario_hito3.normalizar("direccion", v))
            for v in sinteticos.DIRECCIONES_RELLENO
        ],
    }
    return {
        "orden_canales_registro_oro": orden_banco,
        "orden_confiabilidad_generador": orden_generador,
        "mismo_orden": orden_banco == orden_generador,
        "relleno_del_generador_marcado_como_generico": {k: all(v) for k, v in marcados.items()},
    }


# ----------------------------------------------------------------------------------------
# 4. Tiempo real: base y consultas
# ----------------------------------------------------------------------------------------

CAMPOS_CRUDOS = ["numero_documento", "nombres", "apellidos", "fecha_nacimiento", "celular",
                 "correo", "direccion", "ciudad"]  # fmt: skip


def tiempo_real_solapamiento(semilla: int = 5050) -> dict[str, Any]:
    """Qué tan parecidas son las consultas de clientes existentes a lo que ya está en la base."""
    registros_base, consultas, personas = tiempo_real.preparar_evaluacion(3000, semilla)
    existentes = consultas[consultas["existe"]]
    nuevas = consultas[~consultas["existe"]]

    def clave(df: pd.DataFrame) -> pd.Series:
        return df[CAMPOS_CRUDOS].astype("string").fillna("<nulo>").agg("|".join, axis=1)

    base_claves = set(zip(registros_base["cluster"], clave(registros_base), strict=True))
    identicas = [
        (p, k) in base_claves for p, k in zip(existentes["cluster"], clave(existentes), strict=True)
    ]
    prep_base = c.PREPARAR_V2(registros_base)
    prep_cons = c.PREPARAR_V2(existentes)
    doc_base = set(zip(registros_base["cluster"], prep_base["documento"], strict=True))
    mismo_doc = [
        (p, d) in doc_base and pd.notna(d)
        for p, d in zip(existentes["cluster"], prep_cons["documento"], strict=True)
    ]
    familia = personas.set_index("cluster")["familiar_de"]
    en_base = set(registros_base["cluster"])
    nuevas_con_familiar = [
        (pd.notna(familia.get(p)) and familia.get(p) in en_base)
        or bool(set(familia[familia == p].index) & en_base)
        for p in nuevas["cluster"]
    ]
    return {
        "registros_base": len(registros_base),
        "consultas": len(consultas),
        "ids_compartidos": len(set(consultas["unique_id"]) & set(registros_base["unique_id"])),
        "personas_nuevas_en_base": len(set(nuevas["cluster"]) & en_base),
        "existentes_identicas_a_un_registro_de_la_base": float(np.mean(identicas)),
        "existentes_con_mismo_documento_estandarizado_en_la_base": float(np.mean(mismo_doc)),
        "nuevas_con_un_familiar_en_la_base": float(np.mean(nuevas_con_familiar)),
        "prevalencia_existentes_en_consultas": float(consultas["existe"].mean()),
        "nota_previa": "El vinculador fija lambda = 1/N clientes (suma 1 sobre la base), "
        "mientras que la mitad de las consultas son personas nuevas.",
    }


def main() -> None:
    rng = np.random.default_rng(20261018)
    tabla = referencias_a_la_verdad()
    tabla.to_csv(c.RESULTADOS / "a1_referencias_verdad.csv", index=False, lineterminator="\n")
    resultado = {
        "referencias_estaticas": {
            "total_lineas": len(tabla),
            "funciones": tabla.groupby("modulo")["funcion"]
            .apply(lambda s: sorted(set(s)))
            .to_dict(),
        },
        "entrenamiento_no_mira_etiquetas": entrenamiento_no_mira_etiquetas(rng),
        "aplicacion_no_mira_etiquetas_ni_orden": aplicacion_no_mira_etiquetas_ni_orden(rng),
        "escala_no_mira_etiquetas": escala_no_mira_etiquetas(rng),
        "diseno_a_la_medida_del_generador": diseno_a_la_medida(),
        "tiempo_real": tiempo_real_solapamiento(),
    }
    c.guardar_json(resultado, SALIDA)
    print(json.dumps({k: v for k, v in resultado.items() if k != "referencias_estaticas"},
                     indent=2, ensure_ascii=False, default=str))  # fmt: skip


if __name__ == "__main__":
    main()
