# Permisos IAM del controlador

## Acciones necesarias

| Acción | Uso |
| --- | --- |
| `cloudwatch:GetMetricStatistics` | Leer `SimulatedDemand` |
| `cloudwatch:PutMetricData` | Publicar la demanda sintética |
| `autoscaling:DescribeAutoScalingGroups` | Consultar capacidad deseada y disponible |
| `autoscaling:SetDesiredCapacity` | Solicitar el aumento o la reducción |

El controlador no necesita crear ni eliminar directamente instancias,
modificar Launch Templates, crear políticas de escalamiento ni cambiar
Security Groups.

## Restricciones

`PutMetricData` se restringe al namespace
`AutoScalingController`.

`SetDesiredCapacity` se restringe al ASG `asc-web-asg` y exige la
etiqueta `Project=AutoScalingController`.

Las acciones de lectura `GetMetricStatistics` y
`DescribeAutoScalingGroups` utilizan `Resource: "*"` porque esas
operaciones no admiten restricción a un recurso específico.

## Limitación de AWS Academy

El laboratorio entrega credenciales temporales asociadas al rol
`voclabs`. Sus permisos y denegaciones explícitas son administrados por
AWS Academy.

Por esa razón no se aplicó una identidad IAM nueva durante el
experimento. El archivo `infra/controller-policy.json` documenta la
política que se utilizaría en una cuenta donde fuera posible administrar
IAM directamente.

Las credenciales temporales nunca se almacenan en el repositorio.
