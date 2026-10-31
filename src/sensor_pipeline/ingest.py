"""
Ingestion: reads the raw CSV and parses the timestamps.

Rows whose timestamp can't be parsed go to quarantine. Without a timestamp a
row can't be checked for duplicates or gaps (the timestamp is part of the key),
so there's no point sending it on to validation. All other checks (ranges,
units, duplicates) happen in validate.py.
"""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import config


def _try_parse_timestamp(raw: str):
    """
    Tries each format in config.TIMESTAMP_FORMATS in order.

    Returns (timestamp, used_fallback) on success, where used_fallback is True
    if anything other than the first (documented) format was needed. Returns
    (None, None) if no format matches. Fallback parses are counted as
    corrections in the report.
    """
    for i, fmt in enumerate(config.TIMESTAMP_FORMATS):
        try:
            parsed = pd.Timestamp(datetime.strptime(raw.strip(), fmt))
            return parsed, (i > 0)
        except (ValueError, AttributeError):
            continue
    return None, None


def ingest_readings(source_path: Path) -> dict:
    """
    Reads the sensor readings CSV and returns two DataFrames:
      "parsed":      rows with a valid timestamp
      "quarantined": rows whose timestamp matched no format, with a
                     quarantine_reason column

    Every row also gets source_file and ingested_at columns.
    """
    # Everything is read as text first. Numbers are converted in validate.py,
    # once we know which rows have a usable timestamp.
    raw = pd.read_csv(source_path, dtype=str)

    raw["source_file"] = source_path.name
    raw["ingested_at"] = pd.Timestamp(datetime.now(timezone.utc))

    parse_results = raw["timestamp"].apply(_try_parse_timestamp)
    parsed_ts = parse_results.apply(lambda r: r[0])
    used_fallback = parse_results.apply(lambda r: r[1])
    is_parsed = parsed_ts.notna()

    parsed = raw[is_parsed].copy()
    parsed["timestamp_raw"] = parsed["timestamp"]  # keep the original string
    # Set the dtype explicitly. Left alone, pandas picks a different time
    # resolution depending on the version (datetime64[us] on pandas 3.0).
    parsed["timestamp"] = pd.to_datetime(parsed_ts[is_parsed]).astype("datetime64[ns]")
    parsed["timestamp_format_corrected"] = used_fallback[is_parsed]

    quarantined = raw[~is_parsed].copy()
    quarantined["quarantine_reason"] = "unparseable_timestamp"

    return {"parsed": parsed, "quarantined": quarantined}


def ingest_context_events(source_path: Path) -> pd.DataFrame:
    """
    Reads the context events (watering/fertilizing). These only ever use one
    timestamp format, so there's no fallback parsing here.
    """
    events = pd.read_csv(source_path)
    events["event_timestamp"] = pd.to_datetime(events["event_timestamp"])
    return events
