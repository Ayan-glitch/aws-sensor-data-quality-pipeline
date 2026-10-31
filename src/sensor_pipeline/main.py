"""
Runs the whole pipeline (ingest, validate, transform, store) and prints a
report showing how many records went in and what happened to each one.

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
    gaps = validate.find_missing_intervals(silver)

    # --- Storage (can be switched off so tests don't write to disk) ---
    written_paths = {}
    if write_output:
        written_paths["bronze"] = storage.write_bronze(bronze)
        written_paths["silver"] = storage.write_silver(silver)
        written_paths["gold"] = storage.write_gold(gold_quality, gold_events, gaps)

    # --- Report ---
    # The comment on each line says what the number counts.
    report = {
        "original_record_count": original_count,
        "quarantined_record_count": len(quarantined),  # timestamp could not be parsed, so the row never reached validation
        "parsed_record_count": len(parsed),  # original minus quarantined
        "corrected_record_count": int(validated["timestamp_format_corrected"].sum()),  # parsed with the fallback timestamp format
        "full_duplicate_count": int(validated["is_full_duplicate"].sum()),  # exact duplicate, removed when building silver
        "key_conflict_count": int(validated["is_key_conflict"].sum()),  # same key but different values, kept and flagged
        "valid_record_count": len(silver),  # parsed minus full duplicates, i.e. the silver table
        "suspect_record_count": int(silver["is_suspect"].sum()),  # valid records with at least one flag
        "missing_interval_count": len(gaps),  # stretches of missing readings, per device and sensor type
        "missing_reading_count": int(gaps["missing_readings"].sum()),  # readings that should exist but don't
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
        "gaps": gaps,
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
    print(f"  Missing intervals found:      {report['missing_interval_count']:>7,}")
    print(f"    readings missing in them:   {report['missing_reading_count']:>7,}")
    print()
    print("  Flag breakdown (within silver, not mutually exclusive):")
    for flag, count in report["flag_breakdown"].items():
        print(f"    {flag:<35} {count:>7,}")
    print("=" * 60)

    # Every record read must end up either quarantined or parsed. If these
    # don't add up, rows are being lost or counted twice somewhere.
    expected = report["quarantined_record_count"] + report["parsed_record_count"]
    assert report["original_record_count"] == expected, (
        f"Reconciliation mismatch: {report['original_record_count']} != {expected}"
    )
    print("Reconciliation check: original = quarantined + parsed -> OK")


if __name__ == "__main__":
    result = run_pipeline(write_output=True)
    print_report(result["report"])
