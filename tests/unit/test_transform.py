import pandas as pd
from sensor_pipeline import validate, transform
from sample_data import make_raw_readings_df, exact_duplicate_rows, hard_bound_violation_rows


def _validated_from_rows(rows):
    df = make_raw_readings_df(rows)
    df["timestamp"] = df["timestamp"].apply(lambda s: pd.Timestamp(s))
    return validate.run_validation(df)


def test_silver_removes_only_full_duplicates():
    validated = _validated_from_rows(exact_duplicate_rows())
    assert len(validated) == 2  # both still present pre-silver
    silver = transform.build_silver(validated)
    assert len(silver) == 1  # exactly one copy removed
    assert "is_full_duplicate" not in silver.columns  # no longer meaningful post-dedup


def test_silver_keeps_suspect_rows_with_flags_intact():
    # a flagged-but-not-duplicate row must survive into silver, flags and all
    validated = _validated_from_rows(hard_bound_violation_rows())
    silver = transform.build_silver(validated)
    assert len(silver) == 2  # nothing dropped, these aren't duplicates
    assert silver["is_suspect"].all()  # flags preserved, not cleared


def test_gold_quality_summary_counts_are_consistent():
    validated = _validated_from_rows(hard_bound_violation_rows())
    silver = transform.build_silver(validated)
    summary = transform.build_gold_quality_summary(silver)
    assert summary["total_readings"].sum() == len(silver)
    assert summary["suspect_readings"].sum() == silver["is_suspect"].sum()


def test_gold_event_response_computes_expected_delta():
    # hand-built: a device with a clean step up in moisture right at an event
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

    result = transform.build_gold_event_response(silver, events, before_window="1h30min", after_window="1h30min")
    assert len(result) == 1
    row = result.iloc[0]
    assert row["mean_before"] == 20.0  # the two 20.0 readings before the event
    assert row["mean_after"] == 30.0   # the two 30.0 readings after
    assert row["delta"] == 10.0


def test_gold_event_response_excludes_suspect_readings():
    # same shape as above, but the "after" readings are hard-bound violations,
    # they must NOT be averaged into the result
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

    result = transform.build_gold_event_response(silver, events, before_window="1h", after_window="1h")
    assert pd.isna(result.iloc[0]["mean_after"])  # suspect reading correctly excluded, not averaged in
