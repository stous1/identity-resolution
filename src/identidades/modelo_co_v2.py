"""Esquema Splink v2 para clientes colombianos (hito 2b).

Usa ``estandarizacion_v2`` y cambia las comparaciones del esquema v1 (``modelo_co``, que
queda congelado sin cambios):

- **Apellido de casada** como comparación propia: si un registro lo tiene y el otro no,
  es neutral; ya no ocupa el lugar del segundo apellido.
- **Nombres:** los apodos ya llegan como nombre formal; nuevos niveles para nombre y
  apellido en campos intercambiados y para el primer nombre más otra palabra en común
  entre todos los campos de nombre (nombre completo escrito en un solo campo).
- **Primer apellido:** nivel para "el apellido de uno está en los nombres del otro".
- **Documento:** nivel adicional de hasta dos ediciones (OCR, dígitos de más).
- **Teléfonos:** cualquier teléfono contra cualquier teléfono; si alguno de los dos solo
  tiene un fijo, el nivel es aparte (no cuenta como teléfonos distintos). Los números
  que aparecen en más registros de los que puede tener una persona (relleno) se ignoran.
- **Fecha:** se compara la fecha normalizada a ISO.
"""

from __future__ import annotations

import jellyfish
import pandas as pd
import splink.comparison_level_library as cll
import splink.comparison_library as cl
from splink.internals.comparison_creator import ComparisonCreator

from identidades import estandarizacion_v2 as est
from identidades import modelo_co
from identidades.modelo import Esquema, Regla, _codigo_fonetico

# Más registros que esto con el mismo teléfono no pueden ser de una sola persona: es relleno.
MAX_REGISTROS_POR_TELEFONO: int = 6

COLUMNAS_TEXTO: list[str] = [
    "documento",
    "nombre_completo",
    "nombres_ordenados",
    "primer_nombre",
    "primer_apellido",
    "segundo_apellido",
    "apellido_casada",
    "fecha_nacimiento",
    "telefono",
    "email",
    "domicilio",
    "domicilio_clave",
    "municipio",
    "apellido_soundex",
    "nombre_metaphone",
]
COLUMNAS_LISTA: list[str] = ["telefonos", "tokens_nombre"]


def _sin_relleno(telefonos: pd.Series) -> pd.Series:
    """Quita de cada lista los teléfonos que aparecen en demasiados registros."""
    frecuencia = telefonos.explode().value_counts()
    relleno = set(frecuencia[frecuencia > MAX_REGISTROS_POR_TELEFONO].index)
    return telefonos.map(
        lambda t: [n for n in t if n not in relleno] or None if isinstance(t, list) else None
    )


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas del modelo v2 a partir de la estandarización v2."""
    s = est.estandarizar(df)
    clave = s["direccion_via"] + " " + s["direccion_numero"] + " # " + s["direccion_placa"]
    telefonos = _sin_relleno(s["telefonos"])
    modelo = pd.DataFrame(
        {
            "unique_id": df["unique_id"],
            "documento": s["documento"],
            "nombre_completo": s["nombres_std"],
            "nombres_ordenados": s["nombres_ordenados"],
            "primer_nombre": s["primer_nombre"],
            "primer_apellido": s["primer_apellido"],
            "segundo_apellido": s["segundo_apellido"],
            "apellido_casada": s["apellido_casada"],
            "tokens_nombre": s["tokens_nombre"],
            "fecha_nacimiento": s["fecha_std"],
            "telefonos": telefonos,
            "telefono": telefonos.map(
                lambda t: (
                    next((n for n in t if n.startswith("3")), None) if isinstance(t, list) else None
                )
            ),
            "email": s["correo_std"],
            "domicilio": s["direccion_std"],
            "domicilio_clave": clave.where(clave.notna(), None),
            "municipio": s["ciudad_std"],
        }
    )
    modelo = modelo.assign(
        apellido_soundex=modelo["primer_apellido"].map(_codigo_fonetico(jellyfish.soundex)),
        nombre_metaphone=modelo["primer_nombre"].map(_codigo_fonetico(jellyfish.metaphone)),
    )
    modelo[COLUMNAS_TEXTO] = modelo[COLUMNAS_TEXTO].astype("string")
    return modelo.assign(cluster=df["cluster"]) if "cluster" in df else modelo


def _par(columna: str) -> tuple[str, str]:
    return f'"{columna}_l"', f'"{columna}_r"'


def comparacion_documento() -> ComparisonCreator:
    """Documento: exacto, un dígito distinto, transpuestos, uno de más o menos, dos ediciones."""
    izq, der = _par("documento")
    return cl.CustomComparison(
        output_column_name="documento",
        comparison_levels=[
            cll.NullLevel("documento"),
            cll.ExactMatchLevel("documento"),
            cll.CustomLevel(
                f"length({izq}) = length({der}) and levenshtein({izq}, {der}) = 1",
                label_for_charts="Un dígito distinto",
            ),
            cll.CustomLevel(
                f"length({izq}) = length({der}) and damerau_levenshtein({izq}, {der}) = 1",
                label_for_charts="Dos dígitos transpuestos",
            ),
            cll.CustomLevel(
                f"abs(length({izq}) - length({der})) = 1 and levenshtein({izq}, {der}) = 1",
                label_for_charts="Un dígito de más o de menos",
            ),
            cll.CustomLevel(
                f"damerau_levenshtein({izq}, {der}) = 2", label_for_charts="Dos ediciones"
            ),
            cll.ElseLevel(),
        ],
        comparison_description="Documento",
    )


def comparacion_nombres() -> ComparisonCreator:
    """Nombres: iguales, en otro orden, mismo primero, campos cruzados o palabras comunes.

    El nivel de palabras comunes exige que el primer nombre de un registro aparezca en
    algún campo de nombre del otro: así no se activa entre hermanos, que comparten los dos
    apellidos pero no el nombre.
    """
    tok_izq, tok_der = _par("tokens_nombre")
    nom_izq, nom_der = _par("primer_nombre")
    return cl.CustomComparison(
        output_column_name="nombres",
        comparison_levels=[
            cll.NullLevel("nombre_completo"),
            cll.ExactMatchLevel("nombre_completo").configure(
                tf_adjustment_column="nombre_completo"
            ),
            cll.ExactMatchLevel("nombres_ordenados").configure(
                label_for_charts="Mismos nombres en otro orden"
            ),
            cll.ExactMatchLevel("primer_nombre").configure(label_for_charts="Mismo primer nombre"),
            cll.ColumnsReversedLevel("primer_nombre", "primer_apellido").configure(
                label_for_charts="Nombre y apellido en campos intercambiados"
            ),
            cll.CustomLevel(
                f"len(list_intersect({tok_izq}, {tok_der})) >= 2 and ("
                f"list_contains({tok_der}, {nom_izq}) or list_contains({tok_izq}, {nom_der}))",
                label_for_charts="Primer nombre y otra palabra en común (cualquier campo)",
            ),
            cll.JaroWinklerLevel("nombre_completo", 0.92),
            cll.JaroWinklerLevel("nombre_completo", 0.80),
            cll.ElseLevel(),
        ],
        comparison_description="Nombres",
    )


def comparacion_primer_apellido() -> ComparisonCreator:
    izq, der = _par("primer_apellido")
    tok_izq, tok_der = _par("tokens_nombre")
    return cl.CustomComparison(
        output_column_name="primer_apellido",
        comparison_levels=[
            cll.NullLevel("primer_apellido"),
            cll.ExactMatchLevel("primer_apellido").configure(
                tf_adjustment_column="primer_apellido"
            ),
            cll.JaroWinklerLevel("primer_apellido", 0.92),
            cll.JaroWinklerLevel("primer_apellido", 0.80),
            cll.CustomLevel(
                f"list_contains({tok_der}, {izq}) or list_contains({tok_izq}, {der})",
                label_for_charts="Apellido en otro campo de nombre del otro registro",
            ),
            cll.ElseLevel(),
        ],
        comparison_description="Primer apellido",
    )


def comparacion_telefonos() -> ComparisonCreator:
    """Cualquier teléfono contra cualquier teléfono; un fijo solo no cuenta como distinto."""
    izq, der = _par("telefonos")
    return cl.CustomComparison(
        output_column_name="telefonos",
        comparison_levels=[
            cll.NullLevel("telefonos"),
            cll.ArrayIntersectLevel("telefonos", min_intersection=1).configure(
                label_for_charts="Algún teléfono en común"
            ),
            cll.CustomLevel(
                f"len(list_filter({izq}, x -> starts_with(x, '3'))) = 0 "
                f"or len(list_filter({der}, x -> starts_with(x, '3'))) = 0",
                label_for_charts="Alguno de los dos sin celular (solo fijo)",
            ),
            cll.ElseLevel(),
        ],
        comparison_description="Teléfonos",
    )


def comparaciones() -> list[ComparisonCreator]:
    return [
        comparacion_documento(),
        comparacion_nombres(),
        comparacion_primer_apellido(),
        cl.JaroWinklerAtThresholds("segundo_apellido", [0.90]),
        cl.ExactMatch("apellido_casada"),
        cl.DateOfBirthComparison("fecha_nacimiento", input_is_string=True),
        comparacion_telefonos(),
        cl.EmailComparison("email").configure(term_frequency_adjustments=True),
        modelo_co.comparacion_domicilio(),
        cl.ExactMatch("municipio").configure(term_frequency_adjustments=True),
    ]


BLOQUEOS_EXACTOS: list[Regla] = modelo_co.BLOQUEOS_EXACTOS

BLOQUEOS_CANDIDATOS: list[Regla] = modelo_co.BLOQUEOS_CANDIDATOS + [
    ("primer_nombre", "fecha_nacimiento"),
    ("apellido_casada", "primer_nombre"),
    ("primer_apellido", "municipio"),
    ("right(documento, 6)",),
]

ESQUEMA_V2 = Esquema(
    nombre="colombia_v2",
    comparaciones=comparaciones,
    preparar=preparar,
    bloqueos_exactos=BLOQUEOS_EXACTOS,
    bloqueos_candidatos=BLOQUEOS_CANDIDATOS,
    bloqueos_em=modelo_co.BLOQUEOS_EM,
    reglas_deterministicas=modelo_co.REGLAS_DETERMINISTICAS,
)
