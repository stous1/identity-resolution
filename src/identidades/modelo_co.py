"""Esquema Splink para clientes colombianos (hito 2).

Las comparaciones usan columnas con nombres propios del modelo (``documento``,
``nombre_completo``, ``telefono``...). Dos formas de prepararlas, con el mismo modelo:

- ``preparar_estandarizado``: aplica ``identidades.estandarizacion`` (mayúsculas, sin
  tildes, compuestos con partículas, documento solo dígitos, celular, correo y dirección
  canónicos).
- ``preparar_crudo``: sin estandarización; solo parte los textos por espacios para
  llenar las mismas columnas. Sirve para medir cuánto aporta estandarizar.
"""

from __future__ import annotations

import jellyfish
import pandas as pd
import splink.comparison_level_library as cll
import splink.comparison_library as cl
from splink.internals.comparison_creator import ComparisonCreator

from identidades import estandarizacion as est
from identidades.modelo import Esquema, Regla, _codigo_fonetico

COLUMNAS_MODELO: list[str] = [
    "documento",
    "nombre_completo",
    "nombres_ordenados",
    "primer_nombre",
    "primer_apellido",
    "segundo_apellido",
    "fecha_nacimiento",
    "telefono",
    "email",
    "domicilio",
    "domicilio_clave",
    "municipio",
    "apellido_soundex",
    "nombre_metaphone",
]


def _con_foneticos(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(
        apellido_soundex=df["primer_apellido"].map(_codigo_fonetico(jellyfish.soundex)),
        nombre_metaphone=df["primer_nombre"].map(_codigo_fonetico(jellyfish.metaphone)),
    )


def _finalizar(modelo: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Agrega los códigos fonéticos y conserva la verdad (``cluster``) si viene en ``df``.

    Las columnas del modelo se fuerzan a texto: si una queda toda en nulos (por ejemplo
    ``domicilio_clave`` sin estandarizar), DuckDB la leería como número y fallarían las
    comparaciones de texto.
    """
    modelo = _con_foneticos(modelo)
    columnas = [c for c in COLUMNAS_MODELO if c in modelo]
    modelo[columnas] = modelo[columnas].astype("string")
    return modelo.assign(cluster=df["cluster"]) if "cluster" in df else modelo


def preparar_estandarizado(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas del modelo a partir de los datos estandarizados."""
    s = est.estandarizar(df)
    clave = s["direccion_via"] + " " + s["direccion_numero"] + " # " + s["direccion_placa"]
    modelo = pd.DataFrame(
        {
            "unique_id": df["unique_id"],
            "documento": s["documento"],
            "nombre_completo": s["nombres_std"],
            "nombres_ordenados": s["nombres_ordenados"],
            "primer_nombre": s["primer_nombre"],
            "primer_apellido": s["primer_apellido"],
            "segundo_apellido": s["segundo_apellido"],
            "fecha_nacimiento": df["fecha_nacimiento"],
            "telefono": s["celular_std"],
            "email": s["correo_std"],
            "domicilio": s["direccion_std"],
            "domicilio_clave": clave.where(clave.notna(), None),
            "municipio": s["ciudad_std"],
        }
    )
    return _finalizar(modelo, df)


def _partir(valor: object) -> list[str]:
    return [] if est._vacio(valor) else str(valor).split()


def preparar_crudo(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas del modelo sin estandarizar: los textos tal cual, partidos por espacios."""
    nombres = df["nombres"].map(_partir)
    apellidos = df["apellidos"].map(_partir)
    modelo = pd.DataFrame(
        {
            "unique_id": df["unique_id"],
            "documento": df["numero_documento"],
            "nombre_completo": df["nombres"],
            "nombres_ordenados": nombres.map(lambda t: " ".join(sorted(t)) or None),
            "primer_nombre": nombres.map(lambda t: t[0] if t else None),
            "primer_apellido": apellidos.map(lambda t: t[0] if t else None),
            "segundo_apellido": apellidos.map(lambda t: " ".join(t[1:]) or None),
            "fecha_nacimiento": df["fecha_nacimiento"],
            "telefono": df["celular"],
            "email": df["correo"],
            "domicilio": df["direccion"],
            "domicilio_clave": None,
            "municipio": df["ciudad"],
        }
    )
    return _finalizar(modelo, df)


def _l(columna: str) -> str:
    return f'"{columna}_l"'


def _r(columna: str) -> str:
    return f'"{columna}_r"'


def comparacion_documento() -> ComparisonCreator:
    """Documento por niveles: exacto, un dígito distinto, transpuestos, uno de más o menos."""
    izq, der = _l("documento"), _r("documento")
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
            cll.ElseLevel(),
        ],
        comparison_description="Documento",
    )


def comparacion_nombres() -> ComparisonCreator:
    """Nombres: completos iguales, en otro orden, mismo primer nombre o parecidos."""
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
            cll.JaroWinklerLevel("nombre_completo", 0.92),
            cll.JaroWinklerLevel("nombre_completo", 0.80),
            cll.ElseLevel(),
        ],
        comparison_description="Nombres",
    )


def comparacion_domicilio() -> ComparisonCreator:
    """Dirección: igual, misma vía, número y placa, o parecida."""
    return cl.CustomComparison(
        output_column_name="domicilio",
        comparison_levels=[
            cll.NullLevel("domicilio"),
            cll.ExactMatchLevel("domicilio").configure(tf_adjustment_column="domicilio"),
            cll.ExactMatchLevel("domicilio_clave").configure(
                label_for_charts="Misma vía, número y placa"
            ),
            cll.JaroWinklerLevel("domicilio", 0.90),
            cll.ElseLevel(),
        ],
        comparison_description="Dirección",
    )


def comparaciones() -> list[ComparisonCreator]:
    return [
        comparacion_documento(),
        comparacion_nombres(),
        cl.JaroWinklerAtThresholds("primer_apellido", [0.92, 0.80]).configure(
            term_frequency_adjustments=True
        ),
        cl.JaroWinklerAtThresholds("segundo_apellido", [0.90]),
        cl.DateOfBirthComparison("fecha_nacimiento", input_is_string=True),
        cl.ExactMatch("telefono").configure(term_frequency_adjustments=True),
        cl.EmailComparison("email").configure(term_frequency_adjustments=True),
        comparacion_domicilio(),
        cl.ExactMatch("municipio").configure(term_frequency_adjustments=True),
    ]


BLOQUEOS_EXACTOS: list[Regla] = [
    ("documento",),
    ("telefono",),
    ("email",),
    ("primer_apellido", "fecha_nacimiento"),
]

BLOQUEOS_CANDIDATOS: list[Regla] = [
    ("fecha_nacimiento",),
    ("right(documento, 4)",),
    ("substr(documento, 1, 5)",),
    ("apellido_soundex", "substr(fecha_nacimiento, 1, 4)"),
    ("nombre_metaphone", "apellido_soundex"),
    ("nombres_ordenados", "municipio"),
    ("domicilio",),
    ("domicilio_clave",),
    ("segundo_apellido", "substr(fecha_nacimiento, 1, 4)"),
]

BLOQUEOS_EM: list[Regla] = [
    ("documento",),
    ("fecha_nacimiento",),
    ("primer_apellido", "primer_nombre"),
]

REGLAS_DETERMINISTICAS: list[str] = [
    "l.documento = r.documento",
    "l.primer_nombre = r.primer_nombre and l.primer_apellido = r.primer_apellido "
    "and l.fecha_nacimiento = r.fecha_nacimiento",
]


def esquema(estandarizado: bool = True) -> Esquema:
    """Esquema del hito 2, con o sin estandarización (mismo modelo y reglas)."""
    return Esquema(
        nombre="colombia_estandarizado" if estandarizado else "colombia_crudo",
        comparaciones=comparaciones,
        preparar=preparar_estandarizado if estandarizado else preparar_crudo,
        bloqueos_exactos=BLOQUEOS_EXACTOS,
        bloqueos_candidatos=BLOQUEOS_CANDIDATOS,
        bloqueos_em=BLOQUEOS_EM,
        reglas_deterministicas=REGLAS_DETERMINISTICAS,
    )
