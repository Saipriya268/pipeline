import argparse
import json
import logging
from .generate import generate
from .pipeline import ingest
from .report import report


def main():
    parser = argparse.ArgumentParser(description='Stream synthetic order events into SQLite')
    commands = parser.add_subparsers(dest='command', required=True)
    generate_parser = commands.add_parser('generate')
    generate_parser.add_argument('--output', required=True)
    generate_parser.add_argument('--rows', type=int, default=100000)
    generate_parser.add_argument('--seed', type=int, default=42)
    generate_parser.add_argument('--format', choices=['csv', 'ndjson'], default='ndjson')
    generate_parser.add_argument('--dirty', action='store_true')
    run_parser = commands.add_parser('run')
    run_parser.add_argument('--input', required=True)
    run_parser.add_argument('--db', required=True)
    run_parser.add_argument('--format', choices=['csv', 'ndjson'])
    run_parser.add_argument('--fail-after', type=int, help='Test-only fault injection after N records')
    report_parser = commands.add_parser('report')
    report_parser.add_argument('--db', required=True)
    report_parser.add_argument('--output', required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        if args.command == 'generate':
            result = generate(args.output, args.rows, args.seed, args.format, args.dirty)
        elif args.command == 'run':
            result = ingest(args.input, args.db, args.format, args.fail_after)
        else:
            result = report(args.db, args.output)
        print(json.dumps(result, indent=2))
        return 1 if result.get('passed') is False else 0
    except Exception as exc:
        logging.error('%s: %s', type(exc).__name__, exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
