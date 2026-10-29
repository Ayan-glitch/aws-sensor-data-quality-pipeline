from sensor_pipeline import validate
from sample_data import (
    make_raw_readings_df, exact_duplicate_rows, key_conflict_rows,
    unit_mismatch_rows, hard_bound_violation_rows, flatline_rows, short_run_rows,
)


def _validated_from_rows(rows):
    """Builds a DataFrame shaped like ingest.py's output (post-parsing) and validates it."""
    df = make_raw_readings_df(rows)
    df["timestamp"] = df["timestamp"].apply(lambda s: __import__("pandas").Timestamp(s))
    return validate.run_validation(df)


def test_exact_duplicates_flagged_not_removed():
    # validate.py only FLAGS duplicates, removal happens later in transform.py.
    # Both rows should still be present here, with the SECOND one flagged.
    result = _validated_from_rows(exact_duplicate_rows())
    assert len(result) == 2
    assert result["is_full_duplicate"].sum() == 1  # keep=first, so only the 2nd is flagged
    assert not result["is_key_conflict"].any()  # same value, not a conflict


def test_key_conflict_detected_and_not_confused_with_duplicate():
    result = _validated_from_rows(key_conflict_rows())
    assert len(result) == 2
    assert result["is_key_conflict"].sum() == 2  # BOTH rows flagged, different values
    assert result["is_full_duplicate"].sum() == 0  # NOT a duplicate, values differ


def test_unit_mismatch_detected():
    result = _validated_from_rows(unit_mismatch_rows())
    assert result["flag_unit_mismatch"].iloc[0] == True  # noqa: E712


def test_matching_unit_not_flagged():
    rows = [{"device_id": "TEST-OK", "timestamp": "2026-01-01 00:00:00",
              "sensor_type": "soil_temp", "value": "20.0", "unit": "C"}]
    result = _validated_from_rows(rows)
    assert result["flag_unit_mismatch"].iloc[0] == False  # noqa: E712


def test_hard_bound_violation_detected():
    result = _validated_from_rows(hard_bound_violation_rows())
    assert result["flag_hard_bound_violation"].sum() == 2  # both -10 and 150 are out of [0,100]


def test_value_within_bounds_not_flagged():
    rows = [{"device_id": "TEST-OK", "timestamp": "2026-01-01 00:00:00",
              "sensor_type": "soil_moisture", "value": "35.0", "unit": "%"}]
    result = _validated_from_rows(rows)
    assert result["flag_hard_bound_violation"].iloc[0] == False  # noqa: E712


def test_flatline_detected_above_threshold():
    result = _validated_from_rows(flatline_rows(run_length=25))
    assert result["flag_flatline"].sum() == 25  # the WHOLE run, including the first row
    # first row of the run must be flagged too, not just the repeats after it
    assert result.sort_values("timestamp")["flag_flatline"].iloc[0] == True  # noqa: E712


def test_short_run_below_threshold_not_flagged():
    result = _validated_from_rows(short_run_rows(run_length=5))
    assert result["flag_flatline"].sum() == 0


def test_is_suspect_is_true_when_any_flag_fires():
    result = _validated_from_rows(hard_bound_violation_rows())
    assert result["is_suspect"].all()


def test_is_suspect_is_false_for_clean_data():
    rows = [{"device_id": "TEST-OK", "timestamp": "2026-01-01 00:00:00",
              "sensor_type": "soil_moisture", "value": "35.0", "unit": "%"}]
    result = _validated_from_rows(rows)
    assert result["is_suspect"].iloc[0] == False  # noqa: E712
