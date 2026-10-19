"""v1.1: realidad residencial y familiar colombiana.

Uso:
    uv run python scripts/v11.py diagnostico   # diagnóstico previo -> reports/v11/
    uv run python scripts/v11.py desarrollar   # modelo v4 en desarrollo -> reports/v11/
    uv run python scripts/v11.py grafo         # clasificador residencial, 8 pares de semillas
    uv run python scripts/v11.py evaluar       # v3 y v4 congelados, incluida la ciega 4
    uv run python scripts/v11.py universo      # universo de Cosmograph con las categorías nuevas

Entre desarrollar y evaluar, el modelo se publica y se congela con el tag ``v4-congelado``.
"""

from __future__ import annotations

import argparse
import json

from identidades import flujo_v11, rutas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "fase", choices=["diagnostico", "desarrollar", "grafo", "evaluar", "universo"]
    )
    parser.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()
    directorio = rutas.REPORTS_V11

    if args.fase == "diagnostico":
        salida = flujo_v11.diagnostico(directorio)
    elif args.fase == "desarrollar":
        resumen = flujo_v11.desarrollar_v4(directorio)
        salida = {
            "piso_m": {
                k: v["costo"] for k, v in resumen["piso_m"]["candidatos"].items()
            }
            | {"elegido": resumen["piso_m"]["max_bits_en_contra"]},
            "umbral": resumen["umbral"],
            "pesos_domicilio": resumen["pesos_domicilio"],
        }
    elif args.fase == "grafo":
        salida = flujo_v11.grafo_semillas(directorio)["resumen"]
    elif args.fase == "evaluar":
        salida = flujo_v11.evaluar_congelados(directorio, args.bootstrap)["resumen"]
    else:
        salida = flujo_v11.universo(directorio)
    print(json.dumps(salida, indent=2, ensure_ascii=False, default=str))
    print(f"\nResultados en {directorio}")


if __name__ == "__main__":
    main()
