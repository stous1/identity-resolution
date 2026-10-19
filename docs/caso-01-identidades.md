# Caso 1: Calidad del dato y resolución de identidades

## Descripción

La misma persona aparece varias veces en una base de clientes: cédula con un dígito errado,
nombre sin tilde, teléfono viejo. El proyecto detecta qué registros son el mismo cliente,
construye un registro de oro y deja a la vista los datos compartidos sospechosos (un mismo
teléfono en muchos clientes no relacionados), que pueden ser un problema de calidad o una
señal de riesgo.

## Objetivo

Consolidar registros en clientes únicos, explicar cada decisión y reducir la revisión manual
de casos dudosos con un agente.

## Técnicas

- Estandarización: nombres, teléfonos (+57), direcciones colombianas ("Cra", "Carrera", "KR";
  "# 10-20").
- Bloqueo para no comparar todos contra todos.
- Modelo probabilístico Fellegi-Sunter entrenado sin etiquetas (EM).
- Agrupación de pares en grafo (componentes conectados = clientes).
- Reglas de supervivencia para el registro de oro.
- Grafo de identidad compartida: clientes conectados por teléfono, correo, dirección o
  dispositivo.

## Agente

- Revisa la zona gris: lee la explicación de Splink, consulta historial y decide
  unir/separar/escalar con justificación.
- Propone el registro de oro y señala los casos que no encajan en las reglas.
- Opcional: agente que ajusta reglas de bloqueo y comparaciones, vuelve a correr y compara
  métricas.

## Librerías

- [Splink](https://github.com/moj-analytical-services/splink): motor de resolución; corre en
  DuckDB para prototipo y en Spark para escala.
- DuckDB.
- Faker (datos sintéticos colombianos).
- Cosmograph (visualización del universo de registros).
- Claude Agent SDK + MCP (agente).

## Datasets

- Datasets de demostración de Splink (incluyen la verdad conocida de qué registros son la
  misma persona).
- FEBRL (registros sintéticos de personas).
- Sintéticos colombianos generados con Faker, con errores inyectados a propósito.

## Evaluación

- Precisión y recall de emparejamiento contra la verdad conocida.
- Precisión de las decisiones del agente en la zona gris.
- Métricas de negocio simuladas: duplicados detectados, comunicaciones duplicadas evitadas,
  cambio en contactabilidad.

## Visualizaciones

- Gráfico de cascada por par y Cluster Studio (vienen con Splink).
- Universo de registros en Cosmograph: miles de puntos agrupándose en clientes, y estrellas de
  datos compartidos (un teléfono "3000000000" en cientos de registros).
- Antes y después animado.

## Hitos

1. **fake_1000 de punta a punta** (completado): carga del dataset de demostración de Splink,
   entrenamiento sin etiquetas, evaluación contra los grupos verdaderos (por par, por clúster,
   por umbral y recall perdido por el bloqueo) y tableros HTML de Splink. Bloqueo y umbral se
   eligen en desarrollo (60 % de las personas) y las métricas se miden en prueba (40 %), con
   intervalos de confianza por bootstrap. Resultados en el
   [informe técnico](https://github.com/stous1/identity-resolution/blob/main/INFORME_TECNICO.md#hito-1-fake_1000-de-punta-a-punta)
   y en [los tableros publicados](index.md).
2. **Sintéticos colombianos y estandarización** (completado): generador con Faker es_CO
   (errores de captura, familiares y datos de relleno), estandarización de nombres,
   documento, celular, correo y direcciones, modelo con documento por niveles, aporte de la
   estandarización y equidad entre grupos. Validado con una prueba ciega (modelo
   congelado, generador de errores independiente) y con FEBRL3. Resultados en
   [hito2.md](hito2.md).
   **2b. Corrección** (completado): la prueba ciega 1 pasa a desarrollo, se corrigen el
   apellido de casada, los apodos, los nombres cruzados, el documento y los teléfonos, y se
   mide con una segunda prueba ciega. Resultados en [hito2b.md](hito2b.md).
3. **Registro de oro y grafo de identidad compartida** (completado): escenario con historia,
   metadatos y patrones sospechosos; reglas de supervivencia por campo; grafo de datos
   compartidos (relleno, hogar, sospechoso); puentes con las métricas de grafo de Splink;
   universo de registros en Cosmograph; cola de revisión para el agente. Resultados en
   [hito3.md](hito3.md).
4. Agente para la zona gris.
5. **Tiempo real y escala** (completado): "¿ya es cliente?" contra la base de registros de
   oro con el modelo congelado y un servicio local con FastAPI; tiempo y memoria con 100 mil
   y 1 millón de registros en DuckDB; universo grande en Cosmograph desde Parquet.
   Resultados en [hito5.md](hito5.md).

6. **Correcciones post-auditoría** (completado): modelo v3, prueba ciega 3, línea base,
   calibración y estabilidad. Resultados en [hito6.md](hito6.md).
7. **v1.1: realidad residencial y familiar colombiana** (completado): parejas que solo
   comparten la dirección, convivientes, conjuntos y edificios distinguidos por torre,
   bloque, interior o apartamento, y casas de varios pisos. Generador residencial,
   estandarización de la dirección en predio y unidad, modelo v4, grafo que estima el tipo
   de predio y reconoce parejas y la convención de apellidos, y prueba ciega 4. Resultados
   en [v11.md](v11.md).

## Notas

- Es un prototipo de "cliente único". Con datos reales pasaría por gobierno de datos y
  seguridad; este repositorio solo usa datos públicos de demostración o sintéticos.
