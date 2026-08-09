BEGIN;

CREATE TABLE IF NOT EXISTS sap_project_scope (
    id SERIAL PRIMARY KEY,
    project_mapping_id INTEGER NOT NULL
        REFERENCES project_mapping(id) ON DELETE CASCADE,
    owner VARCHAR NOT NULL,
    match_kind VARCHAR NOT NULL,
    match_value VARCHAR NOT NULL,
    allocation_group VARCHAR NOT NULL,
    allocation_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    source_file VARCHAR NOT NULL,
    source_sheet VARCHAR NOT NULL,
    source_row INTEGER NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    upload_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_sap_project_scope_owner
        CHECK (owner IN ('SPV', 'AGEL', 'AGE6L')),
    CONSTRAINT ck_sap_project_scope_match_kind
        CHECK (match_kind IN ('wbs_prefix', 'plant_code')),
    CONSTRAINT ck_sap_project_scope_allocation_weight
        CHECK (allocation_weight > 0 AND allocation_weight <= 1),
    CONSTRAINT uq_sap_project_scope_rule
        UNIQUE (project_mapping_id, owner, match_kind, match_value)
);

CREATE INDEX IF NOT EXISTS ix_sap_project_scope_project_mapping_id
    ON sap_project_scope(project_mapping_id);

CREATE INDEX IF NOT EXISTS ix_sap_project_scope_match
    ON sap_project_scope(match_kind, match_value);

COMMIT;
