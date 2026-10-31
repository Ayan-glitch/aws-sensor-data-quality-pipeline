# aws-sensor-data-quality-pipeline

A pipeline for ingesting, validating and cleaning IoT sensor time-series data,
written in Python. It runs fully on a laptop. There is also a planned AWS version
(S3, Glue and Athena), which hasn't been built yet.

## Status

Phases 0 to 3 are done. The pipeline runs end to end and has 24 passing tests.
The README is updated as each phase is finished.

| Phase | What it covers | Status |
|---|---|---|
| 0 | Planning and setup | Done |
| 1 | Data contract and synthetic dataset | Done |
| 2 | Ingestion, validation and transformation | Done |
| 3 | Automated tests and CI | Done for the rules that exist (see Known gaps) |
| 4 | Local analytics with DuckDB | Not started |
| 5 | Documentation and reproducibility check | Not started |
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

```bash
# 1. Clone and set up
git clone https://github.com/Ayan-glitch/aws-sensor-data-quality-pipeline.git
cd aws-sensor-data-quality-pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Generate the sample data (same output every time)
python scripts/generate_sample_data.py

# 3. Run the pipeline: ingest, validate, transform, write bronze/silver/gold
python scripts/run_local_pipeline.py

# 4. Run the tests (24 tests: unit and end-to-end)
pytest -v
```

Step 3 prints a report with the number of records read, quarantined, corrected,
removed as duplicates and kept, and the number of missing intervals found. It
also writes Parquet files to `output/bronze/`, `output/silver/` and
`output/gold/`. The tests have been run on Windows and on
GitHub Actions (Linux). The workflow is in `.github/workflows/tests.yml` and
runs on every push.

## Known gaps

- **Missing intervals only cover gaps between readings.** A device that stops
  reporting for good, or starts late, isn't caught.
- **The EC drift on `DEV-03` isn't flagged.** It stays inside the configured
  normal range, so no rule picks it up.
- **Null readings aren't flagged.** A value that isn't a number becomes NaN and
  passes every range check.

## Repository structure

```text
data/sample/          synthetic input data (committed)
data/local/           working output (git-ignored)
data/quarantine/      rejected records (git-ignored)
docs/                 data dictionary
scripts/              generate_sample_data.py, run_local_pipeline.py
src/sensor_pipeline/  pipeline code
tests/                unit and integration tests
.github/workflows/    CI: installs dependencies, generates data, runs pytest
```

Planned for later phases: `sql/` for the DuckDB queries and `aws/` for the AWS
version.

## Documentation

- [`docs/data_dictionary.md`](docs/data_dictionary.md) covers the columns, the
  duplicate rule, the validation ranges and the problems added to the sample
  data.
- Documents for the architecture, costs and cleanup will be added in the phases
  they belong to.

## AWS costs

No cloud resources are created by default. Before anything is deployed, the
expected cost will be written down along with how to clean it up. Those details
will go in `docs/cost_estimate.md` in Phase 6.

## License

Not chosen yet.
