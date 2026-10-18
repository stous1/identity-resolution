"""Hito 3: registro de oro, grafo de identidad compartida y puentes.

Uso:
    uv run python scripts/hito3.py [--bootstrap 1000]
    uv run python scripts/hito3.py --captura-universo   # después de publicar --hito 3

Elige reglas y umbrales en el escenario de desarrollo, mide en el de prueba con el modelo
v2 congelado y escribe métricas, cola de revisión y datos del universo en reports/hito3/.
"""

from __future__ import annotations

import argparse
import json

from identidades import rutas, tableros
from identidades.flujo_hito3 import ejecutar_hito3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument(
        "--captura-universo",
        action="store_true",
        help="capturar docs/hito3_universo.html (Cosmograph) en docs/resultados/hito3/",
    )
    args = parser.parse_args()
    if args.captura_universo:
        estado = tableros.capturar_pagina_servida(
            rutas.DOCS, "hito3_universo.html", rutas.DOCS_RESULTADOS_HITO3 / "universo.png"
        )
        print(estado)
        return
    metricas = ejecutar_hito3(rutas.REPORTS_HITO3, n_bootstrap=args.bootstrap)
    resumen = {
        "registro_oro": metricas["registro_oro"]["prueba_con_reglas_elegidas"],
        "grafo": metricas["grafo_compartido"]["prueba"]["por_clase"],
        "cola_revision": metricas["cola_revision"],
    }
    print(json.dumps(resumen, indent=2, ensure_ascii=False, default=str))
    print(f"\nResultados en {rutas.REPORTS_HITO3}")


if __name__ == "__main__":
    main()
