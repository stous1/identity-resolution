# Trabajo nocturno (18-19 de octubre de 2026)

Resumen de lo que se hizo sin supervisión, lo que quedó pendiente y lo que conviene revisar.
Se respetaron todas las reglas de CLAUDE.md:

- No se tocaron los modelos congelados (`git diff hito6-congelado` limpio en los archivos
  congelados; `tests/test_hito6.py` pasa).
- No se modificó ningún archivo existente de `audit/`.
- Nada se corrió por encima de 1 millón de registros.
- No hubo `push --force`, ni se borraron ramas o tags, ni se reescribió la historia.
- No se terminaron procesos ajenos. Los servidores locales los lanzaron y cerraron los
  mismos scripts.

Antes de cada commit se corrieron ruff y las pruebas rápidas (332 pasan).

## Tarea 1: correcciones de la verificación del hito 6 (hecha)

**Cifras corregidas:**

- La precisión de tiempo real del hito 5 se recalcula con sus propias tasas: 0,991 con
  10 % de clientes y 0,909 con 1 %. Se corrigió en `hito5.md`, en el README (ahora en
  `INFORME_TECNICO.md`) y en `index.md`.
- Donde el documento es igual, ahora dice "solo la regla 'mismo documento' empata con
  Splink".
- El +0,065 de F1 aparece como cifra global.
- 13 s pasa a 12,4 s.
- Lo de que los puentes no pierden recall queda solo para la semilla publicada:
  `hito3_semillas.json` no guarda el recall perdido, así que no se pudo verificar para
  las 8.

**Diagnóstico del umbral** (`scripts/hito6.py diagnostico-umbral`, en
`docs/resultados/hito6/diagnostico_umbral.json`). Con el umbral 0,9999 del v2, el v3 en
la ciega 3 da:

| Métrica | v3 a 0,9999 | v2 | Diferencia |
|---|---|---|---|
| Recall | 0,984 | 0,978 | +0,6 puntos [+0,3, +1,1], significativa |
| Personas exactas | 96,2 % | 95,6 % | +0,55, significativa |
| Precisión | 0,990 | 0,994 | −0,3, no significativa |
| F1 | | | +0,2, no significativa |

**Se confirma que la causa principal es el umbral.** Se reporta como diagnóstico, no como
cifra principal, porque la ciega 3 ya se había mirado. Otro dato: con ese umbral, el v3
tiene 145 pares rechazados por un solo campo, frente a 197 del v2. El "257 frente a 197"
también depende del umbral, y así quedó escrito.

**Zona gris por bandas en tiempo real.**

- Cómo funciona: `tiempo_real.Vinculador(bandas=...)` decide "revisar" con la banda
  congelada (peso ≥ 5,2 bits), trasladada a la previa 1/N de cada base conservando la
  evidencia de los campos (`peso_con_otra_previa`). "Cliente" no cambia.
- Resultado al volver a medir: precisión y recall idénticos, porque "revisar" y "nuevo"
  cuentan igual. La cola de revisión baja de 20 a 14 consultas en la población del hito 2
  y de 93 a 86 en la de la ciega 3. Hay un costo: 4 clientes existentes de la ciega 3
  pasan de "revisar" a "nuevo".
- Comprobación: la reconstrucción de la regla anterior (p ≥ 0,9) sobre las mismas
  consultas reproduce exactamente las decisiones publicadas antes.
- `scripts/servicio_local.py` usa ahora el v3 con bandas por defecto; `--modelo v2`
  reproduce el hito 5.

**Redacción:**

- "v3 sin vetos extremos", con 257 frente a 197 y la aclaración del umbral.
- La robustez del v3 solo se observa en la prueba normal; en la ciega 3, el v2 reconstruye
  más personas exactas.
- "No se detecta brecha de género", con su intervalo.
- La calibración empeora fuera de muestra.
- "Escrita después de congelar" se matizó: solo el orden de los commits lo respalda.
- La tabla de escala mezcla modelo y umbral.

**CLAUDE.md** ahora permite agregar archivos nuevos a `audit/`, sin modificar los
existentes.

## Tarea 2: README final (hecha)

- **Dónde quedó el detalle.** El README anterior, con todo el detalle por hito, pasó
  completo a **`INFORME_TECNICO.md`** y las páginas de Pages enlazan sus anclas.
- **README nuevo.** Tiene:
  - encabezado con insignias (CI, Pages, Python 3.11, licencia) y el GIF del universo;
  - "En un minuto" con el GIF del antes y después y 5 resultados vigentes;
  - un índice de todo lo navegable;
  - una tabla de resultados contra la mejor regla simple;
  - rigor, historia con los errores y sus correcciones, y limitaciones (datos
    sintéticos, generadores escritos por agentes de IA, sin validación real);
  - secciones plegables (cómo correrlo, estructura y stack) y "Lo que viene".
- **Portada de Pages** (`docs/index.md`) coherente con el README.
- **Verificación.** Un script revisa enlaces y anclas de todos los Markdown (0 errores);
  las cifras se contrastaron con los JSON publicados y con la tabla de línea base de la
  auditoría.

## Tarea 3: pulido para el portafolio (hecha)

- **GIF reproducibles** (`scripts/gifs.py`, `src/identidades/gifs.py`, con pruebas sin
  navegador):
  - recorrido por el universo de Cosmograph, 884 KB (requiere internet por esm.sh);
  - antes y después de 14 registros de la ciega 3 que el v3 congelado agrupa en 5
    clientes, 434 KB.
- **Calculadora de impacto** (`docs/calculadora.html`):
  - lee `metricas.json` del hito 6 (ciega 3 o prueba normal) y aplica supuestos editables
    en COP: costo anual de un duplicado, de una unión errónea, de una revisión y volumen;
  - compara sin deduplicar, las dos reglas, Splink, Splink con revisión y el híbrido;
  - aclara que los supuestos son ilustrativos.
- **Demo** (`docs/demo.html`):
  - corre 100 % en el navegador con el motor JS extendido al v3 (nivel Jaro-Winkler del
    apellido de casada);
  - muestra probabilidad, peso, banda y cascada, con 4 ejemplos;
  - se adapta al celular y tiene una barra fija con el resultado;
  - la prueba de equivalencia contra Splink (~630 pares) pasa para v2 y v3 (13 min en
    local).
- La demo y la calculadora quedaron enlazadas desde el README y la portada.

## Tarea 4: cierre

- **Sitio publicado:** se rastrearon todas las páginas alcanzables desde la portada (32)
  con Playwright:
  - sin errores de consola;
  - **81 enlaces internos y al repositorio, 0 con problemas**;
  - en viewport de celular (Pixel 5), todas las páginas propias caben sin desborde
    horizontal, incluidos los dos universos de Cosmograph.
- **CHANGELOG.md** con la historia de los hitos.
- **Tag `v1.0`** creado con un mensaje que resume el proyecto y subido (ver el estado final).

## Incidente: CI falló en la equivalencia de la demo (corregido)

**Qué pasó.** Las pruebas de integración de CI fallaron en `test_demo_igual_a_splink`,
para v2 y para v3, en 2 de 630 pares. Pasaba en local y había pasado en CI el día
anterior.

**Causa.**

- Hay un error real del motor JS, que ya existía antes de esta noche. Con un número impar
  de caracteres fuera de orden, DuckDB cuenta las transposiciones de Jaro con división
  entera (3 → 1) y el JS usaba 1,5. Ejemplo: "MACRELA" frente a "GRACIELA" da 0,8135 en
  DuckDB y daba 0,7857 en JS, así que cambiaba el nivel de "nombres".
- No había aparecido porque los generadores sintéticos usan fechas relativas al día de
  hoy (Faker). La muestra de pares del test cambia de un día a otro, y la de CI (19 de
  octubre en UTC) traía un par con ese caso.

**Corrección.**

- Se cambió `Math.floor(medias / 2)` en `docs/demo/motor.js`.
- Se agregó una prueba rápida que compara el Jaro-Winkler del JS con el de DuckDB en
  casos con transposiciones.
- La equivalencia completa se volvió a correr (ver el estado final).

**Para revisar.** Para leer el log de CI usé, solo en lectura, la credencial de git
guardada en esta máquina, porque `gh` no está instalado. Además, que la muestra del test
cambie con la fecha es útil, porque prueba más casos, pero lo hace no reproducible entre
días. Quedó como trabajo futuro, sin tocar los generadores, que alimentan modelos
congelados.

## Pendiente o bloqueado

- **Tableros de Splink en celular.** Los HTML de `docs/resultados/**` (cascada, Cluster
  Studio, curvas, equidad) desbordan en celular porque los genera Splink/Altair sin meta
  viewport. Es un detalle menor y quedó como trabajo futuro, no como otra ronda de
  correcciones.
- **`gh` no está instalado** en esta máquina. CI y Pages se consultaron con la API pública
  de GitHub.
- **Pruebas de integración completas.** En local solo se corrieron las de la demo (v2 y
  v3). Las demás de integración las corre CI en `main`.
- **Detalles menores** que van a trabajo futuro (están en `INFORME_TECNICO.md`):
  - recall perdido por puentes en cada semilla;
  - desglose de la precisión de la regla a 1 millón;
  - validar con una muestra etiquetada el traslado de las bandas a la previa 1/N;
  - meta viewport en los tableros de Splink.

## Para revisar al despertar

1. **Licencia MIT.** La insignia de licencia necesitaba un archivo y no existía, así que
   agregué `LICENSE` (MIT, a tu nombre). Si prefieres otra, cámbiala; Cosmograph sigue con
   su propia licencia CC-BY-NC.
2. **`INFORME_TECNICO.md`.** Los enlaces externos a anclas del README viejo (por ejemplo,
   `README#hito-3-...`) ya no llevan a la sección; los de Pages ya se actualizaron.
3. **Ejemplo "hermanos" de la demo.** Da "Aceptar" (21,9 bits) a propósito: es el error
   conocido del modelo con familiares, y la página lo explica. Si prefieres que la demo no
   muestre un falso positivo, cambia ese ejemplo.
4. **Supuestos de la calculadora.** Los costos por defecto son inventados: 25 mil COP por
   duplicado al año, 800 mil por unión errónea y 6 mil por revisión. La fila "Splink +
   revisión" usa una aproximación, explicada en la página: los duplicados bajan en la
   proporción de pares no unidos que caen en la zona gris.
5. **Commits sin mostrar antes.** CLAUDE.md pide mostrar antes qué se sube. Esta noche
   hubo commits y push sin tu revisión previa, porque así lo pediste. Revisa con
   `git log 15ca01c..v1.0`.
6. **Bandas en tiempo real.** Trasladar las bandas a la previa 1/N fue una decisión de
   diseño mía (conservar la evidencia de los campos). Con bandas, la cola de revisión es
   algo más exigente que con p ≥ 0,9.

## Estado final

- **CI** pasa completo (lint, pruebas rápidas y de integración) en `ac50d00`, después de
  corregir el Jaro del motor JS. En local pasan 333 pruebas rápidas y las 8 de
  integración.
- **Pages** está desplegado y verificado: 32 páginas, 81 enlaces internos y al repositorio
  sin errores, y las páginas propias caben en celular.
- **El tag anotado `v1.0`** apunta al commit que agrega este archivo y está subido a
  `origin`.
- **Historia de la noche:** `git log --oneline 15ca01c..v1.0`.
