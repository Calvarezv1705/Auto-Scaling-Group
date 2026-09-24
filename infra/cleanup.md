# Limpieza segura de recursos AWS

Este procedimiento elimina los recursos del proyecto para detener el
consumo de presupuesto. Funciona tanto con la ejecución histórica en la
VPC predeterminada como con las recreaciones nuevas en `asc-vpc`.

Ejecutarlo solamente después de la demostración o cuando se quiera
recrear toda la infraestructura.

## 1. Verificar cuenta y región

```bash
aws sts get-caller-identity

REGION="us-east-1"
export AWS_PAGER=""
```

Confirma visualmente que `Account` corresponde al laboratorio correcto.

## 2. Recuperar y revisar identificadores

```bash
LT_ID=$(aws ec2 describe-launch-templates \
  --region "$REGION" \
  --launch-template-names asc-launch-template \
  --query 'LaunchTemplates[0].LaunchTemplateId' \
  --output text)

ALB_ARN=$(aws elbv2 describe-load-balancers \
  --region "$REGION" \
  --names asc-alb \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)

TG_ARN=$(aws elbv2 describe-target-groups \
  --region "$REGION" \
  --names asc-targets \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

VPC_ID=$(aws elbv2 describe-target-groups \
  --region "$REGION" \
  --names asc-targets \
  --query 'TargetGroups[0].VpcId' \
  --output text)

IS_DEFAULT=$(aws ec2 describe-vpcs \
  --region "$REGION" \
  --vpc-ids "$VPC_ID" \
  --query 'Vpcs[0].IsDefault' \
  --output text)

VPC_NAME=$(aws ec2 describe-vpcs \
  --region "$REGION" \
  --vpc-ids "$VPC_ID" \
  --query 'Vpcs[0].Tags[?Key==`Name`].Value|[0]' \
  --output text)

ALB_SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" Name=group-name,Values=asc-alb-sg \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

APP_SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" Name=group-name,Values=asc-app-sg \
  --query 'SecurityGroups[0].GroupId' \
  --output text)
```

Revisa todos los valores antes de eliminar:

```bash
echo "VPC: $VPC_ID"
echo "Nombre de VPC: $VPC_NAME"
echo "¿VPC predeterminada?: $IS_DEFAULT"
echo "Launch Template: $LT_ID"
echo "ALB: $ALB_ARN"
echo "Target Group: $TG_ARN"
echo "ALB Security Group: $ALB_SG_ID"
echo "App Security Group: $APP_SG_ID"
```

## 3. Reducir el ASG a cero

```bash
aws autoscaling update-auto-scaling-group \
  --region "$REGION" \
  --auto-scaling-group-name asc-web-asg \
  --min-size 0 \
  --desired-capacity 0
```

Consulta hasta que no aparezcan instancias:

```bash
aws autoscaling describe-auto-scaling-groups \
  --region "$REGION" \
  --auto-scaling-group-names asc-web-asg \
  --query 'AutoScalingGroups[0].Instances[*].[InstanceId,LifecycleState]' \
  --output json
```

Continúa cuando el resultado sea `[]`.

## 4. Eliminar el ASG y el Launch Template

```bash
aws autoscaling delete-auto-scaling-group \
  --region "$REGION" \
  --auto-scaling-group-name asc-web-asg
```

Comprueba que el ASG desapareció:

```bash
aws autoscaling describe-auto-scaling-groups \
  --region "$REGION" \
  --auto-scaling-group-names asc-web-asg \
  --query 'AutoScalingGroups'
```

Cuando el resultado sea `[]`, elimina el Launch Template:

```bash
aws ec2 delete-launch-template \
  --region "$REGION" \
  --launch-template-id "$LT_ID"
```

## 5. Eliminar el ALB y el Target Group

```bash
aws elbv2 delete-load-balancer \
  --region "$REGION" \
  --load-balancer-arn "$ALB_ARN"

aws elbv2 wait load-balancers-deleted \
  --region "$REGION" \
  --load-balancer-arns "$ALB_ARN"
```

El listener se elimina junto con el ALB. Después elimina el Target
Group:

```bash
aws elbv2 delete-target-group \
  --region "$REGION" \
  --target-group-arn "$TG_ARN"
```

## 6. Eliminar los Security Groups

Primero elimina el Security Group de las instancias y después el del
ALB:

```bash
aws ec2 delete-security-group \
  --region "$REGION" \
  --group-id "$APP_SG_ID"

aws ec2 delete-security-group \
  --region "$REGION" \
  --group-id "$ALB_SG_ID"
```

Si aparece `DependencyViolation`, espera aproximadamente un minuto y
repite el comando. AWS puede tardar en retirar las interfaces de red
del ALB.

## 7. Eliminar la red personalizada cuando corresponda

Este bloque tiene una protección explícita: solo elimina la red si la
VPC no es predeterminada y su etiqueta `Name` es exactamente
`asc-vpc`. Nunca elimina la VPC predeterminada.

```bash
if [ "$IS_DEFAULT" = "False" ] && [ "$VPC_NAME" = "asc-vpc" ]; then
  SUBNET_IDS=$(aws ec2 describe-subnets \
    --region "$REGION" \
    --filters Name=vpc-id,Values="$VPC_ID" Name=tag:Project,Values=AutoScalingController \
    --query 'Subnets[*].SubnetId' \
    --output text)

  ROUTE_TABLE_ID=$(aws ec2 describe-route-tables \
    --region "$REGION" \
    --filters Name=vpc-id,Values="$VPC_ID" Name=tag:Name,Values=asc-public-rt \
    --query 'RouteTables[0].RouteTableId' \
    --output text)

  ROUTE_ASSOCIATIONS=$(aws ec2 describe-route-tables \
    --region "$REGION" \
    --route-table-ids "$ROUTE_TABLE_ID" \
    --query 'RouteTables[0].Associations[?Main==`false`].RouteTableAssociationId' \
    --output text)

  IGW_ID=$(aws ec2 describe-internet-gateways \
    --region "$REGION" \
    --filters Name=attachment.vpc-id,Values="$VPC_ID" Name=tag:Name,Values=asc-igw \
    --query 'InternetGateways[0].InternetGatewayId' \
    --output text)

  for ASSOCIATION_ID in $ROUTE_ASSOCIATIONS; do
    aws ec2 disassociate-route-table \
      --region "$REGION" \
      --association-id "$ASSOCIATION_ID"
  done

  aws ec2 delete-route-table \
    --region "$REGION" \
    --route-table-id "$ROUTE_TABLE_ID"

  for SUBNET_ID in $SUBNET_IDS; do
    aws ec2 delete-subnet \
      --region "$REGION" \
      --subnet-id "$SUBNET_ID"
  done

  aws ec2 detach-internet-gateway \
    --region "$REGION" \
    --internet-gateway-id "$IGW_ID" \
    --vpc-id "$VPC_ID"

  aws ec2 delete-internet-gateway \
    --region "$REGION" \
    --internet-gateway-id "$IGW_ID"

  aws ec2 delete-vpc \
    --region "$REGION" \
    --vpc-id "$VPC_ID"
else
  echo "La VPC no se elimina porque es predeterminada o no se llama asc-vpc."
fi
```

## 8. Verificación final

Busca instancias activas del proyecto:

```bash
aws ec2 describe-instances \
  --region "$REGION" \
  --filters \
    Name=tag:Project,Values=AutoScalingController \
    Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[*].Instances[*].[InstanceId,State.Name]' \
  --output json
```

Busca balanceadores del proyecto:

```bash
aws elbv2 describe-load-balancers \
  --region "$REGION" \
  --query 'LoadBalancers[?LoadBalancerName==`asc-alb`]'
```

Ambos resultados deben ser `[]`.

## Métrica de CloudWatch

CloudWatch no ofrece una operación para eliminar directamente una
métrica personalizada individual. Al dejar de publicar
`SimulatedDemand`, la métrica queda inactiva y desaparece de las
búsquedas normales después del periodo de retención del servicio.
