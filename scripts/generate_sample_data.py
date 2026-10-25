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


# --- Event-response model ---
# A deliberately SUBTLE, not obvious, effect: comparable in size to the
# existing sensor noise, so a naive single-event before/after check can
# plausibly miss it on any given event, the same "small real signal
# riding on noise" property as the real-world case this project is
# modelled on. The signal is real and should show up in AGGREGATE across
# many events, not necessarily on every individual one.
WATERING_PEAK_MEAN, WATERING_PEAK_STD = 2.5, 0.6   # soil_moisture, % VWC
WATERING_DECAY_TAU_HOURS = 0.6
WATERING_LOOKBACK_HOURS = 3

FERTILIZING_PEAK_MEAN, FERTILIZING_PEAK_STD = 120, 25  # ec, uS/cm
FERTILIZING_RISE_TAU_HOURS = 2.0
FERTILIZING_LOOKBACK_HOURS = 8


def _most_recent_event(device_events, current_ts, event_type, max_lookback_hours):
    """
    Finds the closest PRIOR event of the given type for this device,
    within the lookback window. Only the single most recent qualifying
    event is used, not a sum over several, to keep the response model
    simple and avoid double-counting overlapping events.
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
    Returns an additive delta to apply to a reading, based on the most
    recent relevant prior event, or 0.0 if none qualifies. Deterministic
    given the shared `random` module state, so still fully reproducible
    under the fixed seed.
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
    # Index events per device once, instead of re-filtering the full
    # events list on every single reading, that would be O(readings x
    # events) unnecessarily; this is a cheap one-time grouping instead.
    events_by_device = {}
    for e in events:
        events_by_device.setdefault(e["device_id"], []).append(
            (datetime.strptime(e["event_timestamp"], "%Y-%m-%d %H:%M:%S"), e["event_type"])
        )

    rows = []
    for device in DEVICES:
        # each device gets its own slight baseline offset so devices aren't identical
        device_offset = {k: random.uniform(-3, 3) for k in SENSOR_TYPES}
        device_events = events_by_device.get(device, [])

        for step in range(N_STEPS):
            ts = START + timedelta(minutes=INTERVAL_MIN * step)

            for sensor_type, cfg in SENSOR_TYPES.items():
                value = cfg["base"] + device_offset[sensor_type] + random.gauss(0, cfg["noise"])
                value += event_response_delta(device_events, ts, sensor_type)
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
