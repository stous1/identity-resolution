"""Pruebas del escenario residencial de la v1.1 (hogares, predios y familias)."""

import pandas as pd
import pytest

from identidades import escenario_hito3, sinteticos
from identidades.escenario_residencial import (
    EscenarioResidencial,
    Predio,
    etiquetar_personas,
    generar_escenario_residencial,
    texto_direccion,
)


@pytest.fixture(scope="module")
def escenario() -> EscenarioResidencial:
    e = EscenarioResidencial(600, semilla=11)
    e.resultado = e.generar()
    return e


def test_determinista():
    a = generar_escenario_residencial(150, semilla=5)
    b = generar_escenario_residencial(150, semilla=5)
    for x, y in zip(a, b, strict=True):
        pd.testing.assert_frame_equal(x, y)


def test_no_cambia_los_datos_de_versiones_anteriores():
    """Generar el escenario residencial no altera los generadores del hito 2 y el hito 3."""
    antes = sinteticos.generar(50, 42)[0]
    hito3 = escenario_hito3.generar_escenario(50, 3030)[0]
    generar_escenario_residencial(100, semilla=1)
    pd.testing.assert_frame_equal(antes, sinteticos.generar(50, 42)[0])
    pd.testing.assert_frame_equal(hito3, escenario_hito3.generar_escenario(50, 3030)[0])


def test_columnas_como_el_escenario_del_hito3(escenario):
    registros = escenario.resultado[0]
    hito3 = escenario_hito3.generar_escenario(30, 1)[0]
    assert list(registros.columns) == list(hito3.columns)


def test_hijos_con_la_convencion_de_apellidos(escenario):
    personas = escenario.verdad_personas.set_index("cluster")
    revisados = 0
    for hogar in escenario.hogares.values():
        if hogar["tipo"] != "familia":
            continue
        miembros = personas.loc[hogar["miembros"]]
        padres = miembros[miembros["rol"] == "pareja"]
        papa = padres[~padres["mujer"]].iloc[0]
        mama = padres[padres["mujer"]].iloc[0]
        for _, hijo in miembros[miembros["rol"] == "hijo"].iterrows():
            primero, segundo = hijo["apellidos"].split()[:2]
            assert primero == papa["apellidos"].split()[0]
            assert segundo == mama["apellidos"].split()[0]
            revisados += 1
    assert revisados > 20


def test_parejas_sin_apellidos_en_comun(escenario):
    personas = escenario.verdad_personas
    parejas = personas[personas["tipo_hogar"] == "pareja"].groupby("hogar")["apellidos"]
    for _, apellidos in parejas:
        a, b = (set(x.split()) for x in apellidos)
        assert not a & b


def test_apellido_de_casada_en_algunos_registros(escenario):
    registros = escenario.resultado[0]
    casadas = escenario.verdad_personas.dropna(subset=["apellido_casada"])
    assert len(casadas) > 30
    de = registros[registros["cluster"].isin(casadas["cluster"])]["apellidos"]
    assert de.str.contains(r"\b[Dd][Ee]\b", regex=True).mean() > 0.2


def test_tipos_de_predio_y_hogar(escenario):
    personas = escenario.verdad_personas
    assert set(personas["tipo_predio"]) == {"casa", "casa_pisos", "edificio", "conjunto"}
    assert {"pareja", "familia", "convivientes", "pareja_hijo"} <= set(personas["tipo_hogar"])


def test_complementos_de_direccion_variados(escenario):
    direcciones = escenario.resultado[0]["direccion"].dropna().str.upper()
    for patron in (r"\bAPTO?\b", r"\bTORRE\b|\bT \d", r"\bPISO\b", r"\bCONJ|\bCJTO", r"\bINT"):
        assert direcciones.str.contains(patron, regex=True).any(), patron


def test_verdad_tiene_las_categorias_residenciales(escenario):
    verdad = escenario.resultado[2]
    etiquetas = set(verdad[verdad["tipo"] == "direccion"]["etiqueta"])
    assert {"hogar", "pareja", "multifamiliar", "convivencia", "sospechoso"} <= etiquetas


def test_texto_direccion_canonica():
    base = {"via": "CL", "numero_via": "45", "cuadrante": None, "placa": "12", "consecutivo": "30"}
    predio = Predio(0, "conjunto", base, "Cali", "Valle")
    unidad = (("torre", "2"), ("apto", "301"))
    assert texto_direccion(predio, unidad) == "Calle 45 # 12-30 Torre 2 Apto 301"


def test_etiquetar_personas():
    verdad = pd.DataFrame(
        {
            "cluster": [1, 2, 3, 4, 5, 6, 7],
            "familia": [10, 10, 20, 21, 30, 31, 32],
            "rol": ["pareja", "pareja", "conviviente", "conviviente", "solo", "solo", "solo"],
            "hogar": [1, 1, 2, 2, 3, 4, 5],
            "predio": [1, 1, 2, 2, 3, 3, 4],
            "unidad": [None, None, "Apto 1", "Apto 1", "Apto 1", "Apto 2", None],
            "tipo_hogar": ["pareja", "pareja", "convivientes", "convivientes", "solo", "solo",
                           "solo"],
        }
    ).set_index("cluster")  # fmt: skip
    assert etiquetar_personas({1, 2}, verdad) == "pareja"
    assert etiquetar_personas({3, 4}, verdad) == "convivencia"
    assert etiquetar_personas({5, 6}, verdad) == "multifamiliar"
    assert etiquetar_personas({5, 7}, verdad) == "coincidencia"
