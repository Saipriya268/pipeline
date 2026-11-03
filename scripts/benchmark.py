"""Linux/macOS subprocess benchmark; Linux workers enforce a 128 MiB address-space cap."""
import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orderpipe.generate import generate
from orderpipe.pipeline import ingest
from orderpipe.report import report


def worker(source, database):
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (128*1024**2, 128*1024**2))
    started = time.perf_counter()
    result = ingest(source, database)
    elapsed = time.perf_counter()-started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mib = peak/(1024**2 if sys.platform == 'darwin' else 1024)
    print(json.dumps(dict(**result, seconds=round(elapsed, 3), peak_rss_mib=round(peak_mib, 2),
                         rows_per_second=round(result['input_count']/elapsed))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, nargs='+', default=[10000,100000,500000])
    parser.add_argument('--work', default='work/benchmark')
    parser.add_argument('--output', default='evidence/performance.json')
    parser.add_argument('--worker', nargs=2)
    args = parser.parse_args()
    if args.worker:
        worker(*args.worker)
        return
    directory = Path(args.work)
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    for count in args.rows:
        source = directory / f'{count}.ndjson'
        database = directory / f'{count}.db'
        if database.exists():
            database.unlink()
        expected = generate(source, count, dirty=True)
        completed = subprocess.run([sys.executable, __file__, '--worker', str(source), str(database)],
                                   capture_output=True, text=True, check=True)
        result = json.loads(completed.stdout)
        validation = report(database, directory / f'report_{count}')
        assert validation['passed']
        assert validation['event_count'] == expected['accepted_count']
        assert validation['net_amount_cents'] == expected['net_amount_cents']
        assert result['rejected_count'] == expected['rejected_count']
        assert result['peak_rss_mib'] < 128
        result.update(input_mib=round(source.stat().st_size/1024**2, 2),
                      expected_aggregate_matches=True, validation_passed=True)
        results.append(result)
        print(json.dumps(result), flush=True)
    payload = dict(python=sys.version, platform=platform.platform(), cpu_count=os.cpu_count(),
                   memory_cap_mib=128 if sys.platform.startswith('linux') else None,
                   method='Separate process per ingestion; ru_maxrss includes interpreter; disk-backed SQLite cache 4 MiB. Generation and export excluded from ingestion timing.',
                   results=results)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, indent=2)+'\n')


if __name__ == '__main__':
    main()
