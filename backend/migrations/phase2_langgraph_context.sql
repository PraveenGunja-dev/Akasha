BEGIN;

ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS chat_engine VARCHAR;
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS deletion_status VARCHAR;

ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS status VARCHAR;
ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS run_id VARCHAR;
ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS engine VARCHAR;
ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS model VARCHAR;
ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS error_code VARCHAR;
ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

UPDATE chat_message SET status = 'completed' WHERE status IS NULL;
UPDATE chat_message SET completed_at = created_at WHERE completed_at IS NULL AND status = 'completed';
ALTER TABLE chat_message ALTER COLUMN status SET DEFAULT 'completed';
ALTER TABLE chat_message ALTER COLUMN status SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_chat_message_status ON chat_message (status);
CREATE INDEX IF NOT EXISTS ix_chat_message_run_id ON chat_message (run_id);

CREATE TABLE IF NOT EXISTS chat_run (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR NOT NULL UNIQUE,
    session_id VARCHAR NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    user_message_id INTEGER NOT NULL,
    assistant_message_id INTEGER NOT NULL,
    request_id VARCHAR NOT NULL,
    engine VARCHAR NOT NULL,
    model VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'pending',
    error_code VARCHAR,
    graph_checkpoint_id VARCHAR,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

ALTER TABLE chat_run ADD COLUMN IF NOT EXISTS model VARCHAR;

CREATE INDEX IF NOT EXISTS ix_chat_run_run_id ON chat_run (run_id);
CREATE INDEX IF NOT EXISTS ix_chat_run_session_id ON chat_run (session_id);
CREATE INDEX IF NOT EXISTS ix_chat_run_request_id ON chat_run (request_id);
CREATE INDEX IF NOT EXISTS ix_chat_run_status ON chat_run (status);
CREATE INDEX IF NOT EXISTS ix_chat_run_session_status ON chat_run (session_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_run_one_active_per_session
    ON chat_run (session_id)
    WHERE status IN ('pending', 'running', 'cancel_requested');

ALTER TABLE chat_run DROP CONSTRAINT IF EXISTS ck_chat_run_status;
ALTER TABLE chat_run ADD CONSTRAINT ck_chat_run_status CHECK (
    status IN ('pending', 'running', 'cancel_requested', 'completed', 'failed', 'cancelled', 'interrupted')
);

ALTER TABLE chat_message DROP CONSTRAINT IF EXISTS ck_chat_message_status;
ALTER TABLE chat_message ADD CONSTRAINT ck_chat_message_status CHECK (
    status IN ('running', 'completed', 'failed', 'cancelled', 'interrupted')
);

COMMIT;
