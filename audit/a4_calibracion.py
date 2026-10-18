"""Auditoría 4: calibración de la probabilidad predicha en los conjuntos de prueba.

Para cada modelo y prueba se toman todos los pares que pasan el bloqueo, se agrupan por
peso de coincidencia (log2 de los odds; las probabilidades se concentran en 0 y 1 y los
bins en probabilidad esconden casi todo) y se compara la probabilidad media predicha con
la frecuencia observada de pares verdaderos, con intervalo de Wilson.

Además, en el punto de operación: falsos positivos esperados según el modelo
(suma de 1 − p sobre los pares sobre el umbral) frente a los observados.

Salidas: ``a4_calibracion.json``, ``a4_confiabilidad.png`` (diagrama de confiabilidad)
y ``a4_logodds.png`` (log-odds observados contra el peso predicho).
"""

from __future__ import annotations

from typing import Any

import altair as alt
import numpy as np
import pandas as pd

from identidades import modelo, tableros
from identidades.escenario_hito3 import generar_escenario
from identidades.modelo_co_v2 import ESQUEMA_V2
from identidades.modelo_febrl import ESQUEMA_FEBRL

import _comun as c

SALIDA = c.RESULTADOS / "a4_calibracion.json"
BORDES = np.array([-np.inf, -20, -15, -10, -5, -2.5, 0, 2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20,
                   25, 30, np.inf])  # fmt: skip
Z = 1.96


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centro = (p + Z**2 / (2 * n)) / (1 + Z**2 / n)
    radio = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / (1 + Z**2 / n)
    return float(max(0.0, centro - radio)), float(min(1.0, centro + radio))


def evaluados() -> dict[str, c.Evaluado]:
    (cfg1, u1), (cfg2, u2) = c.modelo_v1(), c.modelo_v2()
    cfg_h1, u_h1 = c.modelo_desarrollado("hito1")
    cfg_f, u_f = c.modelo_desarrollado("febrl")
    prueba_h2 = c.prueba_hito2()
    ciega1, ciega2 = c.ciega_1()[0], c.ciega_2()[0]
    esc_v1 = c.modelo_co.esquema(True)
    return {
        "hito 1 · fake_1000": c.aplicar_congelado(cfg_h1, c.prueba_hito1()[1],
                                                  modelo.ESQUEMA_FAKE_1000, u_h1),
        "FEBRL3": c.aplicar_congelado(cfg_f, c.prueba_febrl()[1], ESQUEMA_FEBRL, u_f),
        "hito 2 normal · v1": c.aplicar_congelado(cfg1, prueba_h2, esc_v1, u1),
        "hito 2 normal · v2": c.aplicar_congelado(cfg2, prueba_h2, ESQUEMA_V2, u2),
        "ciega 1 · v1": c.aplicar_congelado(cfg1, ciega1, esc_v1, u1),
        "ciega 2 · v1": c.aplicar_congelado(cfg1, ciega2, esc_v1, u1),
        "ciega 2 · v2": c.aplicar_congelado(cfg2, ciega2, ESQUEMA_V2, u2),
        "hito 3 prueba · v2": c.aplicar_congelado(cfg2, generar_escenario(2000, 3131)[0],
                                                  ESQUEMA_V2, u2),
    }  # fmt: skip


def calibrar(marcadas: pd.DataFrame, umbral: float) -> dict[str, Any]:
    p = marcadas["match_probability"].to_numpy()
    y = marcadas["es_match"].to_numpy().astype(float)
    w = marcadas["match_weight"].to_numpy()
    bins = []
    indice = np.digitize(w, BORDES[1:-1])
    for i in range(len(BORDES) - 1):
        en = indice == i
        n = int(en.sum())
        if not n:
            continue
        k = int(y[en].sum())
        inf, sup = wilson(k, n)
        bins.append({
            "peso_desde": float(BORDES[i]), "peso_hasta": float(BORDES[i + 1]), "pares": n,
            "verdaderos": k, "p_predicha": float(p[en].mean()), "frecuencia_observada": k / n,
            "obs_ic_inf": inf, "obs_ic_sup": sup,
            "peso_medio": float(np.clip(w[en], -40, 60).mean()),
            "dentro_del_ic": bool(inf <= p[en].mean() <= sup),
        })  # fmt: skip
    sobre = p >= umbral
    eps = 1e-12
    return {
        "pares": len(p),
        "verdaderos": int(y.sum()),
        "brier": float(np.mean((p - y) ** 2)),
        "log_loss": float(-np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))),
        "ece": float(
            sum(b["pares"] * abs(b["p_predicha"] - b["frecuencia_observada"]) for b in bins)
            / len(p)
        ),  # fmt: skip
        "bins": bins,
        "operacion": {
            "umbral": umbral,
            "pares_sobre_umbral": int(sobre.sum()),
            "fp_esperados_segun_modelo": float((1 - p[sobre]).sum()),
            "fp_observados": int((sobre & (y == 0)).sum()),
            "verdaderos_esperados_bajo_umbral": float(p[~sobre].sum()),
            "verdaderos_observados_bajo_umbral": int(((~sobre) & (y == 1)).sum()),
        },
        "zona_alta": _zona(p, y, 0.9, 0.9999),
    }


def _zona(p: np.ndarray, y: np.ndarray, desde: float, hasta: float) -> dict[str, Any]:
    """Pares con probabilidad en [desde, hasta): la zona gris del hito 5."""
    en = (p >= desde) & (p < hasta)
    n, k = int(en.sum()), int(y[en].sum())
    return {"desde": desde, "hasta": hasta, "pares": n, "verdaderos": k,
            "p_predicha_media": float(p[en].mean()) if n else None,
            "frecuencia_observada": k / n if n else None,
            "ic": wilson(k, n) if n else None}  # fmt: skip


def graficos(resultado: dict[str, Any]) -> None:
    """Diagramas por prueba. Las capas no llevan datos propios: los hereda el facet."""
    t = pd.DataFrame(
        [{"prueba": nombre, **b} for nombre, r in resultado.items() for b in r["bins"]]
    )

    def logit(q: pd.Series) -> pd.Series:
        q = q.clip(1e-6, 1 - 1e-6)
        return np.log2(q / (1 - q))

    t = t.assign(
        logodds_obs=logit(t["frecuencia_observada"]),
        logodds_inf=logit(t["obs_ic_inf"]),
        logodds_sup=logit(t["obs_ic_sup"]),
        logodds_pred=logit(t["p_predicha"]),
    )
    for archivo, (x, y, lo, hi, dom, tx, ty, titulo) in {
        "a4_confiabilidad.html": ("p_predicha", "frecuencia_observada", "obs_ic_inf", "obs_ic_sup", [0, 1],
                                  "Probabilidad predicha (media del bin)", "Frecuencia observada",
                                  "Diagrama de confiabilidad por prueba (bins por peso; IC de Wilson)"),
        "a4_logodds.html": ("logodds_pred", "logodds_obs", "logodds_inf", "logodds_sup", [-20, 20],
                            "log2 odds predichos", "log2 odds observados",
                            "Log-odds observados contra predichos (recortados a ±20)"),
    }.items():  # fmt: skip
        escala = alt.Scale(domain=dom, clamp=True)
        diagonal = (
            alt.Chart()
            .mark_rule(color="#94a3b8", strokeDash=[4, 4])
            .encode(
                x=alt.datum(dom[0]), y=alt.datum(dom[0]), x2=alt.datum(dom[1]), y2=alt.datum(dom[1])
            )
        )
        barras = (
            alt.Chart()
            .mark_rule(color="#64748b")
            .encode(x=alt.X(f"{x}:Q", scale=escala), y=alt.Y(f"{lo}:Q", scale=escala), y2=f"{hi}:Q")
        )
        puntos = alt.Chart().mark_point(filled=True, color="#2563eb").encode(
            x=alt.X(f"{x}:Q", title=tx, scale=escala),
            y=alt.Y(f"{y}:Q", title=ty, scale=escala),
            size=alt.Size("pares:Q", scale=alt.Scale(type="log", range=[15, 300]), title="Pares"),
            tooltip=["prueba", "peso_desde", "peso_hasta", "pares", "verdaderos", "p_predicha",
                     "frecuencia_observada"],
        )  # fmt: skip
        grafico = (
            alt.layer(diagonal, barras, puntos, data=t)
            .properties(width=220, height=220)
            .facet(facet=alt.Facet("prueba:N", title=None), columns=4)
            .properties(title=titulo)
        )
        tableros._guardar_grafico(grafico, c.RESULTADOS / archivo)


def main() -> None:
    resultado = {}
    for nombre, ev in evaluados().items():
        r = calibrar(c.pares_marcados(ev), ev.umbral)
        resultado[nombre] = r
        op = r["operacion"]
        print(f"{nombre:22s} pares={r['pares']:6d} ECE={r['ece']:.4f} brier={r['brier']:.5f} "
              f"FP esperados={op['fp_esperados_segun_modelo']:.2f} observados={op['fp_observados']} "
              f"| verdaderos bajo umbral esperados={op['verdaderos_esperados_bajo_umbral']:.1f} "
              f"observados={op['verdaderos_observados_bajo_umbral']}", flush=True)  # fmt: skip
    c.guardar_json(resultado, SALIDA)
    graficos(resultado)


def solo_graficos() -> None:
    graficos(c.json.loads(SALIDA.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
