"""Carga de datos de demostración con caché local."""

from __future__ import annotations

import io
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

from identidades import rutas

URL_FAKE_1000: str = (
    "https://raw.githubusercontent.com/moj-analytical-services/"
    "splink_datasets/master/data/fake_1000.csv"
)

COLUMNAS_FAKE_1000: list[str] = [
    "unique_id",
    "first_name",
    "surname",
    "dob",
    "city",
    "email",
    "cluster",
]


def descargar(url: str, timeout: float = 60) -> bytes:
    """Descarga el contenido de una URL y lo devuelve como bytes."""
    with urlopen(url, timeout=timeout) as respuesta:
        return respuesta.read()


def cargar_fake_1000(directorio: Path | None = None) -> pd.DataFrame:
    """Carga el dataset de demostración fake_1000 de Splink.

    La primera vez lo descarga y lo guarda como parquet en ``directorio``
    (por defecto ``data/raw``); las siguientes veces lo lee de esa caché.

    Son 1.000 registros de 251 personas simuladas. La columna ``cluster`` es la
    verdad conocida: registros con el mismo ``cluster`` son la misma persona.
    """
    directorio = directorio or rutas.DATA_RAW
    ruta = directorio / "fake_1000.parquet"

    if ruta.exists():
        return pd.read_parquet(ruta)

    df = pd.read_csv(io.BytesIO(descargar(URL_FAKE_1000)))
    faltantes = set(COLUMNAS_FAKE_1000) - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas en fake_1000: {sorted(faltantes)}")

    df = df[COLUMNAS_FAKE_1000]
    directorio.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ruta, index=False)
    return df


URL_FEBRL3: str = (
    "https://raw.githubusercontent.com/moj-analytical-services/"
    "splink_datasets/master/data/febrl/dataset3.csv"
)

COLUMNAS_FEBRL: list[str] = [
    "given_name",
    "surname",
    "street_number",
    "address_1",
    "address_2",
    "suburb",
    "postcode",
    "state",
    "date_of_birth",
    "soc_sec_id",
]


def limpiar_febrl(crudo: pd.DataFrame) -> pd.DataFrame:
    """Deja FEBRL en el formato del proyecto, sin normalizar los valores.

    Quita los espacios sobrantes de nombres de columna y valores, convierte los vacíos
    en nulos, lee todo como texto y agrega ``unique_id`` (entero) y ``cluster`` (la
    persona, tomada de ``rec_id``: "rec-1496-dup-3" es la persona 1496).
    """
    df = crudo.rename(columns=lambda c: c.strip())
    faltantes = {"rec_id", *COLUMNAS_FEBRL} - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas en FEBRL: {sorted(faltantes)}")
    texto = df[COLUMNAS_FEBRL].astype("string").apply(lambda s: s.str.strip())
    texto = texto.mask(texto == "")
    return pd.concat(
        [
            pd.DataFrame(
                {
                    "unique_id": range(len(df)),
                    "rec_id": df["rec_id"].str.strip(),
                    "cluster": df["rec_id"].str.extract(r"rec-(\d+)-")[0].astype(int),
                }
            ),
            texto,
        ],
        axis=1,
    )


def cargar_febrl3(directorio: Path | None = None) -> pd.DataFrame:
    """Carga FEBRL3 (5.000 registros sintéticos de 2.000 personas), con caché local.

    FEBRL es un generador de registros de personas con errores, independiente de este
    proyecto; aquí sirve como validación externa.
    """
    directorio = directorio or rutas.DATA_RAW
    ruta = directorio / "febrl3.parquet"
    if ruta.exists():
        return pd.read_parquet(ruta)

    df = limpiar_febrl(pd.read_csv(io.BytesIO(descargar(URL_FEBRL3)), dtype=str))
    directorio.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ruta, index=False)
    return df


def dividir_por_persona(
    df: pd.DataFrame,
    frac_desarrollo: float = 0.6,
    semilla: int = 42,
    col_grupo: str = "cluster",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divide los registros en desarrollo y prueba por persona (``col_grupo``).

    Todos los registros de una persona quedan del mismo lado, para que el modelo nunca
    vea en desarrollo a alguien que luego se evalúa en prueba. La partición es
    reproducible con ``semilla``.
    """
    if not 0 < frac_desarrollo < 1:
        raise ValueError("frac_desarrollo debe estar entre 0 y 1")
    personas = np.sort(df[col_grupo].unique())
    np.random.default_rng(semilla).shuffle(personas)
    desarrollo = set(personas[: round(frac_desarrollo * len(personas))].tolist())
    en_desarrollo = df[col_grupo].isin(desarrollo)
    return df[en_desarrollo].reset_index(drop=True), df[~en_desarrollo].reset_index(drop=True)
