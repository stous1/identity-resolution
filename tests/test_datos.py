"""Pruebas de la carga de fake_1000, sin depender de internet."""

import pandas as pd
import pytest

from identidades import datos

CSV_FALSO = (
    b"unique_id,first_name,surname,dob,city,email,cluster\n"
    b"0,Robert,Alan,1971-06-24,,robert255@smith.net,0\n"
    b"1,Robert,Allen,1971-05-24,London,roberta25@smith.net,0\n"
    b"2,Grace,,1997-04-26,Hull,grace.kelly52@jones.com,1\n"
)


@pytest.fixture
def descarga_simulada(monkeypatch):
    """Reemplaza la descarga por una función que cuenta llamadas."""
    llamadas: list[str] = []

    def falsa(url: str, timeout: float = 60) -> bytes:
        llamadas.append(url)
        return CSV_FALSO

    monkeypatch.setattr(datos, "descargar", falsa)
    return llamadas


def test_descarga_y_guarda_cache(tmp_path, descarga_simulada):
    df = datos.cargar_fake_1000(tmp_path)

    assert descarga_simulada == [datos.URL_FAKE_1000]
    assert (tmp_path / "fake_1000.parquet").exists()
    assert list(df.columns) == datos.COLUMNAS_FAKE_1000
    assert len(df) == 3
    assert df["cluster"].tolist() == [0, 0, 1]


def test_segunda_carga_usa_cache(tmp_path, descarga_simulada):
    primera = datos.cargar_fake_1000(tmp_path)
    segunda = datos.cargar_fake_1000(tmp_path)

    assert len(descarga_simulada) == 1
    pd.testing.assert_frame_equal(primera, segunda)


def test_columnas_faltantes_lanzan_error(tmp_path, monkeypatch):
    monkeypatch.setattr(datos, "descargar", lambda url, timeout=60: b"unique_id,cluster\n0,0\n")

    with pytest.raises(ValueError, match="Faltan columnas"):
        datos.cargar_fake_1000(tmp_path)
    assert not (tmp_path / "fake_1000.parquet").exists()


def test_dividir_por_persona_no_parte_personas(registros_pequenos):
    grande = pd.concat(
        [
            registros_pequenos.assign(cluster=registros_pequenos["cluster"] + 3 * i)
            for i in range(10)
        ],
        ignore_index=True,
    )

    desarrollo, prueba = datos.dividir_por_persona(grande, frac_desarrollo=0.6, semilla=1)

    assert len(desarrollo) + len(prueba) == len(grande)
    assert set(desarrollo["cluster"]).isdisjoint(prueba["cluster"])
    assert desarrollo["cluster"].nunique() == 18  # 60 % de 30 personas
    assert prueba["cluster"].nunique() == 12


def test_dividir_por_persona_es_reproducible(registros_pequenos):
    a, _ = datos.dividir_por_persona(registros_pequenos, semilla=7)
    b, _ = datos.dividir_por_persona(registros_pequenos, semilla=7)

    pd.testing.assert_frame_equal(a, b)


def test_dividir_por_persona_valida_fraccion(registros_pequenos):
    with pytest.raises(ValueError, match="frac_desarrollo"):
        datos.dividir_por_persona(registros_pequenos, frac_desarrollo=1.0)
