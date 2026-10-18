"""Copia los resultados finales de reports/ a docs/resultados/ (GitHub Pages).

Uso:
    uv run python scripts/publicar_resultados.py [--hito 1|2|validacion|2b]

Correr después del script del hito, solo cuando se quiera actualizar lo publicado.
"""

from __future__ import annotations

import argparse

from identidades import flujo, flujo_hito2, flujo_hito2b, flujo_validacion, rutas

HITOS = {
    1: (rutas.REPORTS, rutas.DOCS_RESULTADOS, flujo.ARCHIVOS_PUBLICABLES),
    2: (rutas.REPORTS_HITO2, rutas.DOCS_RESULTADOS_HITO2, flujo_hito2.ARCHIVOS_PUBLICABLES),
    "validacion": (
        rutas.REPORTS_VALIDACION,
        rutas.DOCS_RESULTADOS_VALIDACION,
        flujo_validacion.ARCHIVOS_PUBLICABLES,
    ),
    "2b": (rutas.REPORTS_HITO2B, rutas.DOCS_RESULTADOS_HITO2B, flujo_hito2b.ARCHIVOS_PUBLICABLES),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hito", choices=[str(h) for h in HITOS], default="1")
    parser.add_argument(
        "--solo", nargs="*", help="publicar solo estos archivos (p. ej. al congelar un modelo)"
    )
    args = parser.parse_args()

    clave = int(args.hito) if args.hito.isdigit() else args.hito
    origen, destino, archivos = HITOS[clave]
    archivos = args.solo or archivos
    for ruta in flujo.publicar_resultados(origen, destino, archivos):
        print(ruta.relative_to(rutas.RAIZ))


if __name__ == "__main__":
    main()
