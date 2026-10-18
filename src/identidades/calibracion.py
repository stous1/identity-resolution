"""Calibración de las probabilidades del modelo y zona gris por bandas de peso.

La auditoría (hallazgo A3) mostró que la probabilidad de Splink no es una probabilidad en
la zona de decisión: pares con p ≈ 0,98 resultan verdaderos entre el 0 y el 11 % de las
veces en datos colombianos, porque los familiares violan la independencia entre campos.

Aquí se ajusta, **solo con datos de desarrollo**, una regresión isotónica de la verdad
sobre el peso de coincidencia (``match_weight``): una función escalonada y creciente que
da la frecuencia observada de verdaderos según el peso. Con ella se definen tres bandas de
peso: ``rechazar`` (probabilidad calibrada < 0,1), ``revisar`` (zona gris: probabilidad
calibrada >= 0,1 pero por debajo del umbral de operación) y ``aceptar`` (desde el umbral
de operación, y con probabilidad calibrada >= 0,9). Las bandas se congelan con el modelo
y se evalúan fuera de muestra.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

LIMITES_ZONA_GRIS: tuple[float, float] = (0.1, 0.9)


@dataclass(frozen=True)
class Calibracion:
    """Función escalonada: ``probabilidad[i]`` vale para pesos en [``desde[i]``, ``desde[i+1]``)."""

    desde: list[float]
    probabilidad: list[float]
    pares: int

    def aplicar(self, pesos: np.ndarray | pd.Series) -> np.ndarray:
        indice = np.searchsorted(np.asarray(self.desde), np.asarray(pesos, float), "right") - 1
        return np.asarray(self.probabilidad)[np.clip(indice, 0, len(self.desde) - 1)]

    def peso_para(self, probabilidad: float) -> float:
        """Menor peso cuya probabilidad calibrada es al menos ``probabilidad``."""
        for desde, p in zip(self.desde, self.probabilidad, strict=True):
            if p >= probabilidad:
                return desde
        return math.inf

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


def ajustar(pesos: np.ndarray | pd.Series, verdad: np.ndarray | pd.Series) -> Calibracion:
    """Regresión isotónica (algoritmo de pools adyacentes) de ``verdad`` sobre ``pesos``."""
    orden = np.argsort(np.asarray(pesos, float), kind="stable")
    x = np.asarray(pesos, float)[orden]
    y = np.asarray(verdad, float)[orden]
    # Bloques: [suma de y, cantidad, primer x]. Empates de x van al mismo bloque.
    bloques: list[list[float]] = []
    for xi, yi in zip(x, y, strict=True):
        if bloques and bloques[-1][2] == xi:
            bloques[-1][0] += yi
            bloques[-1][1] += 1
        else:
            bloques.append([yi, 1.0, xi])
        while (
            len(bloques) > 1 and bloques[-2][0] / bloques[-2][1] >= bloques[-1][0] / bloques[-1][1]
        ):
            s, n, _ = bloques.pop()
            bloques[-1][0] += s
            bloques[-1][1] += n
    return Calibracion(
        desde=[float(b[2]) for b in bloques],
        probabilidad=[float(b[0] / b[1]) for b in bloques],
        pares=len(x),
    )


def bandas(
    calibracion: Calibracion,
    limites: tuple[float, float] = LIMITES_ZONA_GRIS,
    peso_umbral: float | None = None,
) -> dict:
    """Pesos que separan rechazar, revisar (zona gris) y aceptar.

    ``aceptar`` nunca empieza por debajo del umbral de operación (``peso_umbral``): los
    pares con probabilidad calibrada alta que no llegan al umbral van a revisión.
    """
    desde_aceptar = calibracion.peso_para(limites[1])
    return {
        "probabilidad_calibrada": list(limites),
        "peso_desde_revisar": calibracion.peso_para(limites[0]),
        "peso_calibrado_0_9": desde_aceptar,
        "peso_desde_aceptar": max(desde_aceptar, peso_umbral or -math.inf),
    }


def banda(pesos: np.ndarray | pd.Series, limites: dict) -> np.ndarray:
    pesos = np.asarray(pesos, float)
    return np.where(
        pesos >= limites["peso_desde_aceptar"],
        "aceptar",
        np.where(pesos >= limites["peso_desde_revisar"], "revisar", "rechazar"),
    )


def wilson(exitos: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de Wilson del 95 % para una proporción."""
    if n == 0:
        return 0.0, 1.0
    p = exitos / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centro - margen), min(1.0, centro + margen)


def tabla_confiabilidad(
    predicha: np.ndarray | pd.Series, verdad: np.ndarray | pd.Series, cortes: np.ndarray
) -> pd.DataFrame:
    """Por intervalo de probabilidad predicha: media predicha, frecuencia observada e IC."""
    predicha = np.asarray(predicha, float)
    verdad = np.asarray(verdad, bool)
    intervalo = np.clip(np.searchsorted(cortes, predicha, "right") - 1, 0, len(cortes) - 2)
    filas = []
    for i in np.unique(intervalo):
        m = intervalo == i
        n, k = int(m.sum()), int(verdad[m].sum())
        inf, sup = wilson(k, n)
        filas.append(
            {
                "desde": float(cortes[i]),
                "hasta": float(cortes[i + 1]),
                "pares": n,
                "predicha": float(predicha[m].mean()),
                "observada": k / n,
                "ic_inf": inf,
                "ic_sup": sup,
            }
        )
    return pd.DataFrame(filas)


# Cortes de probabilidad finos cerca de 1, donde está la zona de decisión.
CORTES: np.ndarray = np.array(
    [0, 0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99, 0.999, 0.9999, 0.99999, 1.0000001]
)


def resumen(
    pesos: np.ndarray | pd.Series,
    probabilidad: np.ndarray | pd.Series,
    verdad: np.ndarray | pd.Series,
    calibracion: Calibracion,
    limites: dict,
) -> dict[str, Any]:
    """Confiabilidad antes y después de calibrar, y verdaderos observados por banda."""
    verdad = np.asarray(verdad, bool)
    calibrada = calibracion.aplicar(pesos)
    por_banda = {}
    nombres = banda(pesos, limites)
    for nombre in ("rechazar", "revisar", "aceptar"):
        m = nombres == nombre
        n, k = int(m.sum()), int(verdad[m].sum())
        por_banda[nombre] = {
            "pares": n,
            "verdaderos": k,
            "observada": k / n if n else None,
            "ic": wilson(k, n),
            "calibrada_media": float(calibrada[m].mean()) if n else None,
        }
    zona = (np.asarray(probabilidad) >= 0.9) & (np.asarray(probabilidad) < 0.9999)
    return {
        "pares": int(len(verdad)),
        "sin_calibrar": tabla_confiabilidad(probabilidad, verdad, CORTES).to_dict("records"),
        "calibrada": tabla_confiabilidad(calibrada, verdad, CORTES).to_dict("records"),
        "zona_0_9_a_0_9999_sin_calibrar": {
            "pares": int(zona.sum()),
            "predicha_media": float(np.asarray(probabilidad)[zona].mean()) if zona.any() else None,
            "observada": float(verdad[zona].mean()) if zona.any() else None,
            "calibrada_media": float(calibrada[zona].mean()) if zona.any() else None,
        },
        "bandas": por_banda,
    }
