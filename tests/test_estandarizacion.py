"""Pruebas de cada regla de estandarización."""

import pandas as pd
import pytest

from identidades import estandarizacion as e


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("  maría   josé ", "MARÍA JOSÉ"), ("", None), (None, None), (float("nan"), None)],
)
def test_normalizar_texto(entrada, esperado):
    assert e.normalizar_texto(entrada) == esperado


def test_quitar_tildes_incluye_enie_y_dieresis():
    assert e.quitar_tildes("MUÑOZ PÉREZ GÜELL") == "MUNOZ PEREZ GUELL"
    assert e.quitar_tildes(None) is None


def test_normalizar_nombre_quita_signos_y_conserva_tildes():
    assert e.normalizar_nombre("o'neill-peña  ") == "O NEILL PEÑA"
    assert e.normalizar_nombre("123") is None


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Maria Jose", ("MARIA", "JOSE")),
        ("LUIS", ("LUIS", None)),
        ("María de los Ángeles", ("MARÍA", "DE LOS ÁNGELES")),
        ("De La Hoz Gómez", ("DE LA HOZ", "GÓMEZ")),
        ("Gómez de la Hoz", ("GÓMEZ", "DE LA HOZ")),
        (None, (None, None)),
    ],
)
def test_separar_compuesto(entrada, esperado):
    assert e.separar_compuesto(entrada) == esperado


def test_ordenar_tokens_iguala_nombres_invertidos():
    assert e.ordenar_tokens("JOSE MARIA") == e.ordenar_tokens("MARIA JOSE") == "JOSE MARIA"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("1.023.456.789", "1023456789"),
        ("79 123 456", "79123456"),
        ("CC 52,345,678", "52345678"),
        ("0012345", "12345"),
        ("sin dato", None),
    ],
)
def test_limpiar_documento(entrada, esperado):
    assert e.limpiar_documento(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("3001234567", "3001234567"),
        ("+57 300 123 4567", "3001234567"),
        ("573001234567", "3001234567"),
        ("(300) 1234567", "3001234567"),
        ("300-123-4567", "3001234567"),
        ("6012345678", None),  # fijo de Bogotá, no celular
        ("30012345", None),  # incompleto
    ],
)
def test_normalizar_celular(entrada, esperado):
    assert e.normalizar_celular(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (" Ana.Ruiz@Gmail.COM ", "ana.ruiz@gmail.com"),
        ("ana ruiz@gmail.com", "anaruiz@gmail.com"),
        ("sin correo", None),
        ("ana@gmail", None),
    ],
)
def test_normalizar_correo(entrada, esperado):
    assert e.normalizar_correo(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "canonica"),
    [
        ("Cra 45 # 10-20", "KR 45 # 10-20"),
        ("Carrera 45 No. 10 - 20", "KR 45 # 10-20"),
        ("KR 45 10 20", "KR 45 # 10-20"),
        ("Calle 10 Sur # 43A-15", "CL 10 SUR # 43A-15"),
        ("cl 10 # 43a 15 sur", "CL 10 SUR # 43A-15"),
        ("Cl. 135 N° 41A - 36", "CL 135 # 41A-36"),
        ("Carrera 15 BIS Sur # 63-11", "KR 15 BIS SUR # 63-11"),
        ("diag 27b # 56a 12", "DG 27B # 56A-12"),
        ("Trans 90B # 15 91", "TV 90B # 15-91"),
        ("Avenida 28A Este # 45-97", "AV 28A ESTE # 45-97"),
    ],
)
def test_normalizar_direccion_canonica(entrada, canonica):
    assert e.normalizar_direccion(entrada)["direccion"] == canonica


def test_normalizar_direccion_componentes():
    partes = e.normalizar_direccion("Calle 10 Sur # 43A-15")

    assert partes == {
        "via": "CL",
        "numero_via": "10",
        "cuadrante": "SUR",
        "placa": "43A",
        "consecutivo": "15",
        "direccion": "CL 10 SUR # 43A-15",
    }


def test_direccion_sin_estructura_queda_como_texto():
    partes = e.normalizar_direccion("Barrio  Centro")

    assert partes["direccion"] == "BARRIO CENTRO"
    assert partes["via"] is None and partes["placa"] is None
    assert e.normalizar_direccion(None)["direccion"] is None


def test_estandarizar_agrega_columnas_sin_tocar_las_originales():
    df = pd.DataFrame(
        {
            "nombres": ["José María"],
            "apellidos": ["De La Hoz Muñoz"],
            "numero_documento": ["1.023.456.789"],
            "celular": ["+57 300 123 4567"],
            "correo": ["JM@GMAIL.COM"],
            "direccion": ["Cra 45 No. 10-20"],
            "ciudad": ["Bogotá, D.C."],
        }
    )

    s = e.estandarizar(df)

    fila = s.iloc[0]
    assert fila["nombres"] == "José María"  # original intacta
    assert (fila["primer_nombre"], fila["segundo_nombre"]) == ("JOSE", "MARIA")
    assert fila["nombres_ordenados"] == "JOSE MARIA"
    assert fila["nombres_con_tildes"] == "JOSÉ MARÍA"
    assert (fila["primer_apellido"], fila["segundo_apellido"]) == ("DE LA HOZ", "MUNOZ")
    assert fila["documento"] == "1023456789"
    assert fila["celular_std"] == "3001234567"
    assert fila["correo_std"] == "jm@gmail.com"
    assert fila["direccion_std"] == "KR 45 # 10-20"
    assert fila["ciudad_std"] == "BOGOTA, D.C."
