"""GIF del README y de Pages, reproducibles con Playwright.

Uso:
    uv run python scripts/gifs.py                 # los dos
    uv run python scripts/gifs.py agrupacion      # antes y después (ciega 3, v3 congelado)
    uv run python scripts/gifs.py universo        # recorrido por Cosmograph (requiere internet)

Escribe en docs/resultados/gifs/.
"""

from __future__ import annotations

import argparse

from identidades import gifs, rutas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("gif", nargs="?", choices=["agrupacion", "universo"])
    args = parser.parse_args()
    destino = rutas.DOCS_RESULTADOS / "gifs"
    if args.gif in (None, "agrupacion"):
        ruta = gifs.grabar_agrupacion(destino / "agrupacion.gif")
        print(f"{ruta} ({ruta.stat().st_size / 1024:.0f} KB)")
    if args.gif in (None, "universo"):
        ruta = gifs.grabar_universo(rutas.DOCS, destino / "universo.gif")
        print(f"{ruta} ({ruta.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
