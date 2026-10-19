"""La demo en JavaScript da los mismos niveles y el mismo peso que Splink (v2 y v3)."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

from identidades import demo, errores_ciegos, errores_ciegos_2, sinteticos

RAIZ = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
TOLERANCIA = 1e-9
# Faker calcula las fechas de nacimiento desde datetime.now(): sin fijar el día, la muestra
# cambia de un día a otro aunque la semilla sea la misma.
HOY_FIJO = datetime(2026, 1, 15, 12, 0, 0)


class _DatetimeFijo(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ANN001, ANN206
        return HOY_FIJO if tz is None else HOY_FIJO.replace(tzinfo=tz)


def _pares(registros: pd.DataFrame, n_mismos: int, n_azar: int, rng: random.Random) -> list:
    filas = registros.astype(object).where(registros.notna(), None).to_dict("records")
    por_persona: dict = {}
    for f in filas:
        por_persona.setdefault(f["cluster"], []).append(f)
    mismos = [(g[i], g[j]) for g in por_persona.values() for i in range(len(g)) for j in range(i)]
    pares = rng.sample(mismos, min(n_mismos, len(mismos)))
    pares += [tuple(rng.sample(filas, 2)) for _ in range(n_azar)]
    return [
        [{c: (None if r[c] is None else str(r[c])) for c in demo.CAMPOS_CRUDOS} for r in par]
        for par in pares
    ]


def muestra_de_pares(semilla: int = 11) -> list:
    """~630 pares: de la misma persona y al azar, de los tres generadores sintéticos.

    Determinista: semilla fija y fecha de hoy fija (HOY_FIJO) para Faker.
    """
    rng = random.Random(semilla)
    with mock.patch("faker.providers.date_time.datetime", _DatetimeFijo):
        normales, personas = sinteticos.generar(150, semilla)
        ciegos_1, _ = errores_ciegos.capturar(personas, semilla=semilla)
        _, personas_2 = sinteticos.generar(150, semilla + 1)
        ciegos_2, _ = errores_ciegos_2.capturar(personas_2, semilla=semilla + 1)
    pares = []
    for registros in (normales, ciegos_1, ciegos_2):
        pares += _pares(registros, 150, 60, rng)
    return pares


def test_muestra_de_pares_no_depende_de_la_fecha() -> None:
    """Con el reloj de Faker cinco años después, la muestra sale idéntica."""

    class _OtroDia(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return datetime(2031, 7, 3, 8, 0, 0, tzinfo=tz)

    referencia = muestra_de_pares()
    with mock.patch("faker.providers.date_time.datetime", _OtroDia):
        en_otro_dia = muestra_de_pares()
    assert en_otro_dia == referencia


@pytest.mark.parametrize("version", ["v2", "v3"])
def test_exportacion_coincide_con_modelo_congelado(tmp_path: Path, version: str) -> None:
    ruta = tmp_path / "modelo.json"
    demo.exportar_modelo(ruta, version)
    assert json.loads(ruta.read_text(encoding="utf-8")) == json.loads(
        demo.RUTAS[version].read_text(encoding="utf-8")
    )


def test_modelo_v3_lleva_las_bandas_congeladas() -> None:
    modelo = json.loads(demo.RUTA_MODELO_V3.read_text(encoding="utf-8"))
    niveles = {c["columna"]: len(c["niveles"]) for c in modelo["comparaciones"]}

    assert modelo["bandas"]["peso_desde_revisar"] < modelo["bandas"]["peso_desde_aceptar"]
    assert niveles["apellido_casada"] == 4  # el v3 agrega Jaro-Winkler >= 0,88


@pytest.mark.integracion
@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
@pytest.mark.parametrize("version", ["v2", "v3"])
def test_demo_igual_a_splink(tmp_path: Path, version: str) -> None:
    pares = muestra_de_pares()
    ruta_pares = tmp_path / "pares.json"
    ruta_pares.write_text(json.dumps(pares, ensure_ascii=False), encoding="utf-8")
    salida = subprocess.run(
        [
            NODE,
            str(RAIZ / "tests" / "js" / "puntuar_demo.mjs"),
            str(demo.RUTAS[version]),
            str(ruta_pares),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    js = json.loads(salida.stdout)
    referencia = demo.Referencia(version)
    diferencias = []
    for par, resultado in zip(pares, js, strict=True):
        esperado = referencia.puntuar(*par)
        if (
            esperado["gammas"] != resultado["gammas"]
            or abs(esperado["peso"] - resultado["peso"]) > TOLERANCIA
        ):
            diferencias.append((par, esperado, resultado))
    assert len(pares) >= 600
    assert not diferencias, f"{len(diferencias)} de {len(pares)} pares difieren: {diferencias[:3]}"


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_jaro_winkler_del_motor_igual_a_duckdb() -> None:
    """Incluye transposiciones impares: DuckDB las cuenta con división entera."""
    import duckdb

    pares = [
        ("MACRELA", "GRACIELA"),
        ("MARTHA", "MARHTA"),
        ("DWAYNE", "DUANE"),
        ("JOSE LUIS", "LUIS JOSE"),
        ("ABCDEF", "BADCFE"),
        ("RAMIREZ", "RAMRIEZ"),
        ("", "A"),
    ]
    codigo = (
        f"import('{(RAIZ / 'docs' / 'demo' / 'motor.js').as_uri()}').then(m => "
        f"console.log(JSON.stringify({json.dumps(pares)}.map(([a, b]) => m.jaroWinkler(a, b)))))"
    )
    js = json.loads(
        subprocess.run([NODE, "-e", codigo], capture_output=True, text=True, check=True).stdout
    )
    for (a, b), valor in zip(pares, js, strict=True):
        esperado = duckdb.sql("select jaro_winkler_similarity(?, ?)", params=[a, b]).fetchone()[0]
        assert valor == pytest.approx(esperado, abs=1e-12), (a, b)
