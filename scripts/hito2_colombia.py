"""Hito 2: clientes sintéticos colombianos, estandarización y equidad.

Uso:
    uv run python scripts/hito2_colombia.py [--personas 2000] [--semilla 42]
        [--costo-fp 10] [--costo-fn 1] [--bootstrap 1000] [--sin-capturas]

Genera los datos sintéticos, elige bloqueo y umbral en desarrollo, mide en prueba con y
sin estandarización, evalúa la equidad y escribe métricas y tableros en reports/hito2/.
"""

from __future__ import annotations

import argparse
import json

from identidades import rutas
from identidades.flujo_hito2 import ejecutar_hito2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--personas", type=int, default=2000)
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--costo-fp", type=float, default=10.0, help="costo de un falso positivo")
    parser.add_argument("--costo-fn", type=float, default=1.0, help="costo de un falso negativo")
    parser.add_argument("--bootstrap", type=int, default=1000, help="réplicas del bootstrap")
    parser.add_argument(
        "--sin-capturas", action="store_true", help="no capturar PNG de los tableros con Playwright"
    )
    args = parser.parse_args()

    metricas = ejecutar_hito2(
        rutas.REPORTS_HITO2,
        n_personas=args.personas,
        semilla=args.semilla,
        costo_fp=args.costo_fp,
        costo_fn=args.costo_fn,
        n_bootstrap=args.bootstrap,
        capturas=not args.sin_capturas,
    )

    resumen = {
        nombre: {
            "umbral": v["umbral"],
            "prueba_clusters": v["prueba"]["intervalos"]["clusters"],
        }
        for nombre, v in metricas["variantes"].items()
    }
    resumen["equidad"] = metricas["equidad"]["diferencias_significativas"]
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    print(f"\nResultados en {rutas.REPORTS_HITO2}")


if __name__ == "__main__":
    main()
