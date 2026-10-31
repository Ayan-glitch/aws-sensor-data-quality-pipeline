import pandas as pd
from sensor_pipeline import validate
from sample_data import (
    make_raw_readings_df, exact_duplicate_rows, key_conflict_rows,
    unit_mismatch_rows, hard_bound_violation_rows, flatline_rows, short_run_rows,
)


def _validated_from_rows(rows):
    """Builds a DataFrame like the output of ingest.py and runs validation on it."""
    df = make_raw_readings_df(rows)
    df["timestamp"] = df["timestamp"].apply(lambda s: __import__("pandas").Timestamp(s))
    return validate.run_validation(df)


def test_exact_duplicates_flagged_not_removed():
    # validate.py only flags duplicates, transform.py removes them.
    # Both rows are still here, and the second one is flagged.
    result = _validated_from_rows(exact_duplicate_rows())
    assert len(result) == 2
    assert result["is_full_duplicate"].sum() == 1  # keep="first", so only the second is flagged
    assert not result["is_key_conflict"].any()  # same value, so no conflict


def test_key_conflict_detected_and_not_confused_with_duplicate():
    result = _validated_from_rows(key_conflict_rows())
    assert len(result) == 2
    assert result["is_key_conflict"].sum() == 2  # both rows flagged, the values differ
    assert result["is_full_duplicate"].sum() == 0  # not a duplicate, the values differ


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
    assert result["flag_hard_bound_violation"].sum() == 2  # -10 and 150 are both outside 0 to 100


def test_value_within_bounds_not_flagged():
    rows = [{"device_id": "TEST-OK", "timestamp": "2026-01-01 00:00:00",
              "sensor_type": "soil_moisture", "value": "35.0", "unit": "%"}]
    result = _validated_from_rows(rows)
    assert result["flag_hard_bound_violation"].iloc[0] == False  # noqa: E712


def test_flatline_detected_above_threshold():
    result = _validated_from_rows(flatline_rows(run_length=25))
    assert result["flag_flatline"].sum() == 25  # the whole run, first row included
    # the first row of the run is flagged too, not only the repeats
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


def _readings_at(times, device="TEST-G", sensor_type="soil_moisture"):
    """Builds a small DataFrame with one row per timestamp, for the gap tests."""
    return pd.DataFrame({
        "device_id": device,
        "sensor_type": sensor_type,
        "timestamp": pd.to_datetime(times),
    })


def test_no_gap_when_readings_are_on_schedule():
    df = _readings_at(["2026-01-01 00:00", "2026-01-01 00:15", "2026-01-01 00:30"])
    assert len(validate.find_missing_intervals(df)) == 0


def test_gap_is_found_and_counted():
    # 00:15 to 01:00 is 45 minutes, so the readings at 00:30 and 00:45 are missing
    df = _readings_at(["2026-01-01 00:00", "2026-01-01 00:15", "2026-01-01 01:00"])
    gaps = validate.find_missing_intervals(df)
    assert len(gaps) == 1
    row = gaps.iloc[0]
    assert row["missing_readings"] == 2
    assert row["last_seen_before"] == pd.Timestamp("2026-01-01 00:15")
    assert row["first_seen_after"] == pd.Timestamp("2026-01-01 01:00")


def test_a_slightly_late_reading_is_not_a_gap():
    # 20 minutes between readings rounds to one interval, so nothing is missing
    df = _readings_at(["2026-01-01 00:00", "2026-01-01 00:20"])
    assert len(validate.find_missing_intervals(df)) == 0


def test_repeated_timestamps_do_not_create_a_gap():
    df = _readings_at(["2026-01-01 00:00", "2026-01-01 00:00", "2026-01-01 00:15"])
    assert len(validate.find_missing_intervals(df)) == 0


def test_gaps_are_found_separately_for_each_sensor_type():
    # only soil_temp has a gap, soil_moisture is complete
    complete = _readings_at(["2026-01-01 00:00", "2026-01-01 00:15", "2026-01-01 00:30"], sensor_type="soil_moisture")
    with_gap = _readings_at(["2026-01-01 00:00", "2026-01-01 00:30"], sensor_type="soil_temp")
    gaps = validate.find_missing_intervals(pd.concat([complete, with_gap], ignore_index=True))
    assert len(gaps) == 1
    assert gaps.iloc[0]["sensor_type"] == "soil_temp"
    assert gaps.iloc[0]["missing_readings"] == 1


def test_the_interval_can_be_changed():
    # with a 30 minute interval, readings 30 minutes apart are on schedule
    df = _readings_at(["2026-01-01 00:00", "2026-01-01 00:30", "2026-01-01 01:00"])
    assert len(validate.find_missing_intervals(df, expected_minutes=30)) == 0
