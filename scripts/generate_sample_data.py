"""
Deterministic synthetic sensor data generator.

Produces two files under data/sample/:
  - sensor_readings.csv
  - context_events.csv

Fully synthetic. Fixed random seed -> identical output every run, so the
pipeline's behaviour can be verified against known-injected issues rather
than against a dataset whose problems were discovered, not designed.

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


def generate_readings():
    rows = []
    for device in DEVICES:
        # each device gets its own slight baseline offset so devices aren't identical
        device_offset = {k: random.uniform(-3, 3) for k in SENSOR_TYPES}

        for step in range(N_STEPS):
            ts = START + timedelta(minutes=INTERVAL_MIN * step)

            for sensor_type, cfg in SENSOR_TYPES.items():
                value = cfg["base"] + device_offset[sensor_type] + random.gauss(0, cfg["noise"])
                unit = cfg["unit"]
                timestamp_str = iso(ts)

                # --- Issue 3: DEV-07 malformed timestamp format for soil_moisture rows ---
                if device == "DEV-07" and sensor_type == "soil_moisture":
                    timestamp_str = ts.strftime("%d/%m/%Y %H:%M")  # different format, no seconds

                # --- Issue 2: DEV-02's soil_temp unit field is mislabelled as "F" ---
                # The VALUE is a normal Celsius reading; the UNIT COLUMN is wrong.
                # This is what a literal unit-mismatch check is meant to catch:
                # a declared unit that disagrees with the contract's expected unit
                # for this sensor_type, independent of whether the number itself
                # looks plausible.
                if device == "DEV-02" and sensor_type == "soil_temp":
                    unit = "F"

                # --- Issue 6: DEV-06 soil_moisture sticks at one exact value for a long run ---
                if device == "DEV-06" and sensor_type == "soil_moisture" and step >= N_STEPS // 2:
                    value = 28.4  # exact stuck value, no noise

                # --- Issue 7: DEV-03 EC drifts smoothly upward over the back half of the window ---
                if device == "DEV-03" and sensor_type == "ec" and step >= N_STEPS // 2:
                    progress = (step - N_STEPS // 2) / (N_STEPS // 2)
                    value = cfg["base"] + device_offset[sensor_type] + progress * 1400 + random.gauss(0, 20)

                # --- Issue 4: DEV-04 has a clean 2-day gap (skip writing rows entirely) ---
                if device == "DEV-04":
                    gap_start_step = N_STEPS // 3
                    gap_len_steps = (2 * 24 * 60) // INTERVAL_MIN
                    if gap_start_step <= step < gap_start_step + gap_len_steps:
                        continue  # no row written -> a real gap, not a null

                rows.append({
                    "device_id": device,
                    "timestamp": timestamp_str,
                    "sensor_type": sensor_type,
                    "value": round(value, 2),
                    "unit": unit,
                })

    # --- Issue 5: DEV-05 impossible values + exact duplicate rows ---
    impossible_rows = []
    for step in [10, 25, 40]:
        ts = START + timedelta(minutes=INTERVAL_MIN * step)
        impossible_rows.append({
            "device_id": "DEV-05", "timestamp": iso(ts), "sensor_type": "soil_moisture",
            "value": -4.2, "unit": "%",
        })
    rows.extend(impossible_rows)
    # exact duplicates of 3 legitimate DEV-05 rows, appended at the end (retransmission-style)
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
    readings = generate_readings()
    events = generate_context_events()

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
