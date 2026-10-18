"""Auditoría 6: precisión según el volumen, extrapolación a 10 millones y umbral.

Se repite el flujo de ``identidades.escala.correr`` (mismos pasos y parámetros, sin tocar
``data/escala``) en 10 mil (5 semillas), 30 mil, 100 mil y 300 mil registros, y se agrega
el punto publicado de 1 millón. En cada tamaño:

- dos modelos: **reentrenado** (lo que mide el hito 5) y **v2 congelado** (parámetros del
  hito 2b, λ reestimada sin etiquetas), ambos con los correos de relleno anulados;
- métricas por clúster a varios umbrales y el umbral de menor costo 10·FP + FN (solo
  diagnóstico: mira etiquetas);
- composición de los falsos positivos directos (pares sobre el umbral entre personas
  distintas): familiares, mismo documento, homónimos, contacto compartido u otro.

Extrapolación: ajuste log-log de los pares falsos inducidos y de los aciertos contra el
número de registros, **validado** prediciendo 300 mil y 1 millón con un ajuste hecho solo
con 10 mil a 100 mil.

Uso: ``python audit/a6_escala.py [correr] [analizar]``.
"""

from __future__ import annotations

import math
import sys
import time
from typing import Any

import altair as alt
import numpy as np
import pandas as pd
from splink import DuckDBAPI, Linker, block_on

from identidades import escala, evaluacion, modelo, rutas, sinteticos, tableros
from identidades.modelo_co_v2 import ESQUEMA_V2

import _comun as c

SALIDA = c.RESULTADOS / "a6_escala.json"
CORRIDAS = c.CACHE / "a6_corridas.json"
UMBRALES = [
    0.9,
    0.99,
    0.999,
    0.9999,
    0.99999,
    0.999999,
    0.9999999,
    1 - 1e-8,
    1 - 1e-9,
    1 - 1e-10,
    1 - 1e-11,
]
UMBRAL = 0.9999
PLAN: list[tuple[int, int]] = [
    (10_000, 7000), (10_000, 11), (10_000, 22), (10_000, 33), (10_000, 44),
    (30_000, 7000), (30_000, 11),
    (100_000, 7000),
    (300_000, 7000),
]  # fmt: skip


def generar(n: int, semilla: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return sinteticos.generar(round(n / escala.REGISTROS_POR_PERSONA), semilla)


def raiz_familiar(personas: pd.DataFrame) -> pd.Series:
    padre = personas.set_index("cluster")["familiar_de"]
    raiz = pd.Series(personas["cluster"].to_numpy(), index=personas["cluster"].to_numpy())
    for _ in range(50):
        siguiente = padre.reindex(raiz.to_numpy()).to_numpy()
        nuevo = np.where(pd.isna(siguiente), raiz.to_numpy(), siguiente).astype(int)
        if np.array_equal(nuevo, raiz.to_numpy()):
            break
        raiz = pd.Series(nuevo, index=raiz.index)
    return raiz


def entrenar_reentrenado(preparado: pd.DataFrame) -> Linker:
    """Exactamente los pasos de entrenamiento de ``escala.correr``."""
    settings = modelo.crear_settings(ESQUEMA_V2.bloqueos_exactos, ESQUEMA_V2)
    linker = Linker(preparado, settings, db_api=DuckDBAPI())
    linker.training.estimate_probability_two_random_records_match(
        ESQUEMA_V2.reglas_deterministicas, recall=modelo.RECALL_DETERMINISTICO
    )
    linker.training.estimate_u_using_random_sampling(max_pairs=1e7, seed=42)
    for cols in escala.BLOQUEOS_EM_ESCALA:
        linker.training.estimate_parameters_using_expectation_maximisation(block_on(*cols))
    return linker


def congelado(preparado: pd.DataFrame) -> Linker:
    """v2 congelado (m, u y bloqueo del hito 2b) con λ reestimada sin etiquetas."""
    cfg, _ = c.modelo_v2()
    linker = Linker(preparado, cfg, db_api=DuckDBAPI())
    linker.training.estimate_probability_two_random_records_match(
        ESQUEMA_V2.reglas_deterministicas, recall=modelo.RECALL_DETERMINISTICO
    )
    return linker


def clasificar_fp(fp: pd.DataFrame, prep: pd.DataFrame, raiz: pd.Series) -> pd.Series:
    """Motivo de cada falso positivo directo, en orden de prioridad."""
    p = prep.set_index("unique_id")
    izq, der = p.loc[fp["unique_id_l"]], p.loc[fp["unique_id_r"]]

    def igual(col: str) -> np.ndarray:
        a, b = izq[col].to_numpy(), der[col].to_numpy()
        return np.array(
            [x == y if pd.notna(x) and pd.notna(y) else False for x, y in zip(a, b, strict=True)]
        )

    familia = raiz.reindex(fp["persona_l"]).to_numpy() == raiz.reindex(fp["persona_r"]).to_numpy()
    motivo = np.select(
        [familia, igual("documento"), igual("nombre_completo") & igual("primer_apellido"),
         igual("telefono") | igual("email") | igual("domicilio")],
        ["familiar", "mismo documento", "homónimo (mismo nombre y apellido)", "contacto compartido"],
        default="otro",
    )  # fmt: skip
    return pd.Series(motivo, index=fp.index)


def analizar_corrida(nombre: str, linker: Linker, prep: pd.DataFrame, registros: pd.DataFrame,
                     raiz: pd.Series) -> dict[str, Any]:  # fmt: skip
    inicio = time.perf_counter()
    df_pred = linker.inference.predict(threshold_match_probability=escala.UMBRAL_PREDICCION)
    pares = df_pred.as_pandas_dataframe()[
        ["unique_id_l", "unique_id_r", "match_probability", "match_weight"]
    ]
    segundos = time.perf_counter() - inicio
    ids = registros["unique_id"].to_numpy()
    persona = registros.set_index("unique_id")["cluster"]
    por_umbral = {}
    for u in UMBRALES:
        cl = c.clusters_de_pares(ids, pares, u)
        m = evaluacion.metricas_cluster(cl, registros)
        por_umbral[str(u)] = {**c.resumen(m), "costo": 10 * m["fp"] + m["fn"]}
    cl = c.clusters_de_pares(ids, pares, UMBRAL)
    asignacion = cl.assign(persona=cl["unique_id"].map(persona))
    personas_por_cliente = asignacion.groupby("cluster_id")["persona"].nunique()
    mezclados = personas_por_cliente[personas_por_cliente > 1]
    tam = asignacion.groupby("cluster_id").size()
    # Pares falsos inducidos por clúster mezclado: pares del clúster menos pares intra-persona.
    intra = asignacion.groupby(["cluster_id", "persona"]).size()
    intra_pares = (intra * (intra - 1) // 2).groupby(level=0).sum()
    fp_inducidos = (tam * (tam - 1) // 2 - intra_pares.reindex(tam.index).fillna(0)).loc[
        mezclados.index
    ]
    raices = (
        asignacion.assign(raiz=asignacion["persona"].map(raiz))
        .groupby("cluster_id")["raiz"]
        .nunique()
    )
    solo_familia = raices.loc[mezclados.index] == 1

    sobre = pares[pares["match_probability"] >= UMBRAL].assign(
        persona_l=lambda d: d["unique_id_l"].map(persona), persona_r=lambda d: d["unique_id_r"].map(persona)
    )  # fmt: skip
    fp = sobre[sobre["persona_l"] != sobre["persona_r"]]
    motivos = clasificar_fp(fp, prep, raiz) if len(fp) else pd.Series(dtype=str)
    return {
        "modelo": nombre,
        "lambda": linker.misc.save_model_to_json()["probability_two_random_records_match"],
        "segundos_prediccion": segundos,
        "pares_desde_0_9": len(pares),
        "por_umbral": por_umbral,
        "umbral_min_costo": min(por_umbral, key=lambda u: (por_umbral[u]["costo"], -float(u))),
        "mezclas": {
            "clientes_mezclados": int(len(mezclados)),
            "personas_en_clientes_mezclados": int(mezclados.sum()),
            "max_registros_en_un_cliente": int(tam.max()),
            "fp_inducidos": int(fp_inducidos.sum()),
            "fp_inducidos_top10_clientes": int(fp_inducidos.sort_values().tail(10).sum()),
            "fp_inducidos_en_mezclas_solo_familiares": int(fp_inducidos[solo_familia].sum()),
            "clientes_mezclados_solo_familiares": int(solo_familia.sum()),
        },
        "fp_directos": {
            "total": int(len(fp)),
            "por_motivo": motivos.value_counts().to_dict(),
            "peso_medio_por_motivo": fp.assign(m=motivos)
            .groupby("m")["match_weight"]
            .mean()
            .to_dict()
            if len(fp)
            else {},
        },
    }


def correr() -> None:
    previas = c.json.loads(CORRIDAS.read_text(encoding="utf-8")) if CORRIDAS.exists() else {}
    for n, semilla in PLAN:
        clave = f"{n}_{semilla}"
        if clave in previas:
            continue
        registros, personas = generar(n, semilla)
        if n == 100_000 and semilla == 7000:
            cache = rutas.DATA / "escala" / "registros_100000.parquet"
            if cache.exists():
                publicada = pd.read_parquet(cache)
                igual = publicada.astype(str).equals(registros.astype(str))
                print("100 mil idénticos a data/escala:", igual, flush=True)
        raiz = raiz_familiar(personas)
        prep = escala.preparar(registros)
        tam_familia = raiz.value_counts()
        resultado = {"n_objetivo": n, "semilla": semilla, "registros": len(registros),
                     "personas": int(registros["cluster"].nunique()),
                     "familiares": float(personas["familiar_de"].notna().mean()),
                     "pares_de_personas_familiares": int((tam_familia * (tam_familia - 1) // 2).sum())}  # fmt: skip
        inicio = time.perf_counter()
        lk = entrenar_reentrenado(prep)
        resultado["segundos_entrenamiento"] = time.perf_counter() - inicio
        resultado["reentrenado"] = analizar_corrida("reentrenado", lk, prep, registros, raiz)
        del lk
        resultado["congelado"] = analizar_corrida(
            "congelado", congelado(prep), prep, registros, raiz
        )
        previas[clave] = resultado
        c.guardar_json(previas, CORRIDAS)
        for m in ("reentrenado", "congelado"):
            r = resultado[m]["por_umbral"][str(UMBRAL)]
            print(f"{clave:14s} {m:11s} λ={resultado[m]['lambda']:.2e} P={r['precision']:.4f} "
                  f"R={r['recall']:.4f} FP={r['fp']} óptimo={resultado[m]['umbral_min_costo']} "
                  f"motivos={resultado[m]['fp_directos']['por_motivo']}", flush=True)  # fmt: skip


# ------------------------------------------------------------------------------ análisis


def _ajuste(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """y = a·x^b en log-log, con error estándar de b."""
    lx, ly = np.log(x), np.log(y)
    b, a = np.polyfit(lx, ly, 1)
    resid = ly - (a + b * lx)
    se = math.sqrt(resid @ resid / max(len(x) - 2, 1) / ((lx - lx.mean()) @ (lx - lx.mean())))
    return {"a": float(a), "b": float(b), "se_b": float(se)}


def _predecir(aj: dict[str, float], x: float, sigmas: float = 0.0) -> float:
    return float(math.exp(aj["a"] + (aj["b"] + sigmas * aj["se_b"]) * math.log(x)))


def analizar() -> dict[str, Any]:
    corridas = c.json.loads(CORRIDAS.read_text(encoding="utf-8"))
    publicado = c.json.loads(
        (rutas.REPORTS_HITO5 / "escala_1000000.json").read_text(encoding="utf-8")
    )["calidad"]
    filas = []
    for clave, r in corridas.items():
        for m in ("reentrenado", "congelado"):
            u = r[m]["por_umbral"][str(UMBRAL)]
            filas.append({"clave": clave, "n": r["registros"], "n_objetivo": r["n_objetivo"],
                          "semilla": r["semilla"], "modelo": m, "lambda": r[m]["lambda"],
                          **{k: u[k] for k in ("precision", "recall", "fp", "fn", "tp", "pct_clusters_exactos")},
                          "umbral_min_costo": float(r[m]["umbral_min_costo"]),
                          "fp_directos": r[m]["fp_directos"]["total"],
                          **{f"motivo_{k}": v for k, v in r[m]["fp_directos"]["por_motivo"].items()},
                          **r[m]["mezclas"]})  # fmt: skip
    t = pd.DataFrame(filas)
    t = pd.concat([t, pd.DataFrame([{"clave": "1000000_7000 (publicado)", "n": 995_688,
                                     "n_objetivo": 1_000_000, "semilla": 7000, "modelo": "reentrenado",
                                     **{k: publicado[k] for k in ("precision", "recall", "fp", "fn", "tp",
                                                                   "pct_clusters_exactos")}}])],
                  ignore_index=True)  # fmt: skip
    t.to_csv(c.RESULTADOS / "a6_escala.csv", index=False, lineterminator="\n")

    re = t[t["modelo"] == "reentrenado"]
    por_n = re.groupby("n_objetivo").agg(n=("n", "mean"), fp=("fp", "mean"), tp=("tp", "mean"),
                                         fn=("fn", "mean"), precision=("precision", "mean"),
                                         precision_de=("precision", "std"),
                                         recall=("recall", "mean"))  # fmt: skip
    chicos = por_n[por_n.index <= 100_000]
    extrap = {}
    for nombre, datos_ajuste in (("ajuste_10k_a_100k", chicos), ("ajuste_todos", por_n)):
        aj_fp = _ajuste(datos_ajuste["n"].to_numpy(), datos_ajuste["fp"].to_numpy())
        aj_tp = _ajuste(datos_ajuste["n"].to_numpy(), datos_ajuste["tp"].to_numpy())
        aj_fn = _ajuste(datos_ajuste["n"].to_numpy(), datos_ajuste["fn"].to_numpy())
        preds = {}
        for objetivo in (300_000, 1_000_000, 10_000_000):
            n = objetivo * 0.9957  # registros reales por objetivo (~99,6 %)
            tp = _predecir(aj_tp, n)
            pr = {s: tp / (tp + _predecir(aj_fp, n, s)) for s in (-2, 0, 2)}
            fn = _predecir(aj_fn, n)
            preds[str(objetivo)] = {
                "precision": pr[0], "precision_rango_2se": [pr[2], pr[-2]],
                "recall": tp / (tp + fn), "fp_inducidos": _predecir(aj_fp, n),
                "observado": (por_n.loc[objetivo, ["precision", "recall"]].to_dict()
                              if objetivo in por_n.index else None),
            }  # fmt: skip
        extrap[nombre] = {"fp": aj_fp, "tp": aj_tp, "fn": aj_fn, "predicciones": preds}
    co = t[t["modelo"] == "congelado"].groupby("n_objetivo").agg(n=("n", "mean"), fp=("fp", "mean"),
                                                               tp=("tp", "mean"))  # fmt: skip
    aj_fp, aj_tp = (
        _ajuste(co["n"].to_numpy(), co["fp"].to_numpy()),
        _ajuste(co["n"].to_numpy(), co["tp"].to_numpy()),
    )
    extrap["congelado_10k_a_300k"] = {"fp": aj_fp, "tp": aj_tp, "predicciones": {}}
    for objetivo in (1_000_000, 10_000_000):
        n = objetivo * 0.9957
        tp = _predecir(aj_tp, n)
        pr = {s_: tp / (tp + _predecir(aj_fp, n, s_)) for s_ in (-2, 0, 2)}
        extrap["congelado_10k_a_300k"]["predicciones"][str(objetivo)] = {
            "precision": pr[0],
            "precision_rango_2se": [pr[2], pr[-2]],
            "observado": None,
        }
    resultado = {
        "tabla": t.to_dict("records"),
        "por_tamano_reentrenado": por_n.reset_index().to_dict("records"),
        "extrapolacion": extrap,
        "umbral_optimo_por_tamano": t.groupby(["modelo", "n_objetivo"])["umbral_min_costo"]
        .agg(lambda s: sorted(set(s)))
        .reset_index()
        .to_dict("records"),
        "costo_por_umbral": {
            k: {m: r[m]["por_umbral"] for m in ("reentrenado", "congelado")}
            for k, r in corridas.items()
        },  # fmt: skip
    }
    c.guardar_json(resultado, SALIDA)
    graficos(t, extrap)
    return resultado


def graficos(t: pd.DataFrame, extrap: dict[str, Any]) -> None:
    etiquetas = {"ajuste_todos": "reentrenado", "congelado_10k_a_300k": "congelado"}
    proy = pd.DataFrame([
        {"n": int(o) * 0.9957, "precision": p_["precision"], "inf": p_["precision_rango_2se"][0],
         "sup": p_["precision_rango_2se"][1], "modelo": etiquetas[k]}
        for k, e in extrap.items() if k in etiquetas for o, p_ in e["predicciones"].items()
        if int(o) >= 1_000_000
    ])  # fmt: skip
    ultimo = t.sort_values("n").groupby("modelo").tail(1)[["n", "precision", "modelo"]]
    proy = pd.concat([ultimo.assign(inf=ultimo["precision"], sup=ultimo["precision"]), proy])
    escala_y = alt.Scale(domain=[0.85, 1.0], clamp=True)
    eje_x = alt.X(
        "n:Q", title="Registros (escala log)", scale=alt.Scale(type="log", domain=[5000, 2e7])
    )
    color = alt.Color("modelo:N", title="Modelo", scale=alt.Scale(domain=["congelado", "reentrenado"],
                                                                   range=["#2563eb", "#d97706"]))  # fmt: skip
    puntos = alt.Chart(t).mark_point(filled=True, size=70).encode(
        x=eje_x, y=alt.Y("precision:Q", title="Precisión por clúster al umbral 0,9999", scale=escala_y),
        color=color, tooltip=["clave", "modelo", "precision", "recall", "fp"],
    )  # fmt: skip
    lineas = (
        alt.Chart(proy)
        .mark_line(strokeDash=[5, 4])
        .encode(x=eje_x, y=alt.Y("precision:Q", scale=escala_y), color=color)
    )
    bandas = (
        alt.Chart(proy[proy["n"] > 2e6])
        .mark_errorbar(thickness=2)
        .encode(x=eje_x, y=alt.Y("inf:Q", scale=escala_y, title=""), y2="sup:Q", color=color)
    )
    grafico = alt.layer(bandas, lineas, puntos).properties(
        width=560,
        height=320,
        title="Precisión según el volumen: medida (puntos) y proyectada a 10 millones (±2 EE)",
    )
    tableros._guardar_grafico(grafico, c.RESULTADOS / "a6_escala.html")


def main() -> None:
    pasos = sys.argv[1:] or ["correr", "analizar"]
    if "correr" in pasos:
        correr()
    if "analizar" in pasos:
        r = analizar()
        for nombre, e in r["extrapolacion"].items():
            print(nombre, {k: (round(v["precision"], 4), [round(x, 4) for x in v["precision_rango_2se"]],
                               v["observado"]) for k, v in e["predicciones"].items()})  # fmt: skip


if __name__ == "__main__":
    main()
