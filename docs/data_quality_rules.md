# Data quality rules

Every rule either flags a row or puts it in a separate table. Only exact
duplicates are removed, because that row carries no information the first copy
doesn't have. The settings are in `src/sensor_pipeline/config.py` unless noted.

| Rule | Function | Flag or output | What triggers it | What happens to the row |
|---|---|---|---|---|
| Unparseable timestamp | `ingest.py` | `quarantine_reason` | No format in `TIMESTAMP_FORMATS` matches | Quarantined |
| Alternate timestamp format | `ingest.py` | `timestamp_format_corrected` | The second format was needed | Kept, counted as corrected |
| Exact duplicate | `flag_duplicates` | `is_full_duplicate` | Same device, timestamp, sensor type, value and unit as an earlier row | Removed in silver |
| Key conflict | `flag_duplicates` | `is_key_conflict` | Same device, timestamp and sensor type but different values | Kept, flagged |
| Missing value | `cast_numeric` | `flag_missing_value` | Blank or null cell | Kept, flagged |
| Non-numeric value | `cast_numeric` | `flag_non_numeric_value` | Text that isn't a number, like `ERR` | Kept, flagged |
| Unit mismatch | `flag_range_and_unit` | `flag_unit_mismatch` | Unit differs from `SENSOR_RULES` | Kept, flagged |
| Hard bound violation | `flag_range_and_unit` | `flag_hard_bound_violation` | Value outside the limit a real reading can't pass | Kept, flagged |
| Outside usual range | `flag_range_and_unit` | `flag_outside_typical_range` | Value outside the usual range | Kept, flagged |
| Flatline | `flag_flatline` | `flag_flatline` | 20 or more identical readings in a row | Kept, flagged |
| Drift | `flag_drift` | `flag_drift` | Daily median EC at least 150 above the median 3 days earlier (`DRIFT_RULES`) | Kept, flagged |
| Missing interval | `find_missing_intervals` | `missing_intervals` table | A gap longer than the 15-minute interval, rounded | Not a row, so it's a separate table |

`is_suspect` is true for any row with at least one flag, and it's what the quality
summary counts. Rows with a flag are left out of the event-response averages.

## Limits

- **Flatline threshold.** 20 readings is 5 hours at a 15-minute interval. It's a
  rough choice and hasn't been checked against labelled data. It also counts
  readings, not time, so a device that reports every 30 minutes would need 10 hours.
- **Drift.** It only checks EC, and it can't tell a faulty sensor from salt
  building up in the soil. See "Drift" in `data_dictionary.md`.
- **Missing intervals.** Only gaps between two readings are found. A device that
  stops reporting, or starts late, isn't caught.
- **Ranges.** The usual ranges and limits are my own estimates, not official ones.
- **Flags aren't corrections.** The pipeline never changes a value. Someone
  using the silver table needs to decide what to do with flagged rows.
