"""
Settings for the pipeline: paths, thresholds and validation rules.

Everything that might need changing lives here, so adding a sensor type or
changing a range doesn't mean editing the validation code.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

RAW_DATA_DIR = REPO_ROOT / "data" / "sample"
LOCAL_OUTPUT_DIR = REPO_ROOT / "data" / "local"
QUARANTINE_DIR = REPO_ROOT / "data" / "quarantine"

BRONZE_DIR = REPO_ROOT / "output" / "bronze"
SILVER_DIR = REPO_ROOT / "output" / "silver"
GOLD_DIR = REPO_ROOT / "output" / "gold"

# Expected time between readings, as set out in docs/data_dictionary.md.
# It's set here instead of being worked out from the data, so the gap check
# has a fixed value to compare against.
EXPECTED_INTERVAL_MINUTES = 15

# Timestamp formats to try, in order. A row that matches none of them can't
# be placed in time at all, so it goes to quarantine instead of being flagged.
TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",  # the documented format
    "%d/%m/%Y %H:%M",     # alternate format that some devices send
]

# Validation rules per sensor type. hard_min/hard_max are limits a real
# reading can't go past. typical_min/typical_max are only used to flag
# values that look unusual, they don't reject anything.
SENSOR_RULES = {
    "soil_moisture": {"unit": "%", "hard_min": 0, "hard_max": 100, "typical_min": 0, "typical_max": 70},
    "soil_temp": {"unit": "C", "hard_min": None, "hard_max": None, "typical_min": 5, "typical_max": 35},
    "ec": {"unit": "uS_cm", "hard_min": 0, "hard_max": None, "typical_min": 200, "typical_max": 3000},
    "humidity": {"unit": "%", "hard_min": 0, "hard_max": 100, "typical_min": 20, "typical_max": 100},
}

# Key that identifies a reading. Two rows with the same key but different
# values are flagged as a conflict. Only rows that match on every column in
# FULL_ROW_MATCH_COLUMNS count as duplicates (see data_dictionary.md).
DUPLICATE_KEY = ["device_id", "timestamp", "sensor_type"]
FULL_ROW_MATCH_COLUMNS = ["device_id", "timestamp", "sensor_type", "value", "unit"]
