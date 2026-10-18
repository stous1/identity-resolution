"""Pruebas de la selección de ejemplos para los tableros (sin generar HTML)."""

import pandas as pd

from identidades import evaluacion, tableros


def test_seleccionar_ejemplos_cascada(registros_pequenos):
    verdaderos = evaluacion.pares_verdaderos(registros_pequenos)
    pred = pd.DataFrame(
        {
            "unique_id_l": [0, 2, 1, 0],
            "unique_id_r": [1, 3, 2, 3],
            "match_probability": [0.95, 0.40, 0.92, float("nan")],
        }
    )

    ejemplos = tableros.seleccionar_ejemplos_cascada(pred, verdaderos, umbral=0.9, n_por_tipo=1)

    por_tipo = {e["tipo_ejemplo"]: (e["unique_id_l"], e["unique_id_r"]) for e in ejemplos}
    assert por_tipo == {"acierto": (0, 1), "falso_positivo": (1, 2), "falso_negativo": (2, 3)}
    assert "id_l" not in ejemplos[0] and "es_match" not in ejemplos[0]


def test_no_verdadero_bajo_el_umbral_es_casi_falso_positivo(registros_pequenos):
    verdaderos = evaluacion.pares_verdaderos(registros_pequenos)
    pred = pd.DataFrame(
        {"unique_id_l": [0, 1], "unique_id_r": [1, 2], "match_probability": [0.95, 0.40]}
    )

    ejemplos = tableros.seleccionar_ejemplos_cascada(pred, verdaderos, umbral=0.9, n_por_tipo=1)

    tipos = {(e["unique_id_l"], e["unique_id_r"]): e["tipo_ejemplo"] for e in ejemplos}
    assert tipos == {(0, 1): "acierto", (1, 2): "casi_falso_positivo"}


def test_seleccionar_clusters_prioriza_errores(registros_pequenos):
    # {0,1,2} mezcla dos personas; {3} es parte de una persona dividida; {4,5} correcto.
    clusters = pd.DataFrame({"unique_id": [0, 1, 2, 3, 4, 5], "cluster_id": [0, 0, 0, 3, 4, 4]})

    ids, nombres = tableros.seleccionar_clusters(clusters, registros_pequenos)

    assert ids[0] == 0 and "mezcla personas" in nombres[0]
    assert ids[-1] == 4 and "correcto" in nombres[-1]
    assert 3 in ids
    assert len(ids) == len(set(ids))
