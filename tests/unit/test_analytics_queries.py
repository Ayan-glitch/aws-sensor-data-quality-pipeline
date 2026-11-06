import tempfile
from pathlib import Path

import pytest

from sensor_pipeline import analytics

EXPECTED_QUERIES = [
    "missing_by_device",
    "device_overview",
    "worst_day_per_device",
    "flags_by_device_sensor",
    "rule_counts",
    "event_response_overall",
    "event_response_by_device",
]


def test_all_queries_are_found_in_file_order():
    names = [q["name"] for q in analytics.load_queries()]
    assert names == EXPECTED_QUERIES


def test_every_query_has_a_question_and_sql():
    for query in analytics.load_queries():
        assert query["question"], query["name"]
        assert query["sql"].upper().startswith("SELECT"), query["name"]


def test_comment_lines_are_not_part_of_the_sql():
    for query in analytics.load_queries():
        assert "--" not in query["sql"], query["name"]


def test_the_trailing_semicolon_is_removed():
    for query in analytics.load_queries():
        assert not query["sql"].endswith(";"), query["name"]


def test_header_comments_are_not_part_of_the_first_query():
    first = analytics.load_queries()[0]
    assert "-- " not in first["sql"].splitlines()[0]
    assert first["sql"].startswith("SELECT device_id")


def test_connect_explains_what_to_do_when_the_output_is_missing():
    empty_dir = Path(tempfile.mkdtemp())
    with pytest.raises(FileNotFoundError) as error:
        analytics.connect(empty_dir)
    assert "run_local_pipeline.py" in str(error.value)
