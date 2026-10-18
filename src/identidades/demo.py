"""Demo en el navegador: exporta el modelo v2 congelado y da la referencia en Python.

La demo (``docs/demo.html`` y ``docs/demo/motor.js``) reimplementa en JavaScript la
estandarización v2 y las comparaciones del modelo, y calcula el peso de coincidencia con
los parámetros m y u exportados aquí. No aplica el ajuste por frecuencia de términos (que
depende de la base completa), así que la referencia de Python tampoco: suma los factores
de Bayes de cada nivel sin ``bf_tf_adj``. ``tests/test_demo.py`` compara ambos sobre una
muestra de pares.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
from splink import DuckDBAPI, Linker

from identidades import estandarizacion as v1
from identidades import estandarizacion_v2 as v2
from identidades import flujo_hito2b, rutas
from identidades.modelo_co_v2 import ESQUEMA_V2

RUTA_MODELO: Path = rutas.DOCS / "demo" / "modelo_demo.json"
CAMPOS_CRUDOS: list[str] = [
    "numero_documento",
    "nombres",
    "apellidos",
    "fecha_nacimiento",
    "celular",
    "correo",
    "direccion",
    "ciudad",
]


def exportar_modelo(ruta: Path = RUTA_MODELO) -> dict[str, Any]:
    """Parámetros del modelo congelado y diccionarios de la estandarización, en JSON."""
    configuracion, umbral = flujo_hito2b.cargar_congelado_v2()
    comparaciones = [
        {
            "columna": c["output_column_name"],
            "descripcion": c.get("comparison_description", c["output_column_name"]),
            "niveles": [
                {
                    "etiqueta": n.get("label_for_charts", ""),
                    "nulo": bool(n.get("is_null_level", False)),
                    "m": n.get("m_probability"),
                    "u": n.get("u_probability"),
                    "sql": n["sql_condition"],
                }
                for n in c["comparison_levels"]
            ],
        }
        for c in configuracion["comparisons"]
    ]
    modelo = {
        "origen": f"docs/resultados/hito2b/modelo.json (tag {flujo_hito2b.TAG_CONGELADO})",
        "lambda": configuracion["probability_two_random_records_match"],
        "umbral": umbral,
        "zona_gris": 0.9,
        "comparaciones": comparaciones,
        "diccionarios": {
            "apodos": v2.APODOS,
            "compuestos": v2.COMPUESTOS,
            "apellidos_con_de": sorted(v2.APELLIDOS_CON_DE),
            "particulas": sorted(v1.PARTICULAS),
            "alias_via": v1.ALIAS_VIA,
            "meses": v2._MESES,
        },
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(modelo, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    return modelo


class Referencia:
    """Puntúa pares de registros crudos con Splink y el modelo congelado (sin ajuste TF)."""

    def __init__(self) -> None:
        self.configuracion, _ = flujo_hito2b.cargar_congelado_v2()
        vacio = ESQUEMA_V2.preparar(_crudos([{}, {}])).drop(columns=["cluster"], errors="ignore")
        self.linker = Linker(vacio, self.configuracion, db_api=DuckDBAPI())
        self.columnas = [c["output_column_name"] for c in self.configuracion["comparisons"]]
        lam = self.configuracion["probability_two_random_records_match"]
        self.previo = math.log2(lam / (1 - lam))

    def puntuar(self, registro_1: dict, registro_2: dict) -> dict[str, Any]:
        preparado = ESQUEMA_V2.preparar(_crudos([registro_1, registro_2]))
        preparado = preparado.drop(columns=["cluster"], errors="ignore")
        filas = [
            {k: (None if not isinstance(v, list) and pd.isna(v) else v) for k, v in r.items()}
            for r in preparado.to_dict("records")
        ]
        par = self.linker.inference.compare_two_records(filas[0], filas[1])
        fila = par.as_pandas_dataframe().iloc[0]
        gammas = {c: int(fila[f"gamma_{c}"]) for c in self.columnas}
        peso = self.previo + sum(math.log2(float(fila[f"bf_{c}"])) for c in self.columnas)
        return {"gammas": gammas, "peso": peso}


def _crudos(registros: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "unique_id": i,
                "tipo_documento": "CC",
                **{c: r.get(c) for c in CAMPOS_CRUDOS},
                "departamento": None,
            }
            for i, r in enumerate(registros)
        ]
    )
