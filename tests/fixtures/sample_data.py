"""
Small, hand-built test data. Deliberately NOT the full 42k-row generated
dataset, unit tests should run in milliseconds against a handful of rows
built specifically to exercise one rule at a time, not by re-processing
the entire fleet on every test.

Plain functions, not pytest fixtures, on purpose: this lets every test
function call these directly and be understood by reading top to bottom,
and lets this exact file be verified independently of whether pytest is
installed in whatever environment is reading it.
"""
import pandas as pd


def make_raw_readings_df(rows: list[dict]) -> pd.DataFrame:
    """
    Builds a DataFrame matching exactly what pd.read_csv would produce
    from sensor_readings.csv, string dtype throughout, since that's what
    ingest.ingest_readings expects as input (it does its own casting).
    """
    df = pd.DataFrame(rows)
    return df.astype(str)


def valid_rows() -> list[dict]:
    return [
        {"device_id": "TEST-01", "timestamp": "2026-01-01 00:00:00", "sensor_type": "soil_moisture", "value": "35.2", "unit": "%"},
        {"device_id": "TEST-01", "timestamp": "2026-01-01 00:15:00", "sensor_type": "soil_moisture", "value": "34.8", "unit": "%"},
        {"device_id": "TEST-01", "timestamp": "2026-01-01 00:30:00", "sensor_type": "soil_moisture", "value": "35.5", "unit": "%"},
    ]


def malformed_timestamp_rows() -> list[dict]:
    return [
        {"device_id": "TEST-02", "timestamp": "NOT_A_DATE", "sensor_type": "soil_moisture", "value": "30.0", "unit": "%"},
        {"device_id": "TEST-02", "timestamp": "2026-01-01 00:00:00", "sensor_type": "soil_moisture", "value": "31.0", "unit": "%"},
    ]


def fallback_format_rows() -> list[dict]:
    """A row using the documented ALTERNATE format, should parse via fallback, not fail."""
    return [
        {"device_id": "TEST-03", "timestamp": "01/01/2026 00:00", "sensor_type": "soil_moisture", "value": "33.0", "unit": "%"},
    ]


def exact_duplicate_rows() -> list[dict]:
    row = {"device_id": "TEST-04", "timestamp": "2026-01-01 00:00:00", "sensor_type": "ec", "value": "700.0", "unit": "uS_cm"}
    return [row, dict(row)]  # two identical copies


def key_conflict_rows() -> list[dict]:
    """Same device/timestamp/sensor_type, DIFFERENT values, not a duplicate."""
    return [
        {"device_id": "TEST-05", "timestamp": "2026-01-01 00:00:00", "sensor_type": "soil_moisture", "value": "30.0", "unit": "%"},
        {"device_id": "TEST-05", "timestamp": "2026-01-01 00:00:00", "sensor_type": "soil_moisture", "value": "45.0", "unit": "%"},
    ]


def unit_mismatch_rows() -> list[dict]:
    return [
        {"device_id": "TEST-06", "timestamp": "2026-01-01 00:00:00", "sensor_type": "soil_temp", "value": "20.0", "unit": "F"},  # should be C
    ]


def hard_bound_violation_rows() -> list[dict]:
    return [
        {"device_id": "TEST-07", "timestamp": "2026-01-01 00:00:00", "sensor_type": "soil_moisture", "value": "-10.0", "unit": "%"},
        {"device_id": "TEST-07", "timestamp": "2026-01-01 00:15:00", "sensor_type": "soil_moisture", "value": "150.0", "unit": "%"},
    ]


def flatline_rows(run_length: int = 25) -> list[dict]:
    """run_length identical readings in a row, default above the 20-reading threshold."""
    rows = []
    for i in range(run_length):
        rows.append({
            "device_id": "TEST-08",
            "timestamp": f"2026-01-01 {i * 15 // 60:02d}:{i * 15 % 60:02d}:00",
            "sensor_type": "soil_moisture",
            "value": "28.4",
            "unit": "%",
        })
    return rows


def short_run_rows(run_length: int = 5) -> list[dict]:
    """Same value repeated, but BELOW the flatline threshold, should NOT be flagged."""
    rows = []
    for i in range(run_length):
        rows.append({
            "device_id": "TEST-09",
            "timestamp": f"2026-01-01 {i * 15 // 60:02d}:{i * 15 % 60:02d}:00",
            "sensor_type": "soil_moisture",
            "value": "30.0",
            "unit": "%",
        })
    return rows
