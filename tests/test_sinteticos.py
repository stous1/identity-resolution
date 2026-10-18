"""Pruebas del generador de clientes sintéticos colombianos."""

import re
from dataclasses import fields

import pandas as pd
import pytest

from identidades import sinteticos

SIN_ERRORES = sinteticos.TasasError(**{f.name: 0.0 for f in fields(sinteticos.TasasError)})


@pytest.fixture(scope="module")
def muestra():
    return sinteticos.generar(n_personas=300, semilla=5)


def test_es_reproducible_con_la_semilla():
    a, pa = sinteticos.generar(n_personas=50, semilla=9)
    b, pb = sinteticos.generar(n_personas=50, semilla=9)

    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(pa, pb)


def test_cada_persona_tiene_al_menos_un_registro(muestra):
    registros, personas = muestra

    assert registros["unique_id"].is_unique
    assert set(registros["cluster"]) == set(personas["cluster"])
    assert registros.groupby("cluster").size().max() <= 6
    assert (registros.groupby("cluster").size() > 1).mean() > 0.4  # hay duplicados


def test_datos_verdaderos_con_formato_colombiano(muestra):
    _, personas = muestra

    assert personas["tipo_documento"].isin(["CC", "CE"]).all()
    assert personas["numero_documento"].str.fullmatch(r"\d{6,10}").all()
    assert personas["celular"].str.fullmatch(r"3\d{9}").all()
    assert personas["correo"].str.fullmatch(r"[a-z0-9.]+@[a-z.]+").all()
    # Algunas personas con nombre compuesto y algunas con un solo apellido.
    assert 0.2 < personas["nombre_compuesto"].mean() < 0.6
    assert 0.7 < personas["dos_apellidos"].mean() < 0.95


def test_ciudad_y_departamento_son_coherentes():
    gen = sinteticos.Generador(semilla=3)
    for _ in range(50):
        ciudad, departamento = gen._ciudad()
        codigos = [c for c, n in gen._municipios.items() if n == ciudad]
        assert any(gen._departamentos[c[:2]] == departamento for c in codigos)


def test_sin_errores_cada_registro_copia_la_verdad():
    registros, personas = sinteticos.generar(n_personas=40, semilla=2, tasas=SIN_ERRORES)
    unidos = registros.merge(personas, on="cluster", suffixes=("", "_verdad"))

    assert (unidos["numero_documento"] == unidos["numero_documento_verdad"]).all()
    assert (unidos["celular"] == unidos["celular_verdad"]).all()
    assert (unidos["correo"] == unidos["correo_verdad"]).all()
    nombres = unidos["primer_nombre"] + unidos["segundo_nombre"].fillna("").map(
        lambda s: f" {s}" if s else ""
    )
    assert (unidos["nombres"] == nombres).all()
    # Dirección canónica: "Calle 45 # 10-20" o "Calle 10 Sur # 43A-15".
    assert unidos["direccion"].str.fullmatch(r"[A-Za-z]+ \w+( BIS)?( Sur| Este)? # \w+-\d+").all()


def test_relleno_compartido_por_personas_distintas(muestra):
    registros, _ = muestra

    for columna, valores in [
        ("celular", sinteticos.TELEFONOS_RELLENO),
        ("correo", sinteticos.CORREOS_RELLENO),
        ("direccion", sinteticos.DIRECCIONES_RELLENO),
    ]:
        con_relleno = registros[registros[columna].isin(valores)]
        assert con_relleno["cluster"].nunique() > 3, columna


def test_errores_de_documento():
    gen = sinteticos.Generador(
        semilla=1, tasas=sinteticos.TasasError(documento_transpuesto=1.0, documento_con_puntos=0)
    )
    capturado = gen._documento_capturado("1234567890")
    assert sorted(capturado) == sorted("1234567890") and capturado != "1234567890"

    gen = sinteticos.Generador(
        semilla=1, tasas=sinteticos.TasasError(documento_transpuesto=0, documento_con_puntos=1.0)
    )
    capturado = gen._documento_capturado("1234567890")
    assert re.fullmatch(r"1[., ]234[., ]567[., ]890", capturado)


def test_cambiar_tildes():
    gen = sinteticos.Generador(semilla=1)

    assert gen._cambiar_tildes("Gómez Peña") == "Gomez Pena"
    assert sinteticos.tiene_tilde("Muñoz") and not sinteticos.tiene_tilde("Munoz")


def test_digitacion_cambia_una_sola_posicion_aproximadamente():
    gen = sinteticos.Generador(semilla=4)
    for _ in range(30):
        resultado = gen._digitacion("Rodriguez")
        assert resultado != "" and abs(len(resultado) - len("Rodriguez")) <= 1


def test_familiares_comparten_apellido_y_direccion():
    _, personas = sinteticos.generar(n_personas=400, semilla=6)
    familiares = personas[personas["familiar_de"].notna()]
    base = personas.set_index("cluster").loc[familiares["familiar_de"].astype(int)]

    assert 0.15 < len(familiares) / len(personas) < 0.35
    assert (familiares["primer_apellido"].to_numpy() == base["primer_apellido"].to_numpy()).all()
    assert (familiares["direccion_placa"].to_numpy() == base["direccion_placa"].to_numpy()).all()
    # Pero son otras personas: otro documento.
    assert (familiares["numero_documento"].to_numpy() != base["numero_documento"].to_numpy()).all()


def test_fecha_errada_sigue_siendo_una_fecha_valida():
    gen = sinteticos.Generador(semilla=8, tasas=sinteticos.TasasError(fecha_errada=1.0))
    for _ in range(50):
        fecha = gen._fecha_capturada("1985-03-07")
        assert sinteticos._fecha_valida(fecha)
