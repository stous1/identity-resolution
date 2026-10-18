"""Pruebas del flujo del hito 2."""

import json

import pytest

from identidades import flujo_hito2


def test_resumir_equidad_identifica_el_grupo_que_falla_mas():
    equidad = {
        "con_tilde": {
            "clusters": {
                "diferencias": {
                    "con tilde - sin tilde": {
                        "recall": {
                            "valor": -0.05,
                            "ic_inf": -0.08,
                            "ic_sup": -0.02,
                            "significativa": True,
                        },
                        "precision": {
                            "valor": 0.01,
                            "ic_inf": -0.01,
                            "ic_sup": 0.03,
                            "significativa": False,
                        },
                    }
                }
            }
        }
    }

    hallazgos = flujo_hito2.resumir_equidad(equidad)

    assert hallazgos == [
        {
            "atributo": "con_tilde",
            "metrica": "recall",
            "diferencia": "con tilde - sin tilde",
            "valor": -0.05,
            "falla_mas_con": "con tilde",
        }
    ]


@pytest.mark.integracion
def test_hito2_completo_en_pequeno(tmp_path):
    metricas = flujo_hito2.ejecutar_hito2(
        tmp_path, n_personas=150, n_bootstrap=30, capturas=False, comparar=False
    )

    for nombre in flujo_hito2.ARCHIVOS_PUBLICABLES:
        if nombre in {"comparacion_bloqueos.csv", "cluster_studio.png", "comparison_viewer.png"}:
            continue  # se omiten con comparar=False y capturas=False
        assert (tmp_path / nombre).stat().st_size > 0, nombre
    assert json.loads((tmp_path / "metricas.json").read_text(encoding="utf-8")) == metricas

    assert set(metricas["variantes"]) == {"estandarizado", "crudo"}
    for variante in metricas["variantes"].values():
        assert variante["umbral"]["criterio"] == "min_costo_cluster"
        for nivel in ("pares", "clusters"):
            for ic in variante["prueba"]["intervalos"][nivel].values():
                assert 0 <= ic["ic_inf"] <= ic["ic_sup"] <= 1
    assert set(metricas["aporte_estandarizacion"]) >= {"clusters", "pares"}
    for variante in ("estandarizado", "crudo"):
        assert set(metricas["equidad"]["detalle"][variante]) == set(flujo_hito2.GRUPOS_EQUIDAD)
    particion = metricas["particion"]
    assert particion["desarrollo"]["personas"] + particion["prueba"]["personas"] == 150
