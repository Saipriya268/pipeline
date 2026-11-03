# Data dictionary

## What a row represents

The grain is one financial order event. Rows are kept as history rather than
updated to show an order's current state.
`event_id` is the global business primary key, supplied by the source. A producer
must reuse the same event ID on delivery retries and assign a new ID to a new event.
`order_id` groups events; an order may have many events. No separate order master
is inferred. `customer_id` references the `customers` dimension (many events to one
customer). The three synthetic customers are `customer_001` to `customer_003`.
All use one assumed currency, USD; multi-currency input is out of scope.

Purchases contribute positive net amounts and refunds negative net amounts. A
refund is an independent ledger adjustment: it does not require a purchase to
have arrived first. Validating cumulative refund amounts against purchases is a
future enhancement, not an implemented invariant. Repeated order IDs are valid;
repeated event IDs are either exact duplicates or conflicts. Late events are
accepted without a watermark and retain their original event time. There is no
last-write-wins replacement. Corrections must use new compensating events.

## Input: CSV or newline-delimited JSON

Every field below is required and non-null; unexpected fields are disallowed.
CSV includes one header line and one physical line per event. NDJSON contains
one JSON object per physical line, without a header. A blank data line is a
malformed record, not silently ignored. Empty files and header-only CSVs succeed
with zero input records. Reordered CSV headers are allowed; duplicate headers,
missing/extra headers or an invalid UTF-8 header fail the entire batch. JSON arrays,
multiline CSV fields and pretty-printed multiline JSON are intentionally unsupported.
Use NDJSON for JSON sources, or export them to the documented CSV layout upstream.

| Column | Input type | Rules |
|---|---|---|
| event_id | string | Global primary key; 1–64 ASCII letters, digits, `_` or `-` |
| order_id | string | Order grouping key; same ID syntax |
| customer_id | string | Same ID syntax; must exist in customers |
| event_type | string enum | `purchase` or `refund` |
| event_time | string | ISO-8601 date and time, seconds required; timezone required; up to 6 fractional digits |
| quantity | integer | 1 through 10,000 inclusive |
| unit_price_cents | integer | 0 through 100,000,000 inclusive |
| discount_cents | integer | 0 through quantity × unit_price_cents inclusive |

JSON integers and CSV decimal digit strings are accepted for integer columns.
Floats, booleans, negative amounts, whitespace-padded numeric strings, and nulls
are rejected. Digit strings have a maximum length of 15. JSON duplicate property
names, NaN and Infinity are malformed. There is no implicit trimming of identifiers.

## Stored events

`order_events` contains all normalized input columns plus:

| Column | Type | Meaning |
|---|---|---|
| event_time | TEXT | Normalized UTC, `YYYY-MM-DDTHH:MM:SS.ffffffZ` |
| net_amount_cents | INTEGER | `(quantity * unit_price_cents - discount_cents) * sign`; refund sign = −1 |
| payload_sha256 | TEXT | SHA-256 of sorted compact JSON of normalized input and net amount; excludes lineage |
| run_id | TEXT FK | First successful publishing run |
| source_file | TEXT | Absolute input file path at execution |
| source_row | INTEGER | 1-based physical line, including CSV header in numbering |

The event_id index checks duplicates on disk instead of keeping IDs in a Python set.
Matching canonical payloads increment `duplicate_count`. A different canonical
payload under an existing ID yields `duplicate_key_conflict`. First committed
valid event wins; conflicting new content cannot overwrite history. IDs are
stable source business identifiers. Payload hashes are deterministic fingerprints,
not replacement business keys. Operational run IDs are UUID4 execution identifiers
and deliberately differ for retries; they are not entity IDs.

`customers(customer_id TEXT PRIMARY KEY)` is a tiny local source-system mock.
For real onboarding, load an authorized authoritative customer snapshot first.
`customer_summary` is a view with customer_id, event_count and net_amount_cents.
All database/table/column names use snake_case.

## Runs and rejected rows

`runs`: run_id primary key, source_file, source_sha256, started_at, ended_at,
status (`running`, `succeeded`, `failed`), input_count, accepted_count,
duplicate_count, rejected_count, committed_count, failure_reason.
Times are UTC ISO-8601. source_sha256 is the bounded-read hash of the file;
on failed transactions it may be null because its write rolled back.

`rejects`: composite primary key `(run_id, source_row)`, source_file, source_row,
reason, raw_record. Each successful run has its own quarantine audit, so rerunning
invalid input creates new audit records but no duplicate target business events.
Malformed UTF-8 is shown using replacement characters; source path, line and
file fingerprint identify the original bytes. Keep source files immutable and
retained for investigations. No input contains expected-answer labels.

Successful-run invariant:

`input_count = accepted_count + duplicate_count + rejected_count`

`committed_count = accepted_count`

On an ordinary failure, counts reflect attempted records; committed_count is
zero and all event/reject writes from that run roll back. Failure reason and run
status persist separately. A failure is a batch failure, not a rejected row.
