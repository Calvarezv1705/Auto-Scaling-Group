# Resultados del experimento

## Configuración

- Región AWS: `us-east-1`.
- Auto Scaling Group: `asc-web-asg`.
- Capacidad mínima: 1 instancia.
- Capacidad máxima: 5 instancias.
- Capacidad sintética asumida: 40 unidades por instancia saludable.
- Ventana de decisión: 3 mediciones consecutivas.
- Periodo entre mediciones: 60 segundos.
- Umbral de aumento: 80 % de la capacidad saludable actual.
- Umbral de reducción: 60 % de la capacidad que quedaría.
- Cooldown: 300 segundos.
- Semilla del generador: 3016.
- Políticas de escalamiento administradas por AWS: ninguna.

## Resultados

| Caso | Ventana | Capacidad antes | Decisión | Capacidad solicitada | Resultado |
| --- | --- | ---: | --- | ---: | --- |
| Demanda baja | `[19, 15, 21]` | 1 | `MAINTAIN_CAPACITY` | 1 | Acción omitida correctamente |
| Demanda alta | `[89, 90, 74]` | 1 | `INCREASE_CAPACITY` | 2 | Solicitud aceptada por AWS |
| Ventana discontinua | `74`, pausa de 420 s, `15`, `19` | 2 | `MAINTAIN_CAPACITY` | 2 | Reducción bloqueada de forma segura |
| Recuperación | `[15, 19, 22]` | 2 | `REDUCE_CAPACITY` | 1 | Solicitud aceptada por AWS |

## Tiempos observados

La solicitud de aumento fue registrada a las
`2026-09-22T02:56:09.083753+00:00`. Las dos instancias estuvieron
saludables a las `2026-09-22T02:56:46Z`.

El tiempo de adaptación observado después de solicitar el aumento fue
de aproximadamente 36,9 segundos.

La solicitud de reducción fue registrada a las
`2026-09-22T03:07:25.588430+00:00`. La terminación finalizó a las
`2026-09-22T03:14:04Z`.

El tiempo de adaptación observado después de solicitar la reducción
fue de aproximadamente 398,4 segundos, equivalentes a 6 minutos y
38 segundos.

Los tiempos corresponden a una sola ejecución y no representan un
promedio ni una garantía del servicio AWS.

## Disponibilidad

Antes de la reducción, el Target Group declaró saludables las dos
instancias. Veinte solicitudes pequeñas al Application Load Balancer
mostraron respuestas de ambos nombres internos.

Después de la reducción quedó una instancia saludable y el endpoint
`/health` continuó respondiendo `OK`.

No se generó carga masiva real contra la aplicación.

## Comportamientos de seguridad observados

- Una ventana incompleta produjo `MAINTAIN_CAPACITY`.
- Una medición con más de 240 segundos fue rechazada como antigua.
- Una ventana con un intervalo de 420 segundos fue rechazada como
  discontinua.
- El modo sin `--execute` produjo `DRY_RUN` y no cambió AWS.
- El actuador modificó la capacidad de una instancia por acción.
- El controlador respetó el intervalo permitido de 1 a 5 instancias.
- El ASG no tiene políticas de escalamiento dinámico administradas por
  AWS.

## Análisis crítico

La ventana de tres mediciones evita reaccionar ante un pico aislado,
pero introduce al menos dos minutos de espera antes de decidir. A esto
se suma el retraso de publicación de CloudWatch y el tiempo de arranque
de EC2. Durante un crecimiento repentino, la aplicación podría tener
capacidad insuficiente antes de que la nueva instancia esté saludable.

El margen diferente para aumentar y reducir funciona como histéresis.
El aumento usa 80 % de la capacidad actual y la reducción exige que la
demanda quepa bajo 60 % de la capacidad restante. Esto reduce cambios
repetidos alrededor de un solo límite.

La reducción tardó más que el aumento en esta ejecución. Mientras AWS
terminaba la instancia, el ALB conservó un destino saludable. El tiempo
de terminación demuestra que una orden aceptada no equivale a una
adaptación finalizada.

`SimulatedDemand` permitió probar el controlador sin estresar AWS, pero
no demuestra cuántas solicitudes reales soporta una instancia. El
valor de 40 unidades por instancia es una suposición del diseño y
debería calibrarse con pruebas autorizadas de rendimiento.

El experimento contiene una ejecución por escenario. Sirve como prueba
funcional reproducible, pero no permite calcular promedios, variación
ni intervalos de confianza.

El controlador fue invocado manualmente durante el experimento. Antes
de la entrega se añadirá un ejecutor periódico para que el ciclo de
observación y decisión pueda operar automáticamente.

AWS Academy proporciona el rol temporal `voclabs`. Por esa razón, el
experimento no demuestra la creación de un rol real de mínimo
privilegio. La política mínima necesaria se documentará como parte del
diseño.
