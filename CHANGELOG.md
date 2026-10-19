# Historia de cambios

Historia por hitos del caso 1 (calidad del dato y resolución de identidades). Todos los
cambios están en la rama `main`; los modelos congelados tienen su tag. El hito 4 (agente de
revisión de la zona gris) está pendiente.

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
