"""Esquema Splink para FEBRL3 (validación externa).

Mismo enfoque que el hito 2, adaptado a las columnas de FEBRL: número de identificación
(``soc_sec_id``) por niveles, nombre y apellido con ajuste por frecuencia, fecha de
nacimiento, dirección y ubicación. Se define aparte para no tocar los módulos congelados
del hito 2 (``estandarizacion`` y ``modelo_co``).
"""

from __future__ import annotations

import jellyfish
import pandas as pd
import splink.comparison_level_library as cll
import splink.comparison_library as cl
from splink.internals.comparison_creator import ComparisonCreator

from identidades.modelo import Esquema, Regla, _codigo_fonetico

COLUMNAS_TEXTO: list[str] = [
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
    "surname_soundex",
    "given_name_metaphone",
]


def _fecha_iso(valor: object) -> str | None:
    """ "19560409" -> "1956-04-09"; ``None`` si no es una fecha válida."""
    if pd.isna(valor):
        return None
    fecha = pd.to_datetime(str(valor), format="%Y%m%d", errors="coerce")
    return None if pd.isna(fecha) else fecha.strftime("%Y-%m-%d")


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Fecha en ISO, códigos fonéticos y columnas como texto."""
    preparado = df.assign(
        date_of_birth=df["date_of_birth"].map(_fecha_iso),
        surname_soundex=df["surname"].map(_codigo_fonetico(jellyfish.soundex)),
        given_name_metaphone=df["given_name"].map(_codigo_fonetico(jellyfish.metaphone)),
    )
    preparado[COLUMNAS_TEXTO] = preparado[COLUMNAS_TEXTO].astype("string")
    return preparado


def comparacion_identificacion() -> ComparisonCreator:
    """Número de identificación: exacto, un dígito distinto, transpuestos, uno de más o menos."""
    izq, der = '"soc_sec_id_l"', '"soc_sec_id_r"'
    return cl.CustomComparison(
        output_column_name="soc_sec_id",
        comparison_levels=[
            cll.NullLevel("soc_sec_id"),
            cll.ExactMatchLevel("soc_sec_id"),
            cll.CustomLevel(
                f"length({izq}) = length({der}) and levenshtein({izq}, {der}) = 1",
                label_for_charts="Un dígito distinto",
            ),
            cll.CustomLevel(
                f"length({izq}) = length({der}) and damerau_levenshtein({izq}, {der}) = 1",
                label_for_charts="Dos dígitos transpuestos",
            ),
            cll.CustomLevel(
                f"abs(length({izq}) - length({der})) = 1 and levenshtein({izq}, {der}) = 1",
                label_for_charts="Un dígito de más o de menos",
            ),
            cll.ElseLevel(),
        ],
        comparison_description="Identificación",
    )


def comparaciones() -> list[ComparisonCreator]:
    return [
        comparacion_identificacion(),
        cl.NameComparison("given_name").configure(term_frequency_adjustments=True),
        cl.NameComparison("surname").configure(term_frequency_adjustments=True),
        cl.DateOfBirthComparison("date_of_birth", input_is_string=True),
        cl.ExactMatch("street_number"),
        cl.JaroWinklerAtThresholds("address_1", [0.92, 0.80]).configure(
            term_frequency_adjustments=True
        ),
        cl.JaroWinklerAtThresholds("suburb", [0.90]).configure(term_frequency_adjustments=True),
        cl.LevenshteinAtThresholds("postcode", [1]),
        cl.ExactMatch("state"),
    ]


BLOQUEOS_EXACTOS: list[Regla] = [
    ("soc_sec_id",),
    ("given_name", "surname"),
    ("date_of_birth",),
    ("surname", "postcode"),
]

BLOQUEOS_CANDIDATOS: list[Regla] = [
    ("surname_soundex", "substr(date_of_birth, 1, 4)"),
    ("given_name_metaphone", "surname_soundex"),
    ("given_name", "postcode"),
    ("address_1",),
    ("right(soc_sec_id, 4)",),
    ("substr(soc_sec_id, 1, 4)",),
    ("postcode", "street_number"),
    ("suburb", "substr(given_name, 1, 2)"),
]

BLOQUEOS_EM: list[Regla] = [
    ("given_name", "surname"),
    ("date_of_birth",),
    ("postcode",),
]

REGLAS_DETERMINISTICAS: list[str] = [
    "l.soc_sec_id = r.soc_sec_id",
    "l.given_name = r.given_name and l.surname = r.surname and l.date_of_birth = r.date_of_birth",
]

ESQUEMA_FEBRL = Esquema(
    nombre="febrl3",
    comparaciones=comparaciones,
    preparar=preparar,
    bloqueos_exactos=BLOQUEOS_EXACTOS,
    bloqueos_candidatos=BLOQUEOS_CANDIDATOS,
    bloqueos_em=BLOQUEOS_EM,
    reglas_deterministicas=REGLAS_DETERMINISTICAS,
)
