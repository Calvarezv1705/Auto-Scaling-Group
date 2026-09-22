# Infraestructura AWS

Este documento crea la infraestructura utilizada por el controlador en
una cuenta o laboratorio AWS nuevo.

No ejecutes los comandos si ya existen recursos con los nombres
`asc-alb`, `asc-targets`, `asc-launch-template` y `asc-web-asg`.

## 1. Requisitos

Activa el entorno virtual y comprueba las credenciales:

```bash
source .venv/bin/activate
aws sts get-caller-identity
```

Evita que AWS CLI abra el paginador:

```bash
export AWS_PAGER=""
```

Define la región:

```bash
REGION="us-east-1"
```

## 2. Red y AMI

Obtén la VPC predeterminada:

```bash
VPC_ID=$(aws ec2 describe-vpcs \
  --region "$REGION" \
  --filters Name=is-default,Values=true \
  --query 'Vpcs[0].VpcId' \
  --output text)
```

Comprueba:

```bash
echo "$VPC_ID"
```

Obtén dos subredes de diferentes zonas de disponibilidad:

```bash
SUBNET_A=$(aws ec2 describe-subnets \
  --region "$REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'sort_by(Subnets,&AvailabilityZone)[0].SubnetId' \
  --output text)
```

```bash
SUBNET_B=$(aws ec2 describe-subnets \
  --region "$REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'sort_by(Subnets,&AvailabilityZone)[1].SubnetId' \
  --output text)
```

Comprueba:

```bash
echo "$SUBNET_A"
echo "$SUBNET_B"
```

Obtén la versión actual de Amazon Linux 2023 para x86_64:

```bash
AMI_ID=$(aws ssm get-parameter \
  --region "$REGION" \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameter.Value' \
  --output text)
```

Comprueba:

```bash
echo "$AMI_ID"
```

## 3. Security Groups

Crea el Security Group público del ALB:

```bash
ALB_SG_ID=$(aws ec2 create-security-group \
  --region "$REGION" \
  --group-name asc-alb-sg \
  --description "HTTP publico para el ALB del reto" \
  --vpc-id "$VPC_ID" \
  --tag-specifications \
    'ResourceType=security-group,Tags=[{Key=Name,Value=asc-alb-sg},{Key=Project,Value=AutoScalingController}]' \
  --query GroupId \
  --output text)
```

Permite HTTP público en el puerto 80:

```bash
aws ec2 authorize-security-group-ingress \
  --region "$REGION" \
  --group-id "$ALB_SG_ID" \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0
```

Crea el Security Group de las instancias:

```bash
APP_SG_ID=$(aws ec2 create-security-group \
  --region "$REGION" \
  --group-name asc-app-sg \
  --description "Puerto 8080 solo desde el ALB del reto" \
  --vpc-id "$VPC_ID" \
  --tag-specifications \
    'ResourceType=security-group,Tags=[{Key=Name,Value=asc-app-sg},{Key=Project,Value=AutoScalingController}]' \
  --query GroupId \
  --output text)
```

Permite el puerto 8080 solamente desde el ALB:

```bash
aws ec2 authorize-security-group-ingress \
  --region "$REGION" \
  --group-id "$APP_SG_ID" \
  --protocol tcp \
  --port 8080 \
  --source-group "$ALB_SG_ID"
```

Comprueba los identificadores:

```bash
echo "$ALB_SG_ID"
echo "$APP_SG_ID"
```

## 4. Target Group

Crea el Target Group:

```bash
TG_ARN=$(aws elbv2 create-target-group \
  --region "$REGION" \
  --name asc-targets \
  --protocol HTTP \
  --port 8080 \
  --vpc-id "$VPC_ID" \
  --target-type instance \
  --health-check-protocol HTTP \
  --health-check-port traffic-port \
  --health-check-path /health \
  --health-check-interval-seconds 15 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 2 \
  --matcher HttpCode=200 \
  --tags Key=Project,Value=AutoScalingController \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)
```

Comprueba:

```bash
echo "$TG_ARN"
```

## 5. Application Load Balancer

Crea el ALB:

```bash
ALB_ARN=$(aws elbv2 create-load-balancer \
  --region "$REGION" \
  --name asc-alb \
  --type application \
  --scheme internet-facing \
  --ip-address-type ipv4 \
  --subnets "$SUBNET_A" "$SUBNET_B" \
  --security-groups "$ALB_SG_ID" \
  --tags Key=Project,Value=AutoScalingController \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)
```

Espera hasta que esté disponible:

```bash
aws elbv2 wait load-balancer-available \
  --region "$REGION" \
  --load-balancer-arns "$ALB_ARN"
```

Crea el listener HTTP:

```bash
LISTENER_ARN=$(aws elbv2 create-listener \
  --region "$REGION" \
  --load-balancer-arn "$ALB_ARN" \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn="$TG_ARN" \
  --query 'Listeners[0].ListenerArn' \
  --output text)
```

Obtén el DNS:

```bash
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --region "$REGION" \
  --load-balancer-arns "$ALB_ARN" \
  --query 'LoadBalancers[0].DNSName' \
  --output text)
```

Comprueba:

```bash
echo "$ALB_DNS"
```

## 6. Launch Template

Valida el script de inicio:

```bash
bash -n infra/user-data.sh
```

Codifica el script para enviarlo a EC2:

```bash
USER_DATA_B64=$(base64 < infra/user-data.sh | tr -d '\n')
```

Crea el Launch Template:

```bash
LT_ID=$(aws ec2 create-launch-template \
  --region "$REGION" \
  --launch-template-name asc-launch-template \
  --version-description "Aplicacion Python inicial" \
  --launch-template-data \
    "ImageId=$AMI_ID,InstanceType=t3.micro,SecurityGroupIds=[$APP_SG_ID],UserData=$USER_DATA_B64,TagSpecifications=[{ResourceType=instance,Tags=[{Key=Name,Value=asc-app-instance},{Key=Project,Value=AutoScalingController}]}]" \
  --tag-specifications \
    'ResourceType=launch-template,Tags=[{Key=Project,Value=AutoScalingController}]' \
  --query 'LaunchTemplate.LaunchTemplateId' \
  --output text)
```

Comprueba:

```bash
echo "$LT_ID"
```

## 7. Auto Scaling Group

Crea el ASG:

```bash
aws autoscaling create-auto-scaling-group \
  --region "$REGION" \
  --auto-scaling-group-name asc-web-asg \
  --launch-template "LaunchTemplateId=$LT_ID,Version=\$Latest" \
  --min-size 1 \
  --max-size 5 \
  --desired-capacity 1 \
  --default-instance-warmup 300 \
  --health-check-type ELB \
  --health-check-grace-period 300 \
  --vpc-zone-identifier "$SUBNET_A,$SUBNET_B" \
  --target-group-arns "$TG_ARN" \
  --tags \
    ResourceId=asc-web-asg,ResourceType=auto-scaling-group,Key=Name,Value=asc-web-asg,PropagateAtLaunch=true \
    ResourceId=asc-web-asg,ResourceType=auto-scaling-group,Key=Project,Value=AutoScalingController,PropagateAtLaunch=true
```

## 8. Verificación

Consulta el ASG:

```bash
aws autoscaling describe-auto-scaling-groups \
  --region "$REGION" \
  --auto-scaling-group-names asc-web-asg \
  --query 'AutoScalingGroups[0].[MinSize,MaxSize,DesiredCapacity,Instances[*].[InstanceId,LifecycleState,HealthStatus]]' \
  --output json
```

Espera hasta que aparezca una instancia `InService` y `Healthy`.

Comprueba el Target Group:

```bash
aws elbv2 describe-target-health \
  --region "$REGION" \
  --target-group-arn "$TG_ARN" \
  --query 'TargetHealthDescriptions[*].[Target.Id,Target.Port,TargetHealth.State]' \
  --output table
```

Comprueba que no existan políticas administradas:

```bash
aws autoscaling describe-policies \
  --region "$REGION" \
  --auto-scaling-group-name asc-web-asg \
  --query 'ScalingPolicies'
```

El resultado esperado es:

```json
[]
```

Prueba la aplicación:

```bash
curl -sS "http://$ALB_DNS/health"
```

Debe responder:

```text
OK
```

## 9. Recuperar variables en otra terminal

Las variables anteriores existen solamente en la terminal donde se
crearon. Para recuperar los principales identificadores:

```bash
TG_ARN=$(aws elbv2 describe-target-groups \
  --region us-east-1 \
  --names asc-targets \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)
```

```bash
ALB_ARN=$(aws elbv2 describe-load-balancers \
  --region us-east-1 \
  --names asc-alb \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)
```

```bash
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --region us-east-1 \
  --names asc-alb \
  --query 'LoadBalancers[0].DNSName' \
  --output text)
```
