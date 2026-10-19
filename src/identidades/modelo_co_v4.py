"""Esquema Splink v4 para clientes colombianos (v1.1, realidad residencial).

Igual al v3 (``modelo_co_v3``, congelado) salvo la dirección. El v3 compara la dirección
como texto: el mismo apartamento escrito de dos formas ("Apto 502" y "Ap 502") resta 1,7
bits, dos vecinos del mismo edificio suman 5,4 y dos predios de la misma cuadra suman 8,8
("misma vía, número y placa" no incluye el consecutivo). El v4 separa la dirección en
predio y unidad (``estandarizacion_v4``) y la compara por niveles:

1. misma dirección: mismo predio y misma unidad (o ninguno de los dos con unidad);
2. mismo predio, unidad desconocida o incompleta en uno de los dos ("Torre 2 Apto 301"
   contra "Apto 301", o contra la dirección sin unidad);
3. mismo predio, otra unidad (vecinos);
4. predio parecido (error de digitación);
5. distinta.

Los niveles 1 y 2 se ajustan por frecuencia (``term_frequency_adjustments``): en un
conjunto donde viven muchos clientes, compartir el predio dice menos que en una casa. El
piso a las m del v3 (``modelo.aplicar_piso_m``) se vuelve a elegir en desarrollo.
"""

from __future__ import annotations

import pandas as pd
import splink.comparison_level_library as cll
import splink.comparison_library as cl
from splink.internals.comparison_creator import ComparisonCreator

from identidades import estandarizacion_v2 as est_v2
from identidades import modelo_co, modelo_co_v2, modelo_co_v3
from identidades.estandarizacion_v4 import normalizar_direccion_v4
from identidades.modelo import Esquema, Regla

CANDIDATOS_MAX_BITS: tuple[float, ...] = modelo_co_v3.CANDIDATOS_MAX_BITS


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas del v3 con la dirección en predio y unidad.

    ``domicilio`` pasa a ser predio y unidad canónicos ("KR 7 # 40-62 AP502"); si no se
    reconoce la nomenclatura (dirección rural), el texto limpio. ``domicilio_clave`` pasa
    a ser el predio (antes era la cuadra), y se agregan ``predio``, ``unidad`` y
    ``unidad_partes``.
    """
    modelo = modelo_co_v2.preparar(df)
    direcciones = pd.DataFrame(
        df["direccion"].map(est_v2.reparar_codificacion).map(normalizar_direccion_v4).tolist(),
        index=df.index,
    )
    modelo = modelo.assign(
        domicilio=direcciones["direccion"].astype("string"),
        domicilio_clave=direcciones["predio"].astype("string"),
        predio=direcciones["predio"].astype("string"),
        unidad=direcciones["unidad"].astype("string"),
        unidad_partes=direcciones["unidad_partes"],
    )
    return modelo


def _par(columna: str) -> tuple[str, str]:
    return f'"{columna}_l"', f'"{columna}_r"'


def comparacion_domicilio_v4() -> ComparisonCreator:
    """Dirección por niveles de predio y unidad, con ajuste por frecuencia."""
    pl, pr = _par("predio")
    ul, ur = _par("unidad")
    upl, upr = _par("unidad_partes")
    dl, dr = _par("domicilio")
    return cl.CustomComparison(
        output_column_name="domicilio",
        comparison_levels=[
            cll.NullLevel("domicilio"),
            cll.ExactMatchLevel("domicilio").configure(
                tf_adjustment_column="domicilio",
                label_for_charts="Misma dirección (predio y unidad)",
            ),
            cll.CustomLevel(
                f"{pl} = {pr} and ({ul} is null or {ur} is null "
                f"or list_has_all({upl}, {upr}) or list_has_all({upr}, {upl}))",
                label_for_charts="Mismo predio, unidad desconocida o incompleta",
            ).configure(tf_adjustment_column="predio"),
            cll.CustomLevel(f"{pl} = {pr}", label_for_charts="Mismo predio, otra unidad"),
            cll.CustomLevel(
                f"jaro_winkler_similarity(coalesce({pl}, {dl}), coalesce({pr}, {dr})) >= 0.92",
                label_for_charts="Predio parecido (digitación)",
            ),
            cll.ElseLevel(),
        ],
        comparison_description="Dirección (predio y unidad)",
    )


def comparaciones() -> list[ComparisonCreator]:
    return [
        modelo_co_v2.comparacion_documento(),
        modelo_co_v2.comparacion_nombres(),
        modelo_co_v2.comparacion_primer_apellido(),
        cl.JaroWinklerAtThresholds("segundo_apellido", [0.90]),
        modelo_co_v3.comparacion_apellido_casada(),
        cl.DateOfBirthComparison("fecha_nacimiento", input_is_string=True),
        modelo_co_v2.comparacion_telefonos(),
        cl.EmailComparison("email").configure(term_frequency_adjustments=True),
        comparacion_domicilio_v4(),
        cl.ExactMatch("municipio").configure(term_frequency_adjustments=True),
    ]


# Mismos bloqueos que el v3; "domicilio_clave" ahora es el predio, no la cuadra.
BLOQUEOS_CANDIDATOS: list[Regla] = modelo_co_v2.BLOQUEOS_CANDIDATOS

ESQUEMA_V4 = Esquema(
    nombre="colombia_v4",
    comparaciones=comparaciones,
    preparar=preparar,
    bloqueos_exactos=modelo_co_v2.BLOQUEOS_EXACTOS,
    bloqueos_candidatos=BLOQUEOS_CANDIDATOS,
    bloqueos_em=modelo_co.BLOQUEOS_EM,
    reglas_deterministicas=modelo_co.REGLAS_DETERMINISTICAS,
)
