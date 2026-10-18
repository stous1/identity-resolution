"""Auditoría 7: contraste de las cifras del README y de Pages con lo que producen los scripts.

Dos partes:

1. **Cifras publicadas contra los JSON publicados** (``docs/resultados``): cada cifra del
   README y de Pages se reconstruye desde el JSON con el mismo redondeo y se busca
   literalmente en el texto. Rápido; también lo corre ``audit/tests``.
2. **JSON publicados contra una ejecución nueva** de cada flujo (``rerun``): se vuelven a
   correr los flujos del proyecto en ``audit/_cache/rerun`` (sin capturas PNG) y se
   comparan todos los números con los publicados, salvo tiempos.

Uso: ``python audit/a7_afirmaciones.py [cifras] [rerun]``.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from identidades import rutas

import _comun as c

SALIDA = c.RESULTADOS / "a7_afirmaciones.json"
R = rutas.DOCS_RESULTADOS


def _j(ruta: Path) -> dict[str, Any]:
    return json.loads(ruta.read_text(encoding="utf-8"))


def d(v: float, n: int = 3) -> str:
    """Decimal con coma: 0,970."""
    return f"{v:.{n}f}".replace(".", ",")


def p(v: float, n: int = 1) -> str:
    """Porcentaje con coma; 100 sin decimales como en el README."""
    texto = f"{100 * v:.{n}f}".replace(".", ",")
    return "100" if texto in ("100,0", "100,00", "100") else texto


def s(v: float, n: int = 3, escala: float = 1.0) -> str:
    """Con signo: +0,015, −0,8, 0,000."""
    x = v * escala
    texto = f"{abs(x):.{n}f}".replace(".", ",")
    if texto.strip("0,") == "":
        return texto
    return ("+" if x > 0 else "−") + texto


def m(n: int) -> str:
    """Miles con punto: 1.262."""
    return f"{n:,}".replace(",", ".")


def ic(x: dict[str, float], fmt: Callable[[float], str] = d, sep: str = " – ") -> str:
    return f"{fmt(x['valor'])} [{fmt(x['ic_inf'])}{sep}{fmt(x['ic_sup'])}]"


def cifras() -> list[dict[str, Any]]:
    """(documento, texto esperado en el documento, texto reconstruido desde el JSON)."""
    h1 = _j(R / "metricas.json")
    h2 = _j(R / "hito2" / "metricas.json")
    va = _j(R / "validacion" / "metricas.json")
    hb = _j(R / "hito2b" / "metricas.json")
    hd = _j(R / "hito2b" / "desarrollo.json")
    h3 = _j(R / "hito3" / "metricas.json")
    tr = _j(R / "hito5" / "tiempo_real.json")
    e100 = _j(rutas.REPORTS_HITO5 / "escala_100000.json")
    e1m = _j(rutas.REPORTS_HITO5 / "escala_1000000.json")
    import csv

    sel = list(csv.DictReader(open(R / "seleccion_bloqueos.csv", encoding="utf-8")))
    comp = {
        f["candidato"]: f
        for f in csv.DictReader(open(R / "comparacion_bloqueos.csv", encoding="utf-8"))
    }
    esc = list(csv.DictReader(open(R / "hito5" / "escala.csv", encoding="utf-8")))

    pi, pc = h1["prueba"]["intervalos"]["pares"], h1["prueba"]["intervalos"]["clusters"]
    um = {u["criterio"]: u for u in h1["desarrollo"]["umbrales"]}
    e2 = h2["variantes"]["estandarizado"]
    cr = h2["variantes"]["crudo"]
    ap = h2["aporte_estandarizacion"]
    eq = h2["equidad"]["detalle"]
    ci = va["prueba_ciega"]
    ev = hb["evolucion_clusters"]
    mj = hb["mejora_v2_sobre_v1_en_ciega_2"]["clusters"]
    oro = h3["registro_oro"]
    pu = h3["puentes"]
    ce = pu["casos_externos"]
    gr = h3["grafo_compartido"]
    conf = gr["prueba"]["confusion"]

    def grupo(var: str, atributo: str, g: str, metrica: str) -> float:
        return eq[var][atributo]["clusters"]["grupos"][g][metrica]["valor"]

    def diag(atr: str, g: str) -> float:
        return ci["diagnostico_por_error"]["detalle"][atr]["clusters"]["grupos"][g][
            "pct_clusters_exactos"
        ]["valor"]

    def equ(atr: str, g: str) -> float:
        return ci["equidad"][atr]["clusters"]["grupos"][g]["pct_clusters_exactos"]["valor"]

    def dif_eq(atr: str, signo: float = -1) -> str:
        (x,) = ci["equidad"][atr]["clusters"]["diferencias"].values()
        y = x["pct_clusters_exactos"]
        lo, hi = sorted((signo * y["ic_inf"], signo * y["ic_sup"]))
        return f"{s(signo * y['valor'], 1, 100)} puntos [{s(lo, 1, 100)}, {s(hi, 1, 100)}]"

    def brecha(atr: str, momento: str) -> dict[str, float]:
        return hb["brechas"][atr][momento]

    def br_txt(atr: str, momento: str) -> str:
        y = brecha(atr, momento)["pct_clusters_exactos"]
        lo, hi = sorted((-y["ic_inf"], -y["ic_sup"]))
        return f"{s(-y['valor'], 1, 100)} [{s(lo, 1, 100)}, {s(hi, 1, 100)}]"

    def bg(atr: str, momento: str, g: str) -> str:
        return p(brecha(atr, momento)["grupos"][g]["pct_clusters_exactos"]["valor"])

    def esc_fila(n: str, etapa: str) -> dict[str, str]:
        return next(f for f in esc if f["registros"] == n and f["etapa"] == etapa)

    tasas = {k: v["valor"] for k, v in oro["prueba_con_reglas_elegidas"].items()}
    techo = oro["prueba_techo_alcanzable"]
    reglas = {"fuente_confiable": "Fuente más confiable", "mas_reciente": "Más reciente",
              "validado": "Validado más reciente", "frecuente": "Más frecuente"}  # fmt: skip
    campos = {"documento": "Documento", "nombres": "Nombres", "apellidos": "Apellidos",
              "fecha_nacimiento": "Fecha de nacimiento", "celular": "Celular",
              "correo": "Correo", "direccion": "Dirección"}  # fmt: skip
    oro_ic = oro["prueba_con_reglas_elegidas"]

    def oro_fila(k: str, con_ic: bool) -> str:
        x = oro_ic[k]
        valor = f"{p(x['valor'])} %"
        if con_ic and x["ic_inf"] < x["ic_sup"]:
            valor += f" [{p(x['ic_inf'])} – {p(x['ic_sup'])}]"
        return f"| {campos[k]} | {reglas[oro['reglas_elegidas_en_desarrollo'][k]]} | {valor} | {p(techo[k])} % |"

    t_ms = tr["latencia_ms"]
    total_1m = sum(
        float(esc_fila("995688", e)["segundos"])
        for e in ("Preparación", "Entrenamiento", "Predicción", "Agrupación")
    )
    filas: list[tuple[str, str, str]] = [
        # ---------------- Hito 1
        (
            "README",
            "desarrollo** (60 %: 151 personas, 608",
            f"desarrollo** (60 %: {h1['particion']['desarrollo']['personas']} personas, {h1['particion']['desarrollo']['registros']}",
        ),
        (
            "README",
            "**prueba** (40 %: 100 personas, 392",
            f"**prueba** (40 %: {h1['particion']['prueba']['personas']} personas, {h1['particion']['prueba']['registros']}",
        ),
        ("README", "(0,0055 en", f"({d(h1['modelo']['lambda_desarrollo'], 4)} en"),
        ("README", "0,0082 en prueba", f"{d(h1['modelo']['lambda_prueba'], 4)} en prueba"),
        ("README", "Umbral 0,83, elegido", f"Umbral {d(h1['umbral']['valor'], 2)}, elegido"),
        (
            "README",
            f"| Por par | {ic(pi['precision'])} | {ic(pi['recall'])} | {ic(pi['f1'])} |",
            f"| Por par | {ic(pi['precision'])} | {ic(pi['recall'])} | {ic(pi['f1'])} |",
        ),
        (
            "README",
            "| Por clúster (pares inducidos) | 0,970 [0,864 – 1,000] | 0,851 [0,790 – 0,903] | 0,907 [0,845 – 0,946] |",
            f"| Por clúster (pares inducidos) | {ic(pc['precision'])} | {ic(pc['recall'])} | {ic(pc['f1'])} |",
        ),
        (
            "README",
            "73 de 100 (73 % [64 % – 81 %]); 129 clústeres",
            f"{h1['prueba']['clusters']['clusters_exactos']} de {h1['prueba']['clusters']['clusters_reales']} ({p(pc['pct_clusters_exactos']['valor'], 0)} % [{p(pc['pct_clusters_exactos']['ic_inf'], 0)} % – {p(pc['pct_clusters_exactos']['ic_sup'], 0)} %]); {h1['prueba']['clusters']['clusters_predichos']} clústeres",
        ),
        (
            "README",
            "90,8 % de los 808 pares verdaderos de prueba llegan a compararse\n  (1.262 comparaciones)",
            f"{p(h1['prueba']['bloqueo']['recall_bloqueo'])} % de los {h1['prueba']['bloqueo']['pares_verdaderos']} pares verdaderos de prueba llegan a compararse\n  ({m(h1['prueba']['bloqueo']['pares_comparados'])} comparaciones)",
        ),
        ("README", "deja 21 pares", f"deja {h1['prueba']['clusters']['fp']} pares"),
        (
            "README",
            "| Desarrollo (donde se eligió todo) | 0,83 | 1,000 | 0,930 | 84 % |",
            f"| Desarrollo (donde se eligió todo) | {d(h1['umbral']['valor'], 2)} | {d(h1['desarrollo']['clusters']['precision'])} | {d(h1['desarrollo']['clusters']['recall'])} | {p(h1['desarrollo']['clusters']['pct_clusters_exactos'], 0)} % |",
        ),
        (
            "README",
            "| Todo el dataset (solo referencia, optimista) | 0,84 | 1,000 | 0,903 | 81 % |",
            f"| Todo el dataset (solo referencia, optimista) | {d(h1['referencia_todo_el_dataset']['umbral']['valor'], 2)} | {d(h1['referencia_todo_el_dataset']['clusters']['precision'])} | {d(h1['referencia_todo_el_dataset']['clusters']['recall'])} | {p(h1['referencia_todo_el_dataset']['clusters']['pct_clusters_exactos'], 0)} % |",
        ),
        (
            "README",
            "el 18,6 % de los pares verdaderos de desarrollo nunca se compara",
            f"el {p(1 - float(sel[0]['recall_bloqueo']))} % de los pares verdaderos de desarrollo nunca se compara",
        ),
        *[
            (
                "README",
                f"| {i} | {nombre} | {m(int(sel[i]['pares_comparados']))} | {d(float(sel[i]['recall_bloqueo']))} |",
                f"| {i} | {nombre} | {m(int(sel[i]['pares_comparados']))} | {d(float(sel[i]['recall_bloqueo']))} |",
            )
            for i, nombre in enumerate(
                [
                    "Exactas",
                    "Primeros 4 caracteres del correo",
                    "Soundex del apellido",
                    "Ciudad + año de nacimiento",
                ]
            )
            if i < len(sel)
        ],
        ("README", "seleccion_bloqueos.csv: 4 pasos", f"seleccion_bloqueos.csv: {len(sel)} pasos"),
        (
            "README",
            "Con las 12 reglas el recall del bloqueo en desarrollo llega a 0,930, pero con 3.547\ncomparaciones y el mismo recall por clúster (0,930)",
            f"Con las {comp['todas']['reglas']} reglas el recall del bloqueo en desarrollo llega a {d(float(comp['todas']['recall_bloqueo']))}, pero con {m(int(comp['todas']['pares_comparados']))}\ncomparaciones y el mismo recall por clúster ({d(float(comp['todas']['recall_cluster']))})",
        ),
        *[
            (
                "README",
                f"| {etq} | {d(um[k]['umbral'], 2)} | {d(um[k]['clusters']['precision'])} | {d(um[k]['clusters']['recall'])} | {m(int(um[k]['costo_clusters']))} |",
                f"| {etq} | {d(um[k]['umbral'], 2)} | {d(um[k]['clusters']['precision'])} | {d(um[k]['clusters']['recall'])} | {m(int(um[k]['costo_clusters']))} |",
            )
            for k, etq in (
                ("fijo", "Fijo"),
                ("max_f1_par", "Mejor F1 por par"),
                ("min_costo_par", "Menor costo por par"),
            )
        ],
        (
            "README",
            "| **Menor costo por clúster (en uso)** | **0,83** | **1,000** | **0,930** | **86** |",
            f"| **Menor costo por clúster (en uso)** | **{d(um['min_costo_cluster']['umbral'], 2)}** | **{d(um['min_costo_cluster']['clusters']['precision'])}** | **{d(um['min_costo_cluster']['clusters']['recall'])}** | **{int(um['min_costo_cluster']['costo_clusters'])}** |",
        ),
        (
            "README",
            "454 pares de registros quedan juntos por error",
            f"{um['max_f1_par']['clusters']['fp']} pares de registros quedan juntos por error",
        ),
        (
            "index.md",
            "| Por clúster | 0,970 [0,864 – 1,000] | 0,851 [0,790 – 0,903] | 0,907 [0,845 – 0,946] |",
            f"| Por clúster | {ic(pc['precision'])} | {ic(pc['recall'])} | {ic(pc['f1'])} |",
        ),
        (
            "index.md",
            "(precisión\n1,000 y recall 0,903 por clúster)",
            f"(precisión\n{d(h1['referencia_todo_el_dataset']['clusters']['precision'])} y recall {d(h1['referencia_todo_el_dataset']['clusters']['recall'])} por clúster)",
        ),
        # ---------------- Hito 2
        (
            "README",
            "2.000 personas y 4.851\nregistros",
            f"{m(h2['datos']['personas'])} personas y {m(h2['datos']['registros'])}\nregistros",
        ),
        (
            "README",
            "(1.200\npersonas, 2.920 registros) y métricas en prueba (800 personas, 1.931 registros)",
            f"({m(h2['particion']['desarrollo']['personas'])}\npersonas, {m(h2['particion']['desarrollo']['registros'])} registros) y métricas en prueba ({h2['particion']['prueba']['personas']} personas, {m(h2['particion']['prueba']['registros'])} registros)",
        ),
        (
            "README",
            "| **Estandarizado** | 0,999999 | **1,000** [1,000 – 1,000] | **0,998** [0,993 – 1,000] | **99,8 %** [99,4 – 100] | 0,994 [0,989 – 0,998] |",
            "| **Estandarizado** | {u} | **{a}** [{b} – {cc}] | **{dd}** [{e} – {f}] | **{g} %** [{hh} – {i}] | {j} |".format(
                u=str(e2["umbral"]["valor"]).replace(".", ","),
                a=d(e2["prueba"]["intervalos"]["clusters"]["precision"]["valor"]),
                b=d(e2["prueba"]["intervalos"]["clusters"]["precision"]["ic_inf"]),
                cc=d(e2["prueba"]["intervalos"]["clusters"]["precision"]["ic_sup"]),
                dd=d(e2["prueba"]["intervalos"]["clusters"]["recall"]["valor"]),
                e=d(e2["prueba"]["intervalos"]["clusters"]["recall"]["ic_inf"]),
                f=d(e2["prueba"]["intervalos"]["clusters"]["recall"]["ic_sup"]),
                g=p(e2["prueba"]["intervalos"]["clusters"]["pct_clusters_exactos"]["valor"]),
                hh=p(e2["prueba"]["intervalos"]["clusters"]["pct_clusters_exactos"]["ic_inf"]),
                i=p(e2["prueba"]["intervalos"]["clusters"]["pct_clusters_exactos"]["ic_sup"]),
                j=ic(e2["prueba"]["intervalos"]["pares"]["recall"]),
            ),
        ),
        (
            "README",
            "| Sin estandarizar | 0,98 | 0,989 [0,960 – 1,000] | 0,983 [0,975 – 0,990] | 96,1 % [94,8 – 97,4] | 0,907 [0,893 – 0,921] |",
            "| Sin estandarizar | {u} | {a} | {b} | {g} % [{hh} – {i}] | {j} |".format(
                u=d(cr["umbral"]["valor"], 2),
                a=ic(cr["prueba"]["intervalos"]["clusters"]["precision"]),
                b=ic(cr["prueba"]["intervalos"]["clusters"]["recall"]),
                g=p(cr["prueba"]["intervalos"]["clusters"]["pct_clusters_exactos"]["valor"]),
                hh=p(cr["prueba"]["intervalos"]["clusters"]["pct_clusters_exactos"]["ic_inf"]),
                i=p(cr["prueba"]["intervalos"]["clusters"]["pct_clusters_exactos"]["ic_sup"]),
                j=ic(cr["prueba"]["intervalos"]["pares"]["recall"]),
            ),
        ),
        (
            "README",
            "| Recall por clúster | +0,015 | [+0,006, +0,024] | Sí |",
            f"| Recall por clúster | {s(ap['clusters']['recall']['valor'])} | [{s(ap['clusters']['recall']['ic_inf'])}, {s(ap['clusters']['recall']['ic_sup'])}] | Sí |",
        ),
        (
            "README",
            "| Personas exactas | +3,6 puntos | [+2,4, +5,0] | Sí |",
            f"| Personas exactas | {s(ap['clusters']['pct_clusters_exactos']['valor'], 1, 100)} puntos | [{s(ap['clusters']['pct_clusters_exactos']['ic_inf'], 1, 100)}, {s(ap['clusters']['pct_clusters_exactos']['ic_sup'], 1, 100)}] | Sí |",
        ),
        (
            "README",
            "| Recall por par | +0,087 | [+0,073, +0,102] | Sí |",
            f"| Recall por par | {s(ap['pares']['recall']['valor'])} | [{s(ap['pares']['recall']['ic_inf'])}, {s(ap['pares']['recall']['ic_sup'])}] | Sí |",
        ),
        (
            "README",
            "| Precisión por clúster | +0,011 | [0,000, +0,040] | No |",
            f"| Precisión por clúster | {s(ap['clusters']['precision']['valor'])} | [{s(ap['clusters']['precision']['ic_inf'])}, {s(ap['clusters']['precision']['ic_sup'])}] | No |",
        ),
        (
            "README",
            "solo cubre el 82 % de los pares verdaderos en desarrollo\n(frente al 99 % estandarizado)",
            f"solo cubre el {p(cr['desarrollo']['seleccion_bloqueos'][0]['recall_bloqueo'], 0)} % de los pares verdaderos en desarrollo\n(frente al {p(e2['desarrollo']['seleccion_bloqueos'][0]['recall_bloqueo'], 0)} % estandarizado)",
        ),
        (
            "README",
            "Además, 24 pares de registros",
            f"Además, {cr['prueba']['clusters']['fp']} pares de registros",
        ),
        *[
            (
                "README",
                f"| {etq} ({n}) | {d(grupo('estandarizado', a, g, 'recall'))} | {p(grupo('estandarizado', a, g, 'pct_clusters_exactos'))} % | {d(grupo('crudo', a, g, 'recall'))} | {p(grupo('crudo', a, g, 'pct_clusters_exactos'))} % |",
                f"| {etq} ({eq['estandarizado'][a]['clusters']['grupos'][g]['personas']}) | {d(grupo('estandarizado', a, g, 'recall'))} | {p(grupo('estandarizado', a, g, 'pct_clusters_exactos'))} % | {d(grupo('crudo', a, g, 'recall'))} | {p(grupo('crudo', a, g, 'pct_clusters_exactos'))} % |",
            )
            for etq, n, a, g in (
                ("Nombre simple", 457, "nombre_compuesto", "nombre simple"),
                ("Nombre compuesto", 343, "nombre_compuesto", "nombre compuesto"),
                ("Dos apellidos", 667, "dos_apellidos", "dos apellidos"),
                ("Un apellido", 133, "dos_apellidos", "un apellido"),
                ("Con tilde o ñ", 548, "con_tilde", "con tilde o ñ"),
                ("Sin tilde", 252, "con_tilde", "sin tilde"),
            )
        ],
        (
            "README",
            "(95,0 % frente a 96,9 %)",
            f"({p(grupo('crudo', 'nombre_compuesto', 'nombre compuesto', 'pct_clusters_exactos'))} % frente a {p(grupo('crudo', 'nombre_compuesto', 'nombre simple', 'pct_clusters_exactos'))} %)",
        ),
        (
            "README",
            "(+1,9 puntos, IC [−0,8, +4,7])",
            "({} puntos, IC [{}, {}])".format(
                *(
                    s(
                        eq["crudo"]["nombre_compuesto"]["clusters"]["diferencias"][
                            "nombre simple - nombre compuesto"
                        ]["pct_clusters_exactos"][k],
                        1,
                        100,
                    )
                    for k in ("valor", "ic_inf", "ic_sup")
                )
            ),
        ),
        (
            "README",
            "deja todavía 4 pares",
            f"deja todavía {next(u for u in e2['desarrollo']['umbrales'] if u['criterio'] == 'min_costo_cluster')['clusters']['fp']} pares",
        ),
        (
            "hito2.md",
            "La estandarización suma +1,5 puntos de recall",
            f"La estandarización suma {s(ap['clusters']['recall']['valor'], 1, 100)} puntos de recall",
        ),
        # ---------------- Validación
        (
            "README",
            "(6.032\n   registros, otra semilla)",
            f"({m(ci['datos']['registros'])}\n   registros, otra semilla)",
        ),
        *[
            (
                "README",
                f"| {etq} | {ic(x['precision'])} | {ic(x['recall'])} | {ic(x['f1'])} | {p(x['pct_clusters_exactos']['valor'])} % [{p(x['pct_clusters_exactos']['ic_inf'])} – {p(x['pct_clusters_exactos']['ic_sup'])}] |",
                f"| {etq} | {ic(x['precision'])} | {ic(x['recall'])} | {ic(x['f1'])} | {p(x['pct_clusters_exactos']['valor'])} % [{p(x['pct_clusters_exactos']['ic_inf'])} – {p(x['pct_clusters_exactos']['ic_sup'])}] |",
            )
            for etq, x in (
                (
                    "Prueba normal del hito 2 (800 personas)",
                    va["tres_cifras_clusters"]["prueba normal (hito 2)"],
                ),
                ("FEBRL3 (800 personas)", va["tres_cifras_clusters"]["FEBRL3"]),
            )
        ],
        (
            "README",
            "| **Prueba ciega (2.000 personas)** | **0,997** [0,987 – 1,000] | **0,636** [0,616 – 0,657] | **0,777** [0,762 – 0,792] | **60,2 %** [58,1 – 62,3] |",
            "| **Prueba ciega (2.000 personas)** | **{}** [{} – {}] | **{}** [{} – {}] | **{}** [{} – {}] | **{} %** [{} – {}] |".format(
                *[
                    d(va["tres_cifras_clusters"]["prueba ciega"][k][q])
                    for k in ("precision", "recall", "f1")
                    for q in ("valor", "ic_inf", "ic_sup")
                ],
                *[
                    p(va["tres_cifras_clusters"]["prueba ciega"]["pct_clusters_exactos"][q])
                    for q in ("valor", "ic_inf", "ic_sup")
                ],
            ),
        ),
        (
            "README",
            "(3.128 clústeres para 2.000\n  personas)",
            f"({m(ci['prueba']['clusters']['clusters_predichos'])} clústeres para {m(ci['prueba']['clusters']['clusters_reales'])}\n  personas)",
        ),
        (
            "README",
            "a umbral 0,5 el recall sube a 0,807, pero la precisión cae a\n  0,803",
            f"a umbral 0,5 el recall sube a {d(ci['diagnostico_otros_umbrales']['clusters'][0]['recall'])}, pero la precisión cae a\n  {d(ci['diagnostico_otros_umbrales']['clusters'][0]['precision'])}",
        ),
        (
            "README",
            "nombres en otro campo 29,7 % (frente a 62,8 %), documento alterado 45,4 % (frente a\n  63,4 %) y celular cambiado por un fijo 49,1 % (frente a 61,5 %)",
            f"nombres en otro campo {p(diag('nombres_cruzados', 'nombres en otro campo'))} % (frente a {p(diag('nombres_cruzados', 'nombres en su campo'))} %), documento alterado {p(diag('documento_alterado', 'documento alterado'))} % (frente a\n  {p(diag('documento_alterado', 'documento sin alterar'))} %) y celular cambiado por un fijo {p(diag('celular_fijo', 'celular cambiado por fijo'))} % (frente a {p(diag('celular_fijo', 'con celular'))} %)",
        ),
        (
            "README",
            "| Apellido de casada (136) | 41,2 % | 61,5 % sin él | −20,4 puntos [−29,1, −11,4] | **Sí** |",
            f"| Apellido de casada ({ci['equidad']['apellido_casada']['clusters']['grupos']['apellido de casada']['personas']}) | {p(equ('apellido_casada', 'apellido de casada'))} % | {p(equ('apellido_casada', 'sin apellido de casada'))} % sin él | {dif_eq('apellido_casada')} | **Sí** |",
        ),
        (
            "README",
            "| Con apodo (337) | 49,3 % | 62,4 % sin apodo | −13,1 puntos [−19,0, −7,4] | **Sí** |",
            f"| Con apodo ({ci['equidad']['con_apodo']['clusters']['grupos']['con apodo']['personas']}) | {p(equ('con_apodo', 'con apodo'))} % | {p(equ('con_apodo', 'sin apodo'))} % sin apodo | {dif_eq('con_apodo')} | **Sí** |",
        ),
        (
            "README",
            "| Nombre compuesto (788) | 61,8 % | 59,1 % simple | +2,7 [−1,3, +7,1] | No |",
            f"| Nombre compuesto ({ci['equidad']['nombre_compuesto']['clusters']['grupos']['nombre compuesto']['personas']}) | {p(equ('nombre_compuesto', 'nombre compuesto'))} % | {p(equ('nombre_compuesto', 'nombre simple'))} % simple | {dif_eq('nombre_compuesto').replace(' puntos', '')} | No |",
        ),
        (
            "README",
            "| Un apellido (301) | 59,1 % | 60,3 % con dos | −1,2 [−7,0, +4,5] | No |",
            f"| Un apellido ({ci['equidad']['dos_apellidos']['clusters']['grupos']['un apellido']['personas']}) | {p(equ('dos_apellidos', 'un apellido'))} % | {p(equ('dos_apellidos', 'dos apellidos'))} % con dos | {dif_eq('dos_apellidos').replace(' puntos', '')} | No |",
        ),
        (
            "README",
            "| Sin tilde (634) | 59,6 % | 60,4 % con tilde | −0,8 [−5,6, +3,9] | No |",
            f"| Sin tilde ({ci['equidad']['con_tilde']['clusters']['grupos']['sin tilde']['personas']}) | {p(equ('con_tilde', 'sin tilde'))} % | {p(equ('con_tilde', 'con tilde o ñ'))} % con tilde | {dif_eq('con_tilde').replace(' puntos', '')} | No |",
        ),
        (
            "README",
            "| Dirección rural (135) | 59,3 % | 60,2 % urbana | −1,0 [−9,9, +7,5] | No |",
            f"| Dirección rural ({ci['equidad']['rural']['clusters']['grupos']['dirección rural']['personas']}) | {p(equ('rural', 'dirección rural'))} % | {p(equ('rural', 'dirección urbana'))} % urbana | {dif_eq('rural').replace(' puntos', '')} | No |",
        ),
        (
            "README",
            "(5.000 registros de 2.000 personas)",
            f"({m(va['febrl3']['particion']['desarrollo']['registros'] + va['febrl3']['particion']['prueba']['registros'])} registros de {m(va['febrl3']['particion']['desarrollo']['personas'] + va['febrl3']['particion']['prueba']['personas'])} personas)",
        ),
        # ---------------- Hito 2b
        (
            "README",
            "eligieron el bloqueo y el umbral (0,9999)",
            f"eligieron el bloqueo y el umbral ({str(hd['umbral']['valor']).replace('.', ',')})",
        ),
        *[
            (
                "README",
                f"| {etq} | {ic(ev[k]['precision'])} | {ic(ev[k]['recall'])} | {p(ev[k]['pct_clusters_exactos']['valor'])} % |",
                f"| {etq} | {ic(ev[k]['precision'])} | {ic(ev[k]['recall'])} | {p(ev[k]['pct_clusters_exactos']['valor'])} % |",
            )
            for etq, k in (
                ("Prueba normal · modelo v1", "prueba normal · modelo v1"),
                ("Prueba normal · modelo v2", "prueba normal · modelo v2"),
                ("Ciega 1 · modelo v1", "ciega 1 · modelo v1"),
                ("Ciega 2 · modelo v1 (control)", "ciega 2 · modelo v1 (control)"),
            )
        ],
        (
            "README",
            "| Ciega 1 · modelo v2 (*es desarrollo: optimista*) | 1,000 | 1,000 | 100 % |",
            f"| Ciega 1 · modelo v2 (*es desarrollo: optimista*) | {d(ev['ciega 1 · modelo v2 (desarrollo)']['precision']['valor'])} | {d(ev['ciega 1 · modelo v2 (desarrollo)']['recall']['valor'])} | {p(ev['ciega 1 · modelo v2 (desarrollo)']['pct_clusters_exactos']['valor'])} % |",
        ),
        (
            "README",
            "| **Ciega 2 · modelo v2** | **0,998** [0,994 – 1,000] | **1,000** [1,000 – 1,000] | **99,7 %** [99,5 – 99,9] |",
            "| **Ciega 2 · modelo v2** | **{}** [{} – {}] | **{}** [{} – {}] | **{} %** [{} – {}] |".format(
                *[
                    d(ev["ciega 2 · modelo v2"][k][q])
                    for k in ("precision", "recall")
                    for q in ("valor", "ic_inf", "ic_sup")
                ],
                *[
                    p(ev["ciega 2 · modelo v2"]["pct_clusters_exactos"][q])
                    for q in ("valor", "ic_inf", "ic_sup")
                ],
            ),
        ),
        (
            "README",
            "| Recall | +0,080 | [+0,068, +0,093] | Sí |",
            f"| Recall | {s(mj['recall']['valor'])} | [{s(mj['recall']['ic_inf'])}, {s(mj['recall']['ic_sup'])}] | Sí |",
        ),
        (
            "README",
            "| Personas exactas | +8,6 puntos | [+7,4, +9,8] | Sí |",
            f"| Personas exactas | {s(mj['pct_clusters_exactos']['valor'], 1, 100)} puntos | [{s(mj['pct_clusters_exactos']['ic_inf'], 1, 100)}, {s(mj['pct_clusters_exactos']['ic_sup'], 1, 100)}] | Sí |",
        ),
        (
            "README",
            "| Precisión | +0,004 | [−0,003, +0,021] | No |",
            f"| Precisión | {s(mj['precision']['valor'])} | [{s(mj['precision']['ic_inf'])}, {s(mj['precision']['ic_sup'])}] | No |",
        ),
        (
            "README",
            "Quedan 3 uniones erróneas (1.997 clústeres para 2.000 personas)",
            f"Quedan {hb['ciega_2']['clusters']['clusters_reales'] - hb['ciega_2']['clusters']['clusters_predichos']} uniones erróneas ({m(hb['ciega_2']['clusters']['clusters_predichos'])} clústeres para {m(hb['ciega_2']['clusters']['clusters_reales'])} personas)",
        ),
        (
            "README",
            "(15 pares\n  faltantes en vez de 5)",
            f"({hb['prueba_normal_hito2']['clusters']['fn']} pares\n  faltantes en vez de {e2['prueba']['clusters']['fn']})",
        ),
        (
            "README",
            "| Con apellido de casada | 41,2 % | 92,0 % | 100 % |",
            f"| Con apellido de casada | {bg('apellido_casada', 'antes (ciega 1, modelo v1)', 'apellido de casada')} % | {bg('apellido_casada', 'control (ciega 2, modelo v1)', 'apellido de casada')} % | {bg('apellido_casada', 'después (ciega 2, modelo v2)', 'apellido de casada')} % |",
        ),
        (
            "README",
            "| Sin apellido de casada | 61,5 % | 91,0 % | 99,7 % |",
            f"| Sin apellido de casada | {bg('apellido_casada', 'antes (ciega 1, modelo v1)', 'sin apellido de casada')} % | {bg('apellido_casada', 'control (ciega 2, modelo v1)', 'sin apellido de casada')} % | {bg('apellido_casada', 'después (ciega 2, modelo v2)', 'sin apellido de casada')} % |",
        ),
        (
            "README",
            "| **Brecha** | **−20,4 puntos [−29,1, −11,4]** | +1,0 [−2,5, +4,4] | +0,3 [+0,1, +0,6] |",
            f"| **Brecha** | **{br_txt('apellido_casada', 'antes (ciega 1, modelo v1)').replace(' [', ' puntos [')}** | {br_txt('apellido_casada', 'control (ciega 2, modelo v1)')} | {br_txt('apellido_casada', 'después (ciega 2, modelo v2)')} |",
        ),
        (
            "README",
            "| Con apodo | 49,3 % | 90,8 % | 100 % |",
            f"| Con apodo | {bg('con_apodo', 'antes (ciega 1, modelo v1)', 'con apodo')} % | {bg('con_apodo', 'control (ciega 2, modelo v1)', 'con apodo')} % | {bg('con_apodo', 'después (ciega 2, modelo v2)', 'con apodo')} % |",
        ),
        (
            "README",
            "| Sin apodo | 62,4 % | 91,1 % | 99,7 % |",
            f"| Sin apodo | {bg('con_apodo', 'antes (ciega 1, modelo v1)', 'sin apodo')} % | {bg('con_apodo', 'control (ciega 2, modelo v1)', 'sin apodo')} % | {bg('con_apodo', 'después (ciega 2, modelo v2)', 'sin apodo')} % |",
        ),
        (
            "README",
            "| **Brecha** | **−13,1 puntos [−19,0, −7,4]** | −0,3 [−4,5, +3,8] | +0,3 [+0,1, +0,6] |",
            f"| **Brecha** | **{br_txt('con_apodo', 'antes (ciega 1, modelo v1)').replace(' [', ' puntos [')}** | {br_txt('con_apodo', 'control (ciega 2, modelo v1)')} | {br_txt('con_apodo', 'después (ciega 2, modelo v2)')} |",
        ),
        (
            "hito2b.md",
            "**+8,0 puntos de recall y\n+8,6 de personas exactas**",
            f"**{s(mj['recall']['valor'], 1, 100)} puntos de recall y\n{s(mj['pct_clusters_exactos']['valor'], 1, 100)} de personas exactas**",
        ),
        # ---------------- Hito 3
        (
            "README",
            "(semilla 3131, 2.000 personas, 4.839\nregistros)",
            f"(semilla {h3['escenarios']['prueba']['semilla']}, {m(h3['escenarios']['prueba']['personas'])} personas, {m(h3['escenarios']['prueba']['registros'])}\nregistros)",
        ),
        (
            "README",
            "(en prueba: precisión\n1,000 y recall 0,998 por clúster)",
            f"(en prueba: precisión\n{d(h3['calidad_union']['prueba']['precision'])} y recall {d(h3['calidad_union']['prueba']['recall'])} por clúster)",
        ),
        *[("README", oro_fila(k, True), oro_fila(k, True)) for k in campos],
        (
            "README",
            "documento 92,1 % y nombres 89,4 %",
            f"documento {p(oro['prueba_por_regla']['mas_reciente']['documento']['valor'])} % y nombres {p(oro['prueba_por_regla']['mas_reciente']['nombres']['valor'])} %",
        ),
        (
            "README",
            "Las reglas elegidas quedan a\nmenos de 5 puntos de ese techo",
            "Las reglas elegidas quedan a\nmenos de {} puntos de ese techo".format(
                5
                if max(techo[k] - tasas[k] for k in campos) < 0.05
                else f"FALLA({max(techo[k] - tasas[k] for k in campos):.3f})"
            ),
        ),
        (
            "README",
            "o lo comparten más de 15\n   clientes",
            f"o lo comparten más de {gr['parametros_elegidos_en_desarrollo']['max_clientes']}\n   clientes",
        ),
        (
            "README",
            "los 432 grupos quedan bien clasificados (386 de hogar, 36 sospechosos y 10 de\nrelleno); en desarrollo, la exactitud fue 98,4 %",
            f"los {gr['prueba']['grupos']} grupos quedan bien clasificados ({conf['hogar']['hogar']} de hogar, {conf['sospechoso']['sospechoso']} sospechosos y {conf['relleno']['relleno']} de\nrelleno); en desarrollo, la exactitud fue {p(gr['desarrollo']['exactitud'])} %",
        ),
        *[
            (
                "README",
                f"| {etq} | {pol} | {x['mezclados_antes']} → {x['mezclados_despues']} | {x['fp_antes']} → {x['fp_despues']} | {x['recall_perdido']:.0f} |",
                f"| {etq} | {pol} | {x['mezclados_antes']} → {x['mezclados_despues']} | {x['fp_antes']} → {x['fp_despues']} | {x['recall_perdido']:.0f} |",
            )
            for etq, pol, x in (
                ("0,9999 (congelado)", "No cortar", pu["0.9999"]["prueba"]),
                (
                    "0,99",
                    f"Cortar puentes con peso < {pu['0.99']['prueba']['max_peso']:.0f}",
                    pu["0.99"]["prueba"],
                ),
                (
                    "0,9",
                    f"Cortar puentes con peso < {pu['0.9']['prueba']['max_peso']:.0f}",
                    pu["0.9"]["prueba"],
                ),
            )
        ],
        (
            "README",
            "segundo puente más débil de 35 (peso 2,5, une 3 registros)",
            f"segundo puente más débil de {ce['hito1_109_844']['puentes_totales']} (peso {d(ce['hito1_109_844']['match_weight'], 1)}, une {ce['hito1_109_844']['lado_menor']} registros)",
        ),
        (
            "README",
            "(pesos 13,8, 16,9 y 20,9)",
            "(pesos {})".format(
                ", ".join(
                    d(x, 1)
                    for x in sorted(
                        ce["ciega2_modelo_v2_sostenidas_por_puente"]["pesos_de_esos_puentes"]
                    )
                ).rsplit(", ", 1)[0]
                + " y "
                + d(
                    sorted(ce["ciega2_modelo_v2_sostenidas_por_puente"]["pesos_de_esos_puentes"])[
                        -1
                    ],
                    1,
                )
            ),
        ),
        (
            "README",
            "7 uniones sostenidas por un puente débil (al umbral 0,9) y 36 grupos\nsospechosos (12 documentos, 11 correos, 7 direcciones y 6 celulares compartidos)",
            "{} uniones sostenidas por un puente débil (al umbral 0,9) y {} grupos\nsospechosos ({} documentos, {} correos, {} direcciones y {} celulares compartidos)".format(
                h3["cola_revision"].get("puente_debil", 0),
                sum(v for k, v in h3["cola_revision"].items() if k.startswith("grupo_sospechoso")),
                *(
                    h3["cola_revision"].get(f"grupo_sospechoso_{t}", 0)
                    for t in ("documento", "correo", "direccion", "celular")
                ),
            ),
        ),
        # ---------------- Hito 5
        (
            "README",
            "Base de 1.351 clientes (3.000 personas sintéticas) y 2.000 consultas, 1.000 de clientes\nexistentes",
            f"Base de {m(tr['base']['clientes'])} clientes (3.000 personas sintéticas) y {m(tr['consultas'])} consultas, {m(tr['existentes'])} de clientes\nexistentes",
        ),
        (
            "README",
            "| 0,999 (0,997 – 1,000) | 0,993 (0,987 – 0,998) | 0 | 60 ms | 74 ms |",
            f"| {d(tr['precision']['valor'])} ({d(tr['precision']['ic_inf'])} – {d(tr['precision']['ic_sup'])}) | {d(tr['recall']['valor'])} ({d(tr['recall']['ic_inf'])} – {d(tr['recall']['ic_sup'])}) | {tr['cliente_equivocado']} | {t_ms['mediana']:.0f} ms | {t_ms['p95']:.0f} ms |",
        ),
        (
            "README",
            "993 quedan como nuevas, 6 van a revisión y 1 se confunde",
            f"{tr['decisiones']['nuevas'].get('nuevo', 0)} quedan como nuevas, {tr['decisiones']['nuevas'].get('revisar', 0)} van a revisión y {tr['decisiones']['nuevas'].get('cliente', 0)} se confunde",
        ),
        (
            "hito5.md",
            "(1.351 clientes, a partir de 2.916 registros)",
            f"({m(tr['base']['clientes'])} clientes, a partir de {m(tr['base']['registros_usados'])} registros)",
        ),
        (
            "hito5.md",
            "| Cliente equivocado | 0 de 994 | |",
            f"| Cliente equivocado | {tr['cliente_equivocado']} de {sum(v.get('cliente', 0) for v in tr['decisiones'].values())} | |",
        ),
        (
            "hito5.md",
            "| Latencia máxima | 162 ms | |",
            f"| Latencia máxima | {t_ms['maxima']:.0f} ms | |",
        ),
        (
            "hito5.md",
            "| cliente | 993 | 1 |\n| revisar | 0 | 6 |\n| nuevo | 7 | 993 |",
            "| cliente | {} | {} |\n| revisar | {} | {} |\n| nuevo | {} | {} |".format(
                *(
                    tr["decisiones"][g].get(k, 0)
                    for k in ("cliente", "revisar", "nuevo")
                    for g in ("existentes", "nuevas")
                )
            ),
        ),
        *[
            (
                "README",
                f"| {m(int(n))} | {d(float(esc_fila(n, 'Preparación')['segundos']), 1)} s | {d(float(esc_fila(n, 'Entrenamiento')['segundos']), 1)} s | {d(float(esc_fila(n, 'Predicción')['segundos']), 1)} s | {d(float(esc_fila(n, 'Agrupación')['segundos']), 1)} s |",
                f"| {m(int(n))} | {d(float(esc_fila(n, 'Preparación')['segundos']), 1)} s | {d(float(esc_fila(n, 'Entrenamiento')['segundos']), 1)} s | {d(float(esc_fila(n, 'Predicción')['segundos']), 1)} s | {d(float(esc_fila(n, 'Agrupación')['segundos']), 1)} s |",
            )
            for n in ("99088", "995688")
        ],
        (
            "README",
            "| 1,5 GB | 0,982 | 0,997 |",
            f"| {d(max(x['memoria_pico_gb'] for x in e100['mediciones']), 1)} GB | {d(e100['calidad']['precision'])} | {d(e100['calidad']['recall'])} |",
        ),
        (
            "README",
            "| **9,1 GB** | 0,971 | 0,996 |",
            f"| **{d(max(x['memoria_pico_gb'] for x in e1m['mediciones']), 1)} GB** | {d(e1m['calidad']['precision'])} | {d(e1m['calidad']['recall'])} |",
        ),
        (
            "README",
            "91 de 134 s",
            f"{float(esc_fila('995688', 'Preparación')['segundos']):.0f} de {total_1m:.0f} s",
        ),
        (
            "hito5.md",
            "| 99.088 | 0,982 | 0,997 | 97,8 % |",
            f"| 99.088 | {d(e100['calidad']['precision'])} | {d(e100['calidad']['recall'])} | {p(e100['calidad']['pct_clusters_exactos'])} % |",
        ),
        (
            "hito5.md",
            "| 995.688 | 0,971 | 0,996 | 96,6 % |",
            f"| 995.688 | {d(e1m['calidad']['precision'])} | {d(e1m['calidad']['recall'])} | {p(e1m['calidad']['pct_clusters_exactos'])} % |",
        ),
        (
            "hito5.md",
            "**200 mil registros** (240 mil enlaces",
            f"**{round(e1m['universo']['puntos'] / 1000)} mil registros** ({round(e1m['universo']['enlaces'] / 1000):.0f} mil enlaces",
        ),
        (
            "index.md",
            "1 millón de registros en DuckDB en 134 s con 9,1 GB de pico",
            f"1 millón de registros en DuckDB en {total_1m:.0f} s con {d(max(x['memoria_pico_gb'] for x in e1m['mediciones']), 1)} GB de pico",
        ),
        (
            "index.md",
            "con precisión 0,999, recall 0,993 y 60 ms de mediana",
            f"con precisión {d(tr['precision']['valor'])}, recall {d(tr['recall']['valor'])} y {t_ms['mediana']:.0f} ms de mediana",
        ),
    ]
    textos = {
        "README": (rutas.RAIZ / "README.md").read_text(encoding="utf-8"),
        **{f.name: f.read_text(encoding="utf-8") for f in rutas.DOCS.glob("*.md")},
    }
    resultado = []
    for doc, esperado, construido in filas:
        if esperado.startswith("seleccion_bloqueos.csv"):
            resultado.append({"documento": "datos", "cifra": esperado, "desde_json": construido,
                              "coincide": esperado == construido, "en_documento": True})  # fmt: skip
            continue
        texto = textos[doc]
        # Los saltos de línea del README son de ajuste de párrafo: se comparan como espacios.
        plano = " ".join(texto.split())
        resultado.append({
            "documento": doc,
            "cifra": esperado,
            "desde_json": construido,
            "coincide": " ".join(esperado.split()) == " ".join(construido.split()),
            "en_documento": " ".join(esperado.split()) in plano,
        })  # fmt: skip
    return resultado


# ------------------------------------------------------------------------- 2. reejecución


IGNORAR = (
    "segundos",
    "milisegundos",
    "latencia",
    "mediana",
    "p95",
    "maxima",
    "commit",
    "linker_uid",
)


def comparar_json(a: Any, b: Any, ruta: str = "", tol: float = 1e-9) -> list[dict[str, Any]]:
    """Diferencias numéricas o de texto entre dos JSON (publicado ``a``, nuevo ``b``)."""
    if any(k in ruta for k in IGNORAR):
        return []
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in set(a) | set(b):
            if k not in a or k not in b:
                out.append(
                    {
                        "ruta": f"{ruta}/{k}",
                        "publicado": a.get(k, "<falta>"),
                        "nuevo": b.get(k, "<falta>"),
                    }
                )
            else:
                out += comparar_json(a[k], b[k], f"{ruta}/{k}", tol)
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [
                {"ruta": ruta, "publicado": f"lista de {len(a)}", "nuevo": f"lista de {len(b)}"}
            ]
        return [
            x
            for i, (p_, q) in enumerate(zip(a, b, strict=True))
            for x in comparar_json(p_, q, f"{ruta}[{i}]", tol)
        ]
    if isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        if math.isclose(a, b, rel_tol=tol, abs_tol=tol):
            return []
        return [{"ruta": ruta, "publicado": a, "nuevo": b}]
    return [] if a == b else [{"ruta": ruta, "publicado": a, "nuevo": b}]


def rerun() -> dict[str, Any]:
    from identidades import (
        datos,
        flujo,
        flujo_hito2,
        flujo_hito2b,
        flujo_hito3,
        flujo_hito5,
        flujo_validacion,
    )

    base = c.CACHE / "rerun"
    resultado = {}

    def correr(nombre: str, funcion: Callable[[Path], Any], publicados: dict[str, Path]) -> None:
        directorio = base / nombre
        directorio.mkdir(parents=True, exist_ok=True)
        funcion(directorio)
        resultado[nombre] = {}
        for archivo, ruta_pub in publicados.items():
            difs = comparar_json(_j(ruta_pub), _j(directorio / archivo))
            resultado[nombre][archivo] = {"diferencias": len(difs), "ejemplos": difs[:15]}
            print(f"[rerun] {nombre}/{archivo}: {len(difs)} diferencias", flush=True)
        c.guardar_json(resultado, c.RESULTADOS / "a7_rerun.json")

    correr(
        "hito1",
        lambda d_: flujo.ejecutar_hito1(datos.cargar_fake_1000(), d_, capturas=False),
        {"metricas.json": R / "metricas.json"},
    )
    correr(
        "hito2",
        lambda d_: flujo_hito2.ejecutar_hito2(d_, capturas=False),
        {
            "metricas.json": R / "hito2" / "metricas.json",
            "modelo.json": R / "hito2" / "modelo.json",
        },
    )
    correr(
        "validacion",
        lambda d_: flujo_validacion.ejecutar_validacion(d_, capturas=False),
        {"metricas.json": R / "validacion" / "metricas.json"},
    )
    correr(
        "hito2b_desarrollo",
        flujo_hito2b.desarrollar_v2,
        {
            "desarrollo.json": R / "hito2b" / "desarrollo.json",
            "modelo.json": R / "hito2b" / "modelo.json",
        },
    )
    correr(
        "hito2b_evaluacion",
        lambda d_: flujo_hito2b.evaluar_congelado_v2(d_, capturas=False),
        {"metricas.json": R / "hito2b" / "metricas.json"},
    )
    correr("hito3", flujo_hito3.ejecutar_hito3, {"metricas.json": R / "hito3" / "metricas.json"})
    correr(
        "hito5",
        lambda d_: flujo_hito5.ejecutar_tiempo_real(d_),
        {"tiempo_real.json": R / "hito5" / "tiempo_real.json"},
    )
    return resultado


def main() -> None:
    pasos = sys.argv[1:] or ["cifras"]
    if "cifras" in pasos:
        filas = cifras()
        malas = [f for f in filas if not (f["coincide"] and f["en_documento"])]
        c.guardar_json({"total": len(filas), "con_problema": len(malas), "detalle": filas}, SALIDA)
        print(f"{len(filas)} cifras revisadas; {len(malas)} con problema")
        for f in malas:
            print(json.dumps(f, ensure_ascii=False))
    if "rerun" in pasos:
        rerun()


if __name__ == "__main__":
    main()
