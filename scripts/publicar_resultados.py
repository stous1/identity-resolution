"""Copia los resultados finales del hito 1 de reports/ a docs/resultados/.

Uso:
    uv run python scripts/publicar_resultados.py

Correr después de scripts/hito1_fake1000.py, solo cuando se quiera actualizar lo
publicado en GitHub Pages.
"""

from __future__ import annotations

from identidades import rutas
from identidades.flujo import publicar_resultados


def main() -> None:
    copiados = publicar_resultados(rutas.REPORTS, rutas.DOCS_RESULTADOS)
    for ruta in copiados:
        print(ruta.relative_to(rutas.RAIZ))


if __name__ == "__main__":
    main()
