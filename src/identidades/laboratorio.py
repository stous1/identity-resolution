"""Datos del laboratorio interactivo (``docs/laboratorio.html``).

Dos experimentos que el navegador recalcula a partir de los pares puntuados por modelos
congelados, sin servidor (la lógica está en ``docs/laboratorio/motor.js``, y
``tests/test_laboratorio.py`` comprueba con Node que da lo mismo que este módulo):

1. **La auditoría en vivo.** El v1 congelado sobre la prueba ciega 1. La auditoría encontró
   que el recall se perdía por dos vetos aprendidos (municipio distinto y dirección
   parecida). Se exporta, para cada par, su peso y el aporte de esas dos comparaciones (en
   bits, con el ajuste por frecuencia, como en ``audit/a5_ablacion.py``). Quitar los vetos es
   restar ese aporte y volver a agrupar al umbral congelado.
2. **El umbral en tus manos.** El v3 congelado sobre la prueba ciega 3: con un umbral
   movible se ven los clústeres, las uniones erróneas por transitividad, el costo
   (10·FP + FN por clúster) y los puentes.

Los pares se guardan como índices de registro (0..N-1) y la persona verdadera de cada
registro, para que el navegador mida contra la verdad. Todo es sintético.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from identidades import evaluacion, flujo

COLUMNAS_VETO: tuple[str, ...] = ("domicilio", "municipio")
COSTO_FP: float = 10.0
COSTO_FN: float = 1.0
PESO_MIN_UMBRAL: float = 0.0  # el control de umbral va de 0 a 40 bits
PESO_PUENTE_DEBIL: float = 25.0  # política de puentes del hito 3 (umbral 0,9)


def peso_de(probabilidad: float) -> float:
    return math.log2(probabilidad / (1 - probabilidad))


def aportes(pred: pd.DataFrame, columnas: tuple[str, ...]) -> np.ndarray:
    """Suma del aporte (bits, con ajuste por frecuencia) de ``columnas`` a cada par."""
    total = np.zeros(len(pred))
    for k in columnas:
        bf = pred[f"bf_{k}"].astype(float).to_numpy()
        tf_col = f"bf_tf_adj_{k}"
        tf = pred[tf_col].astype(float).fillna(1.0).to_numpy() if tf_col in pred else 1.0
        total += np.log2(bf * tf)
    return total


# ---------- Cálculos que replica motor.js ----------


def componentes(n: int, aristas: np.ndarray) -> np.ndarray:
    """Etiqueta de componente de cada registro (unión-búsqueda; la raíz menor gana)."""
    padre = np.arange(n)

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for a, b in aristas:
        ra, rb = raiz(int(a)), raiz(int(b))
        if ra != rb:
            padre[max(ra, rb)] = min(ra, rb)
    return np.array([raiz(i) for i in range(n)])


def _pares(conteos: pd.Series) -> int:
    return int((conteos * (conteos - 1) // 2).sum())


def metricas(cluster: np.ndarray, persona: np.ndarray) -> dict[str, float]:
    """Métricas por clúster (pares inducidos), como ``evaluacion.metricas_cluster``."""
    tabla = pd.DataFrame({"c": cluster, "p": persona})
    predichos = _pares(tabla.groupby("c").size())
    verdaderos = _pares(tabla.groupby("p").size())
    tp = _pares(tabla.groupby(["c", "p"]).size())
    personas_por_cluster = tabla.groupby("c")["p"].nunique()
    clusters_por_persona = tabla.groupby("p")["c"].nunique()
    exacto = tabla.assign(
        solo=tabla["c"].map(personas_por_cluster).eq(1),
        unico=tabla["p"].map(clusters_por_persona).eq(1),
    )
    exactas = exacto.groupby("p").agg(solo=("solo", "all"), unico=("unico", "all"))
    exactas = exactas["solo"] & exactas["unico"]
    fp, fn = predichos - tp, verdaderos - tp
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / predichos if predichos else 1.0,
        "recall": tp / verdaderos if verdaderos else 1.0,
        "f1": 2 * tp / (predichos + verdaderos) if predichos + verdaderos else 1.0,
        "exactas": int(exactas.sum()),
        "personas": int(len(exactas)),
        "pct_exactas": float(exactas.mean()),
        "mezclados": int((personas_por_cluster > 1).sum()),
        "costo": COSTO_FP * fp + COSTO_FN * fn,
    }


def exactas_por_persona(cluster: np.ndarray, persona: np.ndarray) -> pd.Series:
    """1 si la persona quedó sola y completa en un clúster."""
    tabla = pd.DataFrame({"c": cluster, "p": persona})
    solo = tabla["c"].map(tabla.groupby("c")["p"].nunique()).eq(1)
    unico = tabla["p"].map(tabla.groupby("p")["c"].nunique()).eq(1)
    return tabla.assign(ok=solo & unico).groupby("p")["ok"].all()


def puentes(n: int, aristas: np.ndarray) -> np.ndarray:
    """Índices de las aristas que son puente (al quitarlas, su componente se parte).

    Tarjan iterativo; las aristas repetidas no son puente.
    """
    vecinos: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for k, (a, b) in enumerate(aristas):
        vecinos[int(a)].append((int(b), k))
        vecinos[int(b)].append((int(a), k))
    orden = [-1] * n
    bajo = [0] * n
    contador = 0
    es_puente = np.zeros(len(aristas), dtype=bool)
    for inicio in range(n):
        if orden[inicio] != -1 or not vecinos[inicio]:
            continue
        orden[inicio] = bajo[inicio] = contador
        contador += 1
        pila = [(inicio, -1, 0)]
        while pila:
            v, arista_padre, i = pila[-1]
            if i < len(vecinos[v]):
                pila[-1] = (v, arista_padre, i + 1)
                w, k = vecinos[v][i]
                if k == arista_padre:
                    continue
                if orden[w] == -1:
                    orden[w] = bajo[w] = contador
                    contador += 1
                    pila.append((w, k, 0))
                else:
                    bajo[v] = min(bajo[v], orden[w])
            else:
                pila.pop()
                if pila:
                    u = pila[-1][0]
                    bajo[u] = min(bajo[u], bajo[v])
                    if bajo[v] > orden[u]:
                        es_puente[arista_padre] = True
    return es_puente


def analizar_umbral(
    n: int, izq: np.ndarray, der: np.ndarray, w: np.ndarray, persona: np.ndarray, peso: float
) -> dict[str, Any]:
    """Todo lo que muestra el control de umbral para un peso mínimo ``peso``."""
    sobre = w >= peso
    aristas = np.column_stack([izq[sobre], der[sobre]])
    cluster = componentes(n, aristas)
    m = metricas(cluster, persona)
    directos_falsos = int((persona[izq[sobre]] != persona[der[sobre]]).sum())
    es_puente = puentes(n, aristas)
    pw = w[sobre][es_puente]
    cruza = persona[aristas[es_puente, 0]] != persona[aristas[es_puente, 1]]
    sostenidos = {int(cluster[a]) for a, c in zip(aristas[es_puente, 0], cruza, strict=True) if c}
    return {
        **m,
        "aristas": int(sobre.sum()),
        "falsos_directos": directos_falsos,
        "falsos_por_transitividad": m["fp"] - directos_falsos,
        "puentes": int(es_puente.sum()),
        "puentes_debiles": int((pw < PESO_PUENTE_DEBIL).sum()),
        "mezclas_sostenidas_por_puente": len(sostenidos),
    }


# ---------- Exportación ----------


def _indices(registros: pd.DataFrame, pred: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    posicion = pd.Series(np.arange(len(registros)), index=registros["unique_id"].to_numpy())
    return (
        posicion[pred["unique_id_l"].to_numpy()].to_numpy(),
        posicion[pred["unique_id_r"].to_numpy()].to_numpy(),
    )


def _personas(registros: pd.DataFrame) -> tuple[np.ndarray, list[int]]:
    codigos, unicos = pd.factorize(registros["cluster"])
    return codigos.astype(int), [int(u) for u in unicos]


def datos_auditoria(n_bootstrap: int = 1000) -> dict[str, Any]:
    """v1 congelado en la ciega 1: pares con su peso y el aporte de los dos vetos."""
    from identidades import errores_ciegos, flujo_validacion, modelo_co, sinteticos

    configuracion, umbral = flujo_validacion.cargar_congelado()
    _, personas = sinteticos.generar(2000, 2024)
    registros, condiciones = errores_ciegos.capturar(personas, semilla=2024)
    registros = registros.reset_index(drop=True)
    linker = flujo.aplicar_configuracion(configuracion, registros, modelo_co.esquema(True))
    ev = flujo.evaluar(linker, registros, umbral)
    pred = ev.pred
    w = pred["match_weight"].to_numpy(dtype=float)
    veto = aportes(pred, COLUMNAS_VETO)
    corte = peso_de(umbral)
    util = (w >= corte) | (w - veto >= corte)
    izq, der = _indices(registros, pred[util])
    persona, ids_persona = _personas(registros)
    atributos = {"apellido_casada": "apellido de casada", "con_apodo": "apodo"}
    tabla = condiciones.set_index("cluster")
    marcas = {a: [bool(tabla[a].get(p, False)) for p in ids_persona] for a in atributos}

    n = len(registros)
    referencia = {}
    for nombre, pesos in (("con_vetos", w[util]), ("sin_vetos", (w - veto)[util])):
        sobre = pesos >= corte
        cluster = componentes(n, np.column_stack([izq[sobre], der[sobre]]))
        m = metricas(cluster, persona)
        exactas = exactas_por_persona(cluster, persona)
        clusters_df = pd.DataFrame({"unique_id": registros["unique_id"], "cluster_id": cluster})
        contribuciones = evaluacion.contribuciones_por_persona(
            evaluacion.pares_inducidos(clusters_df), registros, clusters_df
        )
        equidad = {}
        for a, etiqueta in atributos.items():
            serie = pd.Series(
                [etiqueta if marcas[a][i] else f"sin {etiqueta}" for i in range(len(ids_persona))],
                index=ids_persona,
            )
            b = evaluacion.bootstrap_por_grupo(*contribuciones, serie, n=n_bootstrap, semilla=0)
            ((_, d),) = b["diferencias"].items()
            equidad[a] = {
                "exactas_con": float(exactas[np.array(marcas[a])].mean()),
                "exactas_sin": float(exactas[~np.array(marcas[a])].mean()),
                "diferencia": {
                    k: d["pct_clusters_exactos"][k] for k in ("valor", "ic_inf", "ic_sup")
                }
                | {"significativa": bool(d["pct_clusters_exactos"]["significativa"])},
            }
        referencia[nombre] = {**m, "equidad": equidad}
    return {
        "descripcion": "Modelo v1 congelado (hito2-congelado-r1) en la prueba ciega 1",
        "umbral": umbral,
        "peso_umbral": corte,
        "registros": n,
        "persona": persona.tolist(),
        "atributos": atributos,
        "marcas": {a: [i for i, v in enumerate(marcas[a]) if v] for a in atributos},
        "pares": [
            [int(a), int(b), round(float(x), 3), round(float(y), 3)]
            for a, b, x, y in zip(izq, der, w[util], veto[util], strict=True)
        ],
        "referencia": referencia,
    }


def datos_umbral() -> dict[str, Any]:
    """v3 congelado en la ciega 3: pares con peso >= 0 bits y la verdad por registro."""
    from identidades import flujo_hito6
    from identidades.modelo_co_v3 import ESQUEMA_V3

    configuracion, umbral, _, bandas = flujo_hito6.cargar_congelado_v3()
    registros, _, _ = flujo_hito6.registros_ciega_3()
    registros = registros.reset_index(drop=True)
    linker = flujo.aplicar_configuracion(configuracion, registros, ESQUEMA_V3)
    ev = flujo.evaluar(linker, registros, umbral)
    pred = ev.pred
    w = pred["match_weight"].to_numpy(dtype=float)
    util = w >= PESO_MIN_UMBRAL
    izq, der = _indices(registros, pred[util])
    persona, _ = _personas(registros)
    w = np.round(w[util], 3)
    n = len(registros)
    marcas = {
        "v3 congelado (0,999999)": peso_de(umbral),
        "umbral del v2 (0,9999)": peso_de(0.9999),
        "inicio de la zona gris": bandas["peso_desde_revisar"],
    }
    referencia = {
        f"{p:g}": analizar_umbral(n, izq, der, w, persona, p) for p in (0, 5, 10, 13.29, 19.93, 30)
    }
    return {
        "descripcion": "Modelo v3 congelado (hito6-congelado) en la prueba ciega 3",
        "registros": n,
        "persona": persona.tolist(),
        "costo": {"fp": COSTO_FP, "fn": COSTO_FN},
        "peso_puente_debil": PESO_PUENTE_DEBIL,
        "marcas": marcas,
        "pares": [[int(a), int(b), float(x)] for a, b, x in zip(izq, der, w, strict=True)],
        "referencia": referencia,
    }


def exportar(directorio: Path, n_bootstrap: int = 1000) -> dict[str, Any]:
    """Escribe ``auditoria.json`` y ``umbral.json`` en ``directorio``."""
    directorio.mkdir(parents=True, exist_ok=True)
    resumen = {}
    for nombre, datos in (
        ("auditoria", datos_auditoria(n_bootstrap)),
        ("umbral", datos_umbral()),
    ):
        ruta = directorio / f"{nombre}.json"
        ruta.write_text(
            json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
            newline="\n",
        )
        resumen[nombre] = {"pares": len(datos["pares"]), "kb": round(ruta.stat().st_size / 1024)}
    return resumen
