"""Pruebas de las utilidades de auditoría (agrupación y reglas determinísticas)."""

import numpy as np
import pandas as pd

import _comun as c


def test_componentes_une_de_forma_transitiva():
    cl = c.componentes(np.array([10, 11, 12, 13]), np.array([10, 11]), np.array([11, 12]))
    asignado = dict(zip(cl["unique_id"], cl["cluster_id"], strict=True))
    assert asignado[10] == asignado[11] == asignado[12] == 10
    assert asignado[13] == 13


def test_reglas_ignoran_nulos_y_combinan_con_o():
    df = pd.DataFrame(
        {
            "unique_id": [0, 1, 2, 3, 4],
            "documento": ["1", "1", None, None, "9"],
            "nombre": ["A", "B", "C", "C", "A"],
        }
    )
    solo_doc = c.clusters_por_reglas(df, [["documento"]])
    assert solo_doc.groupby("cluster_id").size().max() == 2  # los nulos no se unen
    doc_o_nombre = c.clusters_por_reglas(df, [["documento"], ["nombre"]])
    grupos = doc_o_nombre.groupby("cluster_id")["unique_id"].apply(set).tolist()
    assert {0, 1, 4} in grupos and {2, 3} in grupos  # 0-1 por documento, 0-4 por nombre


def test_clusters_de_pares_respeta_el_umbral():
    pares = pd.DataFrame(
        {"unique_id_l": [0, 1], "unique_id_r": [1, 2], "match_probability": [0.99, 0.5]}
    )
    cl = c.clusters_de_pares(np.array([0, 1, 2]), pares, 0.9)
    assert cl.groupby("cluster_id").size().sort_values().tolist() == [1, 2]
