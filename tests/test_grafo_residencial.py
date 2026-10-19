"""Pruebas del grafo de identidad compartida residencial (v1.1)."""

import pandas as pd
import pytest

from identidades import diagnostico_v11
from identidades import grafo_residencial as gr
from identidades.escenario_residencial import EscenarioResidencial, verdad_compartidos_residencial


@pytest.fixture(scope="module")
def ejemplos() -> pd.DataFrame:
    registros = diagnostico_v11.registros_ejemplo()
    clusters = registros[["unique_id"]].assign(cluster_id=registros["cluster"])
    grupos = gr.grupos_residenciales(registros, clusters)
    caso = registros.set_index("cluster")["caso"]
    return grupos.assign(
        prediccion=gr.clasificar(grupos, gr.ParametrosGrafo()),
        caso=grupos["ids_clientes"].map(lambda ids: caso[ids[0]]),
    )


@pytest.mark.parametrize(
    ("caso", "tipo", "clase"),
    [
        ("pareja_sin_apellidos", "direccion", "convivencia"),
        ("pareja_casada", "direccion", "hogar"),
        ("vecinas_casadas", "direccion", "multifamiliar"),
        ("companeros_apto", "direccion", "convivencia"),
        ("conjunto", "direccion", "multifamiliar"),
        ("casa_dos_pisos", "direccion", "hogar"),
        ("casa_dos_pisos", "celular", "hogar"),
        ("casa_dos_pisos_sin_piso", "direccion", "hogar"),
        ("familia_convencion", "direccion", "hogar"),
        ("anillo_control", "celular", "sospechoso"),
    ],
)
def test_casos_del_diagnostico(ejemplos, caso, tipo, clase):
    fila = ejemplos[(ejemplos["caso"] == caso) & (ejemplos["tipo"] == tipo)]
    assert list(fila["prediccion"]) == [clase]


def test_companeros_quedan_en_un_solo_grupo(ejemplos):
    """ "Apto 502" y "Ap 502" son el mismo predio: los tres compañeros, juntos."""
    fila = ejemplos[ejemplos["caso"] == "companeros_apto"].iloc[0]
    assert fila["clientes"] == 3 and fila["unidades"] == 1


def test_tipo_de_predio(ejemplos):
    tipo = ejemplos[ejemplos["tipo"] == "direccion"].set_index("caso")["tipo_predio"]
    assert tipo["conjunto"] == "conjunto"
    assert tipo["companeros_apto"] == "edificio"
    assert tipo["casa_dos_pisos"] == "casa_pisos"
    assert tipo["pareja_casada"] == "casa"


def test_apellidos_sin_particulas_y_casada():
    assert gr.apellidos_cliente("Rincón de Salazar") == (["RINCON"], "SALAZAR")
    assert gr.apellidos_cliente("Vargas de Ospina")[0] == ["VARGAS"]
    assert gr.apellidos_cliente("De la Hoz Pérez")[0] == ["HOZ", "PEREZ"]


def test_senal_de_convencion():
    clientes = {
        1: gr.Cliente({"RAMIREZ"}, {"SOTO"}, set()),
        2: gr.Cliente({"TORRES"}, {"VELEZ"}, set()),
        3: gr.Cliente({"RAMIREZ"}, {"TORRES"}, set()),
    }
    aristas = gr.senales_hogar([1, 2, 3], clientes)
    assert (1, 2) in aristas["convencion"]


def test_documento_compartido_siempre_es_sospechoso():
    fila = {"tipo": "documento", "generico": False}
    assert gr.clasificar_fila(fila, gr.ParametrosGrafo()) == "sospechoso"


def test_metricas_con_aceptables():
    c = pd.DataFrame(
        {
            "etiqueta": ["pareja", "pareja", "convivencia", "sospechoso", "multifamiliar"],
            "prediccion": ["hogar", "convivencia", "sospechoso", "sospechoso", "multifamiliar"],
        }
    )
    m = gr.metricas(c)
    assert m["exactitud"] == pytest.approx(4 / 5)
    assert m["falsa_sospecha"]["marcados"] == 1
    assert m["sospechoso"]["precision"] == pytest.approx(0.5)


def test_elegir_parametros_mejora_al_clasificador_anterior():
    """En un escenario residencial (clústeres verdaderos), el clasificador nuevo marca
    como sospechosos muchos menos grupos benignos que el del hito 3."""
    from identidades import grafo_compartido as gc

    e = EscenarioResidencial(700, semilla=33)
    registros, _, verdad_anterior = e.generar()
    clusters = registros[["unique_id"]].assign(cluster_id=registros["cluster"])
    verdad = verdad_compartidos_residencial(
        registros, e.verdad_personas, e.sospechosos, gr.normalizar_residencial
    )
    nuevos = gr.unir_verdad(gr.grupos_residenciales(registros, clusters), verdad)
    p, _ = gr.elegir_parametros([nuevos], {"max_convivencia": (3, 4), "min_familia": (0.75,)})
    nuevos = nuevos.assign(prediccion=gr.clasificar(nuevos, p))
    anteriores = gc.grupos_compartidos(registros, clusters)
    anteriores = gc.unir_verdad(
        anteriores.assign(
            prediccion=gc.clasificar(anteriores, gc.ParametrosClasificacion(15, 0.5))
        ),
        verdad_anterior,
    )
    m_nuevo, m_anterior = gr.metricas(nuevos), gr.metricas(anteriores)
    assert m_nuevo["falsa_sospecha"]["tasa"] < m_anterior["falsa_sospecha"]["tasa"] / 3
    assert m_nuevo["sospechoso"]["recall"] >= 0.8
