# "random" pertenece a la biblioteca estándar de Python.
import random


# La semilla predeterminada identifica nuestro escenario reproducible.
DEFAULT_SEED = 3016


def generate_workload(seed=DEFAULT_SEED):
    # Creamos un generador independiente con una semilla fija.
    # No altera otros usos de random dentro del programa.
    generator = random.Random(seed)

    # Cada tupla contiene: nombre, cantidad de ciclos, mínimo y máximo.
    phases = [
        ("LOW", 6, 15, 22),
        ("MEDIUM", 4, 30, 45),
        ("HIGH", 8, 70, 90),
        ("RECOVERY", 8, 15, 22),
    ]

    # Aquí acumularemos todas las mediciones generadas.
    workload = []

    # Empezamos a numerar los ciclos desde 1.
    cycle = 1

    # Recorremos cada fase y desempaquetamos sus cuatro valores.
    for phase, duration, minimum, maximum in phases:
        # "_" indica que no necesitamos usar el número de repetición.
        for _ in range(duration):
            # randint elige un entero dentro del intervalo, incluidos sus extremos.
            demand = generator.randint(minimum, maximum)

            # Guardamos los datos del ciclo en un diccionario.
            workload.append(
                {
                    "cycle": cycle,
                    "phase": phase,
                    "demand": demand,
                }
            )

            cycle += 1

    return workload


# Este bloque se ejecuta solamente al abrir el archivo como programa.
if __name__ == "__main__":
    for point in generate_workload():
        print(
            f"Ciclo {point['cycle']:02d} | "
            f"fase={point['phase']:<8} | "
            f"demanda={point['demand']}"
        )