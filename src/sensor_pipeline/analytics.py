"""
Runs the SQL queries in sql/analytics_queries.sql against the pipeline output
using DuckDB. The Parquet files written by the pipeline are exposed as tables.
"""
from pathlib import Path

import pandas as pd

from . import config

# Table name -> (folder inside the output directory, file name).
TABLE_FILES = {
    "silver": ("silver", "sensor_readings_silver.parquet"),
    "device_daily_quality": ("gold", "device_daily_quality.parquet"),
    "event_response": ("gold", "event_response.parquet"),
    "missing_intervals": ("gold", "missing_intervals.parquet"),
}


def load_queries(sql_path: Path = config.ANALYTICS_QUERIES) -> list[dict]:
    """
    Reads the SQL file and returns one dict per query, in file order, with the
    keys name, question and sql. A query starts at a "-- name:" line.
    """
    queries = []
    current = None
    for line in sql_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- name:"):
            current = {"name": line[len("-- name:"):].strip(), "question": "", "lines": []}
            queries.append(current)
        elif current is None:
            continue  # header comments before the first query
        elif line.startswith("-- question:"):
            current["question"] = line[len("-- question:"):].strip()
        elif line.lstrip().startswith("--"):
            continue  # any other comment line
        elif line.strip():
            current["lines"].append(line)

    return [
        {"name": q["name"], "question": q["question"],
         "sql": "\n".join(q["lines"]).strip().rstrip(";")}
        for q in queries
    ]


def connect(output_dir: Path = config.OUTPUT_DIR):
    """
    Opens an in-memory DuckDB connection with one view per pipeline table,
    read from the Parquet files under output_dir. Run the pipeline first.
    """
    paths = {}
    for table, (folder, filename) in TABLE_FILES.items():
        path = output_dir / folder / filename
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Run python scripts/run_local_pipeline.py first."
            )
        paths[table] = path

    import duckdb  # imported here so load_queries works without duckdb installed

    con = duckdb.connect()
    for table, path in paths.items():
        quoted = path.as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{quoted}')")
    return con


def run_all(con) -> dict:
    """Runs every query and returns {name: {"question": ..., "result": DataFrame}}."""
    results = {}
    for query in load_queries():
        results[query["name"]] = {
            "question": query["question"],
            "result": con.execute(query["sql"]).df(),
        }
    return results
