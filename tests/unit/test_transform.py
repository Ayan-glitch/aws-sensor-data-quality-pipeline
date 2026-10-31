from datetime import timedelta

import pandas as pd
from sensor_pipeline import validate, transform
from sample_data import make_raw_readings_df, exact_duplicate_rows, hard_bound_violation_rows


def _validated_from_rows(rows):
    df = make_raw_readings_df(rows)
    df["timestamp"] = df["timestamp"].apply(lambda s: pd.Timestamp(s))
    return validate.run_validation(df)


def test_silver_removes_only_full_duplicates():
    validated = _validated_from_rows(exact_duplicate_rows())
    assert len(validated) == 2  # both rows are still there before silver
    silver = transform.build_silver(validated)
    assert len(silver) == 1  # one copy removed
    assert "is_full_duplicate" not in silver.columns  # dropped after dedup


def test_silver_keeps_suspect_rows_with_flags_intact():
    # a flagged row that isn't a duplicate has to stay in silver, with its flags
    validated = _validated_from_rows(hard_bound_violation_rows())
    silver = transform.build_silver(validated)
    assert len(silver) == 2  # nothing dropped, they aren't duplicates
    assert silver["is_suspect"].all()  # flags are still set


def test_gold_quality_summary_counts_are_consistent():
    validated = _validated_from_rows(hard_bound_violation_rows())
    silver = transform.build_silver(validated)
    summary = transform.build_gold_quality_summary(silver)
    assert summary["total_readings"].sum() == len(silver)
    assert summary["suspect_readings"].sum() == silver["is_suspect"].sum()


def test_gold_event_response_computes_expected_delta():
    # moisture steps up from 20 to 30 around the event
    rows = [
        {"device_id": "TEST-EV", "timestamp": "2026-01-01 08:00:00", "sensor_type": "soil_moisture", "value": "20.0", "unit": "%"},
        {"device_id": "TEST-EV", "timestamp": "2026-01-01 09:00:00", "sensor_type": "soil_moisture", "value": "20.0", "unit": "%"},
        {"device_id": "TEST-EV", "timestamp": "2026-01-01 10:00:00", "sensor_type": "soil_moisture", "value": "30.0", "unit": "%"},
        {"device_id": "TEST-EV", "timestamp": "2026-01-01 11:00:00", "sensor_type": "soil_moisture", "value": "30.0", "unit": "%"},
    ]
    validated = _validated_from_rows(rows)
    silver = transform.build_silver(validated)

    events = pd.DataFrame([{
        "event_id": 0, "device_id": "TEST-EV", "event_type": "watering",
        "event_timestamp": pd.Timestamp("2026-01-01 09:30:00"), "event_text": "test",
    }])

    result = transform.build_gold_event_response(silver, events, before_window=timedelta(minutes=90), after_window=timedelta(minutes=90))
    assert len(result) == 1
    row = result.iloc[0]
    assert row["mean_before"] == 20.0  # the two 20.0 readings before the event
    assert row["mean_after"] == 30.0   # the two 30.0 readings after
    assert row["delta"] == 10.0


def test_gold_event_response_excludes_suspect_readings():
    # like the test above, but the "after" reading is a hard-bound violation,
    # so it must be left out of the average
    rows = [
        {"device_id": "TEST-EV2", "timestamp": "2026-01-01 08:00:00", "sensor_type": "soil_moisture", "value": "20.0", "unit": "%"},
        {"device_id": "TEST-EV2", "timestamp": "2026-01-01 10:00:00", "sensor_type": "soil_moisture", "value": "-5.0", "unit": "%"},
    ]
    validated = _validated_from_rows(rows)
    silver = transform.build_silver(validated)

    events = pd.DataFrame([{
        "event_id": 0, "device_id": "TEST-EV2", "event_type": "watering",
        "event_timestamp": pd.Timestamp("2026-01-01 09:00:00"), "event_text": "test",
    }])

    result = transform.build_gold_event_response(silver, events, before_window=timedelta(hours=1), after_window=timedelta(hours=1))
    assert pd.isna(result.iloc[0]["mean_after"])  # the suspect reading was left out
