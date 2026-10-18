"""Pruebas del esquema Splink para FEBRL."""

import pandas as pd

from identidades import modelo
from identidades.modelo_febrl import ESQUEMA_FEBRL, _fecha_iso, preparar


def _febrl() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unique_id": [0, 1, 2],
            "cluster": [7, 7, 12],
            "given_name": ["mitchell", "mitchel", "harley"],
            "surname": ["green", "green", None],
            "street_number": ["7", None, "177"],
            "address_1": ["wallaby place", "wallaby pl", "pridham street"],
            "address_2": [None, None, "milton"],
            "suburb": ["cleveland", "cleveland", "marsden"],
            "postcode": ["2119", "2119", "3165"],
            "state": ["sa", "sa", "nsw"],
            "date_of_birth": ["19560409", "19560490", None],
            "soc_sec_id": ["1804974", "1804947", "6089216"],
        }
    )


def test_fecha_iso():
    assert _fecha_iso("19560409") == "1956-04-09"
    assert _fecha_iso("19560490") is None  # día inválido
    assert _fecha_iso(None) is None


def test_preparar_agrega_foneticos_y_no_toca_el_original():
    df = _febrl()

    preparado = preparar(df)

    assert preparado.loc[0, "date_of_birth"] == "1956-04-09"
    assert preparado.loc[0, "surname_soundex"] == "G650"
    assert pd.isna(preparado.loc[2, "surname_soundex"])
    assert df.loc[0, "date_of_birth"] == "19560409"


def test_todas_las_reglas_de_bloqueo_son_sql_valido():
    df = _febrl()
    reglas = (
        ESQUEMA_FEBRL.bloqueos_exactos
        + ESQUEMA_FEBRL.bloqueos_candidatos
        + ESQUEMA_FEBRL.bloqueos_em
    )
    for regla in reglas:
        linker = modelo.crear_linker(
            df, modelo.crear_settings([regla], ESQUEMA_FEBRL), ESQUEMA_FEBRL
        )
        assert linker.inference.predict().as_pandas_dataframe() is not None, regla


def test_identificacion_con_digitos_transpuestos():
    df = _febrl()
    linker = modelo.crear_linker(
        df, modelo.crear_settings([("postcode",)], ESQUEMA_FEBRL), ESQUEMA_FEBRL
    )

    par = linker.inference.predict().as_pandas_dataframe().iloc[0]

    comparacion = next(
        c for c in linker._settings_obj.comparisons if c.output_column_name == "soc_sec_id"
    )
    etiquetas = {
        n.comparison_vector_value: n.label_for_charts for n in comparacion.comparison_levels
    }
    assert etiquetas[par["gamma_soc_sec_id"]] == "Dos dígitos transpuestos"
