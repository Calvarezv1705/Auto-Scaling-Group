# argparse permite probar el actuador desde Terminal.
import argparse

# json muestra resultados estructurados.
import json

# boto3 permite consultar y modificar el ASG.
import boto3


REGION = "us-east-1"
ASG_NAME = "asc-web-asg"

MAINTAIN = "MAINTAIN_CAPACITY"
INCREASE = "INCREASE_CAPACITY"
REDUCE = "REDUCE_CAPACITY"


def read_asg_state(client):
    # Consultamos siempre el estado real antes de actuar.
    response = client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[ASG_NAME]
    )

    groups = response["AutoScalingGroups"]

    if not groups:
        raise RuntimeError(f"No existe el ASG {ASG_NAME}")

    group = groups[0]

    # Contamos solo las instancias que ya están en servicio.
    in_service = sum(
        1
        for instance in group["Instances"]
        if instance["LifecycleState"] == "InService"
    )

    return {
        "minimum": group["MinSize"],
        "maximum": group["MaxSize"],
        "desired": group["DesiredCapacity"],
        "in_service": in_service,
    }


def apply_capacity(decision, target_capacity, execute=False):
    client = boto3.client(
        "autoscaling",
        region_name=REGION,
    )

    state = read_asg_state(client)
    current = state["desired"]

    # Mantener capacidad nunca debe llamar a set_desired_capacity.
    if decision == MAINTAIN:
        return {
            "status": "SKIPPED",
            "reason": "La decisión fue mantener capacidad",
            "before": state,
            "requested_capacity": current,
        }

    # El actuador no permite saltos de más de una instancia.
    expected_target = (
        current + 1
        if decision == INCREASE
        else current - 1
    )

    if target_capacity != expected_target:
        return {
            "status": "REJECTED",
            "reason": (
                f"Se esperaba capacidad {expected_target}, "
                f"pero se solicitó {target_capacity}"
            ),
            "before": state,
            "requested_capacity": target_capacity,
        }

    # Volvemos a aplicar los límites aunque el decisor ya los revisó.
    if not state["minimum"] <= target_capacity <= state["maximum"]:
        return {
            "status": "REJECTED",
            "reason": "La capacidad solicitada viola los límites del ASG",
            "before": state,
            "requested_capacity": target_capacity,
        }

    # Sin --execute mostramos la acción, pero no modificamos AWS.
    if not execute:
        return {
            "status": "DRY_RUN",
            "reason": "La acción es válida, pero no fue ejecutada",
            "before": state,
            "requested_capacity": target_capacity,
        }

    # Nuestro controlador gestiona su propio cooldown.
    client.set_desired_capacity(
        AutoScalingGroupName=ASG_NAME,
        DesiredCapacity=target_capacity,
        HonorCooldown=False,
    )

    # Confirmamos qué capacidad deseada informa AWS después de la llamada.
    after = read_asg_state(client)

    return {
        "status": "REQUESTED",
        "reason": "AWS aceptó la solicitud de capacidad",
        "before": state,
        "requested_capacity": target_capacity,
        "after": after,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Actuador del controlador de elasticidad."
    )

    parser.add_argument(
        "--decision",
        required=True,
        choices=[MAINTAIN, INCREASE, REDUCE],
    )
    parser.add_argument("--target", required=True, type=int)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Realiza el cambio en AWS",
    )
    args = parser.parse_args()

    result = apply_capacity(
        decision=args.decision,
        target_capacity=args.target,
        execute=args.execute,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()