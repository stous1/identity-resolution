"""Copia los resultados finales de reports/ a docs/resultados/ (GitHub Pages).

Uso:
    uv run python scripts/publicar_resultados.py [--hito 1|2|validacion]

Correr después del script del hito, solo cuando se quiera actualizar lo publicado.
"""

from __future__ import annotations

import argparse

from identidades import flujo, flujo_hito2, flujo_validacion, rutas

HITOS = {
    1: (rutas.REPORTS, rutas.DOCS_RESULTADOS, flujo.ARCHIVOS_PUBLICABLES),
    2: (rutas.REPORTS_HITO2, rutas.DOCS_RESULTADOS_HITO2, flujo_hito2.ARCHIVOS_PUBLICABLES),
    "validacion": (
        rutas.REPORTS_VALIDACION,
        rutas.DOCS_RESULTADOS_VALIDACION,
        flujo_validacion.ARCHIVOS_PUBLICABLES,
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hito", choices=[str(h) for h in HITOS], default="1")
    args = parser.parse_args()

    clave = int(args.hito) if args.hito.isdigit() else args.hito
    origen, destino, archivos = HITOS[clave]
    for ruta in flujo.publicar_resultados(origen, destino, archivos):
        print(ruta.relative_to(rutas.RAIZ))


if __name__ == "__main__":
    main()
