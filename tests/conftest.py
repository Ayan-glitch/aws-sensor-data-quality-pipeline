"""
Shared pytest setup. pytest automatically discovers and runs this file
before collecting any tests under tests/, so putting the sys.path setup
here once means individual test files just do normal imports, instead of
every file repeating the same boilerplate.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "fixtures"))
