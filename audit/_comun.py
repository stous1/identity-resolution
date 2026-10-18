"""Utilidades compartidas por los scripts de auditoría.

Nada de aquí modifica ``src/`` ni ``docs/resultados/``: se reutilizan las funciones del
proyecto tal como están y las salidas van a ``audit/resultados/`` (pequeñas, para el
informe) o a ``audit/_cache/`` (intermedias, ignoradas por git).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from identidades import (
    datos,
    errores_ciegos,
    errores_ciegos_2,
    evaluacion,
    flujo,
    flujo_hito2b,
    flujo_validacion,
    modelo,
    modelo_co,
    rutas,
    sinteticos,
)
from identidades.modelo_co_v2 import ESQUEMA_V2

AUDIT: Path = rutas.RAIZ / "audit"
RESULTADOS: Path = AUDIT / "resultados"
CACHE: Path = AUDIT / "_cache"


def guardar_json(obj: Any, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=_a_json),
        encoding="utf-8",
        newline="\n",
    )


def _a_json(valor: Any) -> Any:
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, np.floating):
        return float(valor)
    if isinstance(valor, np.bool_):
        return bool(valor)
    if isinstance(valor, set | tuple):
        return list(valor)
    return str(valor)


# ----------------------------------------------------------------------------------------
# Componentes conectados (equivalente a la agrupación de Splink: transitiva)
# ----------------------------------------------------------------------------------------


def componentes(ids: np.ndarray, izq: np.ndarray, der: np.ndarray) -> pd.DataFrame:
    """Clústeres ``(unique_id, cluster_id)`` de los grafos con aristas ``izq``-``der``.

    ``cluster_id`` es el menor ``unique_id`` del componente. Los registros sin aristas
    quedan solos.
    """
    ids = np.asarray(ids)
    posicion = {int(v): i for i, v in enumerate(ids)}
    padre = np.arange(len(ids))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for a, b in zip(izq, der, strict=True):
        ra, rb = raiz(posicion[int(a)]), raiz(posicion[int(b)])
        if ra != rb:
            padre[max(ra, rb)] = min(ra, rb)
    raices = np.array([raiz(i) for i in range(len(ids))])
    tabla = pd.DataFrame({"unique_id": ids, "_r": raices})
    minimo = tabla.groupby("_r")["unique_id"].transform("min")
    return pd.DataFrame({"unique_id": ids, "cluster_id": minimo.to_numpy()})


def clusters_por_reglas(preparado: pd.DataFrame, reglas: list[list[str]]) -> pd.DataFrame:
    """Une registros que coinciden exactamente (sin nulos) en todas las columnas de alguna regla.

    Es la línea base determinística: cada regla es una lista de columnas; dos registros
    quedan juntos si en alguna regla coinciden en todas sus columnas, y la unión es
    transitiva (como la agrupación de Splink).
    """
    izq, der = [], []
    for regla in reglas:
        sub = preparado[["unique_id", *regla]].dropna(subset=regla)
        if sub.empty:
            continue
        clave = sub[regla].astype(str).agg("\x1f".join, axis=1)
        primero = sub.groupby(clave)["unique_id"].transform("min")
        mascara = primero.to_numpy() != sub["unique_id"].to_numpy()
        izq.append(sub["unique_id"].to_numpy()[mascara])
        der.append(primero.to_numpy()[mascara])
    if izq:
        izq_a, der_a = np.concatenate(izq), np.concatenate(der)
    else:
        izq_a = der_a = np.array([], dtype=int)
    return componentes(preparado["unique_id"].to_numpy(), izq_a, der_a)


def clusters_de_pares(
    ids: np.ndarray, pares: pd.DataFrame, umbral: float, col: str = "match_probability"
) -> pd.DataFrame:
    """Clústeres de los pares con ``col >= umbral``."""
    sobre = pares[pares[col] >= umbral]
    return componentes(ids, sobre["unique_id_l"].to_numpy(), sobre["unique_id_r"].to_numpy())


# ----------------------------------------------------------------------------------------
# Métricas con intervalos (mismas funciones del proyecto)
# ----------------------------------------------------------------------------------------


def contribuciones_cluster(clusters: pd.DataFrame, df: pd.DataFrame):
    return evaluacion.contribuciones_por_persona(evaluacion.pares_inducidos(clusters), df, clusters)


def metricas_cluster(
    clusters: pd.DataFrame, df: pd.DataFrame, n_bootstrap: int = 0, semilla: int = 0
) -> dict[str, Any]:
    """Métricas por clúster del proyecto, con intervalos por bootstrap de personas."""
    m = evaluacion.metricas_cluster(clusters, df)
    if n_bootstrap:
        m["intervalos"] = evaluacion.bootstrap_por_persona(
            *contribuciones_cluster(clusters, df), n=n_bootstrap, semilla=semilla
        )
    return m


def diferencia_pareada(
    clusters_a: pd.DataFrame,
    clusters_b: pd.DataFrame,
    df: pd.DataFrame,
    n_bootstrap: int = 1000,
    semilla: int = 0,
) -> dict[str, dict[str, float]]:
    """``b - a`` por clúster, bootstrap pareado por persona (función del proyecto)."""
    return evaluacion.bootstrap_diferencia(
        contribuciones_cluster(clusters_a, df),
        contribuciones_cluster(clusters_b, df),
        n=n_bootstrap,
        semilla=semilla,
    )


def resumen(m: dict[str, Any]) -> dict[str, float]:
    claves = ("precision", "recall", "f1", "pct_clusters_exactos", "fp", "fn", "tp")
    return {k: m[k] for k in claves if k in m}


# ----------------------------------------------------------------------------------------
# Conjuntos de prueba reportados y modelos que se evalúan en ellos
# ----------------------------------------------------------------------------------------


@dataclass
class Evaluado:
    """Un modelo aplicado a un conjunto de prueba: pares puntuados y clústeres."""

    nombre: str
    registros: pd.DataFrame
    pares: pd.DataFrame
    clusters: pd.DataFrame
    umbral: float
    linker: Any = None


def aplicar_congelado(
    configuracion: dict, registros: pd.DataFrame, esquema: modelo.Esquema, umbral: float
) -> Evaluado:
    """Aplica un modelo guardado (λ reestimada sin etiquetas) y agrupa al umbral."""
    linker = flujo.aplicar_configuracion(configuracion, registros, esquema)
    df_pred = modelo.predecir(linker)
    pares = df_pred.as_pandas_dataframe()
    clusters = modelo.agrupar(linker, df_pred, umbral).as_pandas_dataframe()
    return Evaluado(
        esquema.nombre, registros, pares, clusters[["unique_id", "cluster_id"]], umbral, linker
    )


def modelo_v1() -> tuple[dict, float]:
    return flujo_validacion.cargar_congelado()


def modelo_v2() -> tuple[dict, float]:
    return flujo_hito2b.cargar_congelado_v2()


def prueba_hito2(semilla: int = 42, n: int = 2000) -> pd.DataFrame:
    registros, _ = sinteticos.generar(n, semilla)
    return datos.dividir_por_persona(registros, 0.6, semilla)[1]


def desarrollo_hito2(semilla: int = 42, n: int = 2000) -> pd.DataFrame:
    registros, _ = sinteticos.generar(n, semilla)
    return datos.dividir_por_persona(registros, 0.6, semilla)[0]


def ciega_1(semilla: int = 2024, n: int = 2000) -> tuple[pd.DataFrame, pd.DataFrame]:
    _, personas = sinteticos.generar(n, semilla)
    registros, condiciones = errores_ciegos.capturar(personas, semilla=semilla)
    return registros, personas


def ciega_2(semilla: int = 7777, n: int = 2000) -> tuple[pd.DataFrame, pd.DataFrame]:
    _, personas = sinteticos.generar(n, semilla)
    registros, condiciones = errores_ciegos_2.capturar(personas, semilla=semilla)
    return registros, personas


def prueba_hito1(semilla: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = datos.cargar_fake_1000()
    return datos.dividir_por_persona(df, 0.6, semilla)


def prueba_febrl(semilla: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    return datos.dividir_por_persona(datos.cargar_febrl3(), 0.6, semilla)


def modelo_desarrollado(nombre: str) -> tuple[dict, float]:
    """Modelo del hito 1 o de FEBRL desarrollado como en el proyecto (caché en ``_cache``).

    Estos dos no se versionan como congelados: se repite exactamente el procedimiento
    publicado (partición con semilla 42, ``flujo.desarrollar``).
    """
    ruta = CACHE / f"modelo_{nombre}.json"
    if ruta.exists():
        guardado = json.loads(ruta.read_text(encoding="utf-8"))
        return guardado["configuracion"], guardado["umbral"]
    from identidades.modelo_febrl import ESQUEMA_FEBRL

    if nombre == "hito1":
        dev, _ = prueba_hito1()
        d = flujo.desarrollar(dev)
    elif nombre == "febrl":
        dev, _ = prueba_febrl()
        d = flujo.desarrollar(dev, esquema=ESQUEMA_FEBRL)
    else:
        raise ValueError(nombre)
    guardado = {"configuracion": d.linker.misc.save_model_to_json(), "umbral": d.umbral}
    guardar_json(guardado, ruta)
    return guardado["configuracion"], guardado["umbral"]


def pares_marcados(ev: Evaluado) -> pd.DataFrame:
    """Pares comparados con ``match_probability``, ``match_weight`` y ``es_match``."""
    verdaderos = evaluacion.pares_verdaderos(ev.registros)
    marcadas = evaluacion.marcar_verdaderos(
        ev.pares[["unique_id_l", "unique_id_r", "match_probability"]], verdaderos
    )
    pesos = ev.pares.assign(
        id_l=ev.pares[["unique_id_l", "unique_id_r"]].min(axis=1),
        id_r=ev.pares[["unique_id_l", "unique_id_r"]].max(axis=1),
    )[["id_l", "id_r", "match_weight"]].drop_duplicates(["id_l", "id_r"])
    return marcadas.merge(pesos, on=["id_l", "id_r"])


# Preparaciones para la línea base (mismas que usan los modelos comparados).
PREPARAR_V1: Callable[[pd.DataFrame], pd.DataFrame] = modelo_co.preparar_estandarizado
PREPARAR_V2: Callable[[pd.DataFrame], pd.DataFrame] = ESQUEMA_V2.preparar


def nombre_completo(preparado: pd.DataFrame) -> pd.Series:
    """Nombres + primer apellido + segundo apellido (vacío si no hay); nulo si falta algo."""
    completo = (
        preparado["nombre_completo"].astype("string")
        + " | "
        + preparado["primer_apellido"].astype("string")
        + " | "
        + preparado["segundo_apellido"].astype("string").fillna("")
    )
    return completo.where(
        preparado["nombre_completo"].notna() & preparado["primer_apellido"].notna()
    )
