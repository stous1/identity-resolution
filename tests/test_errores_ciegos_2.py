"""Pruebas del generador independiente de errores de la segunda prueba ciega."""

from dataclasses import fields

import pandas as pd
import pytest

from identidades import errores_ciegos_2 as ec2
from identidades import sinteticos


@pytest.fixture(scope="module")
def personas() -> pd.DataFrame:
    """Personas limpias del generador sintético (solo se usa su salida)."""
    _, tabla = sinteticos.generar(n_personas=600, semilla=314)
    return tabla


def _texto(valor) -> str | None:
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    return str(valor)


def test_reproducible(personas: pd.DataFrame) -> None:
    r1, c1 = ec2.capturar(personas, semilla=11)
    r2, c2 = ec2.capturar(personas, semilla=11)
    r3, _ = ec2.capturar(personas, semilla=12)
    pd.testing.assert_frame_equal(r1, r2)
    pd.testing.assert_frame_equal(c1, c2)
    assert not r1.equals(r3)


def test_columnas_e_ids(personas: pd.DataFrame) -> None:
    registros, condiciones = ec2.capturar(personas, semilla=3)
    assert list(registros.columns) == ec2.COLUMNAS
    assert registros["unique_id"].is_unique
    assert sorted(registros["unique_id"]) == list(range(len(registros)))
    assert set(registros["cluster"]) == set(personas["cluster"])
    assert set(condiciones["cluster"]) == set(personas["cluster"])
    assert len(condiciones) == len(personas)
    for col in ["apellido_casada", "con_apodo", "rural"]:
        assert condiciones[col].dtype == bool


def test_registros_por_persona(personas: pd.DataFrame) -> None:
    registros, _ = ec2.capturar(personas, semilla=5)
    conteo = registros.groupby("cluster").size()
    assert conteo.between(1, 6).all()
    assert 0.25 <= (conteo == 1).mean() <= 0.42


def test_faltantes_son_none(personas: pd.DataFrame) -> None:
    registros, _ = ec2.capturar(personas, semilla=5, tasas=ec2.TasasCiegas2.solo("campo_faltante"))
    valores = registros[["celular", "correo", "direccion", "fecha_nacimiento"]].to_numpy().ravel()
    assert any(v is None for v in valores)
    assert not any(isinstance(v, float) for v in valores)


def test_registros_siempre_ligables(personas: pd.DataFrame) -> None:
    registros, _ = ec2.capturar(personas, semilla=9)
    assert registros["nombres"].notna().all() and registros["apellidos"].notna().all()
    assert (registros["nombres"].str.len() > 0).all()
    assert registros["numero_documento"].notna().all()


@pytest.mark.parametrize("nombre", [f.name for f in fields(ec2.TasasCiegas2)])
def test_cada_error_aparece_con_tasa_uno(personas: pd.DataFrame, nombre: str) -> None:
    tasas = ec2.TasasCiegas2.solo(nombre, 1.0)
    registros, condiciones, traza = ec2.capturar_con_traza(personas, semilla=21, tasas=tasas)
    afectados = set(traza.loc[traza["error"] == nombre, "unique_id"])
    assert afectados, f"{nombre} no apareció"
    limpios, _ = ec2.capturar(personas, semilla=21, tasas=ec2.TasasCiegas2.ninguna())
    # Comparar por cluster: los registros afectados no coinciden con la versión limpia.
    limpio_por_cluster = limpios.drop_duplicates("cluster").set_index("cluster")
    columnas = ec2.COLUMNAS[1:-1]
    afectados_df = registros[registros["unique_id"].isin(afectados)]
    distintos = 0
    for _, fila in afectados_df.iterrows():
        base = limpio_por_cluster.loc[fila["cluster"], columnas]
        if [_texto(fila[c]) for c in columnas] != [_texto(base[c]) for c in columnas]:
            distintos += 1
    assert distintos == len(afectados_df)
    if nombre in ec2.CONDICIONES_PERSONA:
        assert condiciones[nombre].any()


def test_condiciones_obligatorias_se_manifiestan(personas: pd.DataFrame) -> None:
    tasas = ec2.TasasCiegas2(apellido_casada=1.0, con_apodo=1.0, rural=1.0)
    registros, condiciones, traza = ec2.capturar_con_traza(personas, semilla=4, tasas=tasas)
    por_uid = traza.groupby("unique_id")["error"].apply(set)
    errores_cluster: dict[int, set[str]] = {}
    for uid, cluster in zip(registros["unique_id"], registros["cluster"], strict=True):
        errores_cluster.setdefault(cluster, set()).update(por_uid.get(uid, set()))
    for _, c in condiciones.iterrows():
        assert c["con_apodo"] == ("con_apodo" in errores_cluster[c["cluster"]])
        assert c["apellido_casada"] == ("apellido_casada" in errores_cluster[c["cluster"]])
        if c["apellido_casada"]:
            assert c["mujer_aparente"]
    assert condiciones["rural"].all()
    assert condiciones["apellido_casada"].any() and condiciones["con_apodo"].all()
    rurales = (
        registros["direccion"]
        .dropna()
        .str.contains("vereda|vda|finca|fca|corregimiento|km|rural", case=False)
    )
    assert rurales.all()


def test_formas_concretas(personas: pd.DataFrame) -> None:
    def con(nombre: str) -> pd.DataFrame:
        r, _ = ec2.capturar(personas, semilla=8, tasas=ec2.TasasCiegas2.solo(nombre))
        return r

    assert con("apellido_casada")["apellidos"].str.contains(r"\b(?:de|De|D\.)\s").any()
    assert con("apellidos_guion")["apellidos"].str.contains("-").any()
    assert con("digito_verificacion")["numero_documento"].str.contains("-").any()
    assert con("correo_alias")["correo"].str.contains(r"\+", regex=True).all()
    assert con("correo_corporativo")["correo"].str.endswith(".com.co").all()
    assert con("anio_dos_digitos")["fecha_nacimiento"].str.len().le(8).all()
    assert (
        con("titulo")["nombres"]
        .str.match(r"^(Dr|Dra|Sr|Sra|Srta|Ing|Lic|Prof)\.|^(Don|Doña) ")
        .all()
    )
    assert not con("pegado_mayusculas")["nombres"].str.contains(" ").any()
    longitudes = con("celular_longitud")["celular"].str.len()
    assert set(longitudes) <= {9, 11}


def test_tasas_cero_registros_limpios(personas: pd.DataFrame) -> None:
    registros, condiciones = ec2.capturar(personas, semilla=2, tasas=ec2.TasasCiegas2.ninguna())
    assert not condiciones[["apellido_casada", "con_apodo", "rural"]].any().any()
    limpias = personas.set_index("cluster")
    for _, r in registros.iterrows():
        p = limpias.loc[r["cluster"]]
        nombres = " ".join(
            x for x in [_texto(p["primer_nombre"]), _texto(p["segundo_nombre"])] if x
        )
        apellidos = " ".join(
            x for x in [_texto(p["primer_apellido"]), _texto(p["segundo_apellido"])] if x
        )
        direccion = ec2.direccion_urbana(
            p["direccion_via"],
            p["direccion_numero_via"],
            _texto(p["direccion_cuadrante"]),
            p["direccion_placa"],
            p["direccion_consecutivo"],
        )
        assert r["tipo_documento"] == p["tipo_documento"]
        assert r["numero_documento"] == p["numero_documento"]
        assert r["nombres"] == nombres
        assert r["apellidos"] == apellidos
        assert r["fecha_nacimiento"] == p["fecha_nacimiento"]
        assert r["celular"] == p["celular"]
        assert r["correo"] == p["correo"]
        assert r["direccion"] == direccion
        assert r["ciudad"] == p["ciudad"]
        assert r["departamento"] == p["departamento"]


def test_digito_verificacion_conocido() -> None:
    # NIT de ejemplo con DV conocido: 900373115 -> 3 (cálculo módulo 11).
    assert ec2.digito_verificacion("900373115") == 3


def test_parece_mujer() -> None:
    assert ec2.parece_mujer("María") and ec2.parece_mujer("Luz") and ec2.parece_mujer("Inés")
    assert not ec2.parece_mujer("Andrés") and not ec2.parece_mujer("José")
