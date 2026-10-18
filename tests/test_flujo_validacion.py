"""Pruebas de la validación: modelo congelado, prueba ciega y FEBRL."""

import pandas as pd
import pytest

from identidades import errores_ciegos, flujo_validacion, sinteticos


def test_modelo_congelado_no_cambio_desde_el_tag():
    # Si esta prueba falla, la estandarización o el modelo cambiaron después de congelarlos:
    # la prueba ciega dejaría de medir el modelo congelado.
    resultado = flujo_validacion.verificar_congelado()

    assert resultado["sin_cambios"] and len(resultado["commit"]) == 40


def test_cargar_congelado_trae_modelo_y_umbral():
    configuracion, umbral = flujo_validacion.cargar_congelado()

    assert configuracion["link_type"] == "dedupe_only"
    assert 0.5 < umbral < 1


def test_grupos_de_personas_combina_atributos_y_condiciones():
    _, personas = sinteticos.generar(n_personas=30, semilla=1)
    _, condiciones = errores_ciegos.capturar(personas, semilla=1)

    grupos = flujo_validacion.grupos_de_personas(personas, condiciones)

    assert {"nombre_compuesto", "dos_apellidos", "con_tilde", "rural", "con_apodo"} <= set(grupos)
    assert "un_solo_registro" not in grupos and "documento_alterado" not in grupos
    diagnostico = flujo_validacion.grupos_de_personas(
        personas, condiciones, flujo_validacion.GRUPOS_DIAGNOSTICO
    )
    assert set(diagnostico) == set(flujo_validacion.GRUPOS_DIAGNOSTICO)
    assert set(grupos["rural"].unique()) <= {"dirección rural", "dirección urbana"}
    assert all(len(g) == 30 for g in grupos.values())


def test_tres_cifras_toma_las_metricas_por_cluster():
    ic = {"precision": {"valor": 1.0, "ic_inf": 1.0, "ic_sup": 1.0}}
    hito2 = {"variantes": {"estandarizado": {"prueba": {"intervalos": {"clusters": ic}}}}}
    otra = {"prueba": {"intervalos": {"clusters": ic}}}

    resumen = flujo_validacion.tres_cifras(hito2, otra, otra)

    assert list(resumen) == ["prueba normal (hito 2)", "prueba ciega", "FEBRL3"]


@pytest.mark.integracion
def test_prueba_ciega_en_pequeno(tmp_path):
    metricas = flujo_validacion.ejecutar_prueba_ciega(
        tmp_path, n_personas=120, n_bootstrap=30, capturas=False
    )

    assert metricas["datos"]["registros"] > 120
    for nivel in ("pares", "clusters"):
        for ic in metricas["prueba"]["intervalos"][nivel].values():
            assert 0 <= ic["ic_inf"] <= ic["ic_sup"] <= 1
    assert "rural" in metricas["equidad"]
    assert "documento_alterado" in metricas["diagnostico_por_error"]["detalle"]
    umbrales = metricas["diagnostico_otros_umbrales"]["clusters"]
    assert [u["umbral"] for u in umbrales] == flujo_validacion.UMBRALES_DIAGNOSTICO
    assert (tmp_path / "ciega_equidad.png").exists()


@pytest.mark.integracion
def test_febrl_en_pequeno(tmp_path):
    personas = range(60)
    filas = []
    for p in personas:
        for copia in range(2):
            filas.append(
                {
                    "unique_id": len(filas),
                    "rec_id": f"rec-{p}-{'org' if copia == 0 else 'dup-0'}",
                    "cluster": p,
                    "given_name": f"nombre{p % 17}",
                    "surname": f"apellido{p}",
                    "street_number": str(p),
                    "address_1": f"calle {p}",
                    "address_2": None,
                    "suburb": f"barrio{p % 5}",
                    "postcode": str(2000 + p),
                    "state": "nsw",
                    "date_of_birth": f"19{50 + p % 40:02d}0{1 + p % 9}1{p % 10}",
                    "soc_sec_id": str(1000000 + p * 7 + copia * (p % 3 == 0)),
                }
            )

    metricas = flujo_validacion.ejecutar_febrl(tmp_path, n_bootstrap=20, df=pd.DataFrame(filas))

    assert metricas["particion"]["prueba"]["personas"] == 24
    assert 0 <= metricas["prueba"]["clusters"]["recall"] <= 1
    assert (tmp_path / "febrl_seleccion_bloqueos.csv").exists()
