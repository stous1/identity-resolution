"""Configuración, entrenamiento y predicción del modelo Splink (Fellegi-Sunter)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import jellyfish
import pandas as pd
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on
from splink.internals.splink_dataframe import SplinkDataFrame

# Columnas que usan las comparaciones del modelo.
COLUMNAS_COMPARACION: list[str] = ["first_name", "surname", "dob", "city", "email"]

# Columnas derivadas que agrega ``preparar`` para el bloqueo aproximado.
COLUMNAS_DERIVADAS: list[str] = ["surname_soundex", "surname_metaphone", "first_name_metaphone"]

# Bloqueo para predecir: solo se comparan pares que coinciden en alguna de estas reglas.
# Cada regla es una tupla de columnas o expresiones SQL que deben coincidir a la vez.
# En fake_1000 los bloqueos de dos columnas cubrían ~55 % de los pares verdaderos; con
# una columna por regla se cubre ~81 % con ~4.000 comparaciones (de ~500.000).
BLOQUEOS_EXACTOS: list[tuple[str, ...]] = [
    ("first_name",),
    ("surname",),
    ("dob",),
    ("email",),
]

# Reglas aproximadas para pares que no comparten ningún campo exacto. Con ellas el recall
# del bloqueo sube a ~92 % con ~7.100 comparaciones, sin bajar la precisión. Se
# descartaron Metaphone del apellido (no aportaba sobre Soundex) y las tres primeras
# letras del nombre (+0,1 puntos de recall a cambio de ~1.400 comparaciones). La
# comparación completa se genera con ``identidades.flujo.comparar_bloqueos``.
BLOQUEOS_APROXIMADOS: list[tuple[str, ...]] = [
    ("surname_soundex",),
    ("first_name_metaphone",),
    ("substr(dob, 1, 4)", "substr(surname, 1, 1)"),
    ("substr(dob, 1, 4)", "substr(first_name, 1, 1)"),
    ("substr(email, 1, 4)",),
    ("city", "substr(dob, 1, 4)"),
]

BLOQUEOS_PREDICCION: list[tuple[str, ...]] = BLOQUEOS_EXACTOS + BLOQUEOS_APROXIMADOS

# Bloqueos de las pasadas de EM. Cada pasada no puede estimar los parámetros m de las
# columnas de su propio bloqueo, por eso se usan dos bloqueos que se complementan.
BLOQUEOS_EM: list[tuple[str, ...]] = [
    ("first_name", "surname"),
    ("dob",),
]

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
    - ``surname_metaphone``: Metaphone del apellido (probada y descartada en el bloqueo).
    - ``first_name_metaphone``: Metaphone del nombre ("Smith" y "Smyth" -> "SM0").
    """
    return df.assign(
        surname_soundex=df["surname"].map(_codigo_fonetico(jellyfish.soundex)),
        surname_metaphone=df["surname"].map(_codigo_fonetico(jellyfish.metaphone)),
        first_name_metaphone=df["first_name"].map(_codigo_fonetico(jellyfish.metaphone)),
    )


def crear_settings(bloqueos: list[tuple[str, ...]] | None = None) -> SettingsCreator:
    """Construye la configuración del modelo de deduplicación.

    ``bloqueos`` reemplaza las reglas de predicción (por defecto ``BLOQUEOS_PREDICCION``).
    """
    bloqueos = BLOQUEOS_PREDICCION if bloqueos is None else bloqueos
    return SettingsCreator(
        link_type="dedupe_only",
        unique_id_column_name="unique_id",
        comparisons=[
            cl.NameComparison("first_name").configure(term_frequency_adjustments=True),
            cl.NameComparison("surname").configure(term_frequency_adjustments=True),
            cl.DateOfBirthComparison("dob", input_is_string=True),
            cl.ExactMatch("city").configure(term_frequency_adjustments=True),
            cl.EmailComparison("email"),
        ],
        blocking_rules_to_generate_predictions=[block_on(*cols) for cols in bloqueos],
        retain_matching_columns=True,
        retain_intermediate_calculation_columns=True,
    )


def crear_linker(df: pd.DataFrame, settings: SettingsCreator | None = None) -> Linker:
    """Crea un ``Linker`` de Splink sobre DuckDB en memoria, aplicando ``preparar`` a ``df``."""
    return Linker(preparar(df), settings or crear_settings(), db_api=DuckDBAPI())


def entrenar(
    linker: Linker,
    recall_deterministico: float = 0.7,
    max_pares_u: float = 1e6,
    semilla: int = 42,
) -> None:
    """Entrena el modelo sin etiquetas.

    1. lambda por reglas determinísticas, suponiendo su recall.
    2. u por muestreo aleatorio de pares (casi todos son no coincidentes).
    3. m por EM, con una pasada por cada bloqueo de ``BLOQUEOS_EM``.
    """
    linker.training.estimate_probability_two_random_records_match(
        REGLAS_DETERMINISTICAS, recall=recall_deterministico
    )
    linker.training.estimate_u_using_random_sampling(max_pairs=max_pares_u, seed=semilla)
    for cols in BLOQUEOS_EM:
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
