-- Phase 1: canonical user-owned chat history.
-- Run once against PostgreSQL before deploying Phase 1 application code.

ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS owner_subject VARCHAR;
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS tenant_id VARCHAR;
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS owner_role VARCHAR;
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS source VARCHAR NOT NULL DEFAULT 'chat';

ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS visualizations JSON;
ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS request_id VARCHAR;

CREATE INDEX IF NOT EXISTS ix_chat_session_owner_subject ON chat_session (owner_subject);
CREATE INDEX IF NOT EXISTS ix_chat_session_tenant_id ON chat_session (tenant_id);
CREATE INDEX IF NOT EXISTS ix_chat_session_owner_updated
    ON chat_session (tenant_id, owner_subject, updated_at);
CREATE INDEX IF NOT EXISTS ix_chat_message_request_id ON chat_message (request_id);

-- Existing unowned sessions intentionally remain inaccessible. Do not assign them
-- to an Entra user without an explicit, reviewed ownership migration.
