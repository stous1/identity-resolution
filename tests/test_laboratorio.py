"""El laboratorio (docs/laboratorio.html) calcula lo mismo que Python y sus cifras cuadran."""

import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from identidades import evaluacion, laboratorio, rutas

MOTOR = rutas.DOCS / "laboratorio" / "motor.js"
AUDITORIA = rutas.DOCS_RESULTADOS_LABORATORIO / "auditoria.json"
UMBRAL = rutas.DOCS_RESULTADOS_LABORATORIO / "umbral.json"


def _leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


def _node(codigo: str) -> object:
    if shutil.which("node") is None:
        pytest.skip("sin Node.js")
    salida = subprocess.run(
        ["node", "-e", codigo], capture_output=True, text=True, encoding="utf-8", check=True
    )
    return json.loads(salida.stdout)


def _requerir(ruta) -> str:
    return f"require({json.dumps(str(ruta))})"


def test_auditoria_en_vivo_igual_que_python():
    datos = _leer(AUDITORIA)
    js = _node(
        f"const L={_requerir(MOTOR)};const d={_requerir(AUDITORIA)};"
        "console.log(JSON.stringify([L.auditoria(d,false),L.auditoria(d,true)]));"
    )
    for r, clave in zip(js, ("con_vetos", "sin_vetos"), strict=True):
        ref = datos["referencia"][clave]
        for m in ("tp", "fp", "fn", "exactas", "mezclados"):
            assert r[m] == ref[m], (clave, m)
        for a, e in ref["equidad"].items():
            assert r["equidad"][a]["exactas_con"] == pytest.approx(e["exactas_con"], abs=1e-12)
            assert r["equidad"][a]["exactas_sin"] == pytest.approx(e["exactas_sin"], abs=1e-12)


def test_cifras_de_la_auditoria():
    """Quitar los vetos sube el recall de la ciega 1 a cerca de 0,94 (auditoría: 0,943) y
    deja la brecha del apellido de casada sin significancia."""
    ref = _leer(AUDITORIA)["referencia"]
    assert ref["con_vetos"]["recall"] < 0.65 < 0.93 < ref["sin_vetos"]["recall"]
    assert ref["con_vetos"]["equidad"]["apellido_casada"]["diferencia"]["significativa"]
    assert not ref["sin_vetos"]["equidad"]["apellido_casada"]["diferencia"]["significativa"]


def test_umbral_igual_que_python():
    datos = _leer(UMBRAL)
    pesos = [float(p) for p in datos["referencia"]]
    js = _node(
        f"const L={_requerir(MOTOR)};const d={_requerir(UMBRAL)};"
        f"console.log(JSON.stringify({json.dumps(pesos)}.map(p=>L.analizarUmbral(d,p))));"
    )
    for p, r in zip(datos["referencia"], js, strict=True):
        ref = datos["referencia"][p]
        for m in (
            "tp", "fp", "fn", "costo", "mezclados", "exactas", "aristas", "falsos_directos",
            "falsos_por_transitividad", "puentes", "puentes_debiles",
            "mezclas_sostenidas_por_puente",
        ):  # fmt: skip
            assert r[m] == ref[m], (p, m)


def test_metricas_iguales_a_las_del_proyecto():
    """``laboratorio.metricas`` da lo mismo que ``evaluacion.metricas_cluster``."""
    datos = _leer(UMBRAL)
    n, persona = datos["registros"], np.array(datos["persona"])
    pares = np.array(datos["pares"])
    for peso in (5.0, 19.93):
        sobre = pares[:, 2] >= peso
        cluster = laboratorio.componentes(n, pares[sobre][:, :2].astype(int))
        propia = laboratorio.metricas(cluster, persona)
        proyecto = evaluacion.metricas_cluster(
            pd.DataFrame({"unique_id": range(n), "cluster_id": cluster}),
            pd.DataFrame({"unique_id": range(n), "cluster": persona}),
        )
        for m in ("tp", "fp", "fn"):
            assert propia[m] == proyecto[m]
        assert propia["pct_exactas"] == pytest.approx(proyecto["pct_clusters_exactos"])


def test_puentes_por_fuerza_bruta():
    """Una arista es puente si al quitarla aumenta el número de componentes."""
    rng = np.random.default_rng(3)
    n = 30
    aristas = np.unique(np.sort(rng.integers(0, n, size=(40, 2)), axis=1), axis=0)
    aristas = aristas[aristas[:, 0] != aristas[:, 1]]
    esperado = []
    base = len(set(laboratorio.componentes(n, aristas)))
    for k in range(len(aristas)):
        resto = np.delete(aristas, k, axis=0)
        esperado.append(len(set(laboratorio.componentes(n, resto))) > base)
    assert laboratorio.puentes(n, aristas).tolist() == esperado
    js = _node(
        f"const L={_requerir(MOTOR)};"
        f"console.log(JSON.stringify(Array.from(L.puentes({n},{json.dumps(aristas.tolist())}))));"
    )
    assert [bool(x) for x in js] == esperado


def test_jsons_livianos():
    for ruta in (AUDITORIA, UMBRAL):
        assert ruta.stat().st_size < 400_000
