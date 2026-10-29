import pandas as pd
from sensor_pipeline import ingest
from sample_data import (
    make_raw_readings_df, valid_rows, malformed_timestamp_rows,
    fallback_format_rows,
)


def _ingest_from_rows(rows, tmp_path):
    df = make_raw_readings_df(rows)
    csv_path = tmp_path / "test_readings.csv"
    df.to_csv(csv_path, index=False)
    return ingest.ingest_readings(csv_path)


def test_valid_rows_all_parse(tmp_path):
    result = _ingest_from_rows(valid_rows(), tmp_path)
    assert len(result["parsed"]) == 3
    assert len(result["quarantined"]) == 0


def test_malformed_timestamp_is_quarantined_not_dropped(tmp_path):
    result = _ingest_from_rows(malformed_timestamp_rows(), tmp_path)
    # exactly 1 bad row, 1 good row, NEITHER silently disappears
    assert len(result["quarantined"]) == 1
    assert len(result["parsed"]) == 1
    assert result["quarantined"].iloc[0]["quarantine_reason"] == "unparseable_timestamp"


def test_fallback_format_parses_and_is_marked_corrected(tmp_path):
    result = _ingest_from_rows(fallback_format_rows(), tmp_path)
    assert len(result["parsed"]) == 1
    assert len(result["quarantined"]) == 0
    assert result["parsed"].iloc[0]["timestamp_format_corrected"] == True  # noqa: E712


def test_primary_format_is_not_marked_corrected(tmp_path):
    result = _ingest_from_rows(valid_rows(), tmp_path)
    # the documented, primary format should NOT count as a correction
    assert (result["parsed"]["timestamp_format_corrected"] == False).all()  # noqa: E712


def test_raw_timestamp_string_is_preserved(tmp_path):
    result = _ingest_from_rows(fallback_format_rows(), tmp_path)
    row = result["parsed"].iloc[0]
    assert row["timestamp_raw"] == "01/01/2026 00:00"
    assert isinstance(row["timestamp"], pd.Timestamp)


def test_ingestion_metadata_columns_present(tmp_path):
    result = _ingest_from_rows(valid_rows(), tmp_path)
    assert "source_file" in result["parsed"].columns
    assert "ingested_at" in result["parsed"].columns
    assert result["parsed"]["source_file"].iloc[0] == "test_readings.csv"
