"""Hito 1: resolución de identidades sobre fake_1000, con desarrollo y prueba separados.

Uso:
    uv run python scripts/hito1_fake1000.py [--frac-desarrollo 0.6] [--semilla 42]
        [--umbral U] [--costo-fp 10] [--costo-fn 1] [--bootstrap 1000]
        [--sin-capturas] [--sin-referencia]

Las reglas de bloqueo, el modelo y el umbral se eligen en desarrollo; las métricas
principales se miden en prueba. Sin --umbral, usa el que minimiza el costo de errores
por clúster en desarrollo. Escribe métricas, modelo, tableros HTML y PNG en reports/.
"""

from __future__ import annotations

import argparse
import json

from identidades import datos, rutas
from identidades.flujo import ejecutar_hito1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frac-desarrollo", type=float, default=0.6)
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument(
        "--umbral", type=float, default=None, help="umbral fijo (por defecto: mínimo costo)"
    )
    parser.add_argument("--costo-fp", type=float, default=10.0, help="costo de un falso positivo")
    parser.add_argument("--costo-fn", type=float, default=1.0, help="costo de un falso negativo")
    parser.add_argument("--bootstrap", type=int, default=1000, help="réplicas del bootstrap")
    parser.add_argument(
        "--sin-capturas", action="store_true", help="no capturar PNG de los tableros con Playwright"
    )
    parser.add_argument(
        "--sin-referencia",
        action="store_true",
        help="no calcular la referencia con todo el dataset",
    )
    args = parser.parse_args()

    df = datos.cargar_fake_1000()
    metricas = ejecutar_hito1(
        df,
        rutas.REPORTS,
        frac_desarrollo=args.frac_desarrollo,
        semilla=args.semilla,
        umbral=args.umbral,
        costo_fp=args.costo_fp,
        costo_fn=args.costo_fn,
        n_bootstrap=args.bootstrap,
        capturas=not args.sin_capturas,
        referencia=not args.sin_referencia,
    )

    resumen = {
        "particion": metricas["particion"],
        "umbral": metricas["umbral"],
        "prueba": metricas["prueba"]["intervalos"],
    }
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    print(f"\nResultados en {rutas.REPORTS}")


if __name__ == "__main__":
    main()
