BEGIN;

CREATE TABLE IF NOT EXISTS source_sync_state (
    source_system VARCHAR PRIMARY KEY,
    sync_version INTEGER NOT NULL DEFAULT 1,
    data_as_of TIMESTAMP,
    last_synced_at TIMESTAMP NOT NULL
);

COMMIT;
