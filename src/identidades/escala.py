"""Escala con DuckDB: tiempo y memoria de preparar, entrenar, predecir y agrupar.

Para cada tamaño (100 mil y 1 millón de registros) se generan datos sintéticos
con ``sinteticos`` y se corre el esquema v2 completo en DuckDB (sin Spark):

1. **Preparación:** estandarización v2 y columnas del modelo (Python, fila por fila).
2. **Entrenamiento:** lambda por reglas determinísticas, u por muestreo y m por EM.
3. **Predicción:** pares que pasan el bloqueo exacto del modelo v2, puntuados.
4. **Agrupación:** componentes conectadas al umbral congelado.

La memoria es el pico del proceso (RSS, incluye DuckDB), muestreado cada 50 ms. Cada
tamaño se mide en un proceso propio (``scripts/escala.py``) para que no se mezclen picos.
Como los datos de cada etapa siguen en memoria en la siguiente, el pico de una etapa
incluye lo acumulado: con 1 millón de registros el proceso llega a 9,1 GB en la
agrupación. Por eso 5 millones no cabe en la máquina de referencia (la corrida se detuvo
por falta de memoria) y queda fuera de la medición; escalar más allá pide liberar
artefactos entre etapas, DuckDB en disco o un motor distribuido.

Dos ajustes respecto al modelo del hito 2b, necesarios para escalar:

- Los correos de relleno (los que aparecen en más registros de los que puede tener una
  persona) se anulan antes de bloquear, como ya se hacía con los teléfonos: si no, un
  puñado de correos genéricos compartidos por decenas de miles de registros hace explotar
  el bloqueo (crece con el cuadrado).
- Los bloques de EM evitan la fecha de nacimiento sola, que crece con el cuadrado del
  número de registros nacidos el mismo día.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import psutil
from splink import DuckDBAPI, Linker, block_on

from identidades import evaluacion, modelo, rutas, sinteticos
from identidades.modelo_co_v2 import ESQUEMA_V2, MAX_REGISTROS_POR_TELEFONO

REGISTROS_POR_PERSONA: float = 2.42  # promedio de sinteticos.Composicion
TAMANOS: tuple[int, ...] = (100_000, 1_000_000)
BLOQUEOS_EM_ESCALA: list[tuple[str, ...]] = [
    ("documento",),
    ("primer_apellido", "primer_nombre"),
    ("fecha_nacimiento", "substr(primer_apellido, 1, 1)"),
]
UMBRAL_PREDICCION: float = 0.9  # se guardan solo pares desde 0,9 para no materializar todo


@dataclass
class Medicion:
    etapa: str
    segundos: float = 0.0
    memoria_pico_gb: float = 0.0
    detalle: dict[str, Any] = field(default_factory=dict)


@contextmanager
def medir(etapa: str, mediciones: list[Medicion]) -> Iterator[Medicion]:
    """Mide tiempo y pico de memoria del proceso durante el bloque."""
    proceso = psutil.Process()
    pico = [proceso.memory_info().rss]
    activo = [True]

    def muestrear() -> None:
        while activo[0]:
            pico[0] = max(pico[0], proceso.memory_info().rss)
            time.sleep(0.05)

    hilo = threading.Thread(target=muestrear, daemon=True)
    hilo.start()
    medicion = Medicion(etapa)
    inicio = time.perf_counter()
    try:
        yield medicion
    finally:
        medicion.segundos = time.perf_counter() - inicio
        activo[0] = False
        hilo.join()
        medicion.memoria_pico_gb = max(pico[0], proceso.memory_info().rss) / 1024**3
        mediciones.append(medicion)


def generar(n_registros: int, semilla: int = 7000, directorio: Path | None = None) -> pd.DataFrame:
    """Registros sintéticos (aprox. ``n_registros``), con caché en ``data/escala``."""
    directorio = directorio or rutas.DATA / "escala"
    ruta = directorio / f"registros_{n_registros}.parquet"
    if ruta.exists():
        return pd.read_parquet(ruta)
    registros, _ = sinteticos.generar(round(n_registros / REGISTROS_POR_PERSONA), semilla)
    directorio.mkdir(parents=True, exist_ok=True)
    registros.to_parquet(ruta, index=False)
    return registros


def preparar(registros: pd.DataFrame) -> pd.DataFrame:
    """Preparación v2 más correos de relleno anulados (para que el bloqueo escale)."""
    preparado = ESQUEMA_V2.preparar(registros)
    frecuencia = preparado["email"].value_counts()
    relleno = set(frecuencia[frecuencia > MAX_REGISTROS_POR_TELEFONO].index)
    preparado["email"] = preparado["email"].where(~preparado["email"].isin(relleno))
    return preparado


def correr(n_registros: int, umbral: float = 0.9999) -> tuple[list[Medicion], dict[str, Any]]:
    """Corre el flujo completo para un tamaño y devuelve mediciones y artefactos."""
    mediciones: list[Medicion] = []
    registros = generar(n_registros)

    with medir("preparacion", mediciones) as m:
        preparado = preparar(registros)
        m.detalle["registros"] = len(preparado)

    with medir("entrenamiento", mediciones) as m:
        settings = modelo.crear_settings(ESQUEMA_V2.bloqueos_exactos, ESQUEMA_V2)
        linker = Linker(preparado, settings, db_api=DuckDBAPI())
        linker.training.estimate_probability_two_random_records_match(
            ESQUEMA_V2.reglas_deterministicas, recall=modelo.RECALL_DETERMINISTICO
        )
        linker.training.estimate_u_using_random_sampling(max_pairs=1e7, seed=42)
        for cols in BLOQUEOS_EM_ESCALA:
            linker.training.estimate_parameters_using_expectation_maximisation(block_on(*cols))

    with medir("prediccion", mediciones) as m:
        df_pred = linker.inference.predict(threshold_match_probability=UMBRAL_PREDICCION)
        m.detalle["pares_desde_0_9"] = int(
            linker.misc.query_sql(f"select count(*) as n from {df_pred.physical_name}")["n"][0]
        )

    with medir("agrupacion", mediciones) as m:
        df_clusters = modelo.agrupar(linker, df_pred, umbral)
        clusters = df_clusters.as_pandas_dataframe()
        m.detalle["clientes"] = int(clusters["cluster_id"].nunique())

    calidad = evaluacion.metricas_cluster(clusters, registros)
    artefactos = {
        "registros": registros,
        "clusters": clusters,
        "pares": df_pred.as_pandas_dataframe()[
            ["unique_id_l", "unique_id_r", "match_probability", "match_weight"]
        ],
        "calidad": calidad,
    }
    return mediciones, artefactos


def correr_congelado(
    n_registros: int, configuracion: dict[str, Any], umbral: float
) -> tuple[list[Medicion], dict[str, Any]]:
    """Como ``correr``, pero con m y u congelados: solo se vuelve a estimar lambda.

    La auditoría (hallazgo A2) mostró que reentrenar en cada tamaño degrada la precisión:
    el u de los campos casi únicos baja con el volumen y los familiares que comparten
    teléfono y dirección acumulan evidencia. Con los parámetros congelados no pasa. El
    bloqueo de predicción es el exacto del esquema, igual que en ``correr``, para que las
    dos corridas comparen lo mismo. Además de la calidad, mide la línea base
    determinística y el híbrido (sin intervalos: el bootstrap no cabe en memoria a esta
    escala).
    """
    from identidades import linea_base
    from identidades.modelo_co_v3 import ESQUEMA_V3

    mediciones: list[Medicion] = []
    registros = generar(n_registros)

    with medir("preparacion", mediciones) as m:
        preparado = preparar(registros)
        m.detalle["registros"] = len(preparado)

    with medir("lambda", mediciones) as m:
        congelada = {
            **configuracion,
            "blocking_rules_to_generate_predictions": [
                block_on(*cols).get_blocking_rule("duckdb").as_dict()
                for cols in ESQUEMA_V3.bloqueos_exactos
            ],
        }
        linker = Linker(preparado, congelada, db_api=DuckDBAPI())
        linker.training.estimate_probability_two_random_records_match(
            ESQUEMA_V3.reglas_deterministicas, recall=modelo.RECALL_DETERMINISTICO
        )

    with medir("prediccion", mediciones) as m:
        df_pred = linker.inference.predict(threshold_match_probability=UMBRAL_PREDICCION)
        pares = df_pred.as_pandas_dataframe()[
            ["unique_id_l", "unique_id_r", "match_probability", "match_weight"]
        ]
        m.detalle["pares_desde_0_9"] = len(pares)

    with medir("agrupacion", mediciones) as m:
        clusters = modelo.agrupar(linker, df_pred, umbral).as_pandas_dataframe()
        m.detalle["clientes"] = int(clusters["cluster_id"].nunique())

    calidad = evaluacion.metricas_cluster(clusters, registros)
    base = linea_base.comparar(preparado, registros, pares, umbral, n_bootstrap=0)
    return mediciones, {"calidad": calidad, "linea_base": base}


def exportar_universo(
    artefactos: dict[str, Any],
    directorio: Path,
    n_registros: int = 200_000,
    umbral: float = 0.9999,
    semilla: int = 0,
    sufijo: str = "",
) -> dict[str, int]:
    """Muestra de personas (~``n_registros`` registros) en Parquet para Cosmograph.

    Puntos: registros (gris si su cliente quedó exacto, rojo si el cliente mezcla
    personas, naranja si la persona quedó dividida) y estrellas de teléfonos y correos de
    relleno. Enlaces: coincidencias del modelo (fuertes sobre el umbral, débiles desde 0,9)
    y registro-relleno.
    """
    from identidades.escenario_hito3 import normalizar

    registros, clusters, pares = (
        artefactos["registros"],
        artefactos["clusters"],
        artefactos["pares"],
    )
    personas = registros["cluster"].drop_duplicates().sample(frac=1, random_state=semilla)
    tamanos = registros.groupby("cluster").size().reindex(personas)
    elegidas = set(tamanos.index[tamanos.cumsum() <= n_registros])
    muestra = registros[registros["cluster"].isin(elegidas)]
    ids = set(muestra["unique_id"])

    asignacion = clusters[["unique_id", "cluster_id"]].merge(muestra[["unique_id", "cluster"]])
    personas_por_cliente = asignacion.groupby("cluster_id")["cluster"].nunique()
    clientes_por_persona = asignacion.groupby("cluster")["cluster_id"].nunique()
    categoria = pd.Series("registro", index=asignacion["unique_id"].to_numpy())
    dividida = asignacion["cluster"].map(clientes_por_persona).to_numpy() > 1
    mezcla = asignacion["cluster_id"].map(personas_por_cliente).to_numpy() > 1
    categoria[dividida] = "registro_dividido"
    categoria[mezcla] = "registro_mezcla"
    puntos = pd.DataFrame(
        {"id": categoria.index.astype("int64"), "categoria": categoria.to_numpy(), "tamano": 1.5}
    )

    enlaces = pares[pares["unique_id_l"].isin(ids) & pares["unique_id_r"].isin(ids)]
    enlaces = pd.DataFrame(
        {
            "origen": enlaces["unique_id_l"].astype("int64"),
            "destino": enlaces["unique_id_r"].astype("int64"),
            "categoria": (enlaces["match_probability"] >= umbral).map(
                {True: "enlace_fuerte", False: "enlace_debil"}
            ),
        }
    )

    estrellas, enlaces_estrella = [], []
    siguiente = int(registros["unique_id"].max()) + 1
    for tipo, columna, valores in (
        ("celular", "celular", sinteticos.TELEFONOS_RELLENO),
        ("correo", "correo", sinteticos.CORREOS_RELLENO),
    ):
        normalizados = {normalizar(tipo, v) for v in valores}
        claves = muestra[columna].map(lambda v, t=tipo: normalizar(t, v))
        for valor in sorted(normalizados):
            con_valor = muestra.loc[claves == valor, "unique_id"]
            if con_valor.empty:
                continue
            estrellas.append({"id": siguiente, "categoria": "valor_relleno", "tamano": 12.0})
            enlaces_estrella += [
                {"origen": int(i), "destino": siguiente, "categoria": "enlace_relleno"}
                for i in con_valor
            ]
            siguiente += 1
    puntos = pd.concat([puntos, pd.DataFrame(estrellas)], ignore_index=True)
    enlaces = pd.concat([enlaces, pd.DataFrame(enlaces_estrella)], ignore_index=True)

    directorio.mkdir(parents=True, exist_ok=True)
    puntos.astype({"categoria": "category"}).to_parquet(
        directorio / f"universo_grande_puntos{sufijo}.parquet", index=False, compression="zstd"
    )
    enlaces.astype({"categoria": "category"}).to_parquet(
        directorio / f"universo_grande_enlaces{sufijo}.parquet", index=False, compression="zstd"
    )
    return {
        "puntos": len(puntos),
        "enlaces": len(enlaces),
        "registros_mezclados": int((puntos["categoria"] == "registro_mezcla").sum()),
        "registros_divididos": int((puntos["categoria"] == "registro_dividido").sum()),
    }
