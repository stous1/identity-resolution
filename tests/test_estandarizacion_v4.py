"""Pruebas de la estandarización v4: dirección en predio y unidad."""

import random

import pytest

from identidades import estandarizacion as v1
from identidades.escenario_residencial import EscenarioResidencial, texto_direccion
from identidades.estandarizacion_v4 import (
    clave_unidad,
    es_direccion_generica,
    normalizar_direccion_v4,
)


@pytest.mark.parametrize(
    ("texto", "predio", "unidad"),
    [
        ("Calle 45 # 12-30", "CL 45 # 12-30", None),
        ("Carrera 7 # 40-62 Apto 502", "KR 7 # 40-62", "AP502"),
        ("Cra 7 # 40-62 Ap 502", "KR 7 # 40-62", "AP502"),
        ("Cl 140 # 9-50 T 2 Ap 501", "CL 140 # 9-50", "TO2 AP501"),
        ("Calle 140 # 9-50 Torre 2 Apartamento 501", "CL 140 # 9-50", "TO2 AP501"),
        ("CL 140 # 9-50 T2 APTO. 501", "CL 140 # 9-50", "TO2 AP501"),
        ("Calle 140 # 9-50 Interior 3 Apto 201", "CL 140 # 9-50", "IN3 AP201"),
        ("Kr 10 # 5-20 Bloque 4 Apt 302", "KR 10 # 5-20", "BL4 AP302"),
        ("Conjunto Los Pinos Calle 10 # 20-30 Casa 14", "CL 10 # 20-30", "CA14"),
        ("Calle 23 Sur # 5-10 Piso 2", "CL 23 SUR # 5-10", "PI2"),
        ("Calle 23 Sur # 5-10 2do piso", "CL 23 SUR # 5-10", "PI2"),
        ("Calle 23 Sur # 5-10 Segundo Piso", "CL 23 SUR # 5-10", "PI2"),
        ("Calle 23 Sur # 5-10 2 Piso", "CL 23 SUR # 5-10", "PI2"),
        ("KR 104B S # 26B - 82 T7 Apto 304", "KR 104B SUR # 26B-82", "TO7 AP304"),
        ("CRA105C #26A-22", "KR 105C # 26A-22", None),
        ("Calle 10 # 20-30 301", "CL 10 # 20-30", "AP301"),
    ],
)
def test_predio_y_unidad(texto, predio, unidad):
    d = normalizar_direccion_v4(texto)
    assert (d["predio"], d["unidad"]) == (predio, unidad)


def test_no_parte_el_numero_de_via():
    """ "136" no se lee como número 1, placa 3 y consecutivo 6."""
    d = normalizar_direccion_v4("cll. 136 a s n 105 20 la floresta")
    assert d["predio"] == "CL 136A SUR # 105-20"


def test_nombre_del_conjunto_no_entra_en_la_clave():
    a = normalizar_direccion_v4("Calle 10 # 20-30 Conjunto Residencial Los Pinos Torre 1 Apto 101")
    b = normalizar_direccion_v4("Calle 10 # 20-30 T 1 Ap 101")
    assert a["direccion"] == b["direccion"] == "CL 10 # 20-30 TO1 AP101"
    assert a["conjunto"] == "LOS PINOS"


def test_sin_complemento_igual_que_v1():
    for texto in ("Calle 45 # 12-30", "Av 40B Sur No 43-89", "Diagonal 48 # 22-15"):
        assert (
            normalizar_direccion_v4(texto)["direccion"]
            == v1.normalizar_direccion(texto)["direccion"]
        )


def test_clave_unidad_en_orden_fijo():
    assert clave_unidad({"apto": "301", "torre": "2"}) == "TO2 AP301"
    assert clave_unidad({}) is None


def test_genericas():
    assert es_direccion_generica("CENTRO")
    assert es_direccion_generica("Sin dirección")
    assert not es_direccion_generica("Vereda El Salitre Finca La Esperanza")
    assert not es_direccion_generica("Carrera 7 # 40-62 Apto 502")


def test_recupera_las_direcciones_del_escenario_residencial():
    """Cada forma de escribir la dirección de un hogar da su mismo predio y unidad."""
    e = EscenarioResidencial(300, semilla=21)
    e.generar()
    rng = random.Random(0)
    for hogar in e.hogares.values():
        predio = e.predios[hogar["predio"]]
        canonica = normalizar_direccion_v4(texto_direccion(predio, hogar["unidad"]))
        for _ in range(3):
            d = normalizar_direccion_v4(texto_direccion(predio, hogar["unidad"], rng, e.r))
            assert d["predio"] == canonica["predio"]
            assert d["unidad"] in (canonica["unidad"], None)
