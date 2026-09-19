# argparse recibe el estado de capacidad desde la terminal.
import argparse

# json convierte diccionarios de Python en texto estructurado.
import json

# datetime genera la hora del ciclo.
from datetime import datetime, timezone

# Path construye rutas que funcionan desde cualquier carpeta.
from pathlib import Path

# Importamos los dos módulos que ya probamos.
from controller.decisor import decide
from controller.monitor import read_recent_demands


# Guardaremos los registros dentro de experiments.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = PROJECT_ROOT / "experiments" / "decision_log.jsonl"


def validate_window(points, expected_size=3, max_gap_seconds=90):
    # El decisor necesita exactamente tres puntos.
    if len(points) != expected_size:
        return None, f"Ventana incompleta: {len(points)}/{expected_size}"

    # Revisamos cada pareja de mediciones consecutivas.
    for previous, current in zip(points, points[1:]):
        gap = (
            current["timestamp"] - previous["timestamp"]
        ).total_seconds()

        # Con publicación cada 60 segundos, aceptamos hasta 90.
        if gap <= 0 or gap > max_gap_seconds:
            return None, f"Mediciones no consecutivas: separación de {gap}s"

    # Extraemos solo los valores cuando las horas son válidas.
    window = [point["value"] for point in points]
    return window, None


def save_record(record):
    # La carpeta ya existe, pero esta línea hace la función más resistente.
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # "a" añade una línea sin borrar registros anteriores.
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )


def run_cycle(healthy, desired, blocked=False, lookback_minutes=10):
    # La hora del ciclo queda registrada en UTC.
    cycle_time = datetime.now(timezone.utc)

    # La observación proviene realmente de CloudWatch.
    points = read_recent_demands(
        lookback_minutes=lookback_minutes,
        limit=3,
    )

    window, window_error = validate_window(points)

    # Una ventana inválida produce mantenimiento seguro.
    if window_error:
        decision = "MAINTAIN_CAPACITY"
        reason = window_error
        target_capacity = desired
    else:
        decision, reason, target_capacity = decide(
            window=window,
            healthy=healthy,
            desired=desired,
            blocked=blocked,
        )

    # Traducimos la decisión a la acción que el actuador deberá ejecutar.
    if decision == "MAINTAIN_CAPACITY":
        requested_action = "NONE"
    else:
        requested_action = f"SET_DESIRED_CAPACITY:{target_capacity}"

    # Convertimos las horas a texto para que JSON pueda guardarlas.
    metrics = [
        {
            "timestamp": point["timestamp"].isoformat(),
            "value": point["value"],
        }
        for point in points
    ]

    record = {
        "cycle_time": cycle_time.isoformat(),
        "metric_name": "SimulatedDemand",
        "observation_minutes": lookback_minutes,
        "metrics": metrics,
        "window": window,
        "healthy_capacity": healthy,
        "desired_capacity": desired,
        "blocked": blocked,
        "decision": decision,
        "reason": reason,
        "requested_action": requested_action,
        "action_result": "ACTUATOR_PENDING",
    }

    save_record(record)

    # indent=2 muestra el registro de forma legible en Terminal.
    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"Log guardado en: {LOG_PATH}")


def main():
    parser = argparse.ArgumentParser(
        description="Ejecuta un ciclo del controlador."
    )

    parser.add_argument("--healthy", type=int, required=True)
    parser.add_argument("--desired", type=int, required=True)
    parser.add_argument("--blocked", action="store_true")
    parser.add_argument("--minutes", type=int, default=10)
    args = parser.parse_args()

    run_cycle(
        healthy=args.healthy,
        desired=args.desired,
        blocked=args.blocked,
        lookback_minutes=args.minutes,
    )


if __name__ == "__main__":
    main()