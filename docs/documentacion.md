# Clasificación y diseño del controlador de elasticidad

## Solución implementada

La solución consiste en una aplicación web mínima ejecutada en instancias EC2 detrás de un Application Load Balancer.

Un controlador propio escrito en Python observa demanda sintética, consulta el estado del Auto Scaling Group y decide cuándo mantener, aumentar o reducir la capacidad entre 1 y 5 instancias.

El Auto Scaling Group no utiliza políticas de escalamiento dinámico administradas por AWS. Todas las decisiones pertenecen al controlador implementado en este proyecto.

## Clasificación

| Dimensión | Clasificación | Justificación |
| --- | --- | --- |
| Tipo | Elasticidad horizontal | Se añaden o retiran instancias EC2. |
| Dirección | Aumento y reducción | El controlador puede incrementar o disminuir la capacidad. |
| Recurso escalado | Máquinas virtuales EC2 | La capacidad se representa mediante el número de instancias. |
| Límites | Entre 1 y 5 instancias | Restricción establecida para el experimento. |
| Alcance | Infraestructura de una aplicación web | El controlador funciona fuera de la aplicación y administra su infraestructura. |
| Propósito | Mantener disponibilidad y evitar capacidad innecesaria | Busca responder a la demanda sin conservar instancias que no se necesitan. |
| Modo | Automático y reactivo | Reacciona periódicamente a mediciones ya observadas. |
| Método | Reglas con umbrales y retroalimentación | Compara ventanas de demanda con límites calculados según la capacidad. |
| Arquitectura | Centralizada | Un proceso toma las decisiones sobre todo el grupo. |
| Proveedor | AWS | Utiliza EC2, Auto Scaling, ELB y CloudWatch. |

## Fuentes conceptuales

- Al-Dhuraibi et al., *Elasticity in Cloud Computing: State of the Art and Research Challenges*, sección 2.1 y figura 1 para elasticidad horizontal y vertical; sección 2.2 y figura 2 para la taxonomía.
- *Build Your Own Auto-Scaling Controller*, SI3016, secciones 4, 5 y 7 para las decisiones, restricciones y clasificación solicitadas.

## Arquitectura

```text
Generador reproducible
        |
        v
Publicador de SimulatedDemand
        |
        v
Amazon CloudWatch
        |
        v
Monitor -> Decisor -> Actuador
                       |
                       v
             Auto Scaling Group
                       |
                       v
                1 a 5 EC2
                       |
                       v
          Application Load Balancer
```

El controlador se ejecuta como un proceso Python en el computador del operador. La aplicación web funciona en las instancias EC2 y expone el endpoint `/health`.

## Diseño de red reproducible

Las recreaciones nuevas despliegan los recursos en una VPC personalizada
`asc-vpc` con CIDR `172.16.0.0/16`. La red contiene dos subredes públicas:

- `172.16.1.0/24` en `us-east-1a`.
- `172.16.2.0/24` en `us-east-1b`.

Un Internet Gateway y una tabla de rutas con destino `0.0.0.0/0`
permiten que el ALB sea público y que las instancias instalen paquetes
durante el arranque. El ALB acepta HTTP por el puerto 80. Las instancias
aceptan el puerto 8080 exclusivamente desde el Security Group del ALB.

Se eligieron subredes públicas para evitar el costo de un NAT Gateway en
el laboratorio. En producción sería preferible ubicar las instancias en
subredes privadas y proporcionar salida controlada mediante NAT Gateway
o VPC endpoints.

La ejecución experimental registrada se realizó antes de esta mejora de
reproducibilidad y utilizó la VPC predeterminada disponible en AWS
Academy. La topología lógica, la política del controlador y sus
resultados no dependen de que la VPC sea predeterminada o personalizada.

## Componentes del lazo de control

### Generador

`simulation/workload.py` produce una secuencia reproducible de demanda sintética utilizando la semilla `3016`.

### Publicador

`simulation/publisher.py` envía cada valor a CloudWatch con:

- Namespace: `AutoScalingController`
- Métrica: `SimulatedDemand`
- Dimensión: `Scenario=Challenge1`

### Monitor

`controller/monitor.py` consulta las mediciones recientes de `SimulatedDemand` y construye una ventana con las últimas tres.

El monitor rechaza:

- Ventanas con menos de tres mediciones.
- Mediciones separadas por más de 90 segundos.
- Una última medición con más de 240 segundos de antigüedad.
- Valores ausentes o inválidos.

Un dato ausente nunca se interpreta como demanda cero.

### Decisor

`controller/decisor.py` recibe la ventana validada, la capacidad saludable y la capacidad deseada.

Cada instancia saludable representa 40 unidades de demanda sintética.

Las decisiones posibles son:

- `INCREASE_CAPACITY`
- `REDUCE_CAPACITY`
- `MAINTAIN_CAPACITY`

### Actuador

`controller/actuator.py` consulta el estado real del ASG antes de actuar.

Una instancia solo cuenta como capacidad disponible cuando cumple:

```text
LifecycleState = InService
HealthStatus = Healthy
```

El actuador realiza cambios de una sola instancia y comprueba otra vez que la capacidad solicitada se encuentre entre 1 y 5.

Sin `--execute`, informa la acción en modo `DRY_RUN` y no modifica AWS.

### Coordinador

`controller/main.py` ejecuta un ciclo completo:

1. Consulta el estado del ASG.
2. Lee las métricas de CloudWatch.
3. Valida la ventana.
4. Comprueba cambios de capacidad y cooldown.
5. Solicita una decisión.
6. Ejecuta o simula la acción.
7. Guarda el resultado en formato JSONL.

### Ejecutor periódico

`controller/runner.py` repite automáticamente el ciclo del controlador.

Puede ejecutarse continuamente con:

```bash
python -m controller.runner \
  --interval 60 \
  --minutes 15 \
  --execute
```

## Política de decisión

### Aumento

El controlador aumenta una instancia cuando:

- Existen exactamente tres mediciones válidas y consecutivas.
- Las tres superan el 80 % de la capacidad saludable actual.
- Toda la capacidad deseada está disponible.
- No existe otro cambio en curso.
- El cooldown terminó.
- La capacidad deseada es menor que 5.

### Reducción

El controlador retira una instancia cuando:

- Existen exactamente tres mediciones válidas y consecutivas.
- Las tres caben bajo el 60 % de la capacidad que quedaría.
- Toda la capacidad deseada está disponible.
- No existe otro cambio en curso.
- El cooldown terminó.
- Después de reducir queda al menos una instancia.

### Mantenimiento

El controlador conserva la capacidad cuando:

- La demanda permanece dentro de la banda estable.
- Solo aparece un pico aislado.
- La ventana está incompleta, antigua o discontinua.
- Existe una instancia pendiente o no saludable.
- Hay un cambio anterior en curso.
- El cooldown continúa activo.
- Se alcanzó alguno de los límites.

## Estabilidad y seguridad

La ventana de tres mediciones evita reaccionar ante un solo pico.

Los límites diferentes para aumentar y reducir forman una histéresis:

- Aumento sobre el 80 % de la capacidad actual.
- Reducción bajo el 60 % de la capacidad restante.

Después de una acción se aplica un cooldown de 300 segundos.

Una instancia en estado `running` no cuenta inmediatamente como capacidad disponible. Debe estar `InService` y `Healthy`.

## Observaciones utilizadas

La entrada automática de demanda es exclusivamente `SimulatedDemand`, almacenada en CloudWatch.

El controlador también consulta en el Auto Scaling Group:

- Capacidad mínima.
- Capacidad máxima.
- Capacidad deseada.
- Estado del ciclo de vida de cada instancia.
- Estado de salud de cada instancia.

`CPUUtilization` no participa en la decisión porque la aplicación mínima no recibe una carga real representativa.

El Target Group y el endpoint `/health` se utilizaron para comprobar manualmente la disponibilidad y la distribución del tráfico durante el experimento. No son una segunda señal de demanda.

## Objetivo de nivel de servicio

El SLO funcional del experimento fue:

- Mantener al menos una instancia saludable detrás del ALB.
- Conservar el endpoint `/health` respondiendo `HTTP 200` durante los cambios de capacidad.

El experimento no establece un porcentaje de disponibilidad de largo plazo ni una garantía máxima de latencia.

## Manejo de fallos

El controlador conserva la capacidad cuando no dispone de datos confiables.

Si una consulta falla, el runner registra el error y espera al siguiente ciclo. Si una acción tiene resultado incierto, el siguiente ciclo consulta nuevamente el estado real del ASG antes de tomar otra decisión.

La reducción se bloquea cuando no puede confirmarse la capacidad saludable.

## Registro y trazabilidad

Cada ciclo registra:

- Hora.
- Métricas consultadas.
- Ventana utilizada.
- Capacidad mínima, máxima, deseada y saludable.
- Estado del cooldown.
- Decisión y justificación.
- Acción solicitada.
- Resultado de la actuación.

La evidencia definitiva se encuentra en:

- `experiments/final-experiment.jsonl`
- `experiments/results.md`
- `experiments/time-series.png`

## Permisos

El controlador requiere permisos para:

- Leer y publicar la métrica personalizada.
- Consultar el Auto Scaling Group.
- Cambiar su capacidad deseada.

AWS Academy proporciona credenciales temporales mediante el rol `voclabs`. Por esta razón, el experimento no crea una identidad IAM propia.

La propuesta de mínimo privilegio está documentada en:

- `docs/iam.md`
- `infra/controller-policy.json`

Las credenciales temporales se almacenan fuera del repositorio.

## Limitaciones

`SimulatedDemand` representa una carga sintética. No demuestra cuántas solicitudes reales puede atender una instancia.

La capacidad de 40 unidades por instancia es una suposición del diseño y debería calibrarse mediante pruebas de rendimiento autorizadas.

Los tiempos registrados corresponden a una ejecución por escenario. No representan promedios ni garantías del servicio AWS.

Los resultados y su análisis crítico están documentados en `experiments/results.md`.
