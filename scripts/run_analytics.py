"""
Runs the analytics queries on the pipeline output and prints the results.
Run the pipeline first (python scripts/run_local_pipeline.py).

Run from the repo root: python scripts/run_analytics.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sensor_pipeline import analytics

if __name__ == "__main__":
    con = analytics.connect()
    for name, item in analytics.run_all(con).items():
        print(f"\n{name}: {item['question']}")
        print(item["result"].to_string(index=False))
