"""Estandarización v2 (hito 2b): correcciones tras la prueba ciega 1.

Reutiliza ``estandarizacion`` (v1, congelada en ``hito2-congelado-r1``) sin modificarla y
agrega:

- **Apellido de casada:** "Arango de Ramírez" se separa en apellidos "ARANGO" y apellido de
  casada "RAMIREZ", para que no ocupe el lugar del segundo apellido.
- **Apodos:** "Pepe", "Pacho", "Mafe"... pasan a su nombre formal (JOSE, FRANCISCO, MARIA
  FERNANDA).
- **Documento:** errores de lectura (O por 0, l por 1, S por 5, B por 8, Z por 2) en los
  tramos numéricos antes de quedarse con los dígitos.
- **Teléfonos:** todos los números del campo (celulares y fijos), no solo un celular.
- **Fecha:** formatos distintos ("12/10/1988", "20 de octubre de 1999", "09-ABR-1998",
  "19881012") a ISO. Corrección extra, fuera de la lista original.
- **Texto mal codificado:** "RamÃ­rez" vuelve a "Ramírez". Corrección extra.
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd

from identidades import estandarizacion as v1

# Apodos e hipocorísticos colombianos frecuentes -> nombre formal (en mayúsculas, sin
# tildes). Incluye diminutivos comunes; no pretende ser exhaustivo.
APODOS: dict[str, str] = {
    "PEPE": "JOSE",
    "PEPITO": "JOSE",
    "CHEPE": "JOSE",
    "JOSECITO": "JOSE",
    "PACHO": "FRANCISCO",
    "PANCHO": "FRANCISCO",
    "PAQUITO": "FRANCISCO",
    "KIKO": "FRANCISCO",
    "MEMO": "GUILLERMO",
    "GUILLE": "GUILLERMO",
    "CHUCHO": "JESUS",
    "CHUY": "JESUS",
    "CHARO": "ROSARIO",
    "CHAYO": "ROSARIO",
    "CONCHA": "CONCEPCION",
    "CONCHITA": "CONCEPCION",
    "NACHO": "IGNACIO",
    "ALEJO": "ALEJANDRO",
    "ALE": "ALEJANDRA",
    "ALEJA": "ALEJANDRA",
    "SANDRITA": "SANDRA",
    "MARGO": "MARGARITA",
    "MAGO": "MARGARITA",
    "LUCHO": "LUIS",
    "LUCHA": "LUISA",
    "LUCHITO": "LUIS",
    "MANOLO": "MANUEL",
    "MANU": "MANUEL",
    "TONO": "ANTONIO",
    "TONY": "ANTONIO",
    "TOÑO": "ANTONIO",
    "LOLA": "DOLORES",
    "LOLITA": "DOLORES",
    "BETO": "ALBERTO",
    "BETTY": "BEATRIZ",
    "BEA": "BEATRIZ",
    "CAMI": "CAMILO",
    "CAMILITO": "CAMILO",
    "PIPE": "FELIPE",
    "FELO": "RAFAEL",
    "RAFA": "RAFAEL",
    "NANDO": "FERNANDO",
    "FER": "FERNANDO",
    "FERCHO": "FERNANDO",
    "QUIQUE": "ENRIQUE",
    "KIKE": "ENRIQUE",
    "PACO": "FRANCISCO",
    "CHICO": "FRANCISCO",
    "TATO": "ARTURO",
    "TURO": "ARTURO",
    "GUSTI": "GUSTAVO",
    "TAVO": "GUSTAVO",
    "BENJA": "BENJAMIN",
    "NICO": "NICOLAS",
    "SEBAS": "SEBASTIAN",
    "SANTI": "SANTIAGO",
    "DANI": "DANIEL",
    "GABO": "GABRIEL",
    "GABI": "GABRIELA",
    "VALE": "VALENTINA",
    "CATA": "CATALINA",
    "CARO": "CAROLINA",
    "PATO": "PATRICIA",
    "PATY": "PATRICIA",
    "PATI": "PATRICIA",
    "LUPE": "GUADALUPE",
    "MECHE": "MERCEDES",
    "MECHAS": "MERCEDES",
    "CHELA": "GRACIELA",
    "CHELO": "CONSUELO",
    "TERE": "TERESA",
    "TERESITA": "TERESA",
    "LULU": "LUCIA",
    "CHUCHA": "JESUSA",
    "NENA": "ELENA",
    "ELE": "ELENA",
    "MAYE": "MARIA",
    "MARU": "MARIA",
    "MARI": "MARIA",
    "MARUJA": "MARIA",
    "TOMY": "TOMAS",
    "ANDY": "ANDRES",
    "ANDRESITO": "ANDRES",
    "JUANCHO": "JUAN",
    "JUANITO": "JUAN",
    "JUANCHITO": "JUAN",
    "CARLITOS": "CARLOS",
    "CHARLY": "CARLOS",
    "PEDRITO": "PEDRO",
    "PERICO": "PEDRO",
    "RICHI": "RICARDO",
    "RICKY": "RICARDO",
    "TITO": "ALBERTO",
    "BERNA": "BERNARDO",
    "LEO": "LEONARDO",
    "LALO": "EDUARDO",
    "EDU": "EDUARDO",
    "MIGUE": "MIGUEL",
    "MIGUELITO": "MIGUEL",
    "JORGITO": "JORGE",
    "ANITA": "ANA",
    "ROSITA": "ROSA",
    "JUANA": "JUANA",
    "VICKY": "VICTORIA",
    "SUSI": "SUSANA",
    "SUSY": "SUSANA",
    "CLAU": "CLAUDIA",
    "MONI": "MONICA",
    "NATY": "NATALIA",
    "NATI": "NATALIA",
    "PAU": "PAULA",
    "LAU": "LAURA",
    "LAURITA": "LAURA",
    "DIANITA": "DIANA",
    "MARTICA": "MARTA",
    "GLORITA": "GLORIA",
    "AMPARITO": "AMPARO",
    "CRISTI": "CRISTINA",
    "TINA": "CRISTINA",
    "MILE": "MILENA",
    "YOLI": "YOLANDA",
    "ADRI": "ADRIANA",
    "XIMENITA": "XIMENA",
    "FABI": "FABIOLA",
    "LUCHI": "LUCIA",
    "CUCHO": "AGUSTIN",
    "TINO": "AGUSTIN",
    "HUGUITO": "HUGO",
    "OSQUITAR": "OSCAR",
    "GERMANCITO": "GERMAN",
    "WILL": "WILLIAM",
    "WILLY": "WILLIAM",
    "JHONNY": "JOHN",
}

# Formas abreviadas de nombres compuestos -> nombre compuesto formal.
COMPUESTOS: dict[str, str] = {
    "ANAMARIA": "ANA MARIA",
    "MAFE": "MARIA FERNANDA",
    "MAJO": "MARIA JOSE",
    "MAJITO": "MARIA JOSE",
    "MALE": "MARIA ALEJANDRA",
    "MACA": "MARIA CAMILA",
    "MAPI": "MARIA PAULA",
    "MAPA": "MARIA PAULA",
    "MAGA": "MARIA GABRIELA",
    "MARIAJOSE": "MARIA JOSE",
    "MARIAFERNANDA": "MARIA FERNANDA",
    "JUANDA": "JUAN DAVID",
    "JUANPA": "JUAN PABLO",
    "JUANCA": "JUAN CARLOS",
    "JUANSE": "JUAN SEBASTIAN",
    "JUANES": "JUAN ESTEBAN",
    "JUANFE": "JUAN FELIPE",
    "JUANJO": "JUAN JOSE",
    "JOSEMA": "JOSE MANUEL",
    "LUISFE": "LUIS FELIPE",
    "MARIAN": "MARIA ANGELICA",
    "MA": "MARIA",
    "MARIA DEL": "MARIA DEL",
}

# Apellidos compuestos con "de" que no son apellido de casada.
APELLIDOS_CON_DE: set[str] = {"PONCE DE LEON", "MONTES DE OCA", "PEREZ DE GUZMAN"}

_OCR = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "l": "1",
        "I": "1",
        "i": "1",
        "S": "5",
        "s": "5",
        "B": "8",
        "Z": "2",
        "z": "2",
    }
)
_MESES = {
    "ENE": 1,
    "ENERO": 1,
    "FEB": 2,
    "FEBRERO": 2,
    "MAR": 3,
    "MARZO": 3,
    "ABR": 4,
    "ABRIL": 4,
    "MAY": 5,
    "MAYO": 5,
    "JUN": 6,
    "JUNIO": 6,
    "JUL": 7,
    "JULIO": 7,
    "AGO": 8,
    "AGOSTO": 8,
    "SEP": 9,
    "SEPT": 9,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCT": 10,
    "OCTUBRE": 10,
    "NOV": 11,
    "NOVIEMBRE": 11,
    "DIC": 12,
    "DICIEMBRE": 12,
}


def reparar_codificacion(valor: object) -> object:
    """Repara texto UTF-8 leído como Latin-1 ("JosÃ©" -> "José"); lo demás no cambia."""
    if not isinstance(valor, str) or not re.search(r"[ÃÂ]", valor):
        return valor
    try:
        return valor.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return valor


def _ocr_en_tramos_numericos(texto: str) -> str:
    """Corrige O/l/I/S/B/Z en los tramos que son mayoritariamente dígitos."""

    def corregir(m: re.Match) -> str:
        tramo = m.group(0)
        digitos = sum(c.isdigit() for c in tramo)
        return tramo.translate(_OCR) if digitos >= max(3, len(tramo) / 2) else tramo

    return re.sub(r"[0-9OolIiSsBZz]{4,}", corregir, texto)


def limpiar_documento(valor: object) -> str | None:
    """Documento solo dígitos, corrigiendo antes errores de lectura en el tramo numérico.

    Si el texto trae otra cosa después del número ("de Bogotá"), se queda con el tramo
    numérico más largo.
    """
    if v1._vacio(valor):
        return None
    texto = re.sub(r"(?<=\d)[.,\s](?=\d)", "", str(valor))  # 1.023.456 -> 1023456
    tramos = re.findall(r"\d+", _ocr_en_tramos_numericos(texto))
    if not tramos:
        return None
    return max(tramos, key=len).lstrip("0") or None


def extraer_telefonos(valor: object) -> list[str]:
    """Todos los teléfonos del campo: celulares (3XXXXXXXXX) y fijos (7 dígitos o 60X...).

    Quita el indicativo 57 y las extensiones ("ext 61"), y corrige errores de lectura.
    """
    if v1._vacio(valor):
        return []
    texto = re.split(r"\b(?:ext|extension|ext\.)\b", str(valor), flags=re.IGNORECASE)[0]
    texto = _ocr_en_tramos_numericos(texto)
    numeros = []
    for parte in re.split(r"[/;,|]|\by\b", texto):
        digitos = re.sub(r"\D", "", parte)
        if len(digitos) == 12 and digitos.startswith("57"):
            digitos = digitos[2:]
        if re.fullmatch(r"3\d{9}|60\d{8}|\d{7}", digitos):
            numeros.append(digitos)
    return list(dict.fromkeys(numeros))


def normalizar_fecha(valor: object) -> str | None:
    """Fecha en ISO desde formatos colombianos frecuentes; ``None`` si no se reconoce.

    Acepta YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD, DD/MM/YYYY (también con - o .), D/M/YYYY,
    DD/MM/YY, "07 de marzo de 1985" y 07-MAR-1985. Día antes que mes, como en Colombia.
    """
    if v1._vacio(valor):
        return None
    # Signos sueltos dentro del número no separan: "197'7" -> "1977".
    texto = re.sub(r"[_'\";]", "", str(valor))
    texto = re.sub(r"[^0-9A-Za-zÁÉÍÓÚáéíóúÑñ]+", " ", texto).strip()
    # Errores de lectura en las partes numéricas ("1B" -> "18", "lO" -> "10"), antes de
    # pasar a mayúsculas para no confundir la l con una L.
    partes = [
        p.translate(_OCR)
        if re.fullmatch(r"[0-9OolIiSsBZz]+", p) and (re.search(r"\d", p) or len(p) <= 2)
        else p
        for p in texto.split()
    ]
    partes = [v1.quitar_tildes(p.upper()) for p in partes]
    anio = mes = dia = None
    if len(partes) == 1 and re.fullmatch(r"\d{8}", partes[0]):
        anio, mes, dia = int(partes[0][:4]), int(partes[0][4:6]), int(partes[0][6:])
    else:
        partes = [p for p in partes if p != "DE"]
        if len(partes) == 3:
            a, b, c = partes
            if b in _MESES:
                b = str(_MESES[b])
            if all(x.isdigit() for x in (a, b, c)):
                if len(a) == 4:
                    anio, mes, dia = int(a), int(b), int(c)
                else:
                    dia, mes, anio = int(a), int(b), int(c)
                    if len(c) == 2:
                        anio += 1900 if anio > date.today().year % 100 else 2000
    if anio is None:
        return None
    try:
        return date(anio, mes, dia).isoformat()
    except ValueError:
        return None


def nombre_formal(nombres: str | None) -> str | None:
    """Reemplaza apodos y formas abreviadas por el nombre formal ("PEPE" -> "JOSE").

    Recibe nombres en mayúsculas y sin tildes.
    """
    if v1._vacio(nombres):
        return None
    junto = nombres.replace(" ", "")
    if junto in COMPUESTOS:
        return COMPUESTOS[junto]
    tokens = [COMPUESTOS.get(t, APODOS.get(t, t)) for t in nombres.split()]
    return " ".join(tokens)


def separar_apellido_casada(apellidos: str | None) -> tuple[str | None, str | None]:
    """Separa el apellido de casada: "ARANGO DE RAMIREZ" -> ("ARANGO", "RAMIREZ").

    Reconoce "DE X" o "VIUDA DE X" / "VDA DE X" cuando X es una sola palabra y va después
    de al menos un apellido. No toca "DE LA HOZ" ni apellidos como "PONCE DE LEON".
    Recibe apellidos en mayúsculas y sin tildes.
    """
    if v1._vacio(apellidos):
        return None, None
    if any(compuesto in apellidos for compuesto in APELLIDOS_CON_DE):
        return apellidos, None
    m = re.fullmatch(r"(.+?)\s+(?:(?:VIUDA|VDA)\s+)?DE\s+([A-Z]+)", apellidos)
    if not m or m.group(2) in v1.PARTICULAS:
        return apellidos, None
    return m.group(1), m.group(2)


def _texto(valor: object) -> str | None:
    return v1.quitar_tildes(v1.normalizar_nombre(reparar_codificacion(valor)))


def estandarizar(df: pd.DataFrame) -> pd.DataFrame:
    """Estandarización v2: v1 sobre los datos corregidos, más columnas nuevas.

    Columnas nuevas o reemplazadas: ``apellido_casada``, ``nombres_formales``,
    ``tokens_nombre`` (lista de palabras de nombres y apellidos, con nombres formales),
    ``telefonos`` (lista), ``fecha_std``; ``documento`` y ``celular_std`` pasan a la
    versión v2.
    """
    reparado = df.map(reparar_codificacion)
    apellidos = reparado["apellidos"].map(_texto)
    separados = apellidos.map(separar_apellido_casada)
    nombres_formales = reparado["nombres"].map(_texto).map(nombre_formal)
    base = reparado.assign(apellidos=separados.str[0], nombres=nombres_formales)

    s = v1.estandarizar(base)
    telefonos = df["celular"].map(extraer_telefonos)

    def tokens(fila: pd.Series) -> list[str] | None:
        palabras = []
        for campo in ("nombres_std", "primer_apellido", "segundo_apellido"):
            if isinstance(fila[campo], str):
                palabras += [nombre_formal(t) for t in fila[campo].split()]
        palabras = [p for t in palabras for p in t.split() if p not in v1.PARTICULAS]
        return sorted(set(palabras)) or None

    return s.assign(
        apellido_casada=separados.str[1],
        nombres_formales=nombres_formales,
        tokens_nombre=s.apply(tokens, axis=1),
        documento=df["numero_documento"].map(limpiar_documento),
        telefonos=telefonos.map(lambda t: t or None),
        celular_std=telefonos.map(lambda t: next((n for n in t if n.startswith("3")), None)),
        fecha_std=df["fecha_nacimiento"].map(normalizar_fecha),
    )
