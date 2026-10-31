"""
Builds the three layers (bronze, silver, gold) described in the README.

  Bronze: the parsed readings as they came out of ingest.py, plus the
          quarantined rows.

  Silver: the validated readings with exact duplicates removed. Nothing
          else is dropped. Flagged rows stay, with their flags.

  Gold:   summaries built from silver. Right now that's a quality summary per
          device and day, and a before/after table for watering and
          fertilizing events.
"""
from datetime import timedelta

import pandas as pd

from . import config


def build_bronze(parsed: pd.DataFrame, quarantined: pd.DataFrame) -> dict:
    """Keeps the parsed and quarantined rows as two separate tables."""
    return {
        "readings": parsed.copy(),
        "quarantined": quarantined.copy(),
    }


def build_silver(validated: pd.DataFrame) -> pd.DataFrame:
    """
    Drops exact duplicates and nothing else. Rows with hard-bound violations,
    unit mismatches, flatlines or key conflicts stay in, with their flags.
    """
    silver = validated[~validated["is_full_duplicate"]].copy()
    silver = silver.drop(columns=["is_full_duplicate"])  # always False after dedup
    return silver


def build_gold_quality_summary(silver: pd.DataFrame) -> pd.DataFrame:
    """
    One row per device and day: number of readings, how many are suspect,
    the suspect rate, and a count for each flag. Sorted with the worst
    device-days first.
    """
    df = silver.copy()
    df["date"] = df["timestamp"].dt.date

    flag_cols = [c for c in df.columns if c.startswith("flag_") or c == "is_key_conflict"]

    agg_dict = {"is_suspect": ["size", "sum"]}
    for col in flag_cols:
        agg_dict[col] = ["sum"]

    summary = df.groupby(["device_id", "date"]).agg(agg_dict)
    summary.columns = ["_".join(c).strip("_") for c in summary.columns]
    summary = summary.rename(columns={
        "is_suspect_size": "total_readings",
        "is_suspect_sum": "suspect_readings",
    })
    summary["suspect_rate"] = (summary["suspect_readings"] / summary["total_readings"]).round(4)
    return summary.reset_index().sort_values("suspect_rate", ascending=False)


def build_gold_event_response(
    silver: pd.DataFrame,
    events: pd.DataFrame,
    before_window: timedelta = timedelta(hours=2),
    after_window: timedelta = timedelta(hours=2),
) -> pd.DataFrame:
    """
    For each logged event, compares the mean sensor value in the window before
    the event with the window after it. Watering is checked against
    soil_moisture and fertilizing against ec. Suspect readings are left out.

    This is a plain before/after mean. A small response on top of a bigger
    trend (soil drying out, for example) can be missed or even reversed by it.
    """
    relevant_sensor = {"watering": "soil_moisture", "fertilizing": "ec"}
    rows = []

    # The windows are timedelta objects, not strings like "2h". On pandas 2.3
    # with NumPy 2.5, pd.Timedelta("2h") and pd.Timedelta(hours=2) both raise a
    # DeprecationWarning about NumPy's "generic unit". Passing a timedelta
    # object doesn't.
    before_td = pd.Timedelta(before_window)
    after_td = pd.Timedelta(after_window)

    for event in events.itertuples():
        sensor_type = relevant_sensor.get(event.event_type)
        if sensor_type is None:
            continue

        device_data = silver[
            (silver["device_id"] == event.device_id)
            & (silver["sensor_type"] == sensor_type)
            & (~silver["is_suspect"])  # leave out flagged readings
        ]

        before = device_data[
            device_data["timestamp"].between(
                event.event_timestamp - before_td, event.event_timestamp
            )
        ]["value"].mean()

        after = device_data[
            device_data["timestamp"].between(
                event.event_timestamp, event.event_timestamp + after_td
            )
        ]["value"].mean()

        rows.append({
            "event_id": event.event_id,
            "device_id": event.device_id,
            "event_type": event.event_type,
            "event_timestamp": event.event_timestamp,
            "sensor_type": sensor_type,
            "mean_before": before,
            "mean_after": after,
            "delta": after - before if pd.notna(before) and pd.notna(after) else None,
        })

    return pd.DataFrame(rows)
