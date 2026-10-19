"""Estandarización v4: la dirección separada en predio y unidad (v1.1).

La estandarización v1 reconoce la dirección solo si termina en el consecutivo ("Calle 45 #
12-30"). Con un complemento detrás ("Apto 502", "Torre 2", "Piso 2") no la reconoce y la
deja como texto, así que el mismo apartamento escrito de dos formas cuenta como dos
direcciones distintas y el grafo del hito 3 la toma por relleno (diagnóstico de la v1.1).

``normalizar_direccion_v4`` busca la dirección base en cualquier parte del texto y lee el
resto como complemento:

- **predio**: la dirección base canónica, "KR 7 # 40-62" (vía, número, cuadrante, placa
  y consecutivo, como en v1);
- **unidad**: los componentes de la unidad en un orden fijo, "TO2 AP301": torre (TO),
  bloque (BL), interior (IN), casa dentro de un conjunto (CA), apartamento (AP), piso (PI)
  y local u oficina (LC);
- **conjunto**: el nombre del conjunto, la urbanización o el edificio, si aparece (no
  entra en la clave: muchos registros lo omiten).

La estandarización v1 y la v2 no cambian (están congeladas con sus modelos).
"""

from __future__ import annotations

import re

from identidades import estandarizacion as v1

# Orden canónico y etiqueta de cada componente de la unidad.
COMPONENTES: dict[str, str] = {
    "torre": "TO",
    "bloque": "BL",
    "interior": "IN",
    "casa": "CA",
    "apto": "AP",
    "piso": "PI",
    "local": "LC",
}
PALABRAS_UNIDAD: dict[str, str] = {
    "TORRE": "torre", "TORR": "torre", "TO": "torre", "TR": "torre", "T": "torre",
    "BLOQUE": "bloque", "BLOQ": "bloque", "BLQ": "bloque", "BL": "bloque", "BQ": "bloque",
    "INTERIOR": "interior", "INTER": "interior", "INT": "interior", "IN": "interior",
    "CASA": "casa", "CS": "casa", "CAS": "casa",
    "APARTAMENTO": "apto", "APARTAMIENTO": "apto", "APTO": "apto", "APT": "apto",
    "AP": "apto", "APTOS": "apto", "DPTO": "apto", "DEPTO": "apto", "APART": "apto",
    "PISO": "piso", "P": "piso",
    "LOCAL": "local", "LC": "local", "OFICINA": "local", "OF": "local",
}  # fmt: skip
ORDINALES: dict[str, str] = {
    "PRIMER": "1", "PRIMERO": "1", "SEGUNDO": "2", "TERCER": "3", "TERCERO": "3",
    "CUARTO": "4", "QUINTO": "5", "SEXTO": "6",
}  # fmt: skip
PALABRAS_CONJUNTO: set[str] = {
    "CONJUNTO", "CONJ", "CJTO", "CONJUNT", "RESIDENCIAL", "RES", "URBANIZACION", "URB",
    "UNIDAD", "EDIFICIO", "EDIF", "ED", "AGRUPACION", "MULTIFAMILIAR", "CIUDADELA",
}  # fmt: skip

_PATRON_BASE = re.compile(
    r"""
    (?:^|(?<=\s))(?P<via>[A-Z]+)\s+             # tipo de vía (se valida con ALIAS_VIA)
    (?P<numero>\d+\s?[A-Z]?(?:\s?BIS)?)         # número de vía: 45, 45A, 45 A, 45A BIS
    (?:\s+(?P<cuad1>SUR|ESTE|NORTE|OESTE|S|E))? # cuadrante después del número
    (?:\s*\#\s*|\s+)                             # separador: "#" o un espacio
    (?P<placa>\d+\s?[A-Z]?)                     # placa: 10, 43A
    (?:\s*-\s*|\s+)                              # guion o espacio
    (?P<consecutivo>\d+)                        # consecutivo: 20
    (?:\s+(?P<cuad2>SUR|ESTE|NORTE|OESTE))?     # cuadrante al final
    (?=\s|$)
    """,
    re.VERBOSE,
)
# Abreviaturas de vía que la v1 no reconoce (vistas en los datos de desarrollo).
ALIAS_VIA: dict[str, str] = {
    **v1.ALIAS_VIA, "K": "KR", "AK": "KR", "AC": "CL", "TRANSV": "TV", "TRANSVERSAL": "TV",
    "DIAG": "DG", "AVDA": "AV", "AVENIDA": "AV",
}  # fmt: skip
CUADRANTES: dict[str, str] = {"S": "SUR", "E": "ESTE"}
# "2DO", "3ER", "1ER", "2O" -> número de piso.
_ORDINAL_NUMERICO = re.compile(r"^(\d+)(?:ER|RO|DO|O|TO|VO|NO)$")


def _limpiar(valor: object) -> str | None:
    texto = v1.quitar_tildes(v1.normalizar_texto(valor))
    if texto is None:
        return None
    limpio = re.sub(r"[^A-Z0-9#\- ]", " ", texto)
    limpio = re.sub(r"(?<=\s)(?:N|NO|NRO|NUMERO)(?=\s)", "#", limpio)
    # Vía pegada al número: "KR62", "CL124" -> "KR 62", "CL 124".
    limpio = re.sub(r"\b(CALLE|CLL|CL|CARRERA|KRA|KR|CRA|CR|DG|TV|AV|AK|AC|K)(\d)", r"\1 \2",
                    limpio)  # fmt: skip
    # "T2", "AP301", "BL4": separa la palabra de la unidad del número pegado.
    limpio = re.sub(r"\b(TORRE|TO|TR|T|BL|BLQ|BLOQUE|AP|APTO|APT|INT|CS|CASA|P)(\d+)\b",
                    r"\1 \2", limpio)  # fmt: skip
    return re.sub(r"\s+", " ", limpio).strip() or None


def _leer_complemento(palabras: list[str]) -> tuple[dict[str, str], list[str]]:
    """Componentes de la unidad y palabras del nombre del conjunto o edificio."""
    unidad: dict[str, str] = {}
    nombre: list[str] = []
    i = 0
    while i < len(palabras):
        p = palabras[i]
        siguiente = palabras[i + 1] if i + 1 < len(palabras) else None
        ordinal = _ORDINAL_NUMERICO.match(p)
        if siguiente == "PISO" and (p.isdigit() or ordinal or p in ORDINALES):
            # "2 PISO", "2DO PISO", "SEGUNDO PISO"
            valor = p if p.isdigit() else ordinal.group(1) if ordinal else ORDINALES[p]
            unidad.setdefault("piso", valor)
            i += 2
            continue
        componente = PALABRAS_UNIDAD.get(p)
        if componente and siguiente is not None:
            valor_ordinal = _ORDINAL_NUMERICO.match(siguiente)
            if re.fullmatch(r"\d+[A-Z]?|[A-Z]", siguiente):
                if not (componente == "torre" and p == "T" and not siguiente[0].isdigit()):
                    unidad.setdefault(componente, siguiente.lstrip("0") or "0")
                    i += 2
                    continue
            if componente == "piso" and valor_ordinal:
                unidad.setdefault("piso", valor_ordinal.group(1))
                i += 2
                continue
        if p.isdigit() and not unidad and i == len(palabras) - 1 and len(p) >= 3:
            unidad["apto"] = p  # "Calle 10 # 20-30 301": número suelto al final
            i += 1
            continue
        nombre.append(p)
        i += 1
    return unidad, nombre


def clave_unidad(unidad: dict[str, str]) -> str | None:
    """Clave canónica de la unidad: "TO2 AP301" (orden fijo), o ``None`` si no hay."""
    partes = [f"{COMPONENTES[c]}{unidad[c]}" for c in COMPONENTES if c in unidad]
    return " ".join(partes) or None


def normalizar_direccion_v4(valor: object) -> dict[str, object]:
    """Predio, unidad y nombre del conjunto de una dirección colombiana.

    Devuelve ``predio`` (dirección base canónica o ``None`` si no se reconoce),
    ``unidad`` (clave canónica o ``None``), ``unidad_partes`` (lista de componentes),
    ``conjunto`` (nombre o ``None``), ``direccion`` (predio y unidad juntos; si no se
    reconoce el predio, el texto limpio) y ``via``.
    """
    vacio: dict[str, object] = {
        "predio": None,
        "unidad": None,
        "unidad_partes": None,
        "conjunto": None,
        "direccion": None,
        "via": None,
    }
    limpio = _limpiar(valor)
    if limpio is None:
        return vacio
    for m in _PATRON_BASE.finditer(limpio):
        via = ALIAS_VIA.get(m.group("via"))
        if via is None:
            continue
        numero = re.sub(r"\s+", "", m.group("numero")).replace("BIS", " BIS")
        placa = re.sub(r"\s+", "", m.group("placa"))
        cuadrante = m.group("cuad1") or m.group("cuad2")
        cuadrante = CUADRANTES.get(cuadrante, cuadrante)
        predio = f"{via} {numero}" + (f" {cuadrante}" if cuadrante else "")
        predio += f" # {placa}-{m.group('consecutivo')}"
        resto = (limpio[: m.start()] + " " + limpio[m.end() :]).split()
        unidad, nombre = _leer_complemento(resto)
        nombre = [p for p in nombre if p not in PALABRAS_CONJUNTO and p != "#"]
        clave = clave_unidad(unidad)
        return {
            "predio": predio,
            "unidad": clave,
            "unidad_partes": clave.split() if clave else None,
            "conjunto": " ".join(nombre) or None,
            "direccion": f"{predio} {clave}" if clave else predio,
            "via": via,
        }
    return {**vacio, "direccion": limpio}


# Palabras de direcciones de relleno o vagas: si una dirección no reconocida solo tiene
# estas palabras (o es muy corta), es genérica.
PALABRAS_DIRECCION_GENERICA: set[str] = {
    "CENTRO", "SIN", "DIRECCION", "CONOCIDA", "BARRIO", "NO", "TIENE", "NA", "N/A", "XX",
    "NINGUNA", "SD", "S/D", "NOTIENE", "DESCONOCIDA", "CIUDAD", "PUEBLO", "CASA", "LA", "EL",
}  # fmt: skip


def es_direccion_generica(valor: object) -> bool:
    """¿Es una dirección vaga o de relleno? Una rural sin nomenclatura no lo es."""
    d = normalizar_direccion_v4(valor)
    if d["predio"] is not None or d["direccion"] is None:
        return False
    palabras = str(d["direccion"]).split()
    return len(str(d["direccion"])) < 6 or all(p in PALABRAS_DIRECCION_GENERICA for p in palabras)
