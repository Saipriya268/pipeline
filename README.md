# Order file processor

This project reads order events from CSV or NDJSON files and stores valid events
in SQLite. Rows that fail validation go into a separate table with the original
record and a reason. It reads one record at a time, so a larger file does not need
to fit in memory.

Python 3.10 or later is required. There are no extra packages or services to set up.
The data is synthetic and represents purchases and refunds in USD.

## Run it

Open a terminal in this folder:

```bash
python -m unittest discover -s tests -v
python scripts/demo.py
```

On Windows, use `py` instead of `python` if needed. The demo starts with a fresh
`work/demo` directory, loads the sample twice, and checks that the second load
adds no events. It also simulates a failure and retries it in a separate database.
It refreshes the sample reports under `evidence/`.

To run the commands separately, start with a new database path:

```bash
python -m orderpipe run --input samples/events.ndjson --db work/orders.db
python -m orderpipe report --db work/orders.db --output work/report
```

The sample has **12 rows: 4 accepted, 1 duplicate and 7 rejected**. The accepted
events total **1,400 cents ($14.00)**. Running the same input again accepts zero
new events. It counts five duplicates and records the seven rejects under a new
run ID. Expected answers are in `samples/expected.json`, separate from the input.

CSV works too:

```bash
python -m orderpipe run --input samples/events.csv --db work/csv.db
```

That file contains the first ten sample records: four accepted, one duplicate,
and five rejected. The total is still $14.00.

## Try a larger file

```bash
python -m orderpipe generate --output work/large.ndjson --rows 100000 --seed 42 --dirty
python -m orderpipe run --input work/large.ndjson --db work/large.db
python -m orderpipe report --db work/large.db --output work/large_report
```

With `--dirty`, every 25th row has an unknown customer. For 100,000 rows the
expected counts are 96,000 accepted and 4,000 rejected. The generator writes the
expected counts and total to a separate `.expected.json` file. Use `--format csv`
and a `.csv` output path to generate CSV instead.

## How it works

Read a line → check its fields and business rules → check customer and event ID
→ write an event or reject → commit the file and update its run status.

- `orderpipe/readers.py` reads and parses records, with a 1 MiB limit per line.
- `validation.py` checks values, normalizes timestamps and calculates net cents.
- `pipeline.py` handles duplicates, transactions and run counts.
- `schema.py` defines the tables and the three sample customers.
- `report.py` exports results and runs reconciliation checks.

SQLite checks event IDs on disk instead of keeping a growing set in Python.
A repeated ID with matching content is skipped. A repeated ID with different
content is rejected. Purchases are positive amounts; refunds are negative.
Events are kept as history, including those that arrive out of order.

## Check the results

The report folder contains `order_events.csv`, `rejects.csv`, `runs.csv`,
`customer_summary.csv` and `validation.json`. The JSON report checks row counts,
source tracking, foreign keys and calculated amounts. A failed check returns a
nonzero exit code. Progress logs go to stderr; command results go to stdout.

These queries can be run in a SQLite browser:

```sql
SELECT COUNT(*) AS event_count, SUM(net_amount_cents) AS net_amount_cents
FROM order_events;

SELECT run_id, status, input_count, accepted_count, duplicate_count,
       rejected_count, committed_count
FROM runs;

SELECT source_file, source_row, reason FROM rejects;
SELECT * FROM customer_summary ORDER BY customer_id;
PRAGMA foreign_key_check;
```

## Retry a failed load

Each file is one transaction. A processing failure rolls back its event and
reject writes; the run is marked failed with zero committed events. Retry the
same command to start the file again. Older files can be loaded in the same way.

To see this, use a fresh database and deliberately fail after four records:

```bash
python -m orderpipe run --input samples/events.ndjson --db work/retry.db --fail-after 4
# The command above should fail. Retry without the injected failure:
python -m orderpipe run --input samples/events.ndjson --db work/retry.db
```

Keep source files unchanged during processing and retain them for investigations.
Hard termination needs an extra operator step, described in [design notes](docs/design.md).

## Tests and measurements

The tests cover malformed input, missing and null fields, duplicates, schema
changes, unknown customers, empty files, pricing boundaries, late refunds,
rollback and reruns. Recorded output is in [evidence/tests.txt](evidence/tests.txt).
[clean_setup.txt](evidence/clean_setup.txt) records a fresh-environment test run.

On Linux or macOS, run:

```bash
python scripts/benchmark.py --rows 10000 100000 500000
```

The benchmark starts a separate process for each input size and checks its counts
and total against the generator's answers. It measures ingestion time and peak
RSS, excluding generation and export. Linux workers also enforce a 128 MiB
address-space limit. Results and machine details are in
[evidence/performance.json](evidence/performance.json); times will vary by machine.
The core pipeline, tests and demo do not require Unix, but the benchmark does.

## Assumptions and limits

JSON input means NDJSON: one object per line, not a JSON array. CSV records must
also fit on one physical line. Customers are a small local reference table.
Refunds are independent adjustments; matching them against earlier purchases is
outside this version. Only one writer is supported. Disk usage grows with data,
and very large totals can exceed SQLite's signed 64-bit integer range.

More detail:

- [Fields and business rules](docs/data_dictionary.md)
- [Design, recovery and possible improvements](docs/design.md)
- [Challenge checklist](docs/acceptance_matrix.md)
- [Code review notes](docs/review_notes.md)

## Put it on GitHub

Create an empty public repository, then run the following with your own URL:

```bash
git init
git add .
git commit -m "Add order file processor and tests"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/order-file-processor.git
git push -u origin main
```

`work/` is ignored so large generated files and databases stay out of the repo.
The included GitHub Actions workflow runs tests and the demo on Windows and Linux
with Python 3.10, 3.12, 3.13 and 3.14. The 100k benchmark runs on Linux only. Check the hosted results and public repository access
before submitting the URL; local evidence is not a hosted CI result.
