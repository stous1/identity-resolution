"""Hito 1: resolución de identidades sobre fake_1000 de punta a punta.

Uso:
    uv run python scripts/hito1_fake1000.py [--umbral 0.9] [--sin-capturas]

Escribe métricas, modelo, tableros HTML y PNG en reports/.
"""

from __future__ import annotations

import argparse
import json

from identidades import datos, rutas
from identidades.flujo import ejecutar_hito1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--umbral", type=float, default=0.9, help="umbral de match_probability")
    parser.add_argument(
        "--sin-capturas", action="store_true", help="no capturar PNG de los tableros con Playwright"
    )
    args = parser.parse_args()

    df = datos.cargar_fake_1000()
    metricas = ejecutar_hito1(df, rutas.REPORTS, umbral=args.umbral, capturas=not args.sin_capturas)

    resumen = {k: metricas[k] for k in ("bloqueo", "pares", "clusters")}
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    print(f"\nResultados en {rutas.REPORTS}")


if __name__ == "__main__":
    main()
