CREATE TABLE IF NOT EXISTS requests (
 id TEXT PRIMARY KEY,
 update_id INTEGER UNIQUE NOT NULL,
 chat_id TEXT NOT NULL,
 box TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending',
 created INTEGER NOT NULL,
 run_id TEXT,
 outcome TEXT,
 message TEXT,
 notify_after INTEGER NOT NULL DEFAULT 0,
 notified INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS active_box ON requests(box) WHERE active=1;

CREATE INDEX IF NOT EXISTS pending_state ON requests(state,outcome);
CREATE INDEX IF NOT EXISTS pending_notify ON requests(notified) WHERE message IS NOT NULL;
