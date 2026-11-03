"""Small sample with hand-calculated answers stored in a separate file."""
import csv
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orderpipe.readers import FIELDS

base = dict(event_id='evt_001', order_id='order_001', customer_id='customer_001',
            event_type='purchase', event_time='2026-01-02T12:00:00Z', quantity=2,
            unit_price_cents=1000, discount_cents=100)
rows = [base, dict(base), dict(base, quantity=3),
        dict(base, event_id='evt_002', event_type='refund', event_time='2026-01-01T12:00:00Z',
             quantity=1, unit_price_cents=500, discount_cents=0),
        dict(base, event_id='evt_003', customer_id='customer_002', quantity=1, unit_price_cents=0, discount_cents=0),
        dict(base, event_id='evt_004', customer_id='customer_003', quantity=1, unit_price_cents=100, discount_cents=100),
        dict(base, event_id=None), dict(base, event_id='evt_005', customer_id='unknown'),
        dict(base, event_id='evt_006', discount_cents=2001),
        dict(base, event_id='evt_007', quantity=0)]
with (ROOT / 'samples/events.ndjson').open('w') as out:
    for row in rows:
        out.write(json.dumps(row)+'\n')
    out.write('{malformed JSON}\n')
    changed = dict(base, event_id='evt_008', unexpected_column='schema_drift')
    out.write(json.dumps(changed)+'\n')
with (ROOT / 'samples/events.csv').open('w', newline='') as out:
    writer = csv.DictWriter(out, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
expected = dict(input_count=12, accepted_count=4, duplicate_count=1, rejected_count=7,
                event_count=4, net_amount_cents=1400,
                accepted_event_ids=['evt_001','evt_002','evt_003','evt_004'],
                rejected_ndjson_lines=[3,7,8,9,10,11,12],
                note='CSV companion has first 10 records only: accepted=4, duplicates=1, rejected=5. Net total unchanged.')
(ROOT / 'samples/expected.json').write_text(json.dumps(expected, indent=2)+'\n')
