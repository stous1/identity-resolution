"""Hito 6: correcciones post-auditoría.

Uso:
    uv run python scripts/hito6.py desarrollar    # modelo v3 en desarrollo -> reports/hito6/
    uv run python scripts/hito6.py evaluar        # v3 congelado: prueba normal y ciega 3
    uv run python scripts/hito6.py tiempo-real    # "¿ya es cliente?" con prevalencias
    uv run python scripts/hito6.py escala         # 100 mil y 1 millón con el v3 congelado
    uv run python scripts/hito6.py hito3          # hito 3 con varias semillas

Entre desarrollar y evaluar, el modelo se publica y se congela con el tag
``hito6-congelado``.
"""

from __future__ import annotations

import argparse
import json

from identidades import flujo_hito6, rutas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "fase", choices=["desarrollar", "evaluar", "tiempo-real", "escala", "hito3"]
    )
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--tamano", type=int, help="solo para escala: un tamaño")
    args = parser.parse_args()
    directorio = rutas.REPORTS_HITO6

    if args.fase == "desarrollar":
        resumen = flujo_hito6.desarrollar_v3(directorio)
        salida = {k: resumen[k] for k in ("piso_m", "umbral", "calibracion")}
        salida["piso_m"] = {
            k: v["costo"] if isinstance(v, dict) else v
            for k, v in resumen["piso_m"]["candidatos"].items()
        } | {"elegido": resumen["piso_m"]["max_bits_en_contra"]}
    elif args.fase == "evaluar":
        salida = flujo_hito6.evaluar_congelado_v3(directorio, args.bootstrap)["resumen"]
    elif args.fase == "tiempo-real":
        salida = flujo_hito6.tiempo_real_prevalencias(directorio, args.bootstrap)["resumen"]
    elif args.fase == "escala":
        salida = flujo_hito6.escala_congelada(directorio, args.tamano)
    else:
        salida = flujo_hito6.estabilidad_hito3(directorio)["resumen"]
    print(json.dumps(salida, indent=2, ensure_ascii=False, default=str))
    print(f"\nResultados en {directorio}")


if __name__ == "__main__":
    main()
