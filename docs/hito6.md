# Hito 6: correcciones post-auditoría

[← Volver a la portada](index.md) ·
[Detalle en el informe técnico](https://github.com/stous1/identity-resolution/blob/main/INFORME_TECNICO.md#hito-6-correcciones-post-auditoría) ·
[Informe de auditoría](https://github.com/stous1/identity-resolution/blob/main/audit/INFORME.md)

> **Cifras de la v1.1.1.** Los generadores dependían de la fecha del día (Faker); desde la
> v1.1.1 usan una fecha fija y todas las evaluaciones de esta página se volvieron a correr
> con los mismos modelos congelados. Las cifras de abajo son las nuevas; la tabla de lo que
> cambió está en [v1.1.1](v111.md).

Una sesión de auditoría independiente revisó los hitos 1 a 5 sin haber escrito el código.
No encontró fugas de etiquetas y reprodujo todas las cifras. Pero mostró que varias
interpretaciones atribuían al modelo lo que explicaban las propiedades del generador
sintético. Este hito corrige eso con las mismas reglas de siempre: todo se decide en
desarrollo, el modelo se congela y se mide una sola vez en una prueba ciega nueva.

## Qué cambió

1. **Generador con historia:** mudanzas (dirección nueva y, en la mitad de los casos, otra
   ciudad) y apellidos de casada, con divorcio o nuevo matrimonio
   (`sinteticos.agregar_historia`). Sin esto, el modelo aprendía que "municipio distinto"
   no ocurre nunca en la misma persona y lo convertía en un veto.
2. **Modelo v3 sin vetos extremos:** un piso a las probabilidades m hace que ningún campo reste más
   de B bits. B se eligió en desarrollo entre 5 y 20: **10 bits** (los valores de 10 a 20
   empatan en costo y se toma el más estricto). El peor peso negativo pasa de −47,9 bits
   (v1, municipio) y −72,6 (v2, apellido de casada) a **−10,0** (v3, fecha a más de un año).
   Con mudanzas en los datos, EM ya no aprende vetos extremos; el piso es la red de
   seguridad. Eso no impide que un campo decida solo: en la ciega 3, el v3 a su umbral
   rechaza **237** pares verdaderos por un solo campo (fecha 74, documento 65), frente a
   171 del v2; con el umbral del v2, el v3 rechaza 136.
3. **Prueba ciega 3:** generador escrito por un subagente nuevo, sin acceso a la
   estandarización, los modelos, los generadores anteriores, la documentación ni la
   auditoría. Que sea posterior al congelamiento solo lo respalda el orden de los commits
   (`af22bb0` del modelo a las 17:00:33, `de2ff5a` del generador a las 17:00:46): prueba el
   orden de los commits, no el de la escritura. El tag `hito6-congelado` sí garantiza que
   el v3 no cambió después. 2.000 personas, 5.181 registros (con la fecha fija de la
   v1.1.1), con mudanzas (365 personas), apellido de casada (200), documento alterado
   (585), registros sin documento (262), datos de familiares u otros clientes digitados por
   error (132).
4. **Línea base** determinística e **híbrido** en todas las evaluaciones.
5. **Calibración** isotónica sobre el peso, ajustada en desarrollo, y **zona gris por
   bandas de peso**.
6. **Escala y tiempo real** con el modelo congelado, y precisión según la prevalencia.
7. **Hito 3** repetido con 8 pares de semillas.

Desarrollo del v3: el del hito 2 con historia (1.200 personas) más las ciegas 1 y 2
completas (ya se habían visto, así que solo sirven como desarrollo): 13.919 registros de
5.200 personas.
Umbral elegido por costo (10·FP + FN): 0,999999.

## Prueba ciega 3 (por clúster, IC 95 % por bootstrap de personas)

| Modelo congelado | Precisión | Recall | Personas exactas |
|---|---|---|---|
| v1 (`hito2-congelado-r1`) | 0,995 [0,978 – 1,000] | 0,715 [0,692 – 0,738] | 68,3 % |
| v2 (`hito2b-congelado`) | 0,996 [0,977 – 1,000] | **0,972** [0,966 – 0,979] | **95,4 %** |
| **v3 (`hito6-congelado`)** | 0,996 [0,977 – 1,000] | 0,955 [0,947 – 0,963] | 92,9 % |

![Evolución v1, v2 y v3](resultados/hito6/evolucion.png)

- **El v1 vuelve a caer por los vetos:** 1.320 pares verdaderos quedan bajo el umbral
  solo por el municipio o la dirección (personas que se mudaron); si ese campo fuera
  neutral, se unirían.
- **El v3 queda por debajo del v2 en esta prueba.** Diferencia pareada v3 − v2: recall
  −1,7 puntos [−2,3, −1,2] y F1 −0,9 [−1,2, −0,6], las dos significativas; precisión −0,01
  [−0,04, 0,00]. Con los datos anteriores a la v1.1.1, la diferencia de F1 no era
  significativa. El desarrollo del v3 eligió 0,999999 (≈20 bits), 6,6 bits más alto que el
  0,9999 del v2.
- **Diagnóstico del umbral** (no es cifra principal: la ciega 3 ya se había mirado y el
  umbral congelado no cambia). Con el umbral 0,9999 del v2, el v3 tiene **más recall que el
  v2**: 0,975 contra 0,972 (+0,2 puntos [+0,1, +0,5], significativa); personas exactas
  +0,15 [−0,1, +0,45], precisión −0,4 [−1,6, 0,0] y F1 −0,1 [−0,7, +0,2], no
  significativas. **Se confirma que la causa principal es el umbral**, aunque con los datos
  nuevos la ventaja del v3 a ese umbral es menor (antes, +0,6 puntos de recall). La
  auditoría ya había mostrado que el umbral "elegido en desarrollo" varía bastante con la
  muestra. [diagnostico_umbral.json](resultados/hito6/diagnostico_umbral.json)
- **Prueba normal (con historia, 800 personas):** v3 precisión 1,000 y recall 0,998; v2
  0,998 y 0,992; v1 1,000 y 0,939. Ahí el veto del v2 en el apellido de casada deja 19
  pares verdaderos sin unir (mujeres que cambiaron de apellido de casada); el v3, ninguno.
  Esa robustez **solo se observa en la prueba normal**, que usa el mismo mecanismo de
  historia con que se desarrolló el v3. En la ciega 3 el veto del v2 afecta a 17 pares, y
  a sus umbrales congelados **el v2 reconstruye más personas exactas** que el v3 (95,4 %
  contra 92,9 %; −2,5 puntos [−3,3, −1,8], significativa).

## Equidad en la ciega 3 (v3, personas exactas)

| Grupo | Exactas | Frente a | Diferencia [IC 95 %] | ¿Significativa? |
|---|---|---|---|---|
| Mujer (994) | 92,5 % | 93,3 % hombre | −0,9 [−3,1, +1,4] | No |
| Apellido de casada (200) | 89,5 % | 93,3 % sin él | −3,8 [−8,5, +0,2] | No |
| Con apodo (119) | 90,8 % | 93,0 % sin apodo | −2,3 [−8,1, +2,6] | No |
| Con mudanza (365) | 90,1 % | 93,5 % sin mudanza | −3,4 [−6,8, +0,1] | No |
| Dirección rural (208) | 96,2 % | 92,5 % urbana | +3,6 [+0,4, +6,3] | **Sí** |

- **Con el v3 no se detecta brecha de género:** −0,9 puntos [−3,1, +1,4]; el intervalo
  admite hasta unos 3 puntos, así que no se puede afirmar que no la haya. Con el v2
  tampoco (−1,3 [−3,2, +0,6]; con los datos anteriores era significativa). Con el v1, la
  brecha de las mudanzas es de −22,3 puntos y la del apellido de casada de −9,3.
- **La brecha del apellido de casada ya no es significativa con el v3** (−3,8 puntos
  [−8,5, +0,2]; con los datos anteriores era −4,8, significativa). Con el v2 sigue siéndolo
  (−4,3 [−8,4, −0,7]). La única brecha significativa del v3 es que las direcciones
  urbanas quedan 3,6 puntos por debajo de las rurales. Con una sola muestra, brechas de
  este tamaño cambian con los datos: son señales para vigilar, no hallazgos firmes.
- Diagnóstico (no son grupos de población): algún registro sin documento −5,0 puntos y
  documento alterado −6,6 (las dos significativas).

![Equidad en la ciega 3](resultados/hito6/equidad_ciega3.png)

## Línea base y dónde aporta Splink

Las reglas usan la misma estandarización que el modelo y unión transitiva. El **híbrido**
une primero con las reglas ("documento o nombre+fecha") y deja a Splink el resto. El
**híbrido estricto** además prohíbe unir dos registros con documentos distintos.

| Ciega 3 (por clúster) | Precisión | Recall | F1 | Personas exactas |
|---|---|---|---|---|
| Regla: mismo documento | 0,996 | 0,679 | 0,808 | 65,7 % |
| Regla: documento o nombre+fecha | 0,994 | 0,856 | 0,920 | 82,2 % |
| **Splink v3** | **0,996** | 0,955 | 0,975 | 92,9 % |
| Híbrido: reglas y Splink para el resto | 0,988 | **0,975** | **0,982** | **95,4 %** |
| Híbrido estricto | 0,990 | 0,904 | 0,945 | 87,4 % |

**Dónde aporta Splink** (recall por clúster, ciega 3):

| Segmento de personas | Regla documento o nombre+fecha | Splink v3 | Híbrido |
|---|---|---|---|
| Documento siempre igual (1.280) | 1,000 | 0,976 | 1,000 |
| Algún registro sin documento (215) | 0,739 | 0,943 | 0,963 |
| Documento alterado (505) | 0,758 | 0,940 | 0,956 |

- En toda la ciega 3, Splink supera a la mejor regla por **+0,055 de F1** [+0,042,
  +0,066] (cifra global, de todos los segmentos; con los datos anteriores, +0,065), y por
  +0,048 en la prueba normal. Por segmento, el aporte está donde el documento falla: sin
  documento o con documento alterado, Splink recupera el 94 % y la regla el 74–76 %.
- **Donde el documento es igual, la regla "mismo documento" empata con Splink** (precisión
  0,996 y recall 1,000, frente a 0,991 y 0,976). El híbrido: más recall (+2,0 puntos,
  significativo) y **pierde precisión** (−0,8 puntos [−2,3, 0,0], significativa por poco);
  su F1 es mayor que el de Splink (+0,7 puntos [−0,1, +1,1]), pero la diferencia no es
  significativa. Con los datos anteriores perdía 3,2 puntos de precisión: la regla de
  nombre+fecha une personas distintas (homónimos y datos ajenos digitados por error) y el
  híbrido las hereda, en una cantidad que depende de la muestra. Con el error caro (FP)
  pesando 10 veces más, Splink solo sigue siendo la opción por defecto.
- El híbrido estricto pierde recall: los documentos alterados son justamente los que
  Splink sabe unir.

![Línea base](resultados/hito6/linea_base.png)

## Calibración y zona gris

La probabilidad de Splink no es una probabilidad en la zona de decisión. En la prueba
normal, los pares con p entre 0,9 y 0,9999 (22 pares, media 0,982) son verdaderos solo el
9 % de las veces: son familiares. Se ajustó en desarrollo una regresión isotónica de la
verdad sobre el peso, y con ella tres **bandas de peso**, congeladas con el modelo:

| Banda | Peso | En prueba normal | En ciega 3 |
|---|---|---|---|
| Rechazar (calibrada < 0,1) | < 5,2 bits | 593 pares, 0 % verdaderos | 1.892 pares, 4,3 % verdaderos |
| **Revisar (zona gris)** | 5,2 a 19,9 bits | 8 pares, **75 %** verdaderos | 436 pares, **94 %** verdaderos |
| Aceptar (umbral de operación) | ≥ 19,9 bits | 2.131 pares, 100 % | 5.752 pares, 99,97 % |

![Confiabilidad](resultados/hito6/confiabilidad.png)

- **Como triaje, las bandas funcionan:** la zona gris concentra los casos dudosos, y en la
  ciega 3 contiene 412 pares verdaderos que el umbral no acepta. Son el trabajo del agente
  de revisión.
- **Como probabilidad, la calibración no se transfiere, y fuera de muestra empeora.** En
  la prueba normal parece razonable (con muy pocos pares por intervalo), pero en la ciega 3
  queda **subconfiada**. En la zona [0,9, 0,9999) de la ciega 3, la probabilidad **sin
  calibrar** (media 0,989) se acerca más a lo observado (83 % de verdaderos) que la
  calibrada (media 0,29). Lo que hay en cada banda depende de la población: en
  desarrollo, los pesos medios son sobre todo familiares; en la ciega 3, personas reales con
  errores difíciles. La probabilidad calibrada solo vale para una población parecida a la
  de desarrollo; con datos nuevos hay que recalibrar con una muestra etiquetada.

## Tiempo real: precisión según la prevalencia

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

- **La precisión con 1 % de clientes es frágil:** con los datos anteriores a la v1.1.1 hubo
  una falsa alarma en 1.500 personas nuevas y la precisión con 1 % de clientes era 0,938;
  con los datos nuevos no hubo ninguna y es 1,000. Una sola falsa alarma mueve la cifra 6
  puntos. La cifra de 0,999 del hito 5 solo vale para una mezcla 50/50.
- **En la población de la ciega 3 el recall baja a 0,923**: de las consultas de clientes
  existentes, 79 van a revisión y 35 quedan como nuevas; una se asigna a un cliente
  equivocado (por eso 0,999). La latencia mediana fue de 71 a 83 ms por consulta.

**Zona gris por bandas.** "Revisar" ya no es p ≥ 0,9 sin calibrar, sino la banda congelada
en desarrollo (peso ≥ 5,2 bits), trasladada a la previa 1/N de cada base conservando la
evidencia de los campos (5,7 y 5,5 bits). "Cliente" no cambia, así que precisión y recall
tampoco. Cambia la cola de revisión, sobre las mismas consultas:

| Población | Revisión con p ≥ 0,9 | Con bandas | Existentes que pasan a "nuevo" |
|---|---|---|---|
| Generador del hito 2 | 27 | **19** | 0 |
| Generador de la ciega 3 | 91 | **87** | 2 |

Desde la v1.1.1, el servicio local usa por defecto el v4 con sus propias bandas
(`--modelo v3` usa este; `--modelo v2` reproduce el del hito 5).

## Escala con el modelo congelado

El hito 5 reentrenaba el modelo en cada tamaño. La auditoría mostró que eso degrada la
precisión: al crecer los datos, el u de los campos casi únicos (teléfono, documento, correo)
baja, cada coincidencia suma más bits, y los familiares que comparten teléfono y dirección
(campos que no son independientes) acumulan más evidencia de la que quita la previa.
**Reentrenar en cada tamaño degrada la precisión**: de 0,992 con 10 mil registros a 0,976
con 300 mil (auditoría, §6), y a 10 millones se proyectaba ~0,94. Aquí se usa el **v3
congelado**: solo se vuelve a estimar λ, con el mismo bloqueo exacto y los mismos datos del
hito 5.

| Registros | Reentrenado (hito 5) P / R | **Congelado (v3)** P / R | Personas exactas (congelado) | Tiempo total | Memoria pico |
|---|---|---|---|---|---|
| 99.837 | 0,981 / 0,997 | **0,999 / 0,996** | 99,3 % | 14,4 s | 0,8 GB |
| 996.688 | 0,970 / 0,996 | **0,999 / 0,995** | 99,2 % | 128 s | 7,1 GB |

- **Ojo: la tabla compara a la vez modelo y umbral.** La columna del hito 5 es el esquema
  v2 reentrenado con umbral 0,9999; la del hito 6, el v3 congelado con umbral 0,999999. Un
  umbral más alto ya sube la precisión por sí solo, así que la tabla no aísla el efecto de
  congelar. Eso lo aísla la auditoría (§6): el v2 congelado, al mismo umbral, mantiene la
  precisión plana de 10 mil a 300 mil registros.
- **Con el modelo congelado, la precisión no cae entre los dos tamaños medidos** (0,999
  en ambos; los falsos positivos se multiplican por 9,9 con 10 veces más datos), y no hace
  falta entrenar: el tiempo es casi todo de preparación (99 de 128 s).
- **Recomendación:** entrenar m y u una vez con una muestra y congelarlos. Si se reentrena,
  hay que recalibrar el umbral con una muestra etiquetada en cada orden de magnitud.
- **Línea base a escala:** la regla "documento o nombre+fecha" pierde precisión con el
  volumen (0,994 con 100 mil, 0,942 con 1 millón: más personas distintas con el mismo
  nombre y fecha), y el híbrido la hereda (0,939). Splink congelado mantiene 0,999. La
  regla "mismo documento" sigue en 0,997 de precisión, pero con recall 0,62. (Escala de la
  v1.1.1: datos regenerados con la fecha fija, sin la caché anterior.)

## Hito 3 con varias semillas

Ver la tabla en la [página del hito 3](hito3.md). Con el v3 congelado las cifras son
parecidas (precisión de la unión 1,000 ± 0,001, exactitud del grafo 98,2 % ± 0,6, mezclas
evitadas 36 % ± 12 %).

## Detalle

[metricas.json](resultados/hito6/metricas.json) ·
[desarrollo.json](resultados/hito6/desarrollo.json) ·
[calibracion.json](resultados/hito6/calibracion.json) ·
[tiempo_real.json](resultados/hito6/tiempo_real.json) ·
[diagnostico_umbral.json](resultados/hito6/diagnostico_umbral.json) ·
[escala.json](resultados/hito6/escala.json) ·
[hito3_semillas.json](resultados/hito6/hito3_semillas.json) ·
[muestra de la ciega 3](resultados/hito6/ciega3_muestra_registros.csv)
