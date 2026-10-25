"""
Transform layer: turns ingested + validated data into the three logical
layers described in README.md.

  Bronze: raw or minimally altered records. What ingest.py produced,
          basically untouched, just tagged. This is what you'd replay
          FROM if a downstream bug needed reprocessing from scratch.

  Silver: standardized, validated, DEDUPLICATED records. The only rows
          actually removed between bronze and silver are exact full-row
          duplicates (config.FULL_ROW_MATCH_COLUMNS), because that's the
          one case where deletion loses zero information. Everything
          else, flagged or not, survives into silver with its flags
          intact. is_suspect=True does NOT mean "removed here."

  Gold:   analytics-ready summaries built FROM silver. Two tables for
          now: a per-device-per-day quality summary, and a before/after
          event-response table (watering->moisture, fertilizing->EC),
          directly answering the kind of question a modelling team would
          actually ask this data.
"""
import pandas as pd

from . import config


def build_bronze(parsed: pd.DataFrame, quarantined: pd.DataFrame) -> dict:
    """
    Bronze is intentionally thin: just the ingest.py output, split into
    two named tables rather than one, so a consumer can tell at a glance
    what passed structural ingestion vs. what didn't, without having to
    filter a reason column themselves.
    """
    return {
        "readings": parsed.copy(),
        "quarantined": quarantined.copy(),
    }


def build_silver(validated: pd.DataFrame) -> pd.DataFrame:
    """
    Drops ONLY exact full-row duplicates. Every other flagged row
    (hard-bound violations, unit mismatches, flatlines, key conflicts)
    stays in silver, flags and all, so nothing downstream silently loses
    visibility into a real, unresolved data-quality question.
    """
    silver = validated[~validated["is_full_duplicate"]].copy()
    silver = silver.drop(columns=["is_full_duplicate"])  # no longer meaningful post-dedup
    return silver


def build_gold_quality_summary(silver: pd.DataFrame) -> pd.DataFrame:
    """
    Per (device_id, date): how many readings, what fraction suspect, and
    a breakdown by flag type. This is the table a fleet dashboard would
    actually query, sortable by worst-offenders-first.
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
    before_window="2h",
    after_window="2h",
) -> pd.DataFrame:
    """
    For every logged event, compares the mean sensor value in the window
    before vs. after the event, for the sensor_type that event SHOULD
    plausibly affect (watering -> soil_moisture, fertilizing -> ec).

    This mirrors the original FYTA-style watering/fertilizing analysis:
    deliberately a simple before/after mean here, not a detrended check,
    documented as a known limitation (see docs/design_decisions.md),
    not hidden.
    """
    relevant_sensor = {"watering": "soil_moisture", "fertilizing": "ec"}
    rows = []

    for event in events.itertuples():
        sensor_type = relevant_sensor.get(event.event_type)
        if sensor_type is None:
            continue

        device_data = silver[
            (silver["device_id"] == event.device_id)
            & (silver["sensor_type"] == sensor_type)
            & (~silver["is_suspect"])  # don't let a flagged reading corrupt the comparison
        ]

        before = device_data[
            device_data["timestamp"].between(
                event.event_timestamp - pd.Timedelta(before_window), event.event_timestamp
            )
        ]["value"].mean()

        after = device_data[
            device_data["timestamp"].between(
                event.event_timestamp, event.event_timestamp + pd.Timedelta(after_window)
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
