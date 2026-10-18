"""Prueba de integración del flujo completo sobre una muestra sintética (sin internet)."""

import json

import pandas as pd
import pytest
from faker import Faker

from identidades import modelo
from identidades.flujo import candidatos_bloqueo, comparar_bloqueos, ejecutar_hito1


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
    df = _muestra_sintetica()

    metricas = ejecutar_hito1(df, tmp_path, capturas=False, comparar=False)

    for nombre in [
        "modelo.json",
        "metricas.json",
        "curva_umbral.csv",
        "cascada.html",
        "cascada.png",
        "pesos.html",
        "parametros_mu.html",
        "parametros_mu.png",
        "curva_umbral.html",
        "curva_umbral.png",
        "curva_umbral_clusters.csv",
        "curva_umbral_clusters.png",
        "costo_umbral.html",
        "costo_umbral.png",
        "comparison_viewer.html",
        "cluster_studio.html",
    ]:
        assert (tmp_path / nombre).stat().st_size > 0, nombre

    assert json.loads((tmp_path / "metricas.json").read_text(encoding="utf-8")) == metricas
    for seccion in ("pares", "clusters"):
        for clave in ("precision", "recall", "f1"):
            assert 0 <= metricas[seccion][clave] <= 1

    # Sin umbral explícito se usa el de menor costo por clúster.
    umbrales = {u["criterio"]: u for u in metricas["umbrales"]}
    assert set(umbrales) == {"fijo", "max_f1_par", "min_costo_par", "min_costo_cluster"}
    assert metricas["umbral"]["criterio"] == "min_costo_cluster"
    assert metricas["umbral"]["valor"] == umbrales["min_costo_cluster"]["umbral"]
    assert metricas["clusters"]["umbral"] == metricas["umbral"]["valor"]
    costo_elegido = umbrales["min_costo_cluster"]["costo_clusters"]
    assert all(costo_elegido <= u["costo_clusters"] for u in umbrales.values())
    assert 0 <= metricas["bloqueo"]["recall_bloqueo"] <= 1
    assert metricas["dataset"]["registros"] == len(df)


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
    candidatos = candidatos_bloqueo()

    assert candidatos["exactas"] == modelo.BLOQUEOS_EXACTOS
    assert candidatos["selección"] == modelo.BLOQUEOS_PREDICCION
    assert len(candidatos["todas"]) > len(candidatos["selección"])


def test_reglas_candidatas_son_sql_valido():
    # Todas las reglas que compara comparar_bloqueos deben poder ejecutarse.
    df = _muestra_sintetica(n_personas=5)
    for regla in candidatos_bloqueo()["todas"]:
        linker = modelo.crear_linker(df, modelo.crear_settings([regla]))
        assert linker.inference.predict().as_pandas_dataframe() is not None, regla
