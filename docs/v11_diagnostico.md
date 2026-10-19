# v1.1: diagnóstico previo de la realidad residencial

[← Volver a la v1.1](v11.md) · [← Portada](index.md)

Antes de cambiar nada, se revisó cómo tratan el grafo de identidad compartida del hito 3 y
el modelo v3 los casos residenciales y familiares que la v1.1 quiere cubrir. Los ejemplos
están escritos a mano en `src/identidades/diagnostico_v11.py`, y `tests/test_diagnostico_v11.py`
verifica cada hallazgo. Para mirar solo el clasificador, cada persona es un cliente (como
si la unión fuera perfecta). Se usan los parámetros publicados del hito 3
(`max_clientes` = 15, `min_apellido` = 0,5).

## 1. Cómo clasifica el grafo cada caso

| Caso | Lo esperado | Lo que hace el grafo del hito 3 |
|---|---|---|
| Pareja sin apellidos ni teléfono en común, misma casa | normal | **sospechoso**: personas sin apellido común que comparten un dato |
| Pareja casada ("Rincón de Salazar" y "Salazar Mora") | hogar | **sospechoso**: el apellido de casada no se reconoce; de "RINCON DE SALAZAR" solo se miran "RINCON" y "DE" |
| Tres estudiantes en el mismo apartamento ("Apto 502") | convivencia | **relleno**, y la tercera ("Ap 502") queda fuera del grupo |
| Conjunto: seis hogares en torres y apartamentos distintos | normal | **no forma ningún grupo**: cada apartamento es un valor distinto |
| Casa de dos pisos: padres abajo, hijo con su hogar en el "Piso 2" | hogar | los padres salen **sospechosos** por la dirección y por el teléfono fijo (ella usa "de Hernández") y el piso 2 sale **relleno**; las dos mitades de la familia no se conectan |
| La misma casa, sin "Piso 2" (cuatro personas) | hogar | **sospechoso**: solo un tercio de los pares comparte apellido |
| Familia con la convención (hijos "Ramírez Torres") | hogar | hogar (correcto, gracias al apellido del padre) |
| Control: tres desconocidos con el mismo celular | sospechoso | sospechoso (correcto) |

Tres causas explican casi todos los fallos:

1. **Una dirección con complemento no se reconoce.** La expresión de la estandarización v1
   termina en el consecutivo (`# 40-62`); con "Apto 502", "Torre 2", "Interior 3" o "Piso
   2" detrás, no reconoce la dirección y la deja como texto. El grafo marca como genérica
   (relleno) toda dirección sin tipo de vía reconocido. **Toda dirección de apartamento es
   relleno.** Y como cada forma de escribir el complemento es un valor distinto, los
   vecinos de un edificio nunca se ven juntos.
2. **La única señal de hogar es compartir un apellido.** Una pareja no comparte apellidos.
   El apellido de casada tampoco se reconoce, y la partícula "DE" cuenta como apellido: dos
   señoras casadas sin relación ("Vargas de Ospina" y "Cárdenas de Rojas") "comparten"
   apellido.
3. **La sospecha no depende del tipo de dato ni del tamaño del grupo.** Dos personas que
   comparten la casa reciben la misma etiqueta que tres desconocidos con el mismo celular.
   No se miran el canal, la validación ni el tiempo, aunque el escenario los trae.

## 2. El caso "Esther Nancy MONTENEGRO MUÑOZ" del universo

En el [universo del hito 3](hito3_universo.html) aparecen en rojo cinco registros de
"Esther Nancy Montenegro Muñoz", entre ellos "Esthe Rnancy montenegro muñoz". Se
reconstruyó el escenario de prueba (semilla 3131) con la fecha en que se generó el universo
publicado (`diagnostico_v11.caso_esther`):

- Los cinco registros son de la misma persona (la 1057). "Esthe Rnancy" es un error de
  digitación del canal call center: un espacio corrido.
- Un sexto registro, de **otra persona** (la 199, "NATHALIA méndez udque"), lleva el mismo
  documento, 1064372368. El escenario lo inyectó a propósito como **suplantación**: canal
  web, sin validar, de octubre de 2024.

**Conclusión: es una suplantación creada por el escenario, y el clasificador acierta** al
marcar el documento compartido como sospechoso. Lo que confunde es el universo: pinta de
rojo todos los registros del grupo, así que la **víctima** (dueña del documento, con cinco
registros) se ve igual que la **suplantadora**, que tiene uno. La v1.1 las distingue.

**Hallazgo de paso: el escenario del hito 3 cambia con la fecha.** Faker calcula las
fechas de nacimiento desde la fecha de hoy. Con otra fecha cambian las fechas y, con ellas,
parte del resto del sorteo: el mismo escenario y la misma semilla generados otro día dan
registros distintos (el registro 2530 deja de ser de Esther). Las cifras del hito 3 se
reproducen con la fecha fija (`sinteticos_fecha.fecha_fija`). Los generadores de la v1.1
corren siempre con una fecha fija. Los anteriores no se cambian, para no alterar sus datos.

## 3. ¿El v3 ajusta la dirección por frecuencia?

**Sí, pero solo en el nivel de dirección exacta.** En `docs/resultados/hito6/modelo.json`,
el nivel "Exact match on domicilio" tiene `tf_adjustment_column = domicilio` con peso 1.
Las tablas de frecuencia se calculan sobre los datos que se vinculan (en tiempo real,
sobre la base de registros de oro). Los niveles "misma vía, número y placa" y "parecida
(Jaro-Winkler ≥ 0,90)" no tienen ajuste. El municipio y el correo sí lo tienen.

Bits que da el v3 a la dirección en pares típicos, sin el ajuste por frecuencia
(`diagnostico_v11.niveles_direccion_v3`):

| Par | Nivel del v3 | Bits |
|---|---|---|
| Misma casa, otra escritura ("Calle 45 # 12-30" y "Cl 45 # 12-30") | exacta | +11,3 |
| **Mismo apartamento**, otra escritura ("Apto 502" y "Ap 502") | distinta | **−1,7** |
| Mismo edificio, **otro apartamento** | parecida | **+5,4** |
| Mismo conjunto, otra torre | parecida | +5,4 |
| Conjunto con y sin apartamento | distinta | −1,7 |
| Casa: primer piso y "Piso 2" | distinta | −1,7 |
| **Predios distintos** en la misma cuadra ("# 12-30" y "# 12-38") | misma vía, número y placa | **+8,8** |

Dos fallos de diseño: el v3 da más peso a dos vecinos de edificio que a una persona que
escribe su apartamento de dos formas. Y "misma vía, número y placa" no incluye el
consecutivo: es la misma cuadra, no el mismo predio, y aun así suma 8,8 bits.

## Qué hace la v1.1 con esto

- **Generador** con parejas, convivientes, edificios, conjuntos y casas de varios pisos.
- **Modelo v4**, con la dirección separada en predio y unidad.
- **Grafo** con sospecha según el tipo de dato, el tamaño del grupo y el tipo de predio;
  parejas y convención de apellidos; categoría "convivencia probable".
- **Universo** que distingue víctima y suplantador.
