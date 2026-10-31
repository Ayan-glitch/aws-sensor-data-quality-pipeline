"""
Writes the bronze, silver and gold tables to Parquet, in the folders set in
config.py.

Running this file directly (python -m src.sensor_pipeline.storage) writes
every table, reads it back and checks the row counts.
"""
from pathlib import Path

import pandas as pd

from . import config


def _write_parquet(df: pd.DataFrame, directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    out_path = directory / filename
    df.to_parquet(out_path, index=False, engine="pyarrow")
    return out_path


def write_bronze(bronze: dict) -> dict:
    paths = {
        "readings": _write_parquet(bronze["readings"], config.BRONZE_DIR, "sensor_readings.parquet"),
    }
    if len(bronze["quarantined"]) > 0:
        paths["quarantined"] = _write_parquet(
            bronze["quarantined"], config.QUARANTINE_DIR, "quarantined_readings.parquet"
        )
    return paths


def write_silver(silver: pd.DataFrame) -> Path:
    return _write_parquet(silver, config.SILVER_DIR, "sensor_readings_silver.parquet")


def write_gold(gold_quality: pd.DataFrame, gold_events: pd.DataFrame, gaps: pd.DataFrame) -> dict:
    return {
        "quality_summary": _write_parquet(gold_quality, config.GOLD_DIR, "device_daily_quality.parquet"),
        "event_response": _write_parquet(gold_events, config.GOLD_DIR, "event_response.parquet"),
        "missing_intervals": _write_parquet(gaps, config.GOLD_DIR, "missing_intervals.parquet"),
    }


def read_parquet(path: Path) -> pd.DataFrame:
    """Reads a Parquet file back into a DataFrame."""
    return pd.read_parquet(path, engine="pyarrow")


if __name__ == "__main__":
    # Self-check: run the pipeline, write every table, read each one back
    # and compare the row counts.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sensor_pipeline import ingest, validate, transform

    print("Running full pipeline for storage self-check...")
    result = ingest.ingest_readings(config.RAW_DATA_DIR / "sensor_readings.csv")
    validated = validate.run_validation(result["parsed"])
    events = ingest.ingest_context_events(config.RAW_DATA_DIR / "context_events.csv")

    bronze = transform.build_bronze(result["parsed"], result["quarantined"])
    silver = transform.build_silver(validated)
    gold_quality = transform.build_gold_quality_summary(silver)
    gold_events = transform.build_gold_event_response(silver, events)
    gaps = validate.find_missing_intervals(silver)

    bronze_paths = write_bronze(bronze)
    silver_path = write_silver(silver)
    gold_paths = write_gold(gold_quality, gold_events, gaps)

    checks = [
        ("bronze readings", bronze_paths["readings"], len(bronze["readings"])),
        ("silver", silver_path, len(silver)),
        ("gold quality summary", gold_paths["quality_summary"], len(gold_quality)),
        ("gold event response", gold_paths["event_response"], len(gold_events)),
        ("gold missing intervals", gold_paths["missing_intervals"], len(gaps)),
    ]

    all_ok = True
    for name, path, expected_rows in checks:
        read_back = read_parquet(path)
        status = "OK" if len(read_back) == expected_rows else "MISMATCH"
        if status == "MISMATCH":
            all_ok = False
        print(f"  {name}: wrote {expected_rows} rows, read back {len(read_back)} rows -> {status}")

    print()
    print("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED, see above")
