"""Pruebas del hito 6: historia en el generador, piso de las m, línea base y calibración."""

import json
import math
import subprocess

import numpy as np
import pandas as pd
import pytest

from identidades import calibracion, flujo_hito6, linea_base, modelo, rutas, sinteticos, tiempo_real


@pytest.fixture(scope="module")
def con_historia():
    registros, personas = sinteticos.generar(400, 11)
    nuevos, personas_h = sinteticos.agregar_historia(registros, personas, 11)
    return registros, personas, nuevos, personas_h


# ---------- Generador ----------


def test_historia_no_cambia_generar():
    # agregar_historia usa su propio sorteo: generar sigue dando exactamente lo mismo.
    a, _ = sinteticos.generar(200, 5)
    sinteticos.agregar_historia(*sinteticos.generar(200, 5), 5)
    b, _ = sinteticos.generar(200, 5)
    pd.testing.assert_frame_equal(a, b)


def test_historia_solo_toca_direccion_ciudad_y_apellidos(con_historia):
    registros, _, nuevos, _ = con_historia
    cambiadas = [
        c for c in registros.columns if not registros[c].fillna("").equals(nuevos[c].fillna(""))
    ]
    assert set(cambiadas) <= {"direccion", "ciudad", "departamento", "apellidos"}
    assert {"direccion", "apellidos"} <= set(cambiadas)


def test_mudanzas_y_casadas_se_manifiestan(con_historia):
    _, _, nuevos, personas = con_historia
    for cluster in personas.loc[personas["mudanza_otra_ciudad"], "cluster"].head(5):
        ciudades = nuevos.loc[nuevos["cluster"] == cluster, "ciudad"].str.upper()
        assert ciudades.nunique() >= 2
    casadas = personas.loc[personas["apellido_casada"], "cluster"]
    assert len(casadas) > 0
    assert personas.loc[personas["apellido_casada"], "mujer"].all()
    for cluster in casadas.head(5):
        apellidos = nuevos.loc[nuevos["cluster"] == cluster, "apellidos"].dropna()
        assert apellidos.str.contains(r"\bde\b", case=False).any()


def test_historia_reproducible():
    r, p = sinteticos.generar(150, 3)
    a, _ = sinteticos.agregar_historia(r, p, 3)
    b, _ = sinteticos.agregar_historia(r, p, 3)
    pd.testing.assert_frame_equal(a, b)


# ---------- Piso de las m ----------


def _configuracion(m: list[float], u: list[float]) -> dict:
    niveles = [{"sql_condition": "nulo", "is_null_level": True}] + [
        {"sql_condition": f"n{i}", "label_for_charts": f"n{i}", "m_probability": mi,
         "u_probability": ui}
        for i, (mi, ui) in enumerate(zip(m, u, strict=True))
    ]  # fmt: skip
    return {"comparisons": [{"output_column_name": "campo", "comparison_levels": niveles}]}


def test_piso_limita_los_bits_en_contra_y_mantiene_la_suma():
    original = _configuracion([0.9, 0.1 - 1e-20, 1e-20], [0.01, 0.09, 0.9])
    con_piso = modelo.aplicar_piso_m(original, 10)

    niveles = con_piso["comparisons"][0]["comparison_levels"][1:]
    pesos = [math.log2(n["m_probability"] / n["u_probability"]) for n in niveles]
    assert min(pesos) == pytest.approx(-10)
    assert sum(n["m_probability"] for n in niveles) == pytest.approx(1)
    assert pesos[0] > 6  # el acuerdo sigue sumando evidencia
    # No modifica la configuración original.
    assert original["comparisons"][0]["comparison_levels"][3]["m_probability"] == 1e-20


def test_piso_no_toca_comparaciones_sin_vetos():
    original = _configuracion([0.8, 0.2], [0.05, 0.95])
    assert modelo.aplicar_piso_m(original, 10) == original


def test_pesos_extremos_ordena_del_mas_negativo():
    filas = modelo.pesos_extremos(_configuracion([0.9, 0.1], [0.1, 0.9]))
    assert filas[0]["comparacion"] == "campo"
    assert filas[0]["peso"] == pytest.approx(math.log2(0.1 / 0.9))


# ---------- Línea base ----------


@pytest.fixture
def preparado():
    return pd.DataFrame(
        {
            "unique_id": [1, 2, 3, 4, 5],
            "documento": ["10", "10", None, "99", "98"],
            "nombre_completo": ["ANA", "ANA", "ANA", "LUIS", "LUIS"],
            "fecha_nacimiento": ["2000-01-01", "2000-01-01", "2000-01-01", "1990-01-01", None],
        }
    )


def test_reglas_y_union_transitiva(preparado):
    pares = linea_base.pares_regla(preparado)
    assert set(map(tuple, pares[["id_l", "id_r"]].to_numpy())) == {(1, 2), (1, 3), (2, 3)}
    solo_doc = linea_base.pares_regla(preparado, con_nombre_fecha=False)
    assert len(solo_doc) == 1

    clusters = linea_base.agrupar(
        preparado["unique_id"], pd.DataFrame({"id_l": [1, 3], "id_r": [2, 2]})
    )
    assert clusters.groupby("cluster_id").size().sort_values().tolist() == [1, 1, 3]


def test_hibrido_estricto_no_une_documentos_distintos(preparado):
    pred = pd.DataFrame({"unique_id_l": [4], "unique_id_r": [5], "match_probability": [0.99999]})
    clusters = linea_base.clusters_por_metodo(preparado, pred, 0.9)
    juntos = lambda c: c.set_index("unique_id")["cluster_id"]  # noqa: E731
    assert juntos(clusters["hibrido"])[4] == juntos(clusters["hibrido"])[5]
    assert juntos(clusters["hibrido_estricto"])[4] != juntos(clusters["hibrido_estricto"])[5]


def test_segmentos_por_documento(preparado):
    registros = preparado.assign(cluster=[1, 1, 1, 2, 2])
    seg = linea_base.segmentos(preparado, registros)
    assert seg[1] == linea_base.SEGMENTOS["sin_documento"]
    assert seg[2] == linea_base.SEGMENTOS["documento_alterado"]


# ---------- Calibración ----------


def test_isotonica_es_creciente_y_recupera_frecuencias():
    rng = np.random.default_rng(0)
    pesos = rng.uniform(-20, 30, 5000)
    verdad = rng.random(5000) < 1 / (1 + 2.0 ** -(pesos / 2))
    cal = calibracion.ajustar(pesos, verdad)

    assert np.all(np.diff(cal.probabilidad) > 0)
    assert np.all(np.diff(cal.desde) > 0)
    assert cal.aplicar(np.array([-20.0]))[0] < 0.05
    assert cal.aplicar(np.array([30.0]))[0] > 0.95
    b = calibracion.bandas(cal)
    assert b["peso_desde_revisar"] < b["peso_desde_aceptar"]
    assert list(calibracion.banda([-50, b["peso_desde_revisar"], 100], b)) == [
        "rechazar",
        "revisar",
        "aceptar",
    ]


def test_wilson_contiene_la_proporcion():
    inf, sup = calibracion.wilson(30, 100)
    assert inf < 0.3 < sup
    assert calibracion.wilson(0, 0) == (0.0, 1.0)


# ---------- Tiempo real ----------


def test_precision_por_prevalencia_baja_con_menos_clientes():
    t = pd.DataFrame(
        {
            "existe": [True] * 100 + [False] * 100,
            "tp": [True] * 99 + [False] + [False] * 100,
            "fp": [False] * 100 + [True] + [False] * 99,
        }
    )
    r = tiempo_real.precision_por_prevalencia(t, (0.01, 0.5), n_bootstrap=50)
    assert r["precision"]["0.5"]["valor"] == pytest.approx(0.99 / (0.99 + 0.01))
    esperado = 0.01 * 0.99 / (0.01 * 0.99 + 0.99 * 0.01)
    assert r["precision"]["0.01"]["valor"] == pytest.approx(esperado)


# ---------- Modelo congelado ----------


def test_modelo_v3_no_cambio_desde_su_tag():
    # Si falla, el modelo v3 cambió después de congelarlo: la prueba ciega 3 dejaría de
    # medir el modelo congelado. Crear un tag nuevo y repetir con otra prueba ciega.
    cambios = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            flujo_hito6.TAG_CONGELADO,
            "--",
            *flujo_hito6.ARCHIVOS_CONGELADOS,
        ],
        cwd=rutas.RAIZ,
    ).returncode
    assert cambios == 0


def test_v3_congelado_no_veta():
    configuracion, umbral, cal, bandas = flujo_hito6.cargar_congelado_v3()
    desarrollo = json.loads(
        (rutas.DOCS_RESULTADOS_HITO6 / "desarrollo.json").read_text(encoding="utf-8")
    )
    bits = desarrollo["piso_m"]["max_bits_en_contra"]
    assert modelo.pesos_extremos(configuracion)[0]["peso"] >= -bits - 1e-6
    assert 0.5 < umbral < 1
    assert bandas["peso_desde_revisar"] <= bandas["peso_desde_aceptar"]
