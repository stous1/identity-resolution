"""Auditoría 8: "¿ya es cliente?" según el tamaño de la base, la previa y la prevalencia.

El hito 5 mide con una base de 1.351 clientes y una mezcla de consultas 50/50 (existentes y
nuevas), con la previa fijada en 1/N. Aquí, con el mismo vinculador y el modelo v2
congelado:

1. **Tamaño de la base:** 3.000 (el publicado), 10.000 y 30.000 personas sintéticas.
2. **Previa:** la decisión con 1/N (publicada) y con π/N para π = 0,5 (la prevalencia real
   de la evaluación) y 0,1. Cambiar la previa equivale a sumar log2(π) al peso.
3. **Prevalencia en producción:** precisión esperada si solo una fracción π de las
   consultas fuera de clientes existentes, con las tasas observadas.

Uso: ``python audit/a8_tiempo_real.py``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from identidades import flujo_hito2b, tiempo_real

import _comun as c

SALIDA = c.RESULTADOS / "a8_tiempo_real.json"
TAMANOS = (3000, 10_000, 30_000)
UMBRALES = (0.99, 0.999, 0.9999, 0.99999, 0.999999)


def consultas_puntuadas(n_personas: int, semilla: int = 5050) -> tuple[pd.DataFrame, int]:
    cfg, umbral = flujo_hito2b.cargar_congelado_v2()
    registros_base, consultas, _ = tiempo_real.preparar_evaluacion(n_personas, semilla)
    base = tiempo_real.construir_base(registros_base, cfg, umbral)
    v = tiempo_real.Vinculador(
        base, cfg, umbral, relleno=tiempo_real.telefonos_de_relleno(registros_base)
    )
    persona = base.set_index("unique_id")["cluster"]
    filas = []
    for fila in consultas.to_dict("records"):
        r = v.consultar(fila)
        cliente = r.get("cliente", {}).get("cliente_id")
        filas.append({
            "existe": fila["existe"],
            "peso": r["peso"] if r["peso"] is not None else -np.inf,
            "correcto": cliente is not None and persona.get(cliente) == fila["cluster"],
            "ms": r["milisegundos"],
        })  # fmt: skip
    return pd.DataFrame(filas), len(base)


def metricas(t: pd.DataFrame, umbral: float, desplazamiento: float = 0.0) -> dict[str, Any]:
    peso_umbral = math.log2(umbral / (1 - umbral))
    cliente = (t["peso"] + desplazamiento) >= peso_umbral
    tp = int((cliente & t["existe"] & t["correcto"]).sum())
    fp = int((cliente & ~(t["existe"] & t["correcto"])).sum())
    fp_nuevas = int((cliente & ~t["existe"]).sum())
    existentes, nuevas = int(t["existe"].sum()), int((~t["existe"]).sum())
    return {
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / existentes,
        "fp": fp,
        "tasa_fp_en_nuevas": fp_nuevas / nuevas,
        "cliente_equivocado": int((cliente & t["existe"] & ~t["correcto"]).sum()),
    }


def precision_por_prevalencia(recall: float, tasa_fp: float, nuevas: int) -> dict[str, Any]:
    """Precisión si una fracción π de las consultas fuera de clientes (tasas observadas).

    Con 0 falsos positivos observados se usa la cota superior de 95 % (regla del 3: 3/n).
    """
    tasa = tasa_fp if tasa_fp > 0 else 3 / nuevas
    salida = {}
    for pi in (0.5, 0.2, 0.1, 0.05, 0.01):
        salida[str(pi)] = recall * pi / (recall * pi + tasa * (1 - pi))
    return {"tasa_fp_usada": tasa, "cota_si_cero": tasa_fp == 0, "precision": salida}


def main() -> None:
    resultado = {}
    for n in TAMANOS:
        t, clientes = consultas_puntuadas(n)
        por_umbral = {str(u): metricas(t, u) for u in UMBRALES}
        previa = {str(pi): metricas(t, 0.9999, math.log2(pi)) for pi in (1.0, 0.5, 0.1)}
        publicado = por_umbral["0.9999"]
        resultado[str(n)] = {
            "personas": n,
            "clientes_en_base": clientes,
            "consultas": len(t),
            "por_umbral": por_umbral,
            "previa_pi_sobre_N": previa,
            "prevalencia": precision_por_prevalencia(
                publicado["recall"], publicado["tasa_fp_en_nuevas"], int((~t["existe"]).sum())
            ),
            "latencia_mediana_ms": float(t["ms"].median()),
            "latencia_p95_ms": float(t["ms"].quantile(0.95)),
        }
        print(n, clientes, publicado, resultado[str(n)]["prevalencia"], flush=True)
        c.guardar_json(resultado, SALIDA)


if __name__ == "__main__":
    main()
