"""Pruebas del diagnóstico previo de la v1.1 (lo que falla en el grafo del hito 3)."""

import pytest

from identidades import diagnostico_v11, grafo_compartido
from identidades.sinteticos_fecha import fecha_fija


def _por_caso() -> dict:
    return {c["caso"]: c for c in diagnostico_v11.resumen_por_caso()}


def test_pareja_sin_apellidos_sale_sospechosa_en_el_grafo_anterior():
    caso = _por_caso()["pareja_sin_apellidos"]
    assert [g["clase"] for g in caso["grupos"]] == ["sospechoso"]


def test_apartamento_con_complemento_sale_como_relleno():
    caso = _por_caso()["companeros_apto"]
    assert [g["clase"] for g in caso["grupos"]] == ["relleno"]
    # "Ap 502" en vez de "Apto 502" deja a la tercera compañera fuera del grupo.
    assert caso["personas_en_algun_grupo"] == 2


def test_conjunto_no_forma_ningun_grupo():
    assert _por_caso()["conjunto"]["grupos"] == []


def test_control_anillo_sigue_siendo_sospechoso():
    assert [g["clase"] for g in _por_caso()["anillo_control"]["grupos"]] == ["sospechoso"]


def test_particula_de_cuenta_como_apellido_comun():
    """Dos señoras casadas sin relación "comparten" el apellido "DE" en el grafo anterior."""
    assert grafo_compartido.apellido_parecido({"VARGAS", "DE"}, {"CARDENAS", "DE"})


def test_niveles_de_direccion_del_v3():
    niveles = {n["par"]: n for n in diagnostico_v11.niveles_direccion_v3()}
    assert niveles["mismo apartamento, otra escritura"]["bits_v3"] < 0
    assert niveles["mismo edificio, otro apartamento"]["bits_v3"] > 0
    assert niveles["predios distintos en la misma cuadra"]["nivel_v3"].startswith("Misma v")


def test_fecha_fija_hace_reproducible_a_faker():
    from faker import Faker

    def nacimiento() -> str:
        fake = Faker("es_CO")
        fake.seed_instance(1)
        return fake.date_of_birth(minimum_age=18, maximum_age=85).isoformat()

    with fecha_fija(2026, 1, 1):
        a = nacimiento()
    with fecha_fija(2026, 1, 1):
        b = nacimiento()
    with fecha_fija(2030, 6, 1):
        c = nacimiento()
    assert a == b != c


@pytest.mark.integracion
def test_caso_esther_es_una_suplantacion_inyectada():
    caso = diagnostico_v11.caso_esther()
    origenes = {r["origen"] for r in caso["registros"]}
    assert origenes == {"normal", "suplantacion"}
    assert caso["etiqueta_verdadera_del_grupo"] == ["sospechoso"]
    duenos = caso["dueno_del_documento"]
    victima = [r for r in caso["registros"] if r["persona_verdadera"] in duenos]
    assert all("ESTH" in r["nombre"].upper() or "ETSH" in r["nombre"].upper() for r in victima)
