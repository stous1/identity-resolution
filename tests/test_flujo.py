"""Prueba de integración del flujo completo sobre una muestra sintética (sin internet)."""

import json

import pandas as pd
import pytest
from faker import Faker

from identidades import modelo
from identidades.flujo import (
    aplicar_modelo,
    candidatos_bloqueo,
    comparar_bloqueos,
    ejecutar_hito1,
)


def _muestra_sintetica(n_personas: int = 60, semilla: int = 7) -> pd.DataFrame:
    """Personas falsas con 1 a 4 registros cada una y errores menores inyectados.

    Imita el formato de fake_1000 sin descargar nada.
    """
    fake = Faker("es_CO")
    Faker.seed(semilla)
    rng = fake.random
    filas = []
    for persona in range(n_personas):
        nombre, apellido = fake.first_name(), fake.last_name()
        dob = fake.date_of_birth(minimum_age=18, maximum_age=90).isoformat()
        ciudad, correo = fake.city(), fake.email()
        for _ in range(rng.randint(1, 4)):
            filas.append(
                {
                    "unique_id": len(filas),
                    "first_name": nombre if rng.random() > 0.15 else nombre[:-1],
                    "surname": apellido if rng.random() > 0.15 else None,
                    "dob": dob,
                    "city": ciudad if rng.random() > 0.2 else None,
                    "email": correo if rng.random() > 0.2 else None,
                    "cluster": persona,
                }
            )
    return pd.DataFrame(filas)


@pytest.mark.integracion
def test_flujo_completo_genera_salidas(tmp_path):
    df = _muestra_sintetica(n_personas=80)

    metricas = ejecutar_hito1(
        df, tmp_path, n_bootstrap=50, capturas=False, comparar=False, referencia=False
    )

    for nombre in [
        "modelo.json",
        "metricas.json",
        "seleccion_bloqueos.csv",
        "curva_umbral.csv",
        "curva_umbral_clusters.csv",
        "cascada.html",
        "cascada.png",
        "pesos.html",
        "parametros_mu.html",
        "parametros_mu.png",
        "curva_umbral.html",
        "curva_umbral.png",
        "curva_umbral_clusters.png",
        "costo_umbral.html",
        "costo_umbral.png",
        "comparison_viewer.html",
        "cluster_studio.html",
    ]:
        assert (tmp_path / nombre).stat().st_size > 0, nombre
    assert json.loads((tmp_path / "metricas.json").read_text(encoding="utf-8")) == metricas

    # Partición por persona: desarrollo y prueba suman el total.
    particion = metricas["particion"]
    assert particion["desarrollo"]["registros"] + particion["prueba"]["registros"] == len(df)
    assert particion["desarrollo"]["personas"] == 48  # 60 % de 80

    # El umbral se elige en desarrollo: el de menor costo por clúster.
    umbrales = {u["criterio"]: u for u in metricas["desarrollo"]["umbrales"]}
    assert set(umbrales) == {"fijo", "max_f1_par", "min_costo_par", "min_costo_cluster"}
    assert metricas["umbral"]["criterio"] == "min_costo_cluster"
    assert metricas["umbral"]["valor"] == umbrales["min_costo_cluster"]["umbral"]
    costo_elegido = umbrales["min_costo_cluster"]["costo_clusters"]
    assert all(costo_elegido <= u["costo_clusters"] for u in umbrales.values())

    # Prueba se mide con ese umbral, con intervalos que contienen el valor observado.
    prueba = metricas["prueba"]
    assert prueba["clusters"]["umbral"] == metricas["umbral"]["valor"]
    for nivel in ("pares", "clusters"):
        for metrica, ic in prueba["intervalos"][nivel].items():
            assert ic["valor"] == pytest.approx(prueba[nivel][metrica]), (nivel, metrica)
            assert 0 <= ic["ic_inf"] <= ic["ic_sup"] <= 1
    assert "referencia_todo_el_dataset" not in metricas


@pytest.mark.integracion
def test_comparar_bloqueos_mide_cada_candidato():
    df = _muestra_sintetica(n_personas=40)
    candidatos = {
        "solo dob": [("dob",)],
        "dob + email": [("dob",), ("email",)],
    }

    tabla = comparar_bloqueos(df, candidatos, umbral=0.9)

    assert tabla["candidato"].tolist() == list(candidatos)
    assert tabla["reglas"].tolist() == [1, 2]
    # Agregar reglas nunca reduce los pares comparados ni el recall del bloqueo.
    assert tabla["pares_comparados"].is_monotonic_increasing
    assert tabla["recall_bloqueo"].is_monotonic_increasing
    for columna in ("recall_bloqueo", "precision_par", "recall_cluster"):
        assert tabla[columna].between(0, 1).all()


def test_candidatos_incluyen_seleccion_y_referencia():
    seleccion = modelo.BLOQUEOS_EXACTOS + [("surname_soundex",)]
    candidatos = candidatos_bloqueo(seleccion)

    assert candidatos["exactas"] == modelo.BLOQUEOS_EXACTOS
    assert candidatos["selección"] == seleccion
    assert candidatos["todas"] == modelo.BLOQUEOS_EXACTOS + modelo.BLOQUEOS_CANDIDATOS
    assert len(candidatos) == len(modelo.BLOQUEOS_CANDIDATOS) + 3


def test_aplicar_modelo_reestima_lambda_sin_etiquetas():
    desarrollo, prueba = _muestra_sintetica(n_personas=40), _muestra_sintetica(20, semilla=3)
    linker = modelo.crear_linker(desarrollo)
    modelo.entrenar(linker)

    aplicado = aplicar_modelo(linker, prueba.drop(columns="cluster"))

    original = linker.misc.save_model_to_json()
    nuevo = aplicado.misc.save_model_to_json()
    # Mismos niveles con los mismos m y u de desarrollo (solo cambia la descripción).
    niveles = [[c["comparison_levels"] for c in m["comparisons"]] for m in (original, nuevo)]
    assert niveles[0] == niveles[1]
    lam = "probability_two_random_records_match"
    assert nuevo[lam] != original[lam]


def test_reglas_candidatas_son_sql_valido():
    # Todas las reglas que compara comparar_bloqueos deben poder ejecutarse.
    df = _muestra_sintetica(n_personas=5)
    for regla in candidatos_bloqueo(modelo.BLOQUEOS_EXACTOS)["todas"]:
        linker = modelo.crear_linker(df, modelo.crear_settings([regla]))
        assert linker.inference.predict().as_pandas_dataframe() is not None, regla
