"""CSV and NDJSON readers with a fixed limit on each physical line."""
import csv
import json

FIELDS = ('event_id', 'order_id', 'customer_id', 'event_type', 'event_time',
          'quantity', 'unit_price_cents', 'discount_cents')
MAX_LINE_BYTES = 1024 * 1024


def lines(path, limit=MAX_LINE_BYTES):
    with open(path, 'rb') as source:
        row = 0
        while True:
            raw = source.readline(limit + 1)
            if not raw:
                return
            row += 1
            if len(raw) > limit:
                raise ValueError(f'physical line {row} exceeds {limit} bytes; batch aborted')
            yield row, raw


def reject_constant(value):
    raise ValueError(f'nonstandard JSON constant: {value}')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON property: {key}')
        result[key] = value
    return result


def records(path, fmt):
    """Yield (physical line number, bounded raw text, object, parse error)."""
    iterator = iter(lines(path))
    if fmt == 'csv':
        header = next(iterator, None)
        if header is None:
            return
        try:
            names = next(csv.reader([header[1].decode('utf-8-sig')], strict=True))
        except (UnicodeError, csv.Error) as exc:
            raise ValueError(f'invalid CSV header: {exc}') from exc
        if len(names) != len(FIELDS) or set(names) != set(FIELDS):
            raise ValueError('unexpected CSV schema: header must contain exactly the documented fields')
    for row, raw in iterator:
        text = raw.decode('utf-8', errors='replace').rstrip('\r\n')
        try:
            decoded = raw.decode('utf-8')
            if fmt == 'ndjson':
                record = json.loads(decoded, parse_constant=reject_constant, object_pairs_hook=unique_object)
            else:
                values = next(csv.reader([decoded], strict=True))
                if len(values) != len(names):
                    raise ValueError('CSV field count mismatch')
                record = dict(zip(names, values))
            yield row, text, record, None
        except (ValueError, UnicodeError, csv.Error, RecursionError) as exc:
            yield row, text, None, f'malformed_record: {exc}'
