"""Pruebas de las métricas con un caso pequeño calculado a mano.

Grupos verdaderos (fixture ``registros_pequenos``): {0, 1}, {2, 3}, {4, 5}.
Pares verdaderos: (0, 1), (2, 3), (4, 5).

Predicciones simuladas:
    (0, 1) 0.95  verdadero
    (2, 3) 0.60  verdadero
    (2, 1) 0.92  falso      (orden invertido a propósito)
    (3, 0) 0.30  falso      (orden invertido a propósito)
El par (4, 5) nunca se comparó: lo perdió el bloqueo.
"""

import pandas as pd
import pytest

from identidades import evaluacion


@pytest.fixture
def pred() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unique_id_l": [0, 2, 2, 3],
            "unique_id_r": [1, 3, 1, 0],
            "match_probability": [0.95, 0.60, 0.92, 0.30],
        }
    )


@pytest.fixture
def verdaderos(registros_pequenos) -> pd.DataFrame:
    return evaluacion.pares_verdaderos(registros_pequenos)


def test_pares_verdaderos(verdaderos):
    pares = set(map(tuple, verdaderos[["id_l", "id_r"]].to_numpy().tolist()))
    assert pares == {(0, 1), (2, 3), (4, 5)}


def test_metricas_pares_umbral_alto(pred, verdaderos):
    # Positivos a 0.9: (0,1) verdadero y (1,2) falso. FN: (2,3) y (4,5).
    m = evaluacion.metricas_pares(pred, verdaderos, umbral=0.9)

    assert (m["tp"], m["fp"], m["fn"]) == (1, 1, 2)
    assert m["precision"] == pytest.approx(1 / 2)
    assert m["recall"] == pytest.approx(1 / 3)
    assert m["f1"] == pytest.approx(0.4)


def test_metricas_pares_umbral_medio(pred, verdaderos):
    # Positivos a 0.5: (0,1), (2,3) verdaderos y (1,2) falso. FN: (4,5).
    m = evaluacion.metricas_pares(pred, verdaderos, umbral=0.5)

    assert (m["tp"], m["fp"], m["fn"]) == (2, 1, 1)
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["f1"] == pytest.approx(2 / 3)


def test_sin_positivos_no_divide_por_cero(pred, verdaderos):
    m = evaluacion.metricas_pares(pred, verdaderos, umbral=0.99)

    assert (m["tp"], m["fp"], m["fn"]) == (0, 0, 3)
    assert m["precision"] == 0.0
    assert m["f1"] == 0.0


def test_recall_bloqueo(pred, verdaderos):
    r = evaluacion.recall_bloqueo(pred, verdaderos)

    assert r["pares_comparados"] == 4
    assert r["pares_verdaderos"] == 3
    assert r["pares_verdaderos_comparados"] == 2
    assert r["recall_bloqueo"] == pytest.approx(2 / 3)
    assert r["recall_perdido_por_bloqueo"] == pytest.approx(1 / 3)


def test_curva_umbral(pred, verdaderos):
    curva = evaluacion.curva_umbral(pred, verdaderos, umbrales=[0.2, 0.5, 0.9, 0.99])

    assert curva["tp"].tolist() == [2, 2, 1, 0]
    assert curva["fp"].tolist() == [2, 1, 1, 0]
    assert curva["recall"].is_monotonic_decreasing
    assert evaluacion.umbral_max_f1(curva) == 0.5


def test_curva_umbral_por_defecto(pred, verdaderos):
    curva = evaluacion.curva_umbral(pred, verdaderos)

    assert len(curva) == 99
    assert curva["umbral"].between(0, 1).all()


def test_metricas_cluster_con_errores(registros_pequenos):
    # Clústeres predichos: {0, 1, 2}, {3}, {4}, {5}.
    # Pares inducidos: (0,1) verdadero, (0,2) y (1,2) falsos.
    clusters = pd.DataFrame({"unique_id": [0, 1, 2, 3, 4, 5], "cluster_id": [0, 0, 0, 3, 4, 5]})

    m = evaluacion.metricas_cluster(clusters, registros_pequenos)

    assert (m["tp"], m["fp"], m["fn"]) == (1, 2, 2)
    assert m["precision"] == pytest.approx(1 / 3)
    assert m["recall"] == pytest.approx(1 / 3)
    assert m["clusters_predichos"] == 4
    assert m["clusters_reales"] == 3
    assert m["clusters_exactos"] == 0


def test_metricas_cluster_perfectas(registros_pequenos):
    clusters = pd.DataFrame(
        {"unique_id": [0, 1, 2, 3, 4, 5], "cluster_id": ["a", "a", "b", "b", "c", "c"]}
    )

    m = evaluacion.metricas_cluster(clusters, registros_pequenos)

    assert (m["precision"], m["recall"], m["f1"]) == (1.0, 1.0, 1.0)
    assert m["pct_clusters_exactos"] == 1.0


@pytest.fixture
def curva_costos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "umbral": [0.2, 0.5, 0.8, 0.95],
            "fp": [5, 1, 0, 0],
            "fn": [0, 2, 6, 6],
        }
    )


def test_agregar_costo(curva_costos):
    con_costo = evaluacion.agregar_costo(curva_costos, costo_fp=10, costo_fn=1)

    assert con_costo["costo"].tolist() == [50, 12, 6, 6]
    assert "costo" not in curva_costos.columns


def test_umbral_min_costo_desempata_hacia_el_mas_conservador(curva_costos):
    # Costos 50, 12, 6, 6: empate entre 0.8 y 0.95 -> 0.95.
    assert evaluacion.umbral_min_costo(curva_costos) == 0.95


def test_umbral_min_costo_depende_de_los_costos(curva_costos):
    # Con FP y FN al mismo costo: 5, 3, 6, 6 -> 0.5.
    assert evaluacion.umbral_min_costo(curva_costos, costo_fp=1, costo_fn=1) == 0.5
    # Si el FN es mucho más caro: 5, 21, 60, 60 -> 0.2.
    assert evaluacion.umbral_min_costo(curva_costos, costo_fp=1, costo_fn=10) == 0.2


def test_contribuciones_por_persona(registros_pequenos):
    # Positivos: (0,1) acierto de la persona 0; (1,2) error entre personas 0 y 1.
    positivos = pd.DataFrame({"id_l": [0, 1], "id_r": [1, 2]})

    por_persona, cruzados = evaluacion.contribuciones_por_persona(positivos, registros_pequenos)

    assert por_persona[["persona", "tp", "fn"]].to_numpy().tolist() == [
        [0, 1, 0],
        [1, 0, 1],
        [2, 0, 1],
    ]
    assert cruzados.to_numpy().tolist() == [[0, 1, 1]]


def test_bootstrap_valor_observado_coincide_con_metricas(pred, verdaderos, registros_pequenos):
    marcadas = evaluacion.marcar_verdaderos(pred, verdaderos)
    positivos = marcadas[marcadas["match_probability"] >= 0.9]
    por_persona, cruzados = evaluacion.contribuciones_por_persona(positivos, registros_pequenos)

    ic = evaluacion.bootstrap_por_persona(por_persona, cruzados, n=200, semilla=1)
    directas = evaluacion.metricas_pares(pred, verdaderos, umbral=0.9)

    for metrica in ("precision", "recall", "f1"):
        assert ic[metrica]["valor"] == pytest.approx(directas[metrica])
        assert 0 <= ic[metrica]["ic_inf"] <= ic[metrica]["ic_sup"] <= 1


def test_bootstrap_sin_falsos_positivos_da_precision_uno(registros_pequenos):
    positivos = pd.DataFrame({"id_l": [0], "id_r": [1]})
    por_persona, cruzados = evaluacion.contribuciones_por_persona(positivos, registros_pequenos)

    ic = evaluacion.bootstrap_por_persona(por_persona, cruzados, n=200)

    assert cruzados.empty
    assert ic["precision"]["valor"] == 1.0
    assert ic["recall"]["valor"] == pytest.approx(1 / 3)


def test_bootstrap_clusters_y_exactos(registros_pequenos):
    # Clústeres: {0,1,2} mezcla; {3}; {4,5} correcto.
    clusters = pd.DataFrame({"unique_id": [0, 1, 2, 3, 4, 5], "cluster_id": [0, 0, 0, 3, 4, 4]})
    positivos = evaluacion.pares_inducidos(clusters)

    por_persona, cruzados = evaluacion.contribuciones_por_persona(
        positivos, registros_pequenos, clusters
    )
    ic = evaluacion.bootstrap_por_persona(por_persona, cruzados, n=200)
    directas = evaluacion.metricas_cluster(clusters, registros_pequenos)

    assert por_persona["exacto"].tolist() == [0, 0, 1]
    assert ic["pct_clusters_exactos"]["valor"] == pytest.approx(directas["pct_clusters_exactos"])
    for metrica in ("precision", "recall", "f1"):
        assert ic[metrica]["valor"] == pytest.approx(directas[metrica])
