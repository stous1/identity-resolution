"""v1.1.1: reproducibilidad y ficha de cliente único.

Uso:
    uv run python scripts/v111.py hito2    # v1 congelado en la prueba normal con fecha fija
    uv run python scripts/v111.py fichas   # datos de docs/ficha.html -> reports/v11/fichas.json

``fichas`` lee las reglas de supervivencia publicadas del hito 3: correrlo después de
publicar el hito 3.
"""

from __future__ import annotations

import argparse
import json

from identidades import flujo_v111, rutas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fase", choices=["hito2", "fichas"])
    args = parser.parse_args()
    if args.fase == "hito2":
        salida = flujo_v111.reevaluar_hito2(rutas.REPORTS_HITO2)
    else:
        salida = flujo_v111.exportar_fichas(rutas.REPORTS_V11)
    print(json.dumps(salida, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
