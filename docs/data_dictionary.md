# Data dictionary

The data is synthetic. It's created by `scripts/generate_sample_data.py` with a
fixed random seed, so it's the same on every run. The problems in it (duplicates,
a wrong unit, a stuck sensor and so on) are common in sensor data, but the device
IDs, values and timestamps are all made up.

## sensor_readings

| Column | Type | Notes |
|---|---|---|
| `device_id` | text | Looks like `DEV-01`. Part of the reading key. |
| `timestamp` | text, parsed to datetime | Expected format is `YYYY-MM-DD HH:MM:SS`. One device sends a different format, to test the fallback parser. |
| `sensor_type` | text | `soil_moisture`, `soil_temp`, `ec` or `humidity`. |
| `value` | float | The unit depends on `sensor_type`. A blank cell is flagged as missing, and text that isn't a number is flagged as non-numeric. |
| `unit` | text | Checked against the expected unit for the sensor type. A mismatch, such as `F` where `C` is expected, is a unit problem and not an invalid value. |
| `source_file` | text | Added during ingestion. |
| `ingested_at` | datetime | Added during ingestion. |

**Missing and non-numeric values.** Both mean the row has no usable number, and
both leave the value as NaN. They're flagged separately because they point to
different causes: a blank cell suggests the sensor sent nothing, while text like
`ERR` suggests it sent an error code. The row is kept either way, since its other
columns may be fine. A missing value is different from a missing reading (see
Missing intervals below), where the whole row is absent.

**Reading key.** A reading is identified by `device_id`, `timestamp` and
`sensor_type`. A row is only a duplicate if it also has the same value and unit
as an earlier row. Rows with the same key but different values are not
duplicates. They're kept and flagged as a conflict, because dropping one would
throw away a reading that may be real.

**Ranges.** These live in `src/sensor_pipeline/config.py` and are my own
estimates, not official limits.

| `sensor_type` | Unit | Usual range | Limit a real reading can't pass |
|---|---|---|---|
| `soil_moisture` | `%` | 0 to 70 | 0 to 100 |
| `soil_temp` | `C` | 5 to 35 | none set |
| `ec` | `uS_cm` | 200 to 3000 | 0 or more |
| `humidity` | `%` | 20 to 100 | 0 to 100 |

A reading outside the limit is flagged as a hard-bound violation. A reading
outside the usual range but inside the limit is only flagged for review, because
an unusual value can still be real.

**Sampling interval.** Readings are expected every 15 minutes. This is set in
the config instead of being worked out from the data.

**Missing intervals.** A missing reading is a row that doesn't exist, so it can't
be flagged on a row the way the other problems are. `find_missing_intervals` in
`validate.py` returns a separate table with one row per gap, per device and sensor
type:

| Column | Notes |
|---|---|
| `device_id`, `sensor_type` | Which series the gap is in. |
| `last_seen_before` | Last timestamp before the gap. |
| `first_seen_after` | First timestamp after the gap. |
| `missing_readings` | Readings that should have arrived in between. |

The count is the gap length divided by the 15-minute interval, rounded, minus one.
A reading that arrives a few minutes late rounds to nothing missing, so it isn't
reported. Only gaps between two readings are found. A device that stops reporting
for good, or only starts partway through, isn't caught. A missing row is also
different from a null value, which is a row that exists with no number in it.
The table is written to `output/gold/missing_intervals.parquet`.

## context_events

| Column | Type | Notes |
|---|---|---|
| `event_id` | integer | |
| `device_id` | text | Matches `sensor_readings.device_id`. |
| `event_timestamp` | datetime | |
| `event_type` | text | `watering` or `fertilizing`. |
| `event_text` | text | A short note with only a few different wordings. |

## Drift

A drift is a climb that keeps going, unlike the short bump after fertilizing.
`flag_drift` in `validate.py` takes each device's daily median EC and flags a day
if it's at least 150 uS/cm above the median 3 days earlier. The settings are
`DRIFT_RULES` in `config.py`. The median is used so a few hours of high readings
don't count.

How the numbers were picked: in the sample data the largest 3-day rise on a
healthy device is about 52, and the drifting device rises about 600. Any
threshold from 60 to 500 flags the same rows here, so 150 sits in the middle. A
threshold of 40 starts flagging a healthy device.

The flag is for review. A rise like this could be a faulty sensor or real salt
building up, and the data can't say which. `DEV-03` also has a fertilizing event
on Jan 10, inside the drift, so the two can't be told apart even in principle.

Limits:
- Only EC is checked.
- It starts a day or two after the climb does. `DEV-03` starts drifting on Jan 8
  and is flagged from Jan 9.
- A day with no readings, or no comparison day, can't be flagged.
- A lasting one-off jump would be flagged too.
- In the generator the fertilizing bump is gone after 8 hours. In real soil it can
  last longer, so on real data a flagged day might just be fertilizer.

## Problems added to the sample data

| # | Device | Problem | Detected by the pipeline |
|---|---|---|---|
| 1 | `DEV-05` | Exact duplicate rows | Yes |
| 2 | `DEV-02` | `soil_temp` labelled `F` instead of `C` | Yes |
| 3 | `DEV-07` | `soil_moisture` timestamps in a different format | Yes, parsed with the fallback format |
| 4 | `DEV-05` | Impossible moisture values (below 0) | Yes |
| 5 | `DEV-06` | `soil_moisture` stuck on one value | Yes |
| 6 | `DEV-04` | 2-day gap with no rows | Yes, as 4 missing intervals (one per sensor type) of 192 readings each |
| 7 | `DEV-03` | EC drifting upward over several days | Yes, as `flag_drift` on 576 EC rows (Jan 9 to Jan 14) |
| 8 | `DEV-01` | Humidity left blank for 3 readings | Yes, as `flag_missing_value` |
| 9 | `DEV-08` | EC sent as the text `ERR` for 2 readings | Yes, as `flag_non_numeric_value` |

Problem 7 shouldn't be corrected automatically when it is detected. It could be
a real change or a faulty sensor, so it should only be flagged for review.

## Event response

Each `watering` event raises that device's `soil_moisture` a little for about two
hours. Each `fertilizing` event raises `ec` more slowly, over several hours. This
gives `build_gold_event_response` a real effect to find. The code is
`event_response_delta` in `scripts/generate_sample_data.py`.

The effect is small compared to the sensor noise, so a single event can miss it.
In the current sample data, about 61% of watering events show a rise with a
plain before/after average. For fertilizing it is 100%. The fertilizing effect
is stronger relative to its noise (peak around 120 against a noise std of 60,
while watering peaks around 2.5 against a noise std of 3), and the longer window
averages out more of the noise. I left the settings as they are.
