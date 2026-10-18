"""Configuración, entrenamiento y predicción del modelo Splink (Fellegi-Sunter)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import jellyfish
import pandas as pd
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on
from splink.internals.comparison_creator import ComparisonCreator
from splink.internals.splink_dataframe import SplinkDataFrame

Regla = tuple[str, ...]

# Columnas que usan las comparaciones del modelo.
COLUMNAS_COMPARACION: list[str] = ["first_name", "surname", "dob", "city", "email"]

# Columnas derivadas que agrega ``preparar`` para el bloqueo aproximado.
COLUMNAS_DERIVADAS: list[str] = ["surname_soundex", "surname_metaphone", "first_name_metaphone"]

# Bloqueo para predecir: solo se comparan pares que coinciden en alguna regla. Cada regla
# es una tupla de columnas o expresiones SQL que deben coincidir a la vez. En fake_1000 los
# bloqueos de dos columnas cubrían ~55 % de los pares verdaderos; con una columna por regla
# se cubre ~81 % con ~4.000 comparaciones (de ~500.000). Las exactas siempre se usan.
BLOQUEOS_EXACTOS: list[tuple[str, ...]] = [
    ("first_name",),
    ("surname",),
    ("dob",),
    ("email",),
]

# Reglas aproximadas candidatas, para pares que no comparten ningún campo exacto. Cuáles se
# usan lo decide ``identidades.bloqueo.seleccionar_reglas`` sobre el conjunto de desarrollo.
BLOQUEOS_CANDIDATOS: list[tuple[str, ...]] = [
    ("surname_soundex",),
    ("surname_metaphone",),
    ("first_name_metaphone",),
    ("substr(first_name, 1, 3)",),
    ("substr(dob, 1, 4)", "substr(surname, 1, 1)"),
    ("substr(dob, 1, 4)", "substr(first_name, 1, 1)"),
    ("substr(email, 1, 4)",),
    ("city", "substr(dob, 1, 4)"),
]

# Bloqueos de las pasadas de EM. Cada pasada no puede estimar los parámetros m de las
# columnas de su propio bloqueo, por eso se usan dos bloqueos que se complementan.
BLOQUEOS_EM: list[tuple[str, ...]] = [
    ("first_name", "surname"),
    ("dob",),
]

# Recall que se supone para las reglas determinísticas al estimar lambda.
RECALL_DETERMINISTICO: float = 0.7

# Reglas determinísticas (alta precisión) para estimar lambda: la probabilidad a priori
# de que dos registros al azar sean la misma persona.
REGLAS_DETERMINISTICAS: list[str] = [
    "l.first_name = r.first_name and levenshtein(r.dob, l.dob) <= 1",
    "l.surname = r.surname and levenshtein(r.dob, l.dob) <= 1",
    "l.first_name = r.first_name and levenshtein(r.surname, l.surname) <= 2",
    "l.email = r.email",
]


def _codigo_fonetico(funcion: Callable[[str], str]) -> Callable[[object], str | None]:
    """Envuelve una función fonética para que devuelva None con valores nulos."""

    def aplicar(valor: object) -> str | None:
        return None if pd.isna(valor) else funcion(str(valor))

    return aplicar


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega las columnas fonéticas que usa el bloqueo aproximado.

    - ``surname_soundex``: Soundex del apellido ("Allen" y "Alan" -> "A450").
    - ``surname_metaphone``: Metaphone del apellido ("Smith" y "Smyth" -> "SM0").
    - ``first_name_metaphone``: Metaphone del nombre.
    """
    return df.assign(
        surname_soundex=df["surname"].map(_codigo_fonetico(jellyfish.soundex)),
        surname_metaphone=df["surname"].map(_codigo_fonetico(jellyfish.metaphone)),
        first_name_metaphone=df["first_name"].map(_codigo_fonetico(jellyfish.metaphone)),
    )


def _comparaciones_fake_1000() -> list[ComparisonCreator]:
    return [
        cl.NameComparison("first_name").configure(term_frequency_adjustments=True),
        cl.NameComparison("surname").configure(term_frequency_adjustments=True),
        cl.DateOfBirthComparison("dob", input_is_string=True),
        cl.ExactMatch("city").configure(term_frequency_adjustments=True),
        cl.EmailComparison("email"),
    ]


@dataclass(frozen=True)
class Esquema:
    """Todo lo que cambia entre conjuntos de datos: columnas, comparaciones y reglas.

    - ``preparar``: agrega las columnas derivadas que usan comparaciones y bloqueos.
    - ``bloqueos_exactos``: reglas de predicción que siempre se usan.
    - ``bloqueos_candidatos``: reglas aproximadas entre las que se elige en desarrollo.
    - ``bloqueos_em``: un bloqueo por pasada de EM.
    - ``reglas_deterministicas``: reglas de alta precisión para estimar lambda.
    """

    nombre: str
    comparaciones: Callable[[], list[ComparisonCreator]]
    preparar: Callable[[pd.DataFrame], pd.DataFrame]
    bloqueos_exactos: list[Regla]
    bloqueos_candidatos: list[Regla]
    bloqueos_em: list[Regla]
    reglas_deterministicas: list[str]


ESQUEMA_FAKE_1000 = Esquema(
    nombre="fake_1000",
    comparaciones=_comparaciones_fake_1000,
    preparar=preparar,
    bloqueos_exactos=BLOQUEOS_EXACTOS,
    bloqueos_candidatos=BLOQUEOS_CANDIDATOS,
    bloqueos_em=BLOQUEOS_EM,
    reglas_deterministicas=REGLAS_DETERMINISTICAS,
)


def crear_settings(
    bloqueos: list[Regla] | None = None, esquema: Esquema = ESQUEMA_FAKE_1000
) -> SettingsCreator:
    """Construye la configuración del modelo de deduplicación para ``esquema``.

    ``bloqueos`` son las reglas de predicción (por defecto, las exactas del esquema).
    """
    bloqueos = esquema.bloqueos_exactos if bloqueos is None else bloqueos
    return SettingsCreator(
        link_type="dedupe_only",
        unique_id_column_name="unique_id",
        comparisons=esquema.comparaciones(),
        blocking_rules_to_generate_predictions=[block_on(*cols) for cols in bloqueos],
        retain_matching_columns=True,
        retain_intermediate_calculation_columns=True,
    )


def crear_linker(
    df: pd.DataFrame,
    settings: SettingsCreator | None = None,
    esquema: Esquema = ESQUEMA_FAKE_1000,
) -> Linker:
    """Crea un ``Linker`` de Splink sobre DuckDB en memoria, aplicando ``esquema.preparar``."""
    return Linker(
        esquema.preparar(df), settings or crear_settings(esquema=esquema), db_api=DuckDBAPI()
    )


def entrenar(
    linker: Linker,
    esquema: Esquema = ESQUEMA_FAKE_1000,
    recall_deterministico: float = RECALL_DETERMINISTICO,
    max_pares_u: float = 1e6,
    semilla: int = 42,
) -> None:
    """Entrena el modelo sin etiquetas.

    1. lambda por las reglas determinísticas del esquema, suponiendo su recall.
    2. u por muestreo aleatorio de pares (casi todos son no coincidentes).
    3. m por EM, con una pasada por cada bloqueo de ``esquema.bloqueos_em``.
    """
    linker.training.estimate_probability_two_random_records_match(
        esquema.reglas_deterministicas, recall=recall_deterministico
    )
    linker.training.estimate_u_using_random_sampling(max_pairs=max_pares_u, seed=semilla)
    for cols in esquema.bloqueos_em:
        linker.training.estimate_parameters_using_expectation_maximisation(block_on(*cols))


def predecir(linker: Linker, umbral: float | None = None) -> SplinkDataFrame:
    """Puntúa todos los pares que pasan el bloqueo (o solo los que superan ``umbral``)."""
    return linker.inference.predict(threshold_match_probability=umbral)


def agrupar(linker: Linker, df_pred: SplinkDataFrame, umbral: float) -> SplinkDataFrame:
    """Agrupa los pares por encima de ``umbral`` en clústeres (componentes conectados)."""
    return linker.clustering.cluster_pairwise_predictions_at_threshold(
        df_pred, threshold_match_probability=umbral
    )


def guardar_modelo(linker: Linker, ruta: Path) -> None:
    """Guarda los parámetros entrenados del modelo como JSON."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    modelo = linker.misc.save_model_to_json()
    ruta.write_text(
        json.dumps(modelo, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
