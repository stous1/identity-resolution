"""v1.1.1: reproducibilidad y ficha de cliente único.

Uso:
    uv run python scripts/v111.py hito2    # v1 congelado en la prueba normal con fecha fija
    uv run python scripts/v111.py fichas   # datos de docs/ficha.html -> reports/v11/fichas.json
    uv run python scripts/v111.py tiempo-real  # "¿ya es cliente?" con el v4 y el v3

``fichas`` lee las reglas de supervivencia publicadas del hito 3: correrlo después de
publicar el hito 3.
"""

from __future__ import annotations

import argparse
import json

from identidades import flujo_v111, rutas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fase", choices=["hito2", "fichas", "tiempo-real"])
    args = parser.parse_args()
    if args.fase == "hito2":
        salida = flujo_v111.reevaluar_hito2(rutas.REPORTS_HITO2)
    elif args.fase == "fichas":
        salida = flujo_v111.exportar_fichas(rutas.REPORTS_V11)
    else:
        salida = flujo_v111.tiempo_real_v4(rutas.REPORTS_V11)["resumen"]
    print(json.dumps(salida, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
