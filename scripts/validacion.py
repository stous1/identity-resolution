"""Validación del hito 2: prueba ciega con el modelo congelado y FEBRL3.

Uso:
    uv run python scripts/validacion.py [--bootstrap 1000] [--sin-capturas]

Verifica que el modelo del hito 2 no cambió desde el tag ``hito2-congelado``, lo aplica
sin ajustes a registros del generador de errores ciego, repite el procedimiento del hito
2 sobre FEBRL3 y escribe las tres cifras en reports/validacion/.
"""

from __future__ import annotations

import argparse
import json

from identidades import rutas
from identidades.flujo_validacion import ejecutar_validacion


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bootstrap", type=int, default=1000, help="réplicas del bootstrap")
    parser.add_argument(
        "--sin-capturas", action="store_true", help="no capturar PNG de los tableros con Playwright"
    )
    args = parser.parse_args()

    metricas = ejecutar_validacion(
        rutas.REPORTS_VALIDACION, n_bootstrap=args.bootstrap, capturas=not args.sin_capturas
    )
    print(json.dumps(metricas["tres_cifras_clusters"], indent=2, ensure_ascii=False))
    ciega = metricas["prueba_ciega"]
    print(json.dumps(ciega["diferencias_significativas"], indent=2, ensure_ascii=False))
    print(
        json.dumps(
            ciega["diagnostico_por_error"]["diferencias_significativas"],
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"\nResultados en {rutas.REPORTS_VALIDACION}")


if __name__ == "__main__":
    main()
