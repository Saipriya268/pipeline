# Reviewing the code

Start with `pipeline.ingest()`, then follow a record through `readers.records()`
and `validation.validate()`. The report module shows the checks made after loading.

A few choices worth understanding before changing the code:

- Money is stored as integer cents to avoid floating-point rounding.
- The producer's event ID identifies an event. The payload hash only checks
  whether another delivery of that ID contains the same normalized values.
- UTC normalization makes equivalent timestamps compare equally. CSV numeric
  strings and JSON integers also normalize to the same values.
- SQLite performs duplicate lookups so a set of seen IDs does not grow in RAM.
- A refund is a separate signed event. Its purchase may arrive later; there is
  no rule here that validates the total refunded against the purchase amount.
- Per-run counts include duplicate and rejected rows, not just inserted rows.
  Failed-run attempt counts are different from committed target counts.

Useful things to try locally:

1. Change an amount in the sample while keeping its event ID. Load it into a
   database that already contains the original and inspect the conflict reject.
2. Load the unchanged sample twice and compare the target counts.
3. Use `--fail-after 4`, then retry without it and inspect both audit rows.
4. Read the benchmark results alongside the 1 MiB record limit and 4 MiB cache
   settings. Bounded memory does not mean bounded disk space.

The customer list, refund rules and file-level transaction are deliberate scope
choices. They are documented limits, not features to assume are already present.
