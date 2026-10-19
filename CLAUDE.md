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
uv run python scripts/hito2b.py desarrollar   # hito 2b: modelo v2 -> reports/hito2b/
uv run python scripts/hito2b.py evaluar       # v2 congelado en prueba normal y ciegas
uv run python scripts/hito3.py                # hito 3 -> reports/hito3/
uv run python scripts/hito3.py --captura-universo  # PNG de Cosmograph (tras publicar --hito 3)
uv run python scripts/hito5.py tiempo-real    # hito 5: "¿ya es cliente?" -> reports/hito5/
uv run python scripts/escala.py --todos       # escala 100 mil y 1 millón (~10 GB de RAM)
uv run python scripts/hito5.py escala         # tabla y gráficos de escala
uv run python scripts/hito6.py desarrollar   # hito 6: modelo v3 -> reports/hito6/
uv run python scripts/hito6.py evaluar       # v3 congelado: prueba normal y ciega 3
uv run python scripts/hito6.py tiempo-real   # precisión con 1 %, 10 % y 50 % de clientes
uv run python scripts/hito6.py hito3         # hito 3 con 8 pares de semillas (v2 y v3)
uv run python scripts/hito6.py escala        # 100 mil y 1 millón con el v3 congelado
uv run python scripts/hito6.py diagnostico-umbral  # v3 con el umbral del v2 en la ciega 3
uv run python scripts/v11.py diagnostico     # v1.1: diagnóstico previo -> reports/v11/
uv run python scripts/v11.py desarrollar     # v1.1: modelo v4 en desarrollo
uv run python scripts/v11.py grafo           # grafo residencial con 8 pares de semillas
uv run python scripts/v11.py evaluar         # v3 y v4 congelados, grafos, ciega 4
uv run python scripts/v11.py universo        # universo de Cosmograph de la v1.1
uv run python scripts/publicar_resultados.py --hito 1  # o 2, validacion, 2b, 3, 5, 6, v11 -> docs/resultados/
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
  - Hito 2b: `estandarizacion_v2.py` y `modelo_co_v2.py` reutilizan v1 sin modificarla;
    congelados en `hito2b-congelado` junto con `docs/resultados/hito2b/modelo.json` y
    `desarrollo.json` (lo verifica `tests/test_flujo_hito2b.py`). `errores_ciegos_2.py` es
    la segunda prueba ciega: no se usa para desarrollar. Una prueba ciega deja de serlo en
    cuanto se miran sus errores; desde ahí solo sirve como desarrollo.
  - Hito 3: `escenario_hito3.py` (historia, metadatos y patrones sospechosos sobre las
    personas de `sinteticos`, sin modificarlo), `registro_oro.py`, `grafo_compartido.py`,
    `puentes.py` y `flujo_hito3.py`. Desarrollo = escenario semilla 3030; prueba = 3131.
    `docs/hito3_universo.html` (Cosmograph desde esm.sh; jsdelivr carga dos versiones de
    luma.gl y falla) lee `docs/resultados/hito3/universo_*.json`.
  - Hito 5: `tiempo_real.py` (vinculación contra registros de oro, SQL compilado una vez),
    `servicio.py` (FastAPI local), `escala.py` y `flujo_hito5.py`. Los datos de escala van
    a `data/escala/` (no versionados); solo se publican muestras en Parquet. 5 millones no
    cabe en la máquina de referencia (pico de 9,1 GB con 1 millón).
  - Hito 6 (correcciones post-auditoría, ver `audit/INFORME.md`): `sinteticos.agregar_historia`
    (mudanzas y apellido de casada, sin cambiar `generar`), `modelo.aplicar_piso_m` (ningún
    nivel resta más de B bits), `modelo_co_v3.py`, `linea_base.py` (reglas, híbrido y
    segmentos), `calibracion.py` (isotónica sobre el peso y bandas de zona gris) y
    `flujo_hito6.py`. El v3 está congelado en `hito6-congelado` junto con
    `docs/resultados/hito6/{modelo,desarrollo,calibracion}.json` (lo verifica
    `tests/test_hito6.py`). `errores_ciegos_3.py` es la tercera prueba ciega, escrita después
    de congelar. Las ciegas 1, 2 y 3 ya se miraron.
  - `audit/` es el registro de una auditoría independiente: sus archivos existentes no se
    modifican. Sí se pueden agregar archivos nuevos de verificaciones posteriores (por
    ejemplo, `audit/verificacion_hito6.md`), sin tocar los anteriores.
  - Tiempo real con el v3: la zona gris sale de las bandas congeladas
    (`calibracion.json`), trasladadas a la previa 1/N (`tiempo_real.peso_con_otra_previa`).
    `scripts/servicio_local.py` usa el v3 por defecto; `--modelo v2` reproduce el hito 5.
  - Demo: `demo.py` exporta los modelos v2 y v3 a `docs/demo/modelo_demo.json` y
    `modelo_demo_v3.json` (este con las bandas); `docs/demo/motor.js` los reimplementa en
    JavaScript y `tests/test_demo.py` (con Node.js) verifica que da los mismos niveles y
    pesos que Splink. `docs/demo.html` (v3) y `docs/calculadora.html` (lee
    `docs/resultados/hito6/metricas.json`) son páginas estáticas, sin servidor.
  - GIF: `gifs.py` y `scripts/gifs.py` graban con Playwright el recorrido por Cosmograph
    (requiere internet) y el antes y después, en `docs/resultados/gifs/`.
  - v1.1 (realidad residencial): `diagnostico_v11.py` (diagnóstico previo),
    `sinteticos_fecha.py` (fecha de Faker fija: el escenario del hito 3 cambia con la fecha
    de hoy), `escenario_residencial.py` (predios, hogares y familias, sin cambiar los
    generadores anteriores), `estandarizacion_v4.py` (dirección en predio y unidad),
    `modelo_co_v4.py`, `grafo_residencial.py` y `flujo_v11.py`. El v4 está congelado en
    `v4-congelado` junto con `docs/resultados/v11/{modelo,desarrollo,calibracion}.json` y
    `estandarizacion_v4.py`; el grafo residencial, en `grafo-v11-congelado` con
    `clasificador.json` (lo verifica `tests/test_v11.py`). `errores_ciegos_4.py` es la
    cuarta prueba ciega, escrita por un subagente después de congelar. Las ciegas 1 a 4 ya
    se miraron: la próxima corrección necesita una ciega 5. `docs/v11_universo.html` lee
    `docs/resultados/v11/universo_*.json`.
- `scripts/`: puntos de entrada delgados que orquestan funciones de `src/`.
- `notebooks/`: solo exploración. Nada en `src/` ni `scripts/` importa de notebooks.
- `tests/`: pruebas con pytest. Las lentas se marcan con `@pytest.mark.integracion`.
- `data/` (ignorada): datos descargados y caché local.
- `reports/` (ignorada): salidas de trabajo (métricas, modelo, HTML, PNG).
- `README.md` es la puerta de entrada corta; el detalle de cada hito, con todas las cifras,
  está en `INFORME_TECNICO.md`. Las páginas de Pages enlazan sus anclas.
- `docs/`: documentación y fuente de GitHub Pages (rama `main`, carpeta `/docs`).
  - `docs/resultados/`: tableros HTML y PNG finales, **versionados**. Solo se actualizan a
    propósito con `scripts/publicar_resultados.py`.

## Convenciones

- La lógica vive en `src/` como funciones reutilizables **con type hints**.
- Los notebooks son solo para exploración; si algo sirve, se pasa a `src/` con su test.
- Las funciones principales tienen pruebas en `tests/`. Las pruebas no dependen de internet.
- **Las pruebas son deterministas**: el mismo código da el mismo resultado cualquier día y en
  cualquier máquina. Semillas fijas y nada que dependa del reloj (fecha de hoy, hora, zona
  horaria) sin fijarlo; por ejemplo, Faker calcula fechas desde `datetime.now()`, y
  `tests/test_demo.py` lo fija con `HOY_FIJO`.
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

## Regla de procesos (para Claude y cualquier subagente)

- **Nunca terminar procesos que no hayas iniciado tú.** Nada de `taskkill /IM`, `pkill`,
  `killall` ni `kill` generales por nombre: pueden cerrar procesos del usuario o de otras
  sesiones.
- Si un comando se traba, termina solo ese proceso por su identificador (el que lanzaste
  tú) o pregúntale al usuario.
- Al delegar en un subagente, incluye esta regla en sus instrucciones.

## Regla de credenciales (para Claude y cualquier subagente)

- Las credenciales guardadas en la máquina (git, tokens, llaveros) solo se usan para
  `git push`. Para cualquier otra cosa (leer logs de CI, llamar la API de GitHub u otro
  servicio) hay que preguntarle antes al usuario.

## Regla dura de datos

- **Nunca usar datos reales de clientes.** Solo datasets públicos de demostración (Splink,
  FEBRL) o sintéticos generados con Faker.
- **Tampoco** código, reglas ni ideas de proyectos internos de ningún banco.

## Docker

No se usa en este caso: todo corre local con DuckDB. Si más adelante hace falta (por ejemplo,
Spark para escalar Splink), se añade un `docker-compose.yml` en la raíz y se documenta aquí
cómo levantarlo.
