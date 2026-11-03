"""Seeded synthetic generator; expected answers are written separately."""
import csv
import json
import random
from pathlib import Path
from .readers import FIELDS


def event(index, rng):
    return dict(event_id=f'event_{index:09d}', order_id=f'order_{index:09d}',
                customer_id=f'customer_{1 + index % 3:03d}',
                event_type='refund' if index % 10 == 0 else 'purchase',
                event_time=f'2026-01-{1 + index % 28:02d}T12:00:00Z',
                quantity=rng.randint(1, 5), unit_price_cents=rng.randint(0, 10000),
                discount_cents=0)


def generate(path, rows=100000, seed=42, fmt='ndjson', dirty=False):
    if rows < 0:
        raise ValueError('rows must be nonnegative')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    total = 0
    rejected = 0
    with path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS) if fmt == 'csv' else None
        if writer:
            writer.writeheader()
        for i in range(rows):
            record = event(i, rng)
            # Known synthetic anomalies; no expected-answer labels enter the inputs.
            invalid = dirty and i % 25 == 24
            if invalid:
                record['customer_id'] = 'unknown_customer'
                rejected += 1
            else:
                sign = -1 if record['event_type'] == 'refund' else 1
                total += sign * record['quantity'] * record['unit_price_cents']
            if writer:
                writer.writerow(record)
            else:
                output.write(json.dumps(record, separators=(',', ':')) + '\n')
    expected = dict(input_count=rows, accepted_count=rows-rejected, rejected_count=rejected,
                    duplicate_count=0, net_amount_cents=total, seed=seed)
    path.with_suffix(path.suffix + '.expected.json').write_text(json.dumps(expected, indent=2) + '\n')
    return expected
