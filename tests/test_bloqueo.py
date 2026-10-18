"""Pruebas de la selección voraz de reglas de bloqueo."""

import pandas as pd
import pytest

from identidades import bloqueo, modelo


def test_pares_de_regla(registros_pequenos):
    preparado = modelo.preparar(registros_pequenos)

    # Ciudad: London {0,1}, Leeds {4,5}; Hull solo una vez y un nulo que no coincide.
    assert bloqueo.pares_de_regla(preparado, ("city",)) == {(0, 1), (4, 5)}
    # Soundex del apellido: Kelly y Kely coinciden (K400); Allen {0,1}; Davies {4,5}.
    assert bloqueo.pares_de_regla(preparado, ("surname_soundex",)) == {(0, 1), (2, 3), (4, 5)}
    # Dos expresiones a la vez: año de nacimiento y primera letra del apellido.
    regla = ("substr(dob, 1, 4)", "substr(surname, 1, 1)")
    assert bloqueo.pares_de_regla(preparado, regla) == {(0, 1), (2, 3), (4, 5)}


def test_seleccionar_reglas_agrega_solo_lo_que_suma(registros_pequenos):
    # Exacta por correo: solo cubre (2,3). Ciudad suma (0,1) y (4,5). Soundex ya no suma.
    elegidas, historial = bloqueo.seleccionar_reglas(
        registros_pequenos,
        exactas=[("email",)],
        candidatas=[("surname_soundex",), ("city",)],
    )

    assert elegidas[0] == ("email",)
    assert len(elegidas) == 2
    assert historial["recall_bloqueo"].tolist() == [1 / 3, 1.0]
    assert historial["recall_bloqueo"].is_monotonic_increasing


def test_seleccionar_reglas_desempata_por_menos_comparaciones():
    # Dos candidatas cubren el mismo par verdadero; "dob" genera un par falso más.
    df = pd.DataFrame(
        {
            "unique_id": [0, 1, 2],
            "first_name": ["Ana", "Ana", "Luis"],
            "surname": ["Ruiz", "Ruiz", "Gil"],
            "dob": ["2000-01-01", "2000-01-01", "2000-01-01"],
            "city": [None, None, None],
            "email": ["a@x.co", "b@x.co", "c@x.co"],
            "cluster": [0, 0, 1],
        }
    )

    elegidas, _ = bloqueo.seleccionar_reglas(
        df, exactas=[("email",)], candidatas=[("dob",), ("surname",)]
    )

    assert elegidas == [("email",), ("surname",)]


def test_seleccionar_reglas_sin_pares_verdaderos_falla(registros_pequenos):
    todos_distintos = registros_pequenos.assign(cluster=range(len(registros_pequenos)))

    with pytest.raises(ValueError, match="No hay pares verdaderos"):
        bloqueo.seleccionar_reglas(todos_distintos, [("email",)], [("city",)])
