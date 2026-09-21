import argparse
import json

from datetime import datetime, timezone
from pathlib import Path

import boto3

from controller.actuator import (
    ASG_NAME,
    REGION,
    apply_capacity,
    read_asg_state,
)
from controller.decisor import decide
from controller.monitor import read_recent_demands


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = PROJECT_ROOT / "experiments" / "decision_log.jsonl"


def validate_window(points, expected_size=3, max_gap_seconds=90):
    # Una decisión normal requiere exactamente tres mediciones.
    if len(points) != expected_size:
        return None, f"Ventana incompleta: {len(points)}/{expected_size}"

    # Verificamos que no haya huecos grandes entre mediciones.
    for previous, current in zip(points, points[1:]):
        gap = (
            current["timestamp"] - previous["timestamp"]
        ).total_seconds()

        if gap <= 0 or gap > max_gap_seconds:
            return None, f"Mediciones no consecutivas: separación de {gap}s"

    return [point["value"] for point in points], None


def save_record(record):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )


def run_cycle(execute=False, lookback_minutes=10):
    cycle_time = datetime.now(timezone.utc)

    # Consultamos el ASG; ya no recibimos capacidad manual.
    autoscaling = boto3.client(
        "autoscaling",
        region_name=REGION,
    )
    state = read_asg_state(autoscaling)

    # Observamos la demanda desde CloudWatch.
    points = read_recent_demands(
        lookback_minutes=lookback_minutes,
        limit=3,
    )
    window, window_error = validate_window(points)

    # Mientras una instancia arranca o termina, bloqueamos otro cambio.
    capacity_changing = (
        state["in_service"] != state["desired"]
    )

    if window_error:
        decision = "MAINTAIN_CAPACITY"
        reason = window_error
        target_capacity = state["desired"]
    else:
        decision, reason, target_capacity = decide(
            window=window,
            healthy=state["in_service"],
            desired=state["desired"],
            blocked=capacity_changing,
        )

    if decision == "MAINTAIN_CAPACITY":
        requested_action = "NONE"
    else:
        requested_action = (
            f"SET_DESIRED_CAPACITY:{target_capacity}"
        )

    # El actuador consulta nuevamente el ASG antes de actuar.
    action_result = apply_capacity(
        decision=decision,
        target_capacity=target_capacity,
        execute=execute,
    )

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
        "asg_name": ASG_NAME,
        "minimum_capacity": state["minimum"],
        "maximum_capacity": state["maximum"],
        "healthy_capacity": state["in_service"],
        "desired_capacity": state["desired"],
        "capacity_changing": capacity_changing,
        "execution_enabled": execute,
        "decision": decision,
        "reason": reason,
        "requested_action": requested_action,
        "action_result": action_result,
    }

    save_record(record)

    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"Log guardado en: {LOG_PATH}")


def main():
    parser = argparse.ArgumentParser(
        description="Ejecuta un ciclo completo del controlador."
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Permite que el actuador cambie la capacidad real",
    )
    parser.add_argument("--minutes", type=int, default=10)
    args = parser.parse_args()

    run_cycle(
        execute=args.execute,
        lookback_minutes=args.minutes,
    )


if __name__ == "__main__":
    main()