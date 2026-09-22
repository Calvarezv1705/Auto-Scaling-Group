# argparse permite cambiar el intervalo consultado desde la terminal.
import argparse

# Estas clases permiten calcular el inicio y final del intervalo.
from datetime import datetime, timedelta, timezone

# boto3 permite consultar CloudWatch desde Python.
import boto3


# Deben coincidir exactamente con los datos usados por el publicador.
REGION = "us-east-1"
NAMESPACE = "AutoScalingController"
METRIC_NAME = "SimulatedDemand"
SCENARIO = "Challenge1"
MAX_GAP_SECONDS = 90
MAX_METRIC_AGE_SECONDS = 240

def read_recent_demands(lookback_minutes=30, limit=3):
    # Creamos un cliente para consultar CloudWatch.
    cloudwatch = boto3.client("cloudwatch", region_name=REGION)

    # Usamos siempre horas UTC para evitar problemas de zona horaria.
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=lookback_minutes)

    # Pedimos promedios de períodos de 60 segundos.
    response = cloudwatch.get_metric_statistics(
        Namespace=NAMESPACE,
        MetricName=METRIC_NAME,
        Dimensions=[
            {
                "Name": "Scenario",
                "Value": SCENARIO,
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=60,
        Statistics=["Average"],
        Unit="Count",
    )

    # CloudWatch puede entregar los puntos en cualquier orden.
    ordered = sorted(
        response["Datapoints"],
        key=lambda point: point["Timestamp"],
    )

    # Conservamos solamente los últimos puntos solicitados.
    recent = ordered[-limit:]

    # Convertimos la respuesta de AWS a una estructura sencilla.
    return [
        {
            "timestamp": point["Timestamp"],
            "value": point["Average"],
        }
        for point in recent
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Lee la demanda simulada desde CloudWatch."
    )

    # Durante las pruebas podemos ampliar el tiempo de búsqueda.
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args()

    points = read_recent_demands(
        lookback_minutes=args.minutes,
        limit=3,
    )

    # Si CloudWatch no devolvió datos, lo indicamos claramente.
    if not points:
        print("No se encontraron mediciones.")
        return

    # Mostramos cada dato con su hora.
    for point in points:
        print(
            f"hora={point['timestamp'].isoformat()} | "
            f"demanda={point['value']:.1f}"
        )

    # Una ventana incompleta no puede enviarse al decisor.
    if len(points) < 3:
        print(f"Ventana incompleta: {len(points)}/3")
        return

    gaps = [
        (
            current["timestamp"] - previous["timestamp"]
        ).total_seconds()
        for previous, current in zip(points, points[1:])
    ]

    largest_gap = max(gaps)

    if largest_gap > MAX_GAP_SECONDS:
        print(
            "Ventana discontinua: separación máxima de "
            f"{int(largest_gap)} segundos"
        )
        return

    latest_timestamp = points[-1]["timestamp"].astimezone(timezone.utc)
    latest_age = (
        datetime.now(timezone.utc) - latest_timestamp
    ).total_seconds()

    if latest_age < -30:
        print("Ventana inválida: la última medición tiene una hora futura")
        return

    if latest_age > MAX_METRIC_AGE_SECONDS:
        print(
            "Ventana antigua: la última medición tiene "
            f"{int(latest_age)} segundos"
        )
        return

    window = [point["value"] for point in points]
    print(f"Ventana válida y completa: {window}")


if __name__ == "__main__":
    main()
