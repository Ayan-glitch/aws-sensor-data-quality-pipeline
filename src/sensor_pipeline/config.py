"""
Central configuration for the pipeline.

Every threshold, range, and path lives here, not scattered through the
ingestion/validation code. This mirrors the "config, not code" principle:
if a new device needs a different expected sampling interval, or a new
sensor type needs a different valid range, this is the one file to touch,
not a search through business logic.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

RAW_DATA_DIR = REPO_ROOT / "data" / "sample"
LOCAL_OUTPUT_DIR = REPO_ROOT / "data" / "local"
QUARANTINE_DIR = REPO_ROOT / "data" / "quarantine"

BRONZE_DIR = REPO_ROOT / "output" / "bronze"
SILVER_DIR = REPO_ROOT / "output" / "silver"
GOLD_DIR = REPO_ROOT / "output" / "gold"

# Expected sampling interval, per the data contract in docs/data_dictionary.md.
# Declared explicitly rather than inferred from the data itself, so gap
# detection is auditable: anyone reading this file knows exactly what
# assumption the gap detector is using.
EXPECTED_INTERVAL_MINUTES = 15

# Accepted timestamp formats, tried in order. A row that matches none of
# these is a structural failure, not a soft validation issue, and is
# quarantined rather than passed through with a flag.
TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",  # the documented/expected format
    "%d/%m/%Y %H:%M",     # a known alternate format some devices emit
]

# Per-sensor-type validation rules. "hard_min"/"hard_max" are physically
# impossible bounds (quarantine-worthy, not debatable). "typical_min"/
# "typical_max" are plausibility bounds for flagging, not rejecting.
SENSOR_RULES = {
    "soil_moisture": {"unit": "%", "hard_min": 0, "hard_max": 100, "typical_min": 0, "typical_max": 70},
    "soil_temp": {"unit": "C", "hard_min": None, "hard_max": None, "typical_min": 5, "typical_max": 35},
    "ec": {"unit": "uS_cm", "hard_min": 0, "hard_max": None, "typical_min": 200, "typical_max": 3000},
    "humidity": {"unit": "%", "hard_min": 0, "hard_max": 100, "typical_min": 20, "typical_max": 100},
}

# The business key used to define a "duplicate" reading. See data_dictionary.md
# for the reasoning: two rows sharing this key but with DIFFERENT values are
# NOT silently deduplicated, only exact full-row matches are.
DUPLICATE_KEY = ["device_id", "timestamp", "sensor_type"]
FULL_ROW_MATCH_COLUMNS = ["device_id", "timestamp", "sensor_type", "value", "unit"]
