# argparse recibe las opciones escritas en la terminal.
import argparse

# time contiene sleep, que permite esperar entre ciclos.
import time

# Reutilizamos el publicador y el generador ya probados.
from simulation.publisher import publish_point
from simulation.workload import generate_workload


def run_workload(start_cycle=1, count=None, interval=60, dry_run=False):
    # Generamos siempre la misma secuencia con la semilla predeterminada.
    workload = generate_workload()

    # Validamos que el primer ciclo exista.
    if not 1 <= start_cycle <= len(workload):
        raise ValueError(
            f"start_cycle debe estar entre 1 y {len(workload)}"
        )

    # Convertimos el número de ciclo en una posición de lista.
    start_index = start_cycle - 1

    # Si count no fue indicado, llegamos hasta el final.
    if count is None:
        selected = workload[start_index:]
    else:
        # El corte toma solamente la cantidad solicitada.
        selected = workload[start_index:start_index + count]

    # enumerate permite saber cuándo estamos en el último punto.
    for index, point in enumerate(selected):
        publish_point(point, dry_run=dry_run)

        # No esperamos después del último punto.
        is_last = index == len(selected) - 1

        if not is_last and interval > 0:
            print(f"Esperando {interval} segundos...")
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(
        description="Ejecuta una secuencia de demanda simulada."
    )

    parser.add_argument("--start-cycle", type=int, default=1)
    parser.add_argument("--count", type=int)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_workload(
        start_cycle=args.start_cycle,
        count=args.count,
        interval=args.interval,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()