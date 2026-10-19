"""v1.1.1: cierre de reproducibilidad y ficha de cliente único.

- ``reevaluar_hito2``: el modelo v1 congelado sobre la prueba normal del hito 2 regenerada
  con la fecha fija. El hito 2 entrena su modelo; volver a correrlo daría otro modelo y
  cambiaría el umbral congelado que leen la validación y el hito 2b, así que se reevalúa
  el congelado sin reentrenar.
- ``exportar_fichas``: datos de la página "Ficha de cliente único" (ver más abajo).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from identidades import datos, flujo, flujo_v11, flujo_validacion, modelo_co, rutas, sinteticos


def _escribir(datos_json: dict, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(datos_json, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="\n",
    )


def reevaluar_hito2(directorio: Path, n_bootstrap: int = 1000, semilla: int = 42) -> dict:
    """v1 congelado (``hito2-congelado-r1``) en la prueba normal del hito 2 con fecha fija."""
    congelado = flujo_validacion.verificar_congelado()
    configuracion, umbral = flujo_validacion.cargar_congelado()
    registros, _ = sinteticos.generar(2000, semilla)
    _, prueba = datos.dividir_por_persona(registros, 0.6, semilla)
    linker = flujo.aplicar_configuracion(configuracion, prueba, modelo_co.esquema(True))
    ev = flujo.evaluar(linker, prueba, umbral, n_bootstrap, semilla)
    resultado = {
        "descripcion": (
            "Modelo v1 congelado, sin reentrenar, en la prueba normal del hito 2 generada con "
            "la fecha de Faker fija (v1.1.1). Las cifras de metricas.json son de la corrida "
            "original, que dependía de la fecha del día."
        ),
        "modelo_congelado": congelado,
        "umbral": umbral,
        "datos": {"registros": len(prueba), "personas": int(prueba["cluster"].nunique())},
        "clusters": ev.metricas["intervalos"]["clusters"],
        "pares": ev.metricas["intervalos"]["pares"],
    }
    _escribir(resultado, directorio / "reevaluacion_fecha_fija.json")
    return {k: round(v["valor"], 4) for k, v in resultado["clusters"].items() if "valor" in v}


# ---------------------------------------------------------------------------
# Ficha de cliente único
# ---------------------------------------------------------------------------

UMBRAL_REVISION: float = 0.9  # umbral de operación de la cola de revisión del hito 3
CAMPOS_HISTORIA: tuple[str, ...] = ("celular", "correo", "direccion")
COLUMNAS_REGISTRO: dict[str, str] = {
    "nombres": "nombres",
    "apellidos": "apellidos",
    "documento": "numero_documento",
    "fecha_nacimiento": "fecha_nacimiento",
    "celular": "celular",
    "correo": "correo",
    "direccion": "direccion",
    "ciudad": "ciudad",
}


def _texto(valor: object) -> str | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or valor is pd.NA:
        return None
    return str(valor)


def oro_con_origen(cand: pd.DataFrame, reglas: dict[str, str]) -> pd.DataFrame:
    """Como ``registro_oro.registro_de_oro``, pero conserva el registro de origen y la regla.

    Usa el mismo orden de cada regla de ``registro_oro.aplicar_regla``.
    """
    partes = []
    for campo, regla in reglas.items():
        c = cand[cand["campo"] == campo].copy()
        if regla == "frecuente":
            c["frecuencia"] = c.groupby(["cluster_id", "valor"])["valor"].transform("size")
            orden = ["frecuencia", "fecha"]
        elif regla == "mas_reciente":
            orden = ["fecha"]
        elif regla == "validado":
            orden = ["validado", "fecha"]
        else:
            orden = ["rango", "fecha"]
        c = c.sort_values([*orden, "unique_id"], ascending=[*[False] * len(orden), True])
        c = c.drop_duplicates(["cluster_id", "campo"]).assign(regla=regla)
        partes.append(c[["cluster_id", "campo", "valor", "unique_id", "regla"]])
    return pd.concat(partes, ignore_index=True)


def _historia(filas: pd.DataFrame) -> dict[str, list[dict[str, str]]]:
    """Cambios de cada dato de contacto en el tiempo (cada vez que el valor cambia)."""
    from identidades import grafo_residencial as gr

    ordenadas = filas.sort_values(["fecha_actualizacion", "unique_id"])
    salida: dict[str, list[dict[str, str]]] = {}
    for campo in CAMPOS_HISTORIA:
        cambios: list[dict[str, str]] = []
        for f in ordenadas.itertuples():
            valor = gr.normalizar_residencial(campo, getattr(f, campo))
            if campo == "direccion":
                from identidades.estandarizacion_v4 import normalizar_direccion_v4

                valor = normalizar_direccion_v4(getattr(f, campo))["direccion"]
            if valor is None or (cambios and cambios[-1]["valor"] == valor):
                continue
            cambios.append(
                {
                    "fecha": f.fecha_actualizacion,
                    "valor": valor,
                    "canal": f.canal,
                    "registro": int(f.unique_id),
                }
            )
        salida[campo] = cambios
    return salida


class Fichas:
    """El v4 y el grafo residencial congelados aplicados a un escenario, listos para fichas."""

    def __init__(self, registros: pd.DataFrame, escenario: str) -> None:
        from identidades import flujo_v11, modelo, puentes, registro_oro
        from identidades import grafo_residencial as gr

        self.registros = registros.reset_index(drop=True)
        self.escenario = escenario
        configuracion, self.umbral, esquema = flujo_v11.modelos_congelados()["v4"]
        linker = flujo.aplicar_configuracion(configuracion, self.registros, esquema)
        df_pred = modelo.predecir(linker)
        self.pred = df_pred.as_pandas_dataframe()
        df_clusters = modelo.agrupar(linker, df_pred, self.umbral)
        self.clusters = df_clusters.as_pandas_dataframe()
        self.cliente_de = self.clusters.set_index("unique_id")["cluster_id"]

        hito3 = json.loads(
            (rutas.DOCS_RESULTADOS_HITO3 / "metricas.json").read_text(encoding="utf-8")
        )
        self.reglas = hito3["registro_oro"]["reglas_elegidas_en_desarrollo"]
        politica = hito3["puentes"][str(UMBRAL_REVISION)]["politica_elegida_en_desarrollo"]
        self.politica = politica
        clusters_rev = modelo.agrupar(linker, df_pred, UMBRAL_REVISION)
        aristas = puentes.aristas_con_puentes(linker, df_pred, clusters_rev, UMBRAL_REVISION)
        self.debiles = puentes.puentes_debiles(aristas, politica["max_peso"], politica["min_lado"])

        grupos = gr.grupos_residenciales(self.registros, self.clusters)
        self.grupos = grupos.assign(
            prediccion=gr.clasificar(grupos, flujo_v11.cargar_clasificador()),
            cliente_de=[{i: self.cliente_de[i] for i in ids} for ids in grupos["ids_registros"]],
        )
        self.duenos = flujo_v11.duenos_de_documentos(self.grupos, self.registros)
        relleno = self.grupos[self.grupos["prediccion"] == "relleno"]
        relleno = {t: set(g["valor"]) for t, g in relleno.groupby("tipo")}
        cand = registro_oro.candidatos(self.registros, self.clusters, relleno)
        # La dirección se muestra con la estandarización v4 (predio y unidad).
        from identidades.estandarizacion_v4 import normalizar_direccion_v4

        texto = self.registros.set_index("unique_id")["direccion"]
        es_dir = cand["campo"] == "direccion"
        cand.loc[es_dir, "valor"] = cand.loc[es_dir, "unique_id"].map(
            lambda i: normalizar_direccion_v4(texto[i])["direccion"]
        )
        self.oro = oro_con_origen(cand, self.reglas)

    def nombre(self, cliente: int) -> str:
        oro = self.oro[(self.oro["cluster_id"] == cliente)].set_index("campo")["valor"]
        partes = [oro.get("nombres"), oro.get("apellidos")]
        return " ".join(p for p in partes if isinstance(p, str)) or f"Cliente {cliente}"

    def ficha(self, cliente: int, prefijo: str) -> dict[str, Any]:
        ids = sorted(self.clusters[self.clusters["cluster_id"] == cliente]["unique_id"])
        filas = self.registros[self.registros["unique_id"].isin(ids)]
        registros = [
            {
                "id": int(f["unique_id"]),
                **{k: _texto(f[c]) for k, c in COLUMNAS_REGISTRO.items()},
                "fecha": f["fecha_actualizacion"],
                "canal": f["canal"],
                "validado": bool(f["validado"]),
            }
            for _, f in filas.sort_values("fecha_actualizacion").iterrows()
        ]
        en = self.pred[self.pred["unique_id_l"].isin(ids) & self.pred["unique_id_r"].isin(ids)]
        enlaces = [
            [int(f.unique_id_l), int(f.unique_id_r), round(float(f.match_weight), 1)]
            for f in en.itertuples()
        ]
        oro = [
            {"campo": f.campo, "valor": f.valor, "origen": int(f.unique_id), "regla": f.regla}
            for f in self.oro[self.oro["cluster_id"] == cliente].itertuples()
        ]
        comparte, alertas = [], []
        for f in self.grupos[self.grupos["ids_clientes"].map(lambda c: cliente in c)].itertuples():
            otros = [c for c in f.ids_clientes if c != cliente]
            comparte.append(
                {
                    "tipo": f.tipo,
                    "valor": f.valor,
                    "categoria": f.prediccion,
                    "tipo_predio": f.tipo_predio if isinstance(f.tipo_predio, str) else None,
                    "clientes": [
                        {"id": f"{prefijo}{c}", "nombre": self.nombre(c)} for c in otros[:12]
                    ],
                    "mas": max(0, len(otros) - 12),
                }
            )
            if f.tipo == "documento":
                dueno = self.duenos.get(f.valor)
                papel = (
                    "este cliente es la víctima (dueño probable del documento)"
                    if dueno == cliente
                    else "este cliente usa un documento que sería de otro cliente"
                )
                alertas.append(
                    {
                        "tipo": "documento_compartido",
                        "texto": f"Documento {f.valor} compartido con {len(otros)} cliente(s): "
                        f"{papel}.",
                    }
                )
            elif f.prediccion == "sospechoso":
                alertas.append(
                    {
                        "tipo": "grupo_sospechoso",
                        "texto": f"Comparte {f.tipo} {f.valor} con {len(otros)} cliente(s) en un "
                        "patrón sospechoso.",
                    }
                )
        debiles = self.debiles[self.debiles["id_l"].isin(ids) | self.debiles["id_r"].isin(ids)]
        for f in debiles.itertuples():
            alertas.append(
                {
                    "tipo": "puente_debil",
                    "texto": f"Al umbral {UMBRAL_REVISION}, los registros {int(f.id_l)} y "
                    f"{int(f.id_r)} se unirían por un solo enlace de {f.match_weight:.1f} bits "
                    f"(menos de {self.politica['max_peso']:.0f}): revisar antes de unir.",
                }
            )
        return {
            "id": f"{prefijo}{cliente}",
            "nombre": self.nombre(cliente),
            "documento": next((o["valor"] for o in oro if o["campo"] == "documento"), None),
            "escenario": self.escenario,
            "registros": registros,
            "enlaces": enlaces,
            "oro": oro,
            "comparte": comparte,
            "historia": _historia(filas),
            "alertas": alertas,
        }


def _cliente_de_persona(f: Fichas, persona: int) -> int:
    ids = f.registros[f.registros["cluster"] == persona]["unique_id"]
    return int(f.cliente_de[ids].mode().iloc[0])


def exportar_fichas(directorio: Path, n_muestra: int = 130, semilla: int = 11) -> dict[str, Any]:
    """Datos de la página "Ficha de cliente único" (``docs/ficha.html``).

    Muestra del escenario residencial de prueba de la v1.1 (semilla 4141) con el v4 y el
    grafo residencial congelados, más el caso "Esther Nancy" del escenario del hito 3 (con
    la fecha del universo publicado en la v1.1). Ejemplos destacados: una familia, una
    pareja de un conjunto, una casa de varios pisos y el caso Esther.
    """
    import numpy as np

    from identidades import diagnostico_v11, escenario_hito3
    from identidades.escenario_residencial import EscenarioResidencial
    from identidades.sinteticos_fecha import forzar_fecha

    escenario = EscenarioResidencial(2000, flujo_v11.SEMILLA_RESIDENCIAL_PRUEBA)
    registros, personas, _ = escenario.generar()
    f = Fichas(registros, "Escenario residencial de prueba de la v1.1 (semilla 4141)")
    p = personas.set_index("cluster")

    con_direccion = {
        c
        for g in f.grupos[f.grupos["tipo"] == "direccion"].itertuples()
        if g.prediccion in ("hogar", "multifamiliar")
        for c in g.ids_clientes
    }

    def primero(filtro: pd.Series) -> int:
        candidatos = [
            c
            for c in p[filtro].index
            if (registros["cluster"] == c).sum() >= 3 and _cliente_de_persona(f, c) in con_direccion
        ]
        return candidatos[0]

    familia = primero((p["tipo_hogar"] == "familia") & (p["tipo_predio"] == "casa")
                      & (p["rol"] == "hijo"))  # fmt: skip
    pareja = primero((p["tipo_hogar"] == "pareja") & (p["tipo_predio"] == "conjunto")
                     & p["apellido_casada"].notna())  # fmt: skip
    pisos = primero(p["rol"] == "hijo_piso2")
    destacados_personas = {
        "Una familia (hijos con el apellido de cada padre)": familia,
        "Una pareja de un conjunto (apellido de casada)": pareja,
        "Una casa de varios pisos (el hijo vive arriba)": pisos,
    }
    clientes_destacados = {t: _cliente_de_persona(f, c) for t, c in destacados_personas.items()}

    # Muestra: los destacados, los clientes con quienes comparten datos, clientes con alertas
    # y otros al azar.
    elegidos: list[int] = list(clientes_destacados.values())
    for c in list(elegidos):
        for g in f.grupos[f.grupos["ids_clientes"].map(lambda ids, c=c: c in ids)].itertuples():
            elegidos += [x for x in g.ids_clientes if x not in elegidos][:6]
    alertas = f.grupos[(f.grupos["prediccion"] == "sospechoso")]
    for g in alertas.itertuples():
        elegidos += [x for x in g.ids_clientes if x not in elegidos][:3]
    for i in list(f.debiles["id_l"]) + list(f.debiles["id_r"]):
        if f.cliente_de[i] not in elegidos:
            elegidos.append(int(f.cliente_de[i]))
    rng = np.random.default_rng(semilla)
    resto = [c for c in f.clusters["cluster_id"].unique() if c not in elegidos]
    elegidos += list(rng.choice(resto, size=max(0, n_muestra - len(elegidos)), replace=False))
    fichas = {}
    for c in elegidos[: max(n_muestra, len(clientes_destacados))]:
        ficha = f.ficha(int(c), "r")
        fichas[ficha["id"]] = ficha

    # Caso Esther, del escenario del hito 3 con la fecha del universo de la v1.1.
    with forzar_fecha(*diagnostico_v11.FECHA_UNIVERSO_HITO3):
        reg_h3, _, _ = escenario_hito3.generar_escenario(2000, 3131)
    caso = diagnostico_v11.caso_esther()
    involucrados = sorted({r["persona_verdadera"] for r in caso["registros"]})
    ids_caso = {r["unique_id"] for r in caso["registros"]}
    personas_caso = set(reg_h3[reg_h3["unique_id"].isin(ids_caso)]["cluster"]) | set(involucrados)
    sub = reg_h3[reg_h3["cluster"].isin(personas_caso)]
    # Se agregan registros de contexto para que el modelo vea frecuencias razonables.
    contexto = reg_h3[~reg_h3["cluster"].isin(personas_caso)].sample(1500, random_state=semilla)
    fh = Fichas(
        pd.concat([sub, contexto]), "Escenario del hito 3 (semilla 3131, universo de la v1.1)"
    )
    esther = _cliente_de_persona(fh, caso["dueno_del_documento"][0])
    clientes_caso = sorted({_cliente_de_persona(fh, c) for c in involucrados})
    for c in clientes_caso:
        ficha = fh.ficha(c, "h")
        fichas[ficha["id"]] = ficha

    destacados = [{"titulo": t, "id": f"r{c}"} for t, c in clientes_destacados.items()] + [
        {"titulo": "El caso Esther (documento suplantado)", "id": f"h{esther}"}
    ]
    salida = {
        "meta": {
            "descripcion": "Muestra de fichas de cliente único con el modelo v4 y el grafo "
            "residencial congelados. Todos los datos son sintéticos.",
            "umbral": f.umbral,
            "umbral_revision": UMBRAL_REVISION,
            "reglas_supervivencia": f.reglas,
            "clientes": len(fichas),
        },
        "destacados": destacados,
        "clientes": fichas,
    }
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / "fichas.json").write_text(
        json.dumps(salida, ensure_ascii=False, separators=(",", ":"), default=str),
        encoding="utf-8",
        newline="\n",
    )
    return {"clientes": len(fichas), "destacados": destacados}
