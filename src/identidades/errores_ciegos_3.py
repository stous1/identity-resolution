"""Tercera prueba ciega: errores de captura escritos sin conocer el modelo a evaluar.

Este generador parte de la tabla de personas verdaderas de ``identidades.sinteticos`` y
simula cómo esas personas quedan registradas en una base de clientes de un banco
colombiano ficticio: varios registros por persona, capturados en canales distintos
(sucursal, aplicación, call center, corresponsal y bases de prospectos), en momentos
distintos de su vida y por digitadores distintos.

Se escribió sin leer la estandarización ni los modelos que se evalúan con él, y sin leer
los generadores de pruebas ciegas anteriores. Todo es sintético: no usa datos reales de
clientes ni reglas de ningún banco.

La salida es la misma interfaz de las pruebas ciegas anteriores: ``capturar`` devuelve los
registros capturados (con ``cluster`` = persona verdadera) y una tabla de condiciones por
persona, que vale ``True`` solo cuando la condición se manifestó en algún registro.
"""

from __future__ import annotations

import dataclasses
import random
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

COLUMNAS: list[str] = [
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

CONDICIONES: list[str] = [
    "apellido_casada",
    "separacion_o_nuevo_matrimonio",
    "con_apodo",
    "rural",
    "mudanza",
    "cambio_celular",
    "sin_documento",
    "documento_alterado",
    "tarjeta_identidad",
    "datos_ajenos",
    "mujer_aparente",
]

CANALES: tuple[str, ...] = ("sucursal", "app", "call_center", "corresponsal", "prospecto")


@dataclass(frozen=True)
class TasasCiegas3:
    """Tasas de cada tipo de error (probabilidades entre 0 y 1).

    Las tasas "de persona" se sortean una vez por persona; las "de registro", una vez por
    registro y luego se ajustan con un multiplicador según el canal de captura.
    """

    # Cantidad de registros por persona (pesos para 1, 2, ..., 6 registros).
    pesos_n_registros: tuple[float, ...] = (0.30, 0.26, 0.18, 0.12, 0.08, 0.06)
    # Pesos de canal (sucursal, app, call_center, corresponsal, prospecto).
    pesos_canal: tuple[float, ...] = (0.38, 0.24, 0.16, 0.12, 0.10)

    # --- Condiciones de persona ---
    casada: float = 0.24
    separacion_o_nuevo: float = 0.25
    apodo: float = 0.22
    apodo_por_registro: float = 0.55
    rural: float = 0.10
    mudanza: float = 0.24
    mudanza_otra_ciudad: float = 0.45
    cambio_celular: float = 0.18
    cambio_correo: float = 0.14
    tarjeta_identidad: float = 0.40

    # --- Documento ---
    sin_documento: float = 0.06
    documento_alterado: float = 0.09
    documento_formato: float = 0.10
    tipo_documento_formato: float = 0.12
    tipo_documento_errado: float = 0.04

    # --- Nombres y apellidos ---
    sin_tildes: float = 0.40
    codificacion: float = 0.03
    variante_nombre: float = 0.25
    segundo_nombre_omitido: float = 0.28
    segundo_nombre_inicial: float = 0.07
    usa_segundo_nombre: float = 0.04
    nombres_pegados: float = 0.02
    nombre_fonetico: float = 0.07
    nombre_tipeo: float = 0.06
    segundo_apellido_omitido: float = 0.18
    apellido_fonetico: float = 0.06
    apellido_tipeo: float = 0.06
    nombre_completo_en_un_campo: float = 0.02
    nombres_apellidos_cruzados: float = 0.025

    # --- Fecha de nacimiento ---
    fecha_formato: float = 0.18
    fecha_dia_mes: float = 0.04
    fecha_tipeo: float = 0.05
    fecha_expedicion: float = 0.02
    fecha_defecto: float = 0.015
    fecha_faltante: float = 0.04

    # --- Celular ---
    celular_faltante: float = 0.09
    celular_formato: float = 0.16
    celular_tipeo: float = 0.04
    celular_fijo: float = 0.04
    celular_ficticio: float = 0.02

    # --- Correo ---
    correo_faltante: float = 0.16
    correo_tipeo: float = 0.06
    correo_mayusculas: float = 0.08
    correo_generico: float = 0.03

    # --- Dirección y ubicación ---
    direccion_complemento: float = 0.22
    direccion_tipeo: float = 0.06
    direccion_cuadrante_omitido: float = 0.25
    direccion_faltante: float = 0.06
    ciudad_variante: float = 0.25
    ciudad_faltante: float = 0.04
    departamento_faltante: float = 0.08

    # --- Datos de otras personas ---
    dato_familiar: float = 0.06
    arrastre_otro_cliente: float = 0.015


# Multiplicadores de tasa por canal: lo que no aparece vale 1.
_MULTIPLICADORES: dict[str, dict[str, float]] = {
    "sucursal": {
        "sin_documento": 0.2,
        "sin_tildes": 0.7,
        "correo_faltante": 0.8,
        "nombre_tipeo": 0.8,
    },
    "app": {
        "sin_documento": 0.3,
        "documento_alterado": 1.3,
        "sin_tildes": 1.6,
        "apodo_por_registro": 1.5,
        "nombre_tipeo": 1.6,
        "apellido_tipeo": 1.5,
        "correo_faltante": 0.1,
        "correo_tipeo": 1.5,
        "direccion_tipeo": 1.4,
        "segundo_nombre_omitido": 1.4,
        "segundo_apellido_omitido": 1.4,
        "fecha_formato": 0.3,
        "celular_faltante": 0.1,
    },
    "call_center": {
        "sin_documento": 1.5,
        "nombre_fonetico": 2.6,
        "apellido_fonetico": 2.6,
        "correo_tipeo": 2.0,
        "direccion_faltante": 2.5,
        "documento_alterado": 1.4,
        "fecha_dia_mes": 1.5,
    },
    "corresponsal": {
        "sin_documento": 0.1,
        "sin_tildes": 1.8,
        "correo_faltante": 3.0,
        "direccion_faltante": 2.0,
        "celular_formato": 1.5,
        "fecha_formato": 1.8,
        "nombre_tipeo": 1.3,
        "departamento_faltante": 2.0,
    },
    "prospecto": {
        "sin_documento": 5.0,
        "documento_alterado": 1.5,
        "fecha_faltante": 4.0,
        "direccion_faltante": 3.0,
        "apodo_por_registro": 1.6,
        "segundo_apellido_omitido": 2.0,
        "segundo_nombre_omitido": 1.5,
        "correo_faltante": 0.4,
        "correo_generico": 0.3,
    },
}

# Formato de mayúsculas por canal: (mayus, titulo, minus, tal_cual).
_CAJA_CANAL: dict[str, tuple[float, float, float, float]] = {
    "sucursal": (0.6, 0.0, 0.0, 0.4),
    "app": (0.15, 0.1, 0.25, 0.5),
    "call_center": (0.5, 0.5, 0.0, 0.0),
    "corresponsal": (0.8, 0.0, 0.05, 0.15),
    "prospecto": (0.3, 0.0, 0.3, 0.4),
}

# --- Diccionarios propios -------------------------------------------------------------

# Apodos y diminutivos de uso común en Colombia (lista propia).
APODOS: dict[str, tuple[str, ...]] = {
    "José": ("Pepe", "Chepe"),
    "Francisco": ("Pacho", "Pancho", "Paco"),
    "Jesús": ("Chucho",),
    "Guillermo": ("Memo",),
    "Alberto": ("Beto",),
    "Roberto": ("Beto", "Robert"),
    "Ignacio": ("Nacho",),
    "Fernando": ("Nando", "Fercho"),
    "Hernando": ("Nando",),
    "Alejandro": ("Alejo",),
    "Alejandra": ("Aleja",),
    "Rafael": ("Rafa",),
    "Eduardo": ("Lalo",),
    "Antonio": ("Toño",),
    "Manuel": ("Manolo",),
    "Enrique": ("Kike",),
    "Santiago": ("Santi",),
    "Sebastián": ("Sebas",),
    "Nicolás": ("Nico",),
    "Daniel": ("Dani",),
    "Daniela": ("Dani",),
    "Gabriel": ("Gabo",),
    "Gabriela": ("Gaby",),
    "Mauricio": ("Mao",),
    "Felipe": ("Pipe",),
    "Luis": ("Lucho",),
    "Gustavo": ("Tavo",),
    "Ramón": ("Moncho",),
    "Juan": ("Juancho",),
    "Carlos": ("Carlitos", "Calicho"),
    "Jorge": ("Coque",),
    "Javier": ("Javi",),
    "Margarita": ("Margo", "Mago"),
    "Consuelo": ("Chelo",),
    "Socorro": ("Coco",),
    "Mercedes": ("Meche",),
    "Dolores": ("Lola",),
    "Rosario": ("Charo",),
    "Concepción": ("Concha",),
    "Isabel": ("Chabela",),
    "Carolina": ("Caro", "Carito"),
    "Catalina": ("Cata",),
    "Valentina": ("Vale",),
    "Mariana": ("Mari",),
    "María": ("Mari", "Mayo"),
    "Patricia": ("Paty",),
    "Teresa": ("Tere",),
    "Beatriz": ("Betty",),
    "Natalia": ("Naty", "Nata"),
    "Jacqueline": ("Jacky",),
    "Jackeline": ("Jacky",),
    "Elizabeth": ("Eli", "Liz"),
    "Yolanda": ("Yoli",),
    "Ana": ("Anita",),
    "Juana": ("Juanita",),
    "Marta": ("Martica",),
    "Martha": ("Martica",),
    "Alexander": ("Alex",),
    "Alexandra": ("Alex",),
    "Cristina": ("Cris",),
    "Andrea": ("Andre",),
    "Sofía": ("Sofi",),
    "Camila": ("Cami",),
    "Lucía": ("Lucy",),
    "Graciela": ("Chela",),
    "Esperanza": ("Pera",),
    "Gilberto": ("Gilber",),
    "Humberto": ("Beto",),
    "Ernesto": ("Neto",),
    "Gregorio": ("Goyo",),
}

# Variantes ortográficas de un mismo nombre (lista propia).
_GRUPOS_VARIANTES: tuple[tuple[str, ...], ...] = (
    ("Jhon", "John", "Jon"),
    ("Jonathan", "Jhonatan", "Jonatan", "Johnatan"),
    ("Yésica", "Jessica", "Yessica", "Yéssica"),
    ("Yeferson", "Jefferson", "Jeferson", "Yefferson"),
    ("Estiven", "Steven", "Stiven", "Esteven"),
    ("Brayan", "Bryan", "Brian"),
    ("Johana", "Yohana", "Johanna", "Jhoana"),
    ("Katherine", "Katerine", "Catherine", "Katherin", "Kathering"),
    ("Cristian", "Christian", "Cristhian", "Kristian"),
    ("Lizeth", "Liseth", "Lisbeth", "Liceth", "Lisseth"),
    ("Yuli", "Yuly", "Julie"),
    ("Miryam", "Miriam", "Myriam", "Mirian"),
    ("Martha", "Marta"),
    ("Gladis", "Gladys"),
    ("Edison", "Edinson", "Edisson"),
    ("William", "Willian", "Wiliam"),
    ("Stella", "Estela", "Estella"),
    ("Yaneth", "Janeth", "Yanet", "Janneth"),
    ("Yenny", "Jenny", "Yeny"),
    ("Jeisson", "Jeison", "Yeison"),
    ("Vanesa", "Vanessa"),
    ("Yasmín", "Yazmín", "Jazmín"),
    ("Esther", "Ester"),
    ("Freddy", "Fredy"),
    ("Giovanni", "Giovanny", "Geovanny", "Yovany"),
    ("Duván", "Dubán"),
    ("Leidy", "Leydi", "Lady"),
    ("Julieth", "Yulieth", "Juliet"),
    ("Deisy", "Deicy", "Daisy"),
    ("Nathalia", "Natalia"),
    ("Ximena", "Jimena"),
    ("Óscar", "Oscar"),
    ("Mayerly", "Mayerli"),
    ("Sindy", "Cindy"),
    ("Yuri", "Yury"),
    ("Michael", "Maicol", "Mike"),
    ("Edwar", "Edward", "Eduar", "Eduard"),
)
VARIANTES_NOMBRE: dict[str, tuple[str, ...]] = {
    nombre: tuple(v for v in grupo if v != nombre)
    for grupo in _GRUPOS_VARIANTES
    for nombre in grupo
}

_FEMENINOS_SIN_A: frozenset[str] = frozenset(
    """Luz Carmen Mery Inés Isabel Raquel Ruth Esther Ester Beatriz Rocío Consuelo Amparo Pilar
    Socorro Rosario Cielo Flor Mabel Nancy Doris Gladys Gladis Astrid Ingrid Edith Judith
    Elizabeth Lisbeth Liseth Lizeth Liceth Yaneth Janeth Janneth Yanet Yineth Julieth Yulieth
    Ibeth Enith Marlén Marlene Marleny Leydi Leidy Lady Yenny Jenny Yeny Wendy Kelly Betty Lucy
    Dolly Nelly Fanny Ruby Nury Yudy Yuly Yuli Yuri Yury Mary Dary Marly Derly Mayerly Yeimy
    Heidy Cindy Sindy Shirley Jennifer Yenifer Karen Carol Karol Catherine Katherine Katherin
    Katerine Jackeline Jacqueline Geraldine Lilian Miriam Mirian Miryam Myriam Yasmín Yazmín
    Jazmín Yamile Mercedes Dolores Margoth Elcy Elsy Nelcy Nelsy Deicy Deisy Emilce Emilse Alix
    Iris Ivonne Magaly Maribel Marisol Leonor Abigail Michel Nayibe""".split()
)
_MASCULINOS_CON_A: frozenset[str] = frozenset({"Garcilaso", "Bautista", "Nicola", "Luca"})

_VEREDAS: tuple[str, ...] = (
    "El Carmen", "La Esperanza", "San Isidro", "El Palmar", "Santa Rosa", "La Unión",
    "El Rosal", "Las Brisas", "Alto Bonito", "La Floresta", "El Diviso", "Pueblo Nuevo",
    "Guayabal", "Los Naranjos", "La Cristalina", "Buenavista", "El Tablazo", "Quebrada Honda",
    "San Antonio", "La Laguna", "El Retiro", "Monte Redondo", "Agua Bonita", "Peñas Blancas",
)  # fmt: skip
_FINCAS: tuple[str, ...] = (
    "La Esperanza", "El Recreo", "Villa Luz", "Los Almendros", "El Paraíso", "La Fortuna",
    "Bella Vista", "Mi Ranchito", "Los Guaduales", "La Primavera", "El Edén", "San José",
    "Las Palmas", "El Porvenir", "La Ceiba", "Villa María", "Los Cerezos", "El Mirador",
)  # fmt: skip
_BARRIOS: tuple[str, ...] = (
    "Centro", "San Fernando", "El Prado", "La Floresta", "Villa del Río", "Los Alpes",
    "Santa Isabel", "El Poblado", "Kennedy", "Galán", "La Esmeralda", "Las Américas",
    "San Martín", "Altos del Lago", "Los Rosales", "Ciudad Jardín", "El Bosque", "Primero de Mayo",
)  # fmt: skip
_CONJUNTOS: tuple[str, ...] = (
    "Conjunto Los Pinos",
    "Conj. Reservas del Parque",
    "Edificio Mirador",
    "Urb. Villa Sol",
    "Torres de la Sabana",
    "Conjunto Altos de San Juan",
    "Edif. Portal del Norte",
)

_VIAS: dict[str, tuple[str, ...]] = {
    "CL": ("CL", "Calle", "Cll", "CLL", "Cl.", "Cal"),
    "KR": ("KR", "Carrera", "Cra", "Cra.", "KRA", "Cr", "K"),
    "TV": ("TV", "Transversal", "Tv", "Tr", "Transv"),
    "DG": ("DG", "Diagonal", "Dg", "Diag"),
    "AV": ("AV", "Avenida", "Av.", "Avda"),
}
_CUADRANTES: dict[str, tuple[str, ...]] = {
    "SUR": ("SUR", "Sur", "S"),
    "ESTE": ("ESTE", "Este", "E"),
}

_VARIANTES_CIUDAD: dict[str, tuple[str, ...]] = {
    "Bogotá, D.C.": ("Bogotá", "Bogota", "BOGOTA D.C.", "Bogotá D.C", "Santafé de Bogotá", "Bta"),
    "Cartagena de Indias": ("Cartagena", "CARTAGENA", "Ctg"),
    "Medellín": ("Medellin", "MEDELLIN", "Mede"),
    "Barranquilla": ("B/quilla", "Barranquila", "BARRANQUILLA"),
    "Cali": ("Santiago de Cali", "CALI"),
    "Bucaramanga": ("B/manga", "Bucaramamga", "BUCARAMANGA"),
}
_VARIANTES_DEPARTAMENTO: dict[str, tuple[str, ...]] = {
    "Bogotá, D.C.": ("Bogotá", "Cundinamarca", "D.C.", "Distrito Capital"),
    "Valle del Cauca": ("Valle", "VALLE"),
    "Norte de Santander": ("N. Santander", "Nte de Santander", "N/Santander"),
    "La Guajira": ("Guajira",),
    "Atlántico": ("Atlantico", "ATL"),
    "Antioquia": ("Ant.", "Antoquia"),
    "Bolívar": ("Bolivar",),
    "Santander": ("Sder", "Santander del Sur"),
}

_DOMINIOS_TIPEO: dict[str, tuple[str, ...]] = {
    "gmail.com": ("gmial.com", "gmail.co", "gamil.com", "gmail.con", "gmail,com", "gmal.com"),
    "hotmail.com": ("hotmal.com", "hotmail.es", "hotmial.com", "hotmail.co", "hotamil.com"),
    "outlook.com": ("outlok.com", "outlook.es", "outloo.com", "otlook.com"),
    "yahoo.com": ("yaho.com", "yahoo.es", "yahho.com", "yahoo.co"),
}
_CORREOS_GENERICOS: tuple[str, ...] = (
    "notiene@notiene.com",
    "sincorreo@gmail.com",
    "no@no.com",
    "notiene@hotmail.com",
    "na@na.com",
    "cliente@correo.com",
)
_CELULARES_FICTICIOS: tuple[str, ...] = ("3000000000", "3111111111", "0000000000", "1234567")

_VECINOS_TECLADO: dict[str, str] = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij",
    "i": "uok", "o": "ipl", "p": "oñ", "a": "qsz", "s": "adwx", "d": "sfec", "f": "dgrv",
    "g": "fhtb", "h": "gjyn", "j": "hkum", "k": "jli", "l": "kñ", "ñ": "lp", "z": "xa",
    "x": "zcs", "c": "xvd", "v": "cbf", "b": "vng", "n": "bmh", "m": "nj",
}  # fmt: skip
_VECINOS_NUMPAD: dict[str, str] = {
    "0": "12", "1": "024", "2": "135", "3": "26", "4": "157", "5": "2468",
    "6": "359", "7": "48", "8": "579", "9": "68",
}  # fmt: skip


# --- Utilidades ------------------------------------------------------------------------


def _txt(valor: Any) -> str | None:
    """Convierte un valor de pandas en ``str`` o ``None``."""
    if valor is None:
        return None
    if isinstance(valor, float) and valor != valor:
        return None
    if pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto or None


def _como_texto(valor: Any) -> str | None:
    """Como ``_txt`` pero sin recortar espacios: conserva los espacios sobrantes capturados."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    texto = str(valor)
    return texto if texto.strip() else None


def _sin_tildes(texto: str) -> str:
    """Quita tildes y diéresis; la ñ se vuelve n."""
    normal = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normal if not unicodedata.combining(c))


def _elegir(rng: random.Random, pesos: dict[str, float]) -> str:
    """Elige una clave según sus pesos (orden de inserción, determinista)."""
    claves = list(pesos)
    return rng.choices(claves, weights=[pesos[c] for c in claves], k=1)[0]


def es_mujer_aparente(primer_nombre: str | None) -> bool:
    """Infere, solo a partir del primer nombre, si la persona parece mujer."""
    if not primer_nombre:
        return False
    nombre = primer_nombre.strip().split()[0].capitalize()
    if nombre in _FEMENINOS_SIN_A:
        return True
    if nombre in _MASCULINOS_CON_A:
        return False
    return _sin_tildes(nombre).lower().endswith("a")


def _tipeo_texto(rng: random.Random, texto: str) -> str:
    """Error de digitación: tecla vecina, letra omitida, duplicada o transpuesta."""
    posiciones = [i for i, c in enumerate(texto) if c.isalpha()]
    if len(posiciones) < 3:
        return texto
    i = rng.choice(posiciones[1:])
    c = texto[i]
    tipo = rng.choice(("vecina", "omitida", "duplicada", "transpuesta"))
    if tipo == "vecina" and c.lower() in _VECINOS_TECLADO:
        nueva = rng.choice(_VECINOS_TECLADO[c.lower()])
        nueva = nueva.upper() if c.isupper() else nueva
        return texto[:i] + nueva + texto[i + 1 :]
    if tipo == "omitida":
        return texto[:i] + texto[i + 1 :]
    if tipo == "duplicada":
        return texto[:i] + c + texto[i:]
    if i + 1 < len(texto) and texto[i + 1].isalpha():
        return texto[:i] + texto[i + 1] + c + texto[i + 2 :]
    return texto[:i] + texto[i + 1 :]


# Sustituciones fonéticas (lo que se oye igual por teléfono): (patrón, reemplazo).
_FONETICAS: tuple[tuple[str, str], ...] = (
    ("v", "b"), ("b", "v"), ("z", "s"), ("s", "z"), ("ce", "se"), ("ci", "si"),
    ("se", "ce"), ("ll", "y"), ("y", "ll"), ("ge", "je"), ("gi", "ji"), ("je", "ge"),
    ("x", "j"), ("qu", "k"), ("h", ""), ("rr", "r"), ("ñ", "ni"), ("ez", "es"), ("es", "ez"),
)  # fmt: skip


def _fonetico(rng: random.Random, texto: str) -> str:
    """Aplica una sustitución fonética al azar entre las que encajan en el texto."""
    bajo = texto.lower()
    opciones = [(p, r) for p, r in _FONETICAS if p in bajo]
    if not opciones:
        return texto
    patron, reemplazo = rng.choice(opciones)
    inicios = [i for i in range(len(bajo)) if bajo.startswith(patron, i)]
    i = rng.choice(inicios)
    original = texto[i : i + len(patron)]
    if original[:1].isupper():
        reemplazo = reemplazo.capitalize() if reemplazo else ""
        if i + len(patron) < len(texto) and not reemplazo:
            # Al quitar una h inicial, la siguiente letra pasa a mayúscula.
            return texto[:i] + texto[i + 1].upper() + texto[i + 2 :]
    return texto[:i] + reemplazo + texto[i + len(patron) :]


def _mojibake(rng: random.Random, texto: str) -> str:
    """Daño de codificación: UTF-8 leído como Latin-1, o signos de interrogación."""
    if all(ord(c) < 128 for c in texto):
        return texto
    if rng.random() < 0.6:
        return texto.encode("utf-8").decode("latin-1")
    marca = rng.choice(("?", "�", "#"))
    return "".join(c if ord(c) < 128 else marca for c in texto)


def _caja(texto: str | None, modo: str) -> str | None:
    if texto is None:
        return None
    if modo == "mayus":
        return texto.upper()
    if modo == "minus":
        return texto.lower()
    if modo == "titulo":
        return " ".join(p.capitalize() for p in texto.split(" "))
    return texto


def _digitos(texto: str | None) -> str:
    return "".join(c for c in (texto or "") if c.isdigit())


def _alterar_digitos(rng: random.Random, numero: str, tipo: str) -> str:
    """Altera una cadena de dígitos de la forma indicada."""
    if len(numero) < 3:
        return numero + str(rng.randint(0, 9))
    i = rng.randrange(len(numero))
    if tipo == "cambiado":
        nuevo = rng.choice(_VECINOS_NUMPAD.get(numero[i], "0123456789"))
        if nuevo == numero[i]:
            nuevo = str((int(numero[i]) + 1) % 10)
        return numero[:i] + nuevo + numero[i + 1 :]
    if tipo == "transpuesto":
        j = rng.randrange(len(numero) - 1)
        if numero[j] == numero[j + 1]:
            return _alterar_digitos(rng, numero, "cambiado")
        return numero[:j] + numero[j + 1] + numero[j] + numero[j + 2 :]
    if tipo == "omitido":
        return numero[:i] + numero[i + 1 :]
    if tipo == "repetido":
        return numero[:i] + numero[i] + numero[i:]
    if tipo == "truncado":
        return numero[: rng.randint(max(3, len(numero) - 3), len(numero) - 1)]
    return numero


def _sumar_anios(fecha: date, anios: int) -> date:
    try:
        return fecha.replace(year=fecha.year + anios)
    except ValueError:
        return fecha.replace(year=fecha.year + anios, day=28)


# --- Direcciones -------------------------------------------------------------------------


def _direccion_urbana_nueva(rng: random.Random) -> dict[str, Any]:
    """Genera una dirección urbana nueva (para mudanzas)."""
    via = _elegir(rng, {"CL": 0.45, "KR": 0.4, "TV": 0.06, "DG": 0.05, "AV": 0.04})
    numero = str(rng.randint(1, 160))
    if rng.random() < 0.3:
        numero += rng.choice("ABCD")
    cuadrante = _elegir(rng, {"": 0.8, "SUR": 0.12, "ESTE": 0.08}) or None
    placa = str(rng.randint(1, 140)) + (rng.choice("ABC") if rng.random() < 0.15 else "")
    return {
        "tipo": "urbana",
        "via": via,
        "numero": numero,
        "cuadrante": cuadrante,
        "placa": placa,
        "consecutivo": str(rng.randint(2, 99)),
        "complemento": _complemento(rng),
        "barrio": rng.choice(_BARRIOS),
    }


def _complemento(rng: random.Random) -> str:
    tipo = _elegir(rng, {"apto": 0.45, "torre": 0.25, "casa": 0.15, "int": 0.15})
    if tipo == "apto":
        return f"Apto {rng.randint(1, 20)}{rng.randint(0, 1)}{rng.randint(1, 8)}"
    if tipo == "torre":
        return f"Torre {rng.randint(1, 9)} Apto {rng.randint(101, 1204)}"
    if tipo == "casa":
        return f"Casa {rng.randint(1, 80)}"
    return f"Int {rng.randint(1, 12)}"


def _direccion_rural_nueva(rng: random.Random, ciudad: str | None) -> dict[str, Any]:
    """Genera una dirección rural (vereda, finca, kilómetro o corregimiento)."""
    return {
        "tipo": "rural",
        "vereda": rng.choice(_VEREDAS),
        "finca": rng.choice(_FINCAS),
        "km": rng.randint(1, 45),
        "corregimiento": rng.choice(_VEREDAS),
        "via_a": ciudad or "el pueblo",
        "lote": rng.randint(1, 30),
        "forma": _elegir(
            rng, {"vereda_finca": 0.5, "km": 0.2, "corregimiento": 0.15, "lote": 0.15}
        ),
    }


def _render_urbana(rng: random.Random, d: dict[str, Any], con_cuadrante: bool) -> str:
    """Escribe una dirección urbana en uno de varios estilos de captura."""
    via = rng.choice(_VIAS[d["via"]])
    numero = d["numero"]
    corte = len(numero) - len(numero.lstrip("0123456789"))
    base, resto = numero[:corte], numero[corte:].strip()
    if resto:
        numero_txt = rng.choice((f"{base}{resto}", f"{base} {resto}", f"{base}{resto.lower()}"))
    else:
        numero_txt = numero
    placa, cons = d["placa"], d["consecutivo"]
    estilo = rng.choice(("canonico", "largo", "plano", "numero", "compacto", "guion"))
    if estilo == "canonico":
        txt = f"{via} {numero_txt} # {placa}-{cons}"
    elif estilo == "largo":
        txt = f"{via} {numero_txt} No. {placa} - {cons}"
    elif estilo == "plano":
        txt = f"{via} {numero_txt} {placa} {cons}"
    elif estilo == "numero":
        txt = f"{via} {numero_txt} N° {placa}-{cons}"
    elif estilo == "compacto":
        txt = f"{via}{numero_txt.replace(' ', '')} #{placa}-{cons}"
    else:
        txt = f"{via} {numero_txt} {placa}-{cons}"
    if d["cuadrante"] and con_cuadrante:
        txt += " " + rng.choice(_CUADRANTES[d["cuadrante"]])
    return txt


def _render_rural(rng: random.Random, d: dict[str, Any]) -> str:
    """Escribe una dirección rural, a veces completa y a veces a medias."""
    forma = d["forma"]
    if rng.random() < 0.1:
        return rng.choice(("Zona rural", "Rural", "Area rural", "ZONA RURAL"))
    vereda = rng.choice(("Vereda", "Vda", "Vda.", "VDA"))
    finca = rng.choice(("Finca", "Fca", "Fca.", "Hacienda"))
    if forma == "vereda_finca":
        opciones = (
            f"{vereda} {d['vereda']} {finca} {d['finca']}",
            f"{finca} {d['finca']} {vereda} {d['vereda']}",
            f"{vereda} {d['vereda']}",
            f"{finca} {d['finca']}",
        )
        return rng.choices(opciones, weights=(0.45, 0.2, 0.2, 0.15), k=1)[0]
    if forma == "km":
        via = rng.choice(("vía a", "via", "Km", "carretera a"))
        opciones = (
            f"Km {d['km']} {via} {d['via_a']}".replace("Km Km", "Km"),
            f"Kilómetro {d['km']} vía {d['via_a']} {finca} {d['finca']}",
            f"{finca} {d['finca']} km {d['km']}",
        )
        return rng.choice(opciones)
    if forma == "corregimiento":
        corr = rng.choice(("Corregimiento", "Correg.", "Corr"))
        opciones = (
            f"{corr} {d['corregimiento']} Casa {d['lote']}",
            f"{corr} {d['corregimiento']}",
            f"{corr} {d['corregimiento']} {vereda} {d['vereda']}",
        )
        return rng.choice(opciones)
    opciones = (
        f"Lote {d['lote']} {vereda} {d['vereda']}",
        f"Parcela {d['lote']} {vereda} {d['vereda']}",
        f"{vereda} {d['vereda']} Lote {d['lote']}",
    )
    return rng.choice(opciones)


# --- Persona en el tiempo ---------------------------------------------------------------


@dataclass
class _Persona:
    """Estado verdadero de una persona y los eventos de su vida que afectan los registros."""

    cluster: int
    tipo_documento: str
    numero_documento: str
    primer_nombre: str
    segundo_nombre: str | None
    primer_apellido: str
    segundo_apellido: str | None
    fecha_nacimiento: str
    celular: str | None
    correo: str | None
    ciudad: str | None
    departamento: str | None
    direccion: dict[str, Any]
    familiar: int | None
    mujer: bool
    apodo: str | None = None
    casada: tuple[float, str, str] | None = None  # (momento, apellido esposo, forma)
    separacion: tuple[float, str | None] | None = None  # (momento, nuevo apellido o None)
    mudanza: tuple[float, dict[str, Any], str | None, str | None] | None = None
    celular_nuevo: tuple[float, str] | None = None
    correo_nuevo: tuple[float, str] | None = None
    tarjeta_identidad: bool = False


def _direccion_base(rng: random.Random, fila: pd.Series, rural: bool) -> dict[str, Any]:
    if rural:
        return _direccion_rural_nueva(rng, _txt(fila.get("ciudad")))
    via = _txt(fila.get("direccion_via"))
    if via is None or via not in _VIAS:
        return _direccion_urbana_nueva(rng)
    return {
        "tipo": "urbana",
        "via": via,
        "numero": _txt(fila.get("direccion_numero_via")) or str(rng.randint(1, 99)),
        "cuadrante": _txt(fila.get("direccion_cuadrante")),
        "placa": _txt(fila.get("direccion_placa")) or str(rng.randint(1, 99)),
        "consecutivo": _txt(fila.get("direccion_consecutivo")) or str(rng.randint(2, 99)),
        "complemento": _complemento(rng),
        "barrio": rng.choice(_BARRIOS),
    }


def _celular_nuevo(rng: random.Random) -> str:
    prefijo = rng.choice(("300", "301", "304", "310", "311", "313", "314", "315", "316", "317"))
    prefijo = rng.choice((prefijo, "320", "321", "322", "350", "351"))
    return prefijo + "".join(str(rng.randint(0, 9)) for _ in range(7))


def _correo_nuevo(rng: random.Random, p: _Persona) -> str:
    nombre = _sin_tildes(p.primer_nombre).lower().replace(" ", "")
    apellido = _sin_tildes(p.primer_apellido).lower().replace(" ", "")
    usuario = rng.choice(
        (
            f"{nombre}{apellido}{rng.randint(1, 99)}",
            f"{nombre}.{apellido}",
            f"{nombre[0]}{apellido}{p.fecha_nacimiento[2:4]}",
            f"{apellido}{nombre[:3]}",
            f"{nombre}_{rng.randint(100, 999)}",
        )
    )
    return f"{usuario}@{rng.choice(('gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com'))}"


def _construir_persona(
    rng: random.Random, fila: pd.Series, tasas: TasasCiegas3, pool_apellidos: list[str],
    pool_lugares: list[tuple[str, str]],
) -> _Persona:  # fmt: skip
    """Sortea los eventos de vida de una persona (matrimonio, mudanza, etc.)."""
    primer_nombre = _txt(fila["primer_nombre"]) or "Sin"
    rural = rng.random() < tasas.rural
    p = _Persona(
        cluster=int(fila["cluster"]),
        tipo_documento=_txt(fila["tipo_documento"]) or "CC",
        numero_documento=_txt(fila["numero_documento"]) or "",
        primer_nombre=primer_nombre,
        segundo_nombre=_txt(fila.get("segundo_nombre")),
        primer_apellido=_txt(fila["primer_apellido"]) or "",
        segundo_apellido=_txt(fila.get("segundo_apellido")),
        fecha_nacimiento=_txt(fila["fecha_nacimiento"]) or "1980-01-01",
        celular=_txt(fila.get("celular")),
        correo=_txt(fila.get("correo")),
        ciudad=_txt(fila.get("ciudad")),
        departamento=_txt(fila.get("departamento")),
        direccion=_direccion_base(rng, fila, rural),
        familiar=None if _txt(fila.get("familiar_de")) is None else int(fila["familiar_de"]),
        mujer=es_mujer_aparente(primer_nombre),
    )
    anio = int(p.fecha_nacimiento[:4])

    if primer_nombre in APODOS and rng.random() < tasas.apodo:
        p.apodo = rng.choice(APODOS[primer_nombre])

    if p.mujer and anio <= 2003 and rng.random() < tasas.casada:
        esposo = rng.choice([a for a in pool_apellidos if a != p.primer_apellido])
        forma = _elegir(
            rng,
            {
                "de_sin_segundo": 0.35,  # Gómez de Pérez
                "de_con_segundo": 0.20,  # Gómez Cabrera de Pérez
                "en_segundo": 0.25,  # Gómez Pérez (ocupa el lugar del segundo apellido)
                "solo_casada": 0.12,  # Pérez / de Pérez
                "casada_primero": 0.08,  # Pérez Gómez
            },
        )
        p.casada = (rng.uniform(0.0, 0.7), esposo, forma)
        if rng.random() < tasas.separacion_o_nuevo:
            nuevo = None
            if rng.random() < 0.45:
                nuevo = rng.choice(
                    [a for a in pool_apellidos if a not in (esposo, p.primer_apellido)]
                )
            p.separacion = (rng.uniform(p.casada[0] + 0.1, 1.0), nuevo)

    if rng.random() < tasas.mudanza:
        if rng.random() < tasas.mudanza_otra_ciudad and pool_lugares:
            ciudad, depto = rng.choice(pool_lugares)
        else:
            ciudad, depto = p.ciudad, p.departamento
        if p.direccion["tipo"] == "rural" and rng.random() < 0.5:
            nueva = _direccion_urbana_nueva(rng)
        elif p.direccion["tipo"] == "urbana" and rng.random() < 0.06:
            nueva = _direccion_rural_nueva(rng, ciudad)
        else:
            nueva = (
                _direccion_rural_nueva(rng, ciudad)
                if p.direccion["tipo"] == "rural"
                else _direccion_urbana_nueva(rng)
            )
        p.mudanza = (rng.uniform(0.05, 0.95), nueva, ciudad, depto)

    if rng.random() < tasas.cambio_celular:
        p.celular_nuevo = (rng.uniform(0.05, 0.95), _celular_nuevo(rng))
    if rng.random() < tasas.cambio_correo:
        p.correo_nuevo = (rng.uniform(0.05, 0.95), _correo_nuevo(rng, p))
    if anio >= 1988 and p.tipo_documento == "CC" and rng.random() < tasas.tarjeta_identidad:
        p.tarjeta_identidad = True
    return p


def _momentos(rng: random.Random, n: int, eventos: list[float]) -> list[float]:
    """Momentos de captura en [0, 1], ordenados.

    Con dos o más registros se procura que algún evento de vida quede en medio, para que
    haya registros de antes y de después.
    """
    momentos = sorted(rng.random() for _ in range(n))
    if n >= 2 and eventos:
        e = rng.choice(eventos)
        if not (momentos[0] < e < momentos[-1]):
            momentos[0] = rng.uniform(0.0, e)
            momentos[-1] = rng.uniform(e, 1.0)
            momentos.sort()
    return momentos


# --- Captura de un registro --------------------------------------------------------------


class _Captura:
    """Construye registros de una persona y anota la traza de errores."""

    def __init__(
        self,
        rng: random.Random,
        tasas: TasasCiegas3,
        personas: dict[int, _Persona],
        clusters: list[int],
    ) -> None:
        self.rng = rng
        self.tasas = tasas
        self.personas = personas
        self.clusters = clusters
        self.traza: list[tuple[int, str]] = []

    def _p(self, canal: str, nombre: str) -> float:
        base = getattr(self.tasas, nombre)
        return min(1.0, base * _MULTIPLICADORES.get(canal, {}).get(nombre, 1.0))

    def _si(self, canal: str, nombre: str) -> bool:
        return self.rng.random() < self._p(canal, nombre)

    def _anotar(self, indice: int, error: str) -> None:
        self.traza.append((indice, error))

    # Nombres -----------------------------------------------------------------
    def _nombres(self, indice: int, canal: str, p: _Persona) -> str:
        rng = self.rng
        primer, segundo = p.primer_nombre, p.segundo_nombre
        if p.apodo and self._si(canal, "apodo_por_registro"):
            primer = p.apodo
            if segundo and rng.random() < 0.7:
                segundo = None
            self._anotar(indice, "apodo")
        elif primer in VARIANTES_NOMBRE and self._si(canal, "variante_nombre"):
            primer = rng.choice(VARIANTES_NOMBRE[primer])
            self._anotar(indice, "variante_nombre")
        if segundo:
            if self._si(canal, "usa_segundo_nombre"):
                primer, segundo = segundo, None
                self._anotar(indice, "usa_segundo_nombre")
            elif self._si(canal, "segundo_nombre_omitido"):
                segundo = None
                self._anotar(indice, "segundo_nombre_omitido")
            elif self._si(canal, "segundo_nombre_inicial"):
                segundo = segundo[0] + rng.choice((".", ""))
                self._anotar(indice, "segundo_nombre_inicial")
        elif segundo is None and self.rng.random() < 0.01:
            # Un digitador completa un segundo nombre que no existe (lo oyó del cliente).
            segundo = rng.choice(("María", "José", "Del Carmen", "Antonio", "Andrea"))
            self._anotar(indice, "segundo_nombre_inventado")
        texto = f"{primer} {segundo}" if segundo else primer
        if self._si(canal, "nombre_fonetico"):
            texto = _fonetico(rng, texto)
            self._anotar(indice, "nombre_fonetico")
        if self._si(canal, "nombre_tipeo"):
            texto = _tipeo_texto(rng, texto)
            self._anotar(indice, "nombre_tipeo")
        if " " in texto and self._si(canal, "nombres_pegados"):
            texto = texto.replace(" ", "", 1)
            self._anotar(indice, "nombres_pegados")
        return texto

    # Apellidos ---------------------------------------------------------------
    def _apellidos(self, indice: int, canal: str, p: _Persona, momento: float) -> str:
        rng = self.rng
        a1, a2 = p.primer_apellido, p.segundo_apellido
        esposo: str | None = None
        forma = ""
        if p.casada and momento >= p.casada[0]:
            esposo, forma = p.casada[1], p.casada[2]
            if p.separacion and momento >= p.separacion[0]:
                esposo = p.separacion[1]
                self._anotar(indice, "nuevo_matrimonio" if esposo else "separacion")
        if esposo:
            if forma == "de_sin_segundo":
                texto = f"{a1} de {esposo}"
            elif forma == "de_con_segundo":
                texto = f"{a1} {a2} de {esposo}" if a2 else f"{a1} de {esposo}"
            elif forma == "en_segundo":
                texto = f"{a1} {esposo}"
            elif forma == "solo_casada":
                texto = rng.choice((esposo, f"de {esposo}"))
            else:
                texto = f"{esposo} {a1}"
            if rng.random() < 0.15:
                texto = texto.replace(" de ", " De ").replace("de ", "De ", 1)
            self._anotar(indice, f"apellido_casada:{forma}")
        else:
            if a2 and self._si(canal, "segundo_apellido_omitido"):
                a2 = None
                self._anotar(indice, "segundo_apellido_omitido")
            texto = f"{a1} {a2}" if a2 else a1
        if self._si(canal, "apellido_fonetico"):
            texto = _fonetico(rng, texto)
            self._anotar(indice, "apellido_fonetico")
        if self._si(canal, "apellido_tipeo"):
            texto = _tipeo_texto(rng, texto)
            self._anotar(indice, "apellido_tipeo")
        return texto

    # Documento -----------------------------------------------------------------
    def _documento(
        self, indice: int, canal: str, p: _Persona, es_primero: bool
    ) -> tuple[str | None, str | None]:
        rng = self.rng
        tipo, numero = p.tipo_documento, p.numero_documento
        if p.tarjeta_identidad and es_primero:
            # Registro de cuando la persona era menor de edad: tarjeta de identidad.
            anio = int(p.fecha_nacimiento[:4])
            tipo = "TI"
            if anio < 2001:
                numero = p.fecha_nacimiento[2:].replace("-", "") + "".join(
                    str(rng.randint(0, 9)) for _ in range(5)
                )
                self._anotar(indice, "tarjeta_identidad_numero_distinto")
            else:
                self._anotar(indice, "tarjeta_identidad_nuip")
        if self._si(canal, "sin_documento"):
            self._anotar(indice, "sin_documento")
            return (tipo if rng.random() < 0.3 else None), None
        if self._si(canal, "documento_alterado"):
            pesos = {
                "cambiado": 0.30,
                "transpuesto": 0.20,
                "omitido": 0.11,
                "repetido": 0.09,
                "truncado": 0.05,
                "digito_verificacion": 0.07,
                "familiar": 0.08,
                "celular_en_documento": 0.04,
                "pasaporte": 0.03,
                "ce_a_cc": 0.03,
            }
            forma = _elegir(rng, pesos)
            familiar = self.personas.get(p.familiar) if p.familiar is not None else None
            if forma == "familiar" and familiar is None:
                forma = "cambiado"
            if forma in ("pasaporte", "ce_a_cc") and p.tipo_documento != "CE":
                forma = "transpuesto"
            if forma == "digito_verificacion":
                numero = f"{numero}-{rng.randint(0, 9)}"
            elif forma == "familiar" and familiar is not None:
                numero = familiar.numero_documento
                tipo = familiar.tipo_documento
            elif forma == "celular_en_documento":
                numero = p.celular or _celular_nuevo(rng)
            elif forma == "pasaporte":
                tipo = "PA"
                numero = rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") + rng.choice("ABCDEFGHJKLMNPRSTVXZ")
                numero += "".join(str(rng.randint(0, 9)) for _ in range(6))
            elif forma == "ce_a_cc":
                tipo = "CC"
                numero = "1" + "".join(str(rng.randint(0, 9)) for _ in range(9))
            else:
                numero = _alterar_digitos(rng, numero, forma)
            self._anotar(indice, f"documento_alterado:{forma}")
        if self._si(canal, "documento_formato"):
            forma = rng.choice(("puntos", "espacios", "prefijo", "ceros", "guion"))
            if forma == "puntos" and numero.isdigit():
                numero = f"{int(numero):,}".replace(",", ".")
            elif forma == "espacios" and numero.isdigit():
                numero = " ".join(numero[max(0, i - 3) : i] for i in range(len(numero), 0, -3))
                numero = " ".join(reversed(numero.split(" ")))
            elif forma == "prefijo":
                numero = f"{tipo}{rng.choice(('', ' ', '-'))}{numero}"
            elif forma == "ceros":
                numero = "00" + numero
            elif forma == "guion" and numero.isdigit():
                numero = f"{numero[:-3]}-{numero[-3:]}"
            self._anotar(indice, f"documento_formato:{forma}")
        if self._si(canal, "tipo_documento_errado"):
            tipo = {"CC": "CE", "CE": "CC", "TI": "CC", "PA": "CE"}.get(tipo, "CC")
            self._anotar(indice, "tipo_documento_errado")
        elif self._si(canal, "tipo_documento_formato"):
            formatos = {
                "CC": ("C.C.", "Cédula", "CEDULA", "cc", "Cedula de ciudadania", "1"),
                "CE": ("C.E.", "Cédula de extranjería", "ce", "CEDULA EXTRANJERIA", "2"),
                "TI": ("T.I.", "Tarjeta de identidad", "ti", "3"),
                "PA": ("Pasaporte", "PAS", "pa"),
            }
            tipo = rng.choice(formatos.get(tipo, (tipo,)))
            self._anotar(indice, "tipo_documento_formato")
        return tipo, numero

    # Fecha -----------------------------------------------------------------------
    def _fecha(self, indice: int, canal: str, p: _Persona) -> str | None:
        rng = self.rng
        if self._si(canal, "fecha_faltante"):
            self._anotar(indice, "fecha_faltante")
            return None
        if self._si(canal, "fecha_defecto"):
            self._anotar(indice, "fecha_defecto")
            return rng.choice(("1900-01-01", "1901-01-01", "1999-12-31", "2000-01-01"))
        f = date.fromisoformat(p.fecha_nacimiento)
        if self._si(canal, "fecha_expedicion"):
            f = _sumar_anios(f, 18) + timedelta(days=rng.randint(0, 120))
            self._anotar(indice, "fecha_expedicion")
        elif f.day <= 12 and f.day != f.month and self._si(canal, "fecha_dia_mes"):
            f = date(f.year, f.day, f.month)
            self._anotar(indice, "fecha_dia_mes")
        elif self._si(canal, "fecha_tipeo"):
            forma = rng.choice(("anio_digito", "anio_transpuesto", "dia_vecino", "mes_vecino"))
            try:
                if forma == "anio_digito":
                    f = f.replace(year=f.year + rng.choice((-10, -1, 1, 10)))
                elif forma == "anio_transpuesto" and f.year % 10 != (f.year // 10) % 10:
                    y = str(f.year)
                    f = f.replace(year=int(y[:2] + y[3] + y[2]))
                elif forma == "dia_vecino":
                    f = f + timedelta(days=rng.choice((-1, 1)))
                else:
                    f = f.replace(month=min(12, max(1, f.month + rng.choice((-1, 1)))))
            except ValueError:
                f = f + timedelta(days=1)
            self._anotar(indice, f"fecha_tipeo:{forma}")
        if self._si(canal, "fecha_formato"):
            forma = rng.choice(("dd/mm/aaaa", "dd-mm-aaaa", "aaaa/mm/dd", "aaaammdd", "d/m/aaaa"))
            self._anotar(indice, f"fecha_formato:{forma}")
            if forma == "dd/mm/aaaa":
                return f.strftime("%d/%m/%Y")
            if forma == "dd-mm-aaaa":
                return f.strftime("%d-%m-%Y")
            if forma == "aaaa/mm/dd":
                return f.strftime("%Y/%m/%d")
            if forma == "aaaammdd":
                return f.strftime("%Y%m%d")
            return f"{f.day}/{f.month}/{f.year}"
        return f.isoformat()

    # Celular ---------------------------------------------------------------------
    def _celular(self, indice: int, canal: str, p: _Persona, momento: float) -> str | None:
        rng = self.rng
        numero = p.celular
        if p.celular_nuevo and momento >= p.celular_nuevo[0]:
            numero = p.celular_nuevo[1]
            self._anotar(indice, "celular_nuevo")
        if self._si(canal, "celular_faltante") or numero is None:
            self._anotar(indice, "celular_faltante")
            return None
        if self._si(canal, "celular_ficticio"):
            self._anotar(indice, "celular_ficticio")
            return rng.choice(_CELULARES_FICTICIOS)
        if self._si(canal, "celular_fijo"):
            indicativo = rng.choice(("601", "604", "602", "605", "607"))
            fijo = "".join(str(rng.randint(0, 9)) for _ in range(7))
            self._anotar(indice, "celular_fijo")
            return rng.choice((indicativo + fijo, fijo, f"({indicativo[1:]}) {fijo}"))
        if self._si(canal, "celular_tipeo"):
            numero = _alterar_digitos(
                rng, numero, rng.choice(("cambiado", "transpuesto", "omitido"))
            )
            self._anotar(indice, "celular_tipeo")
        if self._si(canal, "celular_formato") and len(numero) == 10:
            forma = rng.choice(("espacios", "mas57", "57", "parentesis", "guiones"))
            self._anotar(indice, f"celular_formato:{forma}")
            if forma == "espacios":
                return f"{numero[:3]} {numero[3:6]} {numero[6:]}"
            if forma == "mas57":
                return f"+57 {numero}"
            if forma == "57":
                return f"57{numero}"
            if forma == "parentesis":
                return f"({numero[:3]}) {numero[3:]}"
            return f"{numero[:3]}-{numero[3:6]}-{numero[6:]}"
        return numero

    # Correo ----------------------------------------------------------------------
    def _correo(self, indice: int, canal: str, p: _Persona, momento: float) -> str | None:
        rng = self.rng
        correo = p.correo
        if p.correo_nuevo and momento >= p.correo_nuevo[0]:
            correo = p.correo_nuevo[1]
            self._anotar(indice, "correo_nuevo")
        if self._si(canal, "correo_faltante") or correo is None:
            self._anotar(indice, "correo_faltante")
            return None
        if self._si(canal, "correo_generico"):
            self._anotar(indice, "correo_generico")
            return rng.choice(_CORREOS_GENERICOS)
        if self._si(canal, "correo_tipeo") and "@" in correo:
            usuario, dominio = correo.split("@", 1)
            if dominio in _DOMINIOS_TIPEO and rng.random() < 0.6:
                dominio = rng.choice(_DOMINIOS_TIPEO[dominio])
                self._anotar(indice, "correo_tipeo:dominio")
            else:
                usuario = _tipeo_texto(rng, usuario)
                self._anotar(indice, "correo_tipeo:usuario")
            correo = f"{usuario}@{dominio}"
        if self._si(canal, "correo_mayusculas"):
            correo = correo.upper() if rng.random() < 0.6 else correo.capitalize()
            self._anotar(indice, "correo_mayusculas")
        if rng.random() < 0.01:
            correo = rng.choice((f" {correo}", f"{correo} ", f"{correo}."))
            self._anotar(indice, "correo_espacios")
        return correo

    # Dirección -------------------------------------------------------------------
    def _ubicacion(
        self, indice: int, canal: str, p: _Persona, momento: float
    ) -> tuple[str | None, str | None, str | None]:
        rng = self.rng
        direccion, ciudad, depto = p.direccion, p.ciudad, p.departamento
        nueva = False
        if p.mudanza and momento >= p.mudanza[0]:
            direccion, ciudad, depto = p.mudanza[1], p.mudanza[2], p.mudanza[3]
            nueva = True
        if self._si(canal, "direccion_faltante"):
            texto = None
            self._anotar(indice, "direccion_faltante")
        else:
            if direccion["tipo"] == "rural":
                texto = _render_rural(rng, direccion)
                self._anotar(indice, "direccion_rural")
            else:
                con_cuadrante = not self._si(canal, "direccion_cuadrante_omitido")
                texto = _render_urbana(rng, direccion, con_cuadrante)
                if self._si(canal, "direccion_complemento"):
                    extra = rng.choice(
                        (
                            direccion["complemento"],
                            f"{direccion['complemento']} {rng.choice(_CONJUNTOS)}",
                            f"Barrio {direccion['barrio']}",
                            f"{direccion['complemento']} B/ {direccion['barrio']}",
                        )
                    )
                    texto = f"{texto} {extra}"
                    self._anotar(indice, "direccion_complemento")
                if self._si(canal, "direccion_tipeo"):
                    digitos = [i for i, c in enumerate(texto) if c.isdigit()]
                    if digitos:
                        i = rng.choice(digitos)
                        texto = texto[:i] + rng.choice(_VECINOS_NUMPAD[texto[i]]) + texto[i + 1 :]
                    self._anotar(indice, "direccion_tipeo")
            if nueva:
                self._anotar(indice, "mudanza_direccion_nueva")
        if nueva:
            self._anotar(indice, "mudanza_ubicacion_nueva")
        if ciudad and self._si(canal, "ciudad_faltante"):
            ciudad = None
            self._anotar(indice, "ciudad_faltante")
        elif ciudad and self._si(canal, "ciudad_variante"):
            opciones = _VARIANTES_CIUDAD.get(ciudad, ()) + (_sin_tildes(ciudad).upper(),)
            ciudad = rng.choice(opciones)
            self._anotar(indice, "ciudad_variante")
        if depto and self._si(canal, "departamento_faltante"):
            depto = None
            self._anotar(indice, "departamento_faltante")
        elif depto and depto in _VARIANTES_DEPARTAMENTO and rng.random() < 0.2:
            depto = rng.choice(_VARIANTES_DEPARTAMENTO[depto])
            self._anotar(indice, "departamento_variante")
        return texto, ciudad, depto

    # Registro completo -------------------------------------------------------------
    def registro(
        self, indice: int, p: _Persona, canal: str, momento: float, es_primero: bool
    ) -> dict[str, Any]:
        """Captura un registro de la persona ``p`` en el canal y momento dados."""
        rng = self.rng
        self._anotar(indice, f"canal:{canal}")
        tipo, numero = self._documento(indice, canal, p, es_primero)
        nombres = self._nombres(indice, canal, p)
        apellidos = self._apellidos(indice, canal, p, momento)
        fecha = self._fecha(indice, canal, p)
        celular = self._celular(indice, canal, p, momento)
        correo = self._correo(indice, canal, p, momento)
        direccion, ciudad, depto = self._ubicacion(indice, canal, p, momento)

        # Datos de un familiar (contacto o dirección de la casa de la familia).
        familiar = self.personas.get(p.familiar) if p.familiar is not None else None
        if familiar is not None and self._si(canal, "dato_familiar"):
            campo = rng.choice(("celular", "correo", "direccion"))
            if campo == "celular" and familiar.celular:
                celular = familiar.celular
            elif campo == "correo" and familiar.correo:
                correo = familiar.correo
            else:
                campo = "direccion"
                if familiar.direccion["tipo"] == "rural":
                    direccion = _render_rural(rng, familiar.direccion)
                else:
                    direccion = _render_urbana(rng, familiar.direccion, True)
                ciudad, depto = familiar.ciudad, familiar.departamento
            self._anotar(indice, f"dato_familiar:{campo}")

        # Arrastre: el digitador deja un dato del cliente anterior en pantalla.
        if self._si(canal, "arrastre_otro_cliente"):
            otro = self.personas[rng.choice(self.clusters)]
            if otro.cluster != p.cluster:
                campo = rng.choice(("celular", "correo", "direccion", "fecha"))
                if campo == "celular":
                    celular = otro.celular
                elif campo == "correo":
                    correo = otro.correo
                elif campo == "fecha":
                    fecha = otro.fecha_nacimiento
                elif otro.direccion["tipo"] == "rural":
                    direccion = _render_rural(rng, otro.direccion)
                    ciudad, depto = otro.ciudad, otro.departamento
                else:
                    direccion = _render_urbana(rng, otro.direccion, True)
                    ciudad, depto = otro.ciudad, otro.departamento
                self._anotar(indice, f"arrastre_otro_cliente:{campo}")

        # Todo el nombre en un solo campo, o nombres y apellidos cruzados.
        if self._si(canal, "nombre_completo_en_un_campo"):
            if rng.random() < 0.5:
                nombres, apellidos = f"{nombres} {apellidos}", None
            else:
                nombres, apellidos = f"{apellidos} {nombres}", None
            self._anotar(indice, "nombre_completo_en_un_campo")
        elif self._si(canal, "nombres_apellidos_cruzados"):
            nombres, apellidos = apellidos, nombres
            self._anotar(indice, "nombres_apellidos_cruzados")

        # Formato de texto: tildes, codificación y mayúsculas.
        if self._si(canal, "sin_tildes"):
            nombres = _sin_tildes(nombres) if nombres else nombres
            apellidos = _sin_tildes(apellidos) if apellidos else apellidos
            direccion = _sin_tildes(direccion) if direccion else direccion
            self._anotar(indice, "sin_tildes")
        elif self._si(canal, "codificacion"):
            nombres = _mojibake(rng, nombres) if nombres else nombres
            apellidos = _mojibake(rng, apellidos) if apellidos else apellidos
            if ciudad and rng.random() < 0.5:
                ciudad = _mojibake(rng, ciudad)
            self._anotar(indice, "codificacion")
        pesos = dict(zip(("mayus", "titulo", "minus", "tal_cual"), _CAJA_CANAL[canal], strict=True))
        modo = _elegir(rng, pesos)
        if modo != "tal_cual":
            nombres, apellidos = _caja(nombres, modo), _caja(apellidos, modo)
            direccion = _caja(direccion, modo)
            if rng.random() < 0.5:
                ciudad, depto = _caja(ciudad, modo), _caja(depto, modo)
            self._anotar(indice, f"caja:{modo}")
        if rng.random() < 0.02 and nombres:
            nombres = rng.choice((f" {nombres}", f"{nombres}  ", nombres.replace(" ", "  ")))
            self._anotar(indice, "espacios_sobrantes")

        registro = {
            "tipo_documento": tipo,
            "numero_documento": numero,
            "nombres": nombres,
            "apellidos": apellidos,
            "fecha_nacimiento": fecha,
            "celular": celular,
            "correo": correo,
            "direccion": direccion,
            "ciudad": ciudad,
            "departamento": depto,
        }
        self._asegurar_identificable(indice, registro, p)
        return registro

    def _asegurar_identificable(self, indice: int, registro: dict[str, Any], p: _Persona) -> None:
        """Garantiza que el registro conserve datos suficientes para identificar a la persona."""
        if not registro["nombres"] and not registro["apellidos"]:
            registro["nombres"] = p.primer_nombre
            registro["apellidos"] = p.primer_apellido
        claves = ("numero_documento", "fecha_nacimiento", "celular", "correo", "direccion")
        presentes = sum(1 for c in claves if registro[c])
        if presentes < 2:
            if not registro["fecha_nacimiento"]:
                registro["fecha_nacimiento"] = p.fecha_nacimiento
            if not registro["celular"] and p.celular:
                registro["celular"] = p.celular
            self._anotar(indice, "restaurado_identificable")
        for clave, valor in registro.items():
            if valor is not None:
                valor = str(valor)
                registro[clave] = valor if valor.strip() else None


# --- Interfaz pública --------------------------------------------------------------------


def describir_tasas(tasas: TasasCiegas3 | None = None) -> dict[str, Any]:
    """Devuelve las tasas como diccionario (para guardarlas junto a los resultados)."""
    tasas = tasas or TasasCiegas3()
    datos = dataclasses.asdict(tasas)
    datos["pesos_n_registros"] = list(tasas.pesos_n_registros)
    datos["pesos_canal"] = dict(zip(CANALES, tasas.pesos_canal, strict=True))
    datos["multiplicadores_canal"] = {c: dict(m) for c, m in _MULTIPLICADORES.items()}
    return datos


def capturar_con_traza(
    personas: pd.DataFrame, semilla: int = 0, tasas: TasasCiegas3 | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Como :func:`capturar`, pero devuelve además la traza ``(unique_id, error)``."""
    tasas = tasas or TasasCiegas3()
    rng = random.Random(semilla)
    personas = personas.sort_values("cluster", kind="stable").reset_index(drop=True)

    pool_apellidos = sorted({a for a in personas["primer_apellido"].dropna().astype(str)})
    lugares = personas[["ciudad", "departamento"]].dropna().astype(str)
    pool_lugares = list(lugares.itertuples(index=False, name=None))

    modelo: dict[int, _Persona] = {}
    for _, fila in personas.iterrows():
        p = _construir_persona(rng, fila, tasas, pool_apellidos, pool_lugares)
        modelo[p.cluster] = p
    clusters = list(modelo)
    captura = _Captura(rng, tasas, modelo, clusters)

    filas: list[dict[str, Any]] = []
    tamanos = range(1, len(tasas.pesos_n_registros) + 1)
    for cluster in clusters:
        p = modelo[cluster]
        n = rng.choices(list(tamanos), weights=tasas.pesos_n_registros, k=1)[0]
        eventos = [
            e
            for e in (
                p.casada[0] if p.casada else None,
                p.separacion[0] if p.separacion else None,
                p.mudanza[0] if p.mudanza else None,
                p.celular_nuevo[0] if p.celular_nuevo else None,
            )
            if e is not None
        ]
        momentos = _momentos(rng, n, eventos)
        for k, momento in enumerate(momentos):
            canal = rng.choices(CANALES, weights=tasas.pesos_canal, k=1)[0]
            indice = len(filas)
            registro = captura.registro(indice, p, canal, momento, es_primero=(k == 0))
            registro["cluster"] = cluster
            filas.append(registro)

    # Barajar y asignar unique_id.
    orden = list(range(len(filas)))
    rng.shuffle(orden)
    nuevo_id = {viejo: nuevo for nuevo, viejo in enumerate(orden)}
    registros = pd.DataFrame([filas[i] for i in orden])
    registros.insert(0, "unique_id", range(len(registros)))
    registros["unique_id"] = registros["unique_id"].astype("int64")
    registros["cluster"] = registros["cluster"].astype("int64")
    texto = [c for c in COLUMNAS if c not in ("unique_id", "cluster")]
    registros[texto] = registros[texto].astype(object)
    registros = registros[COLUMNAS]
    for c in texto:
        registros[c] = pd.Series(
            [_como_texto(v) for v in registros[c]], index=registros.index, dtype=object
        )

    traza = pd.DataFrame(
        [(nuevo_id[i], e) for i, e in captura.traza], columns=["unique_id", "error"]
    )
    traza = traza.sort_values(["unique_id"], kind="stable").reset_index(drop=True)
    traza["unique_id"] = traza["unique_id"].astype("int64")

    condiciones = _condiciones(registros, traza, modelo)
    return registros, condiciones, traza


def capturar(
    personas: pd.DataFrame, semilla: int = 0, tasas: TasasCiegas3 | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genera los registros capturados y las condiciones por persona.

    Args:
        personas: tabla de personas verdaderas de ``identidades.sinteticos.generar``.
        semilla: semilla del generador aleatorio (misma semilla, mismo resultado).
        tasas: tasas de error; por defecto ``TasasCiegas3()``.

    Returns:
        ``(registros, condiciones)``: registros con las columnas de ``COLUMNAS`` y una fila
        por persona con sus condiciones booleanas y ``n_registros``.
    """
    registros, condiciones, _ = capturar_con_traza(personas, semilla=semilla, tasas=tasas)
    return registros, condiciones


def _condiciones(
    registros: pd.DataFrame, traza: pd.DataFrame, modelo: dict[int, _Persona]
) -> pd.DataFrame:
    """Condiciones por persona, verdaderas solo si se manifestaron en algún registro."""
    cluster_de = dict(zip(registros["unique_id"], registros["cluster"], strict=True))
    errores_por_cluster: dict[int, set[str]] = {c: set() for c in modelo}
    for uid, error in zip(traza["unique_id"], traza["error"], strict=True):
        errores_por_cluster[cluster_de[uid]].add(error)

    def tiene(cluster: int, criterio: Callable[[str], bool]) -> bool:
        return any(criterio(e) for e in errores_por_cluster[cluster])

    sin_doc = registros.groupby("cluster")["numero_documento"].apply(lambda s: s.isna().any())
    verdadero = {c: p.numero_documento for c, p in modelo.items()}

    def alterado(fila: pd.Series) -> bool:
        if fila["numero_documento"] is None:
            return False
        dig = _digitos(fila["numero_documento"]).lstrip("0")
        return dig != verdadero[int(fila["cluster"])].lstrip("0")

    marca_alterado = registros.apply(alterado, axis=1)
    doc_alterado = marca_alterado.groupby(registros["cluster"]).any()
    n_registros = registros.groupby("cluster").size()

    filas = []
    for cluster, p in modelo.items():
        filas.append(
            {
                "cluster": cluster,
                "apellido_casada": tiene(cluster, lambda e: e.startswith("apellido_casada")),
                "separacion_o_nuevo_matrimonio": tiene(
                    cluster, lambda e: e in ("separacion", "nuevo_matrimonio")
                ),
                "con_apodo": tiene(cluster, lambda e: e == "apodo"),
                "rural": tiene(cluster, lambda e: e == "direccion_rural"),
                "mudanza": tiene(cluster, lambda e: e == "mudanza_direccion_nueva"),
                "cambio_celular": tiene(cluster, lambda e: e == "celular_nuevo"),
                "sin_documento": bool(sin_doc.get(cluster, False)),
                "documento_alterado": bool(doc_alterado.get(cluster, False)),
                "tarjeta_identidad": tiene(cluster, lambda e: e.startswith("tarjeta_identidad")),
                "datos_ajenos": tiene(
                    cluster,
                    lambda e: e.startswith("dato_familiar") or e.startswith("arrastre_otro"),
                ),
                "mujer_aparente": p.mujer,
                "n_registros": int(n_registros.get(cluster, 0)),
            }
        )
    condiciones = pd.DataFrame(filas)
    condiciones["cluster"] = condiciones["cluster"].astype("int64")
    for c in CONDICIONES:
        condiciones[c] = condiciones[c].astype(bool)
    condiciones["n_registros"] = condiciones["n_registros"].astype("int64")
    return condiciones
