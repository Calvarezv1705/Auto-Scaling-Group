# Auto-Scaling Controller

Controlador propio de elasticidad horizontal para una aplicación web desplegada en instancias EC2 detrás de un Application Load Balancer.

Proyecto desarrollado para el Challenge Based Learning No. 1 del curso SI3016 Cloud Computing de la Universidad EAFIT.

## Objetivo

Observar demanda sintética publicada en CloudWatch y decidir entre:

- `MAINTAIN_CAPACITY`
- `INCREASE_CAPACITY`
- `REDUCE_CAPACITY`

El controlador administra entre 1 y 5 instancias mediante un Auto Scaling Group, sin utilizar políticas de dynamic scaling administradas por AWS.

## Arquitectura

```text
Generador reproducible
        |
        v
SimulatedDemand en CloudWatch
        |
        v
Monitor -> Decisor -> Actuador
                       |
                       v
             Auto Scaling Group
                       |
                       v
       VPC asc-vpc (172.16.0.0/16)
                       |
Internet ----------> ALB :80
                       |
                       v
              Target Group :8080
                       |
          +------------+------------+
          |                         |
          v                         v
  Subred pública A          Subred pública B
          +------ 1 a 5 EC2 --------+
```

El controlador se ejecuta como un proceso Python externo a la aplicación web.

## Componentes

```text
app/
  server.py               Aplicación HTTP mínima y endpoint /health

controller/
  monitor.py              Lee SimulatedDemand desde CloudWatch
  decisor.py              Aplica reglas puras de decisión
  actuator.py             Consulta y modifica el ASG
  main.py                 Ejecuta un ciclo completo
  runner.py               Repite el ciclo automáticamente

simulation/
  workload.py             Genera demanda con semilla fija
  publisher.py            Publica SimulatedDemand
  run_workload.py         Publica secuencias de ciclos

infra/
  README.md               Recrea la red y los recursos AWS
  user-data.sh            Instala y arranca la aplicación en EC2
  cleanup.md              Elimina los recursos de forma segura

docs/
  documentacion.md        Taxonomía y diseño del controlador

experiments/
  final-experiment.jsonl  Evidencia definitiva
  phase5-validation.jsonl Registros de validación
  results.md              Resultados y análisis crítico
  timing.txt              Marcas de tiempo observadas
```

## Requisitos

- Python 3.13 o compatible.
- Git.
- AWS CLI v2.
- Cuenta o laboratorio AWS con acceso a EC2, Auto Scaling, Elastic Load Balancing y CloudWatch.
- Credenciales temporales válidas.
- Región `us-east-1`.

## Instalación local

```bash
git clone https://github.com/Calvarezv1705/Auto-Scaling-Group.git
cd Auto-Scaling-Group

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Las credenciales deben configurarse fuera del repositorio:

```text
~/.aws/credentials
```

Nunca deben copiarse a GitHub.

Comprueba la sesión:

```bash
aws sts get-caller-identity
```

## Recursos AWS utilizados

- Región: `us-east-1`
- VPC reproducible: `asc-vpc` con CIDR `172.16.0.0/16`
- Subred pública A: `172.16.1.0/24` en `us-east-1a`
- Subred pública B: `172.16.2.0/24` en `us-east-1b`
- Auto Scaling Group: `asc-web-asg`
- Launch Template: `asc-launch-template`
- Application Load Balancer: `asc-alb`
- Target Group: `asc-targets`
- Puerto público del ALB: 80
- Puerto de la aplicación: 8080
- Health check: `/health`
- Capacidad mínima: 1
- Capacidad máxima: 5
- Namespace de CloudWatch: `AutoScalingController`
- Métrica: `SimulatedDemand`
- Dimensión: `Scenario=Challenge1`

La ejecución experimental registrada se realizó originalmente sobre la
VPC predeterminada disponible en AWS Academy. La guía de infraestructura
actual crea una VPC personalizada para que las recreaciones futuras sean
independientes de la configuración predeterminada de la cuenta. Este
cambio de red no modifica la política ni los resultados del controlador.

El ASG no debe tener políticas de escalamiento dinámico:

```bash
aws autoscaling describe-policies \
  --region us-east-1 \
  --auto-scaling-group-name asc-web-asg \
  --query 'ScalingPolicies'
```

El resultado esperado es:

```json
[]
```

Las instrucciones completas para recrear estos recursos están en
[`infra/README.md`](infra/README.md).

La propuesta de mínimo privilegio está documentada en
[`docs/iam.md`](docs/iam.md), con la política en
[`infra/controller-policy.json`](infra/controller-policy.json).

## Política de decisión

Cada instancia saludable representa 40 unidades de demanda sintética.

El controlador utiliza tres mediciones consecutivas:

- Aumenta si las tres superan el 80 % de la capacidad saludable.
- Reduce si las tres caben bajo el 60 % de la capacidad que quedaría.
- Mantiene capacidad si ninguna regla se cumple o los datos no son confiables.

Protecciones:

- Capacidad entre 1 y 5.
- Cambios de una instancia por decisión.
- Cooldown de 300 segundos.
- Rechazo de ventanas incompletas.
- Rechazo de separaciones superiores a 90 segundos.
- Rechazo de métricas con más de 240 segundos.
- Espera hasta que la capacidad deseada esté disponible.
- Modo seguro sin `--execute`.

## Simulación reproducible

La semilla predeterminada es `3016`.

Consulta la secuencia:

```bash
python -m simulation.workload
```

Prueba una publicación sin enviar datos a AWS:

```bash
python -m simulation.publisher --cycle 11 --dry-run
```

Publica tres mediciones altas:

```bash
python -m simulation.run_workload \
  --start-cycle 11 \
  --count 3 \
  --interval 61
```

## Uso del controlador

Consulta las mediciones:

```bash
python -m controller.monitor --minutes 15
```

Ejecuta un ciclo sin modificar AWS:

```bash
python -m controller.main --minutes 15
```

Permite una acción real:

```bash
python -m controller.main --minutes 15 --execute
```

Ejecuta un solo ciclo mediante el runner:

```bash
python -m controller.runner --cycles 1 --minutes 15
```

Ejecuta continuamente con acciones reales:

```bash
python -m controller.runner \
  --interval 60 \
  --minutes 15 \
  --execute
```

Se detiene con `Control + C`.

## Reproducción del experimento

El estado inicial debe ser una instancia saludable.

### Mantenimiento

Publica una ventana de demanda baja:

```bash
python -m simulation.run_workload \
  --start-cycle 1 \
  --count 3 \
  --interval 61
```

Ventana esperada:

```text
[19, 15, 21]
```

La decisión esperada es:

```text
MAINTAIN_CAPACITY
```

### Aumento

Publica una ventana de demanda alta:

```bash
python -m simulation.run_workload \
  --start-cycle 11 \
  --count 3 \
  --interval 61
```

Ventana esperada:

```text
[89, 90, 74]
```

La decisión esperada es:

```text
INCREASE_CAPACITY
```

### Reducción

Después de que existan dos instancias saludables y termine el cooldown, publica la ventana de recuperación:

```bash
python -m simulation.run_workload \
  --start-cycle 19 \
  --count 3 \
  --interval 61
```

Ventana esperada:

```text
[15, 19, 22]
```

La decisión esperada es:

```text
REDUCE_CAPACITY
```

En cada escenario se consulta el monitor:

```bash
python -m controller.monitor --minutes 15
```

Después se ejecuta primero en modo seguro:

```bash
python -m controller.main --minutes 15
```

Cuando la decisión sea correcta, se permite la actuación real:

```bash
python -m controller.main --minutes 15 --execute
```

## Pruebas locales

Las pruebas no se conectan con AWS ni generan costos.

Ejecuta:

```bash
python -m unittest discover -s tests -v
```

Las pruebas verifican:

- Aumento ante demanda alta sostenida.
- Reducción ante demanda baja sostenida.
- Mantenimiento ante un pico aislado.
- Exclusión de instancias no saludables del cálculo de capacidad.

El resultado esperado termina con:

```text
Ran 4 tests
OK
```

## Evidencia

Los resultados definitivos están en:

- `experiments/final-experiment.jsonl`
- `experiments/results.md`
- `experiments/timing.txt`
- `experiments/time-series.png`
- `experiments/plot_results.py`

El experimento demostró:

- Mantenimiento con demanda baja.
- Aumento de una a dos instancias.
- Rechazo seguro de una ventana discontinua.
- Reducción de dos a una instancia.
- Continuidad de la aplicación mediante el ALB.

## Limitaciones

- `SimulatedDemand` representa carga; no mide rendimiento real.
- La capacidad de 40 unidades por instancia es una suposición.
- Los tiempos observados provienen de una ejecución por escenario.
- AWS Academy utiliza credenciales temporales y el rol `voclabs`.
- El rol del laboratorio no demuestra mínimo privilegio real.
- El controlador se ejecuta desde el computador del operador.
- El experimento funcional no permite calcular promedios ni intervalos de confianza.

## Seguridad y costos

- No se almacenan credenciales en el repositorio.
- La aplicación solo acepta tráfico en el puerto 8080 desde el Security Group del ALB.
- El experimento no genera tráfico masivo.
- El controlador valida los límites antes de actuar.
- Los recursos deben eliminarse o detenerse después de la demostración.

El procedimiento de eliminación está documentado en
[`infra/cleanup.md`](infra/cleanup.md).
