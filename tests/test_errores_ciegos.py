"""Pruebas del generador independiente de errores de la prueba ciega."""

from dataclasses import fields, replace

import pandas as pd
import pytest

from identidades import errores_ciegos as ec
from identidades import sinteticos


@pytest.fixture(scope="module")
def personas() -> pd.DataFrame:
    _, personas = sinteticos.generar(n_personas=300, semilla=7)
    return personas


@pytest.fixture(scope="module")
def limpios(personas: pd.DataFrame) -> pd.DataFrame:
    registros, _ = ec.capturar(personas, semilla=3, tasas=ec.TasasCiegas.ceros())
    return registros


def _solo(error: str) -> ec.TasasCiegas:
    return replace(ec.TasasCiegas.ceros(), **{error: 1.0})


def test_reproducible(personas: pd.DataFrame) -> None:
    a_reg, a_cond = ec.capturar(personas, semilla=11)
    b_reg, b_cond = ec.capturar(personas, semilla=11)
    pd.testing.assert_frame_equal(a_reg, b_reg)
    pd.testing.assert_frame_equal(a_cond, b_cond)
    c_reg, _ = ec.capturar(personas, semilla=12)
    assert not a_reg.equals(c_reg)


def test_columnas_y_ids(personas: pd.DataFrame) -> None:
    registros, condiciones = ec.capturar(personas, semilla=1)
    assert list(registros.columns) == ec.COLUMNAS
    assert registros["unique_id"].is_unique
    assert sorted(registros["unique_id"]) == list(range(len(registros)))
    assert set(registros["cluster"]) == set(personas["cluster"])
    assert list(condiciones.columns) == ["cluster", *ec.CONDICIONES]
    assert set(condiciones["cluster"]) == set(personas["cluster"])
    assert {"rural", "con_apodo"} <= set(condiciones.columns)
    for columna in ec.CONDICIONES:
        assert condiciones[columna].dtype == bool


def test_registros_por_persona(personas: pd.DataFrame) -> None:
    registros, condiciones = ec.capturar(personas, semilla=1)
    conteo = registros.groupby("cluster").size()
    assert conteo.between(1, 6).all()
    assert 0.25 < (conteo == 1).mean() < 0.45
    unicos = condiciones.set_index("cluster")["un_solo_registro"]
    assert (unicos == (conteo.reindex(unicos.index) == 1)).all()


def test_faltantes_son_none(personas: pd.DataFrame) -> None:
    registros, _ = ec.capturar(personas, semilla=1, tasas=_solo("faltante"))
    vacios = registros.isna()
    assert vacios.any().any()
    for columna in registros.columns:
        assert all(v is None for v in registros.loc[vacios[columna], columna])
    assert registros["numero_documento"].notna().all()
    assert registros["nombres"].notna().all()


def test_tasas_cero_dan_registros_limpios(personas: pd.DataFrame, limpios: pd.DataFrame) -> None:
    por_cluster = personas.set_index("cluster")
    for _, reg in limpios.iterrows():
        esperado = ec.registro_limpio(por_cluster.loc[reg["cluster"]])
        assert {k: reg[k] for k in esperado} == esperado
    fila = limpios.iloc[0]
    assert "#" in fila["direccion"]


@pytest.mark.parametrize("error", [f.name for f in fields(ec.TasasCiegas)])
def test_cada_error_aparece(error: str, personas: pd.DataFrame, limpios: pd.DataFrame) -> None:
    registros, _ = ec.capturar(personas, semilla=3, tasas=_solo(error))
    assert len(registros) == len(limpios)
    cambiado = (registros.drop(columns="unique_id") != limpios.drop(columns="unique_id")) & ~(
        registros.isna() & limpios.isna()
    )
    assert cambiado.any(axis=1).mean() > 0.01, error


def test_rural_todas_las_direcciones(personas: pd.DataFrame, limpios: pd.DataFrame) -> None:
    registros, condiciones = ec.capturar(personas, semilla=3, tasas=_solo("rural"))
    assert condiciones["rural"].all()
    claves = ("vereda", "vda", "finca", "fca", "km", "kilómetro", "corr", "predio")
    assert registros["direccion"].str.lower().map(lambda d: any(k in d for k in claves)).all()
    _, sin_rural = ec.capturar(personas, semilla=3, tasas=ec.TasasCiegas.ceros())
    assert not sin_rural["rural"].any()


def test_apodos(personas: pd.DataFrame, limpios: pd.DataFrame) -> None:
    registros, condiciones = ec.capturar(personas, semilla=3, tasas=_solo("apodo"))
    assert condiciones["con_apodo"].any()
    conocidos = {a for lista in ec.APODOS.values() for a in lista}
    conocidos |= {a for lista in ec.APODOS_COMPUESTOS.values() for a in lista}
    primeros = registros["nombres"].str.split().str[0]
    assert primeros.isin(conocidos | {a.split()[0] for a in conocidos}).any()
    con_apodo = set(condiciones.loc[condiciones["con_apodo"], "cluster"])
    distintos = registros["nombres"] != limpios["nombres"]
    assert set(registros.loc[distintos, "cluster"]) == con_apodo


def test_apodo_diccionario() -> None:
    assert ec.apodo("José", None, ec._rng(0, "x")) in {"Pepe", "Chepe"}
    assert ec.apodo("Ana", "María", ec._rng(0, "x")) in {"Anamaría", "Anamari"}
    assert ec.apodo("Juan", "David", ec._rng(0, "x")) == "Juanda"
    assert ec.apodo("Xiomara", None, ec._rng(0, "x")) is None


def test_ocr_cambia_digitos_por_letras(personas: pd.DataFrame) -> None:
    registros, condiciones = ec.capturar(personas, semilla=3, tasas=_solo("ocr"))
    for campo in ["numero_documento", "celular", "fecha_nacimiento"]:
        assert registros[campo].str.contains(r"[OlISBZ]").mean() > 0.5, campo
    assert condiciones["documento_alterado"].any()


def test_vias_y_formatos(personas: pd.DataFrame) -> None:
    registros, _ = ec.capturar(personas, semilla=3, tasas=_solo("via_variante"))
    primeras = registros["direccion"].str.split().str[0]
    assert not primeras.isin(["CL", "KR", "DG", "TV", "AV"]).any()
    registros, _ = ec.capturar(personas, semilla=3, tasas=_solo("formato_numero"))
    assert (~registros["direccion"].str.contains(" # ", regex=False)).mean() > 0.5


def test_mojibake_y_casada(personas: pd.DataFrame) -> None:
    registros, _ = ec.capturar(personas, semilla=3, tasas=_solo("mojibake"))
    assert registros["apellidos"].str.contains("Ã").any()
    registros, condiciones = ec.capturar(personas, semilla=3, tasas=_solo("apellido_casada"))
    assert registros["apellidos"].str.contains(" de ").any()
    assert condiciones["apellido_casada"].any()


def test_funciones_basicas() -> None:
    rng = ec._rng(0, "f")
    assert ec.invertir_fecha("1985-03-07") == "1985-07-03"
    assert ec.invertir_fecha("1985-03-25") == "1985-03-25"
    assert ec.mojibake("José") == "JosÃ©"
    assert ec._miles("1071194756", ".") == "1.071.194.756"
    assert ec.error_dominio("ana@gmail.com", rng).split("@")[1] in ec.DOMINIOS_ERRADOS["gmail.com"]
    assert ec.formato_fecha("1985-03-07", rng) != "1985-03-07"
