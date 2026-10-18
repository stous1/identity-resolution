"""Generador independiente de errores de captura para la segunda prueba ciega.

Toma una tabla de personas "verdaderas" (una fila por persona, datos limpios) y produce
entre 1 y 6 registros por persona con errores de captura realistas de una base de clientes
bancarios colombiana. Se escribió sin leer la estandarización ni el modelo que se van a
evaluar, para que la prueba sea ciega.

Hay dos niveles de error:

- **De persona**: se deciden una vez por persona y quedan en la tabla ``condiciones``
  (apellido de casada, apodo, vivienda rural, tarjeta de identidad de cuando era menor,
  documento alterno de extranjero). La tasa es la probabilidad de que una persona elegible
  tenga la condición; al menos uno de sus registros la manifiesta.
- **De registro**: se sortean de forma independiente en cada registro. La tasa es la
  probabilidad por registro (y, cuando el error solo aplica a ciertos nombres o personas,
  la probabilidad entre los registros elegibles).

Toda la aleatoriedad sale de un ``random.Random`` con la semilla dada.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import asdict, dataclass, fields
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

ANIO_REFERENCIA = 2026
PESOS_REGISTROS = [0.34, 0.24, 0.17, 0.12, 0.08, 0.05]  # 1..6 registros por persona
USO_CONDICION = 0.6  # probabilidad de que un registro manifieste la condición de persona


@dataclass(frozen=True)
class TasasCiegas2:
    """Probabilidades de cada tipo de error.

    Las de persona se aplican a personas elegibles; las demás, a cada registro elegible.
    Todas valen entre 0 y 1.
    """

    # --- Condiciones de persona ---
    apellido_casada: float = 0.30  # entre mujeres aparentes de 22 años o más
    con_apodo: float = 0.12
    rural: float = 0.06
    doc_tarjeta_identidad: float = 0.10  # entre CC nacidos 1980-2000
    doc_extranjero_alterno: float = 0.35  # entre CE
    # --- Errores de registro ya vistos en la prueba anterior (diseño propio) ---
    segundo_nombre_omitido: float = 0.12
    segundo_apellido_omitido: float = 0.08
    tildes: float = 0.25
    mayusculas: float = 0.30
    letra: float = 0.04
    digito_documento: float = 0.03
    campo_faltante: float = 0.06
    # --- Errores de registro nuevos ---
    grafia_anglo: float = 0.35
    particula_religiosa: float = 0.40
    abreviatura_nombre: float = 0.15
    iniciales: float = 0.04
    titulo: float = 0.03
    apellidos_guion: float = 0.03
    pegado_mayusculas: float = 0.02
    digito_verificacion: float = 0.03
    celular_longitud: float = 0.02
    celular_cambiado: float = 0.05
    correo_corporativo: float = 0.04
    correo_alias: float = 0.03
    ciudad_expedicion: float = 0.03
    barrio_conjunto: float = 0.04
    via_nombre_propio: float = 0.03
    direccion_anterior: float = 0.04
    anio_dos_digitos: float = 0.04

    @classmethod
    def ninguna(cls) -> TasasCiegas2:
        """Todas las tasas en cero: registros limpios."""
        return cls(**{f.name: 0.0 for f in fields(cls)})

    @classmethod
    def solo(cls, nombre: str, valor: float = 1.0) -> TasasCiegas2:
        """Todas las tasas en cero salvo ``nombre``."""
        tasas = {f.name: 0.0 for f in fields(cls)}
        if nombre not in tasas:
            raise ValueError(f"Tipo de error desconocido: {nombre}")
        tasas[nombre] = valor
        return cls(**tasas)


CONDICIONES_PERSONA = [
    "apellido_casada",
    "con_apodo",
    "rural",
    "doc_tarjeta_identidad",
    "doc_extranjero_alterno",
]

# ---------------------------------------------------------------------------
# Vocabularios
# ---------------------------------------------------------------------------

FEMENINOS_SIN_A = {
    "luz",
    "carmen",
    "isabel",
    "ines",
    "esther",
    "ester",
    "beatriz",
    "raquel",
    "rocio",
    "pilar",
    "consuelo",
    "amparo",
    "socorro",
    "mercedes",
    "dolores",
    "ruth",
    "karen",
    "jazmin",
    "yasmin",
    "yazmin",
    "edith",
    "ingrid",
    "yaneth",
    "janeth",
    "lizeth",
    "liseth",
    "liceth",
    "julieth",
    "ibeth",
    "enith",
    "maribel",
    "marisol",
    "nelly",
    "leidy",
    "lady",
    "gladys",
    "rosario",
    "mabel",
    "miriam",
    "mirian",
    "myriam",
    "flor",
    "astrid",
    "betty",
    "lucy",
    "mary",
    "mery",
    "ruby",
    "nury",
    "dary",
    "marly",
    "mayerly",
    "shirley",
    "cindy",
    "heidy",
    "deisy",
    "kelly",
    "jenny",
    "yenny",
    "fanny",
    "doris",
    "iris",
    "elcy",
    "nelcy",
    "nelsy",
    "emilce",
    "emilse",
    "carol",
    "karol",
    "katherine",
    "katherin",
    "katerine",
    "catherine",
    "geraldine",
    "lucero",
    "cielo",
    "margoth",
    "judith",
    "yamile",
    "leonor",
    "piedad",
    "stella",
    "estela",
    "estella",
    "alix",
    "nohemi",
    "abigail",
    "belen",
    "soledad",
    "maryuri",
    "yuly",
    "aracely",
    "aracelly",
    "edilma",
    "rubiela",
    "esperanza",
}
MASCULINOS_CON_A = {"luca", "nicola", "elias", "josue", "garcia"}

# Hipocorísticos y apodos colombianos por nombre (clave sin tildes, en minúsculas).
APODOS: dict[str, list[str]] = {
    # Hombres
    "jose": ["Pepe", "Chepe", "Pepito", "Joselito"],
    "francisco": ["Pacho", "Pacho", "Paco", "Pancho", "Panchito"],
    "jesus": ["Chucho", "Chuchito", "Chuy"],
    "guillermo": ["Memo", "Guille", "Memito"],
    "alberto": ["Beto", "Albertico", "Tico"],
    "roberto": ["Beto", "Robert", "Robertico"],
    "gilberto": ["Gil", "Beto"],
    "humberto": ["Beto", "Humbe"],
    "heriberto": ["Beto", "Heri"],
    "adalberto": ["Beto", "Adal"],
    "antonio": ["Toño", "Toñito", "Tony"],
    "luis": ["Lucho", "Luisito", "Luchito"],
    "eduardo": ["Lalo", "Edu", "Guayo"],
    "manuel": ["Manolo", "Manu", "Manolito"],
    "fernando": ["Fercho", "Nando", "Fer"],
    "hernando": ["Nando", "Hernandito"],
    "alejandro": ["Alejo", "Alex", "Alejito"],
    "gonzalo": ["Chalo", "Gonza"],
    "rafael": ["Rafa", "Rafico", "Rafita"],
    "ricardo": ["Richi", "Richard", "Ricardito"],
    "andres": ["Andresito", "Andy", "Andresico"],
    "juan": ["Juancho", "Juanito", "Juancito"],
    "carlos": ["Carlitos", "Charly", "Calitos"],
    "jorge": ["Coque", "Jorgito", "Yoyo"],
    "javier": ["Javi", "Javiercito"],
    "diego": ["Dieguito", "Dieguín"],
    "daniel": ["Dani", "Danielito"],
    "camilo": ["Cami", "Camilito", "Milo"],
    "sebastian": ["Sebas", "Tatán", "Sebitas"],
    "santiago": ["Santi", "Santy", "Santiaguito"],
    "felipe": ["Pipe", "Pipo", "Felipito"],
    "mauricio": ["Mauro", "Mao", "Mauri"],
    "enrique": ["Kike", "Quique", "Enriquito"],
    "ignacio": ["Nacho", "Nachito"],
    "alfonso": ["Poncho", "Ponchito"],
    "gustavo": ["Tavo", "Tavito"],
    "miguel": ["Migue", "Miguelito"],
    "cristian": ["Cris", "Cristo"],
    "cristhian": ["Cris"],
    "christian": ["Cris"],
    "alexander": ["Alex", "Alexito"],
    "orlando": ["Lando", "Orlandito"],
    "rodrigo": ["Rodri", "Rodriguito"],
    "gabriel": ["Gabo", "Gabi", "Gabito"],
    "nicolas": ["Nico", "Nicolasito"],
    "mateo": ["Teo", "Mateíto"],
    "esteban": ["Teban", "Estebitan"],
    "adolfo": ["Fito"],
    "rodolfo": ["Fito", "Rodo"],
    "ernesto": ["Neto"],
    "benjamin": ["Benja"],
    "william": ["Wili", "Willy"],
    "wilson": ["Wil", "Wilsito"],
    "mario": ["Marito"],
    "pedro": ["Perucho", "Pedrito"],
    "pablo": ["Pablito", "Pablucho"],
    "jaime": ["Jaimito", "Jimmy"],
    "julian": ["Juli", "Julianito"],
    "samuel": ["Samu", "Sammy"],
    "sergio": ["Checho", "Sergi"],
    "jhonatan": ["Jhona", "Yona"],
    "jonathan": ["Jona", "Yona"],
    "leonardo": ["Leo", "Nardo"],
    "armando": ["Mando", "Armandito"],
    "arturo": ["Tuto", "Arturito"],
    "ramiro": ["Rami", "Ramirito"],
    "raul": ["Raulito"],
    "hector": ["Tito", "Hectorcito"],
    "victor": ["Vitico", "Vic"],
    "oscar": ["Osquitar", "Oscarito"],
    "german": ["Germancho", "Mancho"],
    "hernan": ["Nanito", "Hernancito"],
    "cesar": ["Cesitar", "Chécharo"],
    "jairo": ["Jairito"],
    "edwin": ["Edu", "Edwincito"],
    "kevin": ["Kevincito", "Kevo"],
    "brayan": ["Bray", "Brayancito"],
    "freddy": ["Fredy", "Fred"],
    "fredy": ["Freddy", "Fred"],
    "jhon": ["Jhoncito", "Yoni"],
    "john": ["Johncito", "Johnny"],
    "henry": ["Henrycito"],
    "ivan": ["Ivancho"],
    "nestor": ["Tito", "Nestico"],
    "salvador": ["Chava", "Salva"],
    "vicente": ["Chente"],
    "reinaldo": ["Rey", "Reina"],
    "segundo": ["Segundito"],
    # Mujeres
    "maria": ["Mary", "Mari", "Maru", "Mariíta"],
    "luz": ["Lucecita", "Lucy", "Lucesita"],
    "patricia": ["Paty", "Pati", "Patico"],
    "sandra": ["Sandrita", "Sandri"],
    "andrea": ["Andre", "Andreíta"],
    "paola": ["Pao", "Paolita"],
    "martha": ["Marthica", "Martica"],
    "claudia": ["Clau", "Claudita"],
    "marcela": ["Marce", "Chela", "Marcelita"],
    "ana": ["Anita", "Anica"],
    "daniela": ["Dani", "Danielita"],
    "diana": ["Dianita", "Di"],
    "carmen": ["Carmencita", "Mencha", "Menchu"],
    "rosa": ["Rosita", "Rosi", "Chayo"],
    "milena": ["Mile", "Milenita"],
    "cecilia": ["Ceci", "Chechi"],
    "lucia": ["Lucy", "Luchi", "Lucita"],
    "isabel": ["Isa", "Chabela", "Isabelita"],
    "carolina": ["Caro", "Carito", "Carol"],
    "liliana": ["Lili", "Lilianita"],
    "adriana": ["Adri", "Adrianita"],
    "gloria": ["Glorita", "Gloricita"],
    "angela": ["Angie", "Angelita"],
    "beatriz": ["Betty", "Bea", "Beti"],
    "alba": ["Albita"],
    "ines": ["Inesita", "Inecita"],
    "teresa": ["Tere", "Teresita"],
    "mercedes": ["Meche", "Merce", "Mechas"],
    "dolores": ["Lola", "Lolita"],
    "consuelo": ["Chelo", "Consu"],
    "rosario": ["Charo", "Chayo"],
    "socorro": ["Coco", "Socorrito"],
    "margarita": ["Magola", "Margot", "Maggie"],
    "josefina": ["Fina", "Pepa", "Chepa"],
    "graciela": ["Chela", "Gracielita"],
    "fernanda": ["Fer", "Ferchita"],
    "alejandra": ["Aleja", "Ale", "Alejita"],
    "alexandra": ["Alex", "Alexa"],
    "valentina": ["Vale", "Valen", "Valecita"],
    "natalia": ["Nata", "Naty", "Natis"],
    "catalina": ["Cata", "Cati", "Catica"],
    "camila": ["Cami", "Camilita", "Mila"],
    "gabriela": ["Gabi", "Gaby"],
    "victoria": ["Vicky", "Vicki"],
    "elizabeth": ["Eli", "Betty", "Liz"],
    "jennifer": ["Jenny", "Jeni"],
    "jessica": ["Jessi", "Yesi"],
    "estefania": ["Tefa", "Fanny", "Estefa"],
    "johana": ["Joha", "Yoja"],
    "johanna": ["Joha"],
    "lorena": ["Lore", "Lorenita"],
    "monica": ["Moni", "Moniquita"],
    "viviana": ["Vivi", "Vivianita"],
    "sofia": ["Sofi", "Sofita"],
    "laura": ["Lau", "Laurita"],
    "paula": ["Pau", "Paulita"],
    "juliana": ["Juli", "July"],
    "manuela": ["Manu", "Manuelita"],
    "rocio": ["Chío", "Roci"],
    "pilar": ["Pili", "Pilarica"],
    "elena": ["Elenita", "Nena"],
    "helena": ["Helenita", "Nena"],
    "esperanza": ["Espe", "Pera"],
    "concepcion": ["Concha", "Conchita"],
    "guadalupe": ["Lupe", "Lupita"],
    "amparo": ["Ampa", "Amparito"],
    "blanca": ["Blanquita"],
    "nancy": ["Nancycita"],
    "yolanda": ["Yoli", "Yola"],
    "clara": ["Clarita", "Clarisa"],
    "susana": ["Susi", "Susanita"],
    "tatiana": ["Tati", "Tatianita"],
    "lina": ["Linita"],
    "luisa": ["Lucha", "Luisita"],
    "mariana": ["Mari", "Marianita"],
    "stella": ["Estelita"],
    "esther": ["Tete"],
    "aurora": ["Yoyita"],
}

# Hipocorísticos de nombres compuestos, muy usados en Colombia.
APODOS_COMPUESTOS: dict[tuple[str, str], list[str]] = {
    ("maria", "fernanda"): ["Mafe", "Mafer"],
    ("maria", "jose"): ["Majo"],
    ("maria", "camila"): ["Maca", "Mariacami"],
    ("maria", "alejandra"): ["Maleja", "Malejita"],
    ("maria", "paula"): ["Mapau"],
    ("maria", "victoria"): ["Mavi", "Vicky"],
    ("maria", "isabel"): ["Marisa", "Maribel"],
    ("maria", "teresa"): ["Maite", "Marité"],
    ("maria", "eugenia"): ["Maru", "Maruja"],
    ("maria", "luisa"): ["Malu"],
    ("juan", "pablo"): ["Juampa", "Juanpa"],
    ("juan", "jose"): ["Juanjo"],
    ("juan", "camilo"): ["Juanca", "Juancho"],
    ("juan", "carlos"): ["Juanca", "Juancho"],
    ("juan", "david"): ["Juanda"],
    ("juan", "sebastian"): ["Juanse"],
    ("juan", "manuel"): ["Juanma"],
    ("juan", "esteban"): ["Juanes"],
    ("juan", "diego"): ["Juandi"],
    ("jose", "luis"): ["Joselo", "Pepe Luis"],
    ("luz", "marina"): ["Luzma"],
    ("luz", "mery"): ["Luzme"],
    ("ana", "maria"): ["Anamá", "Anita"],
}

# Grafías de nombres de origen anglosajón castellanizados (o al revés), comunes en Colombia.
GRAFIAS_ANGLO: dict[str, list[str]] = {
    "brayan": ["Bryan", "Brian", "Braian"],
    "brian": ["Brayan", "Bryan"],
    "jhon": ["John", "Jon", "Yon"],
    "john": ["Jhon", "Jon"],
    "jhonatan": ["Jonathan", "Yonatan", "Jhonathan"],
    "jonathan": ["Jhonatan", "Yonatan"],
    "jhonny": ["Johnny", "Yoni", "Jhony"],
    "jhony": ["Johnny", "Jhonny", "Yony"],
    "yeison": ["Jeison", "Jayson", "Jason"],
    "jeison": ["Yeison", "Jeisson", "Jason"],
    "stiven": ["Steven", "Estiven", "Stiwen"],
    "steven": ["Stiven", "Estiven", "Stephen"],
    "maicol": ["Michael", "Maikol", "Maycol"],
    "michel": ["Michelle", "Mishel"],
    "jessica": ["Yesica", "Jesica", "Yessica"],
    "jennifer": ["Yenifer", "Jenifer", "Yennifer"],
    "jenny": ["Yenny", "Jeny"],
    "yenny": ["Jenny", "Yeny"],
    "leidy": ["Lady", "Leydi", "Leidi"],
    "lady": ["Leidy", "Leydi"],
    "kelly": ["Keli", "Kely", "Queli"],
    "william": ["Wiliam", "Willian", "Uilliam"],
    "willian": ["William", "Wiliam"],
    "wilson": ["Uilson", "Wilsson"],
    "jeferson": ["Jefferson", "Yeferson", "Jeffersson"],
    "johana": ["Yohana", "Johanna", "Jhoana"],
    "johanna": ["Johana", "Yohanna"],
    "jhoana": ["Johana", "Yoana"],
    "jhoan": ["Johan", "Yoan"],
    "johan": ["Jhoan", "Yohan"],
    "joan": ["Jhoan", "Yoan"],
    "yamile": ["Jamile", "Yamilé"],
    "edwin": ["Eduin", "Edwuin"],
    "harold": ["Jarold", "Harol"],
    "harol": ["Harold", "Jarol"],
    "estefania": ["Stefania", "Stephania", "Estephania"],
    "deisy": ["Daisy", "Deysi", "Deysy"],
    "cindy": ["Sindy", "Cyndi"],
    "shirley": ["Sirley", "Shirly"],
    "katherine": ["Catherine", "Katerine", "Kathering"],
    "katherin": ["Katherine", "Katerin"],
    "katerine": ["Katherine", "Caterine"],
    "catherine": ["Katherine", "Caterin"],
    "geraldine": ["Yeraldín", "Geraldin"],
    "julieth": ["Juliet", "Yulieth"],
    "lizeth": ["Liseth", "Lisseth"],
    "liseth": ["Lizeth", "Liceth"],
    "yaneth": ["Janeth", "Yanet"],
    "janeth": ["Yaneth", "Janet"],
    "smith": ["Esmith", "Smit"],
    "sneider": ["Esneider", "Snaider"],
    "esneider": ["Sneider", "Esnaider"],
    "edinson": ["Edison", "Edisson"],
    "edison": ["Edinson", "Edisson"],
    "anderson": ["Ánderson", "Andersson"],
    "mayerly": ["Mayerli", "Maryerly"],
    "dayana": ["Dayanna", "Dahiana", "Dallana"],
    "dahiana": ["Dayana", "Dahyana"],
    "kevin": ["Kevyn", "Keivin"],
    "erick": ["Erik", "Eric"],
    "giovanny": ["Giovanni", "Yovanny", "Jovanny"],
    "giovanni": ["Giovanny", "Yovani"],
    "freddy": ["Fredy", "Fredi"],
    "danny": ["Dany", "Dani"],
    "ruby": ["Rubi"],
    "betty": ["Beti", "Betti"],
    "heidy": ["Heidi", "Jeidy"],
    "ximena": ["Jimena", "Gimena"],
    "jimena": ["Ximena"],
}

# Nombres que admiten partícula religiosa ("María del Carmen", "José de Jesús").
PARTICULAS_RELIGIOSAS = {
    "carmen": "del",
    "jesus": "de",
    "rosario": "del",
    "pilar": "del",
    "socorro": "del",
    "mar": "del",
    "consuelo": "del",
    "dolores": "de los",
    "mercedes": "de las",
    "angeles": "de los",
    "fatima": "de",
    "lourdes": "de",
    "belen": "de",
    "guadalupe": "de",
}

# Abreviaturas usadas en formularios a mano y sistemas viejos.
ABREVIATURAS: dict[str, list[str]] = {
    "maria": ["Ma.", "Mª", "Ma", "M."],
    "jose": ["J.", "Jse.", "Jos."],
    "francisco": ["Fco.", "Fco", "Franc."],
    "fernando": ["Fdo.", "Fdo"],
    "guillermo": ["Gmo.", "Guill."],
    "alejandro": ["Alej.", "Alejo."],
    "alejandra": ["Alej.", "Aleja."],
    "antonio": ["Ant.", "Anto."],
    "jesus": ["Js.", "Jes."],
    "margarita": ["Marg."],
    "cristina": ["Crist."],
    "concepcion": ["Concep."],
    "alexander": ["Alex.", "Alexr."],
    "alexandra": ["Alex.", "Alexa."],
    "sebastian": ["Seb.", "Sebast."],
    "eduardo": ["Edo.", "Ed."],
    "enrique": ["Enr."],
    "gonzalo": ["Gzlo."],
    "manuel": ["Man.", "Manl."],
    "rafael": ["Raf."],
}

APELLIDOS_ESPOSO = [
    "Rodríguez",
    "Martínez",
    "Gómez",
    "López",
    "González",
    "Hernández",
    "García",
    "Pérez",
    "Sánchez",
    "Ramírez",
    "Torres",
    "Díaz",
    "Vargas",
    "Moreno",
    "Rojas",
    "Jiménez",
    "Castro",
    "Ortiz",
    "Rubio",
    "Suárez",
    "Mejía",
    "Restrepo",
    "Ospina",
    "Arango",
    "Zapata",
    "Cárdenas",
    "Patiño",
    "Valencia",
    "Salazar",
    "Quintero",
    "Londoño",
    "Giraldo",
    "Bermúdez",
    "Cifuentes",
    "Villamizar",
    "Pardo",
    "Beltrán",
    "Acosta",
    "Guerrero",
    "Escobar",
]

VEREDAS = [
    "La Esperanza",
    "El Placer",
    "San José",
    "La Palma",
    "El Retiro",
    "Alto Bonito",
    "La Laguna",
    "El Salitre",
    "Buenos Aires",
    "Santa Rosa",
    "La Cuchilla",
    "El Tablazo",
    "Los Medios",
    "Pueblo Viejo",
    "La Mesa",
    "El Carmen",
    "Monte Loro",
    "Agua Bonita",
    "La Cristalina",
    "El Rosal",
    "Peñas Blancas",
    "Guacamayas",
    "El Hatillo",
    "La Siberia",
    "Quebrada Honda",
    "Llano Grande",
    "El Volcán",
    "Cañaveral",
    "La Unión",
    "San Isidro",
]
FINCAS = [
    "El Porvenir",
    "La Fortuna",
    "Villa Luz",
    "Los Naranjos",
    "El Recreo",
    "La Primavera",
    "San Antonio",
    "Las Brisas",
    "El Mirador",
    "La Ilusión",
    "Villa María",
    "Bellavista",
    "El Diamante",
    "La Gloria",
    "Los Guaduales",
    "Miramar",
    "El Edén",
    "La Esmeralda",
    "Los Cedros",
    "El Paraíso",
    "La Victoria",
    "Santa Helena",
    "El Cafetal",
    "Las Palmas",
]
CORREGIMIENTOS = [
    "San Cristóbal",
    "Santa Elena",
    "La Buitrera",
    "El Hormiguero",
    "Pance",
    "Palmitas",
    "Arenal",
    "Bocachica",
    "La Boquilla",
    "Pasacaballos",
    "La Playa",
    "Juan Mina",
    "Río Frío",
    "El Llanito",
    "Altavista",
    "Nazareth",
    "Betania",
    "Puerto Nuevo",
]
BARRIOS = [
    "La Floresta",
    "El Prado",
    "San Fernando",
    "Los Alpes",
    "Villa del Río",
    "El Recreo",
    "Las Américas",
    "Santa Mónica",
    "Ciudad Jardín",
    "Los Pinos",
    "El Carmen",
    "San Luis",
    "La Esmeralda",
    "Los Rosales",
    "Villa Nueva",
    "El Jardín",
    "La Victoria",
    "Simón Bolívar",
    "El Paraíso",
    "Las Ferias",
    "Kennedy",
    "Manga",
    "Cabecera",
    "El Poblado",
    "Belén",
]
CONJUNTOS = [
    "Reservas del Bosque",
    "Torres de San Juan",
    "Mirador del Parque",
    "Portal de la Sabana",
    "Altos de Santa Fe",
    "Balcones del Río",
    "Parques de Castilla",
    "Hacienda Santa Bárbara",
    "Prados del Norte",
    "Senderos de la Colina",
    "Bosques de Granada",
    "Terrazas del Lago",
    "Vista Hermosa",
    "Arboleda Campestre",
    "Puerta del Sol",
    "Brisas del Mar",
]
VIAS_NOMBRE: dict[str, list[str]] = {
    "bogota": [
        "Av. Boyacá",
        "Av. Caracas",
        "Av. Primero de Mayo",
        "Autopista Norte",
        "Av. Suba",
        "Av. Ciudad de Cali",
        "Av. Las Américas",
        "Av. Chile",
        "Av. El Dorado",
    ],
    "medellin": [
        "Av. El Poblado",
        "Av. Oriental",
        "Av. Nutibara",
        "Av. Bolivariana",
        "Av. San Juan",
        "Av. 80",
        "Av. Guayabal",
    ],
    "cali": [
        "Av. Roosevelt",
        "Av. Pasoancho",
        "Av. Sexta",
        "Av. Simón Bolívar",
        "Av. Ciudad Jardín",
    ],
    "barranquilla": [
        "Vía 40",
        "Av. Murillo",
        "Av. Circunvalar",
        "Av. Olaya Herrera",
        "Av. Cordialidad",
    ],
    "bucaramanga": [
        "Av. Quebradaseca",
        "Av. González Valencia",
        "Av. Los Búcaros",
        "Autopista Floridablanca",
        "Av. La Rosita",
    ],
    "cartagena": ["Av. Pedro de Heredia", "Av. San Martín", "Av. del Lago", "Av. Crisanto Luque"],
}
VIAS_NOMBRE_GENERICAS = [
    "Calle Real",
    "Carrera Principal",
    "Av. Principal",
    "Av. Santander",
    "Av. Bolívar",
    "Calle del Comercio",
    "Av. Los Fundadores",
    "Vía Principal",
]
EMPRESAS = [
    "constructoraandina",
    "agroinsumoscaribe",
    "logisticadelvalle",
    "transportesmontana",
    "clinicasanrafael",
    "colegiosantamaria",
    "distribuidoralapaz",
    "ingenieriasigma",
    "comercializadoraelsol",
    "serviciosintegralesco",
    "laboratoriosnova",
    "editorialcondor",
]
ALIAS_CORREO = ["banco", "compras", "finanzas", "notificaciones", "2", "personal", "pagos"]
CIUDADES_EXPEDICION = [
    ("Tunja", "Boyacá"),
    ("Pasto", "Nariño"),
    ("Neiva", "Huila"),
    ("Ibagué", "Tolima"),
    ("Montería", "Córdoba"),
    ("Sincelejo", "Sucre"),
    ("Valledupar", "Cesar"),
    ("Pereira", "Risaralda"),
    ("Manizales", "Caldas"),
    ("Armenia", "Quindío"),
    ("Villavicencio", "Meta"),
    ("Popayán", "Cauca"),
    ("Cúcuta", "Norte de Santander"),
    ("Santa Marta", "Magdalena"),
    ("Riohacha", "La Guajira"),
    ("Quibdó", "Chocó"),
    ("Yopal", "Casanare"),
    ("Duitama", "Boyacá"),
    ("Girardot", "Cundinamarca"),
    ("Zipaquirá", "Cundinamarca"),
]
TITULOS_HOMBRE = ["Dr.", "Sr.", "Ing.", "Lic.", "Don", "Prof."]
TITULOS_MUJER = ["Dra.", "Sra.", "Ing.", "Lic.", "Doña", "Srta."]
PESOS_DV = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
VECINOS_TECLADO = {
    "a": "qsz",
    "b": "vn",
    "c": "xv",
    "d": "sf",
    "e": "wr",
    "f": "dg",
    "g": "fh",
    "h": "gj",
    "i": "uo",
    "j": "hk",
    "k": "jl",
    "l": "kñ",
    "m": "n",
    "n": "bm",
    "o": "ip",
    "p": "o",
    "q": "w",
    "r": "et",
    "s": "ad",
    "t": "ry",
    "u": "yi",
    "v": "cb",
    "w": "qe",
    "x": "zc",
    "y": "tu",
    "z": "x",
}


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------


def _clave(texto: str) -> str:
    """Minúsculas sin tildes (conserva la ñ) para buscar en los vocabularios."""
    return _sin_tildes(texto, conservar_enie=True).lower().strip()


def _sin_tildes(texto: str, conservar_enie: bool = True) -> str:
    """Quita tildes y diéresis; opcionalmente también convierte la ñ en n."""
    salida = []
    for car in texto:
        if conservar_enie and car in "ñÑ":
            salida.append(car)
            continue
        base = unicodedata.normalize("NFD", car)
        salida.append("".join(c for c in base if unicodedata.category(c) != "Mn"))
    return "".join(salida)


def _vacio(valor: Any) -> bool:
    """Indica si un valor de la tabla de personas está vacío (None, NaN o texto vacío)."""
    if valor is None:
        return True
    if isinstance(valor, float) and valor != valor:
        return True
    return isinstance(valor, str) and not valor.strip()


def _texto(valor: Any) -> str | None:
    """Convierte un valor de la tabla a texto limpio o ``None``."""
    return None if _vacio(valor) else str(valor).strip()


def parece_mujer(primer_nombre: str) -> bool:
    """Heurística por nombre de pila: la tabla de personas no trae el sexo."""
    clave = _clave(primer_nombre)
    if clave in FEMENINOS_SIN_A:
        return True
    return clave.endswith("a") and clave not in MASCULINOS_CON_A


def digito_verificacion(numero: str) -> int:
    """Dígito de verificación al estilo NIT (módulo 11 con pesos primos)."""
    digitos = [int(c) for c in reversed(numero) if c.isdigit()]
    suma = sum(d * p for d, p in zip(digitos, PESOS_DV, strict=False))
    residuo = suma % 11
    return 11 - residuo if residuo > 1 else residuo


def direccion_urbana(
    via: str, numero_via: str, cuadrante: str | None, placa: str, consecutivo: str
) -> str:
    """Dirección limpia con nomenclatura colombiana: ``CL 54 SUR # 42A-68``."""
    texto = f"{via} {numero_via}"
    if cuadrante == "SUR":
        texto += " SUR"
    texto += f" # {placa}-{consecutivo}"
    if cuadrante == "ESTE":
        texto += " ESTE"
    return texto


def _diminutivo(nombre: str) -> str:
    """Diminutivo genérico (-ito, -ita, -cito) para nombres sin apodo en el diccionario."""
    base = _sin_tildes(nombre)
    minus = base.lower()
    if minus.endswith("a"):
        return base[:-1] + "ita"
    if minus.endswith("o"):
        return base[:-1] + "ito"
    if minus.endswith("e"):
        return base[:-1] + "ito"
    if minus.endswith(("n", "r")):
        return base + "cito"
    return base + "ito"


# ---------------------------------------------------------------------------
# Persona y decisiones de persona
# ---------------------------------------------------------------------------


@dataclass
class _Persona:
    """Datos limpios de una persona más las condiciones sorteadas para ella."""

    cluster: int
    tipo_documento: str
    numero_documento: str
    nombres: list[str]
    apellidos: list[str]
    fecha: str
    celular: str | None
    correo: str | None
    ciudad: str | None
    departamento: str | None
    direccion: str | None
    mujer: bool
    casada: str | None = None
    apodos: list[str] | None = None
    rural: dict[str, str] | None = None
    doc_ti: str | None = None
    doc_alterno: tuple[str, str] | None = None


def _leer_persona(fila: dict[str, Any]) -> _Persona:
    """Convierte una fila de la tabla de personas en una ``_Persona`` limpia."""
    nombres = [
        n for n in (_texto(fila.get("primer_nombre")), _texto(fila.get("segundo_nombre"))) if n
    ]
    apellidos = [
        a for a in (_texto(fila.get("primer_apellido")), _texto(fila.get("segundo_apellido"))) if a
    ]
    via = _texto(fila.get("direccion_via"))
    numero_via = _texto(fila.get("direccion_numero_via"))
    placa = _texto(fila.get("direccion_placa"))
    consecutivo = _texto(fila.get("direccion_consecutivo"))
    direccion = None
    if via and numero_via and placa and consecutivo:
        direccion = direccion_urbana(
            via, numero_via, _texto(fila.get("direccion_cuadrante")), placa, consecutivo
        )
    return _Persona(
        cluster=int(fila["cluster"]),
        tipo_documento=_texto(fila.get("tipo_documento")) or "CC",
        numero_documento=_texto(fila.get("numero_documento")) or "",
        nombres=nombres,
        apellidos=apellidos,
        fecha=_texto(fila.get("fecha_nacimiento")) or "",
        celular=_texto(fila.get("celular")),
        correo=_texto(fila.get("correo")),
        ciudad=_texto(fila.get("ciudad")),
        departamento=_texto(fila.get("departamento")),
        direccion=direccion,
        mujer=bool(nombres) and parece_mujer(nombres[0]),
    )


def _anio(fecha: str) -> int | None:
    """Año de una fecha ISO o ``None`` si no se puede leer."""
    try:
        return int(fecha[:4])
    except (TypeError, ValueError):
        return None


def _opciones_apodo(p: _Persona) -> list[str]:
    """Apodos posibles para la persona: compuestos, del diccionario o diminutivo."""
    if not p.nombres:
        return []
    claves = [_clave(n) for n in p.nombres]
    opciones: list[str] = []
    if len(claves) == 2 and (claves[0], claves[1]) in APODOS_COMPUESTOS:
        opciones += APODOS_COMPUESTOS[(claves[0], claves[1])]
    opciones += APODOS.get(claves[0], [])
    if not opciones:
        opciones.append(_diminutivo(p.nombres[0]))
    return opciones


def _sortear_rural(rng: random.Random, p: _Persona) -> dict[str, str]:
    """Elementos fijos de la ubicación rural de una persona."""
    return {
        "vereda": rng.choice(VEREDAS),
        "finca": rng.choice(FINCAS),
        "corregimiento": rng.choice(CORREGIMIENTOS),
        "km": str(rng.randint(2, 38)),
        "destino": rng.choice([c for c, _ in CIUDADES_EXPEDICION]),
        "lote": str(rng.randint(1, 60)),
        "municipio": p.ciudad or "",
    }


def _decidir_persona(rng: random.Random, p: _Persona, tasas: TasasCiegas2) -> None:
    """Sortea las condiciones de persona (se sortean siempre, para estabilizar la semilla)."""
    anio = _anio(p.fecha)
    edad = ANIO_REFERENCIA - anio if anio else 0

    u_casada, esposo = rng.random(), rng.choice(APELLIDOS_ESPOSO)
    if p.mujer and edad >= 22 and p.apellidos and u_casada < tasas.apellido_casada:
        propios = {_clave(a) for a in p.apellidos}
        if _clave(esposo) in propios:
            esposo = next(a for a in APELLIDOS_ESPOSO if _clave(a) not in propios)
        p.casada = esposo

    u_apodo = rng.random()
    if u_apodo < tasas.con_apodo:
        opciones = _opciones_apodo(p)
        if opciones:
            p.apodos = opciones

    u_rural, rural = rng.random(), _sortear_rural(rng, p)
    if u_rural < tasas.rural:
        p.rural = rural

    u_ti, cola_ti = rng.random(), f"{rng.randint(0, 99999):05d}"
    if (
        p.tipo_documento == "CC"
        and anio is not None
        and 1980 <= anio <= 2000
        and u_ti < tasas.doc_tarjeta_identidad
    ):
        p.doc_ti = p.fecha[2:4] + p.fecha[5:7] + p.fecha[8:10] + cola_ti

    u_ext = rng.random()
    tipo_alt = rng.choice(["PA", "PA", "PPT", "PEP"])
    if tipo_alt == "PA":
        numero_alt = (
            str(rng.randint(100_000_000, 199_999_999))
            if rng.random() < 0.6
            else "".join(rng.choice("ABCDEFGHJKLMNPRSTUVXYZ") for _ in range(2))
            + f"{rng.randint(0, 999999):06d}"
        )
    elif tipo_alt == "PPT":
        numero_alt = str(rng.randint(1_000_000, 6_999_999))
    else:
        numero_alt = str(rng.randint(10**14, 10**15 - 1))
    if p.tipo_documento == "CE" and u_ext < tasas.doc_extranjero_alterno:
        p.doc_alterno = (tipo_alt, numero_alt)


# ---------------------------------------------------------------------------
# Construcción de un registro
# ---------------------------------------------------------------------------


def _forma_casada(rng: random.Random, apellidos: list[str], esposo: str) -> list[str]:
    """Apellidos con el del esposo en alguna de las formas usadas en Colombia."""
    a1 = apellidos[0]
    a2 = apellidos[1] if len(apellidos) > 1 else None
    formas = [
        ([a1, "de", esposo], 0.38),  # reemplaza el segundo apellido: "Pérez de Gómez"
        ([a1, a2, "de", esposo] if a2 else [a1, "de", esposo], 0.15),  # lo agrega al final
        ([a1, esposo], 0.15),  # reemplaza el segundo, sin "de"
        ([a1, "De", esposo], 0.08),
        ([a1, "Vda. de", esposo], 0.05),  # viuda
        ([a1, "D.", esposo], 0.05),
        ([a1, "de", esposo, a2] if a2 else [a1, "de", esposo], 0.04),
        (["de", esposo], 0.04),  # solo el de casada, por costumbre antigua
        ([esposo, a1], 0.06),  # el del esposo adelante, por error de digitación
    ]
    piezas = [f for f, _ in formas]
    pesos = [w for _, w in formas]
    return [x for x in rng.choices(piezas, weights=pesos)[0] if x]


def _forma_rural(rng: random.Random, r: dict[str, str]) -> str:
    """Una de las formas en que se escribe una ubicación rural."""
    formas = [
        f"Vereda {r['vereda']} Finca {r['finca']}",
        f"Vda. {r['vereda']} - Fca. {r['finca']}",
        f"VDA {r['vereda'].upper()}",
        f"Finca {r['finca']}, vereda {r['vereda']}",
        f"Km {r['km']} vía {r['municipio'] or 'el pueblo'} - {r['destino']}, Finca {r['finca']}",
        f"Corregimiento {r['corregimiento']}, vereda {r['vereda']}",
        f"Vereda {r['vereda']} lote {r['lote']}",
        f"Sector rural vda {r['vereda']}",
        f"Fca {r['finca']} Vda {r['vereda']}",
    ]
    return rng.choice(formas)


def _cambiar_letra(rng: random.Random, palabra: str) -> str:
    """Un error de digitación: tecla vecina, letra omitida, duplicada o dos letras cruzadas."""
    if len(palabra) < 4:
        return palabra
    i = rng.randrange(1, len(palabra) - 1)
    op = rng.choice(["vecina", "omitir", "duplicar", "cruzar"])
    car = palabra[i]
    if op == "vecina" and _clave(car) in VECINOS_TECLADO:
        nueva = rng.choice(VECINOS_TECLADO[_clave(car)])
        nueva = nueva.upper() if car.isupper() else nueva
        return palabra[:i] + nueva + palabra[i + 1 :]
    if op == "omitir":
        return palabra[:i] + palabra[i + 1 :]
    if op == "duplicar":
        return palabra[:i] + car + palabra[i:]
    return palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2 :]


def _nueva_direccion(rng: random.Random) -> str:
    """Dirección urbana distinta (domicilio anterior de la persona)."""
    via = rng.choice(["CL", "KR", "DG", "TV", "AV"])
    numero = f"{rng.randint(1, 150)}{rng.choice(['', '', 'A', 'B', 'C'])}"
    placa = f"{rng.randint(1, 140)}{rng.choice(['', '', 'A', 'B'])}"
    return direccion_urbana(
        via, numero, rng.choice([None, None, None, "SUR"]), placa, str(rng.randint(2, 99))
    )


def _registro(
    rng: random.Random,
    p: _Persona,
    t: TasasCiegas2,
    forzar: set[str],
) -> tuple[dict[str, Any], list[str]]:
    """Construye un registro de la persona y devuelve también los errores aplicados."""
    errores: list[str] = []

    def sale(nombre: str) -> bool:
        return rng.random() < getattr(t, nombre)

    def usa(condicion: str) -> bool:
        return condicion in forzar or rng.random() < USO_CONDICION

    nombres = list(p.nombres)
    apellidos = list(p.apellidos)
    tipo, numero = p.tipo_documento, p.numero_documento
    fecha: str | None = p.fecha
    celular, correo = p.celular, p.correo
    direccion, ciudad, departamento = p.direccion, p.ciudad, p.departamento
    documento_reemplazado = False

    # --- Documento ---
    if p.doc_ti and usa("doc_tarjeta_identidad"):
        tipo, numero = "TI", p.doc_ti
        documento_reemplazado = True
        errores.append("doc_tarjeta_identidad")
    elif p.doc_alterno and usa("doc_extranjero_alterno"):
        tipo, numero = p.doc_alterno
        documento_reemplazado = True
        errores.append("doc_extranjero_alterno")
    else:
        if sale("digito_documento") and len(numero) > 3:
            i = rng.randrange(len(numero))
            op = rng.choice(["cambiar", "transponer", "omitir"])
            if op == "cambiar":
                nuevo = rng.choice([d for d in "0123456789" if d != numero[i]])
                numero = numero[:i] + nuevo + numero[i + 1 :]
            elif op == "transponer" and i < len(numero) - 1 and numero[i] != numero[i + 1]:
                numero = numero[:i] + numero[i + 1] + numero[i] + numero[i + 2 :]
            else:
                numero = numero[:i] + numero[i + 1 :]
            if numero != p.numero_documento:
                errores.append("digito_documento")
        if sale("digito_verificacion"):
            dv = digito_verificacion(numero)
            numero = rng.choice([f"{numero}-{dv}", f"{numero}{dv}", f"{numero} - {dv}"])
            errores.append("digito_verificacion")

    # --- Nombres ---
    if p.apodos and usa("con_apodo"):
        apodo = rng.choice(p.apodos)
        nombres = [apodo] if rng.random() < 0.75 or len(nombres) < 2 else [apodo, nombres[1]]
        errores.append("con_apodo")
    else:
        if len(nombres) > 1 and sale("segundo_nombre_omitido"):
            nombres = nombres[:1]
            errores.append("segundo_nombre_omitido")
        for i, n in enumerate(nombres):
            if _clave(n) in GRAFIAS_ANGLO and sale("grafia_anglo"):
                nombres[i] = rng.choice(GRAFIAS_ANGLO[_clave(n)])
                errores.append("grafia_anglo")
        if len(nombres) > 1 and PARTICULAS_RELIGIOSAS.get(_clave(nombres[1])):
            if sale("particula_religiosa"):
                nombres = [nombres[0], PARTICULAS_RELIGIOSAS[_clave(nombres[1])], nombres[1]]
                errores.append("particula_religiosa")
        # Solo se abrevia si queda otro nombre completo ("Ma. José", no "Ma." a secas).
        abreviable = len(nombres) > 1 and _clave(nombres[0]) in ABREVIATURAS
        if abreviable and sale("abreviatura_nombre"):
            nombres[0] = rng.choice(ABREVIATURAS[_clave(nombres[0])])
            errores.append("abreviatura_nombre")
        elif len(nombres) > 1 and sale("iniciales"):
            forma = rng.choice(["primero", "segundo", "segundo_sin_punto"])
            if forma == "primero":
                nombres[0] = nombres[0][0] + "."
            else:
                ultimo = nombres[-1]
                nombres[-1] = ultimo[0] + ("." if forma == "segundo" else "")
            errores.append("iniciales")
    if sale("titulo"):
        titulo = rng.choice(TITULOS_MUJER if p.mujer else TITULOS_HOMBRE)
        nombres = [titulo] + nombres
        errores.append("titulo")

    # --- Apellidos ---
    if p.casada and usa("apellido_casada"):
        apellidos = _forma_casada(rng, apellidos, p.casada)
        errores.append("apellido_casada")
    else:
        if len(apellidos) > 1 and sale("segundo_apellido_omitido"):
            apellidos = apellidos[:1]
            errores.append("segundo_apellido_omitido")
        if len(apellidos) == 2 and sale("apellidos_guion"):
            apellidos = [rng.choice(["-", " - ", "-"]).join(apellidos)]
            errores.append("apellidos_guion")

    texto_nombres = " ".join(nombres)
    texto_apellidos = " ".join(apellidos)

    if sale("letra"):
        if rng.random() < 0.5:
            partes = texto_nombres.split(" ")
            j = max(range(len(partes)), key=lambda k: len(partes[k]))
            partes[j] = _cambiar_letra(rng, partes[j])
            nuevo = " ".join(partes)
            cambio = nuevo != texto_nombres
            texto_nombres = nuevo
        else:
            partes = texto_apellidos.split(" ")
            j = max(range(len(partes)), key=lambda k: len(partes[k]))
            partes[j] = _cambiar_letra(rng, partes[j])
            nuevo = " ".join(partes)
            cambio = nuevo != texto_apellidos
            texto_apellidos = nuevo
        if cambio:
            errores.append("letra")

    # --- Fecha ---
    if fecha and sale("anio_dos_digitos"):
        anio, mes, dia = fecha[:4], fecha[5:7], fecha[8:10]
        fecha = rng.choice(
            [f"{dia}/{mes}/{anio[2:]}", f"{dia}-{mes}-{anio[2:]}", f"{anio[2:]}{mes}{dia}"]
        )
        errores.append("anio_dos_digitos")

    # --- Celular ---
    if celular and sale("celular_cambiado"):
        celular = "3" + rng.choice("0123512") + "".join(rng.choice("0123456789") for _ in range(8))
        errores.append("celular_cambiado")
    if celular and sale("celular_longitud"):
        i = rng.randrange(1, len(celular))
        celular = (
            celular[:i] + celular[i - 1] + celular[i:]
            if rng.random() < 0.5
            else celular[:i] + celular[i + 1 :]
        )
        errores.append("celular_longitud")

    # --- Correo ---
    if sale("correo_corporativo") and p.nombres and p.apellidos:
        usuario = rng.choice(
            [
                f"{p.nombres[0]}.{p.apellidos[0]}",
                f"{p.nombres[0][0]}{p.apellidos[0]}",
                f"{p.nombres[0]}{p.apellidos[0][0]}",
            ]
        )
        usuario = _sin_tildes(usuario, conservar_enie=False).lower().replace(" ", "")
        correo = f"{usuario}@{rng.choice(EMPRESAS)}.com.co"
        errores.append("correo_corporativo")
    elif correo and "@" in correo and sale("correo_alias"):
        usuario, dominio = correo.split("@", 1)
        correo = f"{usuario}+{rng.choice(ALIAS_CORREO)}@{dominio}"
        errores.append("correo_alias")

    # --- Dirección ---
    if p.rural:
        rural = p.rural
        if sale("direccion_anterior"):
            rural = dict(rural, vereda=rng.choice(VEREDAS), finca=rng.choice(FINCAS))
            errores.append("direccion_anterior")
        direccion = _forma_rural(rng, rural)
        errores.append("rural")
    else:
        if sale("direccion_anterior"):
            direccion = _nueva_direccion(rng)
            errores.append("direccion_anterior")
        if sale("barrio_conjunto"):
            direccion = rng.choice(
                [
                    f"Conjunto {rng.choice(CONJUNTOS)} Torre {rng.randint(1, 8)} "
                    f"Apto {rng.randint(1, 20)}0{rng.randint(1, 4)}",
                    f"Barrio {rng.choice(BARRIOS)} Mz {rng.randint(1, 30)} "
                    f"Casa {rng.randint(1, 40)}",
                    f"Urb. {rng.choice(CONJUNTOS)} casa {rng.randint(1, 120)}",
                    f"Edificio {rng.choice(CONJUNTOS)} apto {rng.randint(101, 1204)}",
                    f"B/ {rng.choice(BARRIOS)}",
                ]
            )
            errores.append("barrio_conjunto")
        elif direccion and "#" in direccion and sale("via_nombre_propio"):
            clave_ciudad = _clave(ciudad or "")
            opciones = next(
                (v for k, v in VIAS_NOMBRE.items() if k in clave_ciudad), VIAS_NOMBRE_GENERICAS
            )
            direccion = f"{rng.choice(opciones)} #{direccion.split('#', 1)[1]}"
            errores.append("via_nombre_propio")

    # --- Ciudad ---
    if sale("ciudad_expedicion"):
        candidatas = [c for c in CIUDADES_EXPEDICION if c[0] != ciudad]
        ciudad, departamento = rng.choice(candidatas)
        errores.append("ciudad_expedicion")

    # --- Campo faltante (nunca deja el registro sin datos que lo liguen) ---
    if sale("campo_faltante"):
        opciones = ["celular", "correo", "direccion"]
        if not documento_reemplazado:
            opciones.append("fecha")
        campo = rng.choice(opciones)
        if campo == "celular" and celular:
            celular = None
            errores.append("campo_faltante")
        elif campo == "correo" and correo:
            correo = None
            errores.append("campo_faltante")
        elif campo == "direccion" and direccion:
            direccion = None
            errores.append("campo_faltante")
        elif campo == "fecha" and fecha:
            fecha = None
            errores.append("campo_faltante")

    registro: dict[str, Any] = {
        "tipo_documento": tipo,
        "numero_documento": numero,
        "nombres": texto_nombres,
        "apellidos": texto_apellidos,
        "fecha_nacimiento": fecha,
        "celular": celular,
        "correo": correo,
        "direccion": direccion,
        "ciudad": ciudad,
        "departamento": departamento,
        "cluster": p.cluster,
    }

    # --- Transformaciones de todo el texto ---
    textuales = ["nombres", "apellidos", "direccion", "ciudad", "departamento"]
    if sale("tildes"):
        conservar = rng.random() < 0.5
        antes = [registro[c] for c in textuales]
        for c in textuales:
            if registro[c]:
                registro[c] = _sin_tildes(registro[c], conservar_enie=conservar)
        if antes != [registro[c] for c in textuales]:
            errores.append("tildes")
    if sale("pegado_mayusculas"):
        for c in textuales:
            if registro[c]:
                registro[c] = (
                    _sin_tildes(registro[c], conservar_enie=False).upper().replace(" ", "")
                )
        errores.append("pegado_mayusculas")
    elif sale("mayusculas"):
        for c in textuales:
            if registro[c]:
                registro[c] = registro[c].upper()
        errores.append("mayusculas")

    return registro, errores


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def capturar_con_traza(
    personas: pd.DataFrame, semilla: int = 0, tasas: TasasCiegas2 | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Igual que :func:`capturar`, pero devuelve además la traza de errores.

    La traza tiene una fila por (``unique_id``, ``error``) aplicado. Sirve para auditar el
    generador y para las pruebas; no se le entrega al modelo evaluado.
    """
    tasas = tasas or TasasCiegas2()
    rng = random.Random(semilla)
    filas: list[dict[str, Any]] = []
    trazas: list[list[str]] = []
    condiciones: list[dict[str, Any]] = []

    for fila in personas.to_dict("records"):
        p = _leer_persona(fila)
        _decidir_persona(rng, p, tasas)
        n = rng.choices(range(1, len(PESOS_REGISTROS) + 1), weights=PESOS_REGISTROS)[0]
        activas = {
            "apellido_casada": p.casada is not None,
            "con_apodo": p.apodos is not None,
            "doc_tarjeta_identidad": p.doc_ti is not None,
            "doc_extranjero_alterno": p.doc_alterno is not None,
        }
        # Cada condición activa se fuerza en un registro al azar para que se manifieste.
        forzados: dict[int, set[str]] = {}
        for nombre, activa in activas.items():
            if activa:
                forzados.setdefault(rng.randrange(n), set()).add(nombre)
        vistas: set[str] = set()
        for k in range(n):
            registro, errores = _registro(rng, p, tasas, forzados.get(k, set()))
            filas.append(registro)
            trazas.append(errores)
            vistas.update(errores)
        condiciones.append(
            {
                "cluster": p.cluster,
                "apellido_casada": "apellido_casada" in vistas,
                "con_apodo": "con_apodo" in vistas,
                "rural": p.rural is not None,
                "doc_tarjeta_identidad": "doc_tarjeta_identidad" in vistas,
                "doc_extranjero_alterno": "doc_extranjero_alterno" in vistas,
                "mujer_aparente": p.mujer,
                "n_registros": n,
            }
        )

    orden = list(range(len(filas)))
    rng.shuffle(orden)
    datos = {c: pd.Series([filas[i][c] for i in orden], dtype=object) for c in COLUMNAS[1:]}
    registros = pd.DataFrame(datos)
    registros.insert(0, "unique_id", range(len(orden)))
    registros["unique_id"] = registros["unique_id"].astype("int64")
    registros["cluster"] = registros["cluster"].astype("int64")
    registros = registros[COLUMNAS]

    traza = pd.DataFrame(
        [(uid, e) for uid, i in enumerate(orden) for e in trazas[i]],
        columns=["unique_id", "error"],
    )
    tabla_condiciones = pd.DataFrame(condiciones)
    return registros, tabla_condiciones, traza


def capturar(
    personas: pd.DataFrame, semilla: int = 0, tasas: TasasCiegas2 | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genera los registros capturados con errores y las condiciones de cada persona.

    Args:
        personas: una fila por persona con los datos verdaderos y limpios.
        semilla: semilla del generador aleatorio (mismo valor, mismo resultado).
        tasas: probabilidades por tipo de error; por defecto ``TasasCiegas2()``.

    Returns:
        ``(registros, condiciones)``. ``registros`` tiene las columnas de ``COLUMNAS`` y
        entre 1 y 6 filas por persona; ``condiciones`` tiene una fila por persona con
        ``cluster`` y columnas booleanas (``apellido_casada``, ``con_apodo``, ``rural``,
        ``doc_tarjeta_identidad``, ``doc_extranjero_alterno``, ``mujer_aparente``) más
        ``n_registros``.
    """
    registros, condiciones, _ = capturar_con_traza(personas, semilla=semilla, tasas=tasas)
    return registros, condiciones


def describir_tasas(tasas: TasasCiegas2 | None = None) -> dict[str, float]:
    """Diccionario ``{tipo_de_error: tasa}`` para reportes."""
    return asdict(tasas or TasasCiegas2())
