"""Grafo de identidad compartida residencial (v1.1).

Como el grafo del hito 3 (``grafo_compartido``, que no cambia), cada valor que aparece en
dos o más clientes forma un grupo. Cambian tres cosas, por lo que encontró el diagnóstico
de la v1.1:

1. **La dirección se agrupa por predio** (``estandarizacion_v4``): los vecinos de un
   edificio o conjunto quedan en el mismo grupo, y una dirección con apartamento ya no es
   relleno. Dentro del grupo se miran las unidades de cada cliente.
2. **Señales de hogar** entre dos clientes: apellido propio en común (sin partículas como
   "DE"), apellido de casada ("Rincón de Salazar" con "Salazar Mora"), la convención
   colombiana de los hijos (un hijo "Ramírez Torres" conecta a "Ramírez" y "Torres", que
   serían sus padres) y compartir además un teléfono o un correo.
3. **La sospecha depende del tipo de dato, del tamaño y del tipo de predio.** Un documento
   compartido siempre es sospechoso. Un contacto o una dirección compartidos lo son si el
   grupo tiene la forma de un anillo (registros recientes, por canal digital, sin validar,
   en un valor que los clientes casi no usan en sus otros registros) o si es demasiado
   grande para lo normal en su tipo de predio. Se estima el tipo de predio (casa, casa de
   varios pisos, edificio o conjunto) con las unidades que aparecen.

Clases: ``relleno``, ``sospechoso``, ``hogar``, ``convivencia`` (convivencia probable:
grupo pequeño que comparte solo la dirección, sin otras señales) y ``multifamiliar``
(varios hogares en el mismo predio). Los parámetros se eligen en desarrollo.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import asdict, dataclass

import jellyfish
import numpy as np
import pandas as pd

from identidades import estandarizacion as v1
from identidades import estandarizacion_v2 as v2
from identidades.escenario_hito3 import CANALES_DIGITALES, TIPOS_COMPARTIDOS
from identidades.estandarizacion_v4 import es_direccion_generica, normalizar_direccion_v4
from identidades.grafo_compartido import es_generico

CLASES: tuple[str, ...] = ("relleno", "sospechoso", "hogar", "convivencia", "multifamiliar")
UMBRAL_APELLIDO: float = 0.88
TIPOS_PREDIO: tuple[str, ...] = ("casa", "casa_pisos", "edificio", "conjunto")

# Predicciones aceptables para cada etiqueta verdadera. Una pareja sin otra señal que la
# dirección no se distingue de dos compañeros de apartamento: "hogar" o "convivencia".
ACEPTABLES: dict[str, set[str]] = {
    "relleno": {"relleno"},
    "sospechoso": {"sospechoso"},
    "hogar": {"hogar"},
    "pareja": {"hogar", "convivencia"},
    "convivencia": {"convivencia"},
    "multifamiliar": {"multifamiliar"},
    "coincidencia": {"relleno", "hogar", "convivencia", "multifamiliar"},
    "misma_persona": set(CLASES),
}
BENIGNAS: tuple[str, ...] = ("hogar", "pareja", "convivencia", "multifamiliar", "coincidencia")


@dataclass(frozen=True)
class ParametrosGrafo:
    """Umbrales del clasificador (se eligen en desarrollo)."""

    max_convivencia: int = 4  # convivencia probable: hasta tantos clientes sin otra señal
    max_casa: int = 6  # en una casa (sin unidades), más clientes sin parentesco es raro
    max_por_unidad: int = 6  # en un apartamento o piso
    min_familia: float = 0.75  # fracción de clientes conectados por señales de hogar
    anillo_max_validado: float = 0.25
    anillo_min_digital: float = 0.75
    anillo_max_exclusividad: float = 0.6
    max_contacto: int = 6  # un teléfono o correo en más clientes es relleno


# ---------- Normalización y señales por cliente ----------


def normalizar_residencial(tipo: str, valor: object) -> str | None:
    """Clave del valor para agrupar: la dirección por predio; lo demás, como el hito 3."""
    if tipo == "celular":
        telefonos = v2.extraer_telefonos(valor)
        return telefonos[0] if telefonos else None
    if tipo == "correo":
        return v1.normalizar_correo(valor)
    if tipo == "direccion":
        d = normalizar_direccion_v4(v2.reparar_codificacion(valor))
        return d["predio"] or d["direccion"]
    if tipo == "documento":
        return v2.limpiar_documento(valor)
    raise ValueError(tipo)


def apellidos_cliente(apellidos: object) -> tuple[list[str], str | None]:
    """Apellidos propios (sin partículas) y apellido de casada de un registro."""
    texto = v1.quitar_tildes(v1.normalizar_nombre(v2.reparar_codificacion(apellidos)))
    propios, casada = v2.separar_apellido_casada(texto)
    palabras = [p for p in (propios or "").split() if p not in v1.PARTICULAS and len(p) > 1]
    return palabras[:2], casada


def _parecido(a: str, b: str) -> bool:
    return jellyfish.jaro_winkler_similarity(a, b) >= UMBRAL_APELLIDO


@dataclass
class Cliente:
    """Lo que se sabe de un cliente para las señales de hogar."""

    primeros: set[str]
    segundos: set[str]
    casada: set[str]

    @property
    def propios(self) -> set[str]:
        return self.primeros | self.segundos


def clientes_desde(base: pd.DataFrame) -> dict[int, Cliente]:
    """Apellidos de cada cliente (``cluster_id``) en todos sus registros."""
    salida: dict[int, Cliente] = {}
    for cid, g in base.groupby("cluster_id"):
        primeros, segundos, casada = set(), set(), set()
        for propios, cas in g["_apellidos"]:
            if propios:
                primeros.add(propios[0])
            if len(propios) > 1:
                segundos.add(propios[1])
            if cas:
                casada.add(cas)
        salida[cid] = Cliente(primeros, segundos, casada)
    return salida


def senales_hogar(ids: list[int], clientes: dict[int, Cliente]) -> dict[str, set]:
    """Aristas de parentesco entre los clientes de un grupo, por tipo de señal."""
    aristas: dict[str, set] = {"apellido": set(), "casada": set(), "convencion": set()}
    vacio = Cliente(set(), set(), set())
    for a, b in itertools.combinations(ids, 2):
        ca, cb = clientes.get(a, vacio), clientes.get(b, vacio)
        if any(_parecido(x, y) for x in ca.propios for y in cb.propios):
            aristas["apellido"].add((a, b))
        if any(_parecido(x, y) for x in ca.casada for y in cb.primeros) or any(
            _parecido(x, y) for x in cb.casada for y in ca.primeros
        ):
            aristas["casada"].add((a, b))
    # Convención: el hijo h lleva el primer apellido de a y, de segundo, el primero de b.
    for h in ids:
        ch = clientes.get(h, vacio)
        if not ch.primeros or not ch.segundos:
            continue
        padres = [
            a
            for a in ids
            if a != h
            and any(_parecido(x, y) for x in ch.primeros for y in clientes.get(a, vacio).primeros)
        ]
        madres = [b for b in ids if b != h and any(_parecido(x, y)
                  for x in ch.segundos for y in clientes.get(b, vacio).primeros)]  # fmt: skip
        for a, b in itertools.product(padres, madres):
            if a != b:
                aristas["convencion"].add(tuple(sorted((a, b))))
    return aristas


def _componentes(ids: list[int], aristas: set) -> list[set[int]]:
    padre = {i: i for i in ids}

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for a, b in aristas:
        padre[raiz(a)] = raiz(b)
    grupos: dict[int, set[int]] = {}
    for i in ids:
        grupos.setdefault(raiz(i), set()).add(i)
    return sorted(grupos.values(), key=len, reverse=True)


# ---------- Grupos y sus rasgos ----------


def _preparar_base(registros: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    base = registros.merge(clusters[["unique_id", "cluster_id"]], on="unique_id")
    fecha = pd.to_datetime(base["fecha_actualizacion"])
    unidades = base["direccion"].map(
        lambda v: normalizar_direccion_v4(v2.reparar_codificacion(v))["unidad"]
    )
    return base.assign(
        fecha=fecha,
        _apellidos=base["apellidos"].map(apellidos_cliente),
        _unidad=unidades,
        digital=base["canal"].isin(CANALES_DIGITALES),
    )


def estimar_tipo_predio(unidades: list[str | None], componentes_familia: int, clientes: int) -> str:
    """Tipo de predio por las unidades que aparecen en sus registros.

    Torre, bloque, interior o casa numerada: conjunto. Solo apartamentos: edificio. Pisos,
    o varias familias sin unidades en un mismo predio: casa de varios pisos. Si no: casa.
    """
    partes = {p[:2] for u in unidades if isinstance(u, str) for p in u.split()}
    if partes & {"TO", "BL", "IN", "CA"}:
        return "conjunto"
    if "AP" in partes:
        return "edificio"
    if "PI" in partes or (componentes_familia >= 2 and clientes >= 4):
        return "casa_pisos"
    return "casa"


def grupos_residenciales(
    registros: pd.DataFrame,
    clusters: pd.DataFrame,
    normalizador: Callable[[str, object], str | None] = normalizar_residencial,
) -> pd.DataFrame:
    """Un renglón por valor compartido por dos o más clientes, con sus rasgos."""
    base = _preparar_base(registros, clusters)
    clientes = clientes_desde(base)
    registros_por_cliente = base.groupby("cluster_id").size()
    claves = {
        tipo: base[columna].map(lambda v, t=tipo: normalizador(t, v))
        for tipo, columna in TIPOS_COMPARTIDOS.items()
    }
    # Clientes que comparten un teléfono o un correo (para "otras señales" en la dirección).
    pares_contacto: set[tuple[int, int]] = set()
    for tipo in ("celular", "correo"):
        for valor, g in base.assign(valor=claves[tipo]).dropna(subset=["valor"]).groupby("valor"):
            ids = sorted(set(g["cluster_id"]))
            if 2 <= len(ids) <= 6 and not es_generico(tipo, valor):
                pares_contacto |= set(itertools.combinations(ids, 2))
    fin = base["fecha"].max()
    # Predios de cada cliente (para saber si los que comparten un contacto viven juntos).
    predios_cliente = (
        base.assign(predio=claves["direccion"])
        .dropna(subset=["predio"])
        .groupby("cluster_id")["predio"]
        .agg(set)
    )

    def frac_coresidentes(ids: list[int]) -> float:
        conteo = pd.Series([p for c in ids for p in predios_cliente.get(c, set())]).value_counts()
        return float(conteo.iloc[0] / len(ids)) if len(conteo) else 0.0

    filas = []
    for tipo in TIPOS_COMPARTIDOS:
        con_valor = base.assign(valor=claves[tipo]).dropna(subset=["valor"])
        for valor, g in con_valor.groupby("valor"):
            ids = sorted(set(g["cluster_id"]))
            if len(ids) < 2:
                continue
            muestra = ids[:40]
            aristas = senales_hogar(muestra, clientes)
            contacto = {p for p in itertools.combinations(muestra, 2) if p in pares_contacto}
            familia = aristas["apellido"] | aristas["casada"] | aristas["convencion"]
            comps = _componentes(muestra, familia | (contacto if tipo == "direccion" else set()))
            comps_familia = _componentes(muestra, familia)
            unidades_cliente = (
                g.groupby("cluster_id")["_unidad"].agg(lambda s: set(s.dropna()))
                if tipo == "direccion"
                else pd.Series(dtype=object)
            )
            por_unidad = pd.Series(
                [u for us in unidades_cliente for u in us], dtype=object
            ).value_counts()
            exclusividad = float(
                np.mean([(g["cluster_id"] == c).sum() / registros_por_cliente[c] for c in ids])
            )
            generico = (
                es_direccion_generica(valor) if tipo == "direccion" else es_generico(tipo, valor)
            )
            filas.append(
                {
                    "tipo": tipo,
                    "valor": valor,
                    "clientes": len(ids),
                    "registros": len(g),
                    "ids_clientes": ids,
                    "ids_registros": sorted(g["unique_id"]),
                    "generico": bool(generico),
                    "frac_validado": float(g["validado"].mean()),
                    "frac_digital": float(g["digital"].mean()),
                    "dias": int((g["fecha"].max() - g["fecha"].min()).days),
                    "recientes": float((g["fecha"] >= fin - pd.Timedelta(days=540)).mean()),
                    "exclusividad": exclusividad,
                    "frac_familia": len(comps[0]) / len(muestra),
                    "frac_familia_estricta": len(comps_familia[0]) / len(muestra),
                    "componentes_familia": sum(1 for c in comps_familia if len(c) >= 2),
                    "senal_apellido": len(aristas["apellido"]),
                    "senal_casada": len(aristas["casada"]),
                    "senal_convencion": len(aristas["convencion"]),
                    "senal_contacto": len(contacto),
                    "frac_coresidentes": frac_coresidentes(muestra),
                    "unidades": int(len(por_unidad)),
                    "clientes_sin_unidad": int(sum(1 for us in unidades_cliente if not us)),
                    "max_por_unidad": int(por_unidad.max()) if len(por_unidad) else 0,
                    "tipo_predio": estimar_tipo_predio(
                        list(g["_unidad"]), sum(1 for c in comps_familia if len(c) >= 2), len(ids)
                    )
                    if tipo == "direccion"
                    else None,
                }
            )
    return pd.DataFrame(filas)


# ---------- Clasificación ----------


def es_anillo(fila: pd.Series | dict, p: ParametrosGrafo) -> bool:
    """Forma de anillo: registros sin validar, por canal digital, en un valor que los
    clientes casi no usan en sus otros registros."""
    return (
        fila["frac_validado"] <= p.anillo_max_validado
        and fila["frac_digital"] >= p.anillo_min_digital
        and fila["exclusividad"] <= p.anillo_max_exclusividad
    )


def clasificar_fila(f: pd.Series | dict, p: ParametrosGrafo) -> str:
    """Clase de un grupo, con reglas explicables (en orden)."""
    if f["tipo"] == "documento":
        return "sospechoso"
    if f["generico"]:
        return "relleno"
    familia = f["frac_familia"] >= p.min_familia
    if f["tipo"] in ("celular", "correo"):
        if f["clientes"] > p.max_contacto:
            return "relleno"
        if es_anillo(f, p) and not familia:
            return "sospechoso"
        if familia:
            return "hogar"
        # Personas sin parentesco visible que viven en el mismo predio y comparten un fijo o
        # un correo: un hogar o una convivencia, no un anillo.
        return "convivencia" if f["frac_coresidentes"] >= p.min_familia else "sospechoso"
    # Dirección (agrupada por predio).
    if es_anillo(f, p) and not familia:
        return "sospechoso"
    tipo_predio = f["tipo_predio"]
    if tipo_predio in ("edificio", "conjunto"):
        if f["unidades"] >= 2:
            # Varias unidades: varios hogares, salvo que todos sean una misma familia.
            return "hogar" if f["frac_familia_estricta"] >= 1.0 else "multifamiliar"
        # Todos en la misma unidad (o sin unidad): como una casa, con su propio máximo.
        if familia:
            return "hogar"
        if f["clientes"] <= p.max_convivencia:
            return "convivencia"
        return "sospechoso" if f["clientes"] > p.max_por_unidad else "multifamiliar"
    if familia:
        return "hogar"
    if tipo_predio == "casa_pisos":
        return "multifamiliar" if f["clientes"] <= 2 * p.max_casa else "sospechoso"
    if f["clientes"] <= p.max_convivencia:
        return "convivencia"
    return "sospechoso" if f["clientes"] > p.max_casa else "multifamiliar"


def clasificar(grupos: pd.DataFrame, p: ParametrosGrafo) -> pd.Series:
    if grupos.empty:
        return pd.Series(dtype=object)
    return grupos.apply(lambda f: clasificar_fila(f, p), axis=1)


# ---------- Evaluación ----------


def unir_verdad(grupos: pd.DataFrame, verdad: pd.DataFrame) -> pd.DataFrame:
    """Agrega la etiqueta verdadera; un grupo que la verdad no tiene es ``misma_persona``."""
    unidos = grupos.merge(verdad[["tipo", "valor", "etiqueta"]], on=["tipo", "valor"], how="left")
    return unidos.assign(etiqueta=unidos["etiqueta"].fillna("misma_persona"))


def aceptable(etiqueta: str, prediccion: str) -> bool:
    return prediccion in ACEPTABLES.get(etiqueta, set())


def metricas(clasificados: pd.DataFrame) -> dict:
    """Exactitud (con predicciones aceptables), exactitud balanceada, sospecha y confusión.

    - ``exactitud``: fracción de grupos con una predicción aceptable para su etiqueta;
    - ``exactitud_balanceada``: el promedio de esa fracción por etiqueta verdadera (sin
      ``misma_persona``);
    - ``sospechoso``: precisión y recall de la clase sospechoso;
    - ``falsa_sospecha``: por etiqueta benigna, fracción de grupos marcados sospechosos.
    """
    c = clasificados
    if c.empty:
        return {"grupos": 0}
    ok = np.array([aceptable(e, p) for e, p in zip(c["etiqueta"], c["prediccion"], strict=True)])
    por_etiqueta = {
        e: {
            "grupos": int((c["etiqueta"] == e).sum()),
            "aciertos": float(ok[(c["etiqueta"] == e).to_numpy()].mean()),
        }
        for e in sorted(set(c["etiqueta"]))
    }
    evaluables = [e for e in por_etiqueta if e != "misma_persona"]
    pred_s = c["prediccion"] == "sospechoso"
    real_s = c["etiqueta"] == "sospechoso"
    benignas = c["etiqueta"].isin(BENIGNAS)
    confusion = pd.crosstab(c["etiqueta"], c["prediccion"])
    return {
        "grupos": len(c),
        "exactitud": float(ok.mean()),
        "exactitud_balanceada": float(np.mean([por_etiqueta[e]["aciertos"] for e in evaluables])),
        "por_etiqueta": por_etiqueta,
        "sospechoso": {
            "reales": int(real_s.sum()),
            "predichos": int(pred_s.sum()),
            "precision": float((pred_s & real_s).sum() / pred_s.sum()) if pred_s.sum() else 0.0,
            "recall": float((pred_s & real_s).sum() / real_s.sum()) if real_s.sum() else 0.0,
        },
        "falsa_sospecha": {
            "benignos": int(benignas.sum()),
            "marcados": int((benignas & pred_s).sum()),
            "tasa": float((benignas & pred_s).sum() / benignas.sum()) if benignas.sum() else 0.0,
            "por_etiqueta": {
                e: float(pred_s[c["etiqueta"] == e].mean())
                for e in BENIGNAS
                if (c["etiqueta"] == e).any()
            },
        },
        "confusion": {r: confusion.loc[r].to_dict() for r in confusion.index},
    }


def personas_marcadas(
    clasificados: pd.DataFrame, clusters: pd.DataFrame, registros: pd.DataFrame
) -> dict:
    """Personas verdaderas que quedan en un grupo sospechoso sin estar en un patrón
    sospechoso (falsa sospecha por persona) y personas de patrones sospechosos detectadas.
    """
    persona_de = registros.set_index("unique_id")["cluster"]
    sospechosos = clasificados[clasificados["prediccion"] == "sospechoso"]
    reales = clasificados[clasificados["etiqueta"] == "sospechoso"]
    compartidas = clasificados[clasificados["etiqueta"].isin(BENIGNAS)]

    def personas(tabla: pd.DataFrame) -> set:
        return {persona_de[i] for ids in tabla["ids_registros"] for i in ids}

    en_patron = personas(reales)
    marcadas = personas(sospechosos)
    benignas = personas(compartidas) - en_patron
    return {
        "personas_en_grupos_benignos": len(benignas),
        "inocentes_marcadas": len(benignas & marcadas),
        "tasa_inocentes_marcadas": len(benignas & marcadas) / len(benignas) if benignas else 0.0,
        "personas_en_patrones": len(en_patron),
        "detectadas": len(en_patron & marcadas),
        "recall_personas": len(en_patron & marcadas) / len(en_patron) if en_patron else 0.0,
    }


def intervalos(
    clasificados: pd.DataFrame, n: int = 1000, semilla: int = 0, nivel: float = 0.95
) -> dict:
    """Intervalos por bootstrap de grupos: exactitud, recall de sospechosos y falsa sospecha."""
    rng = np.random.default_rng(semilla)
    c = clasificados
    ok = np.array([aceptable(e, p) for e, p in zip(c["etiqueta"], c["prediccion"], strict=True)])
    pred_s = (c["prediccion"] == "sospechoso").to_numpy()
    real_s = (c["etiqueta"] == "sospechoso").to_numpy()
    benigno = c["etiqueta"].isin(BENIGNAS).to_numpy()
    muestras = rng.integers(0, len(c), size=(n, len(c)))
    alfa = (1 - nivel) / 2

    def ic(valores: np.ndarray) -> dict:
        return {
            "ic_inf": float(np.nanquantile(valores, alfa)),
            "ic_sup": float(np.nanquantile(valores, 1 - alfa)),
        }

    with np.errstate(invalid="ignore", divide="ignore"):
        recall = (pred_s & real_s)[muestras].sum(1) / real_s[muestras].sum(1)
        falsa = (pred_s & benigno)[muestras].sum(1) / benigno[muestras].sum(1)
    return {
        "exactitud": ic(ok[muestras].mean(1)),
        "recall_sospechoso": ic(recall),
        "falsa_sospecha": ic(falsa),
    }


def tipo_predio_verdadero(
    grupos: pd.DataFrame, registros: pd.DataFrame, verdad_personas: pd.DataFrame
) -> pd.Series:
    """Tipo de predio verdadero de cada grupo de dirección (el de la mayoría de personas)."""
    persona_de = registros.set_index("unique_id")["cluster"]
    tipo = verdad_personas.set_index("cluster")["tipo_predio"]

    def mayoria(ids: list[int]) -> str | None:
        tipos = pd.Series([tipo.get(persona_de[i]) for i in ids]).dropna()
        return tipos.mode().iloc[0] if len(tipos) else None

    return grupos["ids_registros"].map(mayoria)


GRILLA: dict[str, tuple] = {
    "max_convivencia": (2, 3, 4, 5),
    "max_casa": (5, 6, 8),
    "min_familia": (0.5, 0.75, 1.0),
    "anillo_max_validado": (0.1, 0.25, 0.4),
    "anillo_min_digital": (0.6, 0.75, 0.9),
    "anillo_max_exclusividad": (0.4, 0.6, 0.8),
}


def _puntaje_rapido(filas: list[dict], etiquetas: list[str], p: ParametrosGrafo) -> tuple:
    """Exactitud balanceada y falsa sospecha sin pandas (para recorrer la grilla)."""
    aciertos: dict[str, list[int]] = {}
    benignos = marcados = 0
    for f, e in zip(filas, etiquetas, strict=True):
        pred = clasificar_fila(f, p)
        aciertos.setdefault(e, [0, 0])
        aciertos[e][0] += pred in ACEPTABLES.get(e, set())
        aciertos[e][1] += 1
        if e in BENIGNAS:
            benignos += 1
            marcados += pred == "sospechoso"
    tasas = [a / n for e, (a, n) in aciertos.items() if e != "misma_persona"]
    return float(np.mean(tasas)), marcados / benignos if benignos else 0.0


def elegir_parametros(
    desarrollos: list[pd.DataFrame], grilla: dict[str, tuple] | None = None
) -> tuple[ParametrosGrafo, pd.DataFrame]:
    """Busca en desarrollo los parámetros de mayor exactitud balanceada.

    ``desarrollos`` son grupos con su etiqueta verdadera (de uno o varios escenarios de
    desarrollo); se promedia la exactitud balanceada entre escenarios. A igual valor, gana
    la menor falsa sospecha y luego la combinación que aparece primero en la grilla.
    """
    grilla = grilla or GRILLA
    nombres = list(grilla)
    datos = [(d.to_dict("records"), list(d["etiqueta"])) for d in desarrollos]
    filas = []
    for valores in itertools.product(*grilla.values()):
        p = ParametrosGrafo(**dict(zip(nombres, valores, strict=True)))
        puntajes = [_puntaje_rapido(f, e, p) for f, e in datos]
        filas.append(
            {
                **asdict(p),
                "exactitud_balanceada": float(np.mean([b for b, _ in puntajes])),
                "falsa_sospecha": float(np.mean([s for _, s in puntajes])),
            }
        )
    tabla = pd.DataFrame(filas).reset_index(names="orden")
    tabla = tabla.sort_values(
        ["exactitud_balanceada", "falsa_sospecha", "orden"], ascending=[False, True, True]
    )
    mejor = tabla.iloc[0]
    tipos = {k: type(v) for k, v in asdict(ParametrosGrafo()).items()}
    return ParametrosGrafo(**{k: tipos[k](mejor[k]) for k in tipos}), tabla
