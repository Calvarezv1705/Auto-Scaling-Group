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

## Diseño del lazo de control

### Ejecución y componentes

El controlador correrá en un proceso Python en el Mac durante el
experimento. El simulador publicará SimulatedDemand en CloudWatch.
El monitor leerá las métricas y el estado de AWS; el decisor aplicará
reglas propias; el actuador cambiará la capacidad deseada de un ASG.
El ASG tendrá mínimo 1 y máximo 5, sin políticas de escalado dinámico.

### Observaciones

- SimulatedDemand: demanda sintética publicada cada 60 segundos.
- HealthyHostCount: instancias sanas observadas en CloudWatch.
- Estado del ASG y de sus destinos: confirma capacidad en curso y disponible.
- CPUUtilization: contexto real, no entrada de la regla de demanda sintética.
- Una solicitud HTTP por minuto: estado y latencia de la aplicación,
  sin generar tráfico masivo.

### Política propuesta

El controlador evaluará una vez por minuto las últimas 3 mediciones
válidas y consecutivas de SimulatedDemand. Suponemos inicialmente
40 unidades de demanda sintética por instancia sana.

- INCREASE_CAPACITY: las 3 lecturas superan el 80 % de la capacidad
  sana actual y la capacidad deseada es menor que 5.
- REDUCE_CAPACITY: las 3 lecturas caben en el 60 % de la capacidad
  que quedaría tras retirar una instancia, y quedaría al menos 1.
- MAINTAIN_CAPACITY: no se cumplen esas condiciones, faltan datos
  o hay una acción anterior en curso.

Después de una acción habrá al menos 5 minutos de espera. Para volver
a escalar también deberá haber terminado el cambio y estar confirmada
la salud de las instancias. Una instancia en estado running todavía
no cuenta como disponible para atender la aplicación.

### Fallos y registro

Un dato ausente nunca se interpreta como demanda cero. Si falla una
consulta o no puede confirmarse la salud, no se reduce capacidad.
Si una acción tiene resultado incierto, se consulta el estado real del
ASG antes de repetirla. El actuador comprobará de nuevo los límites
de 1 a 5.

Cada ciclo registrará hora, métricas, ventana, capacidad deseada y
sana, decisión, justificación, acción solicitada y resultado o error.

### Permisos y límite experimental

El controlador solo deberá recibir los permisos AWS necesarios para
leer métricas y salud, consultar el ASG y cambiar su capacidad deseada.
Debemos verificar si AWS Academy permite crear una identidad con esos
permisos; el rol temporal voclabs por sí solo no demuestra mínimo
privilegio.

SimulatedDemand es una carga representada, no tráfico real. La prueba
HTTP ligera permitirá observar disponibilidad y latencia, pero no
validará rendimiento bajo carga masiva real.
