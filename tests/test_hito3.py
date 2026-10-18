"""Pruebas del hito 3: escenario, registro de oro, grafo compartido y puentes."""

from datetime import date

import pandas as pd
import pytest

from identidades import grafo_compartido as gc
from identidades import puentes
from identidades import registro_oro as ro
from identidades.escenario_hito3 import Escenario, generar_escenario, normalizar


@pytest.fixture(scope="module")
def escenario():
    return generar_escenario(n_personas=300, semilla=11)


# ---------- Escenario ----------


def test_escenario_tiene_metadatos_y_verdad(escenario):
    registros, verdad, compartidos = escenario

    assert {"fecha_actualizacion", "canal", "validado", "origen"} <= set(registros.columns)
    assert registros["unique_id"].is_unique
    assert set(registros["cluster"]) == set(verdad["cluster"])
    assert registros["canal"].isin(["sucursal", "app", "web", "call_center", "corresponsal"]).all()
    assert set(compartidos["etiqueta"]) <= {"relleno", "hogar", "sospechoso", "coincidencia"}
    assert (compartidos["personas"] >= 2).all()


def test_escenario_es_reproducible():
    a = generar_escenario(n_personas=50, semilla=4)
    b = generar_escenario(n_personas=50, semilla=4)

    for x, y in zip(a, b, strict=True):
        pd.testing.assert_frame_equal(x, y)


def test_vigente_en_toma_el_ultimo_valor_hasta_la_fecha():
    historia = [(date(2012, 1, 1), "viejo"), (date(2020, 6, 1), "nuevo")]

    assert Escenario.vigente_en(historia, date(2019, 12, 31)) == "viejo"
    assert Escenario.vigente_en(historia, date(2020, 6, 1)) == "nuevo"


def test_registros_validados_no_tienen_errores_de_contacto(escenario):
    registros, verdad, _ = escenario
    validados = registros[registros["validado"] & registros["origen"].eq("normal")]
    documento = verdad.set_index("cluster")["documento"]

    assert (validados["numero_documento"] == validados["cluster"].map(documento)).all()


def test_sospechosos_inyectados_quedan_etiquetados(escenario):
    registros, _, compartidos = escenario

    assert registros["origen"].str.startswith("anillo").any()
    assert (compartidos["etiqueta"] == "sospechoso").any()


# ---------- Registro de oro ----------


def _registros_oro() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    registros = pd.DataFrame(
        {
            "unique_id": [0, 1, 2],
            "numero_documento": ["1023", "1023", "1028"],
            "nombres": ["Ana", "Ana", "Ana"],
            "apellidos": ["Ruiz", "Ruiz", "Ruiz"],
            "fecha_nacimiento": ["1990-01-01"] * 3,
            "celular": ["3001111111", "3002222222", "3000000000"],
            "correo": [None, None, None],
            "direccion": [None, None, None],
            "fecha_actualizacion": ["2015-01-01", "2020-01-01", "2024-01-01"],
            "canal": ["sucursal", "web", "corresponsal"],
            "validado": [True, False, False],
            "cluster": [7, 7, 7],
        }
    )
    clusters = pd.DataFrame({"unique_id": [0, 1, 2], "cluster_id": ["c"] * 3})
    verdad = pd.DataFrame(
        {
            "cluster": [7],
            "documento": ["1023"],
            "nombres": ["Ana"],
            "apellidos": ["Ruiz"],
            "fecha_nacimiento": ["1990-01-01"],
            "celular": ["3002222222"],
            "correo": [None],
            "direccion": [None],
        }
    )
    return registros, clusters, verdad


def test_reglas_de_supervivencia():
    registros, clusters, _ = _registros_oro()
    cand = ro.candidatos(registros, clusters, {"celular": {"3000000000"}})

    def valor(regla, campo):
        oro = ro.aplicar_regla(cand, regla)
        return oro[oro["campo"] == campo]["valor"].iloc[0]

    # El relleno no sobrevive: el más reciente válido es el del registro 1.
    assert valor("mas_reciente", "celular") == "3002222222"
    assert valor("validado", "celular") == "3001111111"
    assert valor("fuente_confiable", "documento") == "1023"
    assert valor("mas_reciente", "documento") == "1028"
    assert valor("frecuente", "documento") == "1023"


def test_evaluar_y_techo_alcanzable():
    registros, clusters, verdad = _registros_oro()
    cand = ro.candidatos(registros, clusters)
    tabla = ro.evaluar(ro.aplicar_regla(cand, "validado"), clusters, registros, verdad)

    aciertos = tabla.set_index("campo")["acierto"]
    assert aciertos["documento"] and not aciertos["celular"]
    techo = ro.alcanzable(cand, tabla)
    assert techo["celular"] == 1.0 and techo["correo"] == 0.0


def test_elegir_reglas_por_campo():
    aciertos = {
        "mas_reciente": {"x": {"valor": 0.9}, "y": {"valor": 0.5}},
        "validado": {"x": {"valor": 0.7}, "y": {"valor": 0.8}},
        "fuente_confiable": {"x": {"valor": 0.9}, "y": {"valor": 0.6}},
        "frecuente": {"x": {"valor": 0.1}, "y": {"valor": 0.1}},
    }

    assert ro.elegir_reglas(aciertos) == {"x": "mas_reciente", "y": "validado"}


# ---------- Grafo de identidad compartida ----------


@pytest.mark.parametrize(
    ("tipo", "valor", "esperado"),
    [
        ("celular", "3000000000", True),
        ("celular", "3001234567", True),
        ("celular", "3157045960", False),
        ("correo", "notiene@gmail.com", True),
        ("correo", "na@na.com", True),
        ("correo", "ana.ruiz@gmail.com", False),
        ("direccion", "BARRIO CENTRO", True),
        ("direccion", "KR 45 # 10-20", False),
    ],
)
def test_es_generico(tipo, valor, esperado):
    assert gc.es_generico(tipo, valor) is esperado


def test_apellido_parecido_tolera_digitacion():
    assert gc.apellido_parecido({"PABON"}, {"PABNO", "QUINTERO"})
    assert not gc.apellido_parecido({"PABON"}, {"GOMEZ"})


def test_clasificar_grupos():
    grupos = pd.DataFrame(
        {
            "tipo": ["documento", "celular", "celular", "direccion", "correo"],
            "valor": ["1", "3000000000", "3157045960", "KR 1 # 2-3", "x@y.com"],
            "clientes": [2, 3, 2, 2, 20],
            "frac_apellido_comun": [0.0, 0.0, 1.0, 0.0, 0.0],
            "generico": [False, True, False, False, False],
        }
    )

    prediccion = gc.clasificar(grupos, gc.ParametrosClasificacion(max_clientes=6, min_apellido=0.5))

    assert prediccion.tolist() == ["sospechoso", "relleno", "hogar", "sospechoso", "relleno"]


def test_grafo_sobre_el_escenario(escenario):
    registros, _, verdad = escenario
    clusters = registros[["unique_id"]].assign(cluster_id=registros["cluster"])

    grupos = gc.grupos_compartidos(registros, clusters)
    unidos = gc.unir_verdad(
        grupos.assign(prediccion=gc.clasificar(grupos, gc.ParametrosClasificacion())), verdad
    )
    m = gc.metricas(unidos)

    assert len(grupos) == len(verdad)  # con los clústeres verdaderos, mismos grupos
    assert 0 <= m["exactitud"] <= 1
    assert set(m["por_clase"]) == set(gc.CLASES)


# ---------- Puentes ----------


def _cadena() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Dos personas (0-1-2 y 3-4) unidas por el puente débil 2-3."""
    aristas = pd.DataFrame(
        {
            "id_l": [0, 1, 0, 2, 3],
            "id_r": [1, 2, 2, 3, 4],
            "is_bridge": [False, False, False, True, True],
            "match_weight": [20.0, 20.0, 20.0, 4.0, 18.0],
            "match_probability": [1.0, 1.0, 1.0, 0.9, 1.0],
            "cluster_id": [0] * 5,
        }
    )
    aristas["lado_menor"] = puentes._lado_menor(aristas)
    clusters = pd.DataFrame({"unique_id": range(5), "cluster_id": [0] * 5})
    df = pd.DataFrame({"unique_id": range(5), "cluster": [0, 0, 0, 1, 1]})
    return aristas, clusters, df


def test_lado_menor_de_cada_puente():
    aristas, _, _ = _cadena()

    assert aristas["lado_menor"].tolist() == [0, 0, 0, 2, 1]


def test_partir_puente_debil_separa_personas():
    aristas, clusters, df = _cadena()

    nuevos = puentes.partir(clusters, aristas, max_peso=10, min_lado=2)

    assert nuevos.groupby("cluster_id").size().sort_values().tolist() == [2, 3]
    assert puentes.mezclados(nuevos, df) == set()
    resultado = puentes.evaluar_politica(clusters, aristas, df, 10, 2)
    assert resultado["mezclados_antes"] == 1 and resultado["mezclados_despues"] == 0
    assert resultado["revision_mezclas_atrapadas"] == 1


def test_mezclas_sostenidas_por_puente():
    aristas, clusters, df = _cadena()

    r = puentes.mezclas_sostenidas_por_puente(clusters, aristas, df)

    assert r == {"mezclados": 1, "sostenidos_por_puente": 1, "pesos_de_esos_puentes": [4.0]}


def test_normalizar_valores_compartidos():
    assert normalizar("celular", "+57 300 111 2222") == "3001112222"
    assert normalizar("documento", "CC 1.023.456") == "1023456"
    assert normalizar("direccion", "Cra 45 No. 10-20") == "KR 45 # 10-20"
