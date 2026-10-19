"""Flujo de la v1.1: realidad residencial y familiar colombiana.

1. **Desarrollar el v4** (``desarrollar_v4``). Desarrollo = el del v3 (hito 2 con historia,
   ciegas 1 y 2) más un escenario residencial de desarrollo (semilla 4040). Ahí se eligen
   el bloqueo, el piso de las m, el umbral y la calibración, como en el hito 6. El modelo se
   congela en el tag ``v4-congelado``.
2. **Grafo residencial** (``grafo_semillas``): el clasificador nuevo se ajusta en el
   escenario de desarrollo y se mide en el de prueba, con 8 pares de semillas, frente al
   clasificador del hito 3.
3. **Evaluar los congelados** (``evaluar_congelados``): v3 y v4 en la prueba normal, la
   ciega 3 (ya mirada, solo como referencia), los escenarios residenciales de prueba y la
   **prueba ciega 4**.

La ciega 3 no entra en el desarrollo del v4 y no se mira mientras se desarrolla.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from identidades import bloqueo, calibracion, evaluacion, flujo_hito6, modelo, rutas
from identidades.escenario_residencial import generar_escenario_residencial
from identidades.modelo_co_v4 import CANDIDATOS_MAX_BITS, ESQUEMA_V4

TAG_CONGELADO: str = "v4-congelado"
ARCHIVOS_CONGELADOS: list[str] = [
    "src/identidades/modelo_co_v4.py",
    "src/identidades/estandarizacion_v4.py",
    "docs/resultados/v11/modelo.json",
    "docs/resultados/v11/desarrollo.json",
    "docs/resultados/v11/calibracion.json",
]
SEMILLA_RESIDENCIAL_DESARROLLO: int = 4040
DESPLAZAMIENTO_RESIDENCIAL: int = 300_000


def _escribir(datos_json: dict, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(datos_json, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="\n",
    )


def datos_desarrollo_v4() -> pd.DataFrame:
    """Desarrollo del v3 más el escenario residencial de desarrollo (ids desplazados)."""
    base = flujo_hito6.datos_desarrollo()
    residencial, _, _ = generar_escenario_residencial(2000, SEMILLA_RESIDENCIAL_DESARROLLO)
    residencial = flujo_hito6._desplazar(residencial, DESPLAZAMIENTO_RESIDENCIAL)
    columnas = list(base.columns)
    return pd.concat([base, residencial[columnas]], ignore_index=True)


def desarrollar_v4(
    directorio: Path, costo_fp: float = 10.0, costo_fn: float = 1.0
) -> dict[str, Any]:
    """Elige bloqueo, piso de las m, umbral y calibración del v4 en desarrollo."""
    directorio.mkdir(parents=True, exist_ok=True)
    df = datos_desarrollo_v4()
    esquema = ESQUEMA_V4
    bloqueos, historial = bloqueo.seleccionar_reglas(
        df, esquema.bloqueos_exactos, esquema.bloqueos_candidatos, 0.005, esquema.preparar
    )
    linker = modelo.crear_linker(df, modelo.crear_settings(bloqueos, esquema), esquema)
    modelo.entrenar(linker, esquema)
    sin_piso = linker.misc.save_model_to_json()
    preparado = esquema.preparar(df)

    candidatos: dict[str, dict[str, Any]] = {}
    for bits in (None, *CANDIDATOS_MAX_BITS):
        configuracion = sin_piso if bits is None else modelo.aplicar_piso_m(sin_piso, bits)
        r = flujo_hito6._evaluar_configuracion(configuracion, preparado, df, costo_fp, costo_fn)
        r["configuracion"] = configuracion
        candidatos["sin piso" if bits is None else str(bits)] = r
    # Como en el v3: el piso es obligatorio; gana el de menor costo y, si empatan, el más
    # estricto.
    elegido = min(CANDIDATOS_MAX_BITS, key=lambda b: (candidatos[str(b)]["costo"], b))
    final = candidatos[str(elegido)]
    _escribir(final["configuracion"], directorio / "modelo.json")

    marcadas = flujo_hito6.marcar(final["pred"], evaluacion.pares_verdaderos(df))
    cal = calibracion.ajustar(marcadas["match_weight"], marcadas["es_match"])
    limites = calibracion.bandas(cal, peso_umbral=flujo_hito6.peso_de(final["umbral"]))
    _escribir({**cal.a_dict(), "bandas": limites}, directorio / "calibracion.json")
    final["curva"].to_csv(
        directorio / "curva_costo_desarrollo.csv", index=False, lineterminator="\n"
    )

    resumen = {
        "desarrollo": {
            "descripcion": (
                "Desarrollo del v3 (hito 2 con historia, ciega 1 y ciega 2) + escenario "
                f"residencial de desarrollo (semilla {SEMILLA_RESIDENCIAL_DESARROLLO})"
            ),
            "registros": len(df),
            "personas": int(df["cluster"].nunique()),
        },
        "bloqueos_prediccion": [list(b) for b in bloqueos],
        "seleccion_bloqueos": historial.to_dict("records"),
        "piso_m": {
            "max_bits_en_contra": elegido,
            "criterio": "menor costo por clúster en desarrollo (10·FP + FN); empate: más estricto",
            "candidatos": {
                k: {kk: v[kk] for kk in ("umbral", "costo", "clusters", "vetos")}
                for k, v in candidatos.items()
            },
        },
        "pesos_extremos": {
            "sin_piso": modelo.pesos_extremos(sin_piso),
            "con_piso": modelo.pesos_extremos(final["configuracion"]),
        },
        "pesos_domicilio": pesos_niveles(final["configuracion"], "domicilio"),
        "umbral": {
            "criterio": "min_costo_cluster",
            "valor": final["umbral"],
            "peso": flujo_hito6.peso_de(final["umbral"]),
            "costo_fp": costo_fp,
            "costo_fn": costo_fn,
        },
        "calibracion": {
            "metodo": "isotónica de la verdad sobre match_weight, pares del bloqueo en desarrollo",
            "pares": cal.pares,
            "bandas": limites,
        },
    }
    _escribir(resumen, directorio / "desarrollo.json")
    return resumen


def pesos_niveles(configuracion: dict, comparacion: str) -> list[dict[str, Any]]:
    """Peso (log2 m/u) de cada nivel de una comparación del modelo guardado."""
    import math

    (comp,) = [c for c in configuracion["comparisons"] if c["output_column_name"] == comparacion]
    return [
        {
            "nivel": n.get("label_for_charts", n["sql_condition"]),
            "bits": round(math.log2(n["m_probability"] / n["u_probability"]), 2),
            "frecuencia": n.get("tf_adjustment_column"),
        }
        for n in comp["comparison_levels"]
        if not n.get("is_null_level")
    ]


def cargar_congelado_v4(
    directorio: Path | None = None,
) -> tuple[dict[str, Any], float, calibracion.Calibracion, dict]:
    """Modelo v4, umbral, calibración y bandas de zona gris congelados."""
    directorio = directorio or rutas.DOCS_RESULTADOS_V11
    configuracion = json.loads((directorio / "modelo.json").read_text(encoding="utf-8"))
    desarrollo = json.loads((directorio / "desarrollo.json").read_text(encoding="utf-8"))
    cal = json.loads((directorio / "calibracion.json").read_text(encoding="utf-8"))
    bandas = cal.pop("bandas")
    return configuracion, desarrollo["umbral"]["valor"], calibracion.Calibracion(**cal), bandas


def verificar_congelado(tag: str = TAG_CONGELADO) -> None:
    """Falla si el esquema, la estandarización o el modelo v4 cambiaron desde ``tag``."""
    cambios = subprocess.run(
        ["git", "diff", "--quiet", tag, "--", *ARCHIVOS_CONGELADOS], cwd=rutas.RAIZ
    ).returncode
    if cambios:
        raise RuntimeError(f"El modelo v4 congelado cambió desde {tag}: {ARCHIVOS_CONGELADOS}")
