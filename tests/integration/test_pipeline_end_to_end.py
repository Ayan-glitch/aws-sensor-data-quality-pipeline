"""
Integration test: runs the FULL pipeline (ingest -> validate -> transform)
against the actual generated sample dataset, not a small fixture. This is
deliberately the one test that touches the whole fleet, verifying the
known, documented issue counts from docs/data_dictionary.md actually
come out of the real pipeline, not just the isolated unit logic.

Requires data/sample/*.csv to exist, run `python scripts/generate_sample_data.py`
first if this fails with a FileNotFoundError.
"""
from sensor_pipeline import main


def test_full_pipeline_matches_known_injected_issues():
    result = main.run_pipeline(write_output=False)
    report = result["report"]

    # These numbers are the documented, known-correct counts for the
    # issues deliberately injected by generate_sample_data.py, see
    # docs/data_dictionary.md. If any of these change, either the
    # generator or the validation logic has a real bug, or the fixture
    # data itself was regenerated differently, investigate, don't just
    # update the expected number to make the test pass.
    assert report["original_record_count"] == 42246
    assert report["quarantined_record_count"] == 0
    assert report["corrected_record_count"] == 1344  # DEV-07 fallback timestamp format
    assert report["full_duplicate_count"] == 3        # DEV-05 duplicates
    assert report["key_conflict_count"] == 6           # DEV-05 impossible-value conflicts
    assert report["valid_record_count"] == 42243

    flags = report["flag_breakdown"]
    assert flags["flag_unit_mismatch"] == 1344          # DEV-02
    assert flags["flag_hard_bound_violation"] == 3        # DEV-05
    assert flags["flag_flatline"] == 672                   # DEV-06

    # reconciliation identity must hold: nothing silently lost or duplicated
    assert report["original_record_count"] == (
        report["quarantined_record_count"] + report["parsed_record_count"]
    )


def test_pipeline_is_idempotent():
    """Running the pipeline twice on the same input must produce identical
    results, not accumulate duplicates or drift between runs."""
    result_1 = main.run_pipeline(write_output=False)
    result_2 = main.run_pipeline(write_output=False)
    assert result_1["report"] == result_2["report"]


def test_reconciliation_report_prints_without_assertion_failure():
    """main.print_report() has its own internal consistency assertion,
    this confirms it actually passes against real data, not just that
    the report dict looks right in isolation."""
    result = main.run_pipeline(write_output=False)
    main.print_report(result["report"])  # raises AssertionError if inconsistent
