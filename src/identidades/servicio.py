"""Servicio local "¿ya es cliente?" con FastAPI (solo para correr en local).

Uso:
    uv run python scripts/servicio_local.py   # http://127.0.0.1:8000/docs

``POST /consultar`` recibe un registro crudo y devuelve la decisión (``cliente``,
``revisar`` o ``nuevo``), el cliente encontrado y la explicación por campo. La zona gris
sale de las bandas congeladas del v3 si el ``Vinculador`` las tiene (ver ``tiempo_real``).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from identidades.tiempo_real import Vinculador


class Registro(BaseModel):
    """Registro crudo, tal como llega de un canal (todos los campos son opcionales)."""

    tipo_documento: str | None = Field(None, examples=["CC"])
    numero_documento: str | None = Field(None, examples=["1.023.456.789"])
    nombres: str | None = Field(None, examples=["José Luis"])
    apellidos: str | None = Field(None, examples=["Pérez Gómez"])
    fecha_nacimiento: str | None = Field(None, examples=["1985-03-07"])
    celular: str | None = Field(None, examples=["+57 300 123 4567"])
    correo: str | None = Field(None, examples=["jose.perez@gmail.com"])
    direccion: str | None = Field(None, examples=["Cra 45 # 10-20"])
    ciudad: str | None = Field(None, examples=["Medellín"])
    departamento: str | None = Field(None, examples=["Antioquia"])


def crear_app(vinculador: Vinculador, modelo: str = "v3 congelado") -> FastAPI:
    app = FastAPI(
        title="¿Ya es cliente?",
        description=(
            f"Vinculación en tiempo real con el modelo {modelo} (datos sintéticos). "
            "Solo para uso local."
        ),
        version="1.0",
    )

    @app.get("/salud")
    def salud() -> dict[str, Any]:
        return {
            "estado": "ok",
            "clientes_en_base": len(vinculador.base),
            "umbral": vinculador.umbral,
            "zona_gris": vinculador.descripcion_zona_gris(),
        }

    @app.post("/consultar")
    def consultar(registro: Registro) -> dict[str, Any]:
        respuesta = vinculador.consultar(registro.model_dump())
        respuesta.get("cliente", {}).pop("cluster", None)  # la verdad no sale del servicio
        return respuesta

    return app
