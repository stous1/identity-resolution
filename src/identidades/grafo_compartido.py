"""Grafo de identidad compartida: clientes distintos que comparten un dato.

Cada valor normalizado (teléfono, correo, dirección o documento) que aparece en dos o más
clientes (clústeres del modelo) forma un grupo: una "estrella" con el valor en el centro.
Cada grupo se clasifica con reglas explicables:

1. ``sospechoso`` si es un **documento** compartido: dos clientes distintos con el mismo
   número de identificación (suplantación, o una unión que el modelo no hizo).
2. ``relleno`` si el valor tiene forma genérica (3000000000, notiene@..., "CENTRO") o lo
   comparten demasiados clientes (``max_clientes``).
3. ``hogar`` si los clientes comparten apellido, tolerando errores de digitación
   (fracción de pares ``>= min_apellido``).
4. ``sospechoso`` en otro caso: personas sin relación que comparten un dato de contacto.

Los umbrales se eligen en desarrollo (``elegir_parametros``).
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

import jellyfish
import numpy as np
import pandas as pd

from identidades import estandarizacion as v1
from identidades.escenario_hito3 import CANALES_DIGITALES, TIPOS_COMPARTIDOS, normalizar

UMBRAL_APELLIDO: float = 0.88
CLASES: tuple[str, ...] = ("relleno", "hogar", "sospechoso")
PALABRAS_GENERICAS: set[str] = {
    "NOTIENE", "NOTENGO", "SINCORREO", "NINGUNO", "NA", "NOAPLICA", "CORREO", "NO", "XX",
    "SINDATO", "NULL", "PRUEBA", "TEST",
}  # fmt: skip


@dataclass(frozen=True)
class ParametrosClasificacion:
    max_clientes: int = 6
    min_apellido: float = 0.5


def es_generico(tipo: str, valor: str) -> bool:
    """¿El valor tiene forma de dato de relleno? (sin mirar cuántos lo comparten)."""
    if tipo == "celular":
        repetido = re.search(r"(\d)\1{5,}", valor) is not None
        secuencia = any(s in valor for s in ("123456", "234567", "345678", "987654"))
        return repetido or secuencia
    if tipo == "correo":
        usuario = re.sub(r"[^A-Z]", "", valor.split("@")[0].upper())
        dominio = valor.split("@")[-1].split(".")[0].upper()
        return usuario in PALABRAS_GENERICAS or usuario == dominio
    if tipo == "direccion":
        return v1.normalizar_direccion(valor)["via"] is None
    return False


def apellido_parecido(a: set[str], b: set[str], umbral: float = UMBRAL_APELLIDO) -> bool:
    """¿Dos clientes comparten algún apellido, tolerando errores de digitación?"""
    return any(jellyfish.jaro_winkler_similarity(x, y) >= umbral for x in a for y in b)


def grupos_compartidos(registros: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    """Un renglón por valor compartido por dos o más clientes, con sus señales."""
    base = registros.merge(clusters[["unique_id", "cluster_id"]], on="unique_id")
    base = base.assign(
        fecha=pd.to_datetime(base["fecha_actualizacion"]),
        apellido=base["apellidos"].map(
            lambda a: (v1.quitar_tildes(v1.normalizar_nombre(a)) or "").split()[:2]
        ),
        digital=base["canal"].isin(CANALES_DIGITALES),
    )
    apellidos_cliente = (
        base.explode("apellido")
        .dropna(subset=["apellido"])
        .groupby("cluster_id")["apellido"]
        .agg(set)
    )
    filas = []
    for tipo, columna in TIPOS_COMPARTIDOS.items():
        claves = base[columna].map(lambda v, t=tipo: normalizar(t, v))
        for valor, g in base.assign(valor=claves).dropna(subset=["valor"]).groupby("valor"):
            clientes = sorted(set(g["cluster_id"]))
            if len(clientes) < 2:
                continue
            pares = list(itertools.combinations(clientes, 2))[:200]
            comparten = [
                apellido_parecido(apellidos_cliente.get(a, set()), apellidos_cliente.get(b, set()))
                for a, b in pares
            ]
            filas.append(
                {
                    "tipo": tipo,
                    "valor": valor,
                    "clientes": len(clientes),
                    "registros": len(g),
                    "ids_clientes": clientes,
                    "ids_registros": sorted(g["unique_id"]),
                    "frac_apellido_comun": float(np.mean(comparten)),
                    "frac_validado": float(g["validado"].mean()),
                    "frac_digital": float(g["digital"].mean()),
                    "dias": int((g["fecha"].max() - g["fecha"].min()).days),
                    "generico": es_generico(tipo, valor),
                }
            )
    return pd.DataFrame(filas)


def clasificar(grupos: pd.DataFrame, p: ParametrosClasificacion) -> pd.Series:
    def regla(fila: pd.Series) -> str:
        if fila["tipo"] == "documento":
            return "sospechoso"
        if fila["generico"] or fila["clientes"] > p.max_clientes:
            return "relleno"
        if fila["frac_apellido_comun"] >= p.min_apellido:
            return "hogar"
        return "sospechoso"

    return grupos.apply(regla, axis=1)


def unir_verdad(grupos: pd.DataFrame, verdad: pd.DataFrame) -> pd.DataFrame:
    """Agrega la etiqueta verdadera. Un grupo que la verdad no tiene es una misma persona
    repartida en varios clústeres (el valor solo lo usa una persona): ``misma_persona``.
    """
    unidos = grupos.merge(verdad[["tipo", "valor", "etiqueta"]], on=["tipo", "valor"], how="left")
    return unidos.assign(etiqueta=unidos["etiqueta"].fillna("misma_persona"))


def metricas(clasificados: pd.DataFrame) -> dict:
    """Matriz de confusión, exactitud y precisión/recall por clase."""
    confusion = pd.crosstab(clasificados["etiqueta"], clasificados["prediccion"])
    por_clase = {}
    for clase in CLASES:
        predichos = clasificados["prediccion"] == clase
        reales = clasificados["etiqueta"] == clase
        tp = int((predichos & reales).sum())
        por_clase[clase] = {
            "reales": int(reales.sum()),
            "predichos": int(predichos.sum()),
            "precision": tp / predichos.sum() if predichos.sum() else 0.0,
            "recall": tp / reales.sum() if reales.sum() else 0.0,
        }
    return {
        "grupos": len(clasificados),
        "exactitud": float((clasificados["prediccion"] == clasificados["etiqueta"]).mean()),
        "por_clase": por_clase,
        "confusion": {r: confusion.loc[r].to_dict() for r in confusion.index},
    }


def intervalos(
    clasificados: pd.DataFrame, n: int = 1000, semilla: int = 0, nivel: float = 0.95
) -> dict:
    """Intervalos por bootstrap de grupos para la exactitud y el recall de cada clase."""
    rng = np.random.default_rng(semilla)
    acierto = (clasificados["prediccion"] == clasificados["etiqueta"]).to_numpy(dtype=float)
    etiquetas = clasificados["etiqueta"].to_numpy()
    muestras = rng.integers(0, len(acierto), size=(n, len(acierto)))
    alfa = (1 - nivel) / 2

    def ic(valores: np.ndarray) -> dict:
        return {
            "ic_inf": float(np.nanquantile(valores, alfa)),
            "ic_sup": float(np.nanquantile(valores, 1 - alfa)),
        }

    resultado = {"exactitud": ic(acierto[muestras].mean(axis=1))}
    for clase in CLASES:
        m = etiquetas[muestras] == clase
        with np.errstate(invalid="ignore", divide="ignore"):
            recall = (acierto[muestras] * m).sum(axis=1) / m.sum(axis=1)
        resultado[f"recall_{clase}"] = ic(recall)
    return resultado


def elegir_parametros(
    grupos: pd.DataFrame,
    verdad: pd.DataFrame,
    maximos: tuple[int, ...] = (3, 4, 5, 6, 8, 10, 15),
    minimos: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0),
) -> tuple[ParametrosClasificacion, pd.DataFrame]:
    """Busca en desarrollo los umbrales con mayor exactitud balanceada (recall medio)."""
    filas = []
    for max_clientes, min_apellido in itertools.product(maximos, minimos):
        p = ParametrosClasificacion(max_clientes, min_apellido)
        c = unir_verdad(grupos.assign(prediccion=clasificar(grupos, p)), verdad)
        m = metricas(c)
        filas.append(
            {
                "max_clientes": max_clientes,
                "min_apellido": min_apellido,
                "exactitud": m["exactitud"],
                "recall_medio": float(np.mean([v["recall"] for v in m["por_clase"].values()])),
            }
        )
    tabla = pd.DataFrame(filas).sort_values(
        ["recall_medio", "exactitud", "max_clientes"], ascending=[False, False, True]
    )
    mejor = tabla.iloc[0]
    return (
        ParametrosClasificacion(int(mejor["max_clientes"]), float(mejor["min_apellido"])),
        tabla,
    )
