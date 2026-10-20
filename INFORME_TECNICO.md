# Informe técnico: resolución de identidades con Splink

> Detalle completo, hito por hito, con todas las cifras y sus correcciones. La puerta de entrada corta es el [README](README.md); los tableros están en [GitHub Pages](https://stous1.github.io/identity-resolution/).

[![CI](https://github.com/stous1/identity-resolution/actions/workflows/ci.yml/badge.svg)](https://github.com/stous1/identity-resolution/actions/workflows/ci.yml)

Caso de uso 1 de un portafolio de ciencia de datos y agentes aplicado a banca: **calidad del
dato y resolución de identidades**.

**Tableros interactivos:** [stous1.github.io/identity-resolution](https://stous1.github.io/identity-resolution/)

| Hito | Datos | Resultado principal (prueba) |
|---|---|---|
| [1. fake_1000](#hito-1-fake_1000-de-punta-a-punta) | Demo de Splink, 251 personas | Precisión 0,970 y recall 0,851 por clúster |
| [2. Colombia](#hito-2-clientes-sintéticos-colombianos-y-estandarización) | Sintéticos es_CO, 2.000 personas | Prueba normal: precisión 1,000 y recall 0,998 por clúster. **[Prueba ciega](#validación-prueba-ciega-y-febrl3): precisión 0,989 y recall 0,635**, sobre todo por dos vetos aprendidos (auditoría) |
| [2b. Corrección](#hito-2b-corregir-y-volver-a-medir-a-ciegas) | Ciega 1 como desarrollo; ciega 2 nueva | **Ciega 2: precisión 1,000 y recall 1,000 por clúster** (v1 en la misma ciega 2: 1,000 y 0,914) |
| [3. Registro de oro y grafo](#hito-3-registro-de-oro-grafo-de-identidad-compartida-y-puentes) | Escenario con historia, metadatos y patrones sospechosos | En 8 pares de semillas: registro de oro a 4,1 ± 0,4 puntos del techo (peor campo); grafo con exactitud 98,3 % ± 0,6; puentes que evitan en promedio 35 % de las mezclas (entre 28 % y 45 % según la semilla) |
| [5. Tiempo real y escala](#hito-5-vinculación-en-tiempo-real-y-escala) | Base de registros de oro; 100 mil y 1 millón de registros | "¿Ya es cliente?": precisión 1,000 y recall 0,992 sin falsas alarmas (con los datos anteriores, una falsa alarma dejaba la precisión en **0,909 con 1 %** de clientes); 1 millón de registros en DuckDB en 155 s |
| [6. Correcciones post-auditoría](#hito-6-correcciones-post-auditoría) | Generador con mudanzas; **prueba ciega 3** nueva | Modelo v3 sin vetos extremos. **Ciega 3: v3 precisión 0,996 y recall 0,955** (v2: 0,996 y 0,972; v1: 0,995 y 0,715). Splink aporta +0,055 de F1 global sobre la mejor regla; la ganancia se concentra donde el documento falla |
| [v1.1. Realidad residencial](#v11-realidad-residencial-y-familiar-colombiana) | Predios, hogares y familias; **prueba ciega 4** nueva | **Ciega 4: v4 F1 0,994 frente a 0,987 del v3** (+0,007, IC 0,004 a 0,011), sin brechas de equidad significativas. Grafo residencial: personas inocentes marcadas 1,6 % frente a 36,7 %, pero detecta menos patrones sospechosos (66,7 % frente a 81,6 % de sus personas) |

**Cifras de la v1.1.1.** Hasta la v1.1, los generadores dependían de la fecha del día
(Faker) y el mismo generador con la misma semilla daba datos distintos otro día. Desde la
v1.1.1 usan una fecha fija y todas las evaluaciones con modelos congelados se volvieron a
correr. Las tablas principales de cada hito tienen las cifras nuevas; las correcciones de
la auditoría que citan cifras anteriores las conservan como registro. Lo que cambió está en
[v1.1.1](#v111-reproducibilidad-demo-con-el-v4-y-ficha-de-cliente-único).

**Auditoría independiente:** [audit/INFORME.md](audit/INFORME.md) ·
[qué encontró y qué cambió](#qué-encontró-la-auditoría-y-qué-cambió)

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
| **Prueba ciega (2.000 personas)** | **0,989** [0,963 – 1,000] | **0,635** [0,614 – 0,655] | **0,774** [0,755 – 0,789] | **60,5 %** |
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

- **La precisión aguanta:** 0,989 (0,997 con los datos anteriores a la v1.1.1). El modelo casi nunca une personas distintas, que en
  banca es el error caro. Pero *corrección de la auditoría:* en esta misma prueba la regla
  de una línea "mismo documento" es mejor en todo lo demás (F1 0,931 frente a 0,777).
- **El recall se cae:** de 0,998 a 0,635. Una de cada tres duplicaciones queda sin unir, y
  solo el 60 % de las personas queda reconstruida exactamente (3.128 clústeres para 2.000
  personas).
- **No es solo el umbral:** a umbral 0,5 el recall sube a 0,807, pero la precisión cae a
  0,803. Los puntajes ya no separan bien; la solución es mejorar la estandarización y las
  comparaciones, no mover el umbral. Este diagnóstico no se usa para la cifra principal:
  elegir otro umbral mirando estos datos sería ajustar el modelo.
- **Dónde falla** (personas reconstruidas exactamente, diagnóstico por tipo de error):
  nombres en otro campo 29,7 % (frente a 62,8 %), documento alterado 45,4 % (frente a
  63,4 %) y celular cambiado por un fijo 49,1 % (frente a 61,5 %). Todas las diferencias
  son significativas, **pero no son la causa principal.** *Corrección de la auditoría
  ([§5](audit/INFORME.md#5-ablación-a5_ablacionpy)):* el modelo v1 aprendió dos **vetos**
  de −48 bits (municipio distinto) y −43 bits (dirección parecida pero no igual), porque el
  generador del hito 2 nunca cambia la ciudad ni la dirección de una persona. Al
  neutralizarlos, el recall en esta prueba sube de 0,636 a **0,943** con precisión 1,000.
  Los nombres cruzados, el documento y los fijos son causas secundarias. El hito 6 lo
  corrige en el origen (mudanzas en el generador y un piso a los pesos negativos).
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

~~El hallazgo de equidad más importante: el modelo falla más con mujeres que usan apellido
de casada.~~ **Corrección de la auditoría:** esta brecha era casi toda una interacción con
los vetos de municipio y dirección. Sin ellos baja de −20,4 a **−3,6 puntos [−9,0, +1,1] y
deja de ser significativa**. El choque del apellido de casada con el segundo apellido
existe, pero por sí solo pesa poco. La brecha de los **apodos sí es real** (−11,5 puntos sin
los vetos, significativa): "Pepe" no se reconoce como "José". Sobre el género: en la prueba
ciega 3 del [hito 6](#hito-6-correcciones-post-auditoría), con el v3 **no se detecta brecha**
entre mujeres y hombres (−1,4 puntos [−3,4, +0,7]); el intervalo admite una brecha de hasta
unos 3 puntos. Con el v2, en esos mismos datos, sí hay una pequeña y significativa (−2,2
[−4,2, −0,4]). La precisión no difiere entre grupos.

![Equidad en la prueba ciega](docs/resultados/validacion/ciega_equidad.png)

Métricas completas en
[docs/resultados/validacion/metricas.json](docs/resultados/validacion/metricas.json) y una
[muestra de registros ciegos](docs/resultados/validacion/ciega_muestra_registros.csv).

## Hito 2b: corregir y volver a medir a ciegas

La prueba ciega 1 dejó de ser ciega en cuanto se vieron sus errores, así que pasó a ser
**desarrollo**. Con ella se corrigió el modelo, se congeló de nuevo y se midió con una
**prueba ciega 2** que nadie había visto.

**Correcciones** ([`estandarizacion_v2.py`](src/identidades/estandarizacion_v2.py) y
[`modelo_co_v2.py`](src/identidades/modelo_co_v2.py); la versión 1 no se modifica, para que
sus cifras sigan siendo reproducibles), en orden de impacto:

1. **Apellido de casada:** "Arango de Ramírez" se separa en apellido ARANGO y apellido de
   casada RAMIREZ, que es una comparación propia. Si un registro lo tiene y el otro no, es
   neutral; ya no choca con el segundo apellido.
2. **Apodos:** un diccionario de 133 apodos y 23 formas abreviadas colombianas (Pepe,
   Pacho, Toño, Betty, Mafe, Juanda...) que pasan a su nombre formal.
3. **Nombres en otro campo:** niveles para nombre y apellido intercambiados, y para "el
   primer nombre de uno y otra palabra aparecen en cualquier campo de nombre del otro". La
   primera versión de este nivel (dos palabras en común) unía hermanos, que comparten los
   dos apellidos, y se endureció en desarrollo.
4. **Documento:** corrección de errores de lectura (O por 0, l por 1...) y un nivel de
   hasta dos ediciones.
5. **Teléfonos:** cualquier teléfono contra cualquier teléfono. Si uno de los dos solo tiene
   un fijo, el nivel es aparte y no cuenta como teléfonos distintos. Los números que
   aparecen en más registros de los que puede tener una persona (relleno) se ignoran.
6. **Extras,** fuera de la lista original: fechas en otros formatos ("20 de octubre de
   1999", "12/10/88", "09-ABR-1998") normalizadas a ISO, que antes perdían la evidencia de
   la fecha, y texto mal codificado ("RamÃ­rez").

**Desarrollo:** el del hito 2 (1.200 personas) más toda la ciega 1 (2.000 personas). Ahí se
eligieron el bloqueo y el umbral (0,9999), y el modelo se congeló en el tag
`hito2b-congelado`. Después, **un subagente nuevo**, sin acceso a la estandarización (v1 ni
v2), los esquemas, los generadores anteriores ni sus resultados, escribió el
[generador de la ciega 2](src/identidades/errores_ciegos_2.py): 2.000 personas nuevas, otra
semilla, su propio diccionario de apodos y sus propias formas de apellido de casada, y 17
tipos de error nuevos (grafías como Brayan, Jhon o Leidy; "María del Carmen"; iniciales;
títulos; apellidos con guion; dígito de verificación; tarjeta de identidad antigua;
pasaporte o PPT en vez de cédula de extranjería; correo corporativo; vías con nombre
propio; dirección anterior; año de dos dígitos...).

### Evolución (por clúster, IC 95 % por bootstrap de personas)

| Evaluación | Precisión | Recall | Personas exactas |
|---|---|---|---|
| Prueba normal · modelo v1 | 1,000 [1,000 – 1,000] | 0,998 [0,993 – 1,000] | 99,8 % |
| Prueba normal · modelo v2 | 1,000 [1,000 – 1,000] | 0,993 [0,986 – 0,999] | 99,5 % |
| Ciega 1 · modelo v1 | 0,989 [0,963 – 1,000] | 0,635 [0,614 – 0,655] | 60,5 % |
| Ciega 1 · modelo v2 (*es desarrollo: optimista*) | 1,000 | 1,000 | 100 % |
| Ciega 2 · modelo v1 (control) | 1,000 [0,998 – 1,000] | 0,914 [0,901 – 0,927] | 90,9 % |
| **Ciega 2 · modelo v2** | **0,998** [0,994 – 1,000] | **1,000** [1,000 – 1,000] | **99,7 %** [99,5 – 99,9] |

![Evolución](docs/resultados/hito2b/evolucion.png)

**Cómo leer esta tabla.** La ciega 2 resultó **más fácil** que la ciega 1: el mismo modelo
v1, que en la ciega 1 tenía recall 0,635, en la ciega 2 llega a 0,914. Comparar "ciega 1 con
v1" contra "ciega 2 con v2" mezclaría la mejora del modelo con la diferencia entre
generadores. Por eso se aplicó también el modelo v1 congelado a la ciega 2 como control. La
comparación justa es sobre las mismas personas de la ciega 2 (diferencia pareada v2 − v1):

| Métrica (por clúster) | v2 − v1 en la ciega 2 | IC 95 % | ¿Significativa? |
|---|---|---|---|
| Recall | +0,080 | [+0,068, +0,093] | Sí |
| Personas exactas | +8,6 puntos | [+7,4, +9,8] | Sí |
| Precisión | +0,004 | [−0,003, +0,021] | No |

- **El modelo v2 mejora a ciegas:** recuperó todos los pares verdaderos de la ciega 2 sin
  perder precisión. *Matiz de la auditoría:* ese recall de 1,000 sale del umbral
  publicado; con cualquiera de 5 desarrollos repetidos queda en 0,998. Y en esta prueba
  Splink aporta poco sobre la regla "documento o nombre+fecha" (+0,010 de F1). Quedan 3 uniones erróneas (1.997 clústeres para 2.000 personas).
- **En la prueba normal empeora un poco:** el recall baja de 0,998 a 0,993 (15 pares
  faltantes en vez de 5). Los intervalos se solapan; es el costo de los niveles más
  tolerantes.

### Brecha de equidad: antes y después

Personas reconstruidas exactamente, por grupo:

| Grupo | Antes (ciega 1, v1) | Control (ciega 2, v1) | Después (ciega 2, v2) |
|---|---|---|---|
| Con apellido de casada | 41,2 % | 92,0 % | 100 % |
| Sin apellido de casada | 61,5 % | 91,0 % | 99,7 % |
| **Brecha** | **−20,4 puntos [−29,1, −11,4]** | +1,0 [−2,5, +4,4] | +0,3 [+0,1, +0,6] |
| Con apodo | 49,3 % | 90,8 % | 100 % |
| Sin apodo | 62,4 % | 91,1 % | 99,7 % |
| **Brecha** | **−13,1 puntos [−19,0, −7,4]** | −0,3 [−4,5, +3,8] | +0,3 [+0,1, +0,6] |

*Nota del hito 6:* la brecha "antes" de esta tabla está inflada por los vetos del v1 (ver
la corrección en la [validación](#validación-prueba-ciega-y-febrl3)). Y el v2 trae un veto
nuevo de −72,6 bits en el apellido de casada: dos registros de la misma mujer con apellidos
de casada distintos (divorcio, nuevo matrimonio) no se unirían nunca. La prueba ciega 3
lo mide.

**¿Se cerró la brecha?** En la ciega 2 no hay brecha en contra de las mujeres con apellido
de casada ni de las personas con apodo: con v2 quedan reconstruidas al 100 %, y el
"+0,3 puntos" a su favor no tiene peso práctico (sale de las 3 uniones erróneas, que cayeron
en personas de los otros grupos). Pero hay que ser honesto con lo que esto demuestra:

- **Con el control no aparece brecha tampoco con v1** (92,0 % frente a 91,0 %). Las formas de
  apellido de casada y los apodos del generador de la ciega 2 perjudican menos que los de la
  ciega 1, así que la ciega 2 no puede confirmar por sí sola que la corrección cerró la
  brecha que se vio en la ciega 1.
- **Lo que sí se puede afirmar:** la corrección elimina la brecha en los casos de la ciega 1
  (en desarrollo, optimista), y en datos que el modelo nunca vio no aparece ninguna brecha
  nueva. Para confirmar a ciegas la corrección del caso difícil haría falta una tercera
  prueba que incluya, a propósito, el apellido de casada en la posición del segundo apellido.

![Brecha de equidad](docs/resultados/hito2b/brecha_equidad.png)

Métricas completas en [docs/resultados/hito2b/metricas.json](docs/resultados/hito2b/metricas.json)
y [muestra de registros de la ciega 2](docs/resultados/hito2b/ciega2_muestra_registros.csv).

## Hito 3: registro de oro, grafo de identidad compartida y puentes

**Visualización:** [universo de registros en Cosmograph](https://stous1.github.io/identity-resolution/hito3_universo.html)

![Universo de registros en Cosmograph](docs/resultados/hito3/universo.png)

### Escenario

El generador del hito 2 no tiene historia en el tiempo ni datos sospechosos, y cambiarlo
alteraría los hitos anteriores. Por eso se creó un escenario aparte
([`escenario_hito3.py`](src/identidades/escenario_hito3.py)) sobre las mismas personas
sintéticas:

- **Historia:** el celular, el correo y el domicilio pueden cambiar en una fecha. El valor
  vigente (el último) es la verdad del registro de oro.
- **Metadatos por registro:** fecha de actualización, canal de origen (sucursal, app, web,
  call center, corresponsal) y si el dato fue validado. Los canales menos confiables y los
  datos sin validar tienen más errores.
- **Datos compartidos con verdad conocida:** relleno (3000000000, notiene@gmail.com,
  "CENTRO"), hogares (familiares con la misma dirección y a veces el mismo teléfono) y
  patrones sospechosos: anillos de 3 a 6 personas no relacionadas que en registros
  recientes, por canales digitales y sin validar, comparten un celular, un correo o una
  dirección; y suplantaciones (un registro con el documento de otra persona).

**Regla de evaluación:** todo lo que se elige (regla de supervivencia, umbrales del
clasificador, política de puentes) se elige en un escenario de **desarrollo** (semilla 3030)
y se mide una sola vez en otro de **prueba** (semilla 3131, 2.000 personas, 4.878
registros con la fecha fija de la v1.1.1). Los clientes salen del modelo v2 congelado, sin
ajustes (en prueba: precisión 0,998 y recall 0,999 por clúster).

### Registro de oro

Para cada cliente y cada campo sobrevive un valor según una regla: el **más reciente**, el
**validado** más reciente, el de la **fuente más confiable** o el **más frecuente**. Los
valores que el grafo clasifica como relleno no pueden sobrevivir. La regla de cada campo se
eligió en desarrollo:

| Campo | Regla (elegida en desarrollo) | Acierto en prueba (IC 95 %) | Techo alcanzable |
|---|---|---|---|
| Documento | Fuente más confiable | 96,0 % [95,0 – 96,8] | 97,8 % |
| Nombres | Más frecuente | 93,6 % [92,6 – 94,7] | 96,8 % |
| Apellidos | Más frecuente | 94,0 % [92,9 – 95,0] | 96,9 % |
| Fecha de nacimiento | Más reciente | 100 % | 100 % |
| Celular | Validado más reciente | 80,0 % [78,2 – 81,7] | 83,2 % |
| Correo | Validado más reciente | 83,5 % [81,7 – 85,0] | 86,2 % |
| Dirección | Fuente más confiable | 84,2 % [82,5 – 85,8] | 88,7 % |

El **techo alcanzable** es la fracción de clientes con el valor correcto en al menos uno de
sus registros: si alguien cambió de celular después de su última actualización, ningún
registro trae el número vigente y ninguna regla puede acertar. Las reglas elegidas quedan a
menos de 5 puntos de ese techo, y eso **se sostiene entre semillas**: con 8 pares de
escenarios, la peor brecha al techo es 4,1 ± 0,4 puntos (de 3,7 a 4,7). Lo que **no** es
robusto es qué regla gana: el documento sale "fuente más confiable" en 4 de 8 y "validado"
en 4; los nombres, "más frecuente" en 6 y "fuente más confiable" en 2; la dirección, "fuente
más confiable" en 4 y "más frecuente" en 4. Los apellidos ("más frecuente"), el correo y el
celular ("validado") salen igual en las 8. Ojo además (auditoría, M4): el orden de confiabilidad de los canales coincide con
el que usa el generador, así que el registro de oro es optimista por construcción. Usar siempre "el más reciente"
sería igual o peor en todos los campos: por ejemplo, documento 92,7 % y nombres 89,8 %.

![Registro de oro por regla](docs/resultados/hito3/registro_oro.png)

### Grafo de identidad compartida

Cada teléfono, correo, dirección o documento que comparten dos o más clientes distintos
forma una estrella. Se clasifica con reglas explicables, con umbrales elegidos en
desarrollo:

1. **Documento** compartido por clientes distintos → sospechoso (suplantación).
2. **Relleno** si el valor tiene forma genérica (dígitos repetidos o secuencias, correos
   como notiene@ o na@na.com, direcciones sin nomenclatura) o lo comparten más de 15
   clientes.
3. **Hogar** si al menos la mitad de los pares de clientes comparte apellido (tolerando
   errores de digitación).
4. **Sospechoso** en otro caso: personas sin relación que comparten un dato de contacto.

Con la semilla publicada, el 99,1 % de los 425 grupos de prueba queda bien clasificado
(376 de hogar, 36 sospechosos, 10 de relleno y 3 coincidencias; los 36 sospechosos, todos).
Con 8 pares de escenarios la exactitud es **98,3 % ± 0,6** (de 97,6 % a 99,1 %; antes de la v1.1.1, 98,6 % ± 0,8). Este resultado es optimista, por la misma
razón que en el hito 2: el escenario y el clasificador los escribió la misma persona, y en
este escenario los anillos no tienen apellidos en común con nadie. Con datos reales, un
anillo puede usar familiares o testaferros con apellidos parecidos.

### Puentes

Una arista es puente si al quitarla el clúster se parte en dos (métricas de grafo de
Splink). En un clúster de dos registros la única arista siempre es puente, así que no basta
con eso: la política mira además el peso del puente y el tamaño del lado más chico.

Semilla publicada (3030/3131):

| Umbral de operación | Política (elegida en desarrollo) | Clientes mezclados (prueba) | Pares unidos por error | Recall perdido |
|---|---|---|---|---|
| 0,9999 (congelado) | No cortar | 2 → 2 | 10 → 10 | 0 |
| 0,99 | Cortar puentes con peso < 25 | 4 → 3 | 15 → 14 | 0,04 % |
| 0,9 | Cortar puentes con peso < 25 | 10 → 6 | 43 → 29 | 0,04 % |

**Entre semillas** (8 pares de escenarios, v2 congelado; media ± DE y rango):

| Cifra | Semilla publicada | Media ± DE | Rango |
|---|---|---|---|
| Clientes mezclados al umbral congelado | 2 | 1,4 ± 0,7 | 0 – 2 |
| Clientes mezclados al umbral 0,9 | 10 | 18,9 ± 5,2 | 10 – 25 |
| Mezclas evitadas al cortar puentes (umbral 0,9) | 4 de 10 (40 %) | 35 % ± 7 % | 28 % – 45 % |

- **Al umbral congelado, el modelo v2 deja de 0 a 2 uniones erróneas** según la semilla
  (antes de la v1.1.1, de 0 a 4). Los puentes sirven sobre todo con un umbral más bajo:
  cortarlos evita en promedio **un tercio de las mezclas**. Con la semilla publicada,
  cortarlos pierde 0,04 % del recall; en las otras 7 no se midió. Las demás mezclas son clústeres densos, que no cuelgan
  de un solo enlace. Detalle en
  [hito3_semillas.json](docs/resultados/hito6/hito3_semillas.json).
- **Las uniones erróneas conocidas cuelgan de puentes:** el caso 109-844 del hito 1 es el
  segundo puente más débil de 35 (peso 2,5, une 3 registros), y las 3 uniones erróneas del
  modelo v2 en la prueba ciega 2 cuelgan cada una de un puente (pesos 13,8, 16,9 y 20,9).
  Como en desarrollo no había mezclas al umbral congelado, desarrollo no puede calibrar ahí
  una política. *Como diagnóstico* (sin usarlo para elegir nada), mandar a revisión los
  puentes de peso menor a 25 marcaría 6 clientes en la ciega 2 y atraparía las 3 uniones,
  y en los escenarios del hito 3 marcaría 1 o 2 casos.

### Cola de revisión para el hito 4

[`cola_revision.csv`](docs/resultados/hito3/cola_revision.csv) reúne los casos de prueba
para el agente: 6 uniones sostenidas por un puente débil (al umbral 0,9) y 37 grupos
sospechosos (12 documentos, 12 correos, 9 celulares y 4 direcciones compartidos), cada uno
con su evidencia.

Métricas completas en [docs/resultados/hito3/metricas.json](docs/resultados/hito3/metricas.json)
y comparación de políticas en
[politicas_puentes_desarrollo.csv](docs/resultados/hito3/politicas_puentes_desarrollo.csv).

### Visualización

La [página de Cosmograph](https://stous1.github.io/identity-resolution/hito3_universo.html)
muestra el escenario de prueba: 4.878 registros, los enlaces del modelo (fuertes sobre el
umbral congelado y débiles entre 0,9 y ese umbral), los puentes débiles en naranja y las
estrellas de datos compartidos (relleno en morado, hogares en verde, sospechosos en rojo).
Cosmograph tiene licencia CC-BY-NC-4.0: libre para uso no comercial, como este portafolio.

## Hito 5: vinculación en tiempo real y escala

**Página:** [hito 5 en GitHub Pages](https://stous1.github.io/identity-resolution/hito5.html) ·
[universo grande en Cosmograph](https://stous1.github.io/identity-resolution/hito5_universo.html)

### ¿Ya es cliente?

[`tiempo_real.py`](src/identidades/tiempo_real.py) compara un registro nuevo contra la base
de registros de oro con el modelo v2 congelado y decide **cliente** (probabilidad sobre el
umbral congelado 0,9999), **revisar** (entre 0,9 y el umbral) o **nuevo**, con el cliente
encontrado y el peso de cada campo. La probabilidad previa se fija en 1 / número de
clientes y los umbrales no se ajustan: las cifras son de prueba, medidas una vez.

Base de 1.351 clientes (3.000 personas sintéticas) y 2.000 consultas, 1.000 de clientes
existentes (con un registro apartado) y 1.000 de personas nuevas; un acierto exige el
cliente correcto. IC 95 % por bootstrap.

| Precisión | Recall | Cliente equivocado | Latencia mediana | p95 |
|---|---|---|---|---|
| 1,000 (1,000 – 1,000) | 0,992 (0,986 – 0,997) | 0 | 68 ms | 89 ms |

De las personas nuevas, 992 quedan como nuevas, 8 van a revisión y ninguna se confunde con
un cliente (con los datos anteriores a la v1.1.1, 1 se confundía). Splink genera el SQL una vez y luego solo se reejecuta en DuckDB (sin esto, ~280 ms).
`uv run python scripts/servicio_local.py` levanta el servicio local con FastAPI
(`POST /consultar`); no se publica ningún servicio. *Desde la v1.1.1, el servicio usa por
defecto el v4 con la zona gris por bandas de peso; `--modelo v3` usa el del hito 6 y
`--modelo v2` reproduce este.*

*Corrección de la auditoría (M5):* la precisión supone 50 % de consultas de clientes
existentes. Con los datos anteriores a la v1.1.1 (993 aciertos entre 1.000 existentes y 1
falsa alarma entre 1.000 nuevas), con 10 % de clientes habría sido **0,991** y con 1 %,
**0,909**. Con los datos nuevos no hubo falsas alarmas, así que la estimación es 1,000 con
cualquier mezcla; con 1.000 consultas nuevas, es una cifra frágil.

### Escala con DuckDB

[`escala.py`](src/identidades/escala.py) corre el esquema v2 completo sobre 100 mil y 1
millón de registros en una máquina (24 núcleos, 63 GB), sin Spark, cada tamaño en un proceso
propio. Memoria = pico del proceso durante cada etapa (los picos no se acumulan entre
etapas, como se decía antes).

| Registros | Preparación | Entrenamiento | Predicción | Agrupación | Memoria pico | Precisión | Recall |
|---|---|---|---|---|---|---|---|
| 99.837 | 10,2 s | 15,3 s | 1,2 s | 0,9 s | 1,5 GB | 0,981 | 0,997 |
| 996.688 | 102,8 s | 43,3 s | 2,4 s | 6,7 s | **9,1 GB** | 0,970 | 0,996 |

![Tiempo por etapa](docs/resultados/hito5/escala_tiempo.png)

- La preparación (estandarización en Python) es el cuello de botella: 103 de 155 s (v1.1.1,
  con la máquina ocupada por otras corridas; antes, 91 de 134 s).
- **La precisión baja con el tamaño porque el flujo reentrena en cada tamaño, no por
  homónimos** (auditoría, A2): todos los falsos positivos son familiares, y con los
  parámetros congelados la precisión queda plana. Ver
  [escala con el modelo congelado](#escala-con-el-modelo-congelado) en el hito 6.
- **5 millones no cabe en esta máquina:** con 1 millón el pico ya es de 9,1 GB y la corrida
  de 5 millones se detuvo por falta de memoria; no se reporta.
- A escala se anulan los correos de relleno antes de bloquear y los bloques de EM evitan la
  fecha de nacimiento sola, para que el bloqueo no crezca con el cuadrado.

El [universo grande](https://stous1.github.io/identity-resolution/hito5_universo.html)
carga desde Parquet una muestra de 200 mil registros del conjunto de 1 millón (40 mil en
el celular). Los datos de escala no se versionan; solo esas muestras.

## Qué encontró la auditoría y qué cambió

Una sesión de auditoría independiente, que no había escrito el código, revisó los hitos 1 a
5. Su informe completo está en [audit/INFORME.md](audit/INFORME.md), con sus scripts y
resultados, y se versiona sin cambios como registro independiente.

**Lo que se sostiene:** no hay fugas de etiquetas (los parámetros y métricas son idénticos
con la verdad barajada), todas las cifras publicadas se reproducen al dígito (114 de 115
coinciden; la otra es un redondeo) y la metodología de partición por persona, medición
única y bootstrap es correcta.

**Lo que no se sostenía, y qué cambió:**

| Hallazgo de la auditoría | Qué decía el README | Qué cambió (hito 6) |
|---|---|---|
| **A1. Vetos de −43 a −73 bits.** El generador del hito 2 nunca cambia la ciudad ni la dirección, así que el v1 aprendió que "municipio distinto" veta el par. Sin esos vetos, el recall de la ciega 1 sube de 0,636 a 0,943. | El fallo de la ciega 1 venía de nombres cruzados, documentos y fijos; el "hallazgo de equidad más importante" era la brecha del apellido de casada (−20,4 puntos). | Generador con mudanzas y apellidos de casada; modelo v3 con un piso a las m (ningún campo resta más de 10 bits). Corregida la interpretación: sin los vetos, la brecha del apellido de casada es de −3,6 puntos y **no es significativa**; la de los apodos sí es real. No había base para hablar de brecha de género. |
| **A2. La precisión cae a escala por reentrenar, no por homónimos.** Todos los falsos positivos son familiares. | "Hay más homónimos con datos parecidos." | Escala con el modelo congelado y documentado que reentrenar en cada tamaño degrada la precisión. |
| **A3. Probabilidades sobreconfiadas** donde se decide: p ≈ 0,98 era verdadero el 0–11 % de las veces. | La zona gris era p ∈ [0,9, 0,9999). | Calibración isotónica en desarrollo, bandas de peso para la zona gris (también en "¿ya es cliente?" y en el servicio local) y diagrama de confiabilidad fuera de muestra. La calibración no se transfiere a la ciega 3. |
| **M1. Sin línea base:** en algunas pruebas, Splink aportaba solo +0,01 de F1 sobre reglas simples. | No se comparaba con reglas. | Reglas determinísticas e híbrido en todas las evaluaciones, con aporte por segmento. |
| **M2. Umbral inestable** entre desarrollos repetidos. | "Umbral elegido en desarrollo." | Se reporta, pero el umbral sigue siendo un único mínimo de costo; la grilla se amplió hasta 1 − 10⁻¹¹. Un diagnóstico confirma que explica por qué el v3 pierde recall frente al v2 (sección siguiente). |
| **M3. Hito 3 con una semilla favorable.** | Puentes que evitan 4 de cada 10 mezclas, 0 uniones erróneas, 432 grupos bien clasificados. | Cifras como media ± DE de 8 pares de semillas. |
| **M5. Tiempo real con 50 % de clientes existentes.** | Precisión 0,999. | Precisión con prevalencias de 1 %, 10 % y 50 %: con el v2 del hito 5, 0,991 y 0,909 con 10 % y 1 %; con el v3, 0,994 y 0,938 (cifras de la v1.0; con los datos de fecha fija de la v1.1.1 no hubo falsas alarmas). |
| B3. "240 mil enlaces" y "memoria acumulada entre etapas". | | Corregido: 241 mil y picos que no se acumulan. |

## Hito 6: correcciones post-auditoría

**Página:** [hito 6 en GitHub Pages](https://stous1.github.io/identity-resolution/hito6.html)

Mismas reglas de siempre: todo se decide en desarrollo, el modelo se congela (tag
`hito6-congelado`) y se mide una sola vez en una prueba ciega nueva.

1. **Generador con historia** ([`sinteticos.agregar_historia`](src/identidades/sinteticos.py)):
   mudanzas (20 % de las personas con dos o más registros; la mitad cambia de ciudad) y
   apellido de casada (30 % de las mujeres; una de cada cinco cambia de apellido de casada
   por divorcio o nuevo matrimonio). `generar` no cambia, así que los hitos anteriores se
   reproducen igual.
2. **Modelo v3** ([`modelo_co_v3.py`](src/identidades/modelo_co_v3.py)): la estandarización
   v2 sin cambios, apellido de casada con un nivel intermedio y un **piso a las
   probabilidades m** ([`modelo.aplicar_piso_m`](src/identidades/modelo.py)): m ≥ u · 2⁻ᴮ,
   así que ningún nivel resta más de B bits. B se eligió en desarrollo entre 5 y 20:
   **10 bits** (de 10 a 20 empatan en costo y se toma el más estricto). El peor peso pasa
   de −47,9 (v1, municipio) y −72,6 (v2, apellido de casada) a **−10,0** (v3). Con mudanzas
   en los datos, EM ya no aprende vetos extremos (el peor era −10,3); el piso es la red de
   seguridad. **Sin vetos extremos no quiere decir que un campo no pueda decidir solo:** en
   la ciega 3, el v3 a su umbral tiene **237** pares verdaderos rechazados por un solo campo
   (sobre todo fecha, 74, y documento, 65), frente a 171 del v2. Parte de la diferencia es
   del umbral: con el mismo umbral del v2 (0,9999), el v3 tiene 136.
3. **Desarrollo:** el del hito 2 con historia más las ciegas 1 y 2 completas (13.919
   registros de 5.200 personas). Umbral de menor costo: 0,999999.
4. **Prueba ciega 3** ([`errores_ciegos_3.py`](src/identidades/errores_ciegos_3.py)): la
   escribió un subagente nuevo, sin acceso a la estandarización, los modelos, los
   generadores anteriores, la documentación ni la auditoría. La evidencia de que es
   posterior al congelamiento es solo el orden de los commits: el del modelo congelado
   (`af22bb0`, 17:00:33) va antes que el del generador (`de2ff5a`, 17:00:46). Eso prueba el
   orden de los commits, no el de la escritura; lo que sí garantiza el tag es que el v3 no
   cambió después. 2.000 personas y 5.181 registros (con la fecha fija), con mudanzas, apellido de casada en varias
   posiciones, separaciones, registros sin documento, documentos alterados y datos de otras
   personas digitados por error.

### Prueba ciega 3 (por clúster, IC 95 % por bootstrap de personas)

| Modelo congelado | Precisión | Recall | Personas exactas |
|---|---|---|---|
| v1 (`hito2-congelado-r1`) | 0,995 [0,978 – 1,000] | 0,715 [0,692 – 0,738] | 68,3 % |
| v2 (`hito2b-congelado`) | 0,996 [0,977 – 1,000] | **0,972** [0,966 – 0,979] | **95,4 %** |
| **v3 (`hito6-congelado`)** | 0,996 [0,977 – 1,000] | 0,955 [0,947 – 0,963] | 92,9 % |

![Evolución v1, v2 y v3](docs/resultados/hito6/evolucion.png)

- **El v1 se vuelve a caer por los vetos:** 1.320 pares verdaderos quedan bajo el umbral
  solo por el municipio o la dirección de personas que se mudaron.
- **El v3 queda por debajo del v2 en esta prueba.** Diferencia pareada v3 − v2: recall −1,7
  puntos [−2,3, −1,2] y F1 −0,9 [−1,2, −0,6], significativas; precisión −0,01 [−0,04,
  0,00]. Con los datos anteriores a la v1.1.1, la diferencia de F1 no era significativa. El desarrollo del v3 eligió el umbral 0,999999, 6,6 bits más alto que el
  0,9999 del v2.
- **Diagnóstico del umbral** (no es una cifra principal: la ciega 3 ya se había mirado y
  el umbral congelado no cambia). Con el umbral del v2, el v3 tiene **más recall que el v2**:
  0,975 contra 0,972, diferencia +0,2 puntos [+0,1, +0,5], significativa; personas exactas
  95,6 % contra 95,4 % (+0,15 [−0,1, +0,45]); precisión 0,992 contra 0,996 (−0,4 [−1,6,
  0,0]) y F1 0,983 contra 0,984 (−0,1 [−0,7, +0,2]), no significativas. **Se confirma que
  la causa principal es el umbral:** a igual umbral, la pérdida de recall se invierte,
  aunque con los datos nuevos la ventaja es menor (antes, +0,6 puntos). Es el hallazgo M2 de la auditoría: el umbral "elegido en desarrollo" depende
  bastante de la muestra. Detalle en
  [diagnostico_umbral.json](docs/resultados/hito6/diagnostico_umbral.json).
- **Robustez frente al apellido de casada, solo en la prueba normal:** en la prueba normal
  con historia (800 personas), el veto del v2 en el apellido de casada deja 19 pares
  verdaderos sin unir; el v3, ninguno (recall 0,998 contra 0,992; precisión 1,000 y 0,998).
  Pero esa prueba usa el mismo mecanismo de historia con que se desarrolló el v3. En la
  ciega 3 el veto del v2 afecta solo a 17 pares, y **el v2 reconstruye más personas exactas
  que el v3** a sus umbrales congelados (95,4 % contra 92,9 %; −2,5 puntos [−3,3, −1,8],
  significativa).

**Equidad en la ciega 3 (v3, personas exactas):**

| Grupo | Exactas | Frente a | Diferencia [IC 95 %] | ¿Significativa? |
|---|---|---|---|---|
| Mujer (994) | 92,5 % | 93,3 % hombre | −0,9 [−3,1, +1,4] | No |
| Apellido de casada (200) | 89,5 % | 93,3 % sin él | −3,8 [−8,5, +0,2] | No |
| Con apodo (119) | 90,8 % | 93,0 % sin apodo | −2,3 [−8,1, +2,6] | No |
| Con mudanza (365) | 90,1 % | 93,5 % sin mudanza | −3,4 [−6,8, +0,1] | No |
| Dirección rural (208) | 96,2 % | 92,5 % urbana | +3,6 [+0,4, +6,3] | **Sí** |

- **Con el v3 no se detecta brecha de género:** −0,9 puntos [−3,1, +1,4]. El intervalo
  admite una brecha de hasta unos 3 puntos, así que no se puede afirmar que no la haya. Con
  el v2 tampoco (−1,3 [−3,2, +0,6]; con los datos anteriores a la v1.1.1 era −2,2,
  significativa).
- **La brecha del apellido de casada ya no es significativa con el v3** (−3,8 puntos [−8,5,
  +0,2]; antes, −4,8 y significativa); con el v2 sigue siéndolo (−4,3 [−8,4, −0,7]). La
  única significativa del v3 es la de las direcciones urbanas frente a las rurales (−3,6
  puntos para las urbanas). Brechas de este tamaño cambian con la muestra: son señales para
  vigilar, no hallazgos firmes.

### Línea base: dónde aporta Splink

Reglas con la misma estandarización y unión transitiva. El **híbrido** une primero con las
reglas ("documento o nombre+fecha") y deja a Splink el resto; el **híbrido estricto** además
prohíbe unir registros con documentos distintos.

| Ciega 3 (por clúster) | Precisión | Recall | F1 | Personas exactas |
|---|---|---|---|---|
| Regla: mismo documento | 0,996 | 0,679 | 0,808 | 65,7 % |
| Regla: documento o nombre+fecha | 0,994 | 0,856 | 0,920 | 82,2 % |
| **Splink v3** | **0,996** | 0,955 | 0,975 | 92,9 % |
| Híbrido | 0,988 | **0,975** | **0,982** | **95,4 %** |
| Híbrido estricto | 0,990 | 0,904 | 0,945 | 87,4 % |

| Recall por segmento (ciega 3) | Regla | Splink v3 | Híbrido |
|---|---|---|---|
| Documento siempre igual (1.280 personas) | 1,000 | 0,976 | 1,000 |
| Algún registro sin documento (215) | 0,739 | 0,943 | 0,963 |
| Documento alterado (505) | 0,758 | 0,940 | 0,956 |

- **Splink aporta sobre todo donde el documento falla.** En toda la ciega 3 supera a la
  mejor regla por +0,055 de F1 [+0,042, +0,066] (cifra global, de todos los segmentos;
  antes de la v1.1.1, +0,065), y por +0,048 en la prueba normal. Por segmento, la
  diferencia está donde el documento falta o está alterado: ahí Splink recupera el 94 % de
  los pares y la regla, el 74–76 %.
- **Donde el documento es igual, la regla "mismo documento" empata con Splink:** precisión
  0,996 y recall 1,000, frente a 0,991 y 0,976 de Splink. El híbrido, en la ciega 3, pierde
  0,8 puntos de precisión (significativo por poco) para ganar 2,0 de recall; su F1 queda
  0,7 puntos por encima del de Splink, sin diferencia significativa. Antes de la v1.1.1
  perdía 3,2 puntos de precisión: la regla de nombre+fecha une homónimos y registros con
  datos ajenos, y el híbrido los hereda en una cantidad que depende de la muestra. En la
  prueba normal no pierde nada (F1 0,999 contra 0,999). Como el falso positivo cuesta 10
  veces más, **Splink solo sigue siendo la opción por defecto**; un híbrido solo con
  "mismo documento" es la variante a probar.
- Línea base de los hitos 1, 2, 2b, FEBRL y 3 en la [auditoría §2](audit/INFORME.md#2-línea-base-determinística-a2_linea_basepy).

![Línea base](docs/resultados/hito6/linea_base.png)

### Calibración y zona gris por bandas de peso

Regresión isotónica de la verdad sobre el peso, ajustada con los pares del bloqueo en
desarrollo ([`calibracion.py`](src/identidades/calibracion.py)), y tres bandas congeladas
con el modelo:

| Banda | Peso | Prueba normal | Ciega 3 |
|---|---|---|---|
| Rechazar (probabilidad calibrada < 0,1) | < 5,2 bits | 593 pares, 0 % verdaderos | 1.892 pares, 4,3 % |
| **Revisar (zona gris)** | 5,2 a 19,9 bits | 8 pares, **75 %** verdaderos | 436 pares, **94 %** |
| Aceptar (umbral de operación) | ≥ 19,9 bits | 2.131 pares, 100 % | 5.752 pares, 99,97 % |

![Confiabilidad](docs/resultados/hito6/confiabilidad.png)

- **Sin calibrar,** en la prueba normal los pares con p entre 0,9 y 0,9999 (8 pares, media
  0,973) son verdaderos el 25 % de las veces: sobre todo familiares.
- **Como triaje, las bandas funcionan:** la zona gris de la ciega 3 contiene 412 pares
  verdaderos que el umbral no acepta. Ese es el trabajo del agente de revisión.
- **Como probabilidad, la calibración no se transfiere a la ciega 3, y fuera de muestra
  empeora la probabilidad:** queda subconfiada. En la zona [0,9, 0,9999) de la ciega 3, la
  probabilidad **sin calibrar** (media 0,989) se acerca más a lo observado (83 % de
  verdaderos) que la calibrada (media 0,29). En
  desarrollo, los pesos medios son sobre todo familiares; en la ciega 3, personas reales
  con errores difíciles. La probabilidad calibrada vale para una población parecida a la
  de desarrollo; con datos nuevos hay que recalibrar con una muestra etiquetada.

### Tiempo real: precisión según la prevalencia

El hito 5 midió "¿ya es cliente?" con 50 % de consultas de clientes existentes y 50 % de
personas nuevas. En un canal real, la mayoría de las consultas pueden ser de personas
nuevas, y entonces una tasa pequeña de falsas alarmas pesa mucho más. Con el v3 congelado
(base de registros de oro, 1.500 consultas de clientes existentes y 1.500 de personas
nuevas por población), la precisión para otra mezcla se recalcula con las tasas de cada
grupo: π·a / (π·a + (1 − π)·f), con a = aciertos entre existentes y f = falsas alarmas
entre nuevas (IC 95 % remuestreando cada grupo).

| Población | Recall | Falsas alarmas | Precisión con 50 % | con 10 % | con 1 % |
|---|---|---|---|---|---|
| Generador del hito 2 (2.768 clientes) | 0,987 | 0 de 1.500 | 1,000 | 1,000 | **1,000** (≥ 0,82*) |
| Generador de la ciega 3 (3.081 clientes) | 0,923 | 0 de 1.500 | 0,999 [0,998 – 1,000] | 0,999 | 0,999 |

\* Con 0 falsas alarmas en 1.500 el bootstrap no da intervalo; con la regla del tres
(tasa ≤ 3/1.500 = 0,2 % con 95 % de confianza), la precisión con 1 % de clientes sería al
menos 0,82.

- **La precisión con 1 % de clientes es frágil:** con los datos anteriores a la v1.1.1
  hubo una falsa alarma en 1.500 personas nuevas y era 0,938; con los datos nuevos no hubo
  ninguna y es 1,000. Una sola falsa alarma la mueve 6 puntos. La cifra del hito 5 con una
  mezcla 50/50 no vale para otras mezclas.
- **En la población de la ciega 3 el recall baja a 0,923**: de las consultas de clientes
  existentes, 79 van a revisión y 35 quedan como nuevas; una se asigna a un cliente
  equivocado. La latencia mediana fue de 71 a 83 ms por consulta.

**Zona gris por bandas en "¿ya es cliente?".** La decisión "revisar" ya no usa p ≥ 0,9 sin
calibrar, sino la banda "revisar" congelada en desarrollo (peso ≥ 5,2 bits). Como el
tiempo real usa la previa 1/N y el desarrollo otra, la banda se traslada a la previa de
cada base conservando la evidencia de los campos: queda en 5,7 bits (población del hito 2)
y 5,5 bits (población de la ciega 3). "Cliente" sigue igual (p ≥ 0,999999), así que
precisión y recall no cambian. Lo que cambia es la cola de revisión, medida sobre las
mismas consultas:

| Población | Revisión con p ≥ 0,9 | Revisión con bandas | Existentes que pasan de revisar a nuevo |
|---|---|---|---|
| Generador del hito 2 | 27 (1 existente, 26 nuevas) | **19** (1 y 18) | 0 |
| Generador de la ciega 3 | 91 (81 y 10) | **87** (79 y 8) | 2 |

Con bandas, menos personas nuevas van a revisión, pero 2 clientes existentes de la ciega 3
pasan de "revisar" a "nuevo": la banda es algo más exigente que p ≥ 0,9 con esta previa.
Desde la v1.1.1, el servicio local (`scripts/servicio_local.py`) usa por defecto el v4 con
sus bandas; `--modelo v3` usa este y `--modelo v2` reproduce el del hito 5.

### Escala con el modelo congelado

El hito 5 reentrenaba el modelo en cada tamaño. La auditoría mostró que eso degrada la
precisión: al crecer los datos, el u de los campos casi únicos (teléfono, documento, correo)
baja, cada coincidencia suma más bits, y los familiares que comparten teléfono y dirección
(campos que no son independientes) acumulan más evidencia de la que quita la previa.
**Reentrenar en cada tamaño degrada la precisión**: de 0,992 con 10 mil registros a 0,976
con 300 mil (auditoría §6), y a 10 millones se proyectaba ~0,94. Aquí se usa el **v3
congelado**: solo se vuelve a estimar λ, con el mismo bloqueo exacto y los mismos datos del
hito 5.

| Registros | Reentrenado (hito 5) P / R | **Congelado (v3)** P / R | Personas exactas (congelado) | Tiempo total | Memoria pico |
|---|---|---|---|---|---|
| 99.837 | 0,981 / 0,997 | **0,999 / 0,996** | 99,3 % | 14,4 s | 0,8 GB |
| 996.688 | 0,970 / 0,996 | **0,999 / 0,995** | 99,2 % | 128 s | 7,1 GB |

- **Ojo: esta tabla compara a la vez tres cambios.** La columna del hito 5 es el esquema
  v2 reentrenado en cada tamaño con umbral 0,9999; la del hito 6 es el v3 congelado con
  umbral 0,999999. Un umbral más alto ya sube la precisión por sí solo, así que la tabla no
  aísla el efecto de congelar. Lo que sí lo aísla es el experimento de la auditoría (§6):
  el v2 congelado, al mismo umbral, mantiene la precisión plana de 10 mil a 300 mil
  registros.
- **Con el modelo congelado, la precisión no cae entre los dos tamaños medidos** (0,999 en
  ambos; los falsos positivos se multiplican por 9,9 cuando los datos crecen 10 veces), y
  no hace falta entrenar: el tiempo es casi todo de preparación (99 de 128 s).
- **Recomendación:** entrenar m y u una vez con una muestra y congelarlos. Si se reentrena,
  hay que recalibrar el umbral con una muestra etiquetada en cada orden de magnitud.
- **Línea base a escala:** la regla "documento o nombre+fecha" pierde precisión con el
  volumen (0,994 con 100 mil, 0,942 con 1 millón: más personas distintas con el mismo
  nombre y fecha), y el híbrido la hereda (0,939). Splink congelado mantiene 0,999. La
  regla "mismo documento" sigue en 0,997 de precisión, pero con recall 0,62.

### Hito 3 con varias semillas

Ver las tablas corregidas en el [hito 3](#puentes). Con el v3 congelado las cifras son
parecidas: precisión de la unión 1,000 ± 0,001, exactitud del grafo 98,2 % ± 0,6 y mezclas
evitadas con puentes 36 % ± 12 %.

Métricas completas en [docs/resultados/hito6/](docs/resultados/hito6/).

## v1.1: realidad residencial y familiar colombiana

Página: [docs/v11.md](docs/v11.md). Código: `diagnostico_v11.py`, `escenario_residencial.py`,
`estandarizacion_v4.py`, `modelo_co_v4.py`, `grafo_residencial.py`, `flujo_v11.py` y
`errores_ciegos_4.py`. Resultados: [docs/resultados/v11](docs/resultados/v11/). Tags:
`v4-congelado` (modelo, estandarización y su desarrollo) y `grafo-v11-congelado`
(clasificador y sus parámetros).

### Diagnóstico previo

Detalle en [docs/v11_diagnostico.md](docs/v11_diagnostico.md); cada hallazgo tiene su
prueba en `tests/test_diagnostico_v11.py`.

- **Grafo del hito 3 con ejemplos escritos a mano** (clústeres verdaderos, parámetros
  publicados 15 y 0,5):
  - pareja sin apellidos en común: sospechosa;
  - pareja casada ("Rincón de Salazar"): sospechosa;
  - estudiantes en el mismo apartamento: relleno;
  - seis hogares de un conjunto: ningún grupo;
  - casa de dos pisos: padres sospechosos e hijos relleno.

  Hay tres causas. La estandarización v1 no reconoce una dirección con complemento, y el
  grafo toma por genérica toda dirección sin vía reconocida. La única señal de hogar es
  compartir apellido, y "DE" cuenta como apellido. La sospecha no depende del tipo de dato
  ni del tamaño.
- **Caso "Esther Nancy MONTENEGRO MUÑOZ":** reconstruido con la fecha del universo publicado
  (18 de octubre de 2026). Sus cinco registros son de la misma persona (la 1057), y el
  registro 4838 de otra persona (la 199) usa su documento: es una suplantación inyectada
  por el escenario. El clasificador acierta, pero el universo pintaba de rojo a la víctima.
- **El escenario del hito 3 cambia con la fecha del día.** Faker calcula las fechas de
  nacimiento desde hoy, y eso cambia el resto del sorteo. Pasa lo mismo con todo lo que
  parte de `sinteticos.generar` (prueba normal, ciegas 1 a 3). La v1.1 usa
  `sinteticos_fecha.fecha_fija`; los generadores anteriores no se cambian.
- **Ajuste por frecuencia del v3:** existe, pero solo en el nivel "dirección exacta"
  (`tf_adjustment_column = domicilio`). Bits del v3:
  - mismo apartamento escrito de otra forma: −1,7;
  - mismo edificio, otro apartamento: +5,4;
  - casa contra "Piso 2": −1,7;
  - otro predio de la misma cuadra: +8,8. "Misma vía, número y placa" no incluye el
    consecutivo.

### Generador residencial

`EscenarioResidencial` hereda la captura del escenario del hito 3 (canales, validación,
errores, relleno, anillos y suplantaciones) y genera la población desde los predios:

- **Predios:** casa 55 %, casa de varios pisos 17 %, edificio 14 % (2 a 6 hogares
  clientes) y conjunto 14 % (3 a 10 hogares).
- **Hogares:** solo 30 %, pareja 22 % (55 % casada, el resto en unión libre, sin apellidos
  en común), familia 23 % (hijos con el primer apellido de cada padre), monoparental 8 %,
  hermanos 5 % y convivientes 12 % (2 a 4).
- **Casa de varios pisos:** el hijo vivió con sus padres y después subió con su pareja;
  el 60 % escribe "piso 2" y el resto la misma dirección. A veces hay un arrendatario.
- **Captura:** apellido de casada en el 55 % de los registros de las casadas; la unidad se
  escribe de muchas formas y se omite el 15 % de las veces en edificios y conjuntos; el
  nombre del conjunto aparece a veces, antes o después.
- **Historia:** llegadas, mudanzas, ocupación sucesiva, fijo del hogar y correo familiar.

La verdad de cada grupo compartido (`etiquetar_personas`) es hogar, pareja, convivencia,
multifamiliar, coincidencia, relleno o sospechoso.

### Modelo v4

Igual al v3 salvo la dirección: `preparar` agrega predio, unidad y sus partes, y la
comparación tiene seis niveles, con ajuste por frecuencia en "misma dirección" (predio y
unidad) y en "unidad desconocida" (predio). Desarrollo: el del v3 (hito 2 con historia,
ciegas 1 y 2) más un escenario residencial (semilla 4040), en total 19.042 registros de
7.233 personas.

- **Piso de las m:** 10 bits. Los valores de 10 a 20 empatan en costo (73) y se toma el
  más estricto, como en el v3.
- **Umbral:** 0,999999.

En el primer desarrollo, la casa sin piso contra "Piso 2" caía en "unidad desconocida"
con +10,6 bits. Eso empuja a unir a padres e hijos de una casa de dos pisos, así que,
antes de congelar, se agregó un nivel propio para ese caso, que aprendió +7,3.

| Nivel de dirección (bits, sin frecuencia) | v4 |
|---|---|
| Misma dirección (predio y unidad) | +11,8 |
| Mismo predio, uno sin unidad y otro con piso | +7,3 |
| Mismo predio, unidad desconocida o incompleta | +10,7 |
| Mismo predio, otra unidad | +3,6 |
| Predio parecido (digitación) | +4,8 |
| Distinta | −2,6 |

Al evaluar apareció un fallo de tipos: con datos sin ninguna unidad (prueba normal), DuckDB
lee `unidad_partes` toda nula como entero. El flujo la tipa como lista de texto
(`flujo_v11.preparar_v4_tipado`) sin cambiar el modelo congelado: en datos con unidades,
el F1 es idéntico.

### Grafo residencial

- **Grupos:** la dirección se agrupa por predio y, dentro del grupo, se miran las unidades
  de cada cliente.
- **Señales de hogar entre dos clientes:**
  - apellido propio en común, sin partículas;
  - apellido de casada de uno igual al primer apellido del otro;
  - convención de los hijos: el primer apellido del hijo es el de uno y su segundo apellido
    es el primero del otro;
  - un teléfono o correo compartido (solo para la dirección).
- **Tipo de predio estimado:** torre, bloque, interior o casa numerada: conjunto; solo
  apartamentos: edificio; pisos, o varias familias sin unidades: casa de varios pisos; si
  no, casa.
- **Reglas:**
  - documento compartido: sospechoso;
  - forma de anillo (poca validación, canal digital, valor que los clientes casi no usan
    en sus otros registros) sin parentesco: sospechoso;
  - edificio o conjunto con varias unidades: multifamiliar, salvo que todos sean familia;
  - con parentesco: hogar;
  - pocos clientes sin otras señales: convivencia probable;
  - un fijo compartido por pocos clientes, o un contacto entre co-residentes: convivencia;
  - demasiados clientes para el tipo de predio: sospechoso.

Los parámetros se eligen por exactitud balanceada; una predicción es aceptable si
corresponde a la etiqueta, y para una pareja se acepta hogar o convivencia. Los ajustes
que siguieron se decidieron mirando solo los 8 escenarios de desarrollo: el fijo del hogar
y la exclusividad 0,5 en la grilla. Parámetros congelados: convivencia hasta 4 clientes,
casa hasta 5, unidad hasta 6, familia ≥ 0,75, anillo con validación ≤ 0,10, digital ≥ 0,75
y exclusividad ≤ 0,4, contacto hasta 6 clientes.

**8 pares de semillas** (desarrollo 4040, 4011 … 4077; prueba 4141, 4111 … 4177). Cada
clasificador elige parámetros en su desarrollo y se mide una vez en la prueba. El del hito
3 usa los clústeres del v3 y su propio procedimiento:

| Media ± DE | Grafo del hito 3 | Residencial (v3) | Residencial (v4) |
|---|---|---|---|
| Exactitud balanceada | 0,508 ± 0,035 | 0,925 ± 0,034 | 0,925 ± 0,034 |
| Falsa sospecha (grupos benignos) | 0,391 ± 0,037 | 0,005 ± 0,003 | 0,005 ± 0,003 |
| Personas inocentes marcadas | 0,368 ± 0,040 | 0,002 ± 0,001 | 0,002 ± 0,001 |
| Recall de sospechosos | 0,976 ± 0,028 | 0,990 ± 0,021 | 0,990 ± 0,021 |
| Precisión de sospechosos | 0,194 ± 0,020 | 0,926 ± 0,024 | 0,945 ± 0,027 |

- Falsa sospecha del grafo del hito 3 por tipo de grupo: parejas 0,83, convivientes 0,86,
  multifamiliar 0,80, hogar 0,03.
- Con la semilla 4141, la exactitud del grafo del hito 3 tiene un IC 95 % de 0,46 a 0,56,
  y la falsa sospecha del residencial, de 0,0 a 0,018.
- El tipo de predio se estima bien en el 0,879 ± 0,017 de los grupos de dirección. El
  error más común es una casa de varios pisos sin "piso" escrito que se toma por casa.
- La unión es casi igual: F1 0,9984 ± 0,0004 con el v3 y 0,9986 ± 0,0004 con el v4.

### Prueba ciega 4

`errores_ciegos_4.py` lo escribió un subagente nuevo, con las mismas prohibiciones de las
ciegas anteriores, más los módulos de la v1.1: no leyó la estandarización, los modelos, los
generadores, la documentación, las pruebas ni el historial. Recibió la interfaz (columnas y
vocabularios de la verdad) y la descripción de la realidad que debía reflejar, sin
indicaciones sobre cómo son los patrones sospechosos ni cómo los detecta el grafo. Se lanzó
a las 08:09:36, después de los tags `v4-congelado` (209da33) y `grafo-v11-congelado`
(9d8fb1b, 08:09:30), y su commit es 8f638c5.

**Qué generó:** 2.000 personas y 4.844 registros.

- **Predios:** conjunto 698 personas, casa 544, edificio 470, casa de varios pisos 288.
- **Hogares:** 15 % de los miembros de un hogar no son clientes. Incluye parejas del mismo
  sexo, estudiantes con correo universitario, abuelos con nietos y ocupación sucesiva.
- **Errores de captura propios:**
  - formatos de fecha por canal;
  - tarjeta de identidad que pasa a cédula;
  - Soacha anotada como Bogotá;
  - indicativos de fijo de 1 y de 3 cifras;
  - unidades escritas como "T2 504".
- **23 valores sospechosos inyectados:** documento ajeno, anillos de celular de 4 a 7
  personas (a veces con el celular real de un "controlador"), correos de tramitador y
  direcciones de fachada.

**Unión** (por clúster, IC 95 % por bootstrap de personas):

| Modelo | Precisión | Recall | F1 | Personas exactas | Vetados |
|---|---|---|---|---|---|
| v3 | 0,995 (0,983 a 1,000) | 0,979 (0,972 a 0,985) | 0,987 (0,980 a 0,992) | 0,965 | 132 |
| v4 | 0,995 (0,984 a 1,000) | 0,993 (0,990 a 0,996) | 0,994 (0,988 a 0,997) | 0,980 | 64 |

Diferencia pareada v4 − v3: F1 +0,0070 (0,0040 a 0,0105), recall +0,0138 (0,0080 a
0,0206), precisión +0,0001 (0,0000 a 0,0003).

**Equidad** (diferencias pareadas entre grupos de personas):

- **v3:**
  - más personas exactas entre las mujeres: +0,018 (0,002 a 0,034);
  - más recall para quienes usan apellido de casada que para quienes no: +0,017 (0,005 a
    0,027);
  - más personas exactas en casa que en edificio o conjunto: +0,017 (0,001 a 0,032);
  - más recall en casa que en edificio o conjunto: +0,012 (0,000 a 0,025).
- **v4:** ninguna diferencia significativa en mujer, apellido de casada, edificio o
  conjunto, casa de varios pisos ni convivientes.

**Grafo.** Los dos están congelados: el del hito 3, con sus parámetros publicados y los
clústeres del v3; el residencial, con `clasificador.json` y los clústeres del v4.

| | Grafo del hito 3 | Residencial |
|---|---|---|
| Exactitud (aceptable) | 0,641 (0,594 a 0,684) | 0,942 (0,922 a 0,960) |
| Exactitud balanceada | 0,444 | 0,921 |
| Falsa sospecha (grupos) | 0,360 (0,311 a 0,410) | 0,006 (0,000 a 0,012) |
| Recall de sospechosos (grupos) | 0,824 (0,619 a 1,000) | 0,765 (0,545 a 0,957) |
| Precisión de sospechosos | 0,074 | 0,394 |
| Personas inocentes marcadas | 289 de 788 | 28 de 1.697 |
| Personas de patrones detectadas | 71 de 87 | 58 de 87 |

- **Diferencias pareadas por persona** (residencial − hito 3):
  - inocentes marcadas: −0,340 (−0,373 a −0,307);
  - personas de patrones detectadas: −0,149 (−0,276 a −0,023).
- **Lo que se escapa:**
  - tres anillos de celular de 7 clientes quedan como relleno, porque un contacto en más
    de 6 clientes es relleno y los anillos propios eran de 3 a 6;
  - una dirección de fachada con 9 clientes y un tercio de registros validados queda como
    multifamiliar.
- **Precisión de sospechosos:** la mayoría de los falsos positivos son documentos que
  comparten dos clústeres de la misma persona (12 de 20), es decir, uniones que el modelo
  no hizo. Revisarlos también tiene valor.
- **Tipo de predio:** se estima bien en el 0,852 de los grupos de dirección.

### Otras pruebas (v3 frente a v4)

| Conjunto | F1 v3 | F1 v4 | Diferencia pareada |
|---|---|---|---|
| Prueba normal del hito 2 (sin unidades) | 0,9988 | 0,9988 | 0,000 |
| Ciega 3 (ya mirada; referencia) | 0,975 | 0,976 | +0,001 (−0,005 a 0,004) |
| Residencial de prueba (4141) | 0,9985 | 0,9985 | 0,000 |

En la ciega 3, el recall sube +0,005 (0,001 a 0,009) y la precisión baja 0,003 (−0,015 a
0,000). Cifras de la v1.1.1 (con la fecha fija); en la v1.1 se habían medido 0,980 y 0,982
con los datos que el generador daba ese día.

### Limitaciones de la v1.1

- **La distribución real de conjuntos, edificios y casas de varios pisos solo se puede
  calibrar con datos reales:** cuántos clientes viven en un mismo predio, con qué
  frecuencia se omite la unidad o se escribe el piso, la mezcla de tipos de hogar y los
  umbrales de tamaño del grafo salen de supuestos sintéticos.
- La pareja sin otra señal que la dirección no se distingue de dos convivientes.
- El clasificador residencial depende de los metadatos de canal y validación para
  reconocer anillos; en una base sin esos metadatos perdería esa señal.
- Las ciegas 1 a 4 ya se miraron.

## v1.1.1: reproducibilidad, demo con el v4 y ficha de cliente único

Página: [docs/v111.md](docs/v111.md). Código: `sinteticos_fecha.py`, `flujo_v111.py`, `tests/test_reproducibilidad.py` y `tests/test_ficha.py`.

### Por qué cambiaron cifras ya publicadas

Faker calcula las fechas de nacimiento desde la fecha de hoy. Con otra fecha cambian las
fechas y, con ellas, parte del resto del sorteo (por ejemplo, qué registros llevan tilde),
así que **el mismo generador con la misma semilla daba datos distintos según el día en que
se corriera**. Lo encontró el diagnóstico de la v1.1 al reconstruir el caso "Esther": el
escenario del hito 3 de un día no era el del día siguiente.

Desde la v1.1.1, `sinteticos.generar` corre con una fecha fija (`HOY_FIJO`, el 15 de enero
de 2026, la misma que ya fijaban las pruebas de la demo), y con ella todo lo que parte de
sus personas: hito 2, pruebas ciegas 1 a 3, escenario del hito 3, tiempo real y escala.
`tests/test_reproducibilidad.py` mueve el reloj que ve Faker a 2026, 2031 y 2040 y exige
exactamente los mismos datos en cada generador; sin la corrección fallan los siete que
dependían de la fecha. Los escenarios de la v1.1 y la ciega 4 ya tenían fecha fija.

Se volvieron a correr **todas las evaluaciones publicadas** con los modelos congelados,
sin reentrenar nada: los modelos v1 a v4, sus umbrales y sus tags no cambian. Lo que cambia
son los datos de prueba, así que estas son cifras nuevas de los mismos modelos. La escala
se repitió sin la caché de `data/escala`, que guardaba los datos generados con la fecha
anterior.

**Lo que no se recalculó:** el hito 2 entrena su modelo; volver a correrlo daría otro
modelo y otro umbral congelado. En su lugar se reevaluó el v1 congelado en la prueba normal
regenerada (`docs/resultados/hito2/reevaluacion_fecha_fija.json`). Las tablas que citan "la
prueba normal del hito 2" con el v1 conservan la cifra de la corrida original.

### Cifras que cambiaron

Por clúster. "Antes" es lo publicado hasta la v1.1; "ahora", con la fecha fija.

| Cifra | Antes | Ahora |
|---|---|---|
| **Ciega 3, v3:** precisión / recall / F1 | 0,997 / 0,966 / 0,981 | **0,996 / 0,955 / 0,975** |
| Ciega 3, v3: personas exactas | 94,5 % | 92,9 % |
| Ciega 3, v2: precisión / recall / F1 | 0,994 / 0,978 / 0,985 | 0,996 / 0,972 / 0,984 |
| Ciega 3, v1: precisión / recall / F1 | 0,989 / 0,693 / 0,815 | 0,995 / 0,715 / 0,832 |
| Ciega 3: F1 v3 − v2 (pareada) | −0,004 (−0,008 a 0,002) | **−0,009 (−0,012 a −0,006)** |
| Ciega 3: v3 con el umbral del v2 (recall / F1) | 0,984 / 0,987 | 0,975 / 0,983 |
| Ciega 3: Splink − mejor regla (F1) | +0,065 (0,053 a 0,079) | **+0,055 (0,042 a 0,066)** |
| Ciega 3: F1 de la mejor regla / híbrido | 0,916 / 0,975 | 0,920 / 0,982 |
| Ciega 3: pares rechazados por un solo campo (v3 / v2 / v1) | 257 / 197 / 1.685 | 237 / 171 / 1.556 |
| Ciega 3: brecha de equidad significativa del v3 | apellido de casada (−4,8 puntos en personas exactas) | **dirección urbana frente a rural** (−3,6 puntos en personas exactas para las urbanas) |
| Prueba normal con historia (hito 6), v3: recall / F1 | 0,992 / 0,996 | 0,998 / 0,999 |
| Prueba normal con historia, v2: precisión / recall | 1,000 / 0,986 | 0,998 / 0,992 |
| Prueba normal con historia, v1: recall | 0,922 | 0,939 |
| Prueba normal del hito 2, v1 congelado: recall | 0,998 | 1,000 |
| Ciega 1, v1: precisión / recall / F1 | 0,997 / 0,636 / 0,777 | 0,989 / 0,635 / 0,774 |
| Ciega 2, v2: precisión / recall / F1 | 0,998 / 1,000 / 0,999 | 1,000 / 1,000 / 1,000 |
| Ciega 2, v1 (control): recall | 0,920 | 0,914 |
| Tiempo real v3, población normal: precisión con 1 % / 10 % de clientes | 0,938 / 0,994 | **1,000 / 1,000** |
| Tiempo real v3, población normal: recall | 0,990 | 0,987 |
| Tiempo real v3, ciega 3: precisión / recall | 1,000 / 0,918 | 0,999 / 0,923 |
| Tiempo real del hito 5 (v2): precisión / recall | 0,999 / 0,993 | 1,000 / 0,992 |
| Hito 3, prueba publicada: exactitud del grafo | 1,000 | 0,991 |
| Hito 3: reglas de supervivencia elegidas | nombres y apellidos: fuente más confiable; dirección: más frecuente | nombres y apellidos: más frecuente; dirección: fuente más confiable |
| Hito 3, 8 semillas (v2): exactitud del grafo | 98,6 % ± 0,8 | 98,3 % ± 0,6 |
| Hito 3, 8 semillas (v2): mezclas evitadas por puentes | 31 % ± 18 | 35 % ± 7 |
| v1.1, ciega 3: F1 v3 / v4 | 0,980 / 0,982 | 0,975 / 0,976 |
| v1.1, prueba normal: F1 v3 = v4 | 0,998 | 0,999 |

Escala (datos regenerados sin la caché anterior):

| Cifra | Antes | Ahora |
|---|---|---|
| 1 millón de registros, v3 congelado: precisión / recall / F1 | 0,998 / 0,995 / 0,997 | 0,999 / 0,995 / 0,997 |
| 1 millón, mejor regla (F1) | 0,924 | 0,925 |
| 1 millón: tiempo total / pico de memoria | 129 s / 7,1 GB | 128 s / 7,1 GB |
| 1 millón, reentrenado (hito 5): precisión / recall | 0,971 / 0,996 | 0,970 / 0,996 |
| 100 mil, v3 congelado: precisión / recall | 0,998 / 0,996 | 0,999 / 0,996 |

**Lo que no cambió:** FEBRL3 y fake_1000 (datos públicos descargados), la prueba ciega 4,
los escenarios residenciales de la v1.1 y el grafo residencial (ya tenían fecha fija), los
modelos congelados y sus umbrales.

**Conclusiones que cambian:**

- En la ciega 3, el v3 a su umbral queda **por debajo del v2 de forma significativa** (antes
  la diferencia no era significativa). Con el umbral del v2, el v3 tiene más recall que el
  v2 (0,975 frente a 0,972), así que el diagnóstico del hito 6 se mantiene: la pérdida es
  del umbral, no del modelo.
- Splink sigue superando a la mejor regla determinística, por +0,055 de F1 en lugar de
  +0,065; la diferencia de precisión ya no es significativa.
- La brecha de equidad significativa del v3 en la ciega 3 ya no es la del apellido de
  casada sino una entre direcciones urbanas y rurales (las urbanas, peor). Con una sola muestra por prueba, estas
  brechas pequeñas cambian con los datos: conviene leerlas como señales, no como hallazgos.
- En tiempo real, el v3 no tuvo falsos positivos con la población normal regenerada: la
  precisión estimada con 1 % de clientes pasa de 0,938 a 1,000. Con 1.500 consultas nuevas,
  un solo falso positivo bajaría esa cifra a cerca de 0,94: es una cifra frágil.

### Demo y "¿ya es cliente?" con el v4

- La [demo](docs/demo.html) usa el v4: el motor en JavaScript reimplementa la dirección en predio
  y unidad, y la prueba de equivalencia con Splink pasa de ~630 a ~990 pares, ahora con
  pares residenciales (misma persona, al azar y vecinos del mismo predio), para el v2, el
  v3 y el v4. Ejemplos nuevos: el mismo apartamento escrito de dos formas y dos vecinos del
  mismo edificio.
- El servicio local "¿ya es cliente?" (`scripts/servicio_local.py`) usa el v4 por defecto,
  con las bandas de zona gris de su calibración congelada.

"¿Ya es cliente?" con las mismas consultas para los dos modelos (1.500 por población, mitad
clientes; `docs/resultados/v11/tiempo_real_v4.json`):

| Población | Modelo | Recall | Precisión con 1 % / 10 % / 50 % de clientes | Mediana |
|---|---|---|---|---|
| Normal (generador del hito 2) | v3 | 0,989 | 1,000 / 1,000 / 1,000 | 83 ms |
| Normal | **v4** | 0,989 | 1,000 / 1,000 / 1,000 | 113 ms |
| Residencial (v1.1) | v3 | 0,995 | 1,000 / 1,000 / 1,000 | 214 ms |
| Residencial | **v4** | **0,997** | 1,000 / 1,000 / 1,000 | 256 ms |

Ninguno de los dos dio falsos positivos en estas consultas, así que la precisión con 1 % de
clientes no distingue los modelos. El v4 recupera algo más en la población residencial y
cuesta unos 30 a 40 ms más por consulta (la comparación de dirección es más compleja). Las
latencias se midieron con la máquina ocupada por otras corridas.

### Ficha de cliente único

La [ficha de cliente único](docs/ficha.html) muestra, para una muestra de clientes del escenario
residencial de prueba (v4 y grafo residencial congelados), sus registros como un grafo
pequeño con la fuerza de cada enlace, el registro de oro campo por campo (valor, registro
de origen y regla de supervivencia), los clientes con quienes comparte datos y su
categoría, la historia de sus datos de contacto y las alertas de puente débil o documento
compartido. Ejemplos destacados: una familia, una pareja de un conjunto, una casa de varios
pisos y el caso Esther (víctima de suplantación).

### Trabajo futuro: anillos por su forma

En la [prueba ciega 4](#prueba-ciega-4), el grafo residencial dejó escapar tres
anillos de celular de 7 clientes: los tomó por relleno porque un contacto compartido por
más de 6 clientes es relleno, y esa regla se aplica antes que la de forma de anillo. El
grafo debe reconocer un anillo **por su forma** (registros recientes, por canal digital,
sin validar, en un valor que los clientes casi no usan en sus otros registros, con
personas sin relación) y no solo por su tamaño, y reservar "relleno" para valores
genéricos o compartidos por muchos clientes sin esa forma. Necesita una prueba ciega 5.

## Laboratorio interactivo

[docs/laboratorio.html](https://stous1.github.io/identity-resolution/laboratorio.html)
recalcula en el navegador, sin servidor, dos decisiones del proyecto a partir de los pares
puntuados por modelos congelados (`laboratorio.py` los exporta; `docs/laboratorio/motor.js`
los procesa; `tests/test_laboratorio.py` comprueba con Node que da lo mismo que Python):

- **La auditoría en vivo** (v1 en la prueba ciega 1, datos de fecha fija): al restar el
  aporte de domicilio y municipio a cada par, como en `audit/a5_ablacion.py`, el recall por
  clúster pasa de 0,635 a 0,944 (la auditoría publicó 0,636 y 0,943 con los datos
  anteriores), las personas exactas de 60,5 % a 92,2 % y los clientes mezclados de 7 a 0.
  La brecha del apellido de casada en personas exactas pasa de −18,4 puntos [−26,4, −9,6]
  a −3,6 [−8,8, +1,4] (no significativa); la de los apodos, de −15,6 a −8,7 (sigue
  significativa).
- **El umbral en tus manos** (v3 en la ciega 3): al umbral congelado (19,9 bits), 24 pares
  unidos por error, 22 de ellos solo por transitividad; con 5 bits, 133 (105 por
  transitividad) y 8 de los 14 clientes mezclados cuelgan de un puente. El umbral de menor
  costo en esta prueba es 23 bits (costo 402 frente a 528 del congelado), pero solo se
  conoce después de mirar la verdad.

## Trabajo futuro

- **Quinta prueba ciega:** las ciegas 1 a 4 ya se miraron. Cualquier corrección nueva
  necesita otra prueba que nadie haya visto. La primera candidata es el grafo: mirar la
  forma de anillo antes que el tamaño, para no tomar por relleno un anillo grande
  (ciega 4).
- **Anillos por su forma, no solo por su tamaño:** en la [prueba ciega 4](#prueba-ciega-4)
  el grafo residencial tomó por relleno tres anillos de celular de 7 clientes, porque un
  contacto compartido por más de 6 clientes es relleno y esa regla va antes que la de forma
  de anillo. El grafo debe reconocer un anillo por su forma (registros recientes, por canal
  digital, sin validar, en un valor que los clientes casi no usan en sus otros registros,
  entre personas sin relación) y reservar "relleno" para valores genéricos o compartidos
  sin esa forma. Necesita una prueba ciega 5.
- **Umbral estable:** elegirlo con remuestreo del desarrollo (por ejemplo, la mediana de
  los umbrales de menor costo) en lugar de un solo mínimo, que varía con la muestra.
- **Híbrido solo con "mismo documento"** y recalibración con una muestra etiquetada de la
  población real.
- **Escenario ciego para el hito 3:** un generador de patrones sospechosos escrito sin
  conocer el clasificador (anillos con familiares o testaferros, contactos reutilizados en
  el tiempo).
- **Calibrar la revisión de puentes al umbral congelado** con un desarrollo que tenga
  uniones erróneas, en lugar del diagnóstico sobre la ciega 2.
- **Detalles menores pendientes** (de la [verificación del hito 6](audit/verificacion_hito6.md)):
  guardar el recall perdido por puentes en cada semilla del hito 3; desglosar por qué la
  regla "documento o nombre+fecha" pierde precisión a 1 millón (homónimos frente a
  documentos repetidos por el generador); validar con una muestra etiquetada el traslado
  de las bandas de zona gris a la previa 1/N del tiempo real; agregar meta viewport a los
  tableros HTML de Splink en `docs/resultados/`, que desbordan en celular. (Hecho después
  de v1.0: la muestra de pares de `tests/test_demo.py` ya no cambia con la fecha, porque
  fija el reloj de Faker.)

## Cómo correrlo

Requiere [uv](https://docs.astral.sh/uv/). uv instala Python 3.11 si hace falta.

```bash
uv sync                                       # entorno y dependencias
uv run playwright install chromium            # una sola vez, para las capturas PNG
uv run pytest                                 # pruebas (sin internet)
uv run python scripts/hito1_fake1000.py       # hito 1 completo -> reports/ (~1,5 min)
uv run python scripts/hito2_colombia.py       # hito 2 completo -> reports/hito2/ (~2,5 min)
uv run python scripts/validacion.py           # prueba ciega + FEBRL3 -> reports/validacion/
uv run python scripts/hito2b.py desarrollar   # hito 2b: modelo v2 -> reports/hito2b/
uv run python scripts/hito2b.py evaluar       # v2 congelado en prueba normal y ciegas
uv run python scripts/hito3.py                # hito 3 -> reports/hito3/
uv run python scripts/hito3.py --captura-universo  # PNG de Cosmograph (tras publicar)
uv run python scripts/hito5.py tiempo-real    # hito 5: "¿ya es cliente?" -> reports/hito5/
uv run python scripts/escala.py --todos       # escala: 100 mil y 1 millón (~10 GB de RAM)
uv run python scripts/hito5.py escala         # tabla y gráficos de escala
uv run python scripts/servicio_local.py       # servicio local en http://127.0.0.1:8000/docs
uv run python scripts/hito6.py desarrollar    # hito 6: modelo v3 -> reports/hito6/
uv run python scripts/hito6.py evaluar        # v3 congelado: prueba normal y ciega 3
uv run python scripts/hito6.py tiempo-real    # precisión con 1 %, 10 % y 50 % de clientes
uv run python scripts/hito6.py hito3          # hito 3 con 8 pares de semillas
uv run python scripts/hito6.py escala         # 100 mil y 1 millón con el v3 congelado
uv run python scripts/publicar_resultados.py --hito 1   # o 2, validacion, 2b, 3, 5, 6: a docs/resultados/
```

La primera ejecución del hito descarga fake_1000 y lo guarda en `data/raw/`.

## Estructura

```
src/identidades/   datos, modelo, bloqueo, evaluación, tableros y flujo del hito 1;
                   sinteticos, estandarizacion, modelo_co y flujo_hito2 (hito 2);
                   errores_ciegos, modelo_febrl y flujo_validacion (validación);
                   estandarizacion_v2, modelo_co_v2, errores_ciegos_2 y flujo_hito2b (2b);
                   escenario_hito3, registro_oro, grafo_compartido, puentes y flujo_hito3 (3);
                   tiempo_real, servicio, escala y flujo_hito5 (5); demo (exporta el modelo);
                   modelo_co_v3, linea_base, calibracion, errores_ciegos_3 y flujo_hito6 (6)
scripts/           puntos de entrada
tests/             pruebas con pytest
notebooks/         solo exploración
docs/              descripción del caso y GitHub Pages (docs/resultados/)
audit/             informe de la auditoría independiente (registro, no se modifica)
data/, reports/    datos y salidas de trabajo (no versionados)
```

## Regla de datos

Este repositorio **nunca usa datos reales de clientes**. Solo datasets públicos de
demostración (Splink, FEBRL) o datos sintéticos generados con Faker.
