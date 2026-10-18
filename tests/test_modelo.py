"""Pruebas de validez de la configuración del modelo Splink."""

import re

import pandas as pd
from splink import SettingsCreator

from identidades import datos, modelo

FUNCIONES_SQL = {"substr"}


def _columnas_de(expresion: str) -> set[str]:
    """Identificadores de columna en una expresión de bloqueo (sin funciones ni números)."""
    return set(re.findall(r"[a-z_]+", expresion)) - FUNCIONES_SQL


def test_columnas_del_modelo_existen_en_los_datos():
    columnas = set(datos.COLUMNAS_FAKE_1000) | set(modelo.COLUMNAS_DERIVADAS)

    assert set(modelo.COLUMNAS_COMPARACION) <= columnas
    for bloqueo in modelo.BLOQUEOS_PREDICCION + modelo.BLOQUEOS_EM:
        for expresion in bloqueo:
            assert _columnas_de(expresion) <= columnas, expresion


def test_bloqueo_incluye_reglas_exactas_y_aproximadas():
    assert modelo.BLOQUEOS_PREDICCION == modelo.BLOQUEOS_EXACTOS + modelo.BLOQUEOS_APROXIMADOS
    assert len(set(modelo.BLOQUEOS_PREDICCION)) == len(modelo.BLOQUEOS_PREDICCION)


def test_preparar_agrega_codigos_foneticos(registros_pequenos):
    preparado = modelo.preparar(registros_pequenos)

    assert set(modelo.COLUMNAS_DERIVADAS) <= set(preparado.columns)
    assert preparado["surname_soundex"].tolist()[:4] == ["A450", "A450", "K400", "K400"]
    # Nombre nulo -> código nulo.
    assert preparado["first_name_metaphone"].isna().tolist() == [False] * 5 + [True]
    assert "surname_soundex" not in registros_pequenos.columns


def test_todas_las_reglas_de_bloqueo_son_sql_valido(registros_pequenos):
    # Una regla por linker: si alguna expresión no es SQL válido, predict falla.
    for regla in modelo.BLOQUEOS_PREDICCION:
        linker = modelo.crear_linker(registros_pequenos, modelo.crear_settings([regla]))
        pred = linker.inference.predict().as_pandas_dataframe()
        assert isinstance(pred, pd.DataFrame), regla


def test_em_usa_al_menos_dos_bloqueos_distintos():
    assert len(set(modelo.BLOQUEOS_EM)) >= 2


def test_settings_se_construyen():
    settings = modelo.crear_settings()

    assert isinstance(settings, SettingsCreator)
    assert settings.link_type == "dedupe_only"
    assert len(settings.comparisons) == len(modelo.COLUMNAS_COMPARACION)


def test_splink_acepta_la_configuracion(registros_pequenos):
    linker = modelo.crear_linker(registros_pequenos)
    configuracion = linker.misc.save_model_to_json()

    nombres = [c["output_column_name"] for c in configuracion["comparisons"]]
    assert nombres == modelo.COLUMNAS_COMPARACION
    assert len(configuracion["blocking_rules_to_generate_predictions"]) == len(
        modelo.BLOQUEOS_PREDICCION
    )


def test_reglas_deterministicas_son_sql_valido(registros_pequenos):
    linker = modelo.crear_linker(registros_pequenos)

    linker.training.estimate_probability_two_random_records_match(
        modelo.REGLAS_DETERMINISTICAS, recall=0.7
    )

    lam = linker.misc.save_model_to_json()["probability_two_random_records_match"]
    assert 0 < lam <= 1


def test_guardar_modelo_escribe_json(tmp_path, registros_pequenos):
    linker = modelo.crear_linker(registros_pequenos)
    ruta = tmp_path / "sub" / "modelo.json"

    modelo.guardar_modelo(linker, ruta)

    assert ruta.exists()
    assert '"link_type": "dedupe_only"' in ruta.read_text(encoding="utf-8")
