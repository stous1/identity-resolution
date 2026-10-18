"""Pruebas de la copia de resultados a docs/resultados/."""

import pytest

from identidades.flujo import ARCHIVOS_PUBLICABLES, publicar_resultados


def test_publicar_copia_todo(tmp_path):
    origen, destino = tmp_path / "reports", tmp_path / "docs" / "resultados"
    origen.mkdir()
    for nombre in ARCHIVOS_PUBLICABLES + ["modelo.json"]:
        (origen / nombre).write_text(nombre, encoding="utf-8")

    copiados = publicar_resultados(origen, destino)

    assert sorted(p.name for p in copiados) == sorted(ARCHIVOS_PUBLICABLES)
    assert not (destino / "modelo.json").exists()
    assert (destino / "cascada.html").read_text(encoding="utf-8") == "cascada.html"


def test_publicar_falla_si_falta_algo(tmp_path):
    origen = tmp_path / "reports"
    origen.mkdir()
    (origen / "metricas.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Faltan salidas"):
        publicar_resultados(origen, tmp_path / "destino")
    assert not (tmp_path / "destino").exists()
