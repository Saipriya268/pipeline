import hashlib
import json
import re
from datetime import datetime, timezone
from .readers import FIELDS


def validate(record):
    if not isinstance(record, dict) or set(record) != set(FIELDS):
        raise ValueError('schema_mismatch: missing or unexpected fields')
    result = dict(record)
    for key in ('event_id', 'order_id', 'customer_id'):
        if not isinstance(record[key], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', record[key]):
            raise ValueError(f'invalid_required_id: {key}')
    if record['event_type'] not in ('purchase', 'refund'):
        raise ValueError('invalid_event_type')
    value = record['event_time']
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)', value):
        raise ValueError('invalid_event_time: ISO-8601 with timezone required')
    if value[-1] != 'Z' and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError('invalid_event_time: timezone offset out of range')
    try:
        timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        result['event_time'] = timestamp.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    except ValueError as exc:
        raise ValueError('invalid_event_time') from exc
    for key in ('quantity', 'unit_price_cents', 'discount_cents'):
        value = record[key]
        if isinstance(value, str) and re.fullmatch(r'\d{1,15}', value):
            value = int(value)
        if type(value) is not int:
            raise ValueError(f'invalid_integer: {key}')
        result[key] = value
    if not 1 <= result['quantity'] <= 10000:
        raise ValueError('quantity_out_of_range')
    if not 0 <= result['unit_price_cents'] <= 100000000:
        raise ValueError('price_out_of_range')
    gross = result['quantity'] * result['unit_price_cents']
    if not 0 <= result['discount_cents'] <= gross:
        raise ValueError('discount_exceeds_gross_or_negative')
    # Keep cents as integers throughout the calculation.
    net = gross - result['discount_cents']
    result['net_amount_cents'] = net if record['event_type'] == 'purchase' else -net
    # Compare business values only; a retry has a different run ID and file path.
    canonical = json.dumps(result, sort_keys=True, separators=(',', ':'))
    result['payload_sha256'] = hashlib.sha256(canonical.encode()).hexdigest()
    return result
