"""
Ingestion layer.

Job: read the raw CSV exactly as it exists on disk, attach ingestion
metadata, and separate rows whose TIMESTAMP cannot be parsed at all from
rows that parse successfully. A timestamp that fails to parse is a
structural failure, not a soft data-quality issue: without a valid
timestamp you can't safely run gap detection, duplicate detection
(timestamp is part of the key), or anything time-based downstream. So
these rows go straight to quarantine here, before validation even starts.

Rows that DO parse continue on; everything else (range checks, unit
checks, duplicate checks) happens in validate.py, not here. Keeping this
split means ingest.py only ever needs to change if the INPUT FORMAT
changes, while validate.py changes if the BUSINESS RULES change. Two
different reasons to change, so two different files.
"""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import config


def _try_parse_timestamp(raw: str):
    """
    Try each configured format in order. Returns (parsed_timestamp, used_fallback)
    on success, or (None, None) if every format fails.

    used_fallback is False only when the FIRST (primary, documented) format
    matched. Any later format matching counts as a deterministic correction,
    not a silent pass-through, because the row's timestamp had to be
    reinterpreted away from the documented contract to be understood at all.
    This is what lets main.py report an honest "corrected record count"
    instead of that correction happening invisibly.
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
    Reads the raw sensor_readings CSV.

    Returns a dict with two DataFrames:
      - "parsed":      rows with a successfully parsed timestamp, ready
                        for validate.py.
      - "quarantined":  rows whose timestamp didn't match any known
                        format, with a reason column explaining why,
                        untouched otherwise, nothing inferred or guessed.

    Also attaches `source_file` and `ingested_at` to every row, per the
    data contract, so downstream consumers always know where a row came
    from and when it entered the pipeline, not just what it contains.
    """
    raw = pd.read_csv(source_path, dtype=str)  # read everything as string first;
    # numeric casting happens in validate.py, AFTER we know which rows are
    # even structurally sound. Casting here would risk silently coercing a
    # malformed value into NaN before we've had a chance to flag it properly.

    raw["source_file"] = source_path.name
    raw["ingested_at"] = pd.Timestamp(datetime.now(timezone.utc))

    parse_results = raw["timestamp"].apply(_try_parse_timestamp)
    parsed_ts = parse_results.apply(lambda r: r[0])
    used_fallback = parse_results.apply(lambda r: r[1])
    is_parsed = parsed_ts.notna()

    parsed = raw[is_parsed].copy()
    parsed["timestamp_raw"] = parsed["timestamp"]  # preserve the original string
    # Explicitly force datetime64[ns]. Left to inference, .apply() producing
    # individual pd.Timestamp objects gets typed inconsistently across
    # pandas versions (observed: datetime64[us] on 3.0, likely plain
    # object dtype on 2.x), and an ambiguous/non-fixed resolution dtype is
    # exactly what triggers "generic unit" datetime64 warnings during later
    # arithmetic. Pin it explicitly here, once, so every downstream
    # consumer gets a column with a known, consistent resolution.
    parsed["timestamp"] = pd.to_datetime(parsed_ts[is_parsed]).astype("datetime64[ns]")
    parsed["timestamp_format_corrected"] = used_fallback[is_parsed]

    quarantined = raw[~is_parsed].copy()
    quarantined["quarantine_reason"] = "unparseable_timestamp"

    return {"parsed": parsed, "quarantined": quarantined}


def ingest_context_events(source_path: Path) -> pd.DataFrame:
    """
    Context events are simpler: the synthetic generator only ever emits
    one timestamp format for these, so there's no fallback-parsing logic
    needed here. Kept as its own function rather than bolted onto
    ingest_readings because the two files have different schemas and
    different roles in the pipeline, conflating them would make both
    harder to reason about.
    """
    events = pd.read_csv(source_path)
    events["event_timestamp"] = pd.to_datetime(events["event_timestamp"])
    return events
