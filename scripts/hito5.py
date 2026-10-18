"""Hito 5: vinculación en tiempo real y tabla de escala.

Uso:
    uv run python scripts/hito5.py tiempo-real  # evalúa "¿ya es cliente?" -> reports/hito5/
    uv run python scripts/hito5.py escala       # junta escala_*.json en tabla y gráficos

Las mediciones de escala se generan antes con ``scripts/escala.py --todos``.
"""

from __future__ import annotations

import argparse
import json

from identidades import flujo_hito5


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("accion", choices=["tiempo-real", "escala"])
    args = parser.parse_args()
    if args.accion == "tiempo-real":
        resultado = flujo_hito5.ejecutar_tiempo_real()
        resumen = {k: resultado[k] for k in ("base", "precision", "recall", "latencia_ms")}
        print(json.dumps(resumen, indent=2, ensure_ascii=False, default=str))
    else:
        print(flujo_hito5.agregar_escala().to_string(index=False))


if __name__ == "__main__":
    main()
