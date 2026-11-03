SCHEMA = '''
CREATE TABLE IF NOT EXISTS customers (
 customer_id TEXT PRIMARY KEY
);
INSERT OR IGNORE INTO customers VALUES ('customer_001'),('customer_002'),('customer_003');
CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, source_file TEXT NOT NULL, source_sha256 TEXT,
 started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL,
 input_count INTEGER NOT NULL DEFAULT 0, accepted_count INTEGER NOT NULL DEFAULT 0,
 duplicate_count INTEGER NOT NULL DEFAULT 0, rejected_count INTEGER NOT NULL DEFAULT 0,
 committed_count INTEGER NOT NULL DEFAULT 0, failure_reason TEXT
);
CREATE TABLE IF NOT EXISTS order_events (
 event_id TEXT PRIMARY KEY, order_id TEXT NOT NULL,
 customer_id TEXT NOT NULL REFERENCES customers(customer_id),
 event_type TEXT NOT NULL CHECK(event_type IN ('purchase','refund')),
 event_time TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
 unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents BETWEEN 0 AND 100000000),
 discount_cents INTEGER NOT NULL CHECK(discount_cents>=0),
 net_amount_cents INTEGER NOT NULL, payload_sha256 TEXT NOT NULL,
 run_id TEXT NOT NULL REFERENCES runs(run_id), source_file TEXT NOT NULL,
 source_row INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rejects (
 run_id TEXT NOT NULL REFERENCES runs(run_id), source_file TEXT NOT NULL,
 source_row INTEGER NOT NULL, reason TEXT NOT NULL, raw_record TEXT NOT NULL,
 PRIMARY KEY(run_id,source_row)
);
CREATE INDEX IF NOT EXISTS events_customer_time ON order_events(customer_id,event_time);
CREATE VIEW IF NOT EXISTS customer_summary AS
 SELECT customer_id, COUNT(*) AS event_count, SUM(net_amount_cents) AS net_amount_cents
 FROM order_events GROUP BY customer_id;
'''
