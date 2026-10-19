"""Diagnóstico previo de la v1.1: cómo trata el grafo del hito 3 la realidad residencial.

Arma ejemplos pequeños y escritos a mano de cada caso que la v1.1 quiere cubrir (parejas
sin apellidos comunes, compañeros de apartamento, edificios y conjuntos, casas de varios
pisos) y los pasa por el grafo de identidad compartida del hito 3 sin cambiarlo, con los
parámetros que eligió el desarrollo publicado (``max_clientes`` 15, ``min_apellido`` 0,5).
Los clústeres son la verdad (cada persona, un cliente): así el diagnóstico mira solo el
clasificador, no el modelo de unión.

Todos los nombres, documentos, teléfonos y direcciones son inventados.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from identidades import estandarizacion as v1
from identidades import grafo_compartido

# Parámetros del clasificador publicados en docs/resultados/hito3/metricas.json.
PARAMETROS_PUBLICADOS = grafo_compartido.ParametrosClasificacion(max_clientes=15, min_apellido=0.5)

# (caso, persona, nombres, apellidos, documento, celular, dirección)
_PERSONAS: list[tuple[str, int, str, str, str, str, str]] = [
    # Pareja (unión libre) sin apellidos ni teléfono en común.
    ("pareja_sin_apellidos", 1, "Carlos Andrés", "Gómez Ruiz", "79811234", "3104567811",
     "Calle 45 # 12-30"),
    ("pareja_sin_apellidos", 2, "Diana Marcela", "Pérez López", "52944321", "3157788123",
     "Cl 45 # 12-30"),
    # Pareja casada: ella usa el apellido de casada ("Pérez de Gómez").
    ("pareja_casada", 3, "Jorge Iván", "Salazar Mora", "80123456", "3001112233",
     "Carrera 19 # 63-15"),
    ("pareja_casada", 4, "Luz Ángela", "Rincón de Salazar", "51987654", "3124445566",
     "Kr 19 # 63-15"),
    # Dos señoras casadas, sin relación entre ellas, que viven en el mismo edificio.
    ("vecinas_casadas", 5, "Martha Lucía", "Vargas de Ospina", "41555111", "3016667788",
     "Calle 100 # 15-20 Apto 401"),
    ("vecinas_casadas", 6, "Gloria Inés", "Cárdenas de Rojas", "41555222", "3209998877",
     "Calle 100 # 15-20 Apto 402"),
    # Tres estudiantes que comparten arriendo (mismo apartamento, escrito de dos formas).
    ("companeros_apto", 7, "Valentina", "Mejía Arango", "1020304050", "3011234567",
     "Carrera 7 # 40-62 Apto 502"),
    ("companeros_apto", 8, "Santiago", "Quintero Bedoya", "1030405060", "3027654321",
     "Carrera 7 # 40-62 Apto 502"),
    ("companeros_apto", 9, "Laura Sofía", "Castaño Pineda", "1040506070", "3139876543",
     "Cra 7 # 40-62 Ap 502"),
    # Conjunto residencial: seis hogares sin relación, distinguidos por torre y apartamento.
    ("conjunto", 10, "Andrea", "Moreno Silva", "1015111222", "3101010101",
     "Calle 140 # 9-50 Torre 1 Apto 101"),
    ("conjunto", 11, "Felipe", "Ortiz Lara", "1015333444", "3102020202",
     "Calle 140 # 9-50 Torre 1 Apto 302"),
    ("conjunto", 12, "Natalia", "Suárez Díaz", "1015555666", "3103030303",
     "Calle 140 # 9-50 Torre 2 Apto 204"),
    ("conjunto", 13, "Camilo", "Rojas Peña", "1015777888", "3104040404",
     "Cl 140 # 9-50 T 2 Ap 501"),
    ("conjunto", 14, "Paula", "Herrera Vélez", "1015999000", "3105050505",
     "Calle 140 # 9-50 Interior 3 Apto 201"),
    ("conjunto", 15, "Julián", "Cruz Patiño", "1016111222", "3106060606",
     "Calle 140 # 9-50"),
    # Casa de dos pisos ("le echaron la plancha"): padres abajo, hijo con su hogar arriba.
    ("casa_dos_pisos", 16, "Luis Alberto", "Hernández Castro", "17123456", "6017384512",
     "Calle 23 Sur # 5-10"),
    ("casa_dos_pisos", 17, "Rosa Elena", "Mejía de Hernández", "41123456", "6017384512",
     "Calle 23 Sur # 5-10"),
    ("casa_dos_pisos", 18, "Andrés Felipe", "Hernández Mejía", "1012345678", "3112223344",
     "Calle 23 Sur # 5-10 Piso 2"),
    ("casa_dos_pisos", 19, "Paola Andrea", "Rincón Díaz", "1023456789", "3115556677",
     "Calle 23 Sur # 5-10 Piso 2"),
    # La misma casa, pero el hijo escribe la dirección sin el piso.
    ("casa_dos_pisos_sin_piso", 20, "Hernando", "Galvis Rueda", "13456789", "3141112222",
     "Carrera 30 # 8-44"),
    ("casa_dos_pisos_sin_piso", 21, "Carmen", "Ochoa de Galvis", "37456789", "3143334444",
     "Carrera 30 # 8-44"),
    ("casa_dos_pisos_sin_piso", 22, "Diego", "Galvis Ochoa", "1098765432", "3145556666",
     "Carrera 30 # 8-44"),
    ("casa_dos_pisos_sin_piso", 23, "Yuliana", "Ramos Prada", "1098123456", "3147778888",
     "Carrera 30 # 8-44"),
    # Familia con la convención colombiana: hijos con el primer apellido de cada padre.
    ("familia_convencion", 24, "Jorge", "Ramírez Soto", "79456123", "3008889900",
     "Diagonal 48 # 22-15"),
    ("familia_convencion", 25, "Ana", "Torres Vélez", "52456123", "3009990011",
     "Dg 48 # 22-15"),
    ("familia_convencion", 26, "Camila", "Ramírez Torres", "1001456123", "3001231231",
     "Diagonal 48 # 22-15"),
    # Control: anillo de personas sin relación que comparten un celular (sí es sospechoso).
    ("anillo_control", 27, "Edwin", "Martínez Cano", "1088111222", "3183334455",
     "Calle 12 # 3-40"),
    ("anillo_control", 28, "Yesica", "Londoño Ríos", "1088333444", "3183334455",
     "Carrera 80 # 33-12"),
    ("anillo_control", 29, "Brayan", "Zapata Gil", "1088555666", "3183334455",
     "Transversal 5 # 61-07"),
]  # fmt: skip

# Qué esperaría un analista de cada caso: los compartidos son normales, salvo el control.
ESPERADO: dict[str, str] = {
    "pareja_sin_apellidos": "normal (pareja que convive)",
    "pareja_casada": "hogar (apellido de casada)",
    "vecinas_casadas": "normal (vecinas, apartamentos distintos)",
    "companeros_apto": "normal (convivencia)",
    "conjunto": "normal (mismo predio, hogares distintos)",
    "casa_dos_pisos": "hogar (familia en dos pisos)",
    "casa_dos_pisos_sin_piso": "hogar (familia en dos pisos)",
    "familia_convencion": "hogar (convención de apellidos)",
    "anillo_control": "sospechoso",
}


def registros_ejemplo() -> pd.DataFrame:
    """Un registro por persona, con las columnas del escenario del hito 3."""
    filas = [
        {
            "unique_id": persona,
            "caso": caso,
            "tipo_documento": "CC",
            "numero_documento": documento,
            "nombres": nombres,
            "apellidos": apellidos,
            "fecha_nacimiento": "1980-01-01",
            "celular": celular,
            "correo": None,
            "direccion": direccion,
            "ciudad": "BOGOTA",
            "departamento": "Bogotá, D.C.",
            "cluster": persona,
            "fecha_actualizacion": "2020-01-01",
            "canal": "sucursal",
            "validado": True,
            "origen": "normal",
        }
        for caso, persona, nombres, apellidos, documento, celular, direccion in _PERSONAS
    ]
    return pd.DataFrame(filas)


def direcciones_v1() -> list[dict[str, Any]]:
    """Cómo descompone la estandarización v1 cada dirección de los ejemplos."""
    salida = []
    for texto in dict.fromkeys(p[6] for p in _PERSONAS):
        d = v1.normalizar_direccion(texto)
        salida.append(
            {
                "texto": texto,
                "canonica": d["direccion"],
                "reconocida": d["via"] is not None,
                "generica_para_el_grafo": grafo_compartido.es_generico("direccion", texto),
            }
        )
    return salida


def grafo_anterior(
    registros: pd.DataFrame | None = None,
    parametros: grafo_compartido.ParametrosClasificacion = PARAMETROS_PUBLICADOS,
) -> pd.DataFrame:
    """Grupos del grafo del hito 3 sobre los ejemplos, con su clase y el caso de origen."""
    registros = registros_ejemplo() if registros is None else registros
    clusters = registros[["unique_id"]].assign(cluster_id=registros["cluster"])
    grupos = grafo_compartido.grupos_compartidos(registros, clusters)
    caso_de = registros.set_index("cluster")["caso"]
    grupos = grupos.assign(
        prediccion=grafo_compartido.clasificar(grupos, parametros),
        casos=grupos["ids_clientes"].map(lambda ids: sorted({caso_de[i] for i in ids})),
    )
    return grupos


def resumen_por_caso(registros: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    """Por caso: personas, grupos que forma el grafo anterior, su clase y lo esperado."""
    registros = registros_ejemplo() if registros is None else registros
    grupos = grafo_anterior(registros)
    salida = []
    for caso, esperado in ESPERADO.items():
        personas = registros[registros["caso"] == caso]
        propios = grupos[grupos["casos"].map(lambda c, k=caso: k in c)]
        en_grupo = {i for ids in propios["ids_clientes"] for i in ids}
        salida.append(
            {
                "caso": caso,
                "esperado": esperado,
                "personas": len(personas),
                "personas_en_algun_grupo": len(en_grupo & set(personas["cluster"])),
                "grupos": [
                    {
                        "tipo": f.tipo,
                        "valor": f.valor,
                        "clientes": f.clientes,
                        "frac_apellido_comun": round(f.frac_apellido_comun, 2),
                        "generico": bool(f.generico),
                        "clase": f.prediccion,
                    }
                    for f in propios.itertuples()
                ],
            }
        )
    return salida


# Pares de direcciones típicos de la realidad residencial y lo que significan.
PARES_DIRECCION: list[tuple[str, str, str]] = [
    ("misma casa, otra escritura", "Calle 45 # 12-30", "Cl 45 # 12-30"),
    ("mismo apartamento, otra escritura", "Carrera 7 # 40-62 Apto 502", "Cra 7 # 40-62 Ap 502"),
    ("mismo edificio, otro apartamento", "Calle 100 # 15-20 Apto 401",
     "Calle 100 # 15-20 Apto 402"),
    ("mismo conjunto, otra torre", "Calle 140 # 9-50 Torre 1 Apto 101",
     "Calle 140 # 9-50 Torre 2 Apto 204"),
    ("conjunto con y sin apartamento", "Calle 140 # 9-50 Torre 1 Apto 101", "Calle 140 # 9-50"),
    ("casa: primer piso y piso 2", "Calle 23 Sur # 5-10", "Calle 23 Sur # 5-10 Piso 2"),
    ("predios distintos en la misma cuadra", "Calle 45 # 12-30", "Calle 45 # 12-38"),
]  # fmt: skip


def niveles_direccion(
    configuracion: dict, preparar: Any, pares: list[tuple[str, str, str]] | None = None
) -> list[dict[str, Any]]:
    """Nivel y bits que da a la dirección un modelo guardado en cada par de direcciones.

    Prepara las direcciones con ``preparar`` (la del esquema del modelo) y evalúa en DuckDB
    los niveles de la comparación ``domicilio``. Los bits son log2(m/u) del nivel, sin el
    ajuste por frecuencia (que depende de toda la base).
    """
    import duckdb

    pares = pares or PARES_DIRECCION
    (domicilio,) = [
        c for c in configuracion["comparisons"] if c["output_column_name"] == "domicilio"
    ]
    niveles = [n for n in domicilio["comparison_levels"] if not n.get("is_null_level")]
    textos = list(dict.fromkeys(t for _, a, b in pares for t in (a, b)))
    base = pd.DataFrame(
        {
            "unique_id": range(len(textos)),
            "numero_documento": None, "nombres": "X", "apellidos": "Y",
            "fecha_nacimiento": "1980-01-01", "celular": None, "correo": None,
            "direccion": textos, "ciudad": "BOGOTA",
        }
    )  # fmt: skip
    preparado = preparar(base).set_index(base["direccion"])
    columnas = [
        c
        for c in ("domicilio", "domicilio_clave", "predio", "unidad", "unidad_partes")
        if c in preparado
    ]
    salida = []
    for descripcion, a, b in pares:
        fila = {}
        for c in columnas:
            for lado, texto in (("l", a), ("r", b)):
                valor = preparado.loc[texto, c]
                fila[f"{c}_{lado}"] = valor if isinstance(valor, list | str) else None
        tabla = pd.DataFrame([fila])  # noqa: F841 (lo lee DuckDB)
        for c in columnas:
            if c != "unidad_partes":
                tabla[[f"{c}_l", f"{c}_r"]] = tabla[[f"{c}_l", f"{c}_r"]].astype("string")
        for nivel in niveles:
            condicion = nivel["sql_condition"]
            if condicion.strip().upper() == "ELSE":
                break
            if duckdb.sql(f"select ({condicion}) as c from tabla").fetchone()[0]:
                break
        bits = math.log2(nivel["m_probability"] / nivel["u_probability"])
        salida.append(
            {
                "par": descripcion,
                "a": a,
                "b": b,
                "nivel": nivel.get("label_for_charts", nivel["sql_condition"]),
                "bits": round(bits, 2),
            }
        )
    return salida


def niveles_direccion_v3(configuracion: dict | None = None) -> list[dict[str, Any]]:
    """Nivel y bits que da a la dirección el v3 congelado en cada par típico."""
    from identidades import flujo_hito6, modelo_co_v2

    if configuracion is None:
        configuracion = flujo_hito6.cargar_congelado_v3()[0]
    return [
        {**{k: n[k] for k in ("par", "a", "b")}, "nivel_v3": n["nivel"], "bits_v3": n["bits"]}
        for n in niveles_direccion(configuracion, modelo_co_v2.preparar)
    ]


# Fecha en que se generó el universo del hito 3 de la v1.1 (commit 638ec65). Faker calculaba
# las fechas de nacimiento desde la fecha de hoy; desde la v1.1.1 los generadores usan
# HOY_FIJO, y ese escenario se reproduce forzando esta fecha.
FECHA_UNIVERSO_HITO3: tuple[int, int, int] = (2026, 10, 18)


def caso_esther(documento: str = "1064372368") -> dict[str, Any]:
    """Reconstruye el caso "Esther Nancy MONTENEGRO MUÑOZ" del universo publicado.

    Genera de nuevo el escenario de prueba del hito 3 (semilla 3131) con la fecha del
    universo publicado y devuelve los registros que llevan ``documento``, su origen en el
    escenario y la etiqueta verdadera del grupo.
    """
    from identidades import escenario_hito3
    from identidades.sinteticos_fecha import forzar_fecha

    with forzar_fecha(*FECHA_UNIVERSO_HITO3):
        registros, personas, verdad = escenario_hito3.generar_escenario(2000, 3131)
    clave = registros["numero_documento"].map(lambda v: escenario_hito3.normalizar("documento", v))
    filas = registros[clave == documento]
    duenos = personas[personas["documento"] == documento]["cluster"].tolist()
    etiqueta = verdad[(verdad["tipo"] == "documento") & (verdad["valor"] == documento)]
    return {
        "documento": documento,
        "dueno_del_documento": duenos,
        "registros": [
            {
                "unique_id": int(f.unique_id),
                "nombre": f"{f.nombres} {f.apellidos}",
                "persona_verdadera": int(f.cluster),
                "origen": f.origen,
                "canal": f.canal,
                "fecha_actualizacion": f.fecha_actualizacion,
                "papel": "víctima (dueña del documento)"
                if f.cluster in duenos
                else "suplantador (usa el documento de otra persona)",
            }
            for f in filas.itertuples()
        ],
        "etiqueta_verdadera_del_grupo": etiqueta["etiqueta"].tolist(),
    }
