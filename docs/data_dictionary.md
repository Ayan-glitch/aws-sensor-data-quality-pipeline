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
| `value` | float | The unit depends on `sensor_type`. A null value is not handled yet (see the README). |
| `unit` | text | Checked against the expected unit for the sensor type. A mismatch, such as `F` where `C` is expected, is a unit problem and not an invalid value. |
| `source_file` | text | Added during ingestion. |
| `ingested_at` | datetime | Added during ingestion. |

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

## context_events

| Column | Type | Notes |
|---|---|---|
| `event_id` | integer | |
| `device_id` | text | Matches `sensor_readings.device_id`. |
| `event_timestamp` | datetime | |
| `event_type` | text | `watering` or `fertilizing`. |
| `event_text` | text | A short note with only a few different wordings. |

## Problems added to the sample data

| # | Device | Problem | Detected by the pipeline |
|---|---|---|---|
| 1 | `DEV-05` | Exact duplicate rows | Yes |
| 2 | `DEV-02` | `soil_temp` labelled `F` instead of `C` | Yes |
| 3 | `DEV-07` | `soil_moisture` timestamps in a different format | Yes, parsed with the fallback format |
| 4 | `DEV-05` | Impossible moisture values (below 0) | Yes |
| 5 | `DEV-06` | `soil_moisture` stuck on one value | Yes |
| 6 | `DEV-04` | 2-day gap with no rows | Not yet |
| 7 | `DEV-03` | EC drifting upward over several days | Not yet |

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
