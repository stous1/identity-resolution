# Resolución de identidades con Splink

Caso de uso 1 de un portafolio de ciencia de datos y agentes aplicado a banca: **calidad del
dato y resolución de identidades**.

## Qué problema resuelve

En una base de clientes, la misma persona aparece varias veces con pequeñas diferencias: un
dígito errado en el documento, un nombre sin tilde, un teléfono viejo. Este proyecto detecta
qué registros corresponden al mismo cliente con un modelo probabilístico (Fellegi-Sunter,
entrenado sin etiquetas con Splink), explica cada decisión y mide su precisión contra la
verdad conocida.

## Cómo correrlo

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
```

## Regla de datos

Este repositorio **nunca usa datos reales de clientes**. Solo datasets públicos de
demostración (Splink, FEBRL) o datos sintéticos generados con Faker.

> Los resultados, capturas y tableros publicados se agregan al completar el hito 1.
