# Hito 3: registro de oro, grafo de identidad compartida y puentes

[← Volver a la portada](index.md) ·
[Detalle en el informe técnico](https://github.com/stous1/identity-resolution/blob/main/INFORME_TECNICO.md#hito-3-registro-de-oro-grafo-de-identidad-compartida-y-puentes)

**[Abrir el universo de registros en Cosmograph →](hito3_universo.html)**

[![Universo de registros del hito 3](resultados/hito3/universo.png)](hito3_universo.html)

> **Cifras de la v1.1.1.** El escenario dependía de la fecha del día (Faker); desde la
> v1.1.1 usa una fecha fija y todo el hito se volvió a correr con el v2 congelado. El
> universo publicado ya no es el del caso "Esther" (ese escenario se reproduce con
> `diagnostico_v11.caso_esther` y está en la [ficha de cliente único](ficha.html)). Tabla de
> cambios en [v1.1.1](v111.md).

Escenario con historia en el tiempo (cambios de celular, correo y domicilio), metadatos por
registro (fecha, canal y validación) y datos compartidos con verdad conocida: relleno,
hogares y patrones sospechosos (anillos y suplantaciones). Reglas y umbrales elegidos en un
escenario de desarrollo y medidos en otro de prueba (2.000 personas, 4.878 registros), con
los clientes del modelo v2 congelado.

**Las cifras de esta página son de un par de semillas (3030/3131).** Repetido con 8
pares (hito 6, media ± DE):

| Cifra | Semilla publicada | 8 semillas |
|---|---|---|
| Peor brecha del registro de oro al techo | 4,5 puntos | 4,1 ± 0,4 (3,7 – 4,7) |
| Exactitud del grafo compartido | 99,1 % | 98,3 % ± 0,6 (97,6 – 99,1) |
| Clientes mezclados al umbral congelado | 2 | 1,4 ± 0,7 (0 – 2) |
| Mezclas evitadas cortando puentes (umbral 0,9) | 40 % | 35 % ± 7 % (28 – 45) |

La regla de supervivencia elegida para documento, nombres, fecha y dirección cambia con la
semilla; la de apellidos ("más frecuente"), celular y correo ("validado") es estable. El
recall perdido al cortar puentes solo se midió con la semilla publicada (tabla de abajo). Detalle en
[hito3_semillas.json](resultados/hito6/hito3_semillas.json).

## Registro de oro (prueba, semilla publicada)

| Campo | Regla elegida | Acierto | Techo alcanzable |
|---|---|---|---|
| Documento | Fuente más confiable | 96,0 % | 97,8 % |
| Nombres | Más frecuente | 93,6 % | 96,8 % |
| Apellidos | Más frecuente | 94,0 % | 96,9 % |
| Fecha de nacimiento | Más reciente | 100 % | 100 % |
| Celular | Validado más reciente | 80,0 % | 83,2 % |
| Correo | Validado más reciente | 83,5 % | 86,2 % |
| Dirección | Fuente más confiable | 84,2 % | 88,7 % |

![Registro de oro por regla](resultados/hito3/registro_oro.png)

## Grafo de identidad compartida

De los 425 grupos de datos compartidos de prueba (376 de hogar, 36 sospechosos, 10 de
relleno y 3 coincidencias), el 99,1 % queda bien clasificado con reglas explicables (los 36
sospechosos, todos). Es una cota optimista: el escenario y el clasificador los escribió la
misma persona, y el escenario no tiene la realidad residencial que agrega la
[v1.1](v11.md), donde este clasificador marca como sospechosos al 39 % de los grupos
benignos.

## Puentes

| Umbral | Política | Clientes mezclados | Recall perdido |
|---|---|---|---|
| 0,9999 (congelado) | No cortar | 2 → 2 | 0 |
| 0,99 | Cortar puentes con peso < 25 | 4 → 3 | 0,04 % |
| 0,9 | Cortar puentes con peso < 25 | 10 → 6 | 0,04 % |

El caso 109-844 del hito 1 y las 3 uniones erróneas del modelo v2 en la prueba ciega 2
cuelgan de un puente débil. La [cola de revisión](resultados/hito3/cola_revision.csv)
(6 puentes débiles y 37 grupos sospechosos) es la entrada del agente del hito 4.

Detalle en [metricas.json](resultados/hito3/metricas.json).
