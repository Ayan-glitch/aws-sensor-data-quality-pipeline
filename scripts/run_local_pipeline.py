"""
CLI entry point for running the full local pipeline.

This is a thin wrapper, not where any logic lives, it exists only so the
README's documented command (`python scripts/run_local_pipeline.py`)
works without requiring the `-m src.sensor_pipeline.main` module syntax,
which is correct but not the friendliest thing to ask a first-time user
to type.

Run from the repo root: python scripts/run_local_pipeline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sensor_pipeline import main

if __name__ == "__main__":
    result = main.run_pipeline(write_output=True)
    main.print_report(result["report"])
