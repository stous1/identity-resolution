"""Las cifras del README y de Pages salen de los JSON publicados."""

import a7_afirmaciones as a7

# Diferencias conocidas y documentadas en audit/INFORME.md (redondeo, sin efecto material).
CONOCIDAS = {"**200 mil registros** (240 mil enlaces"}


def test_formatos():
    assert a7.d(0.97038) == "0,970"
    assert a7.p(0.9975) == "99,8"
    assert a7.p(1.0) == "100"
    assert a7.s(-0.2041, 1, 100) == "−20,4"
    assert a7.s(0.0, 3) == "0,000"
    assert a7.m(1262) == "1.262"


def test_cifras_publicadas_coinciden_con_los_json():
    filas = a7.cifras()
    problemas = {f["cifra"] for f in filas if not (f["coincide"] and f["en_documento"])}
    assert problemas == CONOCIDAS
    assert len(filas) >= 100


def test_comparar_json_detecta_diferencias_y_tolera_tiempos():
    a = {"x": 1.0, "y": {"z": [1, 2]}, "segundos": 3}
    b = {"x": 1.0 + 1e-12, "y": {"z": [1, 3]}, "segundos": 9}
    difs = a7.comparar_json(a, b)
    assert [d["ruta"] for d in difs] == ["/y/z[1]"]
