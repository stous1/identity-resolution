"""Generador independiente de errores de captura para la prueba ciega.

Toma una tabla de personas "verdaderas" (datos limpios, una fila por persona) y produce
entre 1 y 6 registros por persona como los capturaría un banco colombiano: cajeros,
formularios web, escaneo de documentos y migraciones entre sistemas. Fue escrito sin mirar
la estandarización ni el generador del modelo, para medir el modelo congelado con errores
que no conoció.

Cada tipo de error tiene su probabilidad en :class:`TasasCiegas`. Salvo que se diga otra
cosa, la tasa se aplica por registro (y por campo cuando el error afecta varios campos):

Dirección
    - ``via_variante``: otras abreviaturas y nombres de vía ("Cll", "Cra", "Kra", "Av.",
      "Avda", "Ak" avenida carrera, "Ac" avenida calle, "Transversal", "Transv.", "Tv",
      "Diagonal", "Diag.", "Dg", ...).
    - ``formato_numero``: formatos variados del número ("No.", "Nro.", "N°", sin "#",
      "CL45B", "45 B", "15bis", cuadrante "Sur"/"S" al final u omitido, ...).
    - ``complemento_direccion``: apartamento, torre, casa, barrio o conjunto añadidos.
    - ``rural`` (por persona): la persona vive en una vereda o finca; todas sus
      direcciones son rurales ("Vereda La Esperanza", "Finca El Recreo vereda X",
      "Km 5 vía a ...", "Corregimiento ...") y varían entre registros.

Nombres y apellidos
    - ``apodo``: apodo o hipocorístico en lugar del nombre (José -> Pepe, Francisco ->
      Pacho, Ana María -> Anamaría, Juan David -> Juanda, ...).
    - ``segundo_nombre_omitido``: el segundo nombre se omite o queda como inicial.
    - ``segundo_apellido_omitido``: el segundo apellido se omite.
    - ``apellido_casada``: "Padilla de Gómez" (solo nombres que parecen femeninos).
    - ``letras``: letra duplicada, comida, transpuesta o confusión fonética (b/v, s/z,
      c/s, y/ll, h muda).
    - ``campo_cruzado``: nombre completo en un solo campo, nombres y apellidos
      intercambiados, o el segundo nombre en el campo de apellidos.

Documento, fecha y teléfono
    - ``ocr``: lectura errada de documento escaneado (O por 0, l o I por 1, S por 5,
      B por 8, Z por 2), por campo: número de documento, celular y fecha.
    - ``documento_digito``: dígito cambiado, transpuesto, omitido o añadido.
    - ``documento_formato``: prefijo o separadores ("CC 123...", "C.C. 1.071.194.756",
      "1071194756 de Bogotá").
    - ``tipo_documento_variante``: "C.C.", "Cédula de ciudadanía", "cc", o un tipo errado
      ("TI", "PA").
    - ``fecha_formato``: DD/MM/YYYY, YYYYMMDD, "07 de marzo de 1985", ...
    - ``fecha_invertida``: día y mes intercambiados (cuando el día es 12 o menos).
    - ``celular_formato``: indicativo (+57), separadores, paréntesis, extensión o un
      segundo número.
    - ``celular_fijo``: un fijo viejo de 7 dígitos en vez del celular.
    - ``correo_dominio``: dominio mal escrito ("gmial.com", "hotmial.com", "gmail.con").

Ciudad y departamento
    - ``ciudad_variante``: "Bta", "Bogota DC", "Medellin Ant", "B/quilla", "Ctg", ...
    - ``departamento_variante``: "Ant", "Atl", "Cund", "Distrito Capital", ...

Errores transversales
    - ``sin_tilde``: se pierden tildes y eñes en todo el registro.
    - ``capitalizacion``: todo en mayúsculas sostenidas (o, a veces, en minúsculas).
    - ``mojibake``: caracteres mal codificados ("JosÃ©").
    - ``espacios`` (por campo): espacios dobles, al inicio o al final.
    - ``puntuacion`` (por campo): guiones, puntos, comas, guion bajo, barras y comillas
      sueltas.
    - ``faltante`` (por campo): fecha, celular, correo, dirección, ciudad o departamento
      vacíos.

Salvaguarda: el número de documento y los nombres nunca quedan vacíos, y un registro con el
documento alterado pierde a lo sumo un campo más, para que siempre quede algo que lo ligue
a su persona.

La aleatoriedad usa ``random.Random`` con semillas derivadas de (semilla, persona, registro,
tipo de error), así que el resultado es reproducible y cada error es independiente de los
demás: activar o desactivar uno no cambia los demás.
"""

from __future__ import annotations

import math
import random
import unicodedata
from dataclasses import dataclass, fields
from typing import Any

import pandas as pd

COLUMNAS = [
    "unique_id",
    "tipo_documento",
    "numero_documento",
    "nombres",
    "apellidos",
    "fecha_nacimiento",
    "celular",
    "correo",
    "direccion",
    "ciudad",
    "departamento",
    "cluster",
]

CONDICIONES = [
    "rural",
    "con_apodo",
    "apellido_casada",
    "documento_alterado",
    "celular_fijo",
    "nombres_cruzados",
    "un_solo_registro",
]


@dataclass(frozen=True)
class TasasCiegas:
    """Probabilidad de cada tipo de error (ver el docstring del módulo)."""

    via_variante: float = 0.45
    formato_numero: float = 0.45
    complemento_direccion: float = 0.20
    rural: float = 0.07
    apodo: float = 0.15
    segundo_nombre_omitido: float = 0.15
    segundo_apellido_omitido: float = 0.15
    apellido_casada: float = 0.06
    letras: float = 0.06
    campo_cruzado: float = 0.03
    ocr: float = 0.04
    documento_digito: float = 0.03
    documento_formato: float = 0.08
    tipo_documento_variante: float = 0.05
    fecha_formato: float = 0.20
    fecha_invertida: float = 0.03
    celular_formato: float = 0.15
    celular_fijo: float = 0.04
    correo_dominio: float = 0.04
    ciudad_variante: float = 0.15
    departamento_variante: float = 0.12
    sin_tilde: float = 0.30
    capitalizacion: float = 0.25
    mojibake: float = 0.03
    espacios: float = 0.06
    puntuacion: float = 0.04
    faltante: float = 0.05

    @classmethod
    def ceros(cls) -> TasasCiegas:
        """Todas las tasas en cero: registros limpios."""
        return cls(**{f.name: 0.0 for f in fields(cls)})


# ---------------------------------------------------------------------------
# Diccionarios
# ---------------------------------------------------------------------------

APODOS: dict[str, list[str]] = {
    "jose": ["Pepe", "Chepe"],
    "francisco": ["Pacho", "Pancho", "Paco"],
    "guillermo": ["Memo"],
    "jesus": ["Chucho"],
    "rosario": ["Charo"],
    "concepcion": ["Concha"],
    "ignacio": ["Nacho"],
    "alejandro": ["Alejo"],
    "alejandra": ["Aleja"],
    "margarita": ["Margo", "Magola"],
    "luis": ["Lucho"],
    "luisa": ["Lucha"],
    "manuel": ["Manolo"],
    "antonio": ["Toño"],
    "dolores": ["Lola"],
    "gonzalo": ["Chalo"],
    "rafael": ["Rafa"],
    "fernando": ["Fercho", "Nando"],
    "hernando": ["Nando"],
    "eduardo": ["Lalo"],
    "roberto": ["Beto"],
    "alberto": ["Beto"],
    "humberto": ["Beto"],
    "gilberto": ["Beto"],
    "jorge": ["Coque"],
    "enrique": ["Kike"],
    "gabriel": ["Gabo"],
    "gabriela": ["Gabi"],
    "daniel": ["Dani"],
    "daniela": ["Dani"],
    "santiago": ["Santi"],
    "sebastian": ["Sebas"],
    "mauricio": ["Mauro"],
    "ricardo": ["Richi"],
    "isabel": ["Isa", "Chabela"],
    "josefina": ["Pepa"],
    "mercedes": ["Meche"],
    "teresa": ["Tere"],
    "catalina": ["Cata"],
    "valentina": ["Vale"],
    "natalia": ["Nati"],
    "patricia": ["Paty"],
    "leonardo": ["Leo"],
    "federico": ["Fede"],
    "gustavo": ["Tavo"],
    "ernesto": ["Neto"],
    "adolfo": ["Fito"],
    "rodolfo": ["Fito"],
    "ramon": ["Moncho"],
    "carolina": ["Caro"],
    "alexandra": ["Alex"],
    "alexander": ["Alex"],
    "cristina": ["Cris"],
    "guadalupe": ["Lupe"],
    "consuelo": ["Chelo"],
    "graciela": ["Chela"],
    "marcela": ["Chela"],
    "elizabeth": ["Eli"],
    "juliana": ["Juli"],
    "julian": ["Juli"],
    "mariana": ["Mari"],
    "martha": ["Martica"],
    "andres": ["Pipe"],  # sic: frecuente por "Andrés Felipe"
    "felipe": ["Pipe"],
    "camilo": ["Cami"],
    "camila": ["Cami"],
    "carlos": ["Carlitos"],
    "nicolas": ["Nico"],
    "cecilia": ["Ceci"],
    "beatriz": ["Betty"],
    "esperanza": ["Pera"],
    "socorro": ["Coco"],
    "victoria": ["Vicky"],
    "pedro": ["Perucho"],
    "maria": ["Mary", "Mayo"],
}

APODOS_COMPUESTOS: dict[str, list[str]] = {
    "ana maria": ["Anamaría", "Anamari"],
    "juan david": ["Juanda"],
    "juan pablo": ["Juanpa"],
    "juan jose": ["Juanjo"],
    "juan carlos": ["Juanca"],
    "juan camilo": ["Juanca"],
    "juan sebastian": ["Juanse"],
    "juan esteban": ["Juanes"],
    "maria jose": ["Majo"],
    "maria fernanda": ["Mafe"],
    "maria paula": ["Mapis"],
    "maria alejandra": ["Malejita"],
    "luis fernando": ["Lucho"],
    "andres felipe": ["Pipe"],
    "jose luis": ["Pepe Luis"],
    "luz marina": ["Luzma"],
    "luz dary": ["Luzda"],
}

FEMENINOS_SIN_A = {
    "beatriz", "luz", "isabel", "ines", "mercedes", "dolores", "rosario", "carmen",
    "pilar", "raquel", "ruth", "esther", "consuelo", "socorro", "amparo", "nelly",
    "yolanda" , "marisol", "maribel", "elizabeth", "jazmin", "lizeth", "yaneth", "janeth",
    "ingrid", "astrid", "sol", "nidia", "edith", "liliam", "lilian", "miriam",
}  # fmt: skip
MASCULINOS_CON_A = {"luca", "joshua", "garcia", "jona", "nicola", "elias"}

VIAS: dict[str, list[str]] = {
    "CL": ["Calle", "Cll", "Cl.", "Cl", "Clle", "Ac", "Avenida Calle", "calle"],
    "KR": ["Carrera", "Cra", "Cra.", "Kra", "Kr", "Cr", "K", "Ak", "Avenida Carrera"],
    "DG": ["Diagonal", "Diag.", "Dg", "Dg.", "Diag"],
    "TV": ["Transversal", "Transv.", "Tv", "Tv.", "Trans", "Tr"],
    "AV": ["Av.", "Avda", "Avenida", "Av", "Avda."],
}

FORMATOS_URBANOS = [
    "{v} {n}{q} # {p}-{c}",  # canónico (índice 0)
    "{v} {n}{q} No. {p}-{c}",
    "{v} {n}{q} No {p} - {c}",
    "{v} {n}{q} N° {p} {c}",
    "{v} {n}{q} Nro. {p}-{c}",
    "{v} {n}{q}#{p}-{c}",
    "{v} {n}{q} {p} {c}",
    "{v} {n}{q} # {p} - {c}",
    "{v}{n}{q} #{p}-{c}",
    "{v} {n} # {p}-{c}{q}",
    "{v} {n}{q} {p}-{c}",
    "{v} {n}{q} n {p} {c}",
]

VEREDAS = [
    "La Esperanza", "El Retiro", "San Isidro", "La Palma", "El Carmen", "Santa Rosa",
    "Buenavista", "El Hato", "La Cumbre", "Alto Bonito", "Monterredondo", "Llano Grande",
    "La Laguna", "El Tablazo", "Potrerito", "San Antonio", "Las Mercedes", "El Salitre",
]  # fmt: skip
FINCAS = [
    "El Recreo", "La Fortuna", "Villa Luz", "La Primavera", "Los Naranjos", "El Paraíso",
    "La Esmeralda", "Santa Ana", "El Porvenir", "Villa María", "La Ilusión", "Las Brisas",
]  # fmt: skip
CORREGIMIENTOS = [
    "San Cristóbal", "Santa Elena", "La Buitrera", "Pasacaballos", "La Plata", "Bocachica",
    "El Placer", "Puerto Nuevo", "Palmor", "Guayabal", "La Sierra", "El Danubio",
]  # fmt: skip
DESTINOS = [
    "La Calera", "Fusagasugá", "Rionegro", "Santa Fe de Antioquia", "Puerto Colombia",
    "Turbaco", "Jamundí", "Piedecuesta", "Girardot", "Villavicencio", "el mar", "Tunja",
]  # fmt: skip
SECTORES = ["Alto", "Bajo", "La Y", "El Cruce", "La Escuela", "Centro"]
BARRIOS = [
    "La Floresta", "San José", "Villa del Río", "El Prado", "Los Alpes", "Kennedy",
    "Belén", "Manga", "El Poblado", "Chapinero", "La Candelaria", "Ciudad Jardín",
]  # fmt: skip
CONJUNTOS = ["Los Pinos", "Altos del Bosque", "Torres de San Juan", "Mirador del Lago"]
APELLIDOS_ESPOSO = [
    "Gómez", "Rodríguez", "Martínez", "López", "González", "Pérez", "Sánchez", "Ramírez",
    "Torres", "Díaz", "Vargas", "Moreno", "Jiménez", "Rojas", "Castro", "Ortiz",
]  # fmt: skip

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip

OCR: dict[str, list[str]] = {"0": ["O"], "1": ["l", "I"], "5": ["S"], "8": ["B"], "2": ["Z"]}

TIPOS_DOCUMENTO: dict[str, list[str]] = {
    "CC": ["C.C.", "cc", "C.C", "CEDULA", "Cédula de ciudadanía", "Cedula", "TI"],
    "CE": ["C.E.", "ce", "CEX", "Cédula de extranjería", "PA", "CC"],
}

DOMINIOS_ERRADOS: dict[str, list[str]] = {
    "gmail.com": ["gmial.com", "gmal.com", "gamil.com", "gmail.co", "gmail.con", "gmaill.com"],
    "hotmail.com": ["hotmial.com", "hotmal.com", "hotmail.co", "hotmail.con", "hotamil.com"],
    "yahoo.com": ["yahooo.com", "yaho.com", "yahoo.co", "yahoo.con", "yhaoo.com"],
    "outlook.com": ["outlok.com", "outllok.com", "outlook.co", "outlook.con", "otlook.com"],
}

CIUDADES: dict[str, list[str]] = {
    "bogota, d.c.": ["Bogotá", "Bogota DC", "Bogotá D.C.", "Bta", "Bogota", "Santafé de Bogotá"],
    "medellin": ["Medellin", "Medellín Ant", "Medellin Ant", "Mde", "Medellín - Antioquia"],
    "barranquilla": ["B/quilla", "Barranquilla Atl", "Bquilla", "Baq"],
    "cali": ["Santiago de Cali", "Cali Valle", "Cali - Valle", "Cali (V)"],
    "cartagena de indias": ["Cartagena", "Ctg", "Cartagena Bolívar", "Cartagena D.T."],
    "bucaramanga": ["Bmanga", "B/manga", "Bucaramanga Sder", "Bucaramanga S/der"],
}

DEPARTAMENTOS: dict[str, list[str]] = {
    "bogota, d.c.": ["Bogotá D.C.", "Cundinamarca", "DC", "Distrito Capital", "Bogota"],
    "antioquia": ["Ant", "Ant.", "Antioquía"],
    "atlantico": ["Atl", "Atl.", "Atlantico"],
    "valle del cauca": ["Valle", "Valle del Cauca", "V/cauca", "Vlle"],
    "bolivar": ["Bol", "Bol.", "Bolivar"],
    "santander": ["Sder", "Stder", "S/der", "Santanderes"],
    "cundinamarca": ["Cund", "Cund.", "Cundinamrca"],
    "boyaca": ["Boy", "Boyaca", "Boy."],
    "norte de santander": ["N. Santander", "Nte de Santander", "N/der"],
}

PUNTUACION = ["-", ".", ",", "_", "/", "'", '"', ";"]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _rng(semilla: int, *partes: Any) -> random.Random:
    """Generador derivado y reproducible para una combinación de partes."""
    return random.Random("|".join(str(p) for p in (semilla, *partes)))


def _txt(valor: Any) -> str | None:
    """Convierte a texto; NaN, None o vacío pasan a None."""
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    texto = str(valor).strip()
    return texto or None


def _sin_tildes(texto: str) -> str:
    """Quita tildes y eñes, como un sistema viejo sin soporte de acentos."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _clave(texto: str) -> str:
    """Clave de búsqueda en diccionarios: minúsculas y sin tildes."""
    return _sin_tildes(texto).lower().strip()


def _unir(*partes: str | None) -> str | None:
    """Une con espacio las partes no vacías."""
    texto = " ".join(p for p in partes if p)
    return texto or None


# ---------------------------------------------------------------------------
# Versión limpia
# ---------------------------------------------------------------------------


def direccion_canonica(persona: pd.Series | dict) -> str:
    """Dirección urbana limpia, p. ej. ``"CL 45B SUR # 107B-83"``."""
    cuadrante = _txt(persona["direccion_cuadrante"])
    q = f" {cuadrante}" if cuadrante else ""
    return (
        f"{persona['direccion_via']} {persona['direccion_numero_via']}{q} "
        f"# {persona['direccion_placa']}-{persona['direccion_consecutivo']}"
    )


def registro_limpio(persona: pd.Series | dict) -> dict[str, str | None]:
    """Registro sin errores de una persona (sin ``unique_id`` ni ``cluster``)."""
    return {
        "tipo_documento": _txt(persona["tipo_documento"]),
        "numero_documento": _txt(persona["numero_documento"]),
        "nombres": _unir(_txt(persona["primer_nombre"]), _txt(persona["segundo_nombre"])),
        "apellidos": _unir(_txt(persona["primer_apellido"]), _txt(persona["segundo_apellido"])),
        "fecha_nacimiento": _txt(persona["fecha_nacimiento"]),
        "celular": _txt(persona["celular"]),
        "correo": _txt(persona["correo"]),
        "direccion": direccion_canonica(persona),
        "ciudad": _txt(persona["ciudad"]),
        "departamento": _txt(persona["departamento"]),
    }


# ---------------------------------------------------------------------------
# Direcciones
# ---------------------------------------------------------------------------


def _variar_numero(numero: str, rng: random.Random) -> str:
    """Separa o pone en minúscula la letra de un número de vía ("45B" -> "45 B")."""
    if "BIS" in numero:
        return rng.choice([numero.replace(" BIS", "BIS"), numero.replace("BIS", "Bis"),
                           numero.replace(" BIS", "bis"), numero.replace("BIS", "B")])  # fmt: skip
    if numero[-1:].isalpha():
        return rng.choice([f"{numero[:-1]} {numero[-1]}", numero.lower()])
    return numero


def _variar_cuadrante(cuadrante: str | None, rng: random.Random) -> str:
    """Cuadrante con otra grafía o simplemente omitido."""
    if not cuadrante:
        return ""
    return rng.choice(["", f" {cuadrante.title()}", f" {cuadrante[0]}", f" {cuadrante.lower()}"])


def direccion_urbana(
    persona: pd.Series | dict, rng_via: random.Random | None, rng_formato: random.Random | None
) -> str:
    """Dirección urbana con variantes de vía (si ``rng_via``) y de formato (si ``rng_formato``)."""
    via = str(persona["direccion_via"])
    v = rng_via.choice(VIAS.get(via, [via])) if rng_via else via
    n = str(persona["direccion_numero_via"])
    p = str(persona["direccion_placa"])
    c = str(persona["direccion_consecutivo"])
    cuadrante = _txt(persona["direccion_cuadrante"])
    q = f" {cuadrante}" if cuadrante else ""
    plantilla = FORMATOS_URBANOS[0]
    if rng_formato:
        plantilla = rng_formato.choice(FORMATOS_URBANOS[1:])
        if rng_formato.random() < 0.4:
            n = _variar_numero(n, rng_formato)
            p = _variar_numero(p, rng_formato)
        if rng_formato.random() < 0.4:
            q = _variar_cuadrante(cuadrante, rng_formato)
    return plantilla.format(v=v, n=n, q=q, p=p, c=c)


def perfil_rural(rng: random.Random) -> dict[str, str]:
    """Datos rurales fijos de una persona: vereda, finca, kilómetro, destino, etc."""
    return {
        "V": rng.choice(VEREDAS),
        "F": rng.choice(FINCAS),
        "K": str(rng.randint(1, 35)),
        "D": rng.choice(DESTINOS),
        "C": rng.choice(CORREGIMIENTOS),
        "S": rng.choice(SECTORES),
    }


PLANTILLAS_RURALES = [
    "Vereda {V}",
    "Vda {V}",
    "Vda. {V}",
    "Finca {F} vereda {V}",
    "Fca {F} Vda {V}",
    "Finca {F}",
    "Km {K} vía a {D}",
    "Kilómetro {K} vía {D}",
    "Km {K} via {D} Finca {F}",
    "Corregimiento {C}",
    "Corr. {C} vereda {V}",
    "Vereda {V} sector {S}",
    "Predio {F} Vda {V}",
    "Kilómetro {K} vía a {D} vereda {V}",
    "Finca {F} Km {K}",
]


def direccion_rural(perfil: dict[str, str], rng: random.Random) -> str:
    """Una de las formas en que se escribe la dirección rural de la persona."""
    return rng.choice(PLANTILLAS_RURALES).format(**perfil)


def complemento(rng: random.Random) -> list[str]:
    """Complemento fijo de una persona en varias grafías (apartamento, casa, barrio...)."""
    apto = f"{rng.randint(1, 22)}{rng.randint(1, 4):02d}"
    torre, casa = rng.randint(1, 9), rng.randint(1, 60)
    barrio, conjunto = rng.choice(BARRIOS), rng.choice(CONJUNTOS)
    return rng.choice([
        [f"Apto {apto}", f"Apartamento {apto}", f"Ap {apto}", f"Apt. {apto}"],
        [f"Torre {torre} Apto {apto}", f"T{torre} Apto {apto}", f"Int {torre} Ap {apto}"],
        [f"Casa {casa}", f"Cs {casa}", f"casa {casa}"],
        [f"Barrio {barrio}", f"B. {barrio}", f"Brr {barrio}", barrio],
        [f"Conjunto {conjunto} Casa {casa}", f"Conj. {conjunto} Cs {casa}"],
    ])  # fmt: skip


# ---------------------------------------------------------------------------
# Nombres
# ---------------------------------------------------------------------------


def apodo(primer: str, segundo: str | None, rng: random.Random) -> str | None:
    """Apodo para los nombres de pila, o None si la persona no tiene uno conocido."""
    compuesto = _clave(f"{primer} {segundo or ''}")
    if compuesto in APODOS_COMPUESTOS:
        return rng.choice(APODOS_COMPUESTOS[compuesto])
    if _clave(primer) in APODOS:
        nombre = rng.choice(APODOS[_clave(primer)])
        return _unir(nombre, segundo) if segundo and rng.random() < 0.3 else nombre
    if segundo and _clave(segundo) in APODOS:
        return rng.choice(APODOS[_clave(segundo)])
    return None


def parece_femenino(nombre: str) -> bool:
    """Heurística simple: el nombre termina en "a" o está en la lista de femeninos."""
    clave = _clave(nombre)
    return clave in FEMENINOS_SIN_A or (clave.endswith("a") and clave not in MASCULINOS_CON_A)


_CONFUSIONES = [("b", "v"), ("v", "b"), ("s", "z"), ("z", "s"), ("c", "s"), ("y", "ll"),
                ("ll", "y"), ("h", ""), ("qu", "k"), ("g", "j")]  # fmt: skip


def error_letras(texto: str, rng: random.Random) -> str:
    """Letra duplicada, comida, transpuesta o confusión fonética."""
    posiciones = [i for i, c in enumerate(texto) if c.isalpha()]
    if len(posiciones) < 2:
        return texto
    opcion = rng.choice(["duplicar", "comer", "transponer", "fonetica"])
    if opcion == "fonetica":
        candidatas = [(a, b) for a, b in _CONFUSIONES if a in texto.lower()]
        if candidatas:
            a, b = rng.choice(candidatas)
            i = texto.lower().index(a)
            nuevo = b.upper() if texto[i].isupper() and b else b
            return texto[:i] + nuevo + texto[i + len(a) :]
        opcion = "duplicar"
    i = rng.choice(posiciones[1:])
    if opcion == "duplicar":
        return texto[:i] + texto[i] + texto[i:]
    if opcion == "comer":
        return texto[:i] + texto[i + 1 :]
    return texto[: i - 1] + texto[i] + texto[i - 1] + texto[i + 1 :]


def cruzar_campos(
    nombres: str | None, apellidos: str | None, segundo: str | None, rng: random.Random
) -> tuple[str | None, str | None]:
    """Nombre completo en un campo, campos intercambiados o segundo nombre en apellidos."""
    opciones = ["todo_en_nombres", "intercambiar"]
    if segundo and nombres and nombres.endswith(segundo):
        opciones.append("segundo_a_apellidos")
    opcion = rng.choice(opciones)
    if opcion == "todo_en_nombres":
        return _unir(nombres, apellidos), None
    if opcion == "intercambiar":
        return apellidos, nombres
    primero = nombres[: -len(segundo)].strip() if nombres and segundo else nombres
    return primero, _unir(segundo, apellidos)


# ---------------------------------------------------------------------------
# Documento, fecha, celular, correo
# ---------------------------------------------------------------------------


def error_ocr(texto: str, rng: random.Random) -> str:
    """Cambia uno o dos dígitos por letras parecidas (0->O, 1->l/I, 5->S, 8->B, 2->Z)."""
    posiciones = [i for i, c in enumerate(texto) if c in OCR]
    if not posiciones:
        return texto
    caracteres = list(texto)
    for i in rng.sample(posiciones, k=min(len(posiciones), rng.choice([1, 1, 2]))):
        caracteres[i] = rng.choice(OCR[caracteres[i]])
    return "".join(caracteres)


def error_digito(numero: str, rng: random.Random) -> str:
    """Dígito cambiado, transpuesto, omitido o añadido en el documento."""
    i = rng.randrange(len(numero))
    opcion = rng.choice(["cambiar", "transponer", "omitir", "anadir"])
    if opcion == "cambiar":
        nuevo = rng.choice([d for d in "0123456789" if d != numero[i]])
        return numero[:i] + nuevo + numero[i + 1 :]
    if opcion == "transponer" and i + 1 < len(numero) and numero[i] != numero[i + 1]:
        return numero[:i] + numero[i + 1] + numero[i] + numero[i + 2 :]
    if opcion == "omitir" and len(numero) > 6:
        return numero[:i] + numero[i + 1 :]
    return numero[:i] + rng.choice("0123456789") + numero[i:]


def _miles(numero: str, separador: str) -> str:
    """Agrupa los dígitos de tres en tres: 1071194756 -> 1.071.194.756."""
    grupos = []
    while numero:
        grupos.insert(0, numero[-3:])
        numero = numero[:-3]
    return separador.join(grupos)


def formato_documento(numero: str, tipo: str, ciudad: str | None, rng: random.Random) -> str:
    """Documento con prefijo, separadores de miles o lugar de expedición."""
    opciones = [
        f"{tipo} {numero}",
        f"{tipo}{numero}",
        f"{'.'.join(tipo)}. {numero}",
        _miles(numero, "."),
        _miles(numero, ","),
        f"{tipo} {_miles(numero, '.')}",
        f"{numero} de {ciudad or 'Bogotá'}",
        f"No. {numero}",
    ]
    return rng.choice(opciones)


def formato_fecha(fecha: str, rng: random.Random) -> str:
    """Fecha ISO reescrita en otro formato frecuente."""
    anio, mes, dia = fecha.split("-")
    opciones = [
        f"{dia}/{mes}/{anio}",
        f"{dia}-{mes}-{anio}",
        f"{anio}{mes}{dia}",
        f"{dia} de {MESES[int(mes) - 1]} de {anio}",
        f"{int(dia)}/{int(mes)}/{anio}",
        f"{anio}/{mes}/{dia}",
        f"{dia}.{mes}.{anio}",
        f"{dia}/{mes}/{anio[2:]}",
        f"{dia}-{MESES[int(mes) - 1][:3].upper()}-{anio}",
    ]
    return rng.choice(opciones)


def invertir_fecha(fecha: str) -> str:
    """Intercambia día y mes en una fecha ISO si el día es 12 o menos."""
    anio, mes, dia = fecha.split("-")
    return f"{anio}-{dia}-{mes}" if int(dia) <= 12 and dia != mes else fecha


def formato_celular(celular: str, rng: random.Random) -> str:
    """Celular con indicativo, separadores, extensión o un segundo número."""
    a, b, c = celular[:3], celular[3:6], celular[6:]
    otro = f"60{rng.randint(1, 8)}{rng.randint(2000000, 8999999)}"
    opciones = [
        f"+57 {celular}",
        f"57{celular}",
        f"(+57) {a}-{b}-{c}",
        f"{a} {b} {c}",
        f"{a}-{b}{c}",
        f"({a}) {b} {c}",
        f"{celular} ext {rng.randint(1, 999)}",
        f"{celular} / {otro}",
        f"{a} {b}{c}",
    ]
    return rng.choice(opciones)


def fijo(rng: random.Random) -> str:
    """Teléfono fijo viejo de 7 dígitos."""
    return str(rng.randint(2000000, 8999999))


def error_dominio(correo: str, rng: random.Random) -> str:
    """Dominio de correo mal escrito."""
    usuario, _, dominio = correo.partition("@")
    errados = DOMINIOS_ERRADOS.get(dominio)
    if errados:
        return f"{usuario}@{rng.choice(errados)}"
    return f"{usuario}@{dominio[:-1]}" if dominio else correo


# ---------------------------------------------------------------------------
# Ciudad y departamento
# ---------------------------------------------------------------------------


def _abreviar(texto: str) -> str:
    """Abreviatura genérica: primeras cuatro letras sin tilde y punto."""
    return _sin_tildes(texto)[:4].rstrip() + "."


def variante_ciudad(ciudad: str, departamento: str | None, rng: random.Random) -> str:
    """Ciudad abreviada o con el departamento pegado."""
    conocidas = CIUDADES.get(_clave(ciudad))
    if conocidas:
        return rng.choice(conocidas)
    depto = departamento or ""
    opciones = [f"{ciudad} - {depto}", f"{ciudad} ({_abreviar(depto)})"]
    opciones.append(f"{ciudad} {_abreviar(depto)}")
    if _sin_tildes(ciudad) != ciudad:
        opciones.append(_sin_tildes(ciudad).upper())
    return rng.choice(opciones)


def variante_departamento(departamento: str, rng: random.Random) -> str:
    """Departamento abreviado o escrito de otra forma."""
    conocidas = DEPARTAMENTOS.get(_clave(departamento))
    if conocidas:
        return rng.choice(conocidas)
    return rng.choice([_abreviar(departamento), departamento.upper(), f"Dpto. {departamento}"])


# ---------------------------------------------------------------------------
# Errores transversales de texto
# ---------------------------------------------------------------------------


def error_espacios(texto: str, rng: random.Random) -> str:
    """Espacios dobles, al inicio o al final."""
    opcion = rng.choice(["doble", "inicio", "final", "ambos"])
    if opcion == "doble" and " " in texto:
        return texto.replace(" ", "  ", 1)
    if opcion == "inicio":
        return " " + texto
    if opcion == "final":
        return texto + "  "
    return f" {texto} "


def error_puntuacion(texto: str, rng: random.Random) -> str:
    """Signo de puntuación suelto al inicio, al final, en un espacio o en medio."""
    signo = rng.choice(PUNTUACION)
    opcion = rng.choice(["final", "inicio", "espacio", "medio"])
    if opcion == "espacio" and " " in texto:
        return texto.replace(" ", rng.choice([signo, f"{signo} ", f" {signo} "]), 1)
    if opcion == "medio" and len(texto) > 2:
        i = rng.randrange(1, len(texto) - 1)
        return texto[:i] + signo + texto[i:]
    if opcion == "inicio":
        return signo + texto
    return texto + signo


def mojibake(texto: str) -> str:
    """Texto UTF-8 leído como Windows-1252: "José" -> "JosÃ©"."""
    return texto.encode("utf-8").decode("cp1252", errors="replace")


# ---------------------------------------------------------------------------
# Construcción de un registro
# ---------------------------------------------------------------------------

_TEXTO = ["nombres", "apellidos", "direccion", "ciudad", "departamento"]
_CAMPOS_LIBRES = [
    "numero_documento", "nombres", "apellidos", "fecha_nacimiento", "celular", "correo",
    "direccion", "ciudad", "departamento",
]  # fmt: skip
_OPCIONALES = ["fecha_nacimiento", "celular", "correo", "direccion", "ciudad", "departamento"]


@dataclass(frozen=True)
class _Contexto:
    """Lo que necesita cada paso: persona, tasas y el sorteo de errores del registro."""

    persona: pd.Series
    tasas: TasasCiegas
    semilla: int
    registro: int
    rural: dict[str, str] | None
    complemento: list[str]
    esposo: str

    def sorteo(self, error: str, campo: str = "") -> random.Random | None:
        """Generador del error si ocurre en este registro (y campo), o None."""
        rng = _rng(self.semilla, self.persona["cluster"], self.registro, error, campo)
        return rng if rng.random() < getattr(self.tasas, error) else None


def _nombres(reg: dict, ctx: _Contexto, marcas: set[str]) -> None:
    """Apodo, nombres omitidos, apellido de casada, letras y campos cruzados."""
    p = ctx.persona
    primer, segundo = _txt(p["primer_nombre"]), _txt(p["segundo_nombre"])
    primer_ap, segundo_ap = _txt(p["primer_apellido"]), _txt(p["segundo_apellido"])
    rng = ctx.sorteo("apodo")
    alias = apodo(primer, segundo, rng) if rng and primer else None
    if alias:
        reg["nombres"] = alias
        marcas.add("con_apodo")
    elif segundo and (rng := ctx.sorteo("segundo_nombre_omitido")):
        reg["nombres"] = primer if rng.random() < 0.6 else f"{primer} {segundo[0]}."
    if segundo_ap and ctx.sorteo("segundo_apellido_omitido"):
        reg["apellidos"] = primer_ap
    if primer and parece_femenino(primer) and (rng := ctx.sorteo("apellido_casada")):
        reg["apellidos"] = f"{primer_ap} de {ctx.esposo}"
        marcas.add("apellido_casada")
    if rng := ctx.sorteo("letras"):
        campo = rng.choice(["nombres", "apellidos"])
        reg[campo] = error_letras(reg[campo], rng)
    if rng := ctx.sorteo("campo_cruzado"):
        reg["nombres"], reg["apellidos"] = cruzar_campos(
            reg["nombres"], reg["apellidos"], segundo, rng
        )
        marcas.add("nombres_cruzados")


def _documento(reg: dict, ctx: _Contexto, marcas: set[str]) -> None:
    """Tipo de documento, dígito errado, OCR y formato del número."""
    if rng := ctx.sorteo("tipo_documento_variante"):
        reg["tipo_documento"] = rng.choice(TIPOS_DOCUMENTO.get(reg["tipo_documento"], ["CC"]))
    numero = reg["numero_documento"]
    if rng := ctx.sorteo("documento_digito"):
        numero = error_digito(numero, rng)
    if rng := ctx.sorteo("ocr", "numero_documento"):
        numero = error_ocr(numero, rng)
    if numero != reg["numero_documento"]:
        marcas.add("documento_alterado")
    if rng := ctx.sorteo("documento_formato"):
        tipo = _txt(ctx.persona["tipo_documento"]) or "CC"
        numero = formato_documento(numero, tipo, _txt(ctx.persona["ciudad"]), rng)
    reg["numero_documento"] = numero


def _fecha_y_contacto(reg: dict, ctx: _Contexto, marcas: set[str]) -> None:
    """Fecha, celular y correo."""
    fecha = reg["fecha_nacimiento"]
    if fecha:
        if ctx.sorteo("fecha_invertida"):
            fecha = invertir_fecha(fecha)
        if rng := ctx.sorteo("fecha_formato"):
            fecha = formato_fecha(fecha, rng)
        if rng := ctx.sorteo("ocr", "fecha_nacimiento"):
            fecha = error_ocr(fecha, rng)
        reg["fecha_nacimiento"] = fecha
    celular = reg["celular"]
    if celular:
        if rng := ctx.sorteo("celular_fijo"):
            celular = fijo(rng)
            marcas.add("celular_fijo")
        elif rng := ctx.sorteo("celular_formato"):
            celular = formato_celular(celular, rng)
        if rng := ctx.sorteo("ocr", "celular"):
            celular = error_ocr(celular, rng)
        reg["celular"] = celular
    if reg["correo"] and (rng := ctx.sorteo("correo_dominio")):
        reg["correo"] = error_dominio(reg["correo"], rng)


def _direccion(reg: dict, ctx: _Contexto) -> None:
    """Dirección rural o urbana, ciudad y departamento."""
    if ctx.rural is not None:
        rng = _rng(ctx.semilla, ctx.persona["cluster"], ctx.registro, "rural")
        reg["direccion"] = direccion_rural(ctx.rural, rng)
    else:
        reg["direccion"] = direccion_urbana(
            ctx.persona, ctx.sorteo("via_variante"), ctx.sorteo("formato_numero")
        )
        if rng := ctx.sorteo("complemento_direccion"):
            reg["direccion"] += " " + rng.choice(ctx.complemento)
    if reg["ciudad"] and (rng := ctx.sorteo("ciudad_variante")):
        reg["ciudad"] = variante_ciudad(reg["ciudad"], reg["departamento"], rng)
    if reg["departamento"] and (rng := ctx.sorteo("departamento_variante")):
        reg["departamento"] = variante_departamento(reg["departamento"], rng)


def _transversales(reg: dict, ctx: _Contexto) -> None:
    """Mayúsculas, tildes, codificación, espacios y puntuación."""
    if rng := ctx.sorteo("capitalizacion"):
        mayus = rng.random() < 0.8
        for campo in [*_TEXTO, "correo"]:
            if reg[campo]:
                reg[campo] = reg[campo].upper() if mayus else reg[campo].lower()
    if ctx.sorteo("sin_tilde"):
        for campo in _TEXTO:
            if reg[campo]:
                reg[campo] = _sin_tildes(reg[campo])
    if ctx.sorteo("mojibake"):
        for campo in _TEXTO:
            if reg[campo]:
                reg[campo] = mojibake(reg[campo])
    for campo in _CAMPOS_LIBRES:
        if reg[campo] and (rng := ctx.sorteo("espacios", campo)):
            reg[campo] = error_espacios(reg[campo], rng)
        if reg[campo] and (rng := ctx.sorteo("puntuacion", campo)):
            reg[campo] = error_puntuacion(reg[campo], rng)


def _faltantes(reg: dict, ctx: _Contexto, marcas: set[str]) -> None:
    """Vacía campos opcionales sin dejar el registro desligado de su persona."""
    maximo = 1 if "documento_alterado" in marcas else 2
    vaciados = 0
    for campo in _OPCIONALES:
        if vaciados < maximo and reg[campo] and ctx.sorteo("faltante", campo):
            reg[campo] = None
            vaciados += 1


def capturar_registro(ctx: _Contexto, marcas: set[str]) -> dict[str, str | None]:
    """Un registro capturado de la persona del contexto, con sus errores."""
    reg = registro_limpio(ctx.persona)
    _nombres(reg, ctx, marcas)
    _documento(reg, ctx, marcas)
    _fecha_y_contacto(reg, ctx, marcas)
    _direccion(reg, ctx)
    _transversales(reg, ctx)
    _faltantes(reg, ctx, marcas)
    return reg


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def numero_registros(rng: random.Random) -> int:
    """Registros de una persona: 1 con probabilidad 0.35, si no entre 2 y 6."""
    return 1 if rng.random() < 0.35 else rng.randint(2, 6)


def _contexto_persona(
    persona: pd.Series, semilla: int, tasas: TasasCiegas
) -> tuple[dict[str, str] | None, list[str], str]:
    """Datos fijos de la persona: perfil rural (o None), complemento y apellido del esposo."""
    cluster = persona["cluster"]
    rng_rural = _rng(semilla, cluster, "persona", "rural")
    rural = perfil_rural(rng_rural) if rng_rural.random() < tasas.rural else None
    comp = complemento(_rng(semilla, cluster, "persona", "complemento"))
    esposo = _rng(semilla, cluster, "persona", "esposo").choice(APELLIDOS_ESPOSO)
    return rural, comp, esposo


def capturar_persona(
    persona: pd.Series, semilla: int, tasas: TasasCiegas
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Registros capturados de una persona y su fila de condiciones."""
    cluster = persona["cluster"]
    rural, comp, esposo = _contexto_persona(persona, semilla, tasas)
    n = numero_registros(_rng(semilla, cluster, "persona", "conteo"))
    marcas: set[str] = set()
    registros = []
    for k in range(n):
        ctx = _Contexto(persona, tasas, semilla, k, rural, comp, esposo)
        registros.append({**capturar_registro(ctx, marcas), "cluster": int(cluster)})
    condiciones = {"cluster": int(cluster), **{c: c in marcas for c in CONDICIONES}}
    condiciones["rural"] = rural is not None
    condiciones["un_solo_registro"] = n == 1
    return registros, condiciones


def capturar(
    personas: pd.DataFrame, semilla: int = 0, tasas: TasasCiegas | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Simula la captura de las personas y devuelve ``(registros, condiciones)``.

    ``registros`` tiene las columnas de :data:`COLUMNAS`, entre 1 y 6 filas por persona en
    orden aleatorio y ``unique_id`` de 0 a n-1. ``condiciones`` tiene una fila por persona
    con ``cluster`` y las columnas booleanas de :data:`CONDICIONES`.
    """
    tasas = tasas or TasasCiegas()
    registros: list[dict[str, Any]] = []
    condiciones: list[dict[str, Any]] = []
    for _, persona in personas.iterrows():
        regs, cond = capturar_persona(persona, semilla, tasas)
        registros.extend(regs)
        condiciones.append(cond)
    random.Random(semilla).shuffle(registros)
    for i, reg in enumerate(registros):
        reg["unique_id"] = i
    tabla = pd.DataFrame(registros, columns=COLUMNAS).astype(object)
    tabla = tabla.where(tabla.notna(), None)
    tabla["unique_id"] = tabla["unique_id"].astype(int)
    tabla["cluster"] = tabla["cluster"].astype(int)
    return tabla, pd.DataFrame(condiciones, columns=["cluster", *CONDICIONES])
