# Resolución de identidades con Splink

**¿Cuáles registros de una base de clientes son la misma persona?** Un modelo probabilístico
(Fellegi-Sunter con Splink y DuckDB) que lo decide, explica cada decisión y se mide contra
la verdad conocida, con pruebas ciegas y una auditoría independiente. Todo con datos
sintéticos.

[![Universo de registros en Cosmograph](resultados/portada.jpg)](hito3_universo.html)

**[Probar la demo →](demo.html)** · **[Ficha de cliente único →](ficha.html)** ·
**[Calculadora de impacto →](calculadora.html)** · [universo residencial](v11_universo.html)

<sub>Cifras de la v1.1.1: los generadores usan una fecha fija y todas las evaluaciones se
recalcularon con los mismos modelos congelados ([qué cambió](v111.md)).</sub>

## En un minuto

- **v1.1, realidad residencial colombiana** ([página](v11.md)): parejas sin apellidos en
  común, convivientes, conjuntos y casas de varios pisos. En la **prueba ciega 4**, el
  modelo v4 (dirección por predio y unidad) sube el F1 de 0,987 a **0,994** frente al v3, y
  el grafo residencial baja las personas inocentes marcadas como sospechosas de 36,7 % a
  **1,6 %**, aunque detecta menos patrones sospechosos (66,7 % de sus personas frente a
  81,6 %).
- **Prueba ciega 3** (modelo v3 congelado, errores de un generador independiente):
  precisión **0,996** y recall **0,955** por clúster; 92,9 % de las personas reconstruidas
  exactamente.
- **Frente a reglas simples:** +0,055 de F1 sobre la mejor regla determinística; la
  ganancia está donde el documento falta o viene alterado.
- **1 millón de registros** en una máquina en 128 s (7,1 GB de pico), con precisión 0,999.
- **"¿Ya es cliente?"** con el v4 en unos 110 ms: recall 0,989 y ninguna falsa alarma en
  1.500 consultas de personas nuevas; con el 1 % de clientes, la precisión es frágil (una
  sola falsa alarma la baja a cerca de 0,94).
- **Auditoría independiente:** sin fugas de etiquetas y con todas las cifras reproducibles;
  sus hallazgos se corrigieron o matizaron en el [hito 6](hito6.md).

| Prueba | Modelo | Precisión | Recall | F1 Splink | F1 mejor regla |
|---|---|---|---|---|---|
| **Ciega 4** | **v4** | **0,995** | **0,993** | **0,994** | |
| Ciega 3 | v3 | 0,996 | 0,955 | 0,975 | 0,920 |
| Ciega 2 | v2 | 1,000 | 1,000 | 1,000 | 0,990 |
| Ciega 1 | v1 | 0,989 | 0,635 | 0,774 | 0,960 |
| FEBRL3 | propio | 1,000 | 0,997 | 0,998 | 0,957 |
| 1 millón de registros | v3 | 0,999 | 0,995 | 0,997 | 0,925 |

![Antes: registros sueltos; después: clientes agrupados por el modelo v3](resultados/gifs/agrupacion.gif)

Limitaciones: datos sintéticos, generadores de errores escritos por agentes de IA y sin
validación con datos reales.

**Más:** [descripción del caso](caso-01-identidades.md) ·
[código e informe técnico](https://github.com/stous1/identity-resolution/blob/main/INFORME_TECNICO.md) ·
[auditoría](https://github.com/stous1/identity-resolution/blob/main/audit/INFORME.md) ·
[verificación del hito 6](https://github.com/stous1/identity-resolution/blob/main/audit/verificacion_hito6.md) ·
[repositorio](https://github.com/stous1/identity-resolution)

## Hitos

- [Hito 1: fake_1000](#hito-1-fake_1000): el flujo completo sobre el dataset de
  demostración de Splink.
- [Hito 2: clientes sintéticos colombianos y estandarización](hito2.md): en la prueba
  normal, precisión 1,000 y recall 0,998 por clúster (con la fecha fija de la v1.1.1, el
  mismo modelo congelado da 1,000 y 1,000). En la **prueba ciega** (modelo congelado,
  errores de un generador independiente), precisión 0,989 y recall 0,635: la cifra
  honesta. FEBRL3: precisión 1,000 y recall 0,997. *La auditoría mostró que ese
  recall se perdió sobre todo por dos vetos aprendidos (municipio y dirección), no por los
  errores de nombre, y que la brecha del apellido de casada no era significativa sin
  ellos.*
- [Hito 2b: corregir y volver a medir a ciegas](hito2b.md): con las correcciones (apellido
  de casada, apodos, nombres cruzados, documento, teléfonos y fechas), en una **segunda
  prueba ciega**, precisión 1,000 y recall 1,000 por clúster; el modelo anterior, en esos
  mismos datos, 1,000 y 0,914.
- [Hito 3: registro de oro, grafo de identidad compartida y puentes](hito3.md): registro de
  oro a menos de 5 puntos del techo alcanzable, grupos de datos compartidos clasificados
  en relleno, hogar o sospechoso (98,3 % ± 0,6 en 8 semillas), puentes que evitan en
  promedio 3 a 4 de cada 10 mezclas, y el
  [universo de registros en Cosmograph](hito3_universo.html).
- [Hito 5: vinculación en tiempo real y escala](hito5.md): "¿ya es cliente?" contra la base
  de registros de oro con precisión 1,000, recall 0,992 y 68 ms de mediana por consulta;
  1 millón de registros en DuckDB en 155 s con 9,1 GB de pico, y el
  [universo grande en Cosmograph](hito5_universo.html) (200 mil registros desde Parquet).
  *Con los datos anteriores a la v1.1.1 hubo una falsa alarma, y con esas tasas la
  precisión sería 0,909 con 1 % de clientes; con los datos nuevos no hubo ninguna.*
- [v1.1: realidad residencial y familiar colombiana](v11.md): [diagnóstico](v11_diagnostico.md),
  generador con predios y hogares, modelo v4 con la dirección en predio y unidad, grafo
  residencial (convivencia probable, multifamiliar, parejas por apellido de casada y por la
  convención de los hijos) y **prueba ciega 4**; [universo residencial](v11_universo.html).
- [v1.1.1: reproducibilidad](v111.md): fecha fija en todos los generadores, todas las
  evaluaciones recalculadas (con la tabla de lo que cambió), demo y "¿ya es cliente?" con
  el v4, y la [ficha de cliente único](ficha.html).
- [Hito 6: correcciones post-auditoría](hito6.md): modelo v3 sin vetos extremos (ningún
  campo resta más de 10 bits), generador con mudanzas, **prueba ciega 3** (v3: precisión
  0,996 y recall 0,955; v2: 0,996 y 0,972; v1: 0,995 y 0,715; con el umbral del v2, el v3
  tendría más recall), línea base determinística (Splink aporta +0,055 de F1 global sobre
  la mejor regla, sobre todo donde el documento falla), calibración y zona gris por bandas
  de peso (también en "¿ya es cliente?"), escala con el modelo congelado y hito 3 con
  varias semillas.

## Hito 1: fake_1000

1.000 registros de 251 personas (dataset de demostración de Splink), divididas por persona en
desarrollo (60 %) y prueba (40 %). En desarrollo se eligen las reglas de bloqueo, se entrena un
modelo Fellegi-Sunter sin etiquetas y se elige el umbral que minimiza el costo de errores por
clúster (un falso positivo cuesta 10 veces más que un falso negativo). Las métricas se miden
una sola vez en prueba, con intervalos de confianza del 95 % por bootstrap de personas.

**Prueba (100 personas, umbral 0,83):**

| Nivel | Precisión | Recall | F1 |
|---|---|---|---|
| Por par | 0,998 [0,991 – 1,000] | 0,709 [0,649 – 0,761] | 0,829 [0,786 – 0,864] |
| Por clúster | 0,970 [0,864 – 1,000] | 0,851 [0,790 – 0,903] | 0,907 [0,845 – 0,946] |

73 de las 100 personas quedan reconstruidas exactamente. Medidas sobre todo el dataset, con
reglas y umbral elegidos sobre esos mismos datos, las métricas serían optimistas (precisión
1,000 y recall 0,903 por clúster). Detalle en [metricas.json](resultados/metricas.json),
[seleccion_bloqueos.csv](resultados/seleccion_bloqueos.csv) y
[comparacion_bloqueos.csv](resultados/comparacion_bloqueos.csv).

## Tableros

De prueba:

- [Cascada por par](resultados/cascada.html): cómo cada campo suma o resta evidencia
  (aciertos, falsos positivos y falsos negativos).
- [Cluster Studio](resultados/cluster_studio.html): grafo de cada clúster, empezando por los
  que tienen errores.
- [Comparison viewer](resultados/comparison_viewer.html): ejemplos por patrón de comparación.

De desarrollo:

- [Parámetros m/u](resultados/parametros_mu.html) y
  [pesos de coincidencia](resultados/pesos.html) del modelo entrenado.
- Curvas por umbral: [por par](resultados/curva_umbral.html),
  [por clúster](resultados/curva_umbral_clusters.html) y [costo](resultados/costo_umbral.html).

![Cluster Studio: clúster de prueba que mezcla dos personas](resultados/cluster_studio.png)

## Regla de datos

Este proyecto nunca usa datos reales de clientes: solo datasets públicos de demostración
(Splink, FEBRL) o sintéticos generados con Faker.
