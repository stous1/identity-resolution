"""Pruebas de validez de la configuración del modelo Splink."""

from splink import SettingsCreator

from identidades import datos, modelo


def test_columnas_del_modelo_existen_en_los_datos():
    columnas = set(datos.COLUMNAS_FAKE_1000)

    assert set(modelo.COLUMNAS_COMPARACION) <= columnas
    for bloqueo in modelo.BLOQUEOS_PREDICCION + modelo.BLOQUEOS_EM:
        assert set(bloqueo) <= columnas, bloqueo


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
