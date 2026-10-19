"""Prueba ciega 4: base de clientes sintética de un banco colombiano.

Generador escrito desde cero, sin mirar los modelos ni los generadores anteriores. Produce
tres tablas:

- ``registros``: lo que quedó capturado en la base del banco (varios registros por persona,
  en canales y momentos distintos, con errores de digitación, de formato, faltantes y datos
  de relleno).
- ``personas``: la verdad de cada persona (familia, hogar, predio y unidad de su residencia
  más reciente, apellido de casada).
- ``sospechosos``: los valores compartidos de forma sospechosa que se inyectaron a propósito.

Realidades que se simulan: parejas que solo comparten la dirección, compañeros de
apartamento y estudiantes, edificios y conjuntos con muchos hogares sin relación (torre,
bloque, interior, apartamento o casa escritos de muchas formas u omitidos), casas de varios
pisos donde un hijo construyó su hogar encima de los padres, apellido de casada, hijos con
el primer apellido de cada padre, mudanzas, unidades que ocupa un hogar después de otro,
teléfono fijo del hogar, correo de un familiar, cambios de documento (tarjeta de identidad
a cédula, pasaporte a permiso de protección temporal) y valores de relleno compartidos por
personas sin relación (que no son sospechosos).

Todo es sintético: nombres de Faker (``es_CO``) y listas inventadas. Las fechas se calculan
desde fechas fijas, nunca desde el reloj, así que la misma semilla da siempre lo mismo.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
from faker import Faker

INICIO = date(2010, 1, 1)
FIN = date(2025, 12, 31)
ORIGEN = date(1900, 1, 1)  # "desde siempre" para la primera residencia conocida
CAMBIO_FIJOS = date(2021, 9, 1)  # desde aquí los fijos se marcan con indicativo de 3 cifras

CANALES = ("sucursal", "app", "web", "call_center", "corresponsal")
COLUMNAS_REGISTROS = [
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
    "fecha_actualizacion",
    "canal",
    "validado",
    "origen",
]
COLUMNAS_PERSONAS = [
    "cluster",
    "mujer",
    "familia",
    "hogar",
    "rol",
    "tipo_hogar",
    "predio",
    "tipo_predio",
    "unidad",
    "usa_apellido_casada",
]
COLUMNAS_SOSPECHOSOS = ["tipo", "valor", "personas"]


@dataclass(frozen=True)
class Ciudad:
    """Ciudad con sus formas de escribirse, su departamento y barrios inventados."""

    nombre: str
    departamento: str
    peso: float
    indicativo: str
    variantes: tuple[str, ...]
    variantes_depto: tuple[str, ...]
    barrios: tuple[str, ...]
    vecina: str | None = None  # ciudad que la gente a veces escribe en su lugar


CIUDADES: tuple[Ciudad, ...] = (
    Ciudad(
        "Bogotá",
        "Bogotá D.C.",
        0.33,
        "601",
        ("Bogotá", "Bogota", "BOGOTA", "Bogotá D.C.", "BOGOTA D.C.", "Bogota DC", "Bta"),
        ("Bogotá D.C.", "Cundinamarca", "BOGOTA", "Distrito Capital", "Bogota D.C"),
        ("Kennedy", "Suba", "Chapinero", "Engativá", "Bosa", "Usaquén", "Fontibón", "Modelia"),
    ),
    Ciudad(
        "Medellín",
        "Antioquia",
        0.14,
        "604",
        ("Medellín", "Medellin", "MEDELLIN", "Mdellin", "Medellín Antioquia"),
        ("Antioquia", "ANTIOQUIA", "Ant."),
        ("Laureles", "Belén", "Robledo", "Manrique", "Aranjuez", "Buenos Aires"),
    ),
    Ciudad(
        "Cali",
        "Valle del Cauca",
        0.10,
        "602",
        ("Cali", "CALI", "Santiago de Cali", "cali"),
        ("Valle del Cauca", "Valle", "VALLE", "Valle Del Cauca"),
        ("El Ingenio", "San Fernando", "Siloé", "Alfonso López", "La Flora"),
    ),
    Ciudad(
        "Barranquilla",
        "Atlántico",
        0.08,
        "605",
        ("Barranquilla", "BARRANQUILLA", "Barranquila", "B/quilla"),
        ("Atlántico", "Atlantico", "ATLANTICO"),
        ("El Prado", "Boston", "Riomar", "La Victoria", "Las Nieves"),
    ),
    Ciudad(
        "Bucaramanga",
        "Santander",
        0.05,
        "607",
        ("Bucaramanga", "BUCARAMANGA", "B/manga", "Bucaramnga"),
        ("Santander", "SANTANDER", "Sder"),
        ("Cabecera", "San Alonso", "La Concordia", "Provenza"),
    ),
    Ciudad(
        "Cartagena",
        "Bolívar",
        0.05,
        "605",
        ("Cartagena", "CARTAGENA", "Cartagena de Indias", "Ctg"),
        ("Bolívar", "Bolivar", "BOLIVAR"),
        ("Manga", "Crespo", "El Bosque", "Olaya Herrera", "Torices"),
    ),
    Ciudad(
        "Pereira",
        "Risaralda",
        0.04,
        "606",
        ("Pereira", "PEREIRA"),
        ("Risaralda", "RISARALDA"),
        ("Cuba", "Álamos", "Boston", "El Jardín"),
    ),
    Ciudad(
        "Manizales",
        "Caldas",
        0.03,
        "606",
        ("Manizales", "MANIZALES", "Manizalez"),
        ("Caldas", "CALDAS"),
        ("Chipre", "La Enea", "Palermo"),
    ),
    Ciudad(
        "Ibagué",
        "Tolima",
        0.03,
        "608",
        ("Ibagué", "Ibague", "IBAGUE"),
        ("Tolima", "TOLIMA"),
        ("Picaleña", "El Jardín", "Cádiz"),
    ),
    Ciudad(
        "Villavicencio",
        "Meta",
        0.03,
        "608",
        ("Villavicencio", "VILLAVICENCIO", "Villavo"),
        ("Meta", "META"),
        ("El Barzal", "La Esperanza", "Porfía"),
    ),
    Ciudad(
        "Cúcuta",
        "Norte de Santander",
        0.04,
        "607",
        ("Cúcuta", "Cucuta", "CUCUTA", "San José de Cúcuta"),
        ("Norte de Santander", "N. de Santander", "NORTE DE SANTANDER", "Nte Santander"),
        ("La Riviera", "Atalaya", "Caobos", "La Libertad"),
    ),
    Ciudad(
        "Soacha",
        "Cundinamarca",
        0.04,
        "601",
        ("Soacha", "SOACHA"),
        ("Cundinamarca", "CUNDINAMARCA", "Cund."),
        ("Ciudad Verde", "León XIII", "San Mateo", "Compartir"),
        vecina="Bogotá",
    ),
    Ciudad(
        "Bello",
        "Antioquia",
        0.03,
        "604",
        ("Bello", "BELLO"),
        ("Antioquia", "ANTIOQUIA"),
        ("Niquía", "Cabañas", "París"),
        vecina="Medellín",
    ),
    Ciudad(
        "Pasto",
        "Nariño",
        0.01,
        "602",
        ("Pasto", "PASTO", "San Juan de Pasto"),
        ("Nariño", "Narino", "NARIÑO"),
        ("Las Cuadras", "Obrero", "Pandiaco"),
    ),
)
_IDX_CIUDAD = {c.nombre: i for i, c in enumerate(CIUDADES)}

VIAS: dict[str, tuple[float, tuple[str, ...]]] = {
    "Calle": (0.42, ("Calle", "CL", "Cll", "Cl", "CALLE", "Cl.")),
    "Carrera": (0.38, ("Carrera", "KR", "Cra", "Kra", "CRA", "Cr", "Cra.")),
    "Diagonal": (0.07, ("Diagonal", "DG", "Diag", "Dg")),
    "Transversal": (0.07, ("Transversal", "TV", "Tv", "Transv", "Trans")),
    "Avenida Calle": (0.03, ("Avenida Calle", "AC", "Av Calle", "Av. Cl")),
    "Avenida Carrera": (0.03, ("Avenida Carrera", "AK", "Av Cra", "Av. Carrera")),
}
PREFIJOS_CONJUNTO = (
    "Altos de",
    "Torres de",
    "Mirador de",
    "Portal de",
    "Reservas de",
    "Balcones de",
    "Bosques de",
    "Prados de",
    "Villas de",
    "Jardines de",
    "Parque",
    "Senderos de",
)
SUFIJOS_CONJUNTO = (
    "San José",
    "la Pradera",
    "Oriente",
    "Castilla",
    "Madrid",
    "la Colina",
    "los Andes",
    "Santa Fe",
    "Alcalá",
    "Granada",
    "Sevilla",
    "Aragón",
    "Fátima",
    "la Sierra",
    "Bellavista",
    "los Cerezos",
)
NOMBRES_M_EXTRA = (
    "Jhon",
    "Brayan",
    "Stiven",
    "Yeison",
    "Jhonatan",
    "Wilmer",
    "Edwin",
    "Yesid",
    "Duvan",
    "Arley",
    "Fredy",
    "Alexander",
    "Didier",
)
NOMBRES_F_EXTRA = (
    "Yeimy",
    "Leidy",
    "Yuliana",
    "Lizeth",
    "Yesica",
    "Johana",
    "Dayana",
    "Yenny",
    "Marisol",
    "Deisy",
    "Yurany",
    "Mayerli",
    "Nidia",
)
VARIANTES_NOMBRE: dict[str, tuple[str, ...]] = {
    "Jhon": ("John", "Jon"),
    "Brayan": ("Bryan", "Brallan"),
    "Stiven": ("Steven", "Estiven"),
    "Yeison": ("Jeison", "Yeisson"),
    "Jhonatan": ("Jonathan", "Yonatan", "Jhonathan"),
    "Yeimy": ("Jeimy", "Yeimi"),
    "Leidy": ("Leydi", "Lady"),
    "Lizeth": ("Liseth", "Lisseth"),
    "Yesica": ("Jessica", "Yessica"),
    "Johana": ("Yohana", "Joana", "Johanna"),
    "Yenny": ("Jenny", "Yeni"),
    "Duvan": ("Duban", "Dubán"),
    "Mayerli": ("Mayerly", "Mayerlin"),
    "Deisy": ("Daisy", "Deysi"),
    "Yurany": ("Yurani", "Llurany"),
    "Edwin": ("Edwing",),
    "Wilmer": ("Wilmar",),
}
REGLAS_FONETICAS = (
    ("v", "b"),
    ("b", "v"),
    ("ll", "y"),
    ("y", "ll"),
    ("z", "s"),
    ("s", "z"),
    ("ce", "se"),
    ("ci", "si"),
    ("ge", "je"),
    ("gi", "ji"),
    ("je", "ge"),
    ("h", ""),
    ("rr", "r"),
    ("nn", "n"),
    ("x", "j"),
)
DOMINIOS = (
    ("gmail.com", 0.48),
    ("hotmail.com", 0.25),
    ("outlook.com", 0.08),
    ("yahoo.com", 0.05),
    ("yahoo.es", 0.04),
    ("hotmail.es", 0.04),
    ("live.com", 0.03),
    ("une.net.co", 0.02),
    ("etb.net.co", 0.01),
)
DOMINIOS_U = (
    "unal.edu.co",
    "udea.edu.co",
    "javeriana.edu.co",
    "uniandes.edu.co",
    "unicauca.edu.co",
)
ERRATAS_DOMINIO: dict[str, tuple[str, ...]] = {
    "gmail.com": ("gmial.com", "gmail.co", "gmai.com", "gmail.con", "gamil.com", "g.mail.com"),
    "hotmail.com": ("hotmal.com", "hotmail.co", "hotmial.com", "hotmail.con", "homail.com"),
    "outlook.com": ("outlok.com", "outlook.co", "outloo.com"),
    "yahoo.com": ("yaho.com", "yahoo.co", "yahooo.com"),
    "yahoo.es": ("yaho.es", "yahoo.ed"),
    "hotmail.es": ("hotmail.e", "hotmal.es"),
}
CORREOS_RELLENO = (
    "notiene@gmail.com",
    "sincorreo@hotmail.com",
    "no@no.com",
    "ninguno@ninguno.com",
    "notiene@notiene.com",
    "correo@correo.com",
)
CELULARES_RELLENO = ("3000000000", "3111111111", "0000000000", "1234567", "3001234567")
DIRECCIONES_RELLENO = ("NA", "Sin dirección", "CONOCIDA", "No registra", "xxx", "Ciudad")
FECHAS_RELLENO = ("1900-01-01", "01/01/1900", "1901-01-01")
PREFIJOS_CEL = (
    "300",
    "301",
    "302",
    "304",
    "305",
    "310",
    "311",
    "312",
    "313",
    "314",
    "315",
    "316",
    "317",
    "318",
    "319",
    "320",
    "321",
    "322",
    "323",
    "324",
    "350",
    "351",
)
VECINAS_TECLADO = {
    "a": "sqz",
    "b": "vng",
    "c": "xvd",
    "d": "sfe",
    "e": "wrd",
    "f": "dgr",
    "g": "fht",
    "h": "gjy",
    "i": "uok",
    "j": "hku",
    "k": "jli",
    "l": "kño",
    "m": "nj",
    "n": "bmh",
    "o": "ipl",
    "p": "oñ",
    "q": "wa",
    "r": "etf",
    "s": "adw",
    "t": "ryg",
    "u": "yij",
    "v": "cbf",
    "w": "qes",
    "x": "zcs",
    "y": "tuh",
    "z": "xas",
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _sin_tildes(texto: str) -> str:
    """Quita tildes y diéresis (la ñ también pierde la virgulilla)."""
    normal = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normal if not unicodedata.combining(c))


def _slug(texto: str) -> str:
    """Convierte un texto en una parte válida de un correo."""
    return "".join(c for c in _sin_tildes(texto).lower() if c.isalnum())


def _fecha_entre(rng: random.Random, a: date, b: date) -> date:
    """Fecha uniforme entre ``a`` y ``b`` (ambas incluidas)."""
    if b <= a:
        return a
    return a + timedelta(days=rng.randint(0, (b - a).days))


def _mas_anios(d: date, anios: int) -> date:
    """Suma años a una fecha; el 29 de febrero cae en el 28 si hace falta."""
    try:
        return d.replace(year=d.year + anios)
    except ValueError:
        return d.replace(year=d.year + anios, day=28)


def _elegir(rng: random.Random, pares: tuple[tuple[str, float], ...] | list) -> str:
    """Elige un valor de una lista de pares (valor, peso)."""
    valores = [v for v, _ in pares]
    pesos = [p for _, p in pares]
    return rng.choices(valores, weights=pesos)[0]


def _errata(texto: str, rng: random.Random) -> str:
    """Introduce una errata de digitación: cambio por tecla vecina, omisión, duplicado o
    transposición de dos letras."""
    if len(texto) < 3:
        return texto
    pos = [i for i, c in enumerate(texto) if c.isalpha()]
    if len(pos) < 2:
        return texto
    i = rng.choice(pos[1:])  # rara vez se equivoca en la primera letra
    op = rng.random()
    if op < 0.35:
        c = texto[i]
        vecinas = VECINAS_TECLADO.get(_sin_tildes(c.lower()), "")
        if not vecinas:
            return texto
        nueva = rng.choice(vecinas)
        nueva = nueva.upper() if c.isupper() else nueva
        return texto[:i] + nueva + texto[i + 1 :]
    if op < 0.6:
        return texto[:i] + texto[i + 1 :]
    if op < 0.75:
        return texto[:i] + texto[i] + texto[i:]
    if i + 1 < len(texto) and texto[i + 1].isalpha():
        return texto[:i] + texto[i + 1] + texto[i] + texto[i + 2 :]
    return texto[:i] + texto[i + 1 :]


def _fonetica(texto: str, rng: random.Random) -> str:
    """Cambia una letra o sílaba por otra que suena igual (como se escucha por teléfono)."""
    bajo = texto.lower()
    aplicables = [r for r in REGLAS_FONETICAS if r[0] in bajo[1:] or bajo.startswith(r[0])]
    if not aplicables:
        return texto
    viejo, nuevo = rng.choice(aplicables)
    posiciones = [i for i in range(len(bajo)) if bajo.startswith(viejo, i)]
    i = rng.choice(posiciones)
    reemplazo = nuevo
    if texto[i].isupper() and nuevo:
        reemplazo = nuevo[0].upper() + nuevo[1:]
    return texto[:i] + reemplazo + texto[i + len(viejo) :]


def _errata_digito(numero: str, rng: random.Random) -> str:
    """Cambia, transpone u omite un dígito de una cadena numérica."""
    digitos = [i for i, c in enumerate(numero) if c.isdigit()]
    if len(digitos) < 3:
        return numero
    op = rng.random()
    i = rng.choice(digitos[1:])
    if op < 0.55:
        nuevo = str((int(numero[i]) + rng.choice([1, 2, 7, 8, 9])) % 10)
        return numero[:i] + nuevo + numero[i + 1 :]
    if op < 0.85:
        j = digitos[digitos.index(i) - 1]
        lista = list(numero)
        lista[i], lista[j] = lista[j], lista[i]
        return "".join(lista)
    return numero[:i] + numero[i + 1 :]


# ---------------------------------------------------------------------------
# Modelo interno
# ---------------------------------------------------------------------------


@dataclass
class Predio:
    """Lote o edificación con una dirección base."""

    id: int
    tipo: str  # casa, casa_pisos, edificio, conjunto
    ciudad: int
    via: str
    numero: str
    placa1: str
    placa2: str
    sur: bool
    nombre: str | None
    barrio: str
    estilo: str = ""  # para conjuntos: torre, bloque, interior o casa
    dims: tuple[int, int, int] = (0, 0, 0)
    usadas: list[str] = field(default_factory=list)


@dataclass
class Persona:
    """Persona verdadera con su historia (residencias, teléfonos, correos, documentos)."""

    mujer: bool
    nombres: str
    apellido1: str
    apellido2: str
    nacimiento: date
    familia: int
    rol: str
    cluster: int = -1
    tipo_hogar: str = ""
    hogar: int = -1
    extranjera: bool = False
    estudiante: bool = False
    tipo_doc: str = "CC"
    documento: str = ""
    docs_previos: list[tuple[date, str, str]] = field(default_factory=list)  # (hasta, tipo, n)
    residencias: list[tuple[date, Predio, str | None]] = field(default_factory=list)
    celulares: list[tuple[date, str]] = field(default_factory=list)
    correos: list[tuple[date, str]] = field(default_factory=list)
    apellido_esposo: str | None = None
    fijo: str | None = None
    correo_familiar: str | None = None
    cliente: bool = True
    uso_casada: bool = False  # si algún registro quedó con el apellido de casada

    def en(self, lista: list, fecha: date):
        """Devuelve el elemento vigente en ``fecha`` de una lista ordenada (desde, ...)."""
        vigente = lista[0]
        for item in lista:
            if item[0] <= fecha:
                vigente = item
        return vigente


class _Generador:
    """Construye la población, su historia y los registros capturados."""

    def __init__(self, semilla: int) -> None:
        self.rng = random.Random(semilla)
        self.fake = Faker("es_CO")
        self.fake.seed_instance(semilla)
        self.predios: list[Predio] = []
        self.pool: dict[tuple[int, str], list[Predio]] = {}
        self.bases: set[tuple[int, str, str, str, str]] = set()
        self.docs: set[str] = set()
        self.cels: set[str] = set()
        self.correos: set[str] = set()
        self.fijos: set[str] = set()
        self.personas: list[Persona] = []
        self.n_hogar = 0
        self.n_familia = 0

    # -- identificadores -------------------------------------------------------

    def _familia(self) -> int:
        self.n_familia += 1
        return self.n_familia - 1

    def _ciudad(self) -> int:
        return self.rng.choices(range(len(CIUDADES)), weights=[c.peso for c in CIUDADES])[0]

    # -- predios y unidades ----------------------------------------------------

    def _predio_nuevo(self, ciudad: int, tipo: str) -> Predio:
        rng = self.rng
        via = rng.choices(list(VIAS), weights=[v[0] for v in VIAS.values()])[0]
        while True:
            numero = str(rng.randint(1, 170))
            if rng.random() < 0.2:
                numero += rng.choice(["A", "B", "C", " Bis", "A Bis"])
            placa1 = str(rng.randint(1, 140))
            if rng.random() < 0.12:
                placa1 += rng.choice(["A", "B"])
            placa2 = str(rng.randint(1, 99))
            clave = (ciudad, via, numero, placa1, placa2)
            if clave not in self.bases:
                self.bases.add(clave)
                break
        nombre = None
        nombre_inv = f"{rng.choice(PREFIJOS_CONJUNTO)} {rng.choice(SUFIJOS_CONJUNTO)}"
        estilo, dims = "", (0, 0, 0)
        if tipo == "edificio":
            nombre = nombre_inv if rng.random() < 0.6 else None
            dims = (1, rng.randint(3, 15), rng.randint(2, 6))
        elif tipo == "conjunto":
            nombre = nombre_inv
            estilo = _elegir(
                rng, (("torre", 0.45), ("bloque", 0.15), ("interior", 0.1), ("casa", 0.3))
            )
            if estilo == "torre":
                dims = (rng.randint(2, 10), rng.randint(5, 20), rng.randint(4, 8))
            elif estilo == "bloque":
                dims = (rng.randint(3, 15), rng.randint(3, 6), rng.randint(2, 4))
            elif estilo == "interior":
                dims = (rng.randint(2, 12), rng.randint(2, 5), rng.randint(1, 4))
            else:
                dims = (rng.randint(30, 250), 0, 0)
        predio = Predio(
            id=len(self.predios),
            tipo=tipo,
            ciudad=ciudad,
            via=via,
            numero=numero,
            placa1=placa1,
            placa2=placa2,
            sur=CIUDADES[ciudad].nombre in ("Bogotá", "Soacha") and rng.random() < 0.25,
            nombre=nombre,
            barrio=rng.choice(CIUDADES[ciudad].barrios),
            estilo=estilo,
            dims=dims,
        )
        self.predios.append(predio)
        if tipo in ("edificio", "conjunto"):
            self.pool.setdefault((ciudad, tipo), []).append(predio)
        return predio

    def _unidad_libre(self, predio: Predio) -> str | None:
        """Elige una unidad todavía no ocupada por nadie dentro del predio."""
        rng = self.rng
        a, b, c = predio.dims
        for _ in range(40):
            if predio.tipo == "edificio":
                u = f"apto {rng.randint(1, b)}{rng.randint(1, c):02d}"
            elif predio.estilo == "casa":
                u = f"casa {rng.randint(1, a)}"
            else:
                apto = f"apto {rng.randint(1, b)}{rng.randint(1, c):02d}"
                u = f"{predio.estilo} {rng.randint(1, a)} {apto}"
            if u not in predio.usadas:
                predio.usadas.append(u)
                return u
        return None

    def _residencia(self, ciudad: int, tipo: str | None = None) -> tuple[Predio, str | None]:
        """Residencia nueva: casa propia o unidad libre en un edificio o conjunto (a menudo
        uno que ya tiene otros hogares)."""
        rng = self.rng
        if tipo is None:
            tipo = _elegir(rng, (("casa", 0.33), ("edificio", 0.27), ("conjunto", 0.40)))
        if tipo == "casa":
            return self._predio_nuevo(ciudad, "casa"), None
        existentes = self.pool.get((ciudad, tipo), [])
        if existentes and rng.random() < 0.78:
            predio = rng.choice(existentes)
            unidad = self._unidad_libre(predio)
            if unidad is not None:
                return predio, unidad
        predio = self._predio_nuevo(ciudad, tipo)
        return predio, self._unidad_libre(predio)

    def _ciudad_previa(self, ciudad: int, lejos: float = 0.2) -> int:
        return self._ciudad() if self.rng.random() < lejos else ciudad

    # -- personas ----------------------------------------------------------------

    def _nombre(self, mujer: bool, nacimiento: date) -> str:
        rng = self.rng
        gen = self.fake.first_name_female if mujer else self.fake.first_name_male
        extra = NOMBRES_F_EXTRA if mujer else NOMBRES_M_EXTRA
        n1 = rng.choice(extra) if nacimiento.year >= 1975 and rng.random() < 0.22 else gen()
        if rng.random() < 0.5:
            n2 = gen()
            if n2 != n1:
                return f"{n1} {n2}"
        return n1

    def _persona(
        self,
        mujer: bool,
        nacimiento: date,
        familia: int,
        rol: str,
        apellido1: str | None = None,
        apellido2: str | None = None,
    ) -> Persona:
        return Persona(
            mujer=mujer,
            nombres=self._nombre(mujer, nacimiento),
            apellido1=apellido1 or self.fake.last_name(),
            apellido2=apellido2 or self.fake.last_name(),
            nacimiento=nacimiento,
            familia=familia,
            rol=rol,
        )

    def _nac(self, a1: int, a2: int) -> date:
        return _fecha_entre(self.rng, date(a1, 1, 1), date(a2, 12, 31))

    def _hijos(self, madre: Persona | None, padre: Persona | None, n: int, fam: int) -> list:
        """Hijos con el primer apellido del padre y el primero de la madre."""
        rng = self.rng
        base = [p.nacimiento.year for p in (madre, padre) if p is not None]
        hijos = []
        for _ in range(n):
            anio = max(base) + rng.randint(20, 36)
            if anio > 2008:
                continue
            ap1 = padre.apellido1 if padre else self.fake.last_name()
            ap2 = madre.apellido1 if madre else self.fake.last_name()
            if madre and not padre and rng.random() < 0.25:
                ap1, ap2 = madre.apellido1, madre.apellido2  # sin reconocimiento del padre
            hijos.append(
                self._persona(rng.random() < 0.5, self._nac(anio, anio), fam, "hijo", ap1, ap2)
            )
        return hijos

    def _pareja(self, a1: int, a2: int, fam: int) -> tuple[Persona, Persona]:
        """Pareja (casada o en unión libre). Devuelve (mujer, hombre) salvo parejas del mismo
        sexo, que son raras."""
        rng = self.rng
        n1 = self._nac(a1, a2)
        n2 = _mas_anios(n1, rng.randint(-3, 8))
        if rng.random() < 0.03:
            mujer = rng.random() < 0.5
            return (
                self._persona(mujer, n1, fam, "pareja"),
                self._persona(mujer, n2, fam, "pareja"),
            )
        hombre = self._persona(False, n2, fam, "pareja")
        mujer = self._persona(True, n1, fam, "pareja")
        if n1.year < 1982 and rng.random() < 0.6 and rng.random() < 0.55:
            mujer.apellido_esposo = hombre.apellido1
        return mujer, hombre

    # -- hogares ---------------------------------------------------------------

    def _hogar(
        self,
        miembros: list[Persona],
        tipo_hogar: str,
        residencia: tuple[Predio, str | None],
        desde: date = ORIGEN,
        previa: str = "compartida",
        lejos: float = 0.2,
    ) -> None:
        """Asigna hogar y residencia actual; si el hogar llegó en ``desde``, cada miembro sin
        historia recibe una residencia anterior (compartida o individual)."""
        self.n_hogar += 1
        hid = self.n_hogar - 1
        predio, unidad = residencia
        compartida = None
        for m in miembros:
            m.hogar = hid
            m.tipo_hogar = tipo_hogar
            if desde > ORIGEN and not m.residencias:
                if previa == "compartida":
                    if compartida is None:
                        compartida = self._residencia(self._ciudad_previa(predio.ciudad, lejos))
                    m.residencias.append((ORIGEN, *compartida))
                else:
                    anterior = self._residencia(self._ciudad_previa(predio.ciudad, lejos))
                    m.residencias.append((ORIGEN, *anterior))
            m.residencias.append((desde, predio, unidad))

    def _llegada(self, prob: float) -> date:
        """Fecha en que el hogar llegó a su residencia actual (ORIGEN si siempre vivió ahí)."""
        if self.rng.random() < prob:
            return _fecha_entre(self.rng, date(2011, 6, 1), date(2024, 6, 30))
        return ORIGEN

    def _h_solo(self) -> list[Persona]:
        p = self._persona(self.rng.random() < 0.5, self._nac(1945, 2003), self._familia(), "solo")
        self._hogar([p], "solo", self._residencia(self._ciudad()), self._llegada(0.3))
        return [p]

    def _h_pareja(self) -> list[Persona]:
        fam = self._familia()
        m, h = self._pareja(1955, 2000, fam)
        # Antes de vivir juntos cada uno tenía su propia dirección.
        desde = self._llegada(0.4)
        self._hogar([m, h], "pareja", self._residencia(self._ciudad()), desde, "individual")
        return [m, h]

    def _h_familia(self) -> list[Persona]:
        fam = self._familia()
        m, h = self._pareja(1950, 1985, fam)
        hijos = self._hijos(m if m.mujer else None, h, self.rng.randint(1, 3), fam)
        tipo = "familia" if hijos else "pareja"
        self._hogar([m, h, *hijos], tipo, self._residencia(self._ciudad()), self._llegada(0.25))
        return [m, h, *hijos]

    def _h_monoparental(self) -> list[Persona]:
        rng = self.rng
        fam = self._familia()
        mujer = rng.random() < 0.82
        jefe = self._persona(mujer, self._nac(1955, 1985), fam, "jefe")
        hijos = self._hijos(
            jefe if mujer else None, None if mujer else jefe, rng.randint(1, 3), fam
        )
        if not hijos:
            jefe.rol = "solo"
        tipo = "monoparental" if hijos else "solo"
        self._hogar([jefe, *hijos], tipo, self._residencia(self._ciudad()), self._llegada(0.3))
        return [jefe, *hijos]

    def _h_hermanos(self) -> list[Persona]:
        rng = self.rng
        fam = self._familia()
        ap1, ap2 = self.fake.last_name(), self.fake.last_name()
        anio = rng.randint(1975, 2001)
        miembros = [
            self._persona(rng.random() < 0.5, self._nac(anio, anio + 4), fam, "hermano", ap1, ap2)
            for _ in range(rng.randint(2, 3))
        ]
        self._hogar(miembros, "hermanos", self._residencia(self._ciudad()), self._llegada(0.5))
        return miembros

    def _h_convivientes(self) -> list[Persona]:
        """Compañeros de apartamento o estudiantes que comparten arriendo."""
        rng = self.rng
        ciudad = self._ciudad()
        estudiantes = rng.random() < 0.55
        miembros = []
        for _ in range(rng.randint(2, 4)):
            nac = self._nac(1998, 2005) if estudiantes else self._nac(1980, 1998)
            p = self._persona(rng.random() < 0.5, nac, self._familia(), "conviviente")
            p.estudiante = estudiantes
            miembros.append(p)
        tipo = _elegir(rng, (("edificio", 0.45), ("conjunto", 0.3), ("casa", 0.25)))
        desde = _fecha_entre(rng, date(2016, 1, 1), date(2024, 6, 30))
        lejos = 0.6 if estudiantes else 0.25
        self._hogar(
            miembros, "convivientes", self._residencia(ciudad, tipo), desde, "individual", lejos
        )
        return miembros

    def _h_casa_pisos(self) -> list[Persona]:
        """Casa de varios pisos: padres abajo e hijo con su hogar arriba ("le echaron la
        plancha"). Todos son la misma familia."""
        rng = self.rng
        fam = self._familia()
        ciudad = self._ciudad()
        predio = self._predio_nuevo(ciudad, "casa_pisos")
        predio.usadas.extend(["piso 1", "piso 2"])
        if rng.random() < 0.8:
            m, h = self._pareja(1942, 1962, fam)
            padres = [m, h]
            madre, padre = (m if m.mujer else None), h
        else:
            madre = self._persona(True, self._nac(1942, 1962), fam, "jefe")
            padres, padre = [madre], None
        hijos = self._hijos(madre, padre, rng.randint(1, 3), fam)
        if not hijos:
            hijos = [self._persona(rng.random() < 0.5, self._nac(1975, 1990), fam, "hijo")]
        arriba, resto = hijos[0], hijos[1:]
        tercero = resto.pop() if len(resto) >= 2 and rng.random() < 0.5 else None
        # Los demás hijos siguen en casa o ya se fueron (y no son clientes).
        en_casa = resto if rng.random() < 0.6 else []
        miembros_abajo = padres + en_casa
        if len(padres) == 1:
            padres[0].rol = "jefe" if en_casa else "solo"
            tipo_abajo = "monoparental" if en_casa else "solo"
        else:
            tipo_abajo = "familia" if en_casa else "pareja"
        self._hogar(miembros_abajo, tipo_abajo, (predio, "piso 1"), ORIGEN)
        # El hijo vivía en el piso 1 hasta que construyó el piso 2.
        desde = _fecha_entre(rng, date(2012, 1, 1), date(2023, 12, 31))
        arriba.residencias.append((ORIGEN, predio, "piso 1"))
        arriba_hogar = [arriba]
        tipo_arriba = "solo"
        arriba.rol = "solo"
        if rng.random() < 0.75:
            pareja = self._persona(
                not arriba.mujer, _mas_anios(arriba.nacimiento, rng.randint(-4, 4)), fam, "pareja"
            )
            arriba.rol = "pareja"
            arriba_hogar.append(pareja)
            tipo_arriba = "pareja"
            if arriba.mujer and arriba.nacimiento.year < 1982 and rng.random() < 0.3:
                arriba.apellido_esposo = pareja.apellido1
            if arriba.nacimiento.year <= 1986:
                madre2, padre2 = (arriba, pareja) if arriba.mujer else (pareja, arriba)
                nietos = self._hijos(madre2, padre2, rng.randint(0, 2), fam)
                if nietos:
                    arriba_hogar.extend(nietos)
                    tipo_arriba = "familia"
        self._hogar(arriba_hogar, tipo_arriba, (predio, "piso 2"), desde, "individual")
        todos = miembros_abajo + arriba_hogar
        # A veces otro hijo vive solo en un tercer piso.
        if tercero is not None:
            tercero.rol = "solo"
            predio.usadas.append("piso 3")
            tercero.residencias.append((ORIGEN, predio, "piso 1"))
            d3 = _fecha_entre(rng, date(2014, 1, 1), date(2024, 6, 30))
            self._hogar([tercero], "solo", (predio, "piso 3"), d3)
            todos.append(tercero)
        return todos

    def _h_sucesivo(self) -> list[Persona]:
        """Un hogar deja una unidad y otro hogar, sin relación, la ocupa después."""
        rng = self.rng
        ciudad = self._ciudad()
        unidad_compartida = self._residencia(ciudad)
        salida = _fecha_entre(rng, date(2012, 1, 1), date(2022, 12, 31))
        # Hogar A: vivió en la unidad y se mudó.
        tipo_a = _elegir(rng, (("solo", 0.4), ("pareja", 0.35), ("familia", 0.25)))
        fam_a = self._familia()
        if tipo_a == "solo":
            a = [self._persona(rng.random() < 0.5, self._nac(1950, 1998), fam_a, "solo")]
        else:
            m, h = self._pareja(1955, 1990, fam_a)
            a = [m, h]
            if tipo_a == "familia":
                a += self._hijos(m if m.mujer else None, h, rng.randint(1, 2), fam_a)
                tipo_a = "familia" if len(a) > 2 else "pareja"
        for p in a:
            p.residencias.append((ORIGEN, *unidad_compartida))
        nueva = self._residencia(self._ciudad_previa(ciudad, 0.15))
        self._hogar(a, tipo_a, nueva, salida)
        # Hogar B: llega después.
        llegada = salida + timedelta(days=rng.randint(20, 240))
        tipo_b = _elegir(rng, (("solo", 0.45), ("pareja", 0.35), ("familia", 0.2)))
        fam_b = self._familia()
        if tipo_b == "solo":
            b = [self._persona(rng.random() < 0.5, self._nac(1955, 2002), fam_b, "solo")]
        else:
            m, h = self._pareja(1960, 1998, fam_b)
            b = [m, h]
            if tipo_b == "familia":
                b += self._hijos(m if m.mujer else None, h, rng.randint(1, 2), fam_b)
        self._hogar(b, "sucesivo", unidad_compartida, llegada, "compartida")
        return a + b

    def _h_otro(self) -> list[Persona]:
        """Abuela o abuelo que vive con nietos, o tío con sobrino."""
        rng = self.rng
        fam = self._familia()
        jefe = self._persona(rng.random() < 0.7, self._nac(1938, 1962), fam, "jefe")
        otros = []
        for _ in range(rng.randint(1, 2)):
            anio = min(2008, jefe.nacimiento.year + rng.randint(40, 55))
            otros.append(
                self._persona(
                    rng.random() < 0.5,
                    self._nac(anio, anio),
                    fam,
                    "otro",
                    self.fake.last_name(),
                    jefe.apellido1,
                )
            )
        self._hogar([jefe, *otros], "otro", self._residencia(self._ciudad()), self._llegada(0.2))
        return [jefe, *otros]

    def poblar(self, objetivo: int) -> None:
        """Crea hogares hasta tener ``objetivo`` clientes."""
        rng = self.rng
        tipos = (
            (self._h_solo, 0.22),
            (self._h_pareja, 0.14),
            (self._h_familia, 0.19),
            (self._h_monoparental, 0.09),
            (self._h_hermanos, 0.04),
            (self._h_convivientes, 0.08),
            (self._h_casa_pisos, 0.07),
            (self._h_sucesivo, 0.06),
            (self._h_otro, 0.04),
        )
        funciones = [t for t, _ in tipos]
        pesos = [p for _, p in tipos]
        while len(self.personas) < objetivo:
            if objetivo - len(self.personas) <= 8:
                miembros = self._h_solo()
            else:
                miembros = rng.choices(funciones, weights=pesos)[0]()
            # No todos los miembros del hogar son clientes del banco.
            for p in miembros:
                p.cliente = len(miembros) == 1 or rng.random() > 0.15
            if not any(p.cliente for p in miembros):
                miembros[0].cliente = True
            clientes = [p for p in miembros if p.cliente]
            clientes = clientes[: objetivo - len(self.personas)]
            self.personas.extend(clientes)

    # -- datos de contacto y documento ----------------------------------------

    def _documento_cc(self, nac: date) -> str:
        rng = self.rng
        while True:
            if nac.year < 1950:
                n = str(rng.randint(1_000_000, 9_999_999))
            elif nac.year < 1985:
                n = str(rng.randint(10_000_000, 99_999_999))
            else:
                n = "10" + str(rng.randint(0, 99_999_999)).zfill(8)
            if n not in self.docs:
                self.docs.add(n)
                return n

    def _numero(self, largo: int, prefijo: str = "") -> str:
        rng = self.rng
        while True:
            n = prefijo + "".join(str(rng.randint(0, 9)) for _ in range(largo - len(prefijo)))
            if n not in self.docs and n[0] != "0":
                self.docs.add(n)
                return n

    def _celular(self) -> str:
        rng = self.rng
        while True:
            n = rng.choice(PREFIJOS_CEL) + str(rng.randint(0, 9_999_999)).zfill(7)
            if n not in self.cels:
                self.cels.add(n)
                return n

    def _correo(self, p: Persona, dominio: str | None = None) -> str:
        rng = self.rng
        n = _slug(p.nombres.split()[0])
        a = _slug(p.apellido1)
        a2 = _slug(p.apellido2) or "x"
        yy = f"{p.nacimiento.year % 100:02d}"
        patrones = [
            f"{n}.{a}",
            f"{n}{a}",
            f"{n[0]}{a}",
            f"{n}_{a}",
            f"{a}{n}",
            f"{n}.{a}{yy}",
            f"{n}{a}{a2[0]}",
            f"{n[0]}{a}{a2[0]}{p.nacimiento.year}",
        ]
        local = rng.choice(patrones)
        if rng.random() < 0.35:
            local += str(rng.randint(1, 999))
        dominio = dominio or _elegir(rng, DOMINIOS)
        correo = f"{local}@{dominio}"
        while correo in self.correos:
            correo = f"{local}{rng.randint(1, 9999)}@{dominio}"
        self.correos.add(correo)
        return correo

    def contactos(self) -> None:
        """Documento, teléfonos, correos y fijo de cada cliente, con sus cambios en el
        tiempo."""
        rng = self.rng
        fijos_hogar: dict[int, str | None] = {}
        correos_hogar: dict[int, list[str]] = {}
        for i, p in enumerate(self.personas):
            p.cluster = i
            mayor = _mas_anios(p.nacimiento, 18)
            # Documento: extranjeros con pasaporte y luego PPT o cédula de extranjería.
            if (
                p.rol in ("solo", "pareja", "conviviente")
                and 1965 <= p.nacimiento.year <= 2002
                and rng.random() < 0.06
            ):
                p.extranjera = True
                p.tipo_doc = _elegir(rng, (("PPT", 0.6), ("CE", 0.4)))
                largo = 7 if p.tipo_doc == "PPT" else rng.choice([6, 7])
                p.documento = self._numero(largo, rng.choice(["4", "5", "6"]))
                if rng.random() < 0.35:
                    hasta = _fecha_entre(rng, date(2017, 1, 1), date(2022, 12, 31))
                    p.docs_previos.append((hasta, "PA", self._numero(9, "1")))
            else:
                p.documento = self._documento_cc(p.nacimiento)
                if mayor > INICIO:
                    if p.nacimiento.year >= 2000:
                        ti = p.documento
                    else:  # tarjeta de identidad antigua: AAMMDD + 5 dígitos
                        ti = self._numero(11, p.nacimiento.strftime("%y%m%d"))
                    p.docs_previos.append((mayor - timedelta(days=1), "TI", ti))
            # Celulares: uno propio y a veces cambios.
            p.celulares = [(ORIGEN, self._celular())]
            if rng.random() < 0.3:
                p.celulares.append(
                    (_fecha_entre(rng, date(2012, 1, 1), date(2024, 12, 31)), self._celular())
                )
                if rng.random() < 0.25:
                    p.celulares.append(
                        (_fecha_entre(rng, p.celulares[-1][0], FIN), self._celular())
                    )
            # Correos: a veces uno viejo de hotmail y uno nuevo.
            if p.estudiante and rng.random() < 0.35:
                p.correos = [(ORIGEN, self._correo(p, rng.choice(DOMINIOS_U)))]
            else:
                p.correos = [(ORIGEN, self._correo(p))]
            if rng.random() < 0.25:
                p.correos.append(
                    (_fecha_entre(rng, date(2013, 1, 1), date(2024, 12, 31)), self._correo(p))
                )
            # Fijo del hogar (compartido sin nada de sospechoso).
            if p.tipo_hogar in ("familia", "monoparental", "otro", "pareja", "hermanos"):
                if p.hogar not in fijos_hogar:
                    fijo = None
                    if rng.random() < 0.4:
                        while True:
                            fijo = str(rng.randint(2_000_000, 7_999_999))
                            if fijo not in self.fijos:
                                self.fijos.add(fijo)
                                break
                    fijos_hogar[p.hogar] = fijo
                p.fijo = fijos_hogar[p.hogar]
            correos_hogar.setdefault(p.hogar, []).append(p.correos[0][1])
        # Hijos y personas mayores que dan el correo de otro miembro del hogar.
        for p in self.personas:
            otros = [c for c in correos_hogar.get(p.hogar, []) if c != p.correos[0][1]]
            if otros and p.rol in ("hijo", "otro", "jefe") and rng.random() < 0.3:
                p.correo_familiar = rng.choice(otros)

    # -- registros ---------------------------------------------------------------

    def _canal(self, fecha: date) -> tuple[str, bool]:
        rng = self.rng
        if fecha.year < 2015:
            pesos = (0.55, 0.03, 0.12, 0.15, 0.15)
        elif fecha.year < 2020:
            pesos = (0.38, 0.2, 0.15, 0.12, 0.15)
        else:
            pesos = (0.25, 0.35, 0.15, 0.08, 0.17)
        canal = rng.choices(CANALES, weights=pesos)[0]
        prob = {"sucursal": 0.9, "app": 0.6, "web": 0.3, "call_center": 0.4, "corresponsal": 0.5}
        return canal, rng.random() < prob[canal]

    def _caso(self, texto: str, canal: str) -> str:
        rng = self.rng
        r = rng.random()
        mayus = 0.55 if canal in ("sucursal", "corresponsal") else 0.15
        if r < mayus:
            texto = texto.upper()
        elif r < mayus + 0.06:
            texto = texto.lower()
        if rng.random() < (0.6 if texto.isupper() else 0.25):
            texto = _sin_tildes(texto)
        return texto

    def _nombres(self, p: Persona, fecha: date, canal: str, validado: bool) -> tuple:
        rng = self.rng
        f = 0.35 if validado else 1.0
        f *= 2.0 if canal == "call_center" else 1.0
        tokens = p.nombres.split()
        tokens = [
            rng.choice(VARIANTES_NOMBRE[t]) if t in VARIANTES_NOMBRE and rng.random() < 0.3 else t
            for t in tokens
        ]
        if len(tokens) > 1 and rng.random() < 0.18:
            tokens = tokens[:1]
        nombres = " ".join(tokens)
        if p.apellido_esposo and rng.random() < 0.55:
            if rng.random() < 0.7:
                apellidos = f"{p.apellido1} de {p.apellido_esposo}"
            else:
                apellidos = f"{p.apellido1} {p.apellido2} de {p.apellido_esposo}"
        elif rng.random() < 0.12:
            apellidos = p.apellido1
        else:
            apellidos = f"{p.apellido1} {p.apellido2}"
        if rng.random() < 0.04 * f:
            nombres = _errata(nombres, rng)
        if rng.random() < 0.04 * f:
            apellidos = _errata(apellidos, rng)
        if rng.random() < 0.04 * f:
            nombres = _fonetica(nombres, rng)
        if rng.random() < 0.04 * f:
            apellidos = _fonetica(apellidos, rng)
        nombres, apellidos = self._caso(nombres, canal), self._caso(apellidos, canal)
        r = rng.random()
        if r < 0.012:
            nombres, apellidos = apellidos, nombres
        elif r < 0.02:
            nombres, apellidos = f"{nombres} {apellidos}", None
        elif r < 0.025:
            nombres = None
        elif r < 0.03:
            apellidos = None
        if p.apellido_esposo and apellidos and " de " in f" {apellidos.lower()} ":
            p.uso_casada = True
        return nombres, apellidos

    def _documento(self, p: Persona, fecha: date, validado: bool) -> tuple[str, str | None]:
        rng = self.rng
        tipo, numero = p.tipo_doc, p.documento
        for hasta, t, n in p.docs_previos:
            if fecha <= hasta:
                tipo, numero = t, n
                break
        if rng.random() < 0.03:
            tipo = {"CC": rng.choice(["C.C.", "CEDULA", "cc"]), "TI": "T.I."}.get(tipo, tipo)
        f = 0.3 if validado else 1.0
        r = rng.random()
        if r < 0.02 * f:
            return tipo, None
        if r < 0.07 * f:
            numero = _errata_digito(numero, rng)
        if numero.isdigit() and tipo != "PA" and rng.random() < 0.07:
            numero = f"{int(numero):,}".replace(",", ".")
        elif rng.random() < 0.01:
            numero = numero + " "
        return tipo, numero

    def _fecha_nac(self, p: Persona, canal: str) -> str | None:
        rng = self.rng
        r = rng.random()
        if r < (0.01 if canal == "app" else 0.04):
            return None
        if r < 0.05:
            return rng.choice(FECHAS_RELLENO)
        d = p.nacimiento
        r = rng.random()
        if r < 0.03 and d.day <= 12 and d.day != d.month:
            d = date(d.year, d.day, d.month)
        elif r < 0.045:
            d = _mas_anios(d, rng.choice([-10, -1, 1, 10]))
        elif r < 0.06:
            d = d + timedelta(days=rng.choice([-1, 1]))
        formatos = {
            "sucursal": (("dmy/", 0.7), ("iso", 0.3)),
            "app": (("iso", 1.0),),
            "web": (("iso", 0.6), ("dmy/", 0.4)),
            "call_center": (("dmy-", 0.5), ("dmy/", 0.5)),
            "corresponsal": (("dmy", 0.4), ("dmy/", 0.4), ("dmy2", 0.2)),
        }[canal]
        fmt = _elegir(rng, formatos)
        if fmt == "iso":
            return d.isoformat()
        if fmt == "dmy/":
            return f"{d.day:02d}/{d.month:02d}/{d.year}"
        if fmt == "dmy-":
            return f"{d.day:02d}-{d.month:02d}-{d.year}"
        if fmt == "dmy":
            return f"{d.day:02d}{d.month:02d}{d.year}"
        return f"{d.day:02d}/{d.month:02d}/{d.year % 100:02d}"

    def _fmt_celular(self, n: str) -> str:
        opciones = (
            (n, 0.55),
            (f"{n[:3]} {n[3:6]} {n[6:]}", 0.12),
            (f"+57 {n}", 0.1),
            (f"57{n}", 0.05),
            (f"{n[:3]}-{n[3:]}", 0.08),
            (f"({n[:3]}) {n[3:]}", 0.03),
            (f"+57{n}", 0.07),
        )
        return _elegir(self.rng, opciones)

    def _celular_reg(self, p: Persona, fecha: date) -> str | None:
        rng = self.rng
        r = rng.random()
        if r < 0.07:
            return None
        if r < 0.085:
            return rng.choice(CELULARES_RELLENO)
        if p.fijo and r < 0.2:
            ind = CIUDADES[p.en(p.residencias, fecha)[1].ciudad].indicativo
            if fecha < CAMBIO_FIJOS:
                return rng.choice([p.fijo, f"({ind[2]}) {p.fijo}", f"{ind[2]}{p.fijo}"])
            return rng.choice([f"{ind}{p.fijo}", f"{ind} {p.fijo}", f"+57 {ind}{p.fijo}"])
        numero = p.en(p.celulares, fecha)[1]
        # A veces se sigue capturando el número anterior.
        if len(p.celulares) > 1 and numero != p.celulares[0][1] and rng.random() < 0.1:
            numero = p.celulares[0][1]
        if rng.random() < 0.025:
            numero = _errata_digito(numero, rng)
        return self._fmt_celular(numero)

    def _correo_reg(self, p: Persona, fecha: date, canal: str) -> str | None:
        rng = self.rng
        faltante = 0.3 if fecha.year < 2015 else 0.1
        r = rng.random()
        if r < faltante:
            return None
        if r < faltante + 0.02:
            return rng.choice(CORREOS_RELLENO)
        if p.correo_familiar and rng.random() < 0.35:
            correo = p.correo_familiar
        else:
            correo = p.en(p.correos, fecha)[1]
        local, dominio = correo.split("@")
        r = rng.random()
        if r < 0.03 and dominio in ERRATAS_DOMINIO:
            dominio = rng.choice(ERRATAS_DOMINIO[dominio])
        elif r < 0.05:
            local = _errata(local, rng) if len(local) > 3 else local
        correo = f"{local}@{dominio}"
        if canal in ("sucursal", "corresponsal") and rng.random() < 0.25:
            correo = correo.upper()
        elif rng.random() < 0.02:
            correo = " " + correo
        return correo

    def _fmt_unidad(self, unidad: str, predio: Predio) -> str | None:
        """Escribe una unidad de alguna de las muchas formas posibles (o la omite)."""
        rng = self.rng
        partes = unidad.split()
        pares = list(zip(partes[::2], partes[1::2], strict=True))
        if pares[0] == ("piso", "1") and rng.random() < 0.75:
            return None  # el primer piso casi nunca se escribe
        if rng.random() < (0.25 if predio.tipo == "casa_pisos" else 0.12):
            return None
        formas = {
            "torre": ("Torre {}", "T{}", "TO {}", "Tr {}", "T-{}", "TORRE {}", "Tor {}"),
            "bloque": ("Bloque {}", "Bl {}", "BQ {}", "Blq {}", "Bloq. {}"),
            "interior": ("Interior {}", "Int {}", "IN {}", "Int. {}", "Inter {}"),
            "apto": (
                "Apto {}",
                "Apt {}",
                "AP {}",
                "Apartamento {}",
                "Ap. {}",
                "APTO {}",
                "Apto. {}",
            ),
            "casa": ("Casa {}", "CS {}", "Cs {}", "Casa #{}", "Casa No {}"),
            "piso": ("Piso {}", "P{}", "{} piso", "PISO {}", "Piso {}"),
        }
        ordinales = {"1": "Primer piso", "2": "Segundo piso", "3": "Tercer piso"}
        textos = []
        for clave, valor in pares:
            if clave == "piso" and rng.random() < 0.2:
                textos.append(ordinales[valor])
            elif clave == "piso" and valor != "1" and rng.random() < 0.12:
                textos.append(f"Apto {valor}01")
            else:
                textos.append(rng.choice(formas[clave]).format(valor))
        if len(textos) == 2:
            r = rng.random()
            if r < 0.1:
                textos = textos[1:]  # se omite la torre, el bloque o el interior
            elif r < 0.25:
                textos = textos[::-1]
            elif r < 0.33:
                textos = [textos[0], textos[1].split()[-1]]  # "T2 504"
        return rng.choice([" ", ", ", " - "]).join(textos)

    def _direccion(self, predio: Predio, unidad: str | None, canal: str) -> str | None:
        rng = self.rng
        if rng.random() < (0.08 if canal == "call_center" else 0.04):
            return None
        if rng.random() < 0.012:
            return rng.choice(DIRECCIONES_RELLENO)
        via = rng.choice(VIAS[predio.via][1])
        numero = predio.numero
        if " " in numero and rng.random() < 0.5:
            numero = numero.replace(" ", "")
        elif numero[-1] in "ABC" and rng.random() < 0.3:
            numero = numero[:-1] + " " + numero[-1]
        sep = _elegir(
            rng,
            (
                (" # ", 0.35),
                (" #", 0.1),
                (" No ", 0.15),
                (" No. ", 0.1),
                (" N° ", 0.08),
                (" Nro ", 0.05),
                (" ", 0.17),
            ),
        )
        guion = _elegir(rng, (("-", 0.6), (" - ", 0.2), (" ", 0.2)))
        placa1, placa2 = predio.placa1, predio.placa2
        if rng.random() < 0.025:
            placa2 = str(max(1, (int(placa2) + rng.choice([1, -1, 10, -10])) % 100))
        texto = f"{via} {numero}{sep}{placa1}{guion}{placa2}"
        if predio.sur and rng.random() < 0.85:
            texto += rng.choice([" Sur", " SUR", " S"])
        if unidad:
            u = self._fmt_unidad(unidad, predio)
            if u:
                texto += rng.choice([" ", ", ", " "]) + u
        if predio.nombre and rng.random() < (0.35 if predio.tipo == "conjunto" else 0.2):
            if predio.tipo == "conjunto":
                pref = rng.choice(
                    [
                        "Conjunto Residencial",
                        "Cjto",
                        "Conj.",
                        "Unidad Residencial",
                        "U.R.",
                        "Conjunto",
                    ]
                )
            else:
                pref = rng.choice(["Edificio", "Ed.", "Edif"])
            nombre = f"{pref} {predio.nombre}"
            texto = f"{texto} {nombre}" if rng.random() < 0.7 else f"{nombre} {texto}"
        if rng.random() < 0.12:
            texto += rng.choice([" Barrio ", " B/ ", " - ", " Br "]) + predio.barrio
        return self._caso(texto, canal)

    def _ciudad_reg(self, predio: Predio) -> tuple[str | None, str | None]:
        rng = self.rng
        c = CIUDADES[predio.ciudad]
        if c.vecina and rng.random() < 0.12:
            c = CIUDADES[_IDX_CIUDAD[c.vecina]]
        ciudad = None
        if rng.random() > 0.03:
            ciudad = c.variantes[0] if rng.random() < 0.5 else rng.choice(c.variantes)
        depto = None
        if rng.random() > 0.12:
            depto = c.variantes_depto[0] if rng.random() < 0.55 else rng.choice(c.variantes_depto)
        return ciudad, depto

    def registro(self, p: Persona, fecha: date, origen: str = "normal", canal=None) -> dict:
        """Un registro capturado de la persona ``p`` en ``fecha``."""
        if canal is None:
            canal, validado = self._canal(fecha)
        else:
            validado = self.rng.random() < 0.15
        tipo, numero = self._documento(p, fecha, validado)
        nombres, apellidos = self._nombres(p, fecha, canal, validado)
        _, predio, unidad = p.en(p.residencias, fecha)
        ciudad, depto = self._ciudad_reg(predio)
        return {
            "tipo_documento": tipo,
            "numero_documento": numero,
            "nombres": nombres,
            "apellidos": apellidos,
            "fecha_nacimiento": self._fecha_nac(p, canal),
            "celular": self._celular_reg(p, fecha),
            "correo": self._correo_reg(p, fecha, canal),
            "direccion": self._direccion(predio, unidad, canal),
            "ciudad": ciudad,
            "departamento": depto,
            "cluster": p.cluster,
            "fecha_actualizacion": fecha.isoformat(),
            "canal": canal,
            "validado": validado,
            "origen": origen,
        }

    def registros_normales(self) -> list[dict]:
        rng = self.rng
        filas = []
        for p in self.personas:
            n = rng.choices([1, 2, 3, 4, 5, 6], weights=[27, 33, 22, 11, 5, 2])[0]
            inicio = max(INICIO, _mas_anios(p.nacimiento, 14))
            primera = _fecha_entre(rng, inicio, FIN - timedelta(days=30))
            fechas = sorted([primera] + [_fecha_entre(rng, primera, FIN) for _ in range(n - 1)])
            for fecha in fechas:
                fila = self.registro(p, fecha)
                filas.append(fila)
                # Doble carga del mismo formulario unos días después.
                if rng.random() < 0.015:
                    copia = dict(fila)
                    copia["fecha_actualizacion"] = min(
                        FIN, fecha + timedelta(days=rng.randint(0, 3))
                    ).isoformat()
                    filas.append(copia)
        return filas

    # -- patrones sospechosos ------------------------------------------------------

    def _canal_sospechoso(self) -> str:
        return _elegir(self.rng, (("app", 0.45), ("web", 0.3), ("corresponsal", 0.25)))

    def sospechosos(self, n_fraude: int, escala: float) -> tuple[list[dict], list[dict]]:
        """Inyecta los patrones sospechosos y devuelve (registros nuevos, sospechosos)."""
        rng = self.rng
        filas: list[dict] = []
        verdad: list[dict] = []
        usados: set[int] = set()
        adultos = [p for p in self.personas if p.nacimiento.year <= 2000]

        def libres(k: int) -> list[Persona]:
            """``k`` personas sin parentesco entre sí ni con patrones anteriores."""
            elegidas: list[Persona] = []
            familias: set[int] = set()
            for p in rng.sample(adultos, len(adultos)):
                if p.cluster in usados or p.familia in familias:
                    continue
                elegidas.append(p)
                familias.add(p.familia)
                if len(elegidas) == k:
                    break
            for p in elegidas:
                usados.add(p.cluster)
            return elegidas

        # 1. Documento ajeno: suplantación (nombre y documento de la víctima con los datos de
        #    contacto del impostor) o documento prestado (nombre propio, documento ajeno).
        victimas = [p for p in libres(n_fraude) if p.tipo_doc == "CC"]
        for victima in victimas:
            fam = self._familia()
            impostor = self._persona(rng.random() < 0.5, self._nac(1975, 2002), fam, "solo")
            self._hogar([impostor], "solo", self._residencia(self._ciudad()))
            impostor.cluster = len(self.personas)
            impostor.documento = self._documento_cc(impostor.nacimiento)
            impostor.celulares = [(ORIGEN, self._celular())]
            impostor.correos = [(ORIGEN, self._correo(impostor, "gmail.com"))]
            self.personas.append(impostor)
            suplanta = rng.random() < 0.6
            etiqueta = "suplantacion" if suplanta else "doc_prestado"
            inicio = _fecha_entre(rng, date(2019, 1, 1), date(2025, 6, 30))
            if suplanta:
                disfraz = Persona(
                    mujer=victima.mujer,
                    nombres=victima.nombres,
                    apellido1=victima.apellido1,
                    apellido2=victima.apellido2,
                    nacimiento=victima.nacimiento,
                    familia=fam,
                    rol="solo",
                    cluster=impostor.cluster,
                    documento=victima.documento,
                    residencias=impostor.residencias,
                    celulares=impostor.celulares,
                    correos=impostor.correos,
                )
                fuente, n_reg = disfraz, rng.randint(1, 2)
            else:
                # El impostor también tiene registros propios con su documento.
                filas.append(self.registro(impostor, _fecha_entre(rng, date(2014, 1, 1), inicio)))
                fuente, n_reg = impostor, 1
            for k in range(n_reg):
                fecha = min(FIN, inicio + timedelta(days=rng.randint(0, 60) * k))
                fila = self.registro(fuente, fecha, etiqueta, self._canal_sospechoso())
                fila["tipo_documento"] = "CC"
                fila["numero_documento"] = victima.documento
                fila["cluster"] = impostor.cluster
                filas.append(fila)
            verdad.append(
                {
                    "tipo": "documento",
                    "valor": victima.documento,
                    "personas": sorted([victima.cluster, impostor.cluster]),
                }
            )

        def anillo(
            columna: str,
            valor: str,
            miembros: list[Persona],
            etiqueta: str,
            ciudad: Ciudad | None = None,
        ) -> None:
            inicio = _fecha_entre(rng, date(2018, 1, 1), date(2025, 8, 31))
            for p in miembros:
                fecha = min(FIN, inicio + timedelta(days=rng.randint(0, 120)))
                fila = self.registro(p, fecha, etiqueta, self._canal_sospechoso())
                fila[columna] = valor
                if ciudad is not None:
                    fila["ciudad"], fila["departamento"] = ciudad.nombre, ciudad.departamento
                filas.append(fila)

        # 2. Un celular para varias personas sin relación (a veces el de un cliente
        #    "controlador", que no necesita registro extra porque ya tiene el suyo).
        for _ in range(max(1, round(6 * escala))):
            miembros = libres(rng.randint(4, 7))
            if len(miembros) < 3:
                break
            if rng.random() < 0.5:
                controlador = miembros[0]
                valor = controlador.celulares[-1][1]
                anillo("celular", valor, miembros[1:], "anillo_celular")
            else:
                valor = self._celular()
                anillo("celular", valor, miembros, "anillo_celular")
            verdad.append(
                {"tipo": "celular", "valor": valor, "personas": sorted(p.cluster for p in miembros)}
            )

        # 3. Un correo de "tramitador" en registros de personas sin relación.
        for _ in range(max(1, round(4 * escala))):
            miembros = libres(rng.randint(3, 6))
            if len(miembros) < 3:
                break
            local = rng.choice(["tramites", "gestiones", "asesorias", "creditos", "papeleo"])
            local += rng.choice([".rapidos", "express", ".ya", "24h", "facil"])
            valor = f"{local}{rng.randint(1, 99)}@gmail.com"
            self.correos.add(valor)
            anillo("correo", valor, miembros, "anillo_correo")
            verdad.append(
                {"tipo": "correo", "valor": valor, "personas": sorted(p.cluster for p in miembros)}
            )

        # 4. Dirección de fachada: una oficina o bodega que aparece como residencia de muchas
        #    personas sin relación, en pocas semanas.
        for _ in range(max(1, round(3 * escala))):
            miembros = libres(rng.randint(5, 9))
            if len(miembros) < 3:
                break
            predio = self._predio_nuevo(self._ciudad(), "casa")
            via = VIAS[predio.via][1][0]
            local = rng.choice(["Oficina", "Of", "Local", "Bodega"]) + f" {rng.randint(101, 410)}"
            valor = f"{via} {predio.numero} # {predio.placa1}-{predio.placa2} {local}"
            anillo("direccion", valor, miembros, "dir_fachada", CIUDADES[predio.ciudad])
            verdad.append(
                {
                    "tipo": "direccion",
                    "valor": valor,
                    "personas": sorted(p.cluster for p in miembros),
                }
            )
        return filas, verdad

    # -- tablas ------------------------------------------------------------------

    def tabla_personas(self) -> pd.DataFrame:
        filas = []
        for p in self.personas:
            _, predio, unidad = p.residencias[-1]
            filas.append(
                {
                    "cluster": p.cluster,
                    "mujer": p.mujer,
                    "familia": p.familia,
                    "hogar": p.hogar,
                    "rol": p.rol,
                    "tipo_hogar": p.tipo_hogar,
                    "predio": predio.id,
                    "tipo_predio": predio.tipo,
                    "unidad": unidad,
                    "usa_apellido_casada": p.uso_casada,
                }
            )
        tabla = pd.DataFrame(filas, columns=COLUMNAS_PERSONAS)
        tabla["unidad"] = tabla["unidad"].astype(object).where(tabla["unidad"].notna(), None)
        return tabla


def generar(
    n_personas: int = 2000, semilla: int = 4444
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Devuelve (registros, personas, sospechosos).

    ``registros`` tiene un renglón por registro capturado, ``personas`` uno por persona
    verdadera y ``sospechosos`` uno por valor compartido de forma sospechosa que se inyectó.
    La misma semilla da exactamente las mismas tablas.
    """
    if n_personas < 20:
        raise ValueError("n_personas debe ser al menos 20")
    gen = _Generador(semilla)
    escala = n_personas / 2000
    n_fraude = max(1, round(10 * escala))
    gen.poblar(n_personas - n_fraude)
    gen.contactos()
    filas = gen.registros_normales()
    extra, verdad = gen.sospechosos(n_fraude, escala)
    # Si alguna víctima no tenía cédula, completa con personas solas hasta n_personas.
    while len(gen.personas) < n_personas:
        p = gen._h_solo()[0]
        p.cluster = len(gen.personas)
        p.documento = gen._documento_cc(p.nacimiento)
        p.celulares = [(ORIGEN, gen._celular())]
        p.correos = [(ORIGEN, gen._correo(p))]
        gen.personas.append(p)
        filas.append(gen.registro(p, _fecha_entre(gen.rng, date(2012, 1, 1), FIN)))
    filas.extend(extra)
    gen.rng.shuffle(filas)
    registros = pd.DataFrame(filas)
    registros.insert(0, "unique_id", range(len(registros)))
    registros = registros[COLUMNAS_REGISTROS]
    registros["unique_id"] = registros["unique_id"].astype("int64")
    registros["cluster"] = registros["cluster"].astype("int64")
    registros["validado"] = registros["validado"].astype(bool)
    registros = registros.astype(object).where(registros.notna(), None)
    for col in ("unique_id", "cluster"):
        registros[col] = registros[col].astype("int64")
    registros["validado"] = registros["validado"].astype(bool)
    personas = gen.tabla_personas()
    sospechosos = pd.DataFrame(verdad, columns=COLUMNAS_SOSPECHOSOS)
    return registros, personas, sospechosos
