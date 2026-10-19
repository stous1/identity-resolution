"""Cada generador produce lo mismo aunque el reloj marque otro año (v1.1.1).

Faker calcula las fechas de nacimiento desde la fecha de hoy. Antes de la v1.1.1, el mismo
escenario con la misma semilla salía distinto otro día. Estas pruebas mueven el reloj que
ve Faker a otros años y exigen exactamente los mismos datos.
"""

from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from unittest import mock

import pandas as pd
import pytest

from identidades import (
    errores_ciegos,
    errores_ciegos_2,
    errores_ciegos_3,
    errores_ciegos_4,
    escenario_hito3,
    escenario_residencial,
    sinteticos,
)


@contextmanager
def reloj(anio: int):
    """Faker cree que hoy es el 1 de junio de ``anio`` (salvo que el generador lo fije)."""

    class _Otro(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            hoy = datetime(anio, 6, 1, 9, 30)
            return hoy if tz is None else hoy.replace(tzinfo=tz)

    with mock.patch("faker.providers.date_time.datetime", _Otro):
        yield


def _personas(semilla: int) -> pd.DataFrame:
    return sinteticos.generar(120, semilla)[1]


GENERADORES: dict[str, Callable[[], tuple]] = {
    "sinteticos.generar": lambda: sinteticos.generar(120, 42),
    "sinteticos.agregar_historia": lambda: sinteticos.agregar_historia(
        *sinteticos.generar(120, 42), 42
    ),
    "escenario_hito3": lambda: escenario_hito3.generar_escenario(150, 3131),
    "errores_ciegos (1)": lambda: errores_ciegos.capturar(_personas(2024), semilla=2024),
    "errores_ciegos_2": lambda: errores_ciegos_2.capturar(_personas(7777), semilla=7777),
    "errores_ciegos_3": lambda: errores_ciegos_3.capturar(_personas(9191), semilla=9191),
    "errores_ciegos_4": lambda: errores_ciegos_4.generar(150, 4444),
    "escenario_residencial": lambda: escenario_residencial.generar_escenario_residencial(150, 4141),
}


def _iguales(a: tuple, b: tuple) -> None:
    for x, y in zip(a, b, strict=True):
        if isinstance(x, pd.DataFrame):
            pd.testing.assert_frame_equal(x, y)
        else:
            assert x == y


@pytest.mark.parametrize("nombre", list(GENERADORES))
def test_mismo_resultado_con_el_reloj_en_otro_anio(nombre):
    generar = GENERADORES[nombre]
    with reloj(2026):
        base = generar()
    for anio in (2031, 2040):
        with reloj(anio):
            _iguales(base, generar())


def test_forzar_fecha_reproduce_datos_anteriores():
    """``forzar_fecha`` cambia la fecha de los generadores (para datos de antes de fijarla)."""
    from identidades.sinteticos_fecha import forzar_fecha

    normal = sinteticos.generar(80, 3)[1]["fecha_nacimiento"]
    with forzar_fecha(2030, 1, 1):
        forzada = sinteticos.generar(80, 3)[1]["fecha_nacimiento"]
    assert not normal.equals(forzada)
    assert normal.equals(sinteticos.generar(80, 3)[1]["fecha_nacimiento"])
