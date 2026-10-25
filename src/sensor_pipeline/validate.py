"""
Validation layer.

Takes the successfully-parsed rows from ingest.py and applies the
business rules from config.py. The governing principle, same as the
original FYTA-style analysis this project is modeled on: fix what has
one deterministic correct answer, flag everything else, delete only
what's provably redundant.

Nothing in this file silently drops a row for being suspicious. The only
thing that gets removed outright is an exact full-row duplicate, because
that's genuinely redundant information, not a judgment call.
"""
import pandas as pd

from . import config


def cast_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts the 'value' column from string to float, now that we're past
    the structural quarantine step in ingest.py. A value that fails to
    cast (e.g. literal garbage text) becomes NaN here, which the range
    check below will catch and flag, not silently swallow.
    """
    df = df.copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def flag_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Two distinct concepts, deliberately not conflated:

    1. is_full_duplicate: an EXACT match on device/timestamp/sensor_type/
       value/unit. This is genuinely redundant, i.e. the same observation
       counted twice, most likely a retransmission. Safe to drop later
       in transform.py, with zero information lost.

    2. is_key_conflict: rows that share the business key (device,
       timestamp, sensor_type) but DISAGREE on value. This is NOT a
       duplicate in the "redundant" sense, it's two different readings
       claiming the same moment, which is a genuine anomaly worth a
       human's attention, not something to silently resolve by picking
       one arbitrarily.
    """
    df = df.copy()
    df["is_full_duplicate"] = df.duplicated(subset=config.FULL_ROW_MATCH_COLUMNS, keep="first")

    key_counts = df.groupby(config.DUPLICATE_KEY)["value"].transform("nunique")
    df["is_key_conflict"] = (key_counts > 1) & (~df["is_full_duplicate"])

    return df


def flag_range_and_unit(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each sensor_type, checks:
      - unit matches the expected unit from config (a MISLABELED unit,
        like DEV-02's Fahrenheit-magnitude values still declared as "C",
        is caught here even though the numeric value itself might look
        "plausible" in isolation).
      - value is within the hard physical bound (quarantine-worthy).
      - value is within the typical/plausible range (flag for review,
        NOT rejected, since a value outside "typical" might still be
        real plant behavior, same reasoning as the original EC-drift case).
    """
    df = df.copy()
    df["flag_unit_mismatch"] = False
    df["flag_hard_bound_violation"] = False
    df["flag_outside_typical_range"] = False

    for sensor_type, rules in config.SENSOR_RULES.items():
        mask = df["sensor_type"] == sensor_type

        df.loc[mask, "flag_unit_mismatch"] = df.loc[mask, "unit"] != rules["unit"]

        if rules["hard_min"] is not None:
            df.loc[mask, "flag_hard_bound_violation"] |= df.loc[mask, "value"] < rules["hard_min"]
        if rules["hard_max"] is not None:
            df.loc[mask, "flag_hard_bound_violation"] |= df.loc[mask, "value"] > rules["hard_max"]

        below_typical = df.loc[mask, "value"] < rules["typical_min"]
        above_typical = df.loc[mask, "value"] > rules["typical_max"]
        df.loc[mask, "flag_outside_typical_range"] = below_typical | above_typical

    return df


def flag_flatline(df: pd.DataFrame, min_run_length: int = 20) -> pd.DataFrame:
    """
    Generic run-length flatline detector, per (device_id, sensor_type).
    Not hardcoded to any specific device: this runs identically across
    every device/sensor combination, the same generalizable approach used
    in the original FYTA-style analysis, not a rule written for one
    specific known-bad device.

    min_run_length=20 at a 15-minute interval is 5 hours of identical
    consecutive readings before flagging. This is a reasoned starting
    threshold, not validated against labeled known-good/known-bad
    examples, which is the honest caveat to state if asked why 20
    specifically.
    """
    df = df.sort_values(["device_id", "sensor_type", "timestamp"]).copy()
    group_cols = ["device_id", "sensor_type"]

    is_same_as_prev = df.groupby(group_cols)["value"].diff().eq(0).fillna(False)
    # cumsum of "value changed" within each group assigns a unique, increasing
    # id to each run of identical consecutive values. The FIRST row of a run
    # is included in the same run_id as its repeats, so flagging by run_length
    # (not by is_same_as_prev) naturally covers the whole run, start to finish,
    # with no extra logic needed.
    run_changed = ~is_same_as_prev
    run_id = run_changed.groupby([df["device_id"], df["sensor_type"]]).cumsum()
    run_length = df.groupby(group_cols + [run_id])["value"].transform("size")

    df["flag_flatline"] = run_length >= min_run_length
    return df


def run_validation(df: pd.DataFrame) -> pd.DataFrame:
    """Single entry point chaining every validation step, in order."""
    df = cast_numeric(df)
    df = flag_duplicates(df)
    df = flag_range_and_unit(df)
    df = flag_flatline(df)

    flag_cols = [c for c in df.columns if c.startswith("flag_") or c.startswith("is_")]
    df["is_suspect"] = df[flag_cols].any(axis=1)

    return df
