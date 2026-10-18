"""Prueba de integración del flujo completo sobre una muestra sintética (sin internet)."""

import json

import pandas as pd
import pytest
from faker import Faker

from identidades.flujo import ejecutar_hito1


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

    metricas = ejecutar_hito1(df, tmp_path, umbral=0.9, capturas=False)

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
        "comparison_viewer.html",
        "cluster_studio.html",
    ]:
        assert (tmp_path / nombre).stat().st_size > 0, nombre

    assert json.loads((tmp_path / "metricas.json").read_text(encoding="utf-8")) == metricas
    for seccion in ("pares", "pares_umbral_max_f1", "clusters"):
        for clave in ("precision", "recall", "f1"):
            assert 0 <= metricas[seccion][clave] <= 1
    assert 0 <= metricas["bloqueo"]["recall_bloqueo"] <= 1
    assert metricas["dataset"]["registros"] == len(df)
