# Design decisions

Short notes on why things are the way they are.

**Flag rows instead of deleting them.** A row can have one bad value and several
good ones, and a bad value is also evidence that a sensor has a problem. Deleting
the row would lose both. The only rows removed are exact duplicates.

**Keep key conflicts.** Two rows with the same key but different values aren't
duplicates, and there's no way to tell which one is right. Both are kept and flagged.

**Quarantine only what can't be placed in time.** Without a timestamp a row can't
be checked for duplicates or gaps, so those rows are set aside. Every other problem
is something that can be flagged on a row.

**Missing readings go in their own table.** A gap is a row that doesn't exist, so
it can't carry a flag. `find_missing_intervals` returns one row per gap instead.

**Blank and non-numeric values get separate flags.** A blank cell and text like
`ERR` suggest different causes, so they're kept apart.

**Settings live in `config.py`.** Ranges, the sampling interval, timestamp formats
and the drift threshold are all in one file, so changing one doesn't mean editing
the checks. The numbers are estimates and are labelled that way.

**Daily median for drift.** A few hours of high EC after fertilizing would move a
daily mean, but not a median. With the median, the healthy devices in the sample
data never rose more than about 55 over 3 days and the drifting one rose about 600,
so a threshold of 150 separates them.

**The event response is a plain before/after average.** It's easy to explain, but a
small effect on top of a bigger trend can be missed. The moisture result (about
61% of waterings show a rise) is weak for that reason, and a detrended version
would be the next step.

**Parquet and DuckDB.** Parquet keeps column types and is what S3 and Athena would
use later. DuckDB reads those files directly, so the same SQL could move to Athena.

**Local first.** The whole pipeline runs on a laptop with no AWS account. AWS is a
later, optional step, and nothing there will be created without checking the cost first.

**Time windows are `timedelta` objects.** On pandas 2.3 with NumPy 2.5,
`pd.Timedelta("2h")` raises a deprecation warning from inside pandas. Passing a
`datetime.timedelta` avoids it.

**Synthetic data.** It has a fixed random seed, so every run gives the same files,
and the problems in it are known. That makes it possible to check that each rule
finds what it should.
