# Resolución de identidades con Splink

Caso de uso 1 de un portafolio de ciencia de datos y agentes aplicado a banca: **calidad del
dato y resolución de identidades**.

**Tableros interactivos:** [stous1.github.io/identity-resolution](https://stous1.github.io/identity-resolution/)

| Hito | Datos | Resultado principal (prueba) |
|---|---|---|
| [1. fake_1000](#hito-1-fake_1000-de-punta-a-punta) | Demo de Splink, 251 personas | Precisión 0,970 y recall 0,851 por clúster |
| [2. Colombia](#hito-2-clientes-sintéticos-colombianos-y-estandarización) | Sintéticos es_CO, 2.000 personas | Prueba normal: precisión 1,000 y recall 0,998 por clúster. **[Prueba ciega](#validación-prueba-ciega-y-febrl3): precisión 0,997 y recall 0,636** |

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

## Hito 2: clientes sintéticos colombianos y estandarización

**Tableros:** [stous1.github.io/identity-resolution/hito2.html](https://stous1.github.io/identity-resolution/hito2.html)

### Datos sintéticos

`identidades.sinteticos` genera, con Faker `es_CO` y semilla fija, 2.000 personas y 4.851
registros ([muestra](docs/resultados/hito2/muestra_registros.csv)):

- **Personas:** CC o CE, nombres simples y compuestos (40 %), dos apellidos (85 %) o uno,
  fecha de nacimiento, celular de 10 dígitos que empieza por 3, correo, dirección colombiana
  ("Cra 45 # 10-20", "Calle 10 Sur # 43A-15") y ciudad con su departamento.
- **Registros:** de 1 a 6 por persona, con errores a tasas configurables (`TasasError`):
  dígitos transpuestos, faltantes o errados en el documento, documento con puntos o vacío,
  errores de digitación, tildes quitadas o puestas, nombres en otro orden, segundo apellido
  omitido, otras abreviaturas de dirección (Cra, Carrera, KR, Cl, Calle, No., N°), celular en
  otro formato, teléfono o correo cambiados con el tiempo, y fechas con día y mes
  intercambiados.
- **Familiares:** una cuarta parte de las personas son hermanos o padres e hijos de otra.
  Comparten apellidos y dirección, y a veces el teléfono: es la fuente típica de falsos
  positivos.
- **Relleno compartido** por personas distintas, para el hito 3: teléfonos como 3000000000,
  correos genéricos (notiene@gmail.com) y direcciones vagas ("CENTRO").
- La columna `cluster` es la verdad (el id de la persona).

### Estandarización

`identidades.estandarizacion`, con una prueba por regla:

- **Nombres y apellidos:** mayúsculas, columna auxiliar sin tildes (la Ñ pasa a N), y
  separación de compuestos respetando partículas ("MARÍA DE LOS ÁNGELES", "DE LA HOZ").
- **Documento:** solo dígitos. **Celular:** 10 dígitos que empiezan por 3, sin el
  indicativo 57. **Correo:** minúsculas y validación.
- **Dirección:** tipo de vía, número, cuadrante, placa y consecutivo, con forma canónica:
  "Cra 45 No. 10 - 20" y "KR 45 10 20" quedan "KR 45 # 10-20".

### Modelo

El mismo esquema de evaluación del hito 1: bloqueo y umbral elegidos en desarrollo (1.200
personas, 2.920 registros) y métricas en prueba (800 personas, 1.931 registros) con
intervalos del 95 % por bootstrap de personas. Comparaciones:

- **Documento por niveles:** exacto, un dígito distinto, dos dígitos transpuestos, un dígito
  de más o de menos.
- **Nombres:** iguales, los mismos en otro orden, mismo primer nombre o parecidos.
- **Primer y segundo apellido** (Jaro-Winkler), fecha de nacimiento, celular, correo,
  dirección (igual, misma vía, número y placa, o parecida) y ciudad. Celular, correo y
  dirección llevan ajuste por frecuencia, que le baja el peso a los datos de relleno.

Para medir cuánto aporta la estandarización se entrena **el mismo modelo** dos veces: con
los datos estandarizados y con los textos tal cual (solo partidos por espacios). Cada
variante elige su bloqueo y su umbral en desarrollo.

### Resultados en prueba

| Variante | Umbral | Precisión por clúster | Recall por clúster | Personas exactas | Recall por par |
|---|---|---|---|---|---|
| **Estandarizado** | 0,999999 | **1,000** [1,000 – 1,000] | **0,998** [0,993 – 1,000] | **99,8 %** [99,4 – 100] | 0,994 [0,989 – 0,998] |
| Sin estandarizar | 0,98 | 0,989 [0,960 – 1,000] | 0,983 [0,975 – 0,990] | 96,1 % [94,8 – 97,4] | 0,907 [0,893 – 0,921] |

**Aporte de la estandarización** (diferencia pareada en prueba, estandarizado − sin
estandarizar):

| Métrica | Diferencia | IC 95 % | ¿Significativa? |
|---|---|---|---|
| Recall por clúster | +0,015 | [+0,006, +0,024] | Sí |
| Personas exactas | +3,6 puntos | [+2,4, +5,0] | Sí |
| Recall por par | +0,087 | [+0,073, +0,102] | Sí |
| Precisión por clúster | +0,011 | [0,000, +0,040] | No |

Sin estandarizar, el bloqueo exacto solo cubre el 82 % de los pares verdaderos en desarrollo
(frente al 99 % estandarizado), porque "1.023.456" y "1023456", o "+57 300…" y "300…", ya
no coinciden. Además, 24 pares de registros de personas distintas quedan unidos por error.

![Aporte de la estandarización](docs/resultados/hito2/estandarizacion.png)

### Equidad

Precisión, recall y personas reconstruidas exactamente en prueba, por clúster, según
atributos verdaderos de la persona. Las diferencias son pareadas (mismas réplicas del
bootstrap) y se consideran significativas si su intervalo no incluye el cero.

| Grupo (personas en prueba) | Recall, estandarizado | Exactas, estandarizado | Recall, sin estandarizar | Exactas, sin estandarizar |
|---|---|---|---|---|
| Nombre simple (457) | 0,999 | 99,8 % | 0,986 | 96,9 % |
| Nombre compuesto (343) | 0,996 | 99,7 % | 0,979 | 95,0 % |
| Dos apellidos (667) | 0,997 | 99,7 % | 0,982 | 96,1 % |
| Un apellido (133) | 1,000 | 100 % | 0,987 | 96,2 % |
| Con tilde o ñ (548) | 0,997 | 99,8 % | 0,985 | 96,5 % |
| Sin tilde (252) | 0,999 | 99,6 % | 0,981 | 95,2 % |

- **Con estandarización, el modelo no falla más con ningún grupo:** ninguna diferencia es
  significativa y la precisión es 1,000 en todos.
- **Sin estandarizar,** las personas con nombre compuesto quedan reconstruidas exactamente
  un poco menos (95,0 % frente a 96,9 %), pero la diferencia no es significativa
  (+1,9 puntos, IC [−0,8, +4,7]). Tampoco lo son las demás.
- Ojo: el generador aplica las mismas tasas de error a todos, así que los grupos solo
  difieren en la estructura del nombre. Con datos reales, donde la calidad de captura
  puede variar entre poblaciones, este análisis es más necesario.

![Equidad por grupo](docs/resultados/hito2/equidad.png)

### Casos difíciles: familiares con el mismo nombre

Los errores que quedan vienen de familiares que viven juntos. En prueba, el par más difícil
son dos hermanas que se llaman igual (MARÍA ZAPATA ROMERO, nacidas en 1975 y 2006): misma
dirección (factor ×647), mismo nombre (×263) y mismos apellidos superan la evidencia en
contra del documento y la fecha, y el par queda con peso 18,0 (probabilidad 0,999996), justo
por debajo del umbral. La suposición de independencia entre campos de Fellegi-Sunter no se
cumple dentro de un hogar. En desarrollo, el umbral de menor costo deja todavía 4 pares de
ese tipo. Son los casos para el agente de la zona gris (hito 4).

### Limitaciones

- Los datos son sintéticos y el generador y la estandarización los escribió la misma
  persona: la estandarización conoce los errores que se inyectaron. Las métricas son una
  cota optimista; la cifra honesta es la de la
  [prueba ciega](#validación-prueba-ciega-y-febrl3).
- El bloqueo elegido en desarrollo para la variante estandarizada agrega solo
  `domicilio_clave` (vía, número y placa) a las reglas exactas.
- [Comparación de bloqueos](docs/resultados/hito2/comparacion_bloqueos.csv) y
  [selección](docs/resultados/hito2/seleccion_bloqueos.csv) en desarrollo.

### Validación: prueba ciega y FEBRL3

Las métricas del hito 2 tienen un problema de circularidad: el generador de errores y la
estandarización los escribió la misma persona, así que la estandarización ya "conoce" los
errores que va a ver. Para tener una cifra honesta:

1. **Se congeló el modelo** (estandarización, esquema y parámetros entrenados) en el tag
   `hito2-congelado`, con su umbral de 0,999999.
2. **Un subagente que no leyó la estandarización ni el modelo** escribió un generador de
   errores nuevo ([`errores_ciegos.py`](src/identidades/errores_ciegos.py)) con errores no
   contemplados: más tipos y abreviaturas de vía (Ak, Ac, Avda, Transv., Km), direcciones
   rurales (veredas, fincas, corregimientos), apodos (Pepe, Pacho, Chucho, Mafe...), errores
   de lectura de documentos (O por 0, l por 1, S por 5, B por 8), espacios y puntuación
   irregulares, fechas en otros formatos ("07 de marzo de 1985", 07-MAR-1985), apellido de
   casada ("Figueroa de Ortiz"), campos cruzados, fijos de 7 dígitos, dominios de correo mal
   escritos, ciudades abreviadas (Bta, B/quilla) y texto mal codificado ("JosÃ©").
3. **El modelo congelado se aplicó sin ajustar nada** a 2.000 personas nuevas (6.032
   registros, otra semilla). Solo se vuelve a estimar λ, como en cualquier lote nuevo, con
   reglas que no usan etiquetas.
4. **Validación externa:** el mismo procedimiento del hito 2 (bloqueo y umbral elegidos en
   desarrollo, métricas en prueba) sobre FEBRL3, un generador de registros con errores
   ajeno a este proyecto (5.000 registros de 2.000 personas).

**Las tres cifras** (por clúster, en prueba, IC 95 % por bootstrap de personas):

| Evaluación | Precisión | Recall | F1 | Personas exactas |
|---|---|---|---|---|
| Prueba normal del hito 2 (800 personas) | 1,000 [1,000 – 1,000] | 0,998 [0,993 – 1,000] | 0,999 [0,997 – 1,000] | 99,8 % [99,4 – 100] |
| **Prueba ciega (2.000 personas)** | **0,997** [0,987 – 1,000] | **0,636** [0,616 – 0,657] | **0,777** [0,762 – 0,792] | **60,2 %** [58,1 – 62,3] |
| FEBRL3 (800 personas) | 1,000 [1,000 – 1,000] | 0,997 [0,992 – 1,000] | 0,998 [0,996 – 1,000] | 99,6 % [99,1 – 100] |

![Prueba normal, prueba ciega y FEBRL3](docs/resultados/validacion/tres_cifras.png)

**Por qué la prueba ciega es la cifra más honesta.** En la prueba normal, la separación
desarrollo/prueba evita que el modelo vea a las mismas personas, pero no evita que el
diseño (qué normalizar, qué comparaciones usar) se haya hecho a la medida de los errores
del generador: ambos salieron de la misma cabeza. FEBRL es externo, pero el procedimiento
se ajustó a FEBRL (bloqueo, entrenamiento y umbral sobre sus datos), y sus errores son
sencillos (digitación y valores faltantes sobre campos bien separados). La prueba ciega es
la única donde ni el diseño ni los parámetros pudieron adaptarse a los datos evaluados, que
es lo que le pasa a un modelo en producción cuando llega un canal o un sistema nuevo.

**Lo que muestra:**

- **La precisión aguanta:** 0,997. El modelo casi nunca une personas distintas, que en
  banca es el error caro.
- **El recall se cae:** de 0,998 a 0,636. Una de cada tres duplicaciones queda sin unir, y
  solo el 60 % de las personas queda reconstruida exactamente (3.128 clústeres para 2.000
  personas).
- **No es solo el umbral:** a umbral 0,5 el recall sube a 0,807, pero la precisión cae a
  0,803. Los puntajes ya no separan bien; la solución es mejorar la estandarización y las
  comparaciones, no mover el umbral. Este diagnóstico no se usa para la cifra principal:
  elegir otro umbral mirando estos datos sería ajustar el modelo.
- **Dónde falla** (personas reconstruidas exactamente, diagnóstico por tipo de error):
  nombres en otro campo 29,7 % (frente a 62,8 %), documento alterado 45,4 % (frente a
  63,4 %) y celular cambiado por un fijo 49,1 % (frente a 61,5 %). Todas las diferencias
  son significativas.
- **Primer hallazgo:** con el tag original, el modelo **se caía** con 66 registros sin
  apellidos (pandas convierte el `None` en `NaN` y la estandarización no lo esperaba). Se
  corrigió la robustez sin cambiar ningún resultado del hito 2 (métricas idénticas) y se
  congeló de nuevo como `hito2-congelado-r1`. La validación verifica contra ese tag.

**Equidad en la prueba ciega** (personas reconstruidas exactamente, por clúster):

| Grupo | Exactas | Frente a | Diferencia | ¿Significativa? |
|---|---|---|---|---|
| Apellido de casada (136) | 41,2 % | 61,5 % sin él | −20,4 puntos [−29,1, −11,4] | **Sí** |
| Con apodo (337) | 49,3 % | 62,4 % sin apodo | −13,1 puntos [−19,0, −7,4] | **Sí** |
| Nombre compuesto (788) | 61,8 % | 59,1 % simple | +2,7 [−1,3, +7,1] | No |
| Un apellido (301) | 59,1 % | 60,3 % con dos | −1,2 [−7,0, +4,5] | No |
| Sin tilde (634) | 59,6 % | 60,4 % con tilde | −0,8 [−5,6, +3,9] | No |
| Dirección rural (135) | 59,3 % | 60,2 % urbana | −1,0 [−9,9, +7,5] | No |

El hallazgo de equidad más importante: **el modelo falla más con mujeres que usan apellido
de casada**. La estandarización separa "Ramírez de Vargas" en primer apellido RAMIREZ y
segundo apellido DE VARGAS, que choca con el segundo apellido verdadero (OSORIO): el campo
resta evidencia en vez de quedar neutral, y esos registros quedan sin unir. Con los apodos
pasa algo parecido: "Pepe" no se reconoce como "José". La prueba normal no lo podía mostrar, porque su
generador no producía esos casos. La precisión no difiere entre grupos.

![Equidad en la prueba ciega](docs/resultados/validacion/ciega_equidad.png)

Métricas completas en
[docs/resultados/validacion/metricas.json](docs/resultados/validacion/metricas.json) y una
[muestra de registros ciegos](docs/resultados/validacion/ciega_muestra_registros.csv).

## Cómo correrlo

Requiere [uv](https://docs.astral.sh/uv/). uv instala Python 3.11 si hace falta.

```bash
uv sync                                       # entorno y dependencias
uv run playwright install chromium            # una sola vez, para las capturas PNG
uv run pytest                                 # pruebas (sin internet)
uv run python scripts/hito1_fake1000.py       # hito 1 completo -> reports/ (~1,5 min)
uv run python scripts/hito2_colombia.py       # hito 2 completo -> reports/hito2/ (~2,5 min)
uv run python scripts/validacion.py           # prueba ciega + FEBRL3 -> reports/validacion/
uv run python scripts/publicar_resultados.py --hito 1   # o 2, o validacion: a docs/resultados/
```

La primera ejecución del hito descarga fake_1000 y lo guarda en `data/raw/`.

## Estructura

```
src/identidades/   datos, modelo, bloqueo, evaluación, tableros y flujo del hito 1;
                   sinteticos, estandarizacion, modelo_co y flujo_hito2 (hito 2);
                   errores_ciegos, modelo_febrl y flujo_validacion (validación)
scripts/           puntos de entrada
tests/             pruebas con pytest
notebooks/         solo exploración
docs/              descripción del caso y GitHub Pages (docs/resultados/)
data/, reports/    datos y salidas de trabajo (no versionados)
```

## Regla de datos

Este repositorio **nunca usa datos reales de clientes**. Solo datasets públicos de
demostración (Splink, FEBRL) o datos sintéticos generados con Faker.
