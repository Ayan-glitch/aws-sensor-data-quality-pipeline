"""
Runs the analytics queries with DuckDB on Parquet files written from a real
pipeline run, and checks the numbers against the problems listed in
docs/data_dictionary.md. Needs duckdb and pyarrow (both are in requirements.txt).
"""
import tempfile
from pathlib import Path

from sensor_pipeline import analytics, main

_cache = {}


def _results():
    """Runs the pipeline and the queries once and reuses the answer."""
    if "results" not in _cache:
        run = main.run_pipeline(write_output=False)
        tables = {
            "silver": run["silver"],
            "device_daily_quality": run["gold_quality"],
            "event_response": run["gold_events"],
            "missing_intervals": run["gaps"],
        }
        base = Path(tempfile.mkdtemp())
        for table, df in tables.items():
            folder, filename = analytics.TABLE_FILES[table]
            (base / folder).mkdir(parents=True, exist_ok=True)
            df.to_parquet(base / folder / filename, index=False)

        con = analytics.connect(base)
        _cache["results"] = {
            name: item["result"] for name, item in analytics.run_all(con).items()
        }
    return _cache["results"]


def _rows(df):
    return [tuple(row) for row in df.itertuples(index=False, name=None)]


def test_every_query_runs_and_returns_a_table():
    results = _results()
    assert list(results) == [q["name"] for q in analytics.load_queries()]
    for name, df in results.items():
        assert len(df) > 0, name


def test_only_dev_04_has_missing_readings():
    # one gap per sensor type, 192 readings each
    assert _rows(_results()["missing_by_device"]) == [("DEV-04", 4, 768)]


def test_device_overview_ranks_devices_by_suspect_rate():
    overview = _results()["device_overview"].set_index("device_id")
    assert len(overview) == 8
    assert overview.index[0] == "DEV-02"  # every soil_temp row has the wrong unit
    assert overview.loc["DEV-02", "suspect_readings"] == 1344
    assert round(float(overview.loc["DEV-02", "suspect_rate"]), 3) == 0.25
    assert overview.loc["DEV-04", "missing_readings"] == 768
    assert overview.loc[overview.index != "DEV-04", "missing_readings"].sum() == 0


def test_worst_day_per_device_has_one_row_per_device():
    worst = _results()["worst_day_per_device"].set_index("device_id")
    assert len(worst) == 8
    assert worst["worst_day_rate"].is_monotonic_decreasing
    # every device with a problem shows up, not only the first one alphabetically
    assert {"DEV-02", "DEV-03", "DEV-06"} <= set(worst.index[:3])
    assert worst.loc["DEV-02", "days_with_suspect"] == 14
    assert worst.loc["DEV-03", "days_with_suspect"] == 6   # Jan 9 to Jan 14
    assert worst.loc["DEV-06", "days_with_suspect"] == 7   # second half of the window
    assert worst.loc["DEV-04", "days_with_suspect"] == 0


def test_flatline_and_drift_are_found_on_the_right_sensors():
    flags = _results()["flags_by_device_sensor"]
    assert _rows(flags) == [("DEV-03", "ec", 0, 576), ("DEV-06", "soil_moisture", 672, 0)]


def test_rule_counts_match_the_known_problems():
    counts = dict(_rows(_results()["rule_counts"]))
    assert counts == {
        "unit_mismatch": 1344,
        "flatline": 672,
        "drift": 576,
        "key_conflict": 6,
        "hard_bound_violation": 3,
        "missing_value": 3,
        "outside_typical_range": 3,
        "non_numeric_value": 2,
    }


def test_event_response_overall():
    overall = _results()["event_response_overall"].set_index("event_type")
    assert overall.loc["watering", "events_with_data"] == 18
    assert round(float(overall.loc["watering", "share_rising"]), 3) == 0.611
    assert overall.loc["fertilizing", "events_with_data"] == 12
    assert round(float(overall.loc["fertilizing", "share_rising"]), 3) == 1.0


def test_event_response_by_device_adds_up_to_the_overall_total():
    results = _results()
    by_device = results["event_response_by_device"]
    overall = results["event_response_overall"]
    assert by_device["events_with_data"].sum() == overall["events_with_data"].sum()
