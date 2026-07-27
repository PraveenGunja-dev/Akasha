BEGIN;

CREATE TABLE IF NOT EXISTS report_artifact (
    id SERIAL PRIMARY KEY,
    artifact_id VARCHAR NOT NULL UNIQUE,
    session_id VARCHAR NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    owner_subject VARCHAR NOT NULL,
    tenant_id VARCHAR NOT NULL,
    project_id VARCHAR NOT NULL,
    report_type VARCHAR NOT NULL,
    format VARCHAR NOT NULL,
    file_path VARCHAR NOT NULL,
    filename VARCHAR NOT NULL,
    mime_type VARCHAR NOT NULL,
    checksum_sha256 VARCHAR NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_report_artifact_artifact_id ON report_artifact (artifact_id);
CREATE INDEX IF NOT EXISTS ix_report_artifact_session_id ON report_artifact (session_id);
CREATE INDEX IF NOT EXISTS ix_report_artifact_owner_subject ON report_artifact (owner_subject);
CREATE INDEX IF NOT EXISTS ix_report_artifact_tenant_id ON report_artifact (tenant_id);
CREATE INDEX IF NOT EXISTS ix_report_artifact_project_id ON report_artifact (project_id);
CREATE INDEX IF NOT EXISTS ix_report_artifact_expires_at ON report_artifact (expires_at);

COMMIT;
