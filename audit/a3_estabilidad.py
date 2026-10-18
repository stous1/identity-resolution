"""Auditoría 3: estabilidad de las evaluaciones principales con 5 semillas.

Cada evaluación se repite completa (generación de datos y/o partición, desarrollo y
medición) con 5 semillas nuevas. Todos los conjuntos tienen como máximo 10 mil registros.
Se reporta media, desviación estándar, mínimo y máximo, y la cifra publicada al lado.

- ``hito1``: fake_1000 es fijo; cambia la partición desarrollo/prueba.
- ``hito2``: cambia la generación de personas y la partición; se repite el desarrollo.
- ``ciega1_v1``: modelo v1 congelado sobre nuevas muestras del generador ciego 1.
- ``ciega2_v2`` y ``ciega2_v1``: modelos congelados sobre nuevas muestras del ciego 2.
- ``v2_redesarrollado``: el procedimiento del hito 2b repetido (desarrollo = hito 2 + ciega 1
  con otra semilla) y medido en la ciega 2 publicada (semilla 7777).
- ``febrl``: cambia la partición de FEBRL3.
- ``hito3``: cambia el par de escenarios (desarrollo, prueba).
- ``tiempo_real``: cambia la población de la base y las consultas.

Uso: ``python audit/a3_estabilidad.py [evaluación ...]``.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from identidades import flujo, flujo_hito2b, flujo_hito3, modelo, tiempo_real
from identidades.modelo_co_v2 import ESQUEMA_V2
from identidades.modelo_febrl import ESQUEMA_FEBRL

import _comun as c

SEMILLAS: tuple[int, ...] = (11, 22, 33, 44, 55)
SALIDA = c.RESULTADOS / "a3_estabilidad.json"


def _medir(clusters: pd.DataFrame, registros: pd.DataFrame) -> dict[str, float]:
    return c.resumen(c.metricas_cluster(clusters, registros))


def _desarrollar_y_probar(dev, prueba, esquema) -> dict[str, Any]:
    d = flujo.desarrollar(dev, esquema=esquema)
    linker = flujo.aplicar_modelo(d.linker, prueba, esquema)
    cl = modelo.agrupar(linker, modelo.predecir(linker), d.umbral).as_pandas_dataframe()
    return {
        **_medir(cl, prueba),
        "umbral": d.umbral,
        "bloqueos": [" & ".join(b) for b in d.bloqueos[len(esquema.bloqueos_exactos) :]],
        "registros_prueba": len(prueba),
    }


def hito1(s: int) -> dict[str, Any]:
    dev, prueba = c.prueba_hito1(s)
    return _desarrollar_y_probar(dev, prueba, modelo.ESQUEMA_FAKE_1000)


def hito2(s: int) -> dict[str, Any]:
    registros, _ = c.sinteticos.generar(2000, s)
    dev, prueba = c.datos.dividir_por_persona(registros, 0.6, s)
    return _desarrollar_y_probar(dev, prueba, c.modelo_co.esquema(True))


def febrl(s: int) -> dict[str, Any]:
    dev, prueba = c.prueba_febrl(s)
    return _desarrollar_y_probar(dev, prueba, ESQUEMA_FEBRL)


def ciega1_v1(s: int) -> dict[str, Any]:
    reg = c.ciega_1(s)[0]
    cfg, u = c.modelo_v1()
    return {**_medir(c.aplicar_congelado(cfg, reg, c.modelo_co.esquema(True), u).clusters, reg),
            "registros": len(reg)}  # fmt: skip


def ciega2_v2(s: int) -> dict[str, Any]:
    reg = c.ciega_2(s)[0]
    cfg, u = c.modelo_v2()
    return {**_medir(c.aplicar_congelado(cfg, reg, ESQUEMA_V2, u).clusters, reg),
            "registros": len(reg)}  # fmt: skip


def ciega2_v1(s: int) -> dict[str, Any]:
    reg = c.ciega_2(s)[0]
    cfg, u = c.modelo_v1()
    return _medir(c.aplicar_congelado(cfg, reg, c.modelo_co.esquema(True), u).clusters, reg)


def v2_redesarrollado(s: int) -> dict[str, Any]:
    """Procedimiento del hito 2b con otras semillas; medido en la ciega 2 publicada."""
    dev = c.desarrollo_hito2(s)
    ciega = c.ciega_1(s)[0]
    ciega = ciega.assign(
        unique_id=ciega["unique_id"] + flujo_hito2b.DESPLAZAMIENTO_CIEGA_1,
        cluster=ciega["cluster"] + flujo_hito2b.DESPLAZAMIENTO_CIEGA_1,
    )
    dev = pd.concat([dev, ciega], ignore_index=True)
    d = flujo.desarrollar(dev, esquema=ESQUEMA_V2)
    cfg = d.linker.misc.save_model_to_json()
    reg = c.ciega_2()[0]
    cl = c.aplicar_congelado(cfg, reg, ESQUEMA_V2, d.umbral).clusters
    return {**_medir(cl, reg), "umbral": d.umbral, "registros_desarrollo": len(dev),
            "bloqueos": [" & ".join(b) for b in d.bloqueos[len(ESQUEMA_V2.bloqueos_exactos):]]}  # fmt: skip


def hito3(s: int) -> dict[str, Any]:
    """Flujo del hito 3 con otro par de escenarios (sin casos externos ni universo)."""
    originales = (flujo_hito3.SEMILLA_DESARROLLO, flujo_hito3.SEMILLA_PRUEBA,
                  flujo_hito3.casos_externos_puentes, flujo_hito3.exportar_universo)  # fmt: skip
    flujo_hito3.SEMILLA_DESARROLLO, flujo_hito3.SEMILLA_PRUEBA = 3000 + s, 3100 + s
    flujo_hito3.casos_externos_puentes = lambda *a, **k: {}
    flujo_hito3.exportar_universo = lambda *a, **k: None
    try:
        with tempfile.TemporaryDirectory(dir=c.CACHE) as tmp:
            m = flujo_hito3.ejecutar_hito3(Path(tmp), n_bootstrap=50)
    finally:
        (flujo_hito3.SEMILLA_DESARROLLO, flujo_hito3.SEMILLA_PRUEBA,
         flujo_hito3.casos_externos_puentes, flujo_hito3.exportar_universo) = originales  # fmt: skip
    oro = m["registro_oro"]
    techo = oro["prueba_techo_alcanzable"]
    aciertos = {k: v["valor"] for k, v in oro["prueba_con_reglas_elegidas"].items()}
    return {
        "reglas": oro["reglas_elegidas_en_desarrollo"],
        "oro_acierto": aciertos,
        "oro_brecha_al_techo": {k: techo[k] - v for k, v in aciertos.items()},
        "max_brecha_al_techo": max(techo[k] - v for k, v in aciertos.items()),
        "grafo_exactitud_prueba": m["grafo_compartido"]["prueba"]["exactitud"],
        "grafo_grupos_prueba": m["grafo_compartido"]["prueba"]["grupos"],
        "grafo_max_clientes": m["grafo_compartido"]["parametros_elegidos_en_desarrollo"][
            "max_clientes"
        ],
        "union_precision": m["calidad_union"]["prueba"]["precision"],
        "union_recall": m["calidad_union"]["prueba"]["recall"],
        "puentes": {
            u: {
                k: m["puentes"][u]["prueba"][k]
                for k in ("max_peso", "mezclados_antes", "mezclados_despues", "recall_perdido")
            }
            for u in ("0.9", "0.99", "0.9999")
        },  # fmt: skip
    }


def tiempo_real_(s: int) -> dict[str, Any]:
    cfg, umbral = flujo_hito2b.cargar_congelado_v2()
    registros_base, consultas, _ = tiempo_real.preparar_evaluacion(3000, 5000 + s)
    base = tiempo_real.construir_base(registros_base, cfg, umbral)
    v = tiempo_real.Vinculador(
        base, cfg, umbral, relleno=tiempo_real.telefonos_de_relleno(registros_base)
    )
    r = tiempo_real.evaluar(v, consultas, n_bootstrap=50)
    return {
        "precision": r["precision"]["valor"],
        "recall": r["recall"]["valor"],
        "cliente_equivocado": r["cliente_equivocado"],
        "nuevas_como_cliente": r["decisiones"]["nuevas"].get("cliente", 0),
        "nuevas_a_revision": r["decisiones"]["nuevas"].get("revisar", 0),
        "clientes_base": len(base),
        "latencia_mediana_ms": r["latencia_ms"]["mediana"],
    }


EVALUACIONES = {
    "hito1": hito1,
    "hito2": hito2,
    "ciega1_v1": ciega1_v1,
    "ciega2_v2": ciega2_v2,
    "ciega2_v1": ciega2_v1,
    "v2_redesarrollado": v2_redesarrollado,
    "febrl": febrl,
    "hito3": hito3,
    "tiempo_real": tiempo_real_,
}


def resumir(corridas: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Media, desviación, mínimo y máximo de cada métrica numérica (también anidadas)."""
    planas: dict[str, list[float]] = {}

    def aplanar(d: dict, prefijo: str = "") -> None:
        for k, v in d.items():
            if isinstance(v, dict):
                aplanar(v, f"{prefijo}{k}.")
            elif isinstance(v, int | float) and not isinstance(v, bool):
                planas.setdefault(f"{prefijo}{k}", []).append(float(v))

    for r in corridas.values():
        aplanar(r)
    return {
        k: {"media": float(np.mean(v)), "de": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0,
            "min": float(np.min(v)), "max": float(np.max(v)), "n": len(v)}
        for k, v in planas.items()
    }  # fmt: skip


def main() -> None:
    pedidas = sys.argv[1:] or list(EVALUACIONES)
    previo = c.json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    c.CACHE.mkdir(parents=True, exist_ok=True)
    for nombre in pedidas:
        corridas = {}
        for s in SEMILLAS:
            inicio = time.perf_counter()
            corridas[s] = EVALUACIONES[nombre](s)
            print(f"[{nombre}] semilla {s}: {time.perf_counter() - inicio:.0f} s ->",
                  {k: v for k, v in corridas[s].items() if not isinstance(v, dict | list)},
                  flush=True)  # fmt: skip
        previo[nombre] = {"semillas": list(SEMILLAS), "corridas": corridas,
                          "resumen": resumir(corridas)}  # fmt: skip
        c.guardar_json(previo, SALIDA)


if __name__ == "__main__":
    main()
