# argparse permite recibir opciones desde la terminal.
import argparse

# datetime genera la hora asociada a la medición.
from datetime import datetime, timezone

# boto3 es el SDK que permite llamar a servicios de AWS desde Python.
import boto3

# Reutilizamos la secuencia que ya construimos.
from simulation.workload import generate_workload


# Namespace: grupo que contendrá nuestras métricas en CloudWatch.
NAMESPACE = "AutoScalingController"

# Nombre exacto de la métrica que después leerá el monitor.
METRIC_NAME = "SimulatedDemand"

# Región asignada por AWS Academy.
REGION = "us-east-1"


def publish_point(point, dry_run=False):
    # CloudWatch guarda cada valor junto con una hora en UTC.
    timestamp = datetime.now(timezone.utc)

    # En dry-run solo mostramos el punto; no contactamos con AWS.
    if dry_run:
        print(
            f"DRY-RUN | ciclo={point['cycle']} | "
            f"fase={point['phase']} | demanda={point['demand']} | "
            f"hora={timestamp.isoformat()}"
        )
        return

    # Creamos un cliente de bajo nivel para el servicio CloudWatch.
    # Boto3 buscará las credenciales en ~/.aws/credentials.
    cloudwatch = boto3.client("cloudwatch", region_name=REGION)

    # put_metric_data envía uno o varios puntos a CloudWatch.
    response = cloudwatch.put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[
            {
                "MetricName": METRIC_NAME,
                "Dimensions": [
                    {
                        "Name": "Scenario",
                        "Value": "Challenge1",
                    }
                ],
                "Timestamp": timestamp,
                "Value": point["demand"],
                "Unit": "Count",
            }
        ],
    )

    # AWS devuelve 200 cuando recibió correctamente la solicitud.
    status = response["ResponseMetadata"]["HTTPStatusCode"]
    print(
        f"PUBLICADO | ciclo={point['cycle']} | "
        f"fase={point['phase']} | demanda={point['demand']} | "
        f"status={status}"
    )


def main():
    # Creamos el lector de opciones de la terminal.
    parser = argparse.ArgumentParser(
        description="Publica un punto de demanda simulada."
    )

    # --cycle permite escoger uno de los 26 ciclos.
    parser.add_argument("--cycle", type=int, default=1)

    # --dry-run activa el modo que no llama a AWS.
    parser.add_argument("--dry-run", action="store_true")

    # Convertimos las opciones escritas en valores de Python.
    args = parser.parse_args()

    workload = generate_workload()

    # Impedimos solicitar ciclos inexistentes.
    if not 1 <= args.cycle <= len(workload):
        parser.error(f"--cycle debe estar entre 1 y {len(workload)}")

    # Las listas empiezan en posición 0; por eso restamos uno.
    point = workload[args.cycle - 1]
    publish_point(point, dry_run=args.dry_run)


# Ejecutamos main solamente cuando se inicia este archivo como programa.
if __name__ == "__main__":
    main()