"""Hito 2b: corregir con la prueba ciega 1 y volver a medir a ciegas.

Uso:
    uv run python scripts/hito2b.py desarrollar   # elige bloqueo y umbral -> reports/hito2b/
    uv run python scripts/hito2b.py evaluar       # modelo congelado en prueba normal y ciegas

Entre las dos fases, el modelo se publica y se congela con el tag ``hito2b-congelado``.
"""

from __future__ import annotations

import argparse
import json

from identidades import rutas
from identidades.flujo_hito2b import desarrollar_v2, evaluar_congelado_v2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fase", choices=["desarrollar", "evaluar"])
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--sin-capturas", action="store_true")
    args = parser.parse_args()

    if args.fase == "desarrollar":
        resumen = desarrollar_v2(rutas.REPORTS_HITO2B)
        print(json.dumps(resumen["umbral"], indent=2, ensure_ascii=False))
    else:
        metricas = evaluar_congelado_v2(
            rutas.REPORTS_HITO2B, n_bootstrap=args.bootstrap, capturas=not args.sin_capturas
        )
        print(json.dumps(metricas["evolucion_clusters"], indent=2, ensure_ascii=False))
    print(f"\nResultados en {rutas.REPORTS_HITO2B}")


if __name__ == "__main__":
    main()
