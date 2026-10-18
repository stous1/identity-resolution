"""Fugas de etiquetas: lo que no debe mirar la verdad no cambia al barajarla."""

import numpy as np
import pytest

from identidades import sinteticos
from identidades.modelo_co_v2 import ESQUEMA_V2

import _comun as c

pytestmark = pytest.mark.integracion


@pytest.fixture(scope="module")
def ciega_pequena():
    _, personas = sinteticos.generar(300, 99)
    registros, _ = c.errores_ciegos_2.capturar(personas, semilla=99)
    return registros


def _pesos(ev):
    p = ev.pares
    a = p[["unique_id_l", "unique_id_r"]].min(axis=1)
    b = p[["unique_id_l", "unique_id_r"]].max(axis=1)
    return p.assign(a=a, b=b).set_index(["a", "b"])["match_weight"].sort_index()


def test_modelo_congelado_no_mira_la_verdad(ciega_pequena):
    cfg, umbral = c.modelo_v2()
    rng = np.random.default_rng(0)
    real = c.aplicar_congelado(cfg, ciega_pequena, ESQUEMA_V2, umbral)
    barajada = ciega_pequena.assign(cluster=rng.permutation(ciega_pequena["cluster"].to_numpy()))
    otra = c.aplicar_congelado(cfg, barajada, ESQUEMA_V2, umbral)
    assert (_pesos(real) - _pesos(otra)).abs().max() == 0


def test_modelo_congelado_no_depende_del_orden_de_los_ids(ciega_pequena):
    cfg, umbral = c.modelo_v2()
    rng = np.random.default_rng(1)
    nuevos = rng.permutation(len(ciega_pequena)) + 10_000
    inverso = dict(zip(nuevos, ciega_pequena["unique_id"], strict=True))
    renumerada = ciega_pequena.assign(unique_id=nuevos).sample(frac=1, random_state=2)
    real = c.aplicar_congelado(cfg, ciega_pequena, ESQUEMA_V2, umbral)
    otra = c.aplicar_congelado(cfg, renumerada, ESQUEMA_V2, umbral)
    clusters = otra.clusters.assign(unique_id=otra.clusters["unique_id"].map(inverso))
    assert c.resumen(c.metricas_cluster(real.clusters, ciega_pequena)) == c.resumen(
        c.metricas_cluster(clusters, ciega_pequena)
    )


def test_entrenamiento_no_mira_la_verdad():
    from a1_fugas import _max_dif, entrenar

    registros, _ = sinteticos.generar(400, 5)
    rng = np.random.default_rng(3)
    real = entrenar(registros, ESQUEMA_V2)
    barajada = entrenar(registros.assign(cluster=rng.permutation(registros["cluster"])), ESQUEMA_V2)
    sin = entrenar(registros.drop(columns="cluster"), ESQUEMA_V2)
    assert _max_dif(real, barajada) < 1e-12
    assert _max_dif(real, sin) < 1e-12
