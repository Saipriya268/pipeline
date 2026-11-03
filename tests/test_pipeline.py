import csv
from contextlib import closing
import json
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from orderpipe.generate import event, generate
from orderpipe.pipeline import ingest
from orderpipe.report import report
from orderpipe.readers import MAX_LINE_BYTES


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'input.ndjson'
        self.db = self.root / 'target.db'
        self.base = event(1, random.Random(42))

    def write(self, objects):
        self.source.write_text(''.join(json.dumps(obj) + '\n' for obj in objects))

    def scalar(self, sql):
        with closing(sqlite3.connect(self.db)) as db:
            return db.execute(sql).fetchone()[0]

    def test_scalar_closes_connection_on_success_and_error(self):
        # Windows cannot remove a database while a connection still holds it open.
        for sql in ('SELECT 1', 'SELECT * FROM missing_table'):
            with self.subTest(sql=sql):
                connection = sqlite3.connect(self.db)
                try:
                    with patch('sqlite3.connect', return_value=connection):
                        if sql == 'SELECT 1':
                            self.assertEqual(self.scalar(sql), 1)
                        else:
                            with self.assertRaises(sqlite3.OperationalError):
                                self.scalar(sql)
                    with self.assertRaises(sqlite3.ProgrammingError):
                        connection.execute('SELECT 1')
                finally:
                    connection.close()

    def test_happy_path_and_reconciliation(self):
        expected = generate(self.source, 100, dirty=True)
        result = ingest(self.source, self.db)
        self.assertEqual(result['accepted_count'], expected['accepted_count'])
        self.assertEqual(result['rejected_count'], 4)
        result = report(self.db, self.root / 'report')
        self.assertTrue(result['passed'])
        self.assertEqual(result['net_amount_cents'], expected['net_amount_cents'])

    def test_empty_input(self):
        self.source.touch()
        self.assertEqual(ingest(self.source, self.db)['input_count'], 0)

    def test_malformed_and_valid_records(self):
        self.source.write_text('{broken\n' + json.dumps(self.base) + '\n')
        result = ingest(self.source, self.db)
        self.assertEqual((result['rejected_count'], result['accepted_count']), (1, 1))
        self.assertIn('{broken', self.scalar('SELECT raw_record FROM rejects'))
        self.assertEqual(self.scalar('SELECT source_row FROM rejects'), 1)

    def test_missing_null_extra_and_wrong_type(self):
        missing = dict(self.base)
        del missing['order_id']
        self.write([missing, dict(self.base, event_id=None), dict(self.base, extra='x'),
                    dict(self.base, quantity=True), dict(self.base, unit_price_cents=1.5),
                    dict(self.base, event_time=None)])
        self.assertEqual(ingest(self.source, self.db)['rejected_count'], 6)

    def test_duplicate_same_conflicting_and_rerun(self):
        self.write([self.base, self.base, dict(self.base, quantity=self.base['quantity']+1)])
        first = ingest(self.source, self.db)
        self.assertEqual([first[k] for k in ('accepted_count','duplicate_count','rejected_count')], [1,1,1])
        second = ingest(self.source, self.db)
        self.assertEqual([second[k] for k in ('accepted_count','duplicate_count','rejected_count')], [0,2,1])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM order_events'), 1)

    def test_invalid_customer_reference(self):
        self.write([dict(self.base, customer_id='unknown')])
        self.assertEqual(ingest(self.source, self.db)['rejected_count'], 1)
        self.assertIn('invalid_reference', self.scalar('SELECT reason FROM rejects'))

    def test_discount_boundary_and_over_discount(self):
        self.write([dict(self.base, event_id='free', quantity=2, unit_price_cents=100, discount_cents=200),
                    dict(self.base, event_id='bad', quantity=2, unit_price_cents=100, discount_cents=201)])
        result = ingest(self.source, self.db)
        self.assertEqual((result['accepted_count'], result['rejected_count']), (1,1))
        self.assertEqual(self.scalar('SELECT net_amount_cents FROM order_events'), 0)

    def test_refund_and_late_event_history(self):
        self.write([dict(self.base, event_id='new', event_time='2026-02-01T00:00:00Z', quantity=1, unit_price_cents=100),
                    dict(self.base, event_id='late', event_type='refund', event_time='2026-01-01T00:00:00Z', quantity=1, unit_price_cents=25)])
        self.assertEqual(ingest(self.source, self.db)['accepted_count'], 2)
        self.assertEqual(self.scalar('SELECT SUM(net_amount_cents) FROM order_events'), 75)

    def test_quantity_price_boundaries(self):
        self.write([dict(self.base, event_id='zero', quantity=1, unit_price_cents=0),
                    dict(self.base, event_id='max', quantity=10000, unit_price_cents=100000000),
                    dict(self.base, event_id='bad1', quantity=0),
                    dict(self.base, event_id='bad2', unit_price_cents=-1)])
        result = ingest(self.source, self.db)
        self.assertEqual((result['accepted_count'], result['rejected_count']), (2,2))

    def test_partial_failure_and_retry(self):
        generate(self.source, 10, dirty=True)
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            ingest(self.source, self.db, fail_after=5)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM order_events'), 0)
        self.assertEqual(self.scalar('SELECT committed_count FROM runs'), 0)
        self.assertEqual(self.scalar('SELECT status FROM runs'), 'failed')
        self.assertEqual(ingest(self.source, self.db)['accepted_count'], 10)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM runs'), 2)

    def test_csv_and_cross_format_duplicates(self):
        path = self.root / 'input.csv'
        generate(path, 10, fmt='csv')
        self.assertEqual(ingest(path, self.db)['accepted_count'], 10)
        generate(self.source, 10)
        self.assertEqual(ingest(self.source, self.db)['duplicate_count'], 10)

    def test_csv_schema_change_fails(self):
        path = self.root / 'bad.csv'
        path.write_text('event_id,new_column\nx,y\n')
        with self.assertRaisesRegex(ValueError, 'schema'):
            ingest(path, self.db)
        self.assertEqual(self.scalar('SELECT status FROM runs'), 'failed')

    def test_csv_bad_field_count(self):
        path = self.root / 'input.csv'
        generate(path, 1, fmt='csv')
        with path.open('a') as output:
            output.write('too,few\n')
        result = ingest(path, self.db)
        self.assertEqual((result['accepted_count'], result['rejected_count']), (1,1))

    def test_invalid_utf8(self):
        self.source.write_bytes(b'\xff\n')
        self.assertEqual(ingest(self.source, self.db)['rejected_count'], 1)

    def test_oversize_fails_atomically(self):
        self.source.write_bytes((json.dumps(self.base)+'\n').encode()+b'x'*(MAX_LINE_BYTES+1))
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            ingest(self.source, self.db)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM order_events'), 0)

    def test_timezone_normalized_duplicate(self):
        self.write([dict(self.base, event_time='2026-01-01T00:00:00Z'),
                    dict(self.base, event_time='2025-12-31T18:00:00-06:00')])
        self.assertEqual(ingest(self.source, self.db)['duplicate_count'], 1)

    def test_missing_file_exposes_failure(self):
        with self.assertRaises(FileNotFoundError):
            ingest(self.source, self.db)
        self.assertIn('FileNotFoundError', self.scalar('SELECT failure_reason FROM runs'))

    def test_duplicate_json_property(self):
        self.source.write_text('{"event_id":"x","event_id":"y"}\n')
        self.assertEqual(ingest(self.source, self.db)['rejected_count'], 1)

    def test_invalid_timestamp_and_nonstandard_json(self):
        self.write([dict(self.base, event_time='2026-02-30T00:00:00Z')])
        with self.source.open('a') as out:
            out.write('{"quantity":NaN}\n')
        self.assertEqual(ingest(self.source, self.db)['rejected_count'], 2)

    def test_empty_and_header_only_csv(self):
        path = self.root / 'empty.csv'
        path.touch()
        self.assertEqual(ingest(path, self.db)['input_count'], 0)
        generate(path, 0, fmt='csv')
        self.assertEqual(ingest(path, self.db)['input_count'], 0)

    def test_source_mutation_rolls_back(self):
        self.write([self.base])
        with patch('orderpipe.pipeline.fingerprint', side_effect=['before', 'after']):
            with self.assertRaisesRegex(RuntimeError, 'source changed'):
                ingest(self.source, self.db)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM order_events'), 0)
        self.assertEqual(self.scalar('SELECT status FROM runs'), 'failed')

    def test_rejects_rollback_on_partial_failure(self):
        self.write([dict(self.base, customer_id='unknown'), self.base])
        with self.assertRaises(RuntimeError):
            ingest(self.source, self.db, fail_after=2)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM rejects'), 0)
        self.assertEqual(self.scalar('SELECT rejected_count FROM runs'), 1)
        result = ingest(self.source, self.db)
        self.assertEqual((result['accepted_count'], result['rejected_count']), (1,1))
        self.assertTrue(report(self.db, self.root / 'report')['passed'])

    def test_invalid_timezone_offset(self):
        self.write([dict(self.base, event_time='2026-01-01T00:00:00+01:99')])
        self.assertEqual(ingest(self.source, self.db)['rejected_count'], 1)

    def test_report_requires_existing_database(self):
        with self.assertRaises(FileNotFoundError):
            report(self.db, self.root / 'output')
        self.assertFalse(self.db.exists())

    def test_no_final_newline(self):
        self.source.write_text(json.dumps(self.base))
        self.assertEqual(ingest(self.source, self.db)['accepted_count'], 1)

    def test_hand_calculated_sample(self):
        root = Path(__file__).resolve().parents[1]
        expected = json.loads((root / 'samples/expected.json').read_text())
        result = ingest(root / 'samples/events.ndjson', self.db)
        for key in ('input_count','accepted_count','duplicate_count','rejected_count'):
            self.assertEqual(result[key], expected[key])
        self.assertEqual(self.scalar('SELECT SUM(net_amount_cents) FROM order_events'), 1400)

    def test_deterministic_generator(self):
        other = self.root / 'other.ndjson'
        generate(self.source, 50)
        generate(other, 50)
        self.assertEqual(self.source.read_bytes(), other.read_bytes())


if __name__ == '__main__':
    unittest.main()
