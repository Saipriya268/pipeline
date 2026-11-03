import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .schema import SCHEMA
from .readers import records
from .validation import validate

LOG = logging.getLogger('orderpipe')


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def connect(database):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(database, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    # Negative cache_size is measured in KiB, not pages.
    db.execute('PRAGMA cache_size=-4096')
    db.execute('PRAGMA temp_store=FILE')
    db.executescript(SCHEMA)
    return db


def fingerprint(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def store_event(db, record, run_id, source_file, source_row):
    """Validate a record, then either insert it or recognize a repeated delivery."""
    record = validate(record)
    customer = db.execute(
        'SELECT 1 FROM customers WHERE customer_id=?',
        (record['customer_id'],),
    ).fetchone()
    if customer is None:
        raise ValueError('invalid_reference_key: customer_id')

    existing = db.execute(
        'SELECT payload_sha256 FROM order_events WHERE event_id=?',
        (record['event_id'],),
    ).fetchone()
    if existing:
        # A repeated ID is safe only when its normalized content also matches.
        if existing['payload_sha256'] != record['payload_sha256']:
            raise ValueError('duplicate_key_conflict')
        return 'duplicate_count'

    record.update(run_id=run_id, source_file=source_file, source_row=source_row)
    db.execute(
        """INSERT INTO order_events (
            event_id, order_id, customer_id, event_type, event_time, quantity,
            unit_price_cents, discount_cents, net_amount_cents, payload_sha256,
            run_id, source_file, source_row
        ) VALUES (
            :event_id, :order_id, :customer_id, :event_type, :event_time, :quantity,
            :unit_price_cents, :discount_cents, :net_amount_cents, :payload_sha256,
            :run_id, :source_file, :source_row
        )""",
        record,
    )
    return 'accepted_count'


def ingest(source, database, fmt=None, fail_after=None):
    source = str(Path(source).resolve())
    fmt = fmt or ('csv' if source.endswith('.csv') else 'ndjson')
    if fmt not in ('csv', 'ndjson'):
        raise ValueError('format must be csv or ndjson')
    db = connect(database)
    run_id = str(uuid.uuid4())
    counts = dict(input_count=0, accepted_count=0, duplicate_count=0, rejected_count=0)
    db.execute('INSERT INTO runs(run_id,source_file,started_at,status) VALUES(?,?,?,?)',
               (run_id, source, now(), 'running'))
    db.commit()
    LOG.info(json.dumps(dict(event='run_started', run_id=run_id, source_file=source)))
    try:
        initial_hash = fingerprint(source)
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE runs SET source_sha256=? WHERE run_id=?', (initial_hash, run_id))
        for row, raw, record, error in records(source, fmt):
            counts['input_count'] += 1
            if error is None:
                try:
                    outcome = store_event(db, record, run_id, source, row)
                    counts[outcome] += 1
                except ValueError as exc:
                    error = str(exc)
            if error is not None:
                db.execute('INSERT INTO rejects VALUES(?,?,?,?,?)', (run_id, source, row, error, raw))
                counts['rejected_count'] += 1
            if fail_after is not None and counts['input_count'] >= fail_after:
                raise RuntimeError('injected failure for recovery demonstration')
        if fingerprint(source) != initial_hash:
            raise RuntimeError('source changed while processing; retry with an immutable file')
        assert counts['input_count'] == sum(counts[k] for k in ('accepted_count', 'duplicate_count', 'rejected_count'))
        db.execute('''UPDATE runs SET ended_at=?,status='succeeded',input_count=?,accepted_count=?,
         duplicate_count=?,rejected_count=?,committed_count=? WHERE run_id=?''',
         (now(), counts['input_count'], counts['accepted_count'], counts['duplicate_count'],
          counts['rejected_count'], counts['accepted_count'], run_id))
        db.commit()
    except Exception as exc:
        db.rollback()
        # Keep the failure audit even though the file's event and reject writes rolled back.
        db.execute('''UPDATE runs SET ended_at=?,status='failed',input_count=?,accepted_count=?,
         duplicate_count=?,rejected_count=?,committed_count=0,failure_reason=? WHERE run_id=?''',
         (now(), counts['input_count'], counts['accepted_count'], counts['duplicate_count'],
          counts['rejected_count'], f'{type(exc).__name__}: {exc}', run_id))
        db.commit()
        LOG.error(json.dumps(dict(event='run_failed', run_id=run_id, failure_reason=str(exc), **counts)))
        raise
    finally:
        db.close()
    result = dict(run_id=run_id, status='succeeded', committed_count=counts['accepted_count'], **counts)
    LOG.info(json.dumps(dict(event='run_finished', **result)))
    return result
