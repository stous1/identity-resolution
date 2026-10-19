"""Fecha de hoy fija para Faker, para que los generadores no dependan del día en que se corren.

Faker calcula las fechas de nacimiento desde ``datetime.now()``. Con otra fecha cambian las
fechas, y con ellas parte del resto del sorteo (por ejemplo, qué registros llevan tilde),
así que el mismo escenario con la misma semilla salía distinto otro día.

- ``HOY_FIJO`` (15 de enero de 2026, la misma fecha que fijan las pruebas de la demo) es la
  fecha de ``sinteticos.generar`` y, con él, de todo lo que parte de sus personas: hito 2,
  pruebas ciegas 1 a 3, escenario del hito 3, tiempo real y escala (v1.1.1).
- ``HOY_V11`` (19 de octubre de 2026) es la fecha de los escenarios residenciales de la
  v1.1, que se fijó al escribirlos; no se cambia para no alterar el desarrollo del v4.
- ``forzar_fecha`` cambia la fecha de los generadores dentro de un bloque, para reproducir
  datos generados antes de fijarla (por ejemplo, el universo del hito 3 del 18 de octubre).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from unittest import mock

# Fecha de referencia de sinteticos.generar (la de HOY_FIJO en tests/test_demo.py).
HOY_FIJO: tuple[int, int, int] = (2026, 1, 15)
# Fecha de referencia de los escenarios de la v1.1.
HOY_V11: tuple[int, int, int] = (2026, 10, 19)

_forzada: tuple[int, int, int] | None = None


@contextmanager
def fecha_fija(anio: int, mes: int, dia: int) -> Iterator[None]:
    """Dentro del bloque, Faker cree que hoy es ``anio-mes-dia`` a mediodía."""
    hoy = datetime(anio, mes, dia, 12, 0, 0)

    class _Fijo(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return hoy if tz is None else hoy.replace(tzinfo=tz)

    with mock.patch("faker.providers.date_time.datetime", _Fijo):
        yield


@contextmanager
def fecha_generadores(por_defecto: tuple[int, int, int] = HOY_FIJO) -> Iterator[None]:
    """Fecha de un generador: ``por_defecto``, salvo que un bloque ``forzar_fecha`` la cambie."""
    with fecha_fija(*(_forzada or por_defecto)):
        yield


@contextmanager
def forzar_fecha(anio: int, mes: int, dia: int) -> Iterator[None]:
    """Dentro del bloque, los generadores usan esta fecha en lugar de la suya."""
    global _forzada
    anterior, _forzada = _forzada, (anio, mes, dia)
    try:
        yield
    finally:
        _forzada = anterior
