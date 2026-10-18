"""Pruebas de la medición de escala y del flujo del hito 5."""

import json
import time

import pandas as pd
import pytest

from identidades import escala, flujo_hito5, sinteticos


def test_medir_registra_tiempo_y_memoria():
    mediciones: list[escala.Medicion] = []
    with escala.medir("prueba", mediciones) as m:
        time.sleep(0.12)
        m.detalle["x"] = 1

    assert len(mediciones) == 1
    assert mediciones[0].segundos >= 0.1
    assert mediciones[0].memoria_pico_gb > 0
    assert mediciones[0].detalle == {"x": 1}


def test_generar_usa_cache(tmp_path):
    primero = escala.generar(500, semilla=3, directorio=tmp_path)
    segundo = escala.generar(500, semilla=99, directorio=tmp_path)  # lee la caché

    assert (tmp_path / "registros_500.parquet").exists()
    pd.testing.assert_frame_equal(primero, segundo)


def test_preparar_anula_correos_de_relleno():
    registros, _ = sinteticos.generar(60, 4)
    registros = registros.copy()
    registros.loc[registros.index[:10], "correo"] = "sincorreo@gmail.com"

    preparado = escala.preparar(registros)

    assert preparado["email"].iloc[:10].isna().all()


@pytest.mark.integracion
def test_correr_y_exportar_universo(tmp_path, monkeypatch):
    registros, _ = sinteticos.generar(1200, 8)
    monkeypatch.setattr(escala, "generar", lambda n: registros)

    mediciones, artefactos = escala.correr(len(registros))
    resumen = escala.exportar_universo(artefactos, tmp_path, n_registros=800)

    assert [m.etapa for m in mediciones] == [
        "preparacion",
        "entrenamiento",
        "prediccion",
        "agrupacion",
    ]
    assert artefactos["calidad"]["precision"] > 0.9
    puntos = pd.read_parquet(tmp_path / "universo_grande_puntos.parquet")
    enlaces = pd.read_parquet(tmp_path / "universo_grande_enlaces.parquet")
    assert resumen["puntos"] == len(puntos)
    assert (puntos["categoria"] != "valor_relleno").sum() <= 800
    assert set(enlaces["origen"]) | set(enlaces["destino"]) <= set(puntos["id"])


def test_tabla_escala_ordena_por_tamano_y_etapa(tmp_path):
    for n, factor in ((1000, 1), (10000, 10)):
        datos = {
            "mediciones": [
                {
                    "etapa": e,
                    "segundos": factor * 1.0,
                    "memoria_pico_gb": factor * 0.1,
                    "detalle": {"registros": n},
                }
                for e in ("preparacion", "entrenamiento", "prediccion", "agrupacion")
            ],
            "calidad": {"precision": 0.99, "recall": 0.98},
        }
        (tmp_path / f"escala_{n}.json").write_text(json.dumps(datos), encoding="utf-8")

    tabla = flujo_hito5.tabla_escala(tmp_path)

    assert list(tabla["registros"]) == [1000] * 4 + [10000] * 4
    assert list(tabla["etapa"][:4]) == list(flujo_hito5.ETAPAS.values())
    assert tabla["segundos"].iloc[-1] == 10.0
