# Resolución de identidades con Splink

Caso de uso 1 de un portafolio de ciencia de datos y agentes aplicado a banca: **calidad del
dato y resolución de identidades**.

**Tableros interactivos:** [stous1.github.io/identity-resolution](https://stous1.github.io/identity-resolution/)

## Qué problema resuelve

En una base de clientes, la misma persona aparece varias veces con pequeñas diferencias: un
dígito errado en el documento, un nombre sin tilde, un teléfono viejo. Eso infla el número de
clientes, duplica comunicaciones y esconde relaciones de riesgo.

Este proyecto detecta qué registros corresponden al mismo cliente con un modelo probabilístico
Fellegi-Sunter (con [Splink](https://github.com/moj-analytical-services/splink) sobre DuckDB),
**entrenado sin etiquetas**, explica cada decisión campo por campo y mide su precisión contra
la verdad conocida.

Descripción completa del caso: [docs/caso-01-identidades.md](docs/caso-01-identidades.md).

## Hito 1: fake_1000 de punta a punta

Dataset de demostración de Splink: 1.000 registros de 251 personas, con errores de digitación,
campos vacíos y variaciones de nombres. La columna `cluster` (quién es quién) solo se usa para
elegir reglas y umbral en desarrollo y para evaluar.

**Modelo**

- Comparaciones: nombre y apellido (Jaro-Winkler con ajuste por frecuencia), fecha de
  nacimiento (niveles por distancia), ciudad (exacta con ajuste por frecuencia) y correo.
- Entrenamiento sin etiquetas: λ con reglas determinísticas, *u* por muestreo aleatorio y *m*
  con EM en dos pasadas (bloqueo por nombre+apellido y por fecha de nacimiento).
- Bloqueo: 4 reglas exactas (nombre, apellido, fecha de nacimiento, correo) más las reglas
  aproximadas que se eligen en desarrollo (ver abajo).

### Cómo se evalúa

Elegir reglas y umbral mirando la verdad conocida y medir sobre los mismos datos da métricas
optimistas. Por eso:

1. **Partición por persona.** Las 251 personas se dividen al azar (semilla 42) en
   **desarrollo** (60 %: 151 personas, 608 registros) y **prueba** (40 %: 100 personas, 392
   registros). Todos los registros de una persona quedan del mismo lado.
2. **Desarrollo.** Solo aquí se mira la verdad conocida: se eligen las reglas de bloqueo, se
   entrena el modelo y se elige el umbral por costo.
3. **Prueba.** El modelo de desarrollo se aplica a prueba, deduplicando dentro de prueba. Los
   parámetros *m* y *u* vienen de desarrollo; λ (la probabilidad a priori de que dos registros
   al azar sean la misma persona) depende del tamaño del conjunto, así que se vuelve a estimar
   en prueba con las mismas reglas determinísticas, que no usan etiquetas (0,0055 en
   desarrollo, 0,0082 en prueba).
4. **Medición única.** Las métricas de prueba se calculan una sola vez, con intervalos de
   confianza del 95 % por bootstrap: 1.000 réplicas remuestreando personas con reemplazo,
   porque prueba tiene solo 100 personas.

### Resultados en prueba

Umbral 0,83, elegido en desarrollo. Entre corchetes, el intervalo de confianza del 95 %.

| Nivel | Precisión | Recall | F1 |
|---|---|---|---|
| Por par | 0,998 [0,991 – 1,000] | 0,709 [0,649 – 0,761] | 0,829 [0,786 – 0,864] |
| Por clúster (pares inducidos) | 0,970 [0,864 – 1,000] | 0,851 [0,790 – 0,903] | 0,907 [0,845 – 0,946] |

- **Personas reconstruidas exactamente:** 73 de 100 (73 % [64 % – 81 %]); 129 clústeres
  predichos frente a 100 personas.
- **Recall del bloqueo:** 90,8 % de los 808 pares verdaderos de prueba llegan a compararse
  (1.262 comparaciones).
- **Aparecen uniones erróneas que desarrollo no mostraba.** Un solo par falso por encima del
  umbral une dos clústeres y deja 21 pares de registros juntos por error. Es el efecto
  transitivo que motivó elegir el umbral por clúster, y es la captura de Cluster Studio de
  abajo. El intervalo de precisión por clúster (0,864 – 1,000) refleja que con 100 personas un
  solo error así pesa mucho.

Métricas completas: [docs/resultados/metricas.json](docs/resultados/metricas.json).

### Desarrollo, prueba y referencia

| Conjunto | Umbral | Precisión por clúster | Recall por clúster | Personas exactas |
|---|---|---|---|---|
| **Prueba (métrica principal)** | 0,83 | **0,970** | **0,851** | **73 %** |
| Desarrollo (donde se eligió todo) | 0,83 | 1,000 | 0,930 | 84 % |
| Todo el dataset (solo referencia, optimista) | 0,84 | 1,000 | 0,903 | 81 % |

La fila de referencia repite el mismo procedimiento (selección de bloqueo, entrenamiento y
umbral) sobre las 251 personas y mide sobre esas mismas personas, así que **es optimista**: no
hay datos que el procedimiento no haya visto. Desarrollo también lo es, por la misma razón. La
diferencia con prueba (recall por clúster 0,93 → 0,85 y la primera unión errónea) es el tamaño
de ese optimismo.

> **Historia del hito.** En la primera versión de este hito, las 10 reglas de bloqueo y el
> umbral de 0,84 se eligieron mirando todo el dataset, y sus métricas (precisión 1,000 y
> recall 0,904 por clúster, 81,7 % de personas exactas) se midieron sobre los mismos datos.
> Eran optimistas. Hoy la selección es automática y usa solo desarrollo; la versión anterior
> queda en el historial de git.

### Bloqueo aproximado (elegido en desarrollo)

Con solo reglas exactas, el 18,6 % de los pares verdaderos de desarrollo nunca se compara
porque no comparte ningún campo idéntico (por ejemplo, un apellido mal escrito y una fecha con
un dígito cambiado, con el correo vacío). Hay 8 reglas aproximadas candidatas: Soundex y
Metaphone del apellido, Metaphone y primeras 3 letras del nombre (fonética con
[jellyfish](https://github.com/jamesturk/jellyfish)), año de nacimiento + inicial del apellido
o del nombre, primeros 4 caracteres del correo, y ciudad + año de nacimiento.

La selección es voraz: en cada paso se agrega la candidata que más pares verdaderos nuevos
cubre en desarrollo, y se para cuando la mejor suma menos de 0,5 puntos de recall del bloqueo
([seleccion_bloqueos.csv](docs/resultados/seleccion_bloqueos.csv)):

| Paso | Regla agregada | Comparaciones | Recall del bloqueo |
|---|---|---|---|
| 0 | Exactas | 1.771 | 0,814 |
| 1 | Primeros 4 caracteres del correo | 2.028 | 0,883 |
| 2 | Soundex del apellido | 2.436 | 0,907 |
| 3 | Ciudad + año de nacimiento | 2.544 | 0,917 |

Con las 12 reglas el recall del bloqueo en desarrollo llega a 0,930, pero con 3.547
comparaciones y el mismo recall por clúster (0,930). La medición con el modelo entrenado
para cada combinación está en
[comparacion_bloqueos.csv](docs/resultados/comparacion_bloqueos.csv); ninguna bajó la
precisión en desarrollo.

### Umbral por costo (elegido en desarrollo)

Elegir el umbral es una decisión de negocio. En banca, **unir por error a dos clientes
distintos** (falso positivo) mezcla sus productos, datos de contacto y riesgo, y es mucho más
grave que **dejar un duplicado sin unir** (falso negativo), que se puede corregir después. Por
eso se asigna un costo de 10 a cada falso positivo y de 1 a cada falso negativo (ambos
configurables con `--costo-fp` y `--costo-fn`) y se busca, en desarrollo, el umbral que
minimiza `10 × FP + 1 × FN`.

| Criterio (en desarrollo) | Umbral | Precisión por clúster | Recall por clúster | Costo por clúster |
|---|---|---|---|---|
| Fijo | 0,90 | 1,000 | 0,902 | 120 |
| Mejor F1 por par | 0,11 | 0,724 | 0,975 | 4.571 |
| Menor costo por par | 0,82 | 1,000 | 0,930 | 86 |
| **Menor costo por clúster (en uso)** | **0,83** | **1,000** | **0,930** | **86** |

**Se usa el de menor costo por clúster** porque la decisión que de verdad une clientes es el
clúster, no el par. La agrupación es transitiva: si A se parece a B y B a C, A y C quedan
juntos aunque no se parezcan, así que unos pocos falsos positivos por par se multiplican al
agrupar (con el de mejor F1 por par, 454 pares de registros quedan juntos por error). En este
desarrollo los umbrales de menor costo por par y por clúster casi coinciden; cuando hay
empate en costo se elige el umbral más alto, que es el más conservador.

![Costo según el umbral (desarrollo)](docs/resultados/costo_umbral.png)

![Precisión, recall y F1 por clúster según el umbral (desarrollo)](docs/resultados/curva_umbral_clusters.png)

### Cascada por par (prueba)

Cómo cada campo suma o resta evidencia para un par. El tablero interactivo incluye ejemplos de
acierto, falso positivo y falso negativo en prueba.

![Gráfico de cascada de Splink](docs/resultados/cascada.png)

### Cluster Studio (prueba)

Grafo de cada clúster predicho en prueba, con sus registros y pares puntuados, priorizando los
que tienen errores. La captura muestra el clúster que mezcla dos personas: los 7 registros
109–115 y los 3 registros 843–845 quedan juntos por un solo par por encima del umbral
(109–844, probabilidad 0,851 frente al umbral de 0,83), lo que
induce los 7 × 3 = 21 pares falsos. Los enlaces en rojo son pares con baja probabilidad que el
tablero también dibuja.

![Cluster Studio de Splink](docs/resultados/cluster_studio.png)

### Tableros publicados

Cascada, Cluster Studio y comparison viewer son de prueba; parámetros, pesos y curvas son del
modelo y la selección hechos en desarrollo.

- [Cascada por par](https://stous1.github.io/identity-resolution/resultados/cascada.html)
- [Cluster Studio](https://stous1.github.io/identity-resolution/resultados/cluster_studio.html)
- [Comparison viewer](https://stous1.github.io/identity-resolution/resultados/comparison_viewer.html)
- [Parámetros m/u](https://stous1.github.io/identity-resolution/resultados/parametros_mu.html)
  y [pesos de coincidencia](https://stous1.github.io/identity-resolution/resultados/pesos.html)
- Curvas por umbral: [por par](https://stous1.github.io/identity-resolution/resultados/curva_umbral.html),
  [por clúster](https://stous1.github.io/identity-resolution/resultados/curva_umbral_clusters.html)
  y [costo](https://stous1.github.io/identity-resolution/resultados/costo_umbral.html)

## Cómo correrlo

Requiere [uv](https://docs.astral.sh/uv/). uv instala Python 3.11 si hace falta.

```bash
uv sync                                       # entorno y dependencias
uv run playwright install chromium            # una sola vez, para las capturas PNG
uv run pytest                                 # pruebas (sin internet)
uv run python scripts/hito1_fake1000.py       # hito 1 completo -> reports/ (~1,5 min)
uv run python scripts/publicar_resultados.py  # copia los resultados a docs/resultados/
```

La primera ejecución del hito descarga fake_1000 y lo guarda en `data/raw/`.

## Estructura

```
src/identidades/   datos, modelo, bloqueo, evaluación, tableros y flujo del hito
scripts/           puntos de entrada
tests/             pruebas con pytest
notebooks/         solo exploración
docs/              descripción del caso y GitHub Pages (docs/resultados/)
data/, reports/    datos y salidas de trabajo (no versionados)
```

## Regla de datos

Este repositorio **nunca usa datos reales de clientes**. Solo datasets públicos de
demostración (Splink, FEBRL) o datos sintéticos generados con Faker.
