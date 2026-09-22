import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3

from controller.actuator import ASG_NAME, REGION, apply_capacity, read_asg_state
from controller.decisor import decide
from controller.monitor import read_recent_demands


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = PROJECT_ROOT / "experiments" / "decision_log.jsonl"

# Tiempo mínimo entre dos cambios reales de capacidad.
COOLDOWN_SECONDS = 300

# No tomamos decisiones con una última medición de más de cuatro minutos.
MAX_METRIC_AGE_SECONDS = 240


def validate_window(
    points,
    now,
    expected_size=3,
    max_gap_seconds=90,
    max_age_seconds=MAX_METRIC_AGE_SECONDS,
):
    """
    Verifica que la ventana tenga tres mediciones consecutivas y recientes.
    """

    if len(points) != expected_size:
        return None, f"Ventana incompleta: {len(points)}/{expected_size}"

    # Comprobamos que las mediciones sean consecutivas.
    for previous, current in zip(points, points[1:]):
        gap = (
            current["timestamp"] - previous["timestamp"]
        ).total_seconds()

        if gap > max_gap_seconds:
            return None, (
                "Ventana discontinua: existen mediciones separadas "
                f"por {int(gap)} segundos"
            )

    # Comprobamos que la medición más reciente todavía represente
    # el estado actual de la aplicación.
    latest_timestamp = points[-1]["timestamp"].astimezone(timezone.utc)
    latest_age = (now - latest_timestamp).total_seconds()

    if latest_age < -30:
        return None, "La última medición tiene una hora futura"

    if latest_age > max_age_seconds:
        return None, (
            "La última medición es demasiado antigua: "
            f"{int(latest_age)} segundos"
        )

    window = [point["value"] for point in points]

    return window, None


def read_cooldown(now):
    """
    Busca en el registro la última acción aceptada por AWS.

    Retorna:
        cooldown_active: indica si todavía debemos esperar.
        remaining: segundos restantes del cooldown.
    """

    if not LOG_PATH.exists():
        return False, 0

    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()

    # Leemos desde el registro más reciente hacia el más antiguo.
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        action_result = record.get("action_result")

        # Algunos registros antiguos pueden tener otro formato.
        if not isinstance(action_result, dict):
            continue

        # Solo una acción realmente solicitada a AWS inicia cooldown.
        if action_result.get("status") != "REQUESTED":
            continue

        try:
            action_time = datetime.fromisoformat(record["cycle_time"])
        except (KeyError, TypeError, ValueError):
            continue

        action_time = action_time.astimezone(timezone.utc)
        elapsed = (now - action_time).total_seconds()

        remaining = max(
            0,
            int(COOLDOWN_SECONDS - elapsed),
        )

        return remaining > 0, remaining

    return False, 0


def save_record(record):
    """
    Guarda cada ciclo del controlador como una línea JSON.
    """

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )


def run_cycle(execute=False, lookback_minutes=10):
    """
    Ejecuta un ciclo completo:

    Monitor -> Análisis -> Decisión -> Actuación -> Registro
    """

    cycle_time = datetime.now(timezone.utc)

    # Leemos el estado real del Auto Scaling Group.
    autoscaling = boto3.client(
        "autoscaling",
        region_name=REGION,
    )
    state = read_asg_state(autoscaling)

    # El monitor usa el argumento lookback_minutes.
    points = read_recent_demands(
        lookback_minutes=lookback_minutes,
        limit=3,
    )

    window, window_error = validate_window(
        points=points,
        now=cycle_time,
    )

    # Si no están disponibles todas las instancias deseadas,
    # significa que el ASG todavía está cambiando.
    capacity_changing = (
        state["in_service"] != state["desired"]
    )

    cooldown_active, cooldown_remaining = read_cooldown(
        cycle_time
    )

    # Primera protección: datos incompletos, discontinuos o antiguos.
    if window_error:
        decision = "MAINTAIN_CAPACITY"
        reason = window_error
        target_capacity = state["desired"]

    # Segunda protección: esperar a que termine el cambio anterior.
    elif capacity_changing:
        decision = "MAINTAIN_CAPACITY"
        reason = (
            "El ASG todavía está cambiando: "
            f"{state['in_service']} en servicio de "
            f"{state['desired']} deseadas"
        )
        target_capacity = state["desired"]

    # Tercera protección: respetar el cooldown.
    elif cooldown_active:
        decision = "MAINTAIN_CAPACITY"
        reason = (
            "Cooldown activo después del último cambio: "
            f"faltan {cooldown_remaining} segundos"
        )
        target_capacity = state["desired"]

    else:
        # decide() recibe healthy y desired.
        # También devuelve una tupla con tres elementos.
        decision, reason, target_capacity = decide(
            window=window,
            healthy=state["in_service"],
            desired=state["desired"],
            blocked=False,
        )

    if decision == "MAINTAIN_CAPACITY":
        requested_action = "NONE"
    else:
        requested_action = (
            f"SET_DESIRED_CAPACITY:{target_capacity}"
        )

    # apply_capacity crea su propio cliente de Auto Scaling.
    action_result = apply_capacity(
        decision=decision,
        target_capacity=target_capacity,
        execute=execute,
    )

    record = {
        "cycle_time": cycle_time.isoformat(),
        "metric_name": "SimulatedDemand",
        "observation_minutes": lookback_minutes,
        "metrics": [
            {
                "timestamp": point["timestamp"].isoformat(),
                "value": point["value"],
            }
            for point in points
        ],
        "window": window,
        "asg_name": ASG_NAME,
        "minimum_capacity": state["minimum"],
        "maximum_capacity": state["maximum"],
        "healthy_capacity": state["in_service"],
        "desired_capacity": state["desired"],
        "capacity_changing": capacity_changing,
        "cooldown_active": cooldown_active,
        "cooldown_remaining_seconds": cooldown_remaining,
        "execution_enabled": execute,
        "decision": decision,
        "reason": reason,
        "requested_action": requested_action,
        "action_result": action_result,
    }

    save_record(record)

    print(
        json.dumps(
            record,
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"Log guardado en: {LOG_PATH}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta un ciclo del controlador "
            "de autoescalamiento"
        )
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Permite modificar la capacidad deseada del ASG",
    )

    parser.add_argument(
        "--minutes",
        type=int,
        default=10,
        help="Minutos consultados en CloudWatch",
    )

    args = parser.parse_args()

    run_cycle(
        execute=args.execute,
        lookback_minutes=args.minutes,
    )


if __name__ == "__main__":
    main()