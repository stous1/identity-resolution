"""Pruebas del esquema Splink para clientes colombianos."""

import pandas as pd
import pytest

from identidades import modelo, modelo_co, sinteticos


@pytest.fixture(scope="module")
def registros() -> pd.DataFrame:
    return sinteticos.generar(n_personas=60, semilla=11)[0]


@pytest.mark.parametrize("estandarizado", [True, False])
def test_preparar_llena_las_columnas_del_modelo(registros, estandarizado):
    preparado = modelo_co.esquema(estandarizado).preparar(registros)

    assert set(modelo_co.COLUMNAS_MODELO) <= set(preparado.columns)
    assert preparado["unique_id"].tolist() == registros["unique_id"].tolist()
    assert (preparado["cluster"] == registros["cluster"]).all()


def test_estandarizado_y_crudo_difieren_solo_en_la_preparacion():
    con, sin = modelo_co.esquema(True), modelo_co.esquema(False)

    assert con.preparar is not sin.preparar
    assert con.bloqueos_exactos == sin.bloqueos_exactos
    assert con.bloqueos_candidatos == sin.bloqueos_candidatos
    assert [c.get_comparison("duckdb").output_column_name for c in con.comparaciones()] == [
        c.get_comparison("duckdb").output_column_name for c in sin.comparaciones()
    ]


def test_crudo_no_normaliza():
    df = pd.DataFrame(
        {
            "unique_id": [0],
            "numero_documento": ["1.023.456"],
            "nombres": ["josé maría"],
            "apellidos": ["Pérez"],
            "fecha_nacimiento": ["1990-01-01"],
            "celular": ["+57 300 123 4567"],
            "correo": ["A@B.CO"],
            "direccion": ["Cra 45 # 10-20"],
            "ciudad": ["Bogotá"],
        }
    )

    crudo = modelo_co.preparar_crudo(df).iloc[0]
    std = modelo_co.preparar_estandarizado(df).iloc[0]

    assert (crudo["documento"], std["documento"]) == ("1.023.456", "1023456")
    assert (crudo["primer_nombre"], std["primer_nombre"]) == ("josé", "JOSE")
    assert (crudo["telefono"], std["telefono"]) == ("+57 300 123 4567", "3001234567")
    assert pd.isna(crudo["domicilio_clave"]) and std["domicilio_clave"] == "KR 45 # 10"


@pytest.mark.parametrize(
    ("documento_b", "nivel"),
    [
        ("1023456789", "Exact match on documento"),
        ("1023456788", "Un dígito distinto"),
        ("1023456798", "Dos dígitos transpuestos"),
        ("102345678", "Un dígito de más o de menos"),
        ("5555555555", "All other comparisons"),
    ],
)
def test_niveles_de_documento(documento_b, nivel):
    esquema = modelo_co.esquema(True)
    base = {
        "nombres": "Ana",
        "apellidos": "Ruiz",
        "fecha_nacimiento": "1990-01-01",
        "celular": None,
        "correo": None,
        "direccion": None,
        "ciudad": "Cali",
        "cluster": 0,
    }
    df = pd.DataFrame(
        [
            {**base, "unique_id": 0, "numero_documento": "1023456789"},
            {**base, "unique_id": 1, "numero_documento": documento_b},
        ]
    )
    linker = modelo.crear_linker(
        df, modelo.crear_settings([("nombres_ordenados",)], esquema), esquema
    )

    par = linker.inference.predict().as_pandas_dataframe().iloc[0]

    comparacion = next(
        c for c in linker._settings_obj.comparisons if c.output_column_name == "documento"
    )
    etiquetas = {
        lvl.comparison_vector_value: lvl.label_for_charts for lvl in comparacion.comparison_levels
    }
    assert etiquetas[par["gamma_documento"]] == nivel


def test_columna_toda_nula_no_rompe_las_comparaciones_de_texto():
    df = pd.DataFrame(
        {
            "unique_id": [0, 1],
            "numero_documento": ["1", "1"],
            "nombres": ["Ana", "Ana"],
            "apellidos": ["Ruiz", "Ruiz"],  # sin segundo apellido: columna toda nula
            "fecha_nacimiento": ["1990-01-01"] * 2,
            "celular": [None, None],
            "correo": [None, None],
            "direccion": [None, None],
            "ciudad": ["Cali", "Cali"],
        }
    )
    for estandarizado in (True, False):
        esquema = modelo_co.esquema(estandarizado)
        linker = modelo.crear_linker(df, esquema=esquema)
        assert len(linker.inference.predict().as_pandas_dataframe()) == 1


def test_todas_las_reglas_de_bloqueo_son_sql_valido(registros):
    esquema = modelo_co.esquema(True)
    for regla in esquema.bloqueos_exactos + esquema.bloqueos_candidatos + esquema.bloqueos_em:
        linker = modelo.crear_linker(registros, modelo.crear_settings([regla], esquema), esquema)
        assert linker.inference.predict().as_pandas_dataframe() is not None, regla
