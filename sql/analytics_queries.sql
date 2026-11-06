-- Analytics queries over the pipeline output.
--
-- Each query starts with "-- name:" and "-- question:" lines. The tables are:
--   silver                 validated readings, with the flag_* columns
--   device_daily_quality   readings and suspect readings per device and day
--   event_response         mean value before and after each watering/fertilizing event
--   missing_intervals      gaps in the readings
--
-- The SQL is kept to standard features so it also runs outside DuckDB.

-- name: missing_by_device
-- question: Which devices have the most missing readings?
SELECT device_id,
       COUNT(*) AS missing_intervals,
       CAST(SUM(missing_readings) AS BIGINT) AS missing_readings
FROM missing_intervals
GROUP BY device_id
ORDER BY missing_readings DESC, device_id;

-- name: device_overview
-- question: How do the devices compare on suspect and missing readings?
SELECT q.device_id,
       q.readings,
       q.suspect_readings,
       ROUND(CAST(q.suspect_readings AS DOUBLE) / q.readings, 3) AS suspect_rate,
       COALESCE(m.missing_readings, 0) AS missing_readings
FROM (
    SELECT device_id,
           CAST(SUM(total_readings) AS BIGINT) AS readings,
           CAST(SUM(suspect_readings) AS BIGINT) AS suspect_readings
    FROM device_daily_quality
    GROUP BY device_id
) q
LEFT JOIN (
    SELECT device_id, CAST(SUM(missing_readings) AS BIGINT) AS missing_readings
    FROM missing_intervals
    GROUP BY device_id
) m ON q.device_id = m.device_id
ORDER BY suspect_rate DESC, q.device_id;

-- name: worst_day_per_device
-- question: What is each device's worst day, and on how many days did it have suspect readings?
SELECT device_id,
       COUNT(*) AS days,
       CAST(SUM(CASE WHEN suspect_readings > 0 THEN 1 ELSE 0 END) AS BIGINT) AS days_with_suspect,
       ROUND(MAX(CAST(suspect_readings AS DOUBLE) / total_readings), 3) AS worst_day_rate
FROM device_daily_quality
GROUP BY device_id
ORDER BY worst_day_rate DESC, days_with_suspect DESC, device_id;

-- name: flags_by_device_sensor
-- question: Which sensors show repeated or drifting readings?
SELECT device_id,
       sensor_type,
       CAST(SUM(CAST(flag_flatline AS INTEGER)) AS BIGINT) AS flatline_rows,
       CAST(SUM(CAST(flag_drift AS INTEGER)) AS BIGINT) AS drift_rows
FROM silver
GROUP BY device_id, sensor_type
HAVING SUM(CAST(flag_flatline AS INTEGER)) + SUM(CAST(flag_drift AS INTEGER)) > 0
ORDER BY device_id, sensor_type;

-- name: rule_counts
-- question: How many readings does each validation rule flag?
SELECT 'unit_mismatch' AS rule, CAST(SUM(CAST(flag_unit_mismatch AS INTEGER)) AS BIGINT) AS rows_flagged FROM silver
UNION ALL
SELECT 'hard_bound_violation', CAST(SUM(CAST(flag_hard_bound_violation AS INTEGER)) AS BIGINT) FROM silver
UNION ALL
SELECT 'outside_typical_range', CAST(SUM(CAST(flag_outside_typical_range AS INTEGER)) AS BIGINT) FROM silver
UNION ALL
SELECT 'flatline', CAST(SUM(CAST(flag_flatline AS INTEGER)) AS BIGINT) FROM silver
UNION ALL
SELECT 'drift', CAST(SUM(CAST(flag_drift AS INTEGER)) AS BIGINT) FROM silver
UNION ALL
SELECT 'missing_value', CAST(SUM(CAST(flag_missing_value AS INTEGER)) AS BIGINT) FROM silver
UNION ALL
SELECT 'non_numeric_value', CAST(SUM(CAST(flag_non_numeric_value AS INTEGER)) AS BIGINT) FROM silver
UNION ALL
SELECT 'key_conflict', CAST(SUM(CAST(is_key_conflict AS INTEGER)) AS BIGINT) FROM silver
ORDER BY rows_flagged DESC, rule;

-- name: event_response_overall
-- question: Do moisture and EC change after watering and fertilizing events?
SELECT event_type,
       sensor_type,
       COUNT(*) AS events_with_data,
       ROUND(AVG(delta), 2) AS mean_change,
       ROUND(AVG(CASE WHEN delta > 0 THEN 1.0 ELSE 0.0 END), 3) AS share_rising
FROM event_response
WHERE delta IS NOT NULL
GROUP BY event_type, sensor_type
ORDER BY event_type;

-- name: event_response_by_device
-- question: How does the response differ between devices? Each device has only a few events, so treat this as rough.
SELECT device_id,
       event_type,
       COUNT(*) AS events_with_data,
       ROUND(AVG(delta), 2) AS mean_change,
       ROUND(AVG(CASE WHEN delta > 0 THEN 1.0 ELSE 0.0 END), 3) AS share_rising
FROM event_response
WHERE delta IS NOT NULL
GROUP BY device_id, event_type
ORDER BY device_id, event_type;
