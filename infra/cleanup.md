# Limpieza de recursos AWS

Este procedimiento elimina la infraestructura del proyecto para detener
el consumo de presupuesto.

Ejecutarlo solamente después de la demostración o cuando se quiera
recrear toda la infraestructura.

## 1. Verificar cuenta y región

```bash
aws sts get-caller-identity
```

```bash
REGION="us-east-1"
export AWS_PAGER=""
```

## 2. Recuperar identificadores

```bash
LT_ID=$(aws ec2 describe-launch-templates \
  --region "$REGION" \
  --launch-template-names asc-launch-template \
  --query 'LaunchTemplates[0].LaunchTemplateId' \
  --output text)
```

```bash
ALB_ARN=$(aws elbv2 describe-load-balancers \
  --region "$REGION" \
  --names asc-alb \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)
```

```bash
TG_ARN=$(aws elbv2 describe-target-groups \
  --region "$REGION" \
  --names asc-targets \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)
```

```bash
ALB_SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters Name=group-name,Values=asc-alb-sg \
  --query 'SecurityGroups[0].GroupId' \
  --output text)
```

```bash
APP_SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters Name=group-name,Values=asc-app-sg \
  --query 'SecurityGroups[0].GroupId' \
  --output text)
```

Revisar antes de eliminar:

```bash
echo "Launch Template: $LT_ID"
echo "ALB: $ALB_ARN"
echo "Target Group: $TG_ARN"
echo "ALB Security Group: $ALB_SG_ID"
echo "App Security Group: $APP_SG_ID"
```

## 3. Reducir el ASG a cero

Permitir temporalmente una capacidad mínima de cero:

```bash
aws autoscaling update-auto-scaling-group \
  --region "$REGION" \
  --auto-scaling-group-name asc-web-asg \
  --min-size 0 \
  --desired-capacity 0
```

Consultar hasta que no aparezcan instancias:

```bash
aws autoscaling describe-auto-scaling-groups \
  --region "$REGION" \
  --auto-scaling-group-names asc-web-asg \
  --query 'AutoScalingGroups[0].Instances[*].[InstanceId,LifecycleState]' \
  --output json
```

El resultado esperado es:

```json
[]
```

## 4. Eliminar el ASG

```bash
aws autoscaling delete-auto-scaling-group \
  --region "$REGION" \
  --auto-scaling-group-name asc-web-asg
```

Comprobar:

```bash
aws autoscaling describe-auto-scaling-groups \
  --region "$REGION" \
  --auto-scaling-group-names asc-web-asg \
  --query 'AutoScalingGroups'
```

El resultado esperado es:

```json
[]
```

## 5. Eliminar el Launch Template

```bash
aws ec2 delete-launch-template \
  --region "$REGION" \
  --launch-template-id "$LT_ID"
```

## 6. Eliminar el ALB

```bash
aws elbv2 delete-load-balancer \
  --region "$REGION" \
  --load-balancer-arn "$ALB_ARN"
```

Esperar hasta que desaparezca:

```bash
aws elbv2 wait load-balancers-deleted \
  --region "$REGION" \
  --load-balancer-arns "$ALB_ARN"
```

El listener se elimina junto con el ALB.

## 7. Eliminar el Target Group

```bash
aws elbv2 delete-target-group \
  --region "$REGION" \
  --target-group-arn "$TG_ARN"
```

## 8. Eliminar los Security Groups

Primero eliminar el Security Group de las instancias:

```bash
aws ec2 delete-security-group \
  --region "$REGION" \
  --group-id "$APP_SG_ID"
```

Después eliminar el del ALB:

```bash
aws ec2 delete-security-group \
  --region "$REGION" \
  --group-id "$ALB_SG_ID"
```

AWS puede tardar en retirar las interfaces de red del ALB. Si aparece
`DependencyViolation`, esperar aproximadamente un minuto y repetir el
comando correspondiente.

## 9. Verificación final

Buscar recursos EC2 activos del proyecto:

```bash
aws ec2 describe-instances \
  --region "$REGION" \
  --filters \
    Name=tag:Project,Values=AutoScalingController \
    Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[*].Instances[*].[InstanceId,State.Name]' \
  --output json
```

El resultado esperado es:

```json
[]
```

Buscar balanceadores del proyecto:

```bash
aws elbv2 describe-load-balancers \
  --region "$REGION" \
  --query 'LoadBalancers[?LoadBalancerName==`asc-alb`]'
```

El resultado esperado es:

```json
[]
```

## Métrica de CloudWatch

CloudWatch no ofrece una operación para eliminar directamente una
métrica personalizada individual. Al dejar de publicar
`SimulatedDemand`, la métrica queda inactiva y desaparece de las
búsquedas normales después del periodo de retención del servicio.
