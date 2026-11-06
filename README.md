# aws-sensor-data-quality-pipeline

![Tests](https://github.com/Ayan-glitch/aws-sensor-data-quality-pipeline/actions/workflows/tests.yml/badge.svg)

A pipeline for ingesting, validating and cleaning IoT sensor time-series data,
written in Python. It runs fully on a laptop. There is also a planned AWS version
(S3, Glue and Athena), which hasn't been built yet.

## Status

Phases 0 to 5 are done. The pipeline runs end to end, has unit and integration
tests, and the results can be queried with SQL. The README is updated as each
phase is finished.

| Phase | What it covers | Status |
|---|---|---|
| 0 | Planning and setup | Done |
| 1 | Data contract and synthetic dataset | Done |
| 2 | Ingestion, validation and transformation | Done |
| 3 | Automated tests and CI | Done (see Known gaps for the limits) |
| 4 | Local analytics with DuckDB | Done |
| 5 | Documentation and reproducibility check | Done |
| 6 | AWS design and cost review | Not started |
| 7 | AWS deployment (optional) | Not started |

## About the data

The dataset is synthetic. It's made by `scripts/generate_sample_data.py` with a
fixed random seed, so every run gives the same files. It isn't taken from any
company or real device.

The generator adds problems that are common in sensor data: duplicate rows, a
wrong unit label, a different timestamp format, a stuck sensor, a gap in the
readings and a slow drift. Because they're added on purpose, the pipeline can be
checked against a known list of issues (see `docs/data_dictionary.md`).

## Goals

- Find data quality problems in sensor data without deleting rows that might be
  valid. Rows are flagged, and only exact duplicates are removed.
- Keep the core pipeline local, so it needs no AWS account and costs nothing.
- Treat AWS as an optional extra. Nothing has been created on AWS, and anything
  that could cost money will be estimated first.

## Quick start

Needs Python 3.11 or newer. It has been run on Python 3.13.

```bash
# 1. Clone and set up
git clone https://github.com/Ayan-glitch/aws-sensor-data-quality-pipeline.git
cd aws-sensor-data-quality-pipeline
python -m venv .venv
source .venv/bin/activate     # on Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Generate the sample data (same output every time; the repo already includes it)
python scripts/generate_sample_data.py

# 3. Run the pipeline: ingest, validate, transform, write bronze/silver/gold
python scripts/run_local_pipeline.py

# 4. Run the tests (unit and end-to-end)
pytest -v

# 5. Run the SQL queries on the pipeline output (needs step 3 first)
python scripts/run_analytics.py
```

Step 3 prints a report with the number of records read, quarantined, corrected,
removed as duplicates and kept, and the number of missing intervals found. It
also writes Parquet files to `output/bronze/`, `output/silver/` and
`output/gold/`. The tests have been run on Windows and on
GitHub Actions (Linux). The workflow is in `.github/workflows/tests.yml` and
runs on every push.

## Analytics

`scripts/run_analytics.py` runs the queries in `sql/analytics_queries.sql` with
DuckDB, reading the Parquet files the pipeline wrote to `output/`. Run the pipeline
first.

| Query | Question |
|---|---|
| `missing_by_device` | Which devices have the most missing readings? |
| `device_overview` | How do the devices compare on suspect and missing readings? |
| `worst_device_days` | Which device-days have the highest share of suspect readings? |
| `flags_by_device_sensor` | Which sensors show repeated or drifting readings? |
| `rule_counts` | How many readings does each validation rule flag? |
| `event_response_overall` | Do moisture and EC change after watering and fertilizing events? |
| `event_response_by_device` | How does the response to events differ between devices? |

The event response is a plain before/after average. On this data it shows EC
rising after fertilizing every time, and soil moisture rising after about 61% of
waterings. The moisture effect is small compared to the noise, so the result is
weak (see "Event response" in `docs/data_dictionary.md`).

## Known gaps

- **Missing intervals only cover gaps between readings.** A device that stops
  reporting for good, or starts late, isn't caught.
- **The drift flag only means "EC rose and stayed up".** It can't tell a faulty
  sensor from real salt build-up, so flagged rows are for review. It only checks
  EC, and it starts a day or two after the climb begins.

## Repository structure

```text
data/sample/          synthetic input data (committed)
data/local/           working output (git-ignored)
data/quarantine/      rejected records (git-ignored)
docs/                 documentation
scripts/              generate_sample_data.py, run_local_pipeline.py, run_analytics.py
sql/                  analytics queries
src/sensor_pipeline/  pipeline code
tests/                unit and integration tests
.github/workflows/    CI: installs dependencies, generates data, runs pytest
```

Planned for later phases: `aws/` for the AWS version.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) shows how the data flows and
  what each layer holds.
- [`docs/data_quality_rules.md`](docs/data_quality_rules.md) lists every rule,
  its threshold and its limits.
- [`docs/data_dictionary.md`](docs/data_dictionary.md) covers the columns, the
  duplicate rule, the validation ranges and the problems added to the sample
  data.
- [`docs/design_decisions.md`](docs/design_decisions.md) explains why things are
  done the way they are.
- Documents for costs and cleanup will be added with the AWS phase.

## AWS costs

No cloud resources are created by default. Before anything is deployed, the
expected cost will be written down along with how to clean it up. Those details
will go in `docs/cost_estimate.md` in Phase 6.

## License

Not chosen yet.
