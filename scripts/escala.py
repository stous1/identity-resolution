"""Escala con DuckDB: tiempo y memoria por etapa para 100 mil y 1 millón de registros.

Uso:
    uv run python scripts/escala.py --todos          # cada tamaño en un proceso propio
    uv run python scripts/escala.py --tamano 100000  # un solo tamaño

Los datos van a data/escala/ (no se versionan); las mediciones, a reports/hito5/. Con 1
millón también se exporta el universo grande (Parquet) para Cosmograph.

5 millones no cabe en la máquina de referencia: con 1 millón el pico ya es de 9,1 GB y la
corrida de 5 millones se detuvo por falta de memoria.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict

from identidades import escala, rutas

DIRECTORIO = rutas.REPORTS_HITO5


def un_tamano(n: int) -> None:
    mediciones, artefactos = escala.correr(n)
    resultado = {
        "registros_objetivo": n,
        "mediciones": [asdict(m) for m in mediciones],
        "calidad": artefactos["calidad"],
    }
    if n == 1_000_000:
        resultado["universo"] = escala.exportar_universo(artefactos, DIRECTORIO, 200_000)
        resultado["universo_liviano"] = escala.exportar_universo(
            artefactos, DIRECTORIO, 40_000, sufijo="_liviano"
        )
    DIRECTORIO.mkdir(parents=True, exist_ok=True)
    (DIRECTORIO / f"escala_{n}.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(resultado["mediciones"], ensure_ascii=False, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tamano", type=int)
    parser.add_argument("--todos", action="store_true")
    args = parser.parse_args()
    if args.todos:
        for n in escala.TAMANOS:
            # Un proceso propio por tamaño: el pico de memoria de uno no contamina al otro.
            subprocess.run([sys.executable, __file__, "--tamano", str(n)], check=True)
    elif args.tamano:
        un_tamano(args.tamano)
    else:
        parser.error("indica --tamano N o --todos")


if __name__ == "__main__":
    main()
