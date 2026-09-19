# Cada instancia sana representa 40 unidades de demanda simulada.
CAPACITY_PER_INSTANCE = 40


# "def" crea una función; sus cuatro parámetros son los datos que recibe.
def decide(window, healthy, desired, blocked=False):
    # Si hay una acción en curso o cooldown, conservamos la capacidad.
    if blocked:
        # "return" entrega decisión, explicación y capacidad en una tupla.
        return ("MAINTAIN_CAPACITY", "Acción anterior en curso o cooldown", desired)

    # La capacidad deseada debe respetar el rango obligatorio del reto.
    if not 1 <= desired <= 5:
        return ("MAINTAIN_CAPACITY", "Capacidad deseada fuera de 1 a 5", desired)

    # Si aún no están sanas todas las instancias deseadas, esperamos.
    if healthy != desired:
        return ("MAINTAIN_CAPACITY", "Capacidad todavía no disponible", desired)

    # "len" cuenta lecturas; exigimos exactamente tres.
    if len(window) != 3:
        return ("MAINTAIN_CAPACITY", "Ventana incompleta", desired)

    # "any" detecta si alguna lectura no es un número.
    if any(not isinstance(value, (int, float)) for value in window):
        return ("MAINTAIN_CAPACITY", "Ventana con dato inválido", desired)

    # Una demanda negativa tampoco es válida.
    if any(value < 0 for value in window):
        return ("MAINTAIN_CAPACITY", "Ventana con demanda negativa", desired)

    # Este es el 80 % de la capacidad sana actual.
    high_limit = healthy * CAPACITY_PER_INSTANCE * 0.80

    # "all" exige que las tres lecturas superen el límite.
    if desired < 5 and all(value > high_limit for value in window):
        # Una f-string inserta valores concretos en la explicación.
        reason = f"Las tres lecturas {window} superan {high_limit:.1f}"
        return ("INCREASE_CAPACITY", reason, desired + 1)

    # Solo podemos estudiar una reducción si quedarían instancias.
    if desired > 1:
        # Calculamos el 60 % de la capacidad DESPUÉS de retirar una.
        low_limit = (healthy - 1) * CAPACITY_PER_INSTANCE * 0.60

        # Reducimos solo si las tres lecturas cabrían con ese margen.
        if all(value <= low_limit for value in window):
            reason = f"Las tres lecturas {window} caben bajo {low_limit:.1f}"
            return ("REDUCE_CAPACITY", reason, desired - 1)

    # Si ninguna regla anterior se cumplió, no cambiamos nada.
    return ("MAINTAIN_CAPACITY", "Demanda dentro de la banda estable", desired)
