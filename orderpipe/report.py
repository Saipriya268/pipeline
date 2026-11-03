import csv
import json
from pathlib import Path
from .pipeline import connect


def report(database, output_dir):
    if not Path(database).is_file():
        raise FileNotFoundError(f'target database does not exist: {database}')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    db = connect(database)
    try:
        db.execute('BEGIN')  # Keep all exports on the same database snapshot.
        # Stream the cursor into CSV rather than building a list of rows.
        for table in ('order_events', 'rejects', 'runs', 'customer_summary'):
            cursor = db.execute(f'SELECT * FROM {table}')
            temporary = output_dir / f'.{table}.csv.tmp'
            with temporary.open('w', newline='', encoding='utf-8') as output:
                writer = csv.writer(output)
                writer.writerow([column[0] for column in cursor.description])
                writer.writerows(cursor)
            temporary.replace(output_dir / f'{table}.csv')
        count_errors = db.execute('''SELECT COUNT(*) FROM runs WHERE status='succeeded'
          AND input_count != accepted_count + duplicate_count + rejected_count''').fetchone()[0]
        reject_count_errors = db.execute('''SELECT COUNT(*) FROM runs r WHERE status='succeeded'
          AND rejected_count != (SELECT COUNT(*) FROM rejects q WHERE q.run_id=r.run_id)''').fetchone()[0]
        output_count_errors = db.execute('''SELECT COUNT(*) FROM runs r WHERE status='succeeded'
          AND committed_count != (SELECT COUNT(*) FROM order_events e WHERE e.run_id=r.run_id)''').fetchone()[0]
        invalid_totals = db.execute('''SELECT COUNT(*) FROM order_events WHERE net_amount_cents !=
          (quantity*unit_price_cents-discount_cents)*CASE event_type WHEN 'refund' THEN -1 ELSE 1 END''').fetchone()[0]
        fk_errors = sum(1 for _ in db.execute('PRAGMA foreign_key_check'))
        metrics = dict(db.execute('SELECT COUNT(*) AS event_count, COALESCE(SUM(net_amount_cents),0) AS net_amount_cents FROM order_events').fetchone())
        metrics.update(run_count_equation_errors=count_errors, reject_trace_errors=reject_count_errors,
                       output_trace_errors=output_count_errors, transformation_errors=invalid_totals,
                       foreign_key_errors=fk_errors)
        metrics['passed'] = not any((count_errors, reject_count_errors, output_count_errors, invalid_totals, fk_errors))
        (output_dir / 'validation.json').write_text(json.dumps(metrics, indent=2) + '\n')
        return metrics
    finally:
        db.close()
