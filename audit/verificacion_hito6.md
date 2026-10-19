# Verificación rápida del hito 6

Fecha: 18 de octubre de 2026 · Commit verificado: `15ca01c` (rama `main`, árbol limpio).

Esto es una verificación rápida, no una auditoría completa. No reentrené ni volví a correr
ningún modelo. Lo único que corrí fue `pytest tests/test_hito6.py -m "not integracion"`
(15 pruebas pasan) y algunas lecturas de los JSON. No se modificó ningún archivo; este es
el único archivo nuevo.

**Alcance.** Contrasté contra los JSON publicados (`docs/resultados/hito6/*.json`,
`hito5/tiempo_real.json`, `hito5/escala.csv`) y contra `audit/INFORME.md`:

- todas las cifras de `docs/hito6.md`;
- la sección "Hito 6" del README y la tabla "Qué encontró la auditoría";
- las líneas que cambió el commit `15ca01c` en el README, `index.md`, `hito2.md`,
  `hito2b.md`, `hito3.md` y `hito5.md`.

No volví a revisar las cifras de los hitos 1 a 5 que la auditoría ya había verificado
(114 de 115).

## 1. Cifras contra los JSON

**Coinciden** con el redondeo publicado:

- La ciega 3: precisión, recall, IC y personas exactas de v1, v2 y v3.
- Las diferencias pareadas v3 − v2.
- Los 1.456 pares vetados del v1 (753 por municipio y 703 por domicilio).
- Las condiciones de la ciega 3 (356 mudanzas, 181 apellidos de casada, 578 documentos
  alterados, 249 registros sin documento y 131 casos de datos ajenos).
- La prueba normal (v3 0,992; v2 0,986; v1 0,922, y 28 vetos del v2 por apellido de
  casada).
- Las tablas de equidad y de diagnóstico.
- La línea base y los segmentos.
- Las bandas de calibración (5,2 y 19,9 bits; 1.198, 27 y 2.165 pares; 1.717, 479 y 6.001
  pares; 48 % y 91 %).
- Tiempo real: 0,999, 0,994 y 0,938 [0,833 – 1,000]; 0,918; 84 a revisión y 39 nuevas; la
  cota de ≥ 0,82 con la regla del tres.
- Escala: P y R, 99,2 %, 129 s, 100 s y 7,1 GB.
- Hito 3 con 8 semillas: 4,1 ± 0,5; 98,6 ± 0,8; 1,5 ± 1,3 (0 – 4); 31 % ± 18 %
  (13 – 56); los conteos de reglas por campo y los valores del v3.
- El desarrollo: 13.919 registros y 5.200 personas, umbral 0,999999, piso de 10 bits, peor
  peso −10,0 con piso y −10,3 sin piso.

**Discrepancias:**

| # | Dónde | Qué dice | Qué muestran los datos | Gravedad |
|---|---|---|---|---|
| D1 | `docs/hito5.md`, fila 5 de la tabla resumen del README, `docs/index.md` | Con el hito 5, "con 10 % de clientes, 0,994, y con 1 %, **0,94**" | Esas cifras son del **v3** (hito 6, base de 2.705 clientes, umbral 0,999999). Con las tasas del propio hito 5 (`hito5/tiempo_real.json`: 993/1.000 aciertos y 1/1.000 falsas alarmas) salen **0,991 y 0,909**, que es lo que decía la auditoría (M5). La corrección subestima la caída del modelo del hito 5. | Media |
| D2 | Hito 6 (README y Pages), línea base por segmento | "Donde el documento es igual, la regla es mejor (recall 1,000 contra 0,978) y gana en costo" | La regla de la tabla es "documento o nombre+fecha". En ese segmento de la ciega 3 su precisión es 0,962 y la de Splink, 0,993. Estimado por par verdadero, el costo 10·FP + FN es ≈ 0,39 para la regla frente a ≈ 0,09 para Splink: **la regla pierde**. Solo "mismo documento" (P 0,991, R 1,000, costo ≈ 0,087) empata con Splink. | Media |
| D3 | Tabla resumen del README y `index.md` | "Splink aporta +0,065 de F1 sobre reglas **donde el documento falla**" | +0,065 es el F1 global de toda la ciega 3. Lo que se mide "donde el documento falla" es el recall por segmento (0,95–0,97 frente a 0,75–0,76). | Baja |
| D4 | Escala, hito 6 | 99.088 registros: "13 s" en total | La suma de las etapas en `escala.json` da 12,4 s. | Baja |
| D5 | Tabla resumen del README (hito 3) y `docs/hito3.md` | Puentes que evitan mezclas "sin perder recall" en 8 semillas | `hito3_semillas.json` no guarda el recall perdido. Solo se puede comprobar para la semilla publicada. | No verificable |

## 2. Hallazgos graves de la auditoría: ¿quedaron corregidos?

- **A1 (vetos de 43 a 73 bits): corregido.**
  - En el v3, el peor peso es −10,0 (`metricas.json → pesos_extremos.v3`), y sin piso EM
    llega a −10,3 (`desarrollo.json`).
  - En la prueba normal, 0 pares quedan vetados por el apellido de casada, frente a 28 en
    el v2.
  - `git diff hito6-congelado HEAD` no toca los archivos congelados.
  - Queda algo por resolver: en la ciega 3 sigue una brecha significativa del apellido de
    casada, de −4,8 puntos.
- **A2 (la precisión cae a escala por reentrenar): corregido en el texto y en la
  medición.**
  - Con el modelo congelado, `escala.json` da P 0,9976 y 0,9983, frente a 0,9815 y 0,9714
    reentrenado. `hito5.md` ya no habla de homónimos.
  - Matiz: la tabla del hito 6 compara el v2 reentrenado a 0,9999 con el v3 congelado a
    0,999999, así que mezcla tres cambios a la vez (congelar, el modelo y el umbral).
  - La prueba aislada de que congelar estabiliza la precisión sigue siendo la de la
    auditoría (§6, v2 congelado al mismo umbral).
- **A3 (probabilidades sobreconfiadas): parcialmente corregido.**
  - Lo que sí existe: la calibración isotónica, las bandas y un diagrama fuera de muestra
    (`calibracion.json`, `metricas.json → calibracion`).
  - Las bandas sirven como triaje: en la ciega 3, la zona gris tiene un 91 % de pares
    verdaderos.
  - Pero la calibración no se transfiere a la ciega 3, y el README lo reconoce.
  - Además, "¿ya es cliente?" **no usa las bandas.** `tiempo_real.ZONA_GRIS = 0.9` es una
    probabilidad sin calibrar, y `flujo_hito6.tiempo_real` construye el `Vinculador` sin
    ellas.
  - Por eso la tabla del README ("bandas de peso para la zona gris") se aplica solo a la
    evaluación por lotes.

De paso, los hallazgos de gravedad media:

- **M1 (línea base):** corregido.
- **M2 (umbral inestable):** no corregido, solo se reporta. El umbral sigue siendo un
  único mínimo de costo, y el README lo deja en "Trabajo futuro".
- **M3 (hito 3 con una sola semilla):** corregido, ahora con 8 semillas.
- **M4 (diseño circular del hito 3):** solo se advierte.
- **M5 (tiempo real con 50 % de clientes):** corregido para el v3, pero ver D1.
- **B3:** corregido.

## 3. Conclusiones del README que van más allá de los datos

1. **"Modelo v3 sin vetos".** Es cierto en magnitud: ningún campo resta más de 10 bits.
   Pero con la misma definición de veto del código (`flujo_hito6.pares_vetados`: un par
   verdadero que pasaría el umbral si su peor campo fuera neutral), en la ciega 3 el v3
   tiene **257** pares vetados y el v2, 197. La mayoría son de fecha (103) y documento
   (53). El piso limita cuánto pesa cada campo, pero no evita que un solo campo decida,
   y el umbral más alto hace que pase más seguido.
2. **"La causa principal es el umbral"** (de que el v3 pierda recall frente al v2). No se
   midió: no hay ninguna evaluación del v3 a 0,9999. En desarrollo, pasar de 0,9999 a
   0,999999 solo cuesta 0,0006 de recall (`reports/hito6/curva_costo_desarrollo.csv`).
   Es plausible, porque la zona gris de la ciega 3 tiene 438 pares verdaderos, pero
   habría que presentarlo como hipótesis.
3. **"Lo que sí gana el v3 es robustez".** Solo se ve en la prueba normal, que usa el
   mismo `agregar_historia` con el que se desarrolló el v3, un mecanismo pensado para
   activar el veto del v2. En la ciega 3, ese veto del v2 afecta solo a 13 pares, y el v2
   reconstruye más personas exactas que el v3 (−1,15 puntos para el v3, significativo).
   Aun así, el v3 queda como modelo de tiempo real y de escala sin que una prueba ciega lo
   respalde frente al v2.
4. **"Con el v3 no hay brecha de género"** y **"no había base para hablar de brecha de
   género"**.
   - Que la diferencia no sea significativa no quiere decir que no exista: el IC
     [−3,4, +0,7] admite una brecha de unos 3 puntos.
   - En la misma ciega 3, el v2 sí tiene una brecha significativa (−2,2), y el v1 también
     la tiene en recall (−4,7 [−9,5, −0,2]).
   - Lo que los datos permiten decir es "con el v3 no se detecta brecha".
5. **"Con el modelo congelado, la precisión no cae con el volumen".** Se apoya en dos
   tamaños (99 mil y 996 mil), y la comparación mezcla otros cambios (ver A2). Los FP se
   multiplican por 7,1 cuando los datos crecen 10 veces. Sirve como observación, no como
   regla general. Para 10 millones, la cifra de referencia sigue siendo la proyección de
   la auditoría.
6. **La calibración.**
   - Que "en la prueba normal es razonable" se apoya en bins de 3 a 8 pares.
   - Falta un matiz: en la ciega 3, la probabilidad **sin calibrar** acierta más que la
     calibrada. En [0,9, 0,9999), la media sin calibrar es 0,987 y la frecuencia
     observada, 81 %; la calibrada da en promedio 0,27.
   - Es decir, fuera de muestra la recalibración empeoró la probabilidad.
7. **"Escrita después de congelar el v3"** (la ciega 3). La única evidencia es el orden de
   los commits: `af22bb0` a las 17:00:33 y `de2ff5a` a las 17:00:46, con 13 s entre uno y
   otro. Eso prueba en qué orden se hicieron los commits, no en qué orden se escribieron
   los archivos. No lo contradice, pero no lo demuestra.
8. **La explicación de por qué la regla pierde precisión a escala** ("más personas
   distintas con el mismo nombre y fecha"). No hay un desglose que la respalde. Es
   coherente con que la regla de documento casi no pierda precisión (0,9997 → 0,9973),
   pero no está medido.

**En resumen:** las cifras del hito 6 están bien transcritas. Hay una cifra mal atribuida
al hito 5 (D1) y una afirmación sobre la regla que los datos contradicen (D2). De los
hallazgos graves, A1 y A2 quedaron corregidos, y A3 solo en parte, porque las bandas no
llegan al servicio de tiempo real. Lo que más se exagera es la comparación v3 frente a v2:
la única prueba ciega favorece al v2 en recall, y la explicación por el umbral no está
medida.
