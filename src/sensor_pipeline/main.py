"""
Pipeline entry point. Chains ingest -> validate -> transform -> storage,
then prints a reconciliation report: how many records went in, how many
came out, and exactly what happened to the difference. Nothing in this
report should ever be a surprise, every number here is explainable by
pointing at a specific line of code in validate.py or transform.py.

Run with: python -m src.sensor_pipeline.main
"""
from . import config, ingest, validate, transform, storage


def run_pipeline(write_output: bool = True) -> dict:
    # --- Ingest ---
    result = ingest.ingest_readings(config.RAW_DATA_DIR / "sensor_readings.csv")
    parsed, quarantined = result["parsed"], result["quarantined"]
    events = ingest.ingest_context_events(config.RAW_DATA_DIR / "context_events.csv")

    original_count = len(parsed) + len(quarantined)

    # --- Validate ---
    validated = validate.run_validation(parsed)

    # --- Transform (bronze / silver / gold) ---
    bronze = transform.build_bronze(parsed, quarantined)
    silver = transform.build_silver(validated)
    gold_quality = transform.build_gold_quality_summary(silver)
    gold_events = transform.build_gold_event_response(silver, events)

    # --- Storage (optional, so tests can run this without touching disk) ---
    written_paths = {}
    if write_output:
        written_paths["bronze"] = storage.write_bronze(bronze)
        written_paths["silver"] = storage.write_silver(silver)
        written_paths["gold"] = storage.write_gold(gold_quality, gold_events)

    # --- Reconciliation report ---
    # Every count here is defined precisely enough that none of them can
    # double-count the same row under two different labels, see the
    # comments on each line for exactly what it counts and why.
    report = {
        "original_record_count": original_count,
        "quarantined_record_count": len(quarantined),  # unparseable timestamp, never reached validation
        "parsed_record_count": len(parsed),  # original minus quarantined
        "corrected_record_count": int(validated["timestamp_format_corrected"].sum()),  # fallback timestamp format used, a row that needed reinterpretation to be understood at all
        "full_duplicate_count": int(validated["is_full_duplicate"].sum()),  # exact row match, removed between validated and silver
        "key_conflict_count": int(validated["is_key_conflict"].sum()),  # same key, different values, kept and flagged, not removed
        "valid_record_count": len(silver),  # parsed minus full duplicates, everything that reached silver
        "suspect_record_count": int(silver["is_suspect"].sum()),  # subset of valid records carrying at least one quality flag
        "flag_breakdown": {
            col: int(silver[col].sum())
            for col in silver.columns
            if col.startswith("flag_")
        },
    }

    return {
        "report": report,
        "bronze": bronze,
        "silver": silver,
        "gold_quality": gold_quality,
        "gold_events": gold_events,
        "written_paths": written_paths,
    }


def print_report(report: dict) -> None:
    print("=" * 60)
    print("PIPELINE RECONCILIATION REPORT")
    print("=" * 60)
    print(f"  Original records read:        {report['original_record_count']:>7,}")
    print(f"  Quarantined (bad timestamp):  {report['quarantined_record_count']:>7,}")
    print(f"  Parsed successfully:          {report['parsed_record_count']:>7,}")
    print(f"    of which corrected"
          f" (fallback timestamp fmt):  {report['corrected_record_count']:>7,}")
    print(f"  Full duplicates removed:      {report['full_duplicate_count']:>7,}")
    print(f"  Key conflicts (kept, flagged):{report['key_conflict_count']:>7,}")
    print(f"  Valid records (silver layer): {report['valid_record_count']:>7,}")
    print(f"    of which flagged suspect:   {report['suspect_record_count']:>7,}")
    print()
    print("  Flag breakdown (within silver, not mutually exclusive):")
    for flag, count in report["flag_breakdown"].items():
        print(f"    {flag:<35} {count:>7,}")
    print("=" * 60)

    # One sanity-check assertion, not just a printed number: original
    # records must equal quarantined + parsed, exactly, with nothing lost
    # or double-counted in between. If this ever fails, something in the
    # pipeline is silently dropping or duplicating rows.
    expected = report["quarantined_record_count"] + report["parsed_record_count"]
    assert report["original_record_count"] == expected, (
        f"Reconciliation mismatch: {report['original_record_count']} != {expected}"
    )
    print("Reconciliation check: original = quarantined + parsed -> OK")


if __name__ == "__main__":
    result = run_pipeline(write_output=True)
    print_report(result["report"])
