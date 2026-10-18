"""Copia los resultados finales de reports/ a docs/resultados/ (GitHub Pages).

Uso:
    uv run python scripts/publicar_resultados.py [--hito 1|2]

Correr después del script del hito, solo cuando se quiera actualizar lo publicado.
"""

from __future__ import annotations

import argparse

from identidades import flujo, flujo_hito2, rutas

HITOS = {
    1: (rutas.REPORTS, rutas.DOCS_RESULTADOS, flujo.ARCHIVOS_PUBLICABLES),
    2: (rutas.REPORTS_HITO2, rutas.DOCS_RESULTADOS_HITO2, flujo_hito2.ARCHIVOS_PUBLICABLES),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hito", type=int, choices=sorted(HITOS), default=1)
    args = parser.parse_args()

    origen, destino, archivos = HITOS[args.hito]
    for ruta in flujo.publicar_resultados(origen, destino, archivos):
        print(ruta.relative_to(rutas.RAIZ))


if __name__ == "__main__":
    main()
