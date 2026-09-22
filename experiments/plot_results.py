import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


# Matplotlib necesita una carpeta local para su caché.
MPL_CONFIG = Path(tempfile.gettempdir()) / "autoscaling-matplotlib"
MPL_CONFIG.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("MPLCONFIGDIR", str(MPL_CONFIG))
os.environ.setdefault("XDG_CACHE_HOME", str(MPL_CONFIG))

import matplotlib

# Agg permite generar la imagen sin abrir una ventana gráfica.
matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = PROJECT_ROOT / "experiments" / "final-experiment.jsonl"
OUTPUT_PATH = PROJECT_ROOT / "experiments" / "time-series.png"

MAX_GAP_SECONDS = 90


def load_records():
    records = []

    with LOG_PATH.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"JSON inválido en la línea {line_number}"
                ) from error

    if not records:
        raise ValueError("El experimento no contiene registros")

    return records


def collect_metrics(records):
    metrics_by_time = {}

    for record in records:
        for metric in record.get("metrics", []):
            timestamp = datetime.fromisoformat(metric["timestamp"])
            metrics_by_time[timestamp] = float(metric["value"])

    if not metrics_by_time:
        raise ValueError("El experimento no contiene métricas")

    return sorted(metrics_by_time.items())


def split_segments(metrics):
    segments = []
    current_segment = []

    for timestamp, value in metrics:
        if current_segment:
            previous_time = current_segment[-1][0]
            gap = (timestamp - previous_time).total_seconds()

            if gap > MAX_GAP_SECONDS:
                segments.append(current_segment)
                current_segment = []

        current_segment.append((timestamp, value))

    if current_segment:
        segments.append(current_segment)

    return segments


def collect_capacity_events(records, start_time, end_time):
    current_capacity = int(records[0]["desired_capacity"])

    events = [(start_time, current_capacity)]

    for record in records:
        result = record.get("action_result")

        if not isinstance(result, dict):
            continue

        if result.get("status") != "REQUESTED":
            continue

        after = result.get("after", {})

        if "desired" not in after:
            continue

        timestamp = datetime.fromisoformat(record["cycle_time"])
        current_capacity = int(after["desired"])

        events.append((timestamp, current_capacity))

    events.sort(key=lambda event: event[0])
    events.append((end_time, current_capacity))

    return events


def create_chart(records):
    metrics = collect_metrics(records)
    segments = split_segments(metrics)

    decision_times = [
        datetime.fromisoformat(record["cycle_time"])
        for record in records
    ]

    start_time = min(metrics[0][0], decision_times[0])

    end_time = (
        max(metrics[-1][0], decision_times[-1])
        + timedelta(minutes=1)
    )

    capacity_events = collect_capacity_events(
        records,
        start_time,
        end_time,
    )

    figure, demand_axis = plt.subplots(figsize=(12, 6.5))

    # Dibujamos cada grupo consecutivo por separado.
    for index, segment in enumerate(segments):
        times = [point[0] for point in segment]
        values = [point[1] for point in segment]

        demand_axis.plot(
            times,
            values,
            color="#2563eb",
            marker="o",
            linewidth=2.2,
            markersize=6,
            label="Demanda simulada" if index == 0 else None,
        )

    demand_axis.set_ylabel(
        "Demanda simulada",
        color="#1d4ed8",
    )
    demand_axis.set_ylim(0, 105)
    demand_axis.tick_params(
        axis="y",
        labelcolor="#1d4ed8",
    )
    demand_axis.grid(
        True,
        axis="both",
        alpha=0.25,
    )

    decision_styles = {
        "MAINTAIN_CAPACITY": ("#64748b", "MANTENER"),
        "INCREASE_CAPACITY": ("#dc2626", "AUMENTAR"),
        "REDUCE_CAPACITY": ("#16a34a", "REDUCIR"),
    }

    # Marcamos la hora de cada decisión.
    for record in records:
        timestamp = datetime.fromisoformat(record["cycle_time"])
        decision = record["decision"]

        color, label = decision_styles[decision]

        if "discontinua" in record.get("reason", "").lower():
            label = "MANTENER\n(datos discontinuos)"

        demand_axis.axvline(
            timestamp,
            color=color,
            linestyle="--",
            linewidth=1.3,
            alpha=0.8,
        )

        demand_axis.text(
            timestamp,
            101,
            label,
            color=color,
            fontsize=8,
            rotation=90,
            horizontalalignment="right",
            verticalalignment="top",
        )

    # El segundo eje representa la capacidad deseada.
    capacity_axis = demand_axis.twinx()

    capacity_times = [
        event[0]
        for event in capacity_events
    ]

    capacity_values = [
        event[1]
        for event in capacity_events
    ]

    capacity_axis.step(
        capacity_times,
        capacity_values,
        where="post",
        color="#f59e0b",
        linewidth=2.5,
        label="Capacidad deseada",
    )

    capacity_axis.set_ylabel(
        "Instancias deseadas",
        color="#b45309",
    )
    capacity_axis.set_ylim(0.5, 5.5)
    capacity_axis.set_yticks(range(1, 6))
    capacity_axis.tick_params(
        axis="y",
        labelcolor="#b45309",
    )

    demand_axis.xaxis.set_major_formatter(
        mdates.DateFormatter(
            "%H:%M",
            tz=timezone.utc,
        )
    )

    demand_axis.set_xlabel(
        "Hora del experimento (UTC)"
    )

    demand_lines, demand_labels = (
        demand_axis.get_legend_handles_labels()
    )

    capacity_lines, capacity_labels = (
        capacity_axis.get_legend_handles_labels()
    )

    demand_axis.legend(
        demand_lines + capacity_lines,
        demand_labels + capacity_labels,
        loc="upper left",
    )

    figure.suptitle(
        "Experimento del controlador de autoescalamiento",
        fontsize=16,
        fontweight="bold",
    )

    demand_axis.set_title(
        "Demanda observada, decisiones y capacidad deseada",
        fontsize=11,
    )

    figure.text(
        0.5,
        0.015,
        "Fuente: experiments/final-experiment.jsonl | Semilla: 3016",
        horizontalalignment="center",
        fontsize=9,
        color="#475569",
    )

    figure.tight_layout(
        rect=(0, 0.04, 1, 0.94)
    )

    figure.savefig(
        OUTPUT_PATH,
        dpi=180,
        bbox_inches="tight",
    )

    plt.close(figure)

    print(f"Gráfica guardada en: {OUTPUT_PATH}")


def main():
    records = load_records()
    create_chart(records)


if __name__ == "__main__":
    main()
