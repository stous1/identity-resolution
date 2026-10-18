"""Selección de reglas de bloqueo medida contra la verdad conocida.

Calcula en DuckDB qué pares genera cada regla, sin entrenar el modelo, y elige de
forma voraz las reglas aproximadas que más recall del bloqueo agregan. La selección
usa etiquetas, así que solo debe correr sobre el conjunto de desarrollo.
"""

from __future__ import annotations

from collections.abc import Callable

import duckdb
import pandas as pd

from identidades import evaluacion, modelo

Regla = tuple[str, ...]
Par = tuple[int, int]


def pares_de_regla(df: pd.DataFrame, regla: Regla) -> set[Par]:
    """Pares ``(id menor, id mayor)`` que coinciden en todas las expresiones de ``regla``.

    ``df`` debe tener las columnas que usa ``regla`` (las que agrega ``preparar``).
    Como en Splink, un valor nulo nunca coincide.
    """
    claves = ", ".join(f"{expr} as k{i}" for i, expr in enumerate(regla))
    condicion = " and ".join(f"a.k{i} = b.k{i}" for i in range(len(regla)))
    con = duckdb.connect()
    con.register("df", df)
    filas = con.sql(
        f"""
        with t as (select unique_id, {claves} from df)
        select a.unique_id, b.unique_id
        from t a join t b on a.unique_id < b.unique_id and {condicion}
        """
    ).fetchall()
    return set(filas)


def seleccionar_reglas(
    df: pd.DataFrame,
    exactas: list[Regla],
    candidatas: list[Regla],
    min_ganancia: float = 0.005,
    preparar: Callable[[pd.DataFrame], pd.DataFrame] = modelo.preparar,
) -> tuple[list[Regla], pd.DataFrame]:
    """Agrega reglas candidatas de forma voraz mientras suban el recall del bloqueo.

    Parte de ``exactas``. En cada paso agrega la candidata que más pares verdaderos
    nuevos cubre (a igual cobertura, la que genera menos comparaciones) y se detiene
    cuando la mejor ganancia de recall es menor que ``min_ganancia``.

    Devuelve las reglas elegidas y el historial de pasos (reglas, comparaciones y
    recall del bloqueo acumulados).
    """
    preparado = preparar(df)
    verdaderos = {
        tuple(p) for p in evaluacion.pares_verdaderos(df)[["id_l", "id_r"]].to_numpy().tolist()
    }
    if not verdaderos:
        raise ValueError("No hay pares verdaderos: no se puede medir el recall del bloqueo")
    pares = {regla: pares_de_regla(preparado, regla) for regla in exactas + candidatas}

    def _paso(nombre: str, reglas: list[Regla], ganancia: float) -> dict:
        union = set().union(*(pares[r] for r in reglas))
        return {
            "regla_agregada": nombre,
            "reglas": len(reglas),
            "pares_comparados": len(union),
            "recall_bloqueo": len(union & verdaderos) / len(verdaderos),
            "ganancia_recall": ganancia,
        }

    elegidas = list(exactas)
    historial = [_paso("exactas", elegidas, 0.0)]
    cubiertos = set().union(*(pares[r] for r in elegidas)) & verdaderos
    restantes = list(candidatas)
    while restantes:
        mejor = max(
            restantes,
            key=lambda r: (len((pares[r] & verdaderos) - cubiertos), -len(pares[r])),
        )
        ganancia = len((pares[mejor] & verdaderos) - cubiertos) / len(verdaderos)
        if ganancia < min_ganancia:
            break
        elegidas.append(mejor)
        restantes.remove(mejor)
        cubiertos |= pares[mejor] & verdaderos
        historial.append(_paso(" & ".join(mejor), elegidas, ganancia))
    return elegidas, pd.DataFrame(historial)
