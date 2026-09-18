# Clasificación del controlador de elasticidad

## Solución propuesta

Aplicación web mínima en instancias EC2 detrás de un balanceador.
Un controlador propio observará el sistema y decidirá cuándo mantener,
aumentar o reducir la capacidad, dentro del límite de 1 a 5 instancias.

| Dimensión | Clasificación | Justificación y origen |
| --- | --- | --- |
| Tipo y dirección | Horizontal; aumento y reducción | El reto exige añadir y retirar instancias EC2. Impuesto. |
| Recursos escalados | Número de máquinas virtuales EC2, entre 1 y 5 | Recurso y límites impuestos por el reto. |
| Alcance | Infraestructura de la aplicación web | Elegimos un controlador separado de la aplicación que actúa sobre EC2. |
| Propósito | Sostener el rendimiento y evitar capacidad innecesaria | Objetivos impuestos; la meta numérica de rendimiento será elección nuestra. |
| Modo | Automático y reactivo | La autonomía es obligatoria; reaccionar a mediciones observadas es elección nuestra. |
| Método de decisión | Reglas con umbrales y retroalimentación | Elección nuestra; definiremos métricas, umbrales y protección contra oscilaciones en el diseño. |
| Arquitectura | Centralizada | Elegimos un solo proceso que decide sobre todas las instancias. |
| Alcance de proveedor | Un solo proveedor: AWS | Impuesto por el reto. |

## Fuentes

- Al-Dhuraibi et al., *Elasticity in Cloud Computing: State of the Art
  and Research Challenges*, sección 2.1 y figura 1 (horizontal y vertical);
  sección 2.2 y figura 2 (taxonomía).
- *Build Your Own Auto-Scaling Controller*, SI3016, secciones 4, 5 y 7
  (decisiones requeridas, clasificación y restricciones).
