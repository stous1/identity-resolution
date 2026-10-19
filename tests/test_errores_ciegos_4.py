"""Pruebas del generador de la prueba ciega 4."""

from __future__ import annotations

import re

import pandas as pd
import pytest

from identidades.errores_ciegos_4 import (
    CANALES,
    COLUMNAS_PERSONAS,
    COLUMNAS_REGISTROS,
    COLUMNAS_SOSPECHOSOS,
    generar,
)

ROLES = {"pareja", "hijo", "jefe", "hermano", "conviviente", "solo", "otro"}
TIPOS_HOGAR = {
    "solo",
    "pareja",
    "familia",
    "monoparental",
    "hermanos",
    "convivientes",
    "sucesivo",
    "otro",
}
TIPOS_PREDIO = {"casa", "casa_pisos", "edificio", "conjunto"}
COLUMNA_POR_TIPO = {
    "celular": "celular",
    "correo": "correo",
    "direccion": "direccion",
    "documento": "numero_documento",
}


@pytest.fixture(scope="module")
def completo() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return generar()


@pytest.fixture(scope="module")
def pequeno() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return generar(n_personas=300, semilla=7)


def test_determinista() -> None:
    a = generar(n_personas=300, semilla=7)
    b = generar(n_personas=300, semilla=7)
    for x, y in zip(a, b, strict=True):
        pd.testing.assert_frame_equal(x, y)


def test_semillas_distintas_dan_datos_distintos(pequeno) -> None:
    otro = generar(n_personas=300, semilla=8)
    assert not pequeno[0]["nombres"].equals(otro[0]["nombres"])


def test_columnas_y_tipos(completo) -> None:
    registros, personas, sospechosos = completo
    assert list(registros.columns) == COLUMNAS_REGISTROS
    assert list(personas.columns) == COLUMNAS_PERSONAS
    assert list(sospechosos.columns) == COLUMNAS_SOSPECHOSOS
    assert registros["unique_id"].tolist() == list(range(len(registros)))
    assert registros["cluster"].dtype == "int64"
    assert registros["validado"].dtype == bool
    texto = [c for c in COLUMNAS_REGISTROS if c not in ("unique_id", "cluster", "validado")]
    for col in texto:
        assert registros[col].map(lambda v: v is None or isinstance(v, str)).all(), col
    for col in ("tipo_documento", "fecha_actualizacion", "canal", "origen"):
        assert registros[col].notna().all(), col
    assert personas["mujer"].dtype == bool
    assert personas["usa_apellido_casada"].dtype == bool
    assert personas["unidad"].map(lambda v: v is None or isinstance(v, str)).all()


def test_tamanos(completo) -> None:
    registros, personas, sospechosos = completo
    assert len(personas) == 2000
    assert 4000 <= len(registros) <= 6000
    assert len(sospechosos) > 0


def test_vocabularios(completo) -> None:
    registros, personas, _ = completo
    assert set(registros["canal"]) <= set(CANALES)
    assert set(personas["rol"]) <= ROLES
    assert set(personas["tipo_hogar"]) <= TIPOS_HOGAR
    assert set(personas["tipo_predio"]) == TIPOS_PREDIO
    fechas = registros["fecha_actualizacion"]
    assert fechas.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
    assert fechas.min() >= "2010-01-01" and fechas.max() <= "2025-12-31"
    assert "normal" in set(registros["origen"])
    assert len(set(registros["origen"])) > 2


def test_consistencia_de_la_verdad(completo) -> None:
    registros, personas, _ = completo
    assert personas["cluster"].is_unique
    assert set(registros["cluster"]) == set(personas["cluster"])
    # El mismo hogar vive en el mismo predio y la misma unidad.
    por_hogar = personas.fillna({"unidad": "-"}).groupby("hogar")
    assert (por_hogar["predio"].nunique() == 1).all()
    assert (por_hogar["unidad"].nunique() == 1).all()
    # Un hogar no mezcla familias salvo los convivientes.
    mezcla = personas.groupby("hogar")["familia"].nunique() > 1
    hogares_mezcla = set(mezcla[mezcla].index)
    tipos = set(personas.loc[personas["hogar"].isin(hogares_mezcla), "tipo_hogar"])
    assert tipos <= {"convivientes"}
    # Las casas no tienen unidad; los demás predios sí.
    casas = personas["tipo_predio"] == "casa"
    assert personas.loc[casas, "unidad"].isna().all()
    assert personas.loc[~casas, "unidad"].notna().all()
    # Cada predio tiene un único tipo.
    assert (personas.groupby("predio")["tipo_predio"].nunique() == 1).all()


def test_realidades_presentes(completo) -> None:
    _, personas, _ = completo
    # Edificios y conjuntos con varios hogares sin relación.
    multi = personas[personas["tipo_predio"].isin(["edificio", "conjunto"])]
    hogares = multi.groupby("predio")["hogar"].nunique()
    assert (hogares >= 3).sum() >= 20
    # Casas de varios pisos con más de un hogar de la misma familia.
    pisos = personas[personas["tipo_predio"] == "casa_pisos"].groupby("predio")
    assert ((pisos["hogar"].nunique() >= 2) & (pisos["familia"].nunique() == 1)).sum() >= 10
    assert (personas["tipo_hogar"] == "sucesivo").any()
    assert (personas["rol"] == "conviviente").any()


def test_apellido_de_casada(completo) -> None:
    registros, personas, _ = completo
    casadas = personas[personas["usa_apellido_casada"]]
    assert len(casadas) > 0
    assert casadas["mujer"].all()
    por_cluster = registros.groupby("cluster")["apellidos"].apply(
        lambda s: any(re.search(r"\bde\b", v, re.IGNORECASE) for v in s.dropna())
    )
    assert por_cluster.loc[casadas["cluster"]].all()


def test_sospechosos_aparecen_en_registros(completo) -> None:
    registros, personas, sospechosos = completo
    clusters = set(personas["cluster"])
    assert set(sospechosos["tipo"]) == set(COLUMNA_POR_TIPO)
    for fila in sospechosos.itertuples():
        columna = COLUMNA_POR_TIPO[fila.tipo]
        con_valor = registros[registros[columna] == fila.valor]
        assert len(con_valor) > 0, fila.valor
        assert isinstance(fila.personas, list) and len(fila.personas) >= 2
        assert set(fila.personas) <= clusters
        # Los registros con el valor exacto pertenecen a personas involucradas.
        assert set(con_valor["cluster"]) & set(fila.personas)
    marcados = registros[registros["origen"] != "normal"]
    involucrados = {c for lista in sospechosos["personas"] for c in lista}
    assert set(marcados["cluster"]) <= involucrados


def test_hay_errores_de_captura(completo) -> None:
    registros, _, _ = completo
    for col in ("numero_documento", "nombres", "fecha_nacimiento", "celular", "correo"):
        assert registros[col].isna().any(), col
    # Varios formatos de fecha de nacimiento y documentos con puntos.
    fechas = registros["fecha_nacimiento"].dropna()
    assert fechas.str.contains("/").any() and fechas.str.contains(r"^\d{4}-").any()
    assert registros["numero_documento"].dropna().str.contains(r"\.").any()
