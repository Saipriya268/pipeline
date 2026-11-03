"""End-to-end clean demo, replay, fault injection and independently checked outputs."""
import json
import shutil
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orderpipe.pipeline import ingest
from orderpipe.report import report

work = ROOT / 'work/demo'
if work.exists():
    shutil.rmtree(work)
work.mkdir(parents=True)
source = ROOT / 'samples/events.ndjson'
db = work / 'orders.db'
expected = json.loads((ROOT / 'samples/expected.json').read_text())
first = ingest(source, db)
for key in ('input_count','accepted_count','duplicate_count','rejected_count'):
    assert first[key] == expected[key], (key, first[key], expected[key])
replay = ingest(source, db)
assert replay['accepted_count'] == 0 and replay['duplicate_count'] == 5
fault_db = work / 'retry.db'
try:
    ingest(source, fault_db, fail_after=4)
except RuntimeError:
    pass
else:
    raise AssertionError('fault injection did not fail')
retry = ingest(source, fault_db)
assert retry['accepted_count'] == 4
validation = report(db, ROOT / 'evidence/sample_output')
assert validation['passed'] and validation['net_amount_cents'] == expected['net_amount_cents']
assert validation['event_count'] == expected['event_count']
report(fault_db, ROOT / 'evidence/recovery_output')
summary = dict(first_run=first, rerun=replay, retry=retry, validation=validation,
               expected_answers_matched=True)
(ROOT / 'evidence/demo.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2))
