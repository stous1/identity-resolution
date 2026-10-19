"""Demo en el navegador: exporta los modelos v2, v3 y v4 congelados y da la referencia en Python.

La demo (``docs/demo.html`` y ``docs/demo/motor.js``) reimplementa en JavaScript la
estandarización v2 (que el v3 y el v4 reutilizan), la dirección en predio y unidad del v4
(``estandarizacion_v4``) y las comparaciones de los modelos, y calcula el peso de
coincidencia con los parámetros m y u exportados aquí. El v3 y el v4 llevan además las
bandas de zona gris congeladas en desarrollo; la página usa el v4. No aplica el ajuste
por frecuencia de términos (que depende de la base completa), así que la referencia de
Python tampoco: suma los factores de Bayes de cada nivel sin ``bf_tf_adj``.
``tests/test_demo.py`` compara ambos sobre una muestra de pares.
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
from identidades import estandarizacion_v4 as v4
from identidades import flujo_hito2b, flujo_hito6, flujo_v11, rutas
from identidades.modelo_co_v2 import ESQUEMA_V2

RUTA_MODELO: Path = rutas.DOCS / "demo" / "modelo_demo.json"
RUTA_MODELO_V3: Path = rutas.DOCS / "demo" / "modelo_demo_v3.json"
RUTA_MODELO_V4: Path = rutas.DOCS / "demo" / "modelo_demo_v4.json"
RUTAS: dict[str, Path] = {"v2": RUTA_MODELO, "v3": RUTA_MODELO_V3, "v4": RUTA_MODELO_V4}


def cargar(version: str) -> tuple[dict[str, Any], float, dict | None, str]:
    """Configuración, umbral, bandas de zona gris (v3 y v4) y origen del modelo congelado."""
    if version == "v4":
        configuracion, umbral, _, bandas = flujo_v11.cargar_congelado_v4()
        origen = f"docs/resultados/v11/modelo.json (tag {flujo_v11.TAG_CONGELADO})"
        return configuracion, umbral, bandas, origen
    if version == "v3":
        configuracion, umbral, _, bandas = flujo_hito6.cargar_congelado_v3()
        origen = f"docs/resultados/hito6/modelo.json (tag {flujo_hito6.TAG_CONGELADO})"
        return configuracion, umbral, bandas, origen
    configuracion, umbral = flujo_hito2b.cargar_congelado_v2()
    origen = f"docs/resultados/hito2b/modelo.json (tag {flujo_hito2b.TAG_CONGELADO})"
    return configuracion, umbral, None, origen


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


def exportar_modelo(ruta: Path | None = None, version: str = "v2") -> dict[str, Any]:
    """Parámetros del modelo congelado y diccionarios de la estandarización, en JSON."""
    ruta = ruta or RUTAS[version]
    configuracion, umbral, bandas, origen = cargar(version)
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
    modelo: dict[str, Any] = {
        "origen": origen,
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
    if version == "v4":
        modelo["diccionarios"]["direccion_v4"] = {
            "alias_via": v4.ALIAS_VIA,
            "cuadrantes": v4.CUADRANTES,
            "palabras_unidad": v4.PALABRAS_UNIDAD,
            "ordinales": v4.ORDINALES,
            "componentes": v4.COMPONENTES,
        }
    if bandas is not None:
        modelo["bandas"] = bandas
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(modelo, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    return modelo


class Referencia:
    """Puntúa pares de registros crudos con Splink y el modelo congelado (sin ajuste TF)."""

    def __init__(self, version: str = "v2") -> None:
        self.configuracion, _, _, _ = cargar(version)
        # El v4 prepara además predio y unidad, con la lista de partes tipada como texto.
        self.preparar = flujo_v11.preparar_v4_tipado if version == "v4" else ESQUEMA_V2.preparar
        vacio = self.preparar(_crudos([{}, {}])).drop(columns=["cluster"], errors="ignore")
        self.linker = Linker(vacio, self.configuracion, db_api=DuckDBAPI())
        self.columnas = [c["output_column_name"] for c in self.configuracion["comparisons"]]
        lam = self.configuracion["probability_two_random_records_match"]
        self.previo = math.log2(lam / (1 - lam))

    def puntuar(self, registro_1: dict, registro_2: dict) -> dict[str, Any]:
        preparado = self.preparar(_crudos([registro_1, registro_2]))
        preparado = preparado.drop(columns=["cluster"], errors="ignore")
        # Cada registro como tabla de un renglón, para conservar los tipos de las listas.
        par = self.linker.inference.compare_two_records(
            preparado.iloc[[0]].reset_index(drop=True), preparado.iloc[[1]].reset_index(drop=True)
        )
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
