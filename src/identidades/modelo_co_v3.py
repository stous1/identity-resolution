"""Esquema Splink v3 para clientes colombianos (hito 6, correcciones post-auditoría).

Reutiliza sin cambios la estandarización y la preparación del v2 (mismas columnas, así
que el vinculador de tiempo real y el hito 3 funcionan igual). Cambia dos cosas:

- **Ningún campo puede vetar por sí solo.** Después de entrenar se pone un piso a las
  probabilidades m (``modelo.aplicar_piso_m``): ningún nivel resta más de
  ``max_bits_en_contra`` bits. El valor se elige en desarrollo. La auditoría encontró
  vetos de −48 bits (municipio, v1), −43 (dirección, v1) y −72,6 (apellido de casada, v2).
- **Apellido de casada** con un nivel intermedio (Jaro-Winkler >= 0,88, error de
  digitación) además de igual y distinto. Que cambie (divorcio, nuevo matrimonio) ahora
  está en los datos de entrenamiento, y el piso limita lo que resta.

El entrenamiento usa datos con mudanzas y apellidos de casada reales
(``sinteticos.agregar_historia``): su ausencia en el generador del hito 2 causó los vetos.
"""

from __future__ import annotations

import splink.comparison_level_library as cll
import splink.comparison_library as cl
from splink.internals.comparison_creator import ComparisonCreator

from identidades import modelo_co, modelo_co_v2
from identidades.modelo import Esquema

# Candidatos para el piso, en bits en contra como máximo por nivel. Se elige en desarrollo.
CANDIDATOS_MAX_BITS: tuple[float, ...] = (5.0, 7.5, 10.0, 12.5, 15.0, 20.0)


def comparacion_apellido_casada() -> ComparisonCreator:
    """Apellido de casada: igual, casi igual (digitación) o distinto; nulo si falta en uno."""
    return cl.CustomComparison(
        output_column_name="apellido_casada",
        comparison_levels=[
            cll.NullLevel("apellido_casada"),
            cll.ExactMatchLevel("apellido_casada"),
            cll.JaroWinklerLevel("apellido_casada", 0.88),
            cll.ElseLevel(),
        ],
        comparison_description="Apellido de casada",
    )


def comparaciones() -> list[ComparisonCreator]:
    return [
        modelo_co_v2.comparacion_documento(),
        modelo_co_v2.comparacion_nombres(),
        modelo_co_v2.comparacion_primer_apellido(),
        cl.JaroWinklerAtThresholds("segundo_apellido", [0.90]),
        comparacion_apellido_casada(),
        cl.DateOfBirthComparison("fecha_nacimiento", input_is_string=True),
        modelo_co_v2.comparacion_telefonos(),
        cl.EmailComparison("email").configure(term_frequency_adjustments=True),
        modelo_co.comparacion_domicilio(),
        cl.ExactMatch("municipio").configure(term_frequency_adjustments=True),
    ]


ESQUEMA_V3 = Esquema(
    nombre="colombia_v3",
    comparaciones=comparaciones,
    preparar=modelo_co_v2.preparar,
    bloqueos_exactos=modelo_co_v2.BLOQUEOS_EXACTOS,
    bloqueos_candidatos=modelo_co_v2.BLOQUEOS_CANDIDATOS,
    bloqueos_em=modelo_co.BLOQUEOS_EM,
    reglas_deterministicas=modelo_co.REGLAS_DETERMINISTICAS,
)
