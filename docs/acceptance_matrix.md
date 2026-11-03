# Challenge checklist

| Requirement | Implementation / evidence |
|---|---|
| Source/target schema, types, keys, grain, relationships | data_dictionary.md; schema.py; customer FK and event primary key |
| Small reproducible input; scalable fixed-seed generator | samples/events.ndjson and events.csv; generate.py; make_sample.py |
| Ingestion, validation, transformation, publishing | readers.py → validation.py → pipeline.py → SQLite; report.py |
| Bounded resource use; 100,000+ rows | 1 MiB record cap, 4 MiB SQLite cache, bounded hash reads; performance.json with 10k/100k/500k runs |
| Malformed and missing/null records | quarantine with raw record, physical line, source_file, run_id; automated tests |
| Unexpected schema | Strict exact fields; JSON row reject; CSV header fails batch |
| Duplicate event and conflicting duplicate | Canonical payload hash + event primary key; exact duplicate skipped, conflict quarantined |
| Empty batch | Empty NDJSON/CSV and header-only CSV supported; tests |
| Invalid reference key | customers table lookup and SQL FK; test_invalid_customer_reference |
| Domain-specific edge cases | Full discount/over-discount, zero price, quantity limits, negative refund amount |
| Late and out-of-order data; history | test_refund_and_late_event_history; immutable ledger with original event time |
| Partial failure/retry | Fault injection, atomic rollback and successful replay; recovery_output and tests |
| Rerun same input | demo.py replays sample; zero newly accepted events; no target duplicates |
| Logs and operational metrics | JSON log events; runs table with status, counts, times and failure reason |
| Deterministic IDs and transformations | Producer event IDs; normalized UTC; canonical hashes; integer cents |
| Independent correctness check | Hand-calculated samples/expected.json; generator expected sidecars; report SQL invariants |
| Setup/run and clean reproducibility | README quickstart; standard library; CI runs tests and demo |
| Performance measurement and optimization | scripts/benchmark.py; evidence/performance.json; design.md |
| Source, tests, sample output and design note | Entire project; evidence/sample_output; docs/design.md |
| Public GitHub repository | Publish the repository and verify public access before submission; commands are in README |
