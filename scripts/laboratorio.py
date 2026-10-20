"""Datos del laboratorio interactivo (docs/laboratorio.html).

Uso:
    uv run python scripts/laboratorio.py   # -> reports/laboratorio/ y docs/resultados/laboratorio/

Pares de la prueba ciega 1 con el v1 congelado (y el aporte de los vetos) y de la ciega 3
con el v3 congelado, con las cifras de referencia calculadas en Python.
"""

from __future__ import annotations

import json
import shutil

from identidades import laboratorio, rutas


def main() -> None:
    resumen = laboratorio.exportar(rutas.REPORTS_LABORATORIO)
    rutas.DOCS_RESULTADOS_LABORATORIO.mkdir(parents=True, exist_ok=True)
    for nombre in ("auditoria.json", "umbral.json"):
        shutil.copy2(rutas.REPORTS_LABORATORIO / nombre, rutas.DOCS_RESULTADOS_LABORATORIO / nombre)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
