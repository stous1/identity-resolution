"""Pruebas del generador de errores de la tercera prueba ciega."""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from identidades import errores_ciegos_3 as ec3
from identidades import sinteticos


@pytest.fixture(scope="module")
def personas() -> pd.DataFrame:
    _, personas = sinteticos.generar(600, 77)
    return personas


@pytest.fixture(scope="module")
def captura(personas: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return ec3.capturar_con_traza(personas, semilla=11)


def test_columnas_y_tipos(captura, personas) -> None:
    registros, _, _ = captura
    assert list(registros.columns) == ec3.COLUMNAS
    assert registros["cluster"].dtype == "int64"
    assert sorted(registros["unique_id"]) == list(range(len(registros)))
    assert set(registros["cluster"]) == set(personas["cluster"].astype(int))
    for columna in ec3.COLUMNAS:
        if columna in ("unique_id", "cluster"):
            continue
        valores = registros[columna].tolist()
        assert all(v is None or isinstance(v, str) for v in valores), columna


def test_registros_por_persona_y_barajado(captura) -> None:
    registros, condiciones, _ = captura
    conteo = registros.groupby("cluster").size()
    assert conteo.min() >= 1 and conteo.max() <= 6
    assert (conteo.sort_index().values == condiciones.set_index("cluster")["n_registros"]).all()
    # Las filas están barajadas: los registros de una persona no quedan contiguos.
    assert not registros["cluster"].is_monotonic_increasing


def test_determinismo(personas) -> None:
    a, ca = ec3.capturar(personas, semilla=5)
    b, cb = ec3.capturar(personas, semilla=5)
    c, _ = ec3.capturar(personas, semilla=6)
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(ca, cb)
    assert not a.equals(c)


def test_condiciones(captura, personas) -> None:
    _, condiciones, _ = captura
    assert len(condiciones) == len(personas)
    assert condiciones["cluster"].is_unique
    for columna in ec3.CONDICIONES:
        assert condiciones[columna].dtype == bool, columna
        # Con 600 personas cada condición aparece, pero nunca en todas.
        assert 0 < condiciones[columna].sum() < len(condiciones), columna
    # El apellido de casada solo se da en quien parece mujer por el nombre.
    casadas = condiciones[condiciones["apellido_casada"]]
    assert casadas["mujer_aparente"].all()


def test_condiciones_documento_coinciden_con_registros(captura, personas) -> None:
    registros, condiciones, _ = captura
    cond = condiciones.set_index("cluster")
    verdadero = personas.set_index("cluster")["numero_documento"].astype(str)
    sin_doc = registros.groupby("cluster")["numero_documento"].apply(lambda s: s.isna().any())
    assert (sin_doc.sort_index() == cond["sin_documento"].sort_index()).all()

    def distinto(fila: pd.Series) -> bool:
        if fila["numero_documento"] is None:
            return False
        digitos = "".join(c for c in fila["numero_documento"] if c.isdigit()).lstrip("0")
        return digitos != verdadero[fila["cluster"]].lstrip("0")

    alterado = registros.apply(distinto, axis=1).groupby(registros["cluster"]).any()
    assert (alterado.sort_index() == cond["documento_alterado"].sort_index()).all()


def test_condiciones_se_manifiestan_en_la_traza(captura) -> None:
    registros, condiciones, traza = captura
    cluster_de = registros.set_index("unique_id")["cluster"]
    traza = traza.assign(cluster=traza["unique_id"].map(cluster_de))
    con_mudanza = set(traza.loc[traza["error"] == "mudanza_direccion_nueva", "cluster"])
    assert con_mudanza == set(condiciones.loc[condiciones["mudanza"], "cluster"])
    con_apodo = set(traza.loc[traza["error"] == "apodo", "cluster"])
    assert con_apodo == set(condiciones.loc[condiciones["con_apodo"], "cluster"])


def test_registros_identificables(captura) -> None:
    registros, _, _ = captura
    assert (registros["nombres"].notna() | registros["apellidos"].notna()).all()
    claves = ["numero_documento", "fecha_nacimiento", "celular", "correo", "direccion"]
    assert (registros[claves].notna().sum(axis=1) >= 2).all()


def test_sin_errores_de_documento(personas) -> None:
    tasas = dataclasses.replace(
        ec3.TasasCiegas3(),
        sin_documento=0.0,
        documento_alterado=0.0,
        tarjeta_identidad=0.0,
    )
    registros, condiciones = ec3.capturar(personas, semilla=3, tasas=tasas)
    assert registros["numero_documento"].notna().all()
    assert not condiciones["sin_documento"].any()
    assert not condiciones["documento_alterado"].any()


def test_mujer_aparente() -> None:
    assert ec3.es_mujer_aparente("Patricia")
    assert ec3.es_mujer_aparente("Luz")
    assert ec3.es_mujer_aparente("Mercedes")
    assert not ec3.es_mujer_aparente("Humberto")
    assert not ec3.es_mujer_aparente(None)


def test_describir_tasas() -> None:
    descripcion = ec3.describir_tasas(ec3.TasasCiegas3())
    assert descripcion["casada"] == ec3.TasasCiegas3().casada
    assert set(descripcion["pesos_canal"]) == set(ec3.CANALES)
    assert "multiplicadores_canal" in descripcion
