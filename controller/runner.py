# argparse permite configurar el ejecutor desde la terminal.
import argparse

# json permite guardar errores con una estructura fácil de analizar.
import json

# time controla el intervalo entre ciclos.
import time

# Estas clases permiten registrar cada error con hora UTC.
from datetime import datetime, timezone

# Path construye la ruta del archivo de errores.
from pathlib import Path

# Estas excepciones representan fallos de AWS y boto3.
from botocore.exceptions import BotoCoreError, ClientError

# Reutilizamos el ciclo completo que ya probamos.
from controller.main import run_cycle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ERROR_LOG_PATH = PROJECT_ROOT / "experiments" / "controller_errors.jsonl"


def save_error(error):
    """
    Registra un fallo de AWS sin detener permanentemente el controlador.
    """

    record = {
        "cycle_time": datetime.now(timezone.utc).isoformat(),
        "status": "ERROR",
        "error_type": type(error).__name__,
        "reason": str(error),
    }

    ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with ERROR_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(record, indent=2, ensure_ascii=False))
    print(f"Error guardado en: {ERROR_LOG_PATH}")


def run_controller(
    interval_seconds=60,
    lookback_minutes=15,
    execute=False,
    cycles=None,
):
    """
    Ejecuta ciclos periódicos.

    cycles=None significa continuar hasta presionar Control + C.
    """

    completed_cycles = 0

    while cycles is None or completed_cycles < cycles:
        cycle_started = time.monotonic()

        print(
            f"\nIniciando ciclo {completed_cycles + 1} | "
            f"execute={execute}"
        )

        try:
            run_cycle(
                execute=execute,
                lookback_minutes=lookback_minutes,
            )
        except (BotoCoreError, ClientError, RuntimeError) as error:
            save_error(error)

        completed_cycles += 1

        # Si ya alcanzamos el número solicitado, terminamos sin esperar.
        if cycles is not None and completed_cycles >= cycles:
            break

        # monotonic mide duración sin depender de cambios en el reloj.
        elapsed = time.monotonic() - cycle_started
        remaining = max(0, interval_seconds - elapsed)

        print(f"Próximo ciclo en {remaining:.1f} segundos")

        time.sleep(remaining)


def main():
    parser = argparse.ArgumentParser(
        description="Ejecutor periódico del controlador de elasticidad"
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Segundos entre el inicio de cada ciclo",
    )

    parser.add_argument(
        "--minutes",
        type=int,
        default=15,
        help="Minutos consultados en CloudWatch",
    )

    parser.add_argument(
        "--cycles",
        type=int,
        help="Cantidad de ciclos; si se omite, continúa indefinidamente",
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Permite realizar cambios reales en el ASG",
    )

    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval debe ser mayor que 0")

    if args.minutes <= 0:
        parser.error("--minutes debe ser mayor que 0")

    if args.cycles is not None and args.cycles <= 0:
        parser.error("--cycles debe ser mayor que 0")

    try:
        run_controller(
            interval_seconds=args.interval,
            lookback_minutes=args.minutes,
            execute=args.execute,
            cycles=args.cycles,
        )
    except KeyboardInterrupt:
        print("\nControlador detenido por el usuario.")


if __name__ == "__main__":
    main()
