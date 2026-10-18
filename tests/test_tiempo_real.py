"""Pruebas de la vinculación en tiempo real y del servicio local."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from identidades import flujo_hito2b, tiempo_real
from identidades.servicio import crear_app


@pytest.fixture(scope="module")
def vinculador():
    configuracion, umbral = flujo_hito2b.cargar_congelado_v2()
    registros_base, consultas, _ = tiempo_real.preparar_evaluacion(
        n_personas=400, semilla=21, max_consultas=15
    )
    base = tiempo_real.construir_base(registros_base, configuracion, umbral)
    v = tiempo_real.Vinculador(
        base, configuracion, umbral, relleno=tiempo_real.telefonos_de_relleno(registros_base)
    )
    return v, consultas


def test_preparar_evaluacion_separa_existentes_y_nuevas():
    registros_base, consultas, _ = tiempo_real.preparar_evaluacion(300, 5, max_consultas=10)

    existentes = consultas[consultas["existe"]]
    nuevas = consultas[~consultas["existe"]]
    assert set(existentes["cluster"]) <= set(registros_base["cluster"])
    assert set(nuevas["cluster"]).isdisjoint(registros_base["cluster"])
    assert not set(consultas["unique_id"]) & set(registros_base["unique_id"])


def test_base_tiene_un_renglon_por_cliente(vinculador):
    v, _ = vinculador

    assert v.base["unique_id"].is_unique
    assert {"numero_documento", "nombres", "apellidos", "celular"} <= set(v.base.columns)


def test_camino_compilado_igual_a_splink(vinculador):
    v, consultas = vinculador
    for fila in consultas.head(10).to_dict("records"):
        rapido = v.comparar(fila, compilado=True).sort_values(["unique_id_l", "unique_id_r"])
        splink = v.comparar(fila, compilado=False).sort_values(["unique_id_l", "unique_id_r"])
        assert len(rapido) == len(splink)
        pd.testing.assert_series_equal(
            rapido["match_weight"].reset_index(drop=True),
            splink["match_weight"].reset_index(drop=True),
            check_names=False,
        )


def test_consulta_de_cliente_existente(vinculador):
    v, consultas = vinculador
    fila = consultas[consultas["existe"]].iloc[0].to_dict()

    r = v.consultar(fila)

    assert r["decision"] in {"cliente", "revisar", "nuevo"}
    if r["decision"] == "cliente":
        assert (
            v.base.set_index("unique_id").at[r["cliente"]["cliente_id"], "cluster"]
            == fila["cluster"]
        )
        assert r["explicacion"][0]["peso"] > 0


def test_evaluar_reporta_precision_recall_y_latencia(vinculador):
    v, consultas = vinculador

    ev = tiempo_real.evaluar(v, consultas, n_bootstrap=20)

    assert ev["consultas"] == len(consultas)
    assert 0 <= ev["precision"]["valor"] <= 1 and 0 <= ev["recall"]["valor"] <= 1
    assert ev["latencia_ms"]["mediana"] > 0


def test_servicio(vinculador):
    v, consultas = vinculador
    cliente = TestClient(crear_app(v))

    assert cliente.get("/salud").json()["estado"] == "ok"
    fila = consultas.iloc[0].to_dict()
    campos = ["tipo_documento", "numero_documento", "nombres", "apellidos", "fecha_nacimiento",
              "celular", "correo", "direccion", "ciudad", "departamento"]  # fmt: skip
    cuerpo = {c: (None if pd.isna(fila[c]) else str(fila[c])) for c in campos}
    r = cliente.post("/consultar", json=cuerpo)

    assert r.status_code == 200
    datos = r.json()
    assert datos["decision"] in {"cliente", "revisar", "nuevo"}
    assert "cluster" not in datos.get("cliente", {})  # la verdad no se expone
