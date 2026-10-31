"""
Generates the synthetic sensor data used by the pipeline.

Writes two files to data/sample/:
  - sensor_readings.csv
  - context_events.csv

All values are made up. The random seed is fixed, so every run gives the same
files. Some problems are added on purpose (see the comments below), so the
pipeline can be checked against issues we know are there.

Run: python scripts/generate_sample_data.py
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
random.seed(SEED)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEVICES = [f"DEV-{i:02d}" for i in range(1, 9)]  # DEV-01 .. DEV-08
START = datetime(2026, 1, 1, 0, 0, 0)
DAYS = 14
INTERVAL_MIN = 15
N_STEPS = (DAYS * 24 * 60) // INTERVAL_MIN  # readings per device over the window

SENSOR_TYPES = {
    "soil_moisture": {"unit": "%", "base": 35, "noise": 3},
    "soil_temp": {"unit": "C", "base": 20, "noise": 1.5},
    "ec": {"unit": "uS_cm", "base": 750, "noise": 60},
    "humidity": {"unit": "%", "base": 55, "noise": 5},
}


def iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


# --- Event response ---
# Watering raises soil moisture a little and fertilizing raises EC, for a few
# hours afterwards. The effect is small compared to the sensor noise, so a
# single event can easily miss it. It should show up across many events.
WATERING_PEAK_MEAN, WATERING_PEAK_STD = 2.5, 0.6   # soil_moisture, % VWC
WATERING_DECAY_TAU_HOURS = 0.6
WATERING_LOOKBACK_HOURS = 3

FERTILIZING_PEAK_MEAN, FERTILIZING_PEAK_STD = 120, 25  # ec, uS/cm
FERTILIZING_RISE_TAU_HOURS = 2.0
FERTILIZING_LOOKBACK_HOURS = 8


def _most_recent_event(device_events, current_ts, event_type, max_lookback_hours):
    """
    Returns the hours since the most recent event of this type before
    current_ts, or None if there isn't one inside the lookback window. Only
    the latest event counts, so overlapping events aren't added together.
    """
    best = None
    for ev_ts, ev_type in device_events:
        if ev_type != event_type or ev_ts > current_ts:
            continue
        elapsed_hours = (current_ts - ev_ts).total_seconds() / 3600
        if elapsed_hours > max_lookback_hours:
            continue
        if best is None or ev_ts > best:
            best = ev_ts
    if best is None:
        return None
    return (current_ts - best).total_seconds() / 3600


def event_response_delta(device_events, current_ts, sensor_type):
    """
    Returns the amount to add to a reading because of a recent event, or 0.0
    if there isn't one. Uses the shared random state, so it's still the same
    every run with the fixed seed.
    """
    if sensor_type == "soil_moisture":
        elapsed = _most_recent_event(device_events, current_ts, "watering", WATERING_LOOKBACK_HOURS)
        if elapsed is None:
            return 0.0
        peak = random.gauss(WATERING_PEAK_MEAN, WATERING_PEAK_STD)
        return peak * pow(2.71828, -elapsed / WATERING_DECAY_TAU_HOURS)

    if sensor_type == "ec":
        elapsed = _most_recent_event(device_events, current_ts, "fertilizing", FERTILIZING_LOOKBACK_HOURS)
        if elapsed is None:
            return 0.0
        peak = random.gauss(FERTILIZING_PEAK_MEAN, FERTILIZING_PEAK_STD)
        return peak * (1 - pow(2.71828, -elapsed / FERTILIZING_RISE_TAU_HOURS))

    return 0.0


def generate_readings(events):
    # Group the events by device once, so they aren't filtered again for
    # every reading.
    events_by_device = {}
    for e in events:
        events_by_device.setdefault(e["device_id"], []).append(
            (datetime.strptime(e["event_timestamp"], "%Y-%m-%d %H:%M:%S"), e["event_type"])
        )

    rows = []
    for device in DEVICES:
        # small baseline offset per device, so the devices aren't identical
        device_offset = {k: random.uniform(-3, 3) for k in SENSOR_TYPES}
        device_events = events_by_device.get(device, [])

        for step in range(N_STEPS):
            ts = START + timedelta(minutes=INTERVAL_MIN * step)

            for sensor_type, cfg in SENSOR_TYPES.items():
                value = cfg["base"] + device_offset[sensor_type] + random.gauss(0, cfg["noise"])
                value += event_response_delta(device_events, ts, sensor_type)
                unit = cfg["unit"]
                timestamp_str = iso(ts)

                # DEV-07: soil_moisture rows use a different timestamp format
                if device == "DEV-07" and sensor_type == "soil_moisture":
                    timestamp_str = ts.strftime("%d/%m/%Y %H:%M")  # different format, no seconds

                # DEV-02: soil_temp is labelled "F" in the unit column. The values
                # themselves are normal Celsius readings, only the label is wrong.
                if device == "DEV-02" and sensor_type == "soil_temp":
                    unit = "F"

                # DEV-06: soil_moisture gets stuck on one value for the second half
                if device == "DEV-06" and sensor_type == "soil_moisture" and step >= N_STEPS // 2:
                    value = 28.4  # no noise

                # DEV-03: EC drifts upward through the second half. This also replaces
                # any fertilizing bump on those rows.
                if device == "DEV-03" and sensor_type == "ec" and step >= N_STEPS // 2:
                    progress = (step - N_STEPS // 2) / (N_STEPS // 2)
                    value = cfg["base"] + device_offset[sensor_type] + progress * 1400 + random.gauss(0, 20)

                # DEV-04: no rows at all for a 2-day stretch
                if device == "DEV-04":
                    gap_start_step = N_STEPS // 3
                    gap_len_steps = (2 * 24 * 60) // INTERVAL_MIN
                    if gap_start_step <= step < gap_start_step + gap_len_steps:
                        continue  # no row at all, which is different from a null value

                rows.append({
                    "device_id": device,
                    "timestamp": timestamp_str,
                    "sensor_type": sensor_type,
                    "value": round(value, 2),
                    "unit": unit,
                })

    # DEV-05: three impossible moisture readings, plus exact duplicates
    impossible_rows = []
    for step in [10, 25, 40]:
        ts = START + timedelta(minutes=INTERVAL_MIN * step)
        impossible_rows.append({
            "device_id": "DEV-05", "timestamp": iso(ts), "sensor_type": "soil_moisture",
            "value": -4.2, "unit": "%",
        })
    rows.extend(impossible_rows)
    # three DEV-05 rows repeated at the end, like a retransmission
    dev05_rows = [r for r in rows if r["device_id"] == "DEV-05"][:3]
    rows.extend([dict(r) for r in dev05_rows])

    return rows


def generate_context_events():
    rows = []
    event_id = 0
    for device in DEVICES:
        n_events = random.randint(3, 6)
        for _ in range(n_events):
            step = random.randint(0, N_STEPS - 1)
            ts = START + timedelta(minutes=INTERVAL_MIN * step)
            event_type = random.choice(["watering", "watering", "fertilizing"])
            text = {
                "watering": random.choice(["Watered ~200ml", "Gave it a good soak", "Quick water"]),
                "fertilizing": random.choice(["Liquid feed", "Diluted seaweed feed"]),
            }[event_type]
            rows.append({
                "event_id": event_id, "device_id": device, "event_timestamp": iso(ts),
                "event_type": event_type, "event_text": text,
            })
            event_id += 1
    return rows


def main():
    events = generate_context_events()
    readings = generate_readings(events)

    readings_path = OUT_DIR / "sensor_readings.csv"
    with open(readings_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["device_id", "timestamp", "sensor_type", "value", "unit"])
        writer.writeheader()
        writer.writerows(readings)

    events_path = OUT_DIR / "context_events.csv"
    with open(events_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["event_id", "device_id", "event_timestamp", "event_type", "event_text"])
        writer.writeheader()
        writer.writerows(events)

    print(f"Wrote {len(readings)} sensor readings -> {readings_path}")
    print(f"Wrote {len(events)} context events -> {events_path}")
    print(f"Seed: {SEED} (deterministic -- re-running reproduces identical output)")


if __name__ == "__main__":
    main()
