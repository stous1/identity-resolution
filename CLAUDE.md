# CLAUDE.md

Guía para trabajar en este repositorio.

## Objetivo

Caso de uso 1 del portafolio de ciencia de datos y agentes aplicado a banca: **calidad del dato
y resolución de identidades**. La misma persona aparece varias veces en una base de clientes
(cédula con un dígito errado, nombre sin tilde, teléfono viejo). El proyecto detecta qué
registros son el mismo cliente con un modelo probabilístico Fellegi-Sunter (Splink), explica
cada decisión, evalúa contra la verdad conocida y, más adelante, construye un registro de oro,
un grafo de datos compartidos sospechosos y un agente que revisa la zona gris.

Descripción completa del caso: [docs/caso-01-identidades.md](docs/caso-01-identidades.md).

## Stack

- Python 3.11, manejado por **uv** (`.python-version` fija 3.11).
- **Splink 4** sobre **DuckDB** (motor local).
- **Faker** para datos sintéticos.
- Altair + vl-convert para gráficos y PNG; Playwright (dev) para capturar tableros HTML.
- **pytest** para pruebas y **ruff** para lint y formato.

## Comandos

```bash
uv sync                                     # crea .venv e instala dependencias (incluye dev)
uv run playwright install chromium          # una sola vez, para las capturas PNG
uv run pytest                               # todas las pruebas
uv run pytest -m "not integracion"          # solo pruebas rápidas
uv run ruff check . && uv run ruff format . # lint y formato
uv run python scripts/hito1_fake1000.py     # flujo completo del hito 1 -> reports/
uv run python scripts/hito2_colombia.py      # hito 2 (sintéticos colombianos) -> reports/hito2/
uv run python scripts/validacion.py          # prueba ciega + FEBRL3 -> reports/validacion/
uv run python scripts/publicar_resultados.py --hito 1  # o 2, o validacion -> docs/resultados/
```

## Estructura

- `src/identidades/`: toda la lógica, como funciones reutilizables.
  - `rutas.py`: rutas del proyecto. **Toda ruta se obtiene de aquí.**
  - `datos.py`, `modelo.py`, `bloqueo.py`, `evaluacion.py`, `tableros.py` y `flujo.py`
    (flujo del hito 1 y publicación de resultados).
  - Hito 2: `sinteticos.py` (generador), `estandarizacion.py`, `modelo_co.py` (esquema
    colombiano) y `flujo_hito2.py`. Un `modelo.Esquema` agrupa comparaciones, preparación
    y reglas de cada conjunto de datos.
  - Validación: `errores_ciegos.py` (generador escrito sin leer la estandarización),
    `modelo_febrl.py` y `flujo_validacion.py`. El modelo del hito 2 está congelado en el tag
    `hito2-congelado-r1`: `estandarizacion.py`, `modelo_co.py` y
    `docs/resultados/hito2/modelo.json` no se cambian sin crear un tag nuevo y repetir la
    prueba ciega (lo verifica `tests/test_flujo_validacion.py`).
- `scripts/`: puntos de entrada delgados que orquestan funciones de `src/`.
- `notebooks/`: solo exploración. Nada en `src/` ni `scripts/` importa de notebooks.
- `tests/`: pruebas con pytest. Las lentas se marcan con `@pytest.mark.integracion`.
- `data/` (ignorada): datos descargados y caché local.
- `reports/` (ignorada): salidas de trabajo (métricas, modelo, HTML, PNG).
- `docs/`: documentación y fuente de GitHub Pages (rama `main`, carpeta `/docs`).
  - `docs/resultados/`: tableros HTML y PNG finales, **versionados**. Solo se actualizan a
    propósito con `scripts/publicar_resultados.py`.

## Convenciones

- La lógica vive en `src/` como funciones reutilizables **con type hints**.
- Los notebooks son solo para exploración; si algo sirve, se pasa a `src/` con su test.
- Las funciones principales tienen pruebas en `tests/`. Las pruebas no dependen de internet.
- Documentación, docstrings y mensajes de commit **en español**.
- Rutas centralizadas en `identidades.rutas`; **nunca rutas absolutas** en el código.
- Commits pequeños y enfocados. No hacer commit sin mostrar antes qué se va a subir.

## Regla de evaluación

- Toda decisión que mire la verdad conocida (reglas de bloqueo, umbral, parámetros) se toma
  solo en **desarrollo**. Las métricas principales se reportan en **prueba**, medidas una sola
  vez y con intervalos de confianza (bootstrap por persona).
- La partición es por persona: todos los registros de una persona quedan del mismo lado.
- Métricas medidas sobre los mismos datos con que se eligió algo se presentan solo como
  referencia y marcadas como optimistas.

## Regla dura de datos

- **Nunca usar datos reales de clientes.** Solo datasets públicos de demostración (Splink,
  FEBRL) o sintéticos generados con Faker.
- **Tampoco** código, reglas ni ideas de proyectos internos de ningún banco.

## Docker

No se usa en este caso: todo corre local con DuckDB. Si más adelante hace falta (por ejemplo,
Spark para escalar Splink), se añade un `docker-compose.yml` en la raíz y se documenta aquí
cómo levantarlo.
