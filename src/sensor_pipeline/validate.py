"""
Validation: applies the rules from config.py to the parsed readings.

Rows are flagged, not dropped. The only thing removed later (in transform.py)
is an exact duplicate, since that row carries no extra information.
"""
import pandas as pd

from . import config


def cast_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts the value column from text to float. Anything that isn't a number
    becomes NaN. NaN isn't flagged yet (see "Known gaps" in the README).
    """
    df = df.copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def flag_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds two columns:

    is_full_duplicate: the row matches an earlier one on every column in
    config.FULL_ROW_MATCH_COLUMNS. It's the same reading sent twice, so
    transform.py drops it. The first copy is kept.

    is_key_conflict: several rows share device, timestamp and sensor_type but
    have different values. These aren't duplicates, so they're kept and flagged
    for review instead of picking one.
    """
    df = df.copy()
    df["is_full_duplicate"] = df.duplicated(subset=config.FULL_ROW_MATCH_COLUMNS, keep="first")

    key_counts = df.groupby(config.DUPLICATE_KEY)["value"].transform("nunique")
    df["is_key_conflict"] = (key_counts > 1) & (~df["is_full_duplicate"])

    return df


def flag_range_and_unit(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each sensor type, adds three flags:
      flag_unit_mismatch: the unit column differs from the expected unit
        (for example a soil_temp row labelled "F")
      flag_hard_bound_violation: the value is outside the limits a real
        reading can't pass
      flag_outside_typical_range: the value is outside the usual range. This
        is only a flag, since an unusual value can still be real.
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
    Flags runs of identical readings, separately for each device and sensor
    type. A stuck sensor keeps repeating the same value, while a working one
    shows some noise.

    With readings every 15 minutes, 20 in a row is 5 hours. The threshold is
    a rough choice and hasn't been checked against labelled data.
    """
    df = df.sort_values(["device_id", "sensor_type", "timestamp"]).copy()
    group_cols = ["device_id", "sensor_type"]

    is_same_as_prev = df.groupby(group_cols)["value"].diff().eq(0).fillna(False)
    # Every time the value changes, the run id goes up by one, so all the
    # rows in one run share an id (including the first row of the run).
    run_changed = ~is_same_as_prev
    run_id = run_changed.groupby([df["device_id"], df["sensor_type"]]).cumsum()
    run_length = df.groupby(group_cols + [run_id])["value"].transform("size")

    df["flag_flatline"] = run_length >= min_run_length
    return df


def run_validation(df: pd.DataFrame) -> pd.DataFrame:
    """Runs all the validation steps in order and adds is_suspect."""
    df = cast_numeric(df)
    df = flag_duplicates(df)
    df = flag_range_and_unit(df)
    df = flag_flatline(df)

    flag_cols = [c for c in df.columns if c.startswith("flag_") or c.startswith("is_")]
    df["is_suspect"] = df[flag_cols].any(axis=1)

    return df
