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
