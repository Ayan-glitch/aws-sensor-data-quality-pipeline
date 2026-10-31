"""
Shared pytest setup. pytest loads this file before the tests, so src/ and the
fixtures folder are on the import path for every test file.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "fixtures"))
