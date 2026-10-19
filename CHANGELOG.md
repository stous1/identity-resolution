# Historia de cambios

Historia por hitos del caso 1 (calidad del dato y resolución de identidades). Todos los
cambios están en la rama `main`; los modelos congelados tienen su tag. El hito 4 (agente de
revisión de la zona gris) está pendiente.

## v1.1.1: reproducibilidad, demo con el v4 y ficha de cliente único

- **Fecha fija en los generadores:** `sinteticos.generar` (y lo que parte de él: hito 2,
  ciegas 1 a 3, escenario del hito 3, tiempo real y escala) corre con `HOY_FIJO` (15 de
  enero de 2026). Antes, el mismo generador con la misma semilla daba datos distintos otro
  día. `tests/test_reproducibilidad.py` mueve el reloj de Faker a 2031 y 2040 y exige los
  mismos datos en cada generador.
- **Todas las evaluaciones publicadas se volvieron a correr** con los modelos congelados,
  sin reentrenar (la escala, sin la caché de `data/escala`). Lo que cambió, en
  [docs/v111.md](docs/v111.md):
  - ciega 3 con el v3: de 0,997 / 0,966 / 0,981 a 0,996 / 0,955 / 0,975 (precisión /
    recall / F1); el v3 queda por debajo del v2 de forma significativa (F1 −0,009);
  - Splink frente a la mejor regla: de +0,065 a +0,055 de F1;
  - la brecha de equidad significativa del v3 pasa del apellido de casada a las direcciones
    urbanas frente a rurales;
  - tiempo real del v3 con 1 % de clientes: de 0,938 a 1,000 (sin falsas alarmas; cifra
    frágil);
  - hito 3: exactitud del grafo en 8 semillas de 98,6 % ± 0,8 a 98,3 % ± 0,6 y otras reglas
    de supervivencia para nombres, apellidos y dirección;
  - 1 millón de registros: precisión de 0,998 a 0,999.
- **Demo y "¿ya es cliente?" con el v4:** el motor en JavaScript reimplementa la dirección
  en predio y unidad; la prueba de equivalencia con Splink pasa de ~630 a ~990 pares (con
  pares residenciales) para el v2, el v3 y el v4. El servicio local usa el v4 por defecto.
  Tiempo real del v4: mismo recall que el v3 en la población normal (0,989) y algo más en la
  residencial (0,997 frente a 0,995), sin falsas alarmas.
- **Ficha de cliente único** ([docs/ficha.html](docs/ficha.html)): registros como grafo con
  la fuerza de cada enlace, registro de oro con origen y regla, datos compartidos con su
  categoría, historia de contacto y alertas; ejemplos de una familia, una pareja de un
  conjunto, una casa de varios pisos y el caso Esther.
- GIF del README con el universo de la v1.1. Trabajo futuro: que el grafo reconozca los
  anillos por su forma y no solo por su tamaño (hallazgo de la ciega 4).

## v1.1: realidad residencial y familiar colombiana (tags `v4-congelado` y `grafo-v11-congelado`)

- **Diagnóstico previo** ([docs/v11_diagnostico.md](docs/v11_diagnostico.md)):
  - el grafo del hito 3 marcaba sospechosas a las parejas sin apellido común, tomaba por
    relleno toda dirección con apartamento y no veía a los vecinos de un edificio;
  - el v3 restaba 1,7 bits al mismo apartamento escrito distinto y sumaba 5,4 a dos vecinos;
    ajusta por frecuencia solo el nivel de dirección exacta;
  - "Esther Nancy MONTENEGRO MUÑOZ" es una suplantación inyectada: la víctima se veía igual
    que la suplantadora;
  - los escenarios del hito 3 y de la ciega 3 cambian con la fecha del día (Faker).
- **Generador residencial** con predios, hogares, parejas, convivientes, conjuntos, casas de
  varios pisos, apellido de casada y convención de apellidos de los hijos.
- **Modelo v4:** dirección en predio y unidad, comparada por niveles con ajuste por
  frecuencia.
- **Grafo residencial:** agrupa la dirección por predio, estima el tipo de predio, reconoce
  parejas y la convención de apellidos, y agrega convivencia probable y multifamiliar. En 8
  pares de semillas, la falsa sospecha pasa de 39,1 % a 0,5 %.
- **Prueba ciega 4:** v4 F1 0,994 frente a 0,987 del v3 (+0,007, IC 0,004 a 0,011), sin
  brechas de equidad significativas. Las personas inocentes marcadas por el grafo pasan de
  36,7 % a 1,6 %, pero las personas de patrones sospechosos detectadas bajan de 81,6 % a
  66,7 % (anillos de 7 clientes tomados como relleno).
- Universo de Cosmograph con las categorías nuevas y con víctima y suplantador distinguidos.

## v1.0: cierre del portafolio

- **Verificación del hito 6** ([audit/verificacion_hito6.md](audit/verificacion_hito6.md))
  y correcciones:
  - la precisión de tiempo real del hito 5 se recalcula con sus propias tasas (0,991 y
    0,909 con 10 % y 1 % de clientes);
  - "solo la regla 'mismo documento' empata con Splink" donde el documento es igual;
  - +0,065 de F1 como cifra global;
  - "no se detecta" brecha de género, con su intervalo;
  - la calibración empeora fuera de muestra;
  - la tabla de escala mezcla modelo y umbral.
- **Diagnóstico del umbral:** con el umbral del v2, el v3 tiene más recall que el v2 en la
  ciega 3 (0,984 frente a 0,978). Se confirma que el umbral explica por qué el v3 pierde
  recall a su umbral congelado.
- **Zona gris por bandas en tiempo real:** "¿ya es cliente?" y el servicio local usan las
  bandas congeladas del v3, trasladadas a la previa 1/N. Precisión y recall no cambian; la
  cola de revisión baja de 20 a 14 consultas (población normal) y de 93 a 86 (ciega 3).
- **README como puerta de entrada.** El detalle completo pasa a
  [INFORME_TECNICO.md](INFORME_TECNICO.md); se agrega la licencia MIT.
- **Demo en el navegador** con el modelo v3, verificada contra Splink. **Calculadora de
  impacto** con supuestos editables. **GIF reproducibles** con Playwright.

## Hito 6: correcciones post-auditoría (tag `hito6-congelado`)

- **Generador con historia** (mudanzas y apellido de casada con divorcio o nuevo
  matrimonio), sin cambiar `generar`.
- **Modelo v3:** un piso a las probabilidades m (ningún campo resta más de 10 bits) y un
  nivel intermedio para el apellido de casada. Peor peso: −10,0 bits, frente a −47,9 (v1)
  y −72,6 (v2).
- **Prueba ciega 3**, de un generador escrito por un subagente nuevo:
  - v3: precisión 0,997 y recall 0,966;
  - v2: 0,994 y 0,978;
  - v1: 0,989 y 0,693.
- Línea base determinística e híbrido; calibración isotónica y bandas de zona gris;
  precisión de tiempo real según la prevalencia; escala con el modelo congelado (precisión
  0,998 con 1 millón de registros); hito 3 con 8 pares de semillas.

## Auditoría independiente

- [audit/INFORME.md](audit/INFORME.md): sin fugas de etiquetas y con todas las cifras
  reproducibles.
- Hallazgos graves:
  - vetos aprendidos de 43 a 73 bits;
  - la precisión cae a escala por reentrenar, no por homónimos;
  - las probabilidades no están calibradas en la zona de decisión.
- Hallazgos medios: no había línea base, el umbral es inestable, el hito 3 se midió con
  una sola semilla y el tiempo real, con 50 % de clientes.

## Demo en JavaScript

- Motor que reimplementa la estandarización y las comparaciones del v2, con una prueba de
  equivalencia contra Splink sobre unos 630 pares.

## Hito 5: tiempo real y escala

- **"¿Ya es cliente?"** contra una base de registros de oro, con el SQL de Splink compilado
  una vez: precisión 0,999 y recall 0,993, con 60 ms de mediana. Incluye un servicio local
  con FastAPI.
- **Escala con DuckDB:** 100 mil y 1 millón de registros en una sola máquina (134 s y
  9,1 GB de pico con 1 millón), más un universo grande en Cosmograph desde Parquet.
- Integración continua con GitHub Actions (ruff, pruebas rápidas y de integración).

## Hito 3: registro de oro, grafo y puentes

- Escenario con historia, metadatos por registro y patrones sospechosos (anillos y
  suplantaciones).
- Registro de oro por reglas de supervivencia elegidas en desarrollo, a menos de 5 puntos
  del techo alcanzable.
- Grafo de identidad compartida (relleno, hogar o sospechoso), puentes, cola de revisión y
  universo en Cosmograph.

## Hito 2b: corregir y volver a medir a ciegas (tag `hito2b-congelado`)

- Estandarización y esquema v2 corregidos con la prueba ciega 1 (apellido de casada,
  apodos, nombres cruzados, documento, teléfonos y fechas).
- **Prueba ciega 2**, de un segundo generador escrito después de congelar: precisión 0,998
  y recall 1,000 (v1 en los mismos datos: 0,995 y 0,920).

## Hito 2: clientes sintéticos colombianos (tags `hito2-congelado` y `hito2-congelado-r1`)

- Generador es_CO con familiares, fechas erradas y documentos vacíos; estandarización de
  nombres, documento, celular, correo y dirección; equidad por grupo con bootstrap.
- **Prueba normal:** precisión 1,000 y recall 0,998.
- **Prueba ciega 1:** recall 0,636, la cifra honesta. Además, la prueba ciega encontró un
  fallo con apellidos vacíos; se corrigió sin cambiar resultados y se creó el tag `-r1`.
- Validación externa con FEBRL3: precisión 1,000 y recall 0,997.

## Hito 1: fake_1000 de punta a punta

- Carga de fake_1000 con caché, modelo Fellegi-Sunter sin etiquetas, bloqueo aproximado,
  umbral por costo y partición desarrollo/prueba por persona con bootstrap.
- Tableros de Splink (cascada, Cluster Studio, comparison viewer) y portada en GitHub
  Pages.
- Prueba: precisión 0,970 y recall 0,851 por clúster.
