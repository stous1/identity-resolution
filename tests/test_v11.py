"""Pruebas del flujo de la v1.1: modelo v4 y grafo residencial congelados, universo."""

import json
import subprocess

import pandas as pd
import pytest

from identidades import diagnostico_v11, flujo_v11, modelo, rutas
from identidades.modelo_co_v4 import preparar


def _sin_cambios(tag: str, archivos: list[str]) -> bool:
    return (
        subprocess.run(["git", "diff", "--quiet", tag, "--", *archivos], cwd=rutas.RAIZ).returncode
        == 0
    )


def test_modelo_v4_no_cambio_desde_su_tag():
    # Si falla, el v4 cambió después de congelarlo: la prueba ciega 4 dejaría de medir el
    # modelo congelado. Crear un tag nuevo y repetir con otra prueba ciega.
    assert _sin_cambios(flujo_v11.TAG_CONGELADO, flujo_v11.ARCHIVOS_CONGELADOS)


def test_grafo_residencial_no_cambio_desde_su_tag():
    assert _sin_cambios(flujo_v11.TAG_GRAFO, flujo_v11.ARCHIVOS_GRAFO_CONGELADOS)


def test_v4_congelado_no_veta():
    configuracion, umbral, _, bandas = flujo_v11.cargar_congelado_v4()
    desarrollo = json.loads(
        (rutas.DOCS_RESULTADOS_V11 / "desarrollo.json").read_text(encoding="utf-8")
    )
    bits = desarrollo["piso_m"]["max_bits_en_contra"]
    assert modelo.pesos_extremos(configuracion)[0]["peso"] >= -bits - 1e-6
    assert 0.5 < umbral < 1
    assert bandas["peso_desde_revisar"] <= bandas["peso_desde_aceptar"]


def test_niveles_de_direccion_del_v4():
    configuracion = flujo_v11.cargar_congelado_v4()[0]
    niveles = {n["par"]: n for n in diagnostico_v11.niveles_direccion(configuracion, preparar)}
    assert niveles["mismo apartamento, otra escritura"]["nivel"].startswith("Misma direcci")
    assert niveles["mismo edificio, otro apartamento"]["nivel"] == "Mismo predio, otra unidad"
    assert niveles["casa: primer piso y piso 2"]["nivel"].endswith("otro con piso")
    # El mismo apartamento pesa más que dos vecinos del edificio (en el v3 era al revés).
    assert (
        niveles["mismo apartamento, otra escritura"]["bits"]
        > niveles["mismo edificio, otro apartamento"]["bits"]
    )


def test_clasificador_congelado_se_carga():
    p = flujo_v11.cargar_clasificador()
    assert p.max_convivencia >= 2 and 0 < p.min_familia <= 1


def _registros(filas: list[tuple]) -> pd.DataFrame:
    columnas = ["unique_id", "nombres", "apellidos", "validado", "fecha_actualizacion"]
    return pd.DataFrame(filas, columns=columnas)


def test_duenos_de_documentos():
    registros = _registros(
        [
            (1, "ESTHER", "MONTENEGRO", True, "2016-02-15"),
            (2, "ESTHER", "MONTENEGRO", True, "2014-01-12"),
            (3, "NATHALIA", "MENDEZ", False, "2024-10-22"),
        ]
    )
    clasificados = pd.DataFrame(
        {
            "tipo": ["documento"],
            "valor": ["1064372368"],
            "ids_registros": [[1, 2, 3]],
            "cliente_de": [{1: 10, 2: 10, 3: 20}],
        }
    )
    assert flujo_v11.duenos_de_documentos(clasificados, registros) == {"1064372368": 10}


def test_universo_distingue_victima_y_suplantador(tmp_path):
    registros = _registros(
        [
            (1, "ESTHER", "MONTENEGRO", True, "2016-02-15"),
            (2, "ESTHER", "MONTENEGRO", True, "2014-01-12"),
            (3, "NATHALIA", "MENDEZ", False, "2024-10-22"),
            (4, "ANA", "TORRES", True, "2020-01-01"),
            (5, "LUIS", "PEREZ", True, "2020-01-01"),
        ]
    )
    clusters = pd.DataFrame({"unique_id": [1, 2, 3, 4, 5], "cluster_id": [10, 10, 20, 30, 40]})
    pred = pd.DataFrame({"unique_id_l": [1], "unique_id_r": [2], "match_probability": [0.9999999]})
    clasificados = pd.DataFrame(
        {
            "tipo": ["documento", "direccion"],
            "valor": ["1064372368", "KR 7 # 40-62"],
            "clientes": [2, 2],
            "ids_registros": [[1, 2, 3], [4, 5]],
            "prediccion": ["sospechoso", "convivencia"],
            "tipo_predio": [None, "edificio"],
        }
    )
    conteo = flujo_v11.exportar_universo_v11(
        registros, clusters, pred, 0.999999, clasificados, tmp_path
    )
    puntos = {
        p["id"]: p["categoria"]
        for p in json.loads((tmp_path / "universo_puntos.json").read_text(encoding="utf-8"))
    }
    assert puntos["r1"] == puntos["r2"] == "registro_victima"
    assert puntos["r3"] == "registro_suplantador"
    assert puntos["r4"] == "registro"
    assert puntos["v:direccion:KR 7 # 40-62"] == "valor_convivencia"
    assert conteo["enlaces"] == 1 + 3 + 2


@pytest.mark.integracion
def test_escenario_aplicado_pequeno():
    modelos = flujo_v11.modelos_congelados()
    a = flujo_v11.escenario_aplicado(4999, modelos, n_personas=300)
    assert set(a["grupos"]) == {"anterior_v3", "residencial_v3", "residencial_v4"}
    assert a["union"]["v4"]["precision"] > 0.9


@pytest.mark.integracion
def test_ya_es_cliente_con_el_v4():
    """El vinculador de tiempo real acepta el esquema v4 (dirección en predio y unidad)."""
    from identidades import tiempo_real
    from identidades.escenario_residencial import generar_escenario_residencial

    configuracion, umbral, esquema = flujo_v11.modelos_congelados()["v4"]
    registros, _, _ = generar_escenario_residencial(300, 4999)
    base_registros, consultas, _ = tiempo_real.preparar_evaluacion(
        300, registros=registros, max_consultas=40
    )
    base = tiempo_real.construir_base(base_registros, configuracion, umbral, esquema)
    vinculador = tiempo_real.Vinculador(
        base, configuracion, umbral, bandas=flujo_v11.cargar_congelado_v4()[3], esquema=esquema
    )
    t = tiempo_real.resultados_por_consulta(vinculador, consultas)
    assert t["fp"].sum() == 0
    assert t["tp"].sum() >= 0.9 * t["existe"].sum()
