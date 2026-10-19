"""Fecha de hoy fija para Faker, para que los escenarios no dependan del día en que se corren.

Faker calcula las fechas de nacimiento desde ``datetime.now()``. Con otra fecha cambian las
fechas, y con ellas parte del resto del sorteo (por ejemplo, qué registros llevan tilde),
así que el mismo escenario con la misma semilla sale distinto otro día. Los generadores de
la v1.1 corren dentro de ``fecha_fija`` y son deterministas; los de versiones anteriores no
se tocan.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from unittest import mock

# Fecha de referencia de los escenarios de la v1.1.
HOY_V11: tuple[int, int, int] = (2026, 10, 19)


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
