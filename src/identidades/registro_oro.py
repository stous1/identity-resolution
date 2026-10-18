"""Registro de oro: un valor por campo para cada cliente (clúster), con reglas de supervivencia.

Para cada campo y cada clúster se elige uno de los valores de sus registros según una
regla:

- ``mas_reciente``: el del registro con la fecha de actualización más reciente.
- ``validado``: el más reciente entre los validados; si no hay, el más reciente.
- ``fuente_confiable``: el del canal más confiable (sucursal > app > web > call center >
  corresponsal); a igual canal, el más reciente.
- ``frecuente``: el valor (normalizado) que más se repite; a igual frecuencia, el más
  reciente. Es la referencia sin metadatos.

Los valores de relleno (los que el grafo de datos compartidos clasifica como relleno) no
pueden sobrevivir: si un registro los trae, se ignoran para ese campo.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from identidades import estandarizacion as v1
from identidades import estandarizacion_v2 as v2
from identidades.escenario_hito3 import normalizar

# Orden de confiabilidad de los canales que conoce el banco (no las tasas del generador).
RANGO_CANAL: dict[str, int] = {
    "sucursal": 5,
    "app": 4,
    "web": 3,
    "call_center": 2,
    "corresponsal": 1,
}

REGLAS: tuple[str, ...] = ("mas_reciente", "validado", "fuente_confiable", "frecuente")


def _nombre(valor: object) -> str | None:
    return v1.quitar_tildes(v1.normalizar_nombre(valor))


# Campo del registro de oro -> (columna de los registros, normalización para comparar).
CAMPOS: dict[str, tuple[str, Callable[[object], str | None]]] = {
    "documento": ("numero_documento", lambda v: normalizar("documento", v)),
    "nombres": ("nombres", _nombre),
    "apellidos": ("apellidos", _nombre),
    "fecha_nacimiento": ("fecha_nacimiento", v2.normalizar_fecha),
    "celular": ("celular", lambda v: normalizar("celular", v)),
    "correo": ("correo", lambda v: normalizar("correo", v)),
    "direccion": ("direccion", lambda v: normalizar("direccion", v)),
}


def candidatos(
    registros: pd.DataFrame,
    clusters: pd.DataFrame,
    relleno: dict[str, set[str]] | None = None,
) -> pd.DataFrame:
    """Tabla larga de valores candidatos: un renglón por (clúster, campo, registro).

    ``clusters`` asigna ``cluster_id`` a cada ``unique_id``. ``relleno`` da, por campo,
    los valores normalizados que no pueden sobrevivir.
    """
    relleno = relleno or {}
    base = registros.merge(clusters[["unique_id", "cluster_id"]], on="unique_id")
    base = base.assign(
        fecha=pd.to_datetime(base["fecha_actualizacion"]),
        rango=base["canal"].map(RANGO_CANAL).fillna(0),
    )
    partes = []
    for campo, (columna, norma) in CAMPOS.items():
        valores = base[columna].map(norma)
        parte = base[["cluster_id", "unique_id", "fecha", "rango", "validado"]].assign(
            campo=campo, valor=valores
        )
        parte = parte.dropna(subset=["valor"])
        parte = parte[~parte["valor"].isin(relleno.get(campo, set()))]
        partes.append(parte)
    return pd.concat(partes, ignore_index=True)


def aplicar_regla(cand: pd.DataFrame, regla: str) -> pd.DataFrame:
    """Valor sobreviviente por (clúster, campo) según ``regla``."""
    if regla not in REGLAS:
        raise ValueError(f"Regla desconocida: {regla}")
    c = cand.copy()
    if regla == "frecuente":
        c["frecuencia"] = c.groupby(["cluster_id", "campo", "valor"])["valor"].transform("size")
        orden = ["frecuencia", "fecha"]
    elif regla == "mas_reciente":
        orden = ["fecha"]
    elif regla == "validado":
        orden = ["validado", "fecha"]
    else:
        orden = ["rango", "fecha"]
    c = c.sort_values([*orden, "unique_id"], ascending=[*[False] * len(orden), True])
    return c.drop_duplicates(["cluster_id", "campo"])[["cluster_id", "campo", "valor"]]


def evaluar(
    oro: pd.DataFrame,
    clusters: pd.DataFrame,
    registros: pd.DataFrame,
    verdad: pd.DataFrame,
) -> pd.DataFrame:
    """Acierto por campo: ¿el registro de oro quedó con el valor vigente verdadero?

    Cada clúster se compara con la persona a la que pertenece la mayoría de sus registros.
    Un clúster sin ningún valor para un campo cuenta como fallo de ese campo. Devuelve una
    fila por (clúster, campo) con ``acierto`` (bool) y ``persona``.
    """
    asignacion = clusters[["unique_id", "cluster_id"]].merge(
        registros[["unique_id", "cluster"]], on="unique_id"
    )
    persona = asignacion.groupby("cluster_id")["cluster"].agg(lambda s: s.mode().iloc[0])
    esperado = verdad.set_index("cluster")
    filas = []
    for campo, (_, norma) in CAMPOS.items():
        correcto = esperado[campo].map(norma)
        filas.append(
            pd.DataFrame(
                {
                    "cluster_id": persona.index,
                    "persona": persona.to_numpy(),
                    "campo": campo,
                    "esperado": correcto.reindex(persona.to_numpy()).to_numpy(),
                }
            )
        )
    tabla = pd.concat(filas, ignore_index=True).merge(oro, on=["cluster_id", "campo"], how="left")
    tabla["acierto"] = tabla["valor"].notna() & (tabla["valor"] == tabla["esperado"])
    return tabla


def alcanzable(cand: pd.DataFrame, tabla: pd.DataFrame) -> pd.Series:
    """Techo por campo: fracción de clientes con el valor correcto en algún registro.

    Si ningún registro del cliente trae el valor vigente (por ejemplo, cambió de celular
    después de su última actualización), ninguna regla de supervivencia puede acertar.
    """
    presentes = cand[["cluster_id", "campo", "valor"]].drop_duplicates()
    unidos = tabla[["cluster_id", "campo", "esperado"]].merge(
        presentes,
        left_on=["cluster_id", "campo", "esperado"],
        right_on=["cluster_id", "campo", "valor"],
        how="left",
    )
    return unidos.assign(ok=unidos["valor"].notna()).groupby("campo")["ok"].mean()


def resumen_aciertos(
    tabla: pd.DataFrame, n_bootstrap: int = 1000, semilla: int = 0, nivel: float = 0.95
) -> dict[str, dict[str, float]]:
    """Porcentaje de acierto por campo, con intervalo por bootstrap de clientes."""
    rng = np.random.default_rng(semilla)
    clientes = tabla["cluster_id"].unique()
    alfa = (1 - nivel) / 2
    resultado = {}
    for campo, g in tabla.groupby("campo", sort=False):
        por_cliente = g.set_index("cluster_id")["acierto"].reindex(clientes).fillna(False)
        valores = por_cliente.to_numpy(dtype=float)
        muestras = rng.integers(0, len(valores), size=(n_bootstrap, len(valores)))
        medias = valores[muestras].mean(axis=1)
        resultado[campo] = {
            "valor": float(valores.mean()),
            "ic_inf": float(np.quantile(medias, alfa)),
            "ic_sup": float(np.quantile(medias, 1 - alfa)),
        }
    return resultado


def elegir_reglas(aciertos_por_regla: dict[str, dict[str, dict[str, float]]]) -> dict[str, str]:
    """Para cada campo, la regla con más acierto (a igual acierto, la primera de ``REGLAS``)."""
    campos = next(iter(aciertos_por_regla.values())).keys()
    return {
        campo: max(REGLAS, key=lambda r: (aciertos_por_regla[r][campo]["valor"], -REGLAS.index(r)))
        for campo in campos
    }


def registro_de_oro(cand: pd.DataFrame, reglas: dict[str, str]) -> pd.DataFrame:
    """Registro de oro con una regla por campo."""
    return pd.concat(
        [aplicar_regla(cand[cand["campo"] == campo], regla) for campo, regla in reglas.items()],
        ignore_index=True,
    )
