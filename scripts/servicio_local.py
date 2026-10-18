"""Servicio local "¿ya es cliente?" (FastAPI + uvicorn), solo en 127.0.0.1.

Uso:
    uv run python scripts/servicio_local.py [--puerto 8000]

Construye una base de clientes sintéticos (registros de oro con el modelo v2 congelado)
y expone POST /consultar. Documentación interactiva en http://127.0.0.1:8000/docs.
"""

from __future__ import annotations

import argparse

import uvicorn

from identidades import flujo_hito2b, tiempo_real
from identidades.servicio import crear_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--puerto", type=int, default=8000)
    parser.add_argument("--personas", type=int, default=3000)
    args = parser.parse_args()

    configuracion, umbral = flujo_hito2b.cargar_congelado_v2()
    registros_base, _, _ = tiempo_real.preparar_evaluacion(args.personas)
    base = tiempo_real.construir_base(registros_base, configuracion, umbral)
    vinculador = tiempo_real.Vinculador(
        base, configuracion, umbral, relleno=tiempo_real.telefonos_de_relleno(registros_base)
    )
    uvicorn.run(crear_app(vinculador), host="127.0.0.1", port=args.puerto)


if __name__ == "__main__":
    main()
