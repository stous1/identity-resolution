"""Pruebas del hito 2b: congelamiento del modelo v2 y cálculo de brechas."""

import subprocess

from identidades import flujo_hito2b, rutas

ARCHIVOS_V2 = [
    "src/identidades/estandarizacion_v2.py",
    "src/identidades/modelo_co_v2.py",
    "docs/resultados/hito2b/modelo.json",
    "docs/resultados/hito2b/desarrollo.json",
]


def test_modelo_v2_no_cambio_desde_su_tag():
    # Si falla, el modelo v2 cambió después de congelarlo: la prueba ciega 2 dejaría de
    # medir el modelo congelado. Crear un tag nuevo y repetir la prueba ciega.
    cambios = subprocess.run(
        ["git", "diff", "--quiet", flujo_hito2b.TAG_CONGELADO, "--", *ARCHIVOS_V2],
        cwd=rutas.RAIZ,
    ).returncode
    assert cambios == 0


def test_cargar_congelado_v2():
    configuracion, umbral = flujo_hito2b.cargar_congelado_v2()

    assert configuracion["link_type"] == "dedupe_only"
    assert 0.5 < umbral < 1


def test_datos_desarrollo_no_mezcla_personas():
    desarrollo, prueba = flujo_hito2b.datos_desarrollo()

    assert desarrollo["unique_id"].is_unique
    assert set(desarrollo["cluster"]).isdisjoint(prueba["cluster"])
    assert (desarrollo["cluster"] >= flujo_hito2b.DESPLAZAMIENTO_CIEGA_1).sum() > 0


def test_brecha_resume_grupos_y_diferencia():
    ic = {"valor": 0.5, "ic_inf": 0.4, "ic_sup": 0.6}
    grupo = {"personas": 10, "recall": ic, "pct_clusters_exactos": ic, "precision": ic}
    equidad = {
        "con_apodo": {
            "clusters": {
                "grupos": {"sin apodo": grupo, "con apodo": grupo},
                "diferencias": {
                    "sin apodo - con apodo": {
                        "pct_clusters_exactos": {**ic, "significativa": True},
                        "recall": {**ic, "significativa": False},
                    }
                },
            }
        }
    }

    b = flujo_hito2b.brecha(equidad, "con_apodo")

    assert b["diferencia"] == "sin apodo - con apodo"
    assert set(b["grupos"]) == {"sin apodo", "con apodo"}
    assert b["pct_clusters_exactos"]["significativa"]
