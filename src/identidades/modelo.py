"""Configuración, entrenamiento y predicción del modelo Splink (Fellegi-Sunter)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on
from splink.internals.splink_dataframe import SplinkDataFrame

# Columnas que usan las comparaciones del modelo.
COLUMNAS_COMPARACION: list[str] = ["first_name", "surname", "dob", "city", "email"]

# Bloqueo para predecir: solo se comparan pares que coinciden en alguna de estas
# combinaciones de columnas. Se definen como tuplas para poder validarlas en pruebas.
# En fake_1000 los bloqueos de dos columnas solo cubren ~55 % de los pares verdaderos;
# con una columna por regla se cubre ~81 % con unas 4.000 comparaciones (de ~500.000).
BLOQUEOS_PREDICCION: list[tuple[str, ...]] = [
    ("first_name",),
    ("surname",),
    ("dob",),
    ("email",),
]

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


def crear_settings() -> SettingsCreator:
    """Construye la configuración del modelo de deduplicación."""
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
        blocking_rules_to_generate_predictions=[block_on(*cols) for cols in BLOQUEOS_PREDICCION],
        retain_matching_columns=True,
        retain_intermediate_calculation_columns=True,
    )


def crear_linker(df: pd.DataFrame, settings: SettingsCreator | None = None) -> Linker:
    """Crea un ``Linker`` de Splink sobre DuckDB en memoria."""
    return Linker(df, settings or crear_settings(), db_api=DuckDBAPI())


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
    ruta.write_text(json.dumps(modelo, indent=2, ensure_ascii=False), encoding="utf-8")
