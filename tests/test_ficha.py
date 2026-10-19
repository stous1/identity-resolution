"""Pruebas de la ficha de cliente único (v1.1.1)."""

import json

import pandas as pd
import pytest

from identidades import flujo_v111, registro_oro, rutas


def _candidatos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cluster_id": [1, 1, 1, 2],
            "unique_id": [10, 11, 12, 20],
            "fecha": pd.to_datetime(["2020-01-01", "2023-01-01", "2021-01-01", "2022-01-01"]),
            "rango": [5, 1, 3, 4],
            "validado": [True, False, False, True],
            "campo": "celular",
            "valor": ["3001", "3002", "3002", "3009"],
        }
    )


@pytest.mark.parametrize("regla", registro_oro.REGLAS)
def test_oro_con_origen_elige_lo_mismo_que_registro_oro(regla):
    cand = _candidatos()
    con_origen = flujo_v111.oro_con_origen(cand, {"celular": regla})
    original = registro_oro.registro_de_oro(cand, {"celular": regla})
    pd.testing.assert_frame_equal(
        con_origen[["cluster_id", "campo", "valor"]].reset_index(drop=True),
        original.reset_index(drop=True),
    )
    assert set(con_origen["regla"]) == {regla}


def test_oro_con_origen_conserva_el_registro():
    oro = flujo_v111.oro_con_origen(_candidatos(), {"celular": "fuente_confiable"})
    assert oro.set_index("cluster_id").loc[1, "unique_id"] == 10


def test_historia_registra_solo_los_cambios():
    filas = pd.DataFrame(
        {
            "unique_id": [1, 2, 3],
            "fecha_actualizacion": ["2015-01-01", "2018-01-01", "2020-01-01"],
            "canal": ["sucursal", "app", "web"],
            "celular": ["3001112233", "300 111 2233", "3104445566"],
            "correo": [None, "a@b.com", "a@b.com"],
            "direccion": ["Calle 1 # 2-3 Apto 101", "CL 1 # 2-3 AP 101", "Kr 9 # 8-7"],
        }
    )
    h = flujo_v111._historia(filas)
    assert [c["valor"] for c in h["celular"]] == ["3001112233", "3104445566"]
    assert [c["valor"] for c in h["direccion"]] == ["CL 1 # 2-3 AP101", "KR 9 # 8-7"]
    assert len(h["correo"]) == 1


def test_fichas_publicadas_tienen_los_destacados():
    ruta = rutas.DOCS_RESULTADOS_V11 / "fichas.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert len(datos["destacados"]) == 4
    for d in datos["destacados"]:
        ficha = datos["clientes"][d["id"]]
        assert ficha["registros"] and ficha["oro"]
    esther = datos["clientes"][datos["destacados"][-1]["id"]]
    assert any(a["tipo"] == "documento_compartido" for a in esther["alertas"])
    assert ruta.stat().st_size < 600_000  # la página debe cargar liviana
