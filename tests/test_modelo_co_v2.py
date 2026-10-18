"""Pruebas del esquema Splink v2 (hito 2b)."""

import pandas as pd
import pytest

from identidades import modelo
from identidades.modelo_co_v2 import ESQUEMA_V2, _sin_relleno, preparar

BASE = {
    "tipo_documento": "CC",
    "fecha_nacimiento": "1990-01-01",
    "correo": None,
    "direccion": None,
    "ciudad": "Cali",
    "departamento": "Valle",
}


def _par(a: dict, b: dict) -> pd.Series:
    df = pd.DataFrame(
        [
            {**BASE, "unique_id": 0, "cluster": 0, **a},
            {**BASE, "unique_id": 1, "cluster": 0, **b},
        ]
    )
    linker = modelo.crear_linker(
        df, modelo.crear_settings([("municipio",)], ESQUEMA_V2), ESQUEMA_V2
    )
    return linker.inference.predict().as_pandas_dataframe().iloc[0], linker


def _etiqueta(linker, columna: str, gamma: int) -> str:
    comparacion = next(
        c for c in linker._settings_obj.comparisons if c.output_column_name == columna
    )
    return {n.comparison_vector_value: n.label_for_charts for n in comparacion.comparison_levels}[
        gamma
    ]


PERSONA = {"numero_documento": "1023456789", "celular": "3001234567"}


def test_apellido_de_casada_no_choca_con_el_segundo_apellido():
    par, linker = _par(
        {**PERSONA, "nombres": "Amparo", "apellidos": "Arango Parra"},
        {**PERSONA, "nombres": "Amparo", "apellidos": "Arango de Ramírez"},
    )

    assert _etiqueta(linker, "segundo_apellido", par["gamma_segundo_apellido"]).endswith("NULL")
    assert par["gamma_apellido_casada"] == -1  # nulo en uno de los dos: neutral


def test_apodo_coincide_con_el_nombre_formal():
    par, linker = _par(
        {**PERSONA, "nombres": "Antonio", "apellidos": "Ramírez"},
        {**PERSONA, "nombres": "Toño", "apellidos": "Ramírez"},
    )

    assert _etiqueta(linker, "nombres", par["gamma_nombres"]).startswith("Exact match")


def test_nombre_y_apellido_en_campos_intercambiados():
    par, linker = _par(
        {**PERSONA, "nombres": "Alberto", "apellidos": "Salgado"},
        {**PERSONA, "nombres": "Salgado", "apellidos": "Beto"},
    )

    # "Beto" llega en el campo de apellidos, así que se reconoce por las palabras comunes.
    assert _etiqueta(linker, "nombres", par["gamma_nombres"]) in {
        "Nombre y apellido en campos intercambiados",
        "Primer nombre y otra palabra en común (cualquier campo)",
    }
    assert _etiqueta(linker, "primer_apellido", par["gamma_primer_apellido"]) == (
        "Apellido en otro campo de nombre del otro registro"
    )


def test_hermanos_no_activan_el_nivel_de_palabras_comunes():
    par, linker = _par(
        {**PERSONA, "nombres": "Elvira", "apellidos": "Castrillón Mejía"},
        {**PERSONA, "nombres": "Jenny", "apellidos": "Castrillón Mejía"},
    )

    assert _etiqueta(linker, "nombres", par["gamma_nombres"]) not in {
        "Primer nombre y otra palabra en común (cualquier campo)",
        "Nombre y apellido en campos intercambiados",
    }


@pytest.mark.parametrize(
    ("documento_b", "nivel"),
    [
        ("1023456789", "Exact match on documento"),
        ("1023456798", "Dos dígitos transpuestos"),
        ("1023465798", "Dos ediciones"),
        ("l023456789", "Exact match on documento"),
    ],
)
def test_niveles_de_documento(documento_b, nivel):
    par, linker = _par(
        {**PERSONA, "nombres": "Ana", "apellidos": "Ruiz"},
        {**PERSONA, "numero_documento": documento_b, "nombres": "Ana", "apellidos": "Ruiz"},
    )

    assert _etiqueta(linker, "documento", par["gamma_documento"]) == nivel


def test_celular_contra_fijo_no_cuenta_como_telefonos_distintos():
    par, linker = _par(
        {"numero_documento": "1", "celular": "3001234567", "nombres": "Ana", "apellidos": "Ruiz"},
        {"numero_documento": "1", "celular": "4771580", "nombres": "Ana", "apellidos": "Ruiz"},
    )
    assert _etiqueta(linker, "telefonos", par["gamma_telefonos"]) == (
        "Alguno de los dos sin celular (solo fijo)"
    )

    par, linker = _par(
        {"numero_documento": "1", "celular": "3001234567", "nombres": "Ana", "apellidos": "Ruiz"},
        {
            "numero_documento": "1",
            "celular": "3119998888 / 3001234567",
            "nombres": "Ana",
            "apellidos": "Ruiz",
        },
    )
    assert _etiqueta(linker, "telefonos", par["gamma_telefonos"]) == "Algún teléfono en común"


def test_telefonos_de_relleno_se_ignoran():
    telefonos = pd.Series([["3000000000", "3001112222"]] + [["3000000000"]] * 7 + [None])

    limpios = _sin_relleno(telefonos)

    assert limpios[0] == ["3001112222"]
    assert limpios[1] is None and limpios[8] is None


def test_todas_las_reglas_de_bloqueo_son_sql_valido():
    from identidades import sinteticos

    registros, _ = sinteticos.generar(n_personas=40, semilla=3)
    preparado = preparar(registros)
    assert preparado["tokens_nombre"].map(lambda t: t is None or isinstance(t, list)).all()
    reglas = ESQUEMA_V2.bloqueos_exactos + ESQUEMA_V2.bloqueos_candidatos + ESQUEMA_V2.bloqueos_em
    for regla in reglas:
        linker = modelo.crear_linker(
            registros, modelo.crear_settings([regla], ESQUEMA_V2), ESQUEMA_V2
        )
        assert linker.inference.predict().as_pandas_dataframe() is not None, regla
