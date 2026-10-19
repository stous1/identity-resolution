"""Servicio local "¿ya es cliente?" (FastAPI + uvicorn), solo en 127.0.0.1.

Uso:
    uv run python scripts/servicio_local.py [--puerto 8000] [--modelo v4|v3|v2]

Construye una base de clientes sintéticos (registros de oro con el modelo congelado) y
expone POST /consultar. Documentación interactiva en http://127.0.0.1:8000/docs.

Por defecto usa el v4 (``v4-congelado``, dirección por predio y unidad) con la zona gris
por bandas de peso de su calibración congelada. ``--modelo v3`` usa el v3 (``hito6-congelado``)
y ``--modelo v2`` reproduce el servicio del hito 5 (zona gris p >= 0,9).
"""

from __future__ import annotations

import argparse

import uvicorn

from identidades import flujo_hito2b, flujo_hito6, flujo_v11, tiempo_real
from identidades.servicio import crear_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--puerto", type=int, default=8000)
    parser.add_argument("--personas", type=int, default=3000)
    parser.add_argument("--modelo", choices=["v4", "v3", "v2"], default="v4")
    args = parser.parse_args()

    esquema = None
    if args.modelo == "v4":
        configuracion, umbral, esquema = flujo_v11.modelos_congelados()["v4"]
        bandas = flujo_v11.cargar_congelado_v4()[3]
    elif args.modelo == "v3":
        configuracion, umbral, _, bandas = flujo_hito6.cargar_congelado_v3()
    else:
        (configuracion, umbral), bandas = flujo_hito2b.cargar_congelado_v2(), None
    registros_base, _, _ = tiempo_real.preparar_evaluacion(args.personas)
    base = tiempo_real.construir_base(registros_base, configuracion, umbral, esquema)
    vinculador = tiempo_real.Vinculador(
        base,
        configuracion,
        umbral,
        relleno=tiempo_real.telefonos_de_relleno(registros_base),
        bandas=bandas,
        esquema=esquema,
    )
    app = crear_app(vinculador, f"{args.modelo} congelado")
    uvicorn.run(app, host="127.0.0.1", port=args.puerto)


if __name__ == "__main__":
    main()
