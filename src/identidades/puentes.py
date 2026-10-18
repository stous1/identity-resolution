"""Puentes: uniones sostenidas por un solo enlace débil (como el caso 109-844 del hito 1).

Una arista es **puente** (``is_bridge``, de las métricas de grafo de Splink) si al quitarla
el clúster se parte en dos. En un clúster de dos registros la única arista siempre es
puente, así que un puente no es sospechoso por sí solo. Las políticas miran además:

- ``max_peso``: el peso de coincidencia del puente (débil si es menor);
- ``min_lado``: cuántos registros quedan del lado más chico al cortarlo. Un puente débil
  entre dos grupos de dos o más registros es la forma típica de una unión errónea por
  transitividad.

Dos usos: **partir** automáticamente esos clústeres, o **mandarlos a revisión** (la
entrada del agente del hito 4). Se mide cuántas uniones erróneas se evitan y cuánto recall
se pierde.
"""

from __future__ import annotations

import pandas as pd
from splink import Linker
from splink.internals.splink_dataframe import SplinkDataFrame

from identidades import evaluacion


def aristas_con_puentes(
    linker: Linker, df_pred: SplinkDataFrame, df_clusters: SplinkDataFrame, umbral: float
) -> pd.DataFrame:
    """Aristas de los clústeres (pares sobre el umbral) con ``is_bridge``, peso y lado menor."""
    metricas = linker.clustering.compute_graph_metrics(
        df_pred, df_clusters, threshold_match_probability=umbral
    )
    aristas = metricas.edges.as_pandas_dataframe().rename(
        columns={"composite_unique_id_l": "id_l", "composite_unique_id_r": "id_r"}
    )
    pred = df_pred.as_pandas_dataframe()[
        ["unique_id_l", "unique_id_r", "match_weight", "match_probability"]
    ].rename(columns={"unique_id_l": "id_l", "unique_id_r": "id_r"})
    aristas = aristas.merge(pred, on=["id_l", "id_r"], how="left")
    cluster_de = df_clusters.as_pandas_dataframe().set_index("unique_id")["cluster_id"]
    aristas["cluster_id"] = aristas["id_l"].map(cluster_de)
    aristas["lado_menor"] = _lado_menor(aristas)
    return aristas


def _componentes(nodos: list, aristas: list[tuple]) -> dict:
    """Componente conectada de cada nodo (unión-búsqueda)."""
    padre = {n: n for n in nodos}

    def raiz(n):
        while padre[n] != n:
            padre[n] = padre[padre[n]]
            n = padre[n]
        return n

    for a, b in aristas:
        padre[raiz(a)] = raiz(b)
    return {n: raiz(n) for n in nodos}


def _lado_menor(aristas: pd.DataFrame) -> pd.Series:
    """Para cada puente, el tamaño del lado más chico al quitarlo (0 si no es puente)."""
    resultado = pd.Series(0, index=aristas.index)
    for _, g in aristas.groupby("cluster_id"):
        pares = list(zip(g["id_l"], g["id_r"], strict=True))
        nodos = sorted({n for par in pares for n in par})
        for idx, fila in g[g["is_bridge"]].iterrows():
            resto = [p for p in pares if p != (fila["id_l"], fila["id_r"])]
            comp = _componentes(nodos, resto)
            lado = sum(1 for n in nodos if comp[n] == comp[fila["id_l"]])
            resultado[idx] = min(lado, len(nodos) - lado)
    return resultado


def puentes_debiles(aristas: pd.DataFrame, max_peso: float, min_lado: int) -> pd.DataFrame:
    return aristas[
        aristas["is_bridge"]
        & (aristas["match_weight"] < max_peso)
        & (aristas["lado_menor"] >= min_lado)
    ]


def partir(
    clusters: pd.DataFrame, aristas: pd.DataFrame, max_peso: float, min_lado: int
) -> pd.DataFrame:
    """Nuevos clústeres tras quitar los puentes débiles (componentes conectadas)."""
    cortar = set(map(tuple, puentes_debiles(aristas, max_peso, min_lado)[["id_l", "id_r"]].values))
    quedan = [
        (a, b)
        for a, b in zip(aristas["id_l"], aristas["id_r"], strict=True)
        if (a, b) not in cortar
    ]
    comp = _componentes(list(clusters["unique_id"]), quedan)
    return pd.DataFrame(
        {"unique_id": clusters["unique_id"], "cluster_id": clusters["unique_id"].map(comp)}
    )


def mezclados(clusters: pd.DataFrame, df: pd.DataFrame) -> set:
    """Clústeres que juntan registros de más de una persona verdadera."""
    asignacion = clusters[["unique_id", "cluster_id"]].merge(df[["unique_id", "cluster"]])
    personas = asignacion.groupby("cluster_id")["cluster"].nunique()
    return set(personas[personas > 1].index)


def evaluar_politica(
    clusters: pd.DataFrame,
    aristas: pd.DataFrame,
    df: pd.DataFrame,
    max_peso: float,
    min_lado: int,
    costo_fp: float = 10.0,
    costo_fn: float = 1.0,
) -> dict:
    """Efecto de partir y de mandar a revisión los clústeres con puentes débiles."""
    antes = evaluacion.metricas_cluster(clusters, df)
    nuevos = partir(clusters, aristas, max_peso, min_lado)
    despues = evaluacion.metricas_cluster(nuevos, df)
    marcados = set(puentes_debiles(aristas, max_peso, min_lado)["cluster_id"])
    mezcla = mezclados(clusters, df)
    return {
        "max_peso": max_peso,
        "min_lado": min_lado,
        "puentes_cortados": len(puentes_debiles(aristas, max_peso, min_lado)),
        "mezclados_antes": len(mezcla),
        "mezclados_despues": len(mezclados(nuevos, df)),
        "fp_antes": antes["fp"],
        "fp_despues": despues["fp"],
        "fn_antes": antes["fn"],
        "fn_despues": despues["fn"],
        "precision_despues": despues["precision"],
        "recall_despues": despues["recall"],
        "recall_perdido": antes["recall"] - despues["recall"],
        "costo_antes": costo_fp * antes["fp"] + costo_fn * antes["fn"],
        "costo_despues": costo_fp * despues["fp"] + costo_fn * despues["fn"],
        "revision_marcados": len(marcados),
        "revision_mezclas_atrapadas": len(marcados & mezcla),
        "revision_precision": len(marcados & mezcla) / len(marcados) if marcados else 0.0,
        "revision_recall": len(marcados & mezcla) / len(mezcla) if mezcla else 0.0,
    }


def comparar_politicas(
    clusters: pd.DataFrame,
    aristas: pd.DataFrame,
    df: pd.DataFrame,
    pesos: tuple[float, ...] = (0, 5, 10, 15, 20, 25, 30),
    lados: tuple[int, ...] = (1, 2),
) -> pd.DataFrame:
    """Tabla de políticas (``max_peso`` 0 = no cortar nada)."""
    return pd.DataFrame(
        [evaluar_politica(clusters, aristas, df, peso, lado) for lado in lados for peso in pesos]
    )


def mezclas_sostenidas_por_puente(
    clusters: pd.DataFrame, aristas: pd.DataFrame, df: pd.DataFrame
) -> dict:
    """¿Cuántas uniones erróneas cuelgan de un puente? (sin parámetros que elegir).

    Un clúster mezclado está "sostenido por un puente" si alguna de sus aristas puente une
    registros de personas distintas: cortarla separaría las personas. Devuelve el conteo
    y el peso de esos puentes.
    """
    persona = df.set_index("unique_id")["cluster"]
    mezcla = mezclados(clusters, df)
    puentes = aristas[aristas["is_bridge"] & aristas["cluster_id"].isin(mezcla)]
    cruzan = puentes[puentes["id_l"].map(persona) != puentes["id_r"].map(persona)]
    sostenidos = set(cruzan["cluster_id"])
    return {
        "mezclados": len(mezcla),
        "sostenidos_por_puente": len(sostenidos),
        "pesos_de_esos_puentes": sorted(round(float(w), 2) for w in cruzan["match_weight"]),
    }


def elegir_politica(tabla: pd.DataFrame) -> pd.Series:
    """La política de menor costo; a igual costo, la que menos interviene."""
    return tabla.sort_values(["costo_despues", "puentes_cortados", "max_peso"]).iloc[0]
