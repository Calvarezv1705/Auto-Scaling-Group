# Infraestructura AWS reproducible

Este documento crea desde cero la infraestructura utilizada por el
controlador. 

No ejecutes los comandos si ya existen recursos con los nombres
`asc-vpc`, `asc-alb`, `asc-targets`, `asc-launch-template` y
`asc-web-asg`.

## Arquitectura de red

```text
Internet
   |
Internet Gateway
   |
VPC asc-vpc: 172.16.0.0/16
   |
   +-- Subred pública A: 172.16.1.0/24 (us-east-1a)
   |      +-- ALB
   |      +-- Instancias EC2 del ASG
   |
   +-- Subred pública B: 172.16.2.0/24 (us-east-1b)
          +-- ALB
          +-- Instancias EC2 del ASG
```

Las instancias se ubican en subredes públicas para que `user-data.sh`
pueda instalar paquetes sin el costo adicional de un NAT Gateway. El
Security Group de la aplicación no acepta tráfico público: el puerto
8080 solo recibe conexiones provenientes del Security Group del ALB.

En una arquitectura de producción sería preferible colocar las
instancias en subredes privadas y proporcionar salida mediante NAT
Gateway o VPC endpoints. Esa alternativa no se usa en este experimento
por costo y complejidad.

## 1. Requisitos

Activa el entorno virtual y comprueba las credenciales:

```bash
source .venv/bin/activate
aws sts get-caller-identity
```

Evita que AWS CLI abra el paginador y define la región:

```bash
export AWS_PAGER=""
REGION="us-east-1"
```

## 2. VPC personalizada

Define los rangos de red:

```bash
VPC_CIDR="172.16.0.0/16"
SUBNET_A_CIDR="172.16.1.0/24"
SUBNET_B_CIDR="172.16.2.0/24"
AZ_A="us-east-1a"
AZ_B="us-east-1b"
```

Crea la VPC:

```bash
VPC_ID=$(aws ec2 create-vpc \
  --region "$REGION" \
  --cidr-block "$VPC_CIDR" \
  --tag-specifications \
    'ResourceType=vpc,Tags=[{Key=Name,Value=asc-vpc},{Key=Project,Value=AutoScalingController}]' \
  --query 'Vpc.VpcId' \
  --output text)
```

Espera hasta que esté disponible:

```bash
aws ec2 wait vpc-available \
  --region "$REGION" \
  --vpc-ids "$VPC_ID"
```

Activa la resolución DNS y los nombres DNS internos:

```bash
aws ec2 modify-vpc-attribute \
  --region "$REGION" \
  --vpc-id "$VPC_ID" \
  --enable-dns-support '{"Value":true}'

aws ec2 modify-vpc-attribute \
  --region "$REGION" \
  --vpc-id "$VPC_ID" \
  --enable-dns-hostnames '{"Value":true}'
```

Comprueba que no sea la VPC predeterminada:

```bash
aws ec2 describe-vpcs \
  --region "$REGION" \
  --vpc-ids "$VPC_ID" \
  --query 'Vpcs[0].[VpcId,CidrBlock,IsDefault,State]' \
  --output table
```

El resultado debe mostrar `172.16.0.0/16`, `False` y `available`.

## 3. Internet Gateway

Crea el Internet Gateway:

```bash
IGW_ID=$(aws ec2 create-internet-gateway \
  --region "$REGION" \
  --tag-specifications \
    'ResourceType=internet-gateway,Tags=[{Key=Name,Value=asc-igw},{Key=Project,Value=AutoScalingController}]' \
  --query 'InternetGateway.InternetGatewayId' \
  --output text)
```

Conéctalo a la VPC:

```bash
aws ec2 attach-internet-gateway \
  --region "$REGION" \
  --internet-gateway-id "$IGW_ID" \
  --vpc-id "$VPC_ID"
```

## 4. Subredes públicas

Crea una subred en cada zona de disponibilidad:

```bash
SUBNET_A=$(aws ec2 create-subnet \
  --region "$REGION" \
  --vpc-id "$VPC_ID" \
  --cidr-block "$SUBNET_A_CIDR" \
  --availability-zone "$AZ_A" \
  --tag-specifications \
    'ResourceType=subnet,Tags=[{Key=Name,Value=asc-public-a},{Key=Project,Value=AutoScalingController}]' \
  --query 'Subnet.SubnetId' \
  --output text)

SUBNET_B=$(aws ec2 create-subnet \
  --region "$REGION" \
  --vpc-id "$VPC_ID" \
  --cidr-block "$SUBNET_B_CIDR" \
  --availability-zone "$AZ_B" \
  --tag-specifications \
    'ResourceType=subnet,Tags=[{Key=Name,Value=asc-public-b},{Key=Project,Value=AutoScalingController}]' \
  --query 'Subnet.SubnetId' \
  --output text)
```

Activa la asignación automática de IPv4 pública. Esto permite que las
instancias descarguen paquetes durante su arranque:

```bash
aws ec2 modify-subnet-attribute \
  --region "$REGION" \
  --subnet-id "$SUBNET_A" \
  --map-public-ip-on-launch

aws ec2 modify-subnet-attribute \
  --region "$REGION" \
  --subnet-id "$SUBNET_B" \
  --map-public-ip-on-launch
```

## 5. Tabla de rutas pública

Crea la tabla de rutas:

```bash
ROUTE_TABLE_ID=$(aws ec2 create-route-table \
  --region "$REGION" \
  --vpc-id "$VPC_ID" \
  --tag-specifications \
    'ResourceType=route-table,Tags=[{Key=Name,Value=asc-public-rt},{Key=Project,Value=AutoScalingController}]' \
  --query 'RouteTable.RouteTableId' \
  --output text)
```

Crea la ruta hacia Internet:

```bash
aws ec2 create-route \
  --region "$REGION" \
  --route-table-id "$ROUTE_TABLE_ID" \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id "$IGW_ID"
```

Asocia ambas subredes:

```bash
ROUTE_ASSOC_A=$(aws ec2 associate-route-table \
  --region "$REGION" \
  --route-table-id "$ROUTE_TABLE_ID" \
  --subnet-id "$SUBNET_A" \
  --query 'AssociationId' \
  --output text)

ROUTE_ASSOC_B=$(aws ec2 associate-route-table \
  --region "$REGION" \
  --route-table-id "$ROUTE_TABLE_ID" \
  --subnet-id "$SUBNET_B" \
  --query 'AssociationId' \
  --output text)
```

## 6. AMI

Obtén la versión actual de Amazon Linux 2023 para x86_64:

```bash
AMI_ID=$(aws ssm get-parameter \
  --region "$REGION" \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameter.Value' \
  --output text)
```

## 7. Security Groups

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

## 8. Target Group

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

## 9. Application Load Balancer

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

## 10. Launch Template

Valida y codifica el script de inicio:

```bash
bash -n infra/user-data.sh
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

## 11. Auto Scaling Group

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

## 12. Verificación final

Comprueba la red:

```bash
aws ec2 describe-vpcs \
  --region "$REGION" \
  --vpc-ids "$VPC_ID" \
  --query 'Vpcs[0].[VpcId,CidrBlock,IsDefault]' \
  --output table
```

`IsDefault` debe ser `False`.

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

El resultado esperado es `[]`.

Prueba la aplicación:

```bash
curl -sS "http://$ALB_DNS/health"
```

Debe responder `OK`.

## 13. Recuperar variables en otra terminal

Las variables anteriores existen solamente en la terminal donde se
crearon. Para recuperarlas por etiquetas y nombres:

```bash
VPC_ID=$(aws ec2 describe-vpcs \
  --region us-east-1 \
  --filters Name=tag:Name,Values=asc-vpc \
  --query 'Vpcs[?IsDefault==`false`]|[0].VpcId' \
  --output text)

SUBNET_A=$(aws ec2 describe-subnets \
  --region us-east-1 \
  --filters Name=vpc-id,Values="$VPC_ID" Name=tag:Name,Values=asc-public-a \
  --query 'Subnets[0].SubnetId' \
  --output text)

SUBNET_B=$(aws ec2 describe-subnets \
  --region us-east-1 \
  --filters Name=vpc-id,Values="$VPC_ID" Name=tag:Name,Values=asc-public-b \
  --query 'Subnets[0].SubnetId' \
  --output text)

TG_ARN=$(aws elbv2 describe-target-groups \
  --region us-east-1 \
  --names asc-targets \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

ALB_ARN=$(aws elbv2 describe-load-balancers \
  --region us-east-1 \
  --names asc-alb \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)

ALB_DNS=$(aws elbv2 describe-load-balancers \
  --region us-east-1 \
  --names asc-alb \
  --query 'LoadBalancers[0].DNSName' \
  --output text)
```
