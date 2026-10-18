"""Hito 1: resolución de identidades sobre fake_1000 de punta a punta.

Uso:
    uv run python scripts/hito1_fake1000.py [--umbral U] [--costo-fp 10] [--costo-fn 1]
                                            [--sin-capturas]

Sin --umbral, usa el que minimiza el costo de errores por clúster.

Escribe métricas, modelo, tableros HTML y PNG en reports/.
"""

from __future__ import annotations

import argparse
import json

from identidades import datos, rutas
from identidades.flujo import ejecutar_hito1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--umbral", type=float, default=None, help="umbral fijo (por defecto: mínimo costo)"
    )
    parser.add_argument("--costo-fp", type=float, default=10.0, help="costo de un falso positivo")
    parser.add_argument("--costo-fn", type=float, default=1.0, help="costo de un falso negativo")
    parser.add_argument(
        "--sin-capturas", action="store_true", help="no capturar PNG de los tableros con Playwright"
    )
    args = parser.parse_args()

    df = datos.cargar_fake_1000()
    metricas = ejecutar_hito1(
        df,
        rutas.REPORTS,
        umbral=args.umbral,
        costo_fp=args.costo_fp,
        costo_fn=args.costo_fn,
        capturas=not args.sin_capturas,
    )

    resumen = {k: metricas[k] for k in ("umbral", "bloqueo", "pares", "clusters")}
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    print(f"\nResultados en {rutas.REPORTS}")


if __name__ == "__main__":
    main()
