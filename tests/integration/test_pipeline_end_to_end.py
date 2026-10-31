"""
Integration test: runs the whole pipeline (ingest, validate, transform) on the
generated sample data and checks the counts against the problems listed in
docs/data_dictionary.md.

Needs data/sample/*.csv. If it fails with a FileNotFoundError, run
`python scripts/generate_sample_data.py` first.
"""
from sensor_pipeline import main


def test_full_pipeline_matches_known_injected_issues():
    result = main.run_pipeline(write_output=False)
    report = result["report"]

    # These are the counts for the problems that generate_sample_data.py puts
    # in on purpose (see docs/data_dictionary.md). If one changes, check
    # whether the generator or the validation changed before editing the
    # expected number.
    assert report["original_record_count"] == 42246
    assert report["quarantined_record_count"] == 0
    assert report["corrected_record_count"] == 1344  # DEV-07 fallback timestamp format
    assert report["full_duplicate_count"] == 3        # DEV-05 duplicates
    assert report["key_conflict_count"] == 6           # DEV-05 impossible-value conflicts
    assert report["valid_record_count"] == 42243
    assert report["missing_interval_count"] == 4         # DEV-04 outage, one gap per sensor type
    assert report["missing_reading_count"] == 768         # 4 sensor types x 192 readings (2 days)

    flags = report["flag_breakdown"]
    assert flags["flag_unit_mismatch"] == 1344          # DEV-02
    assert flags["flag_hard_bound_violation"] == 3        # DEV-05
    assert flags["flag_flatline"] == 672                   # DEV-06

    # every record must be either quarantined or parsed
    assert report["original_record_count"] == (
        report["quarantined_record_count"] + report["parsed_record_count"]
    )


def test_pipeline_is_idempotent():
    """Running the pipeline twice on the same input gives the same report."""
    result_1 = main.run_pipeline(write_output=False)
    result_2 = main.run_pipeline(write_output=False)
    assert result_1["report"] == result_2["report"]


def test_reconciliation_report_prints_without_assertion_failure():
    """print_report() checks that the counts add up. Make sure that check passes on the real data."""
    result = main.run_pipeline(write_output=False)
    main.print_report(result["report"])  # raises AssertionError if inconsistent
