"""Pruebas de la estandarización v2 (hito 2b)."""

import pandas as pd
import pytest

from identidades import estandarizacion_v2 as v2


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("ARANGO DE RAMIREZ", ("ARANGO", "RAMIREZ")),
        ("MONTOYA DE LOPEZ", ("MONTOYA", "LOPEZ")),
        ("GOMEZ VDA DE PEREZ", ("GOMEZ", "PEREZ")),
        ("GOMEZ VIUDA DE PEREZ", ("GOMEZ", "PEREZ")),
        ("DE LA HOZ GOMEZ", ("DE LA HOZ GOMEZ", None)),
        ("GOMEZ DE LA TORRE", ("GOMEZ DE LA TORRE", None)),
        ("PONCE DE LEON", ("PONCE DE LEON", None)),
        ("RAMIREZ OSORIO", ("RAMIREZ OSORIO", None)),
        (None, (None, None)),
        (float("nan"), (None, None)),
    ],
)
def test_separar_apellido_casada(entrada, esperado):
    assert v2.separar_apellido_casada(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("PEPE", "JOSE"),
        ("TONO", "ANTONIO"),
        ("BETTY", "BEATRIZ"),
        ("MAFE", "MARIA FERNANDA"),
        ("ANAMARIA", "ANA MARIA"),
        ("JUANDA", "JUAN DAVID"),
        ("PACHO ANDRES", "FRANCISCO ANDRES"),
        ("CARLOS", "CARLOS"),
        (None, None),
    ],
)
def test_nombre_formal(entrada, esperado):
    assert v2.nombre_formal(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("CC 1.114.989.117", "1114989117"),
        ("l036B30967", "1036830967"),
        ("1O23456789", "1023456789"),
        ("1114989117-", "1114989117"),
        ("1071194756 de Bogotá", "1071194756"),
        ("C.C.  1123778954", "1123778954"),
        ("sin dato", None),
    ],
)
def test_limpiar_documento_con_ocr(entrada, esperado):
    assert v2.limpiar_documento(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("3011988647 / 6077779054", ["3011988647", "6077779054"]),
        ("3009764252 ext 61", ["3009764252"]),
        ("315704S960", ["3157045960"]),
        ("(+57) 315-025-5098", ["3150255098"]),
        ("4771580", ["4771580"]),
        ("sin teléfono", []),
        (None, []),
    ],
)
def test_extraer_telefonos(entrada, esperado):
    assert v2.extraer_telefonos(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("1988-10-12", "1988-10-12"),
        ("12/10/1988", "1988-10-12"),
        ("12/10/88", "1988-10-12"),
        ("12/10/05", "2005-10-12"),
        ("20 de octubre de 1999", "1999-10-20"),
        ("09-ABR-1998", "1998-04-09"),
        ("19881012", "1988-10-12"),
        ("1988/10/12", "1988-10-12"),
        ("12.10.1988", "1988-10-12"),
        ("1966-O5-l2", "1966-05-12"),
        ('"01-05-1962', "1962-05-01"),
        ("31/02/1990", None),
        ("mañana", None),
        (None, None),
    ],
)
def test_normalizar_fecha(entrada, esperado):
    assert v2.normalizar_fecha(entrada) == esperado


def test_reparar_codificacion():
    assert v2.reparar_codificacion("RamÃ­rez") == "Ramírez"
    assert v2.reparar_codificacion("Ramírez") == "Ramírez"
    assert v2.reparar_codificacion(None) is None


def test_estandarizar_v2():
    df = pd.DataFrame(
        {
            "nombres": ["Toño", "Salgado"],
            "apellidos": ["Ramírez de Vargas", "Beto"],
            "numero_documento": ["l114989117", "81215024"],
            "fecha_nacimiento": ["12/10/1988", "2005-03-15"],
            "celular": ["3150255098 / 4771580", None],
            "correo": [None, None],
            "direccion": [None, None],
            "ciudad": ["Cali", "Cali"],
        }
    )

    s = v2.estandarizar(df)

    assert s.loc[0, "primer_nombre"] == "ANTONIO"
    assert (s.loc[0, "primer_apellido"], s.loc[0, "apellido_casada"]) == ("RAMIREZ", "VARGAS")
    assert pd.isna(s.loc[0, "segundo_apellido"])
    assert s.loc[0, "documento"] == "1114989117"
    assert s.loc[0, "telefonos"] == ["3150255098", "4771580"]
    assert s.loc[0, "celular_std"] == "3150255098"
    assert s.loc[0, "fecha_std"] == "1988-10-12"
    # Campos cruzados: las palabras de nombre se juntan y el apodo pasa a formal.
    assert s.loc[1, "tokens_nombre"] == ["ALBERTO", "SALGADO"]
