"""
Runs the full local pipeline. This is a short wrapper around
src/sensor_pipeline/main.py, so it can be started with a plain script path.

Run from the repo root: python scripts/run_local_pipeline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sensor_pipeline import main

if __name__ == "__main__":
    result = main.run_pipeline(write_output=True)
    main.print_report(result["report"])
