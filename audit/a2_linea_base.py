"""Auditoría 2: Splink contra reglas determinísticas simples, en todas las pruebas reportadas.

Reglas (unión transitiva, como la agrupación de Splink; nulos nunca coinciden):

- ``R1 documento``: mismo documento estandarizado.
- ``R2 documento + 1er apellido``: mismo documento y mismo primer apellido.
- ``R3 nombre completo + fecha``: mismos nombres, apellidos y fecha de nacimiento.
- ``R1 ∪ R3``: cualquiera de las dos (la más fuerte de las simples).

Las reglas usan **la misma estandarización** que el modelo con el que se comparan (v1 o
v2), así que la diferencia mide lo que aporta el modelo probabilístico, no la limpieza.
En fake_1000 no hay documento: R1 usa el correo. En FEBRL, ``soc_sec_id``.

Las diferencias Splink − regla son pareadas por persona (bootstrap del proyecto).
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np
import pandas as pd

from identidades import escala as escala_mod
from identidades import flujo, modelo, tiempo_real
from identidades.escenario_hito3 import generar_escenario
from identidades.modelo_co_v2 import ESQUEMA_V2
from identidades.modelo_febrl import ESQUEMA_FEBRL

import _comun as c

SALIDA = c.RESULTADOS / "a2_linea_base.json"
N_BOOT = 1000


def reglas_colombia(preparado: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[list[str]]]]:
    p = preparado.assign(_nombre_completo=c.nombre_completo(preparado))
    return p, {
        "R1 documento": [["documento"]],
        "R2 documento + 1er apellido": [["documento", "primer_apellido"]],
        "R3 nombre completo + fecha": [["_nombre_completo", "fecha_nacimiento"]],
        "R1 ∪ R3": [["documento"], ["_nombre_completo", "fecha_nacimiento"]],
    }


def reglas_fake_1000(preparado: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[list[str]]]]:
    return preparado, {
        "R1 correo (no hay documento)": [["email"]],
        "R2 correo + apellido": [["email", "surname"]],
        "R3 nombre + apellido + fecha": [["first_name", "surname", "dob"]],
        "R1 ∪ R3": [["email"], ["first_name", "surname", "dob"]],
    }


def reglas_febrl(preparado: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[list[str]]]]:
    return preparado, {
        "R1 documento (soc_sec_id)": [["soc_sec_id"]],
        "R2 documento + apellido": [["soc_sec_id", "surname"]],
        "R3 nombre + apellido + fecha": [["given_name", "surname", "date_of_birth"]],
        "R1 ∪ R3": [["soc_sec_id"], ["given_name", "surname", "date_of_birth"]],
    }


def comparar(
    nombre: str,
    registros: pd.DataFrame,
    splink: dict[str, pd.DataFrame],
    preparado: pd.DataFrame,
    reglas_fn,
    n_bootstrap: int = N_BOOT,
) -> dict[str, Any]:
    """Métricas por clúster de cada modelo Splink y cada regla, y diferencias pareadas."""
    p, reglas = reglas_fn(preparado)
    metodos: dict[str, pd.DataFrame] = dict(splink)
    for etiqueta, regla in reglas.items():
        metodos[etiqueta] = c.clusters_por_reglas(p, regla)
    filas = {}
    for etiqueta, cl in metodos.items():
        m = c.metricas_cluster(cl, registros, n_bootstrap)
        filas[etiqueta] = {**c.resumen(m), "intervalos": m.get("intervalos")}
    diferencias = {}
    if n_bootstrap:
        for s_nombre, s_cl in splink.items():
            for etiqueta in reglas:
                diferencias[f"{s_nombre} − {etiqueta}"] = c.diferencia_pareada(
                    metodos[etiqueta], s_cl, registros, n_bootstrap
                )
    print(nombre)
    for etiqueta, f in filas.items():
        print(f"   {etiqueta:38s} P={f['precision']:.4f} R={f['recall']:.4f} "
              f"F1={f['f1']:.4f} exactas={f['pct_clusters_exactos']:.4f}")  # fmt: skip
    return {"registros": len(registros), "personas": int(registros["cluster"].nunique()),
            "metodos": filas, "diferencias": diferencias}  # fmt: skip


def hito1() -> dict[str, Any]:
    dev, prueba = c.prueba_hito1()
    d = flujo.desarrollar(dev)
    linker = flujo.aplicar_modelo(d.linker, prueba)
    cl = modelo.agrupar(linker, modelo.predecir(linker), d.umbral).as_pandas_dataframe()
    return comparar("hito 1 · prueba fake_1000", prueba, {"Splink (hito 1)": cl},
                    modelo.preparar(prueba), reglas_fake_1000)  # fmt: skip


def febrl() -> dict[str, Any]:
    dev, prueba = c.prueba_febrl()
    d = flujo.desarrollar(dev, esquema=ESQUEMA_FEBRL)
    linker = flujo.aplicar_modelo(d.linker, prueba, ESQUEMA_FEBRL)
    cl = modelo.agrupar(linker, modelo.predecir(linker), d.umbral).as_pandas_dataframe()
    return comparar("FEBRL3 · prueba", prueba, {"Splink (FEBRL)": cl},
                    ESQUEMA_FEBRL.preparar(prueba), reglas_febrl)  # fmt: skip


def colombia(nombre: str, registros: pd.DataFrame, n_bootstrap: int = N_BOOT) -> dict[str, Any]:
    """v1 y v2 congelados, y las reglas con cada estandarización."""
    (cfg1, u1), (cfg2, u2) = c.modelo_v1(), c.modelo_v2()
    v1 = c.aplicar_congelado(cfg1, registros, c.modelo_co.esquema(True), u1).clusters
    v2 = c.aplicar_congelado(cfg2, registros, ESQUEMA_V2, u2).clusters
    return {
        "estandarizacion_v1": comparar(f"{nombre} · reglas con estandarización v1", registros,
                                       {"Splink v1": v1}, c.PREPARAR_V1(registros),
                                       reglas_colombia, n_bootstrap),
        "estandarizacion_v2": comparar(f"{nombre} · reglas con estandarización v2", registros,
                                       {"Splink v2": v2}, c.PREPARAR_V2(registros),
                                       reglas_colombia, n_bootstrap),
    }  # fmt: skip


def tiempo_real_reglas() -> dict[str, Any]:
    """'¿Ya es cliente?' por regla contra la misma base de registros de oro del hito 5."""
    cfg, umbral = c.modelo_v2()
    registros_base, consultas, _ = tiempo_real.preparar_evaluacion(3000, 5050)
    base = tiempo_real.construir_base(registros_base, cfg, umbral)
    pb = c.PREPARAR_V2(base).assign(_nombre_completo=lambda d: c.nombre_completo(d))
    pc = c.PREPARAR_V2(consultas.drop(columns="existe")).assign(
        _nombre_completo=lambda d: c.nombre_completo(d)
    )
    persona_cliente = base.set_index("unique_id")["cluster"]
    reglas = {
        "R1 documento": [["documento"]],
        "R2 documento + 1er apellido": [["documento", "primer_apellido"]],
        "R3 nombre completo + fecha": [["_nombre_completo", "fecha_nacimiento"]],
        "R1 ∪ R3": [["documento"], ["_nombre_completo", "fecha_nacimiento"]],
    }
    resultado = {}
    for etiqueta, regla in reglas.items():
        decisiones = []
        for i in range(len(pc)):
            encontrados: list[int] = []
            for cols in regla:
                fila = pc.iloc[i][cols]
                if fila.isna().any():
                    continue
                mascara = np.logical_and.reduce(
                    [(pb[col] == fila[col]).fillna(False).to_numpy(dtype=bool) for col in cols]
                )
                encontrados += pb.loc[mascara, "unique_id"].tolist()
            unicos = sorted(set(encontrados))
            # Un solo cliente: "cliente". Varios: no se puede decidir sin modelo -> revisar.
            decision = "cliente" if len(unicos) == 1 else ("revisar" if unicos else "nuevo")
            correcto = (
                len(unicos) == 1 and persona_cliente[unicos[0]] == consultas["cluster"].iloc[i]
            )
            decisiones.append((decision, correcto))
        t = pd.DataFrame(decisiones, columns=["decision", "correcto"]).assign(
            existe=consultas["existe"].to_numpy()
        )
        tp = int(((t["decision"] == "cliente") & t["existe"] & t["correcto"]).sum())
        fp = int(((t["decision"] == "cliente") & ~(t["existe"] & t["correcto"])).sum())
        fn = int(t["existe"].sum()) - tp
        resultado[etiqueta] = {
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn),
            "tp": tp, "fp": fp, "fn": fn,
            "decisiones_existentes": t[t["existe"]]["decision"].value_counts().to_dict(),
            "decisiones_nuevas": t[~t["existe"]]["decision"].value_counts().to_dict(),
        }  # fmt: skip
        print(f"   tiempo real {etiqueta:30s} P={resultado[etiqueta]['precision']:.4f} "
              f"R={resultado[etiqueta]['recall']:.4f}")  # fmt: skip
    return {"base_clientes": len(base), "consultas": len(consultas), "reglas": resultado}


def escala_reglas(n: int) -> dict[str, Any]:
    """Reglas sobre los datos de escala ya generados (``data/escala``, solo lectura)."""
    registros = escala_mod.generar(n)  # lee la caché existente; no escribe si ya está
    preparado = escala_mod.preparar(registros)
    return comparar(f"escala {len(registros):,} registros", registros, {}, preparado,
                    reglas_colombia, n_bootstrap=0)  # fmt: skip


SECCIONES = {
    "hito1_prueba": hito1,
    "hito2_prueba_normal": lambda: colombia("hito 2 · prueba normal", c.prueba_hito2()),
    "ciega_1": lambda: colombia("ciega 1", c.ciega_1()[0]),
    "ciega_2": lambda: colombia("ciega 2", c.ciega_2()[0]),
    "febrl3_prueba": febrl,
    "hito3_prueba": lambda: colombia(
        "hito 3 · escenario de prueba (3131)", generar_escenario(2000, 3131)[0]
    ),  # fmt: skip
    "hito5_tiempo_real": tiempo_real_reglas,
    "escala_100000": lambda: escala_reglas(100_000),
    "escala_1000000": lambda: escala_reglas(1_000_000),
}


def main() -> None:
    """Corre las secciones pedidas (todas por defecto) y guarda después de cada una."""
    pedidas = sys.argv[1:] or list(SECCIONES)
    resultado = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    for nombre in pedidas:
        if (
            nombre.startswith("escala_")
            and not (c.rutas.DATA / "escala" / f"registros_{nombre.split('_')[1]}.parquet").exists()
        ):
            continue  # no se generan datos de escala nuevos en data/
        resultado[nombre] = SECCIONES[nombre]()
        c.guardar_json(resultado, SALIDA)


if __name__ == "__main__":
    main()
