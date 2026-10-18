"""Estandarización de datos de clientes colombianos.

Cada regla es una función pequeña y probada por separado:

- Texto: mayúsculas, espacios colapsados y una versión auxiliar sin tildes.
- Nombres y apellidos: separación de compuestos respetando partículas ("DE LA HOZ").
- Documento: solo dígitos.
- Celular: 10 dígitos que empiezan por 3 (se quita el indicativo 57).
- Correo: minúsculas y validación básica.
- Dirección: tipo de vía, número, cuadrante, placa y consecutivo, con una forma canónica
  ("KR 45 # 10-20", "CL 10 SUR # 43A-15").

Las funciones devuelven ``None`` cuando el valor está vacío o no es válido, para que el
modelo lo trate como dato faltante y no como un valor que coincide.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

PARTICULAS: set[str] = {"DE", "DEL", "LA", "LAS", "LOS", "Y"}

ALIAS_VIA: dict[str, str] = {
    "CALLE": "CL",
    "CL": "CL",
    "CLL": "CL",
    "CALL": "CL",
    "CLLE": "CL",
    "CARRERA": "KR",
    "KR": "KR",
    "KRA": "KR",
    "CRA": "KR",
    "CR": "KR",
    "CARR": "KR",
    "DIAGONAL": "DG",
    "DG": "DG",
    "DIAG": "DG",
    "TRANSVERSAL": "TV",
    "TV": "TV",
    "TRANS": "TV",
    "TR": "TV",
    "AVENIDA": "AV",
    "AV": "AV",
    "AVE": "AV",
}
CUADRANTES: set[str] = {"SUR", "ESTE", "NORTE", "OESTE"}

_PATRON_CORREO = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
_PATRON_DIRECCION = re.compile(
    r"""
    ^(?P<via>[A-Z]+)\s+                         # tipo de vía
    (?P<numero>\d+\s?[A-Z]?(?:\s?BIS)?)         # número de vía: 45, 45A, 45 A, 45A BIS
    (?:\s+(?P<cuad1>SUR|ESTE|NORTE|OESTE))?     # cuadrante después del número
    \s*\#?\s*                                   # separador (N°, No. y Nro ya son "#")
    (?P<placa>\d+\s?[A-Z]?)                     # placa: 10, 43A
    \s*-?\s*
    (?P<consecutivo>\d+)                        # consecutivo: 20
    (?:\s+(?P<cuad2>SUR|ESTE|NORTE|OESTE))?$    # cuadrante al final
    """,
    re.VERBOSE,
)


def _vacio(valor: object) -> bool:
    return valor is None or (isinstance(valor, float) and pd.isna(valor)) or str(valor) == ""


def normalizar_texto(valor: object) -> str | None:
    """Mayúsculas, sin espacios repetidos ni en los extremos; ``None`` si queda vacío."""
    if _vacio(valor):
        return None
    texto = re.sub(r"\s+", " ", str(valor)).strip().upper()
    return texto or None


def quitar_tildes(valor: str | None) -> str | None:
    """Quita tildes y diéresis; la Ñ pasa a N (variante frecuente al digitar)."""
    if valor is None:
        return None
    descompuesto = unicodedata.normalize("NFD", valor)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def normalizar_nombre(valor: object) -> str | None:
    """Mayúsculas, solo letras y espacios (conserva tildes y Ñ)."""
    texto = normalizar_texto(valor)
    if texto is None:
        return None
    texto = re.sub(r"[^A-ZÁÉÍÓÚÜÑ ]", " ", texto)
    return normalizar_texto(texto)


def _agrupar_particulas(tokens: list[str]) -> list[str]:
    """Une las partículas con la palabra siguiente: DE LA HOZ -> ["DE LA HOZ"]."""
    grupos, pendiente = [], []
    for token in tokens:
        if quitar_tildes(token) in PARTICULAS:
            pendiente.append(token)
        else:
            grupos.append(" ".join([*pendiente, token]))
            pendiente = []
    if pendiente:
        if grupos:
            grupos[-1] = " ".join([grupos[-1], *pendiente])
        else:
            grupos.append(" ".join(pendiente))
    return grupos


def separar_compuesto(valor: object) -> tuple[str | None, str | None]:
    """Separa un nombre o apellido compuesto en (primero, resto).

    "MARIA JOSE" -> ("MARIA", "JOSE"); "MARIA DE LOS ANGELES" -> ("MARIA",
    "DE LOS ANGELES"); "DE LA HOZ GOMEZ" -> ("DE LA HOZ", "GOMEZ").
    """
    texto = normalizar_nombre(valor)
    if texto is None:
        return None, None
    grupos = _agrupar_particulas(texto.split())
    return grupos[0], (" ".join(grupos[1:]) or None)


def ordenar_tokens(valor: str | None) -> str | None:
    """Palabras en orden alfabético: "JOSE MARIA" y "MARIA JOSE" quedan iguales."""
    if valor is None:
        return None
    return " ".join(sorted(valor.split()))


def limpiar_documento(valor: object) -> str | None:
    """Solo dígitos, sin ceros a la izquierda; ``None`` si no queda ninguno."""
    if _vacio(valor):
        return None
    digitos = re.sub(r"\D", "", str(valor)).lstrip("0")
    return digitos or None


def normalizar_celular(valor: object) -> str | None:
    """Celular colombiano de 10 dígitos que empieza por 3; quita el indicativo 57."""
    if _vacio(valor):
        return None
    digitos = re.sub(r"\D", "", str(valor))
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]
    return digitos if re.fullmatch(r"3\d{9}", digitos) else None


def normalizar_correo(valor: object) -> str | None:
    """Correo en minúsculas y sin espacios; ``None`` si no tiene forma de correo."""
    if _vacio(valor):
        return None
    correo = re.sub(r"\s+", "", str(valor)).lower()
    return correo if _PATRON_CORREO.fullmatch(correo) else None


def normalizar_direccion(valor: object) -> dict[str, str | None]:
    """Descompone una dirección colombiana y arma su forma canónica.

    Devuelve ``via``, ``numero_via``, ``cuadrante``, ``placa``, ``consecutivo`` y
    ``direccion`` (canónica). Si no se reconoce la estructura (por ejemplo "BARRIO
    CENTRO"), los componentes quedan en ``None`` y ``direccion`` es el texto
    normalizado.
    """
    vacio = dict.fromkeys(["via", "numero_via", "cuadrante", "placa", "consecutivo"])
    texto = quitar_tildes(normalizar_texto(valor))
    if texto is None:
        return {**vacio, "direccion": None}
    limpio = re.sub(r"[.,°º]", " ", texto)
    # "N°", "No.", "Nro" sueltos son el separador "#", no la letra del número de vía.
    limpio = re.sub(r"(?<=\s)(?:N|NO|NRO|NUMERO)(?=\s)", "#", limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    coincidencia = _PATRON_DIRECCION.match(limpio)
    via = ALIAS_VIA.get(coincidencia.group("via")) if coincidencia else None
    if not coincidencia or via is None:
        return {**vacio, "direccion": limpio}

    numero = re.sub(r"\s+", "", coincidencia.group("numero")).replace("BIS", " BIS")
    placa = re.sub(r"\s+", "", coincidencia.group("placa"))
    consecutivo = coincidencia.group("consecutivo")
    cuadrante = coincidencia.group("cuad1") or coincidencia.group("cuad2")
    canonica = f"{via} {numero}" + (f" {cuadrante}" if cuadrante else "")
    canonica += f" # {placa}-{consecutivo}"
    return {
        "via": via,
        "numero_via": numero,
        "cuadrante": cuadrante,
        "placa": placa,
        "consecutivo": consecutivo,
        "direccion": canonica,
    }


def estandarizar(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica todas las reglas a un DataFrame de registros capturados.

    Agrega columnas (no modifica las originales): ``nombres_std``, ``primer_nombre``,
    ``segundo_nombre``, ``nombres_ordenados``, ``primer_apellido``, ``segundo_apellido``
    (estas en mayúsculas y sin tildes), ``nombres_con_tildes`` y ``apellidos_con_tildes``
    (auxiliares, en mayúsculas), ``documento``, ``celular_std``, ``correo_std``,
    ``direccion_std`` y sus componentes, ``ciudad_std``.
    """
    nombres = df["nombres"].map(normalizar_nombre)
    apellidos = df["apellidos"].map(normalizar_nombre)
    nombres_sin = nombres.map(quitar_tildes)
    apellidos_sin = apellidos.map(quitar_tildes)
    sep_nombres = nombres_sin.map(separar_compuesto)
    sep_apellidos = apellidos_sin.map(separar_compuesto)
    direcciones = pd.DataFrame(df["direccion"].map(normalizar_direccion).tolist(), index=df.index)
    return df.assign(
        nombres_con_tildes=nombres,
        apellidos_con_tildes=apellidos,
        nombres_std=nombres_sin,
        primer_nombre=sep_nombres.str[0],
        segundo_nombre=sep_nombres.str[1],
        nombres_ordenados=nombres_sin.map(ordenar_tokens),
        primer_apellido=sep_apellidos.str[0],
        segundo_apellido=sep_apellidos.str[1],
        documento=df["numero_documento"].map(limpiar_documento),
        celular_std=df["celular"].map(normalizar_celular),
        correo_std=df["correo"].map(normalizar_correo),
        direccion_std=direcciones["direccion"],
        direccion_via=direcciones["via"],
        direccion_numero=direcciones["numero_via"],
        direccion_placa=direcciones["placa"],
        ciudad_std=df["ciudad"].map(normalizar_texto).map(quitar_tildes),
    )
