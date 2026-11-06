# Architecture

The pipeline reads two CSV files, checks and cleans the readings, writes three
layers of Parquet files, and lets DuckDB query the results. All of it runs locally.

```text
data/sample/*.csv
      |
      v
  ingest.py       parse timestamps, quarantine rows that can't be parsed
      |
      v
  validate.py     add flags: duplicates, units, ranges, blanks, flatlines, drift
      |
      v
  transform.py    build bronze, silver and gold tables
      |
      v
  storage.py      write the tables to output/ as Parquet
      |
      v
  analytics.py    DuckDB views over the Parquet files, runs sql/analytics_queries.sql
```

`main.py` runs the first four steps and prints a report. `scripts/run_local_pipeline.py`
starts it, and `scripts/run_analytics.py` runs the queries.

## Layers

| Layer | What it holds | Written to |
|---|---|---|
| Bronze | The readings with a valid timestamp, as they were read | `output/bronze/sensor_readings.parquet` |
| Quarantine | Rows whose timestamp couldn't be parsed. The file only exists if there are any. | `data/quarantine/quarantined_readings.parquet` |
| Silver | The readings after validation, with exact duplicates removed. Flagged rows stay in. | `output/silver/sensor_readings_silver.parquet` |
| Gold | Summaries built from silver (below) | `output/gold/` |

Gold tables:
- `device_daily_quality.parquet`: readings and suspect readings per device and day.
- `event_response.parquet`: mean value before and after each watering or fertilizing event.
- `missing_intervals.parquet`: gaps in the readings, one row per gap.

Running the pipeline again overwrites these files, so a second run on the same
input gives the same output instead of adding rows.

## Where each kind of problem is handled

| Problem | Step | Result |
|---|---|---|
| Timestamp that can't be parsed | `ingest.py` | Quarantined |
| Timestamp in the alternate format | `ingest.py` | Parsed, counted as corrected |
| Exact duplicate | `validate.py` flags it, `transform.py` removes it | Removed |
| Same key, different value | `validate.py` | Kept, flagged |
| Wrong unit, impossible value, unusual value | `validate.py` | Kept, flagged |
| Blank or non-numeric value | `validate.py` | Kept, flagged |
| Flatline, drift | `validate.py` | Kept, flagged |
| Missing readings | `validate.py` | Separate table, since there's no row to flag |

The rules and thresholds are in [`data_quality_rules.md`](data_quality_rules.md).
Settings such as ranges, the sampling interval and the drift threshold are in
`src/sensor_pipeline/config.py`.

## Reconciliation

The report printed by `main.py` accounts for every record: the number read equals
the number quarantined plus the number parsed, and the silver count is the parsed
count minus the exact duplicates. The report raises an error if the first of
those doesn't add up.

## What isn't here

The AWS version (S3, Glue, Athena) isn't built. Everything above runs on one
machine, with files on disk instead of S3 and DuckDB instead of Athena.
