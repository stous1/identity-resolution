"""Flujo del hito 3: registro de oro, grafo de identidad compartida y puentes.

Regla de evaluación: todo lo que se elige (regla de supervivencia por campo, umbrales del
clasificador de grupos, política de puentes) se elige en el escenario de **desarrollo**
(semilla 3030) y se mide una sola vez en el de **prueba** (semilla 3131). Los clústeres
salen del modelo v2 congelado (``hito2b-congelado``), sin ajustes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from identidades import (
    datos,
    errores_ciegos_2,
    flujo,
    flujo_hito2b,
    grafo_compartido,
    modelo,
    puentes,
    registro_oro,
    sinteticos,
    tableros,
)
from identidades.escenario_hito3 import generar_escenario
from identidades.modelo_co_v2 import ESQUEMA_V2

SEMILLA_DESARROLLO: int = 3030
SEMILLA_PRUEBA: int = 3131
UMBRALES_OPERACION: tuple[float, ...] = (0.9, 0.99)  # además del congelado

ETIQUETAS_REGLAS: dict[str, str] = {
    "mas_reciente": "Más reciente",
    "validado": "Validado más reciente",
    "fuente_confiable": "Fuente más confiable",
    "frecuente": "Más frecuente",
}

ARCHIVOS_PUBLICABLES: list[str] = [
    "metricas.json",
    "registro_oro.html",
    "registro_oro.png",
    "politicas_puentes_desarrollo.csv",
    "cola_revision.csv",
    "universo_puntos.json",
    "universo_enlaces.json",
]


class Aplicado:
    """El modelo congelado aplicado a un escenario."""

    def __init__(self, registros: pd.DataFrame, configuracion: dict, umbral: float) -> None:
        self.registros = registros
        self.umbral = umbral
        self.linker = flujo.aplicar_configuracion(configuracion, registros, ESQUEMA_V2)
        self.df_pred = modelo.predecir(self.linker)
        self._clusters: dict[float, tuple] = {}

    def clusters(self, umbral: float | None = None):
        """``(df_clusters, clusters_pandas, aristas_con_puentes)`` a un umbral."""
        umbral = self.umbral if umbral is None else umbral
        if umbral not in self._clusters:
            df_clusters = modelo.agrupar(self.linker, self.df_pred, umbral)
            aristas = puentes.aristas_con_puentes(self.linker, self.df_pred, df_clusters, umbral)
            self._clusters[umbral] = (df_clusters, df_clusters.as_pandas_dataframe(), aristas)
        return self._clusters[umbral]


def _relleno_predicho(grupos: pd.DataFrame, prediccion: pd.Series) -> dict[str, set[str]]:
    relleno = grupos[prediccion == "relleno"]
    return {tipo: set(g["valor"]) for tipo, g in relleno.groupby("tipo")}


def ejecutar_hito3(
    directorio: Path, n_personas: int = 2000, n_bootstrap: int = 1000
) -> dict[str, Any]:
    directorio.mkdir(parents=True, exist_ok=True)
    configuracion, umbral = flujo_hito2b.cargar_congelado_v2()

    escenarios = {
        "desarrollo": generar_escenario(n_personas, SEMILLA_DESARROLLO),
        "prueba": generar_escenario(n_personas, SEMILLA_PRUEBA),
    }
    aplicados = {k: Aplicado(r, configuracion, umbral) for k, (r, _, _) in escenarios.items()}
    calidad_union = {
        k: flujo.evaluar(a.linker, a.registros, umbral).metricas["clusters"]
        for k, a in aplicados.items()
    }

    # ---- Grafo de identidad compartida: umbrales en desarrollo, medición en prueba ----
    grupos, clasificados = {}, {}
    for k, a in aplicados.items():
        grupos[k] = grafo_compartido.grupos_compartidos(a.registros, a.clusters()[1])
    parametros, busqueda = grafo_compartido.elegir_parametros(
        grupos["desarrollo"], escenarios["desarrollo"][2]
    )
    for k in aplicados:
        g = grupos[k].assign(prediccion=grafo_compartido.clasificar(grupos[k], parametros))
        clasificados[k] = grafo_compartido.unir_verdad(g, escenarios[k][2])
    grafo_resultado = {
        "parametros_elegidos_en_desarrollo": parametros.__dict__,
        "desarrollo": grafo_compartido.metricas(clasificados["desarrollo"]),
        "prueba": {
            **grafo_compartido.metricas(clasificados["prueba"]),
            "intervalos": grafo_compartido.intervalos(clasificados["prueba"], n_bootstrap),
        },
    }

    # ---- Registro de oro: regla por campo en desarrollo, acierto en prueba ----
    oro = {}
    for k, a in aplicados.items():
        cl = a.clusters()[1]
        relleno = _relleno_predicho(clasificados[k], clasificados[k]["prediccion"])
        relleno = {"celular": relleno.get("celular", set()), "correo": relleno.get("correo", set()),
                   "direccion": relleno.get("direccion", set())}  # fmt: skip
        cand = registro_oro.candidatos(a.registros, cl, relleno)
        por_regla = {}
        for regla in registro_oro.REGLAS:
            tabla = registro_oro.evaluar(
                registro_oro.aplicar_regla(cand, regla), cl, a.registros, escenarios[k][1]
            )
            por_regla[regla] = registro_oro.resumen_aciertos(
                tabla, n_bootstrap if k == "prueba" else 50
            )
        oro[k] = {"candidatos": cand, "por_regla": por_regla, "clusters": cl}
    reglas = registro_oro.elegir_reglas(oro["desarrollo"]["por_regla"])
    a_prueba = aplicados["prueba"]
    tabla_final = registro_oro.evaluar(
        registro_oro.registro_de_oro(oro["prueba"]["candidatos"], reglas),
        oro["prueba"]["clusters"],
        a_prueba.registros,
        escenarios["prueba"][1],
    )
    techo = registro_oro.alcanzable(oro["prueba"]["candidatos"], tabla_final)
    oro_resultado = {
        "reglas_elegidas_en_desarrollo": reglas,
        "prueba_con_reglas_elegidas": registro_oro.resumen_aciertos(tabla_final, n_bootstrap),
        "prueba_techo_alcanzable": techo.to_dict(),
        "prueba_por_regla": oro["prueba"]["por_regla"],
        "desarrollo_por_regla": oro["desarrollo"]["por_regla"],
    }

    # ---- Puentes: política por umbral elegida en desarrollo, medida en prueba ----
    umbrales = (umbral, *UMBRALES_OPERACION)
    politicas, puentes_resultado = [], {}
    for u in umbrales:
        _, cl_dev, ar_dev = aplicados["desarrollo"].clusters(u)
        tabla = puentes.comparar_politicas(cl_dev, ar_dev, escenarios["desarrollo"][0])
        politicas.append(tabla.assign(umbral=u))
        elegida = puentes.elegir_politica(tabla)
        _, cl, ar = a_prueba.clusters(u)
        puentes_resultado[str(u)] = {
            "politica_elegida_en_desarrollo": {
                "max_peso": float(elegida["max_peso"]),
                "min_lado": int(elegida["min_lado"]),
            },
            "prueba": puentes.evaluar_politica(
                cl, ar, a_prueba.registros, float(elegida["max_peso"]), int(elegida["min_lado"])
            ),
            "prueba_sostenidas_por_puente": puentes.mezclas_sostenidas_por_puente(
                cl, ar, a_prueba.registros
            ),
        }
    pd.concat(politicas).to_csv(
        directorio / "politicas_puentes_desarrollo.csv", index=False, lineterminator="\n"
    )
    puentes_resultado["casos_externos"] = casos_externos_puentes(configuracion, umbral)

    # ---- Cola de revisión (entrada del agente del hito 4) ----
    cola = cola_de_revision(a_prueba, clasificados["prueba"], puentes_resultado)
    cola.to_csv(directorio / "cola_revision.csv", index=False, lineterminator="\n")

    # ---- Gráfico del registro de oro y universo para Cosmograph ----
    filas = {}
    for regla in registro_oro.REGLAS:
        for campo, v in oro["prueba"]["por_regla"][regla].items():
            filas.setdefault(f"{campo}", {})[regla] = v
    tabla_grafico = pd.DataFrame(
        [
            {
                "grupo": campo,
                "metrica": ETIQUETAS_REGLAS[regla],
                **{k: v[k] for k in ("valor", "ic_inf", "ic_sup")},
            }
            for campo, reglas_campo in filas.items()
            for regla, v in reglas_campo.items()
        ]
    )
    tableros.guardar_intervalos(
        tabla_grafico,
        "Registro de oro en prueba: acierto por campo y regla de supervivencia",
        directorio / "registro_oro.html",
    )
    exportar_universo(a_prueba, clasificados["prueba"], puentes_resultado, directorio)

    metricas = {
        "escenarios": {
            k: {
                "semilla": SEMILLA_DESARROLLO if k == "desarrollo" else SEMILLA_PRUEBA,
                "registros": len(r),
                "personas": int(r["cluster"].nunique()),
                "grupos_compartidos_verdaderos": v["etiqueta"].value_counts().to_dict(),
                "origen_registros": r["origen"].value_counts().to_dict(),
            }
            for k, (r, _, v) in escenarios.items()
        },
        "modelo": {"tag": flujo_hito2b.TAG_CONGELADO, "umbral": umbral},
        "calidad_union": calidad_union,
        "registro_oro": oro_resultado,
        "grafo_compartido": grafo_resultado,
        "puentes": puentes_resultado,
        "cola_revision": cola["motivo"].value_counts().to_dict(),
    }
    (directorio / "metricas.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="\n",
    )
    return metricas


def casos_externos_puentes(configuracion: dict, umbral: float) -> dict:
    """Puentes en dos casos conocidos: el 109-844 del hito 1 y las uniones de la ciega 2."""
    df = datos.cargar_fake_1000()
    dev, prueba = datos.dividir_por_persona(df)
    d = flujo.desarrollar(dev)
    lk = flujo.aplicar_modelo(d.linker, prueba)
    sp = modelo.predecir(lk)
    sc = modelo.agrupar(lk, sp, d.umbral)
    ar = puentes.aristas_con_puentes(lk, sp, sc, d.umbral)
    caso = ar[(ar["id_l"] == 109) & (ar["id_r"] == 844)].iloc[0]
    puentes_hito1 = ar[ar["is_bridge"]].sort_values("match_weight").reset_index(drop=True)
    rango = (
        int(puentes_hito1.index[puentes_hito1["id_l"].eq(109) & puentes_hito1["id_r"].eq(844)][0])
        + 1
    )

    _, personas = sinteticos.generar(2000, 7777)
    registros = errores_ciegos_2.capturar(personas, semilla=7777)[0]
    aplicado = Aplicado(registros, configuracion, umbral)
    _, cl, ar2 = aplicado.clusters()
    return {
        "hito1_109_844": {
            "es_puente": bool(caso["is_bridge"]),
            "match_weight": float(caso["match_weight"]),
            "lado_menor": int(caso["lado_menor"]),
            "rango_entre_puentes_por_peso": rango,
            "puentes_totales": len(puentes_hito1),
        },
        "hito1_sostenidas_por_puente": puentes.mezclas_sostenidas_por_puente(
            sc.as_pandas_dataframe(), ar, prueba
        ),
        "ciega2_modelo_v2_sostenidas_por_puente": puentes.mezclas_sostenidas_por_puente(
            cl, ar2, registros
        ),
    }


def cola_de_revision(
    aplicado: Aplicado, clasificados: pd.DataFrame, puentes_resultado: dict
) -> pd.DataFrame:
    """Casos para el agente del hito 4: puentes débiles y grupos sospechosos (prueba)."""
    politica = puentes_resultado[str(UMBRALES_OPERACION[0])]["politica_elegida_en_desarrollo"]
    _, _, aristas = aplicado.clusters(UMBRALES_OPERACION[0])
    debiles = puentes.puentes_debiles(aristas, politica["max_peso"], politica["min_lado"])
    filas = [
        {
            "motivo": "puente_debil",
            "detalle": f"umbral {UMBRALES_OPERACION[0]}: une {int(f.lado_menor)} registro(s) "
            f"con peso {f.match_weight:.1f}",
            "ids_registros": f"{int(f.id_l)};{int(f.id_r)}",
            "cluster_id": f.cluster_id,
        }
        for f in debiles.itertuples()
    ]
    for f in clasificados[clasificados["prediccion"] == "sospechoso"].itertuples():
        filas.append(
            {
                "motivo": f"grupo_sospechoso_{f.tipo}",
                "detalle": f"{f.clientes} clientes comparten {f.tipo} {f.valor}; "
                f"{f.frac_apellido_comun:.0%} con apellido común; "
                f"{f.frac_digital:.0%} por canal digital",
                "ids_registros": ";".join(map(str, f.ids_registros)),
                "cluster_id": ";".join(map(str, f.ids_clientes)),
            }
        )
    return pd.DataFrame(filas)


COLORES_UNIVERSO: dict[str, str] = {
    "registro": "#94a3b8",
    "registro_puente": "#f97316",
    "registro_sospechoso": "#dc2626",
    "valor_relleno": "#7c3aed",
    "valor_hogar": "#16a34a",
    "valor_sospechoso": "#dc2626",
    "enlace_fuerte": "#64748b",
    "enlace_debil": "#cbd5e1",
    "enlace_puente": "#f97316",
    "enlace_relleno": "#a78bfa",
    "enlace_hogar": "#86efac",
    "enlace_sospechoso": "#f87171",
}


def exportar_universo(
    aplicado: Aplicado, clasificados: pd.DataFrame, puentes_resultado: dict, directorio: Path
) -> None:
    """Puntos y enlaces del escenario de prueba para Cosmograph (JSON).

    Puntos: registros y valores compartidos (estrellas). Enlaces: coincidencias del
    modelo (fuertes sobre el umbral congelado, débiles entre 0,9 y ese umbral), puentes
    débiles, y registro-valor por clase del grupo.
    """
    u_bajo = UMBRALES_OPERACION[0]
    politica = puentes_resultado[str(u_bajo)]["politica_elegida_en_desarrollo"]
    _, cl_bajo, aristas = aplicado.clusters(u_bajo)
    debiles = puentes.puentes_debiles(aristas, politica["max_peso"], politica["min_lado"])
    pares_debiles = set(zip(debiles["id_l"], debiles["id_r"], strict=True))
    en_puente = {i for par in pares_debiles for i in par}
    sospechosos = clasificados[clasificados["prediccion"] == "sospechoso"]
    en_sospecha = {i for ids in sospechosos["ids_registros"] for i in ids}

    puntos = []
    for f in aplicado.registros.itertuples():
        categoria = (
            "registro_puente"
            if f.unique_id in en_puente
            else "registro_sospechoso"
            if f.unique_id in en_sospecha
            else "registro"
        )
        puntos.append(
            {
                "id": f"r{f.unique_id}",
                "categoria": categoria,
                "tamano": 2,
                "etiqueta": f"{f.nombres} {f.apellidos}",
            }
        )
    enlaces = []
    for f in aristas.itertuples():
        if (f.id_l, f.id_r) in pares_debiles:
            categoria = "enlace_puente"
        elif f.match_probability >= aplicado.umbral:
            categoria = "enlace_fuerte"
        else:
            categoria = "enlace_debil"
        enlaces.append(
            {"origen": f"r{int(f.id_l)}", "destino": f"r{int(f.id_r)}", "categoria": categoria}
        )
    for f in clasificados.itertuples():
        id_valor = f"v:{f.tipo}:{f.valor}"
        puntos.append(
            {
                "id": id_valor,
                "categoria": f"valor_{f.prediccion}",
                "tamano": 4 + 2 * min(f.clientes, 20),
                "etiqueta": f"{f.tipo}: {f.valor} ({f.clientes} clientes)",
            }
        )
        for i in f.ids_registros:
            enlaces.append(
                {"origen": f"r{i}", "destino": id_valor, "categoria": f"enlace_{f.prediccion}"}
            )
    (directorio / "universo_puntos.json").write_text(
        json.dumps(puntos, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    (directorio / "universo_enlaces.json").write_text(
        json.dumps(enlaces, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
