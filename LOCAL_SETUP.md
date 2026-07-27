# Akasha Complete Local Setup and Test Guide

## 1. Purpose

This runbook takes a coworker from a fresh clone of `feature/langgraph-refactor` to a
working local Akasha application with:

- Private server-backed chat sessions.
- LangGraph execution and PostgreSQL checkpoints.
- P6/SAP/TC/Pulse-backed tools when source data is available.
- Corrected project progress and SPI/CPI behavior.
- Chat cancellation and durable failed/cancelled states.
- Project Progress Report previews and PDF/DOCX downloads.
- Development authentication or optional Microsoft Entra authentication.

The commands target Windows PowerShell. Run repository commands from the directory stated
in each section.

## 2. What a Fresh Clone Does and Does Not Include

The repository contains application code, schema models, incremental SQL migrations, and
tests. It does not contain:

- `backend/.env` or any provider/source credentials.
- A production database dump.
- LangGraph checkpoint tables until the setup command is run.
- `node_modules`, Python virtual environments, or generated report files.
- Guaranteed current P6, SAP, TC, or Pulse business data.

Schema setup is enough to test authentication, sessions, lifecycle, greetings, and mocked
automated tests. Data-backed questions and reports require an approved database snapshot or
successful source synchronization.

## 3. Prerequisites

Install:

1. Git.
2. Python 3.12 (recommended project baseline).
3. Node.js 20.19+ with npm. Node 22.13+ is also suitable.
4. PostgreSQL with the `psql` client; PostgreSQL 16 or 17 is recommended.
5. Optional: DBeaver or pgAdmin for database inspection.

Verify:

```powershell
git --version
py -3.12 --version
node --version
npm --version
psql --version
```

If `npm.ps1` is blocked, use `npm.cmd` for npm commands. If `psql` is not on `PATH`, use
its full installation path or execute the SQL files through DBeaver/pgAdmin.

## 4. Clone the Feature Branch

```powershell
git clone --branch feature/langgraph-refactor --single-branch https://github.com/PraveenGunja-dev/Akasha.git
Set-Location Akasha
git status
git branch --show-current
```

Expected branch:

```text
feature/langgraph-refactor
```

Do not copy `.env`, `.venv`, `node_modules`, `dist`, report artifacts, or database files
from another developer.

## 5. Create PostgreSQL Database

Use a local PostgreSQL administrator account to create the database once:

```powershell
psql -h localhost -U postgres -d postgres -c "CREATE DATABASE akasha_local;"
```

If it already exists, PostgreSQL will report that fact; do not delete a database containing
data you need.

Test the connection:

```powershell
psql -h localhost -U postgres -d akasha_local -c "SELECT current_database(), current_user;"
```

## 6. Backend Virtual Environment

From the repository root:

```powershell
Set-Location backend
py -3.12 -m venv .venv
& ".venv\Scripts\Activate.ps1"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

If activation is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

All backend scripts, tests, and server commands should use `backend/.venv`. You can always
replace `python` below with `& ".venv\Scripts\python.exe"`.

## 7. Create `backend/.env`

Create `backend/.env`; it is ignored by Git. Never commit or share it.

### 7.1 Recommended Local Configuration: OpenRouter + LangGraph

```dotenv
# Application database used by SQLAlchemy.
DATABASE_URL=postgresql+psycopg2://postgres:<URL_ENCODED_PASSWORD>@localhost:5432/akasha_local

# Optional. Use a plain PostgreSQL DSN when checkpoints use another database.
# AKASHA_LANGGRAPH_CHECKPOINT_DSN=postgresql://postgres:<URL_ENCODED_PASSWORD>@localhost:5432/akasha_local

# Local-only identity selector. Never expose this mode to an untrusted network.
AKASHA_AUTH_MODE=development
AKASHA_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3510

# Activate the new graph for all local chat sessions.
AKASHA_CHAT_ENGINE=langgraph
AKASHA_LANGGRAPH_ROLLOUT_PERCENT=100

# Model provider. The selected model and every fallback must support tools/tool_choice.
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=<YOUR_OPENROUTER_KEY>
OPENROUTER_MODEL=<TOOL_CAPABLE_OPENROUTER_MODEL_ID>

# Set an approved ordered list, or leave empty to disable cross-model fallbacks.
OPENROUTER_FALLBACK_MODELS=
OPENROUTER_APP_URL=http://localhost:5173/akasha/
OPENROUTER_APP_NAME=Akasha

# Optional runtime tuning. Defaults are normally suitable.
AKASHA_MODEL_OUTPUT_TOKENS=2048
AKASHA_GRAPH_MAX_MODEL_CALLS=12
AKASHA_GRAPH_RECURSION_LIMIT=40
AKASHA_CHAT_RUN_STALE_SECONDS=600
AKASHA_LANGGRAPH_POOL_SIZE=10

# The provider/model context window is discovered automatically.
# Set this only as an intentional upper-bound override.
# AKASHA_MODEL_CONTEXT_WINDOW=32768

# Report MVP.
AKASHA_REPORT_AI_NARRATIVE=true
# AKASHA_REPORT_ARTIFACT_DIR=D:\akasha-report-artifacts

# Do not perform runtime schema changes during normal startup.
AUTO_SETUP_DB=false
```

Use only provider/model combinations approved for the sensitivity of project data. Free
model endpoints may log prompts or use data under provider-specific terms.

### 7.2 Ollama Alternative

The Ollama model must actually support native tool calls. Report AI narrative also requires
structured JSON; otherwise set `AKASHA_REPORT_AI_NARRATIVE=false` and the deterministic
narrative will be used.

```dotenv
AI_PROVIDER=ollama
OLLAMA_ENDPOINT=http://localhost:11434/v1
OLLAMA_MODEL=<INSTALLED_TOOL_CAPABLE_MODEL>
OLLAMA_SUPPORTS_TOOL_CALLING=true
OLLAMA_SUPPORTS_STRUCTURED_JSON=true
```

Do not set capability flags to `true` unless the selected model has been tested for them.

### 7.3 Azure OpenAI Alternative

```dotenv
AI_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=<AZURE_ENDPOINT>
AZURE_OPENAI_API_KEY=<AZURE_KEY>
AZURE_OPENAI_DEPLOYMENT_NAME=<DEPLOYMENT>
AZURE_OPENAI_MODEL=<UNDERLYING_MODEL_NAME>
AZURE_OPENAI_API_VERSION=<API_VERSION>
```

`AZURE_OPENAI_MODEL` should be the underlying model identity so context-window metadata can
be resolved when the deployment has a custom name.

### 7.4 Groq Alternative

```dotenv
AI_PROVIDER=groq
AKASHA_AI_API_KEY=<GROQ_KEY>
GROQ_MODEL=llama-3.3-70b-versatile
```

## 8. Create the Application Schema

This branch does not yet contain a complete Alembic baseline for a completely empty
database. Use the explicit local bootstrap below, then apply all reviewed incremental SQL
migrations. Do not use `alembic upgrade head`; there is no active migration tree for this
branch.

From `backend` with `.venv` active:

```powershell
python -c "from database import Base, engine; import models; Base.metadata.create_all(bind=engine); print('Application tables ready')"
```

This creates missing application tables from current SQLAlchemy metadata. It does not load
business data.

## 9. Apply Reviewed SQL Migrations

Still from `backend`, run these in order:

```powershell
psql -h localhost -U postgres -d akasha_local -v ON_ERROR_STOP=1 -f migrations/phase1_chat_ownership.sql
psql -h localhost -U postgres -d akasha_local -v ON_ERROR_STOP=1 -f migrations/phase2_langgraph_context.sql
psql -h localhost -U postgres -d akasha_local -v ON_ERROR_STOP=1 -f migrations/phase5_mvp_reports.sql
```

The migrations are designed to be rerunnable using `IF NOT EXISTS` and reviewed constraint
replacement where appropriate. They provide:

- Phase 1: session ownership and canonical chat metadata.
- Phase 2: engine/run/message lifecycle and cancellation state.
- Report MVP: temporary report-artifact records.

### 9.1 Apply the Application Migrations with DBeaver

Use this procedure instead of the three `psql` commands when DBeaver is preferred:

1. Start PostgreSQL and open DBeaver.
2. Create or open a PostgreSQL connection with:
   - Host: `localhost`
   - Port: `5432`
   - Database: `akasha_local`
   - Username: `postgres` or the application migration user
   - Password: the password used in `DATABASE_URL`
3. Click **Test Connection** and confirm it succeeds.
4. In **Database Navigator**, expand the connection and confirm the active database is
   `akasha_local`. Do not run these scripts against the default `postgres` database or an
   unrelated shared database.
5. Use **SQL Editor > Open SQL Script** (or the open-file button in the SQL editor) and open:

   ```text
   <repository>\backend\migrations\phase1_chat_ownership.sql
   ```

6. Check the connection selector in the editor toolbar again; it must show
   `akasha_local`.
7. Run the entire file with **Execute SQL Script**. In common DBeaver keymaps this is
   `Alt+X`; use the toolbar/script action if the shortcut differs. Do not use an action that
   executes only the statement under the cursor.
8. Confirm the **Output** panel ends without an error. The scripts control their own
   transaction where required; if DBeaver reports an error, stop and resolve it before
   continuing.
9. Repeat Steps 5-8 in this exact order for:

   ```text
   phase2_langgraph_context.sql
   phase5_mvp_reports.sql
   ```

10. In Database Navigator, right-click `Schemas > public > Tables` and select
    **Refresh**.

The expected application changes are:

- `chat_session`: tenant/user ownership, engine assignment, and deletion lifecycle columns.
- `chat_message`: request, visualization, run, engine, model, status, error, and completion
  columns.
- `chat_run`: durable pending/running/completed/failed/cancelled/interrupted turn state.
- `report_artifact`: owner-scoped temporary PDF/DOCX metadata and expiry.

### 9.2 Verify the Application Migrations in DBeaver

Open **SQL Editor > New SQL Script** on the `akasha_local` connection and execute:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('chat_session', 'chat_message', 'chat_run', 'report_artifact')
ORDER BY table_name;

SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (
    (table_name = 'chat_session' AND column_name IN ('owner_subject', 'tenant_id', 'chat_engine'))
    OR (table_name = 'chat_message' AND column_name IN ('status', 'run_id', 'engine', 'model'))
    OR (table_name = 'chat_run' AND column_name IN ('status', 'graph_checkpoint_id'))
    OR (table_name = 'report_artifact' AND column_name IN ('artifact_id', 'expires_at'))
  )
ORDER BY table_name, column_name;
```

The first result should contain all four application tables. The second should contain every
listed lifecycle/ownership column. Missing rows mean a migration was skipped, run against the
wrong database, or rolled back after an error.

## 10. Provision LangGraph Checkpoints

From `backend`:

```powershell
python scripts/setup_langgraph_checkpoint.py
```

Expected output:

```text
LangGraph checkpoint schema is ready.
```

This idempotently creates/upgrades LangGraph-owned tables such as `checkpoints`,
`checkpoint_blobs`, `checkpoint_writes`, and `checkpoint_migrations`. API startup checks
readiness but does not create them.

### 10.1 Important DBeaver Note for LangGraph Checkpoints

The four LangGraph checkpoint tables are not created by one of the repository SQL migration
files. Their schema is versioned by `langgraph-checkpoint-postgres`, so the supported setup
method is the Python command above. Do not manually invent or copy checkpoint DDL into
DBeaver because it can drift from the installed LangGraph package version.

You can keep DBeaver open while running the command in PowerShell. After the command prints
`LangGraph checkpoint schema is ready`:

1. Return to DBeaver.
2. Right-click `Schemas > public > Tables` and select **Refresh**.
3. Confirm these tables appear:
   - `checkpoint_migrations`
   - `checkpoints`
   - `checkpoint_blobs`
   - `checkpoint_writes`
4. Open a new SQL script on `akasha_local` and run:

   ```sql
   SELECT table_schema, table_name
   FROM information_schema.tables
   WHERE table_name IN (
       'checkpoint_migrations',
       'checkpoints',
       'checkpoint_blobs',
       'checkpoint_writes'
   )
   ORDER BY table_schema, table_name;
   ```

All four rows should be in the same PostgreSQL database/schema used by the backend checkpoint
DSN. If they appear in another database, correct `DATABASE_URL` or
`AKASHA_LANGGRAPH_CHECKPOINT_DSN`, then rerun the Python setup command.

## 11. Verify Database Readiness

Application connection:

```powershell
python -c "from sqlalchemy import text; from database import engine; c=engine.connect(); print(c.execute(text('SELECT 1')).scalar()); c.close()"
```

Expected: `1`.

Required tables:

```powershell
psql -h localhost -U postgres -d akasha_local -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('chat_session','chat_message','chat_run','report_artifact','checkpoints','checkpoint_blobs','checkpoint_writes') ORDER BY table_name;"
```

The same query can be pasted into a DBeaver SQL editor connected to `akasha_local`; no
command-line substitution is required.

## 12. Load Business Data

### 12.1 Recommended: Approved Snapshot

For repeatable chatbot testing, restore an approved sanitized PostgreSQL snapshot supplied by
the project owner. Never commit the dump. After restoring, rerun Sections 9 and 10 because the
snapshot may predate chat/report tables.

### 12.2 Source Synchronization

To synchronize live sources, obtain approved credentials/configuration for the relevant
services. Typical backend variables include:

- P6: `ORACLE_P6_BASE_URL`, `ORACLE_P6_AUTH_TOKEN`, and any required corporate CA/proxy.
- SAP/SharePoint: `SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`,
  `SHAREPOINT_CLIENT_SECRET`, `SHAREPOINT_SITE_URL`, and optional base folder.
- Pulse: organization-specific Pulse base configuration and NC/RFI endpoint values.
- TC: organization-specific Transmission Portal configuration required by `tc_sync.py`.

All sync API routes are authenticated. In development mode, trigger them from the
application's integration UI or send the same development identity headers used by the
frontend. Do not expose sync or credential-update routes outside a trusted development
environment.

### 12.3 Included SAP Loader

If the tracked sample input files are available and disposable local data is acceptable:

```powershell
python scripts/ingest_sap_data.py
```

The loader can clear and replace selected SAP tables. Never run it against a database whose
data must be preserved.

### 12.4 Confirm Useful Chat Data

```powershell
python -c "from database import SessionLocal; import models; d=SessionLocal(); print({'projects': d.query(models.P6Project).count(), 'activities': d.query(models.P6Activity).count(), 'po_rows': d.query(models.MTPOAmount).count(), 'tc_rows': d.query(models.TcNetworkEdge).count(), 'pulse_nc': d.query(models.PulseNC).count(), 'pulse_rfi': d.query(models.PulseRFI).count()}); d.close()"
```

If projects/activities are zero, data-backed P6 prompts and reports cannot return meaningful
results. The chatbot must report missing data rather than fabricate it.

## 13. Install Frontend Dependencies

Open a second PowerShell terminal at the repository root:

```powershell
Set-Location frontend
npm ci
```

Let `npm ci` complete; interrupting it can leave `node_modules` incomplete. No frontend
`.env` is needed for local development auth. Vite proxies `/akasha/api` to
`http://localhost:3510`.

## 14. Start the Backend

Terminal 1, from `backend` with `.venv` active:

```powershell
python run.py
```

Expected:

- API: `http://localhost:3510`
- Swagger: `http://localhost:3510/docs`
- Reload mode enabled.
- A startup log showing the resolved LangGraph model context window.
- No checkpoint-readiness or missing-provider error.

Do not use `AUTO_SETUP_DB=true` for normal startup. Explicit setup makes schema changes
reviewable and repeatable.

## 15. Start the Frontend

Terminal 2, from `frontend`:

```powershell
npm run dev
```

Open:

```text
http://localhost:5173/akasha/
```

Select a development CEO or PMAG identity. Local development mode does not use password
accounts. The old `/api/auth/seed` and local password login paths return HTTP 410 and should
not be used.

## 16. Optional Entra Setup

For real Microsoft Entra login, configure both sides:

Backend `backend/.env`:

```dotenv
AKASHA_AUTH_MODE=entra
ENTRA_TENANT_ID=<TENANT_ID>
ENTRA_CLIENT_ID=<API_CLIENT_ID>
ENTRA_AUDIENCE=<API_AUDIENCE>
ENTRA_CEO_APP_ROLE=Akasha.CEO
ENTRA_PMAG_APP_ROLE=Akasha.PMAG
```

Frontend `frontend/.env.local`:

```dotenv
VITE_AUTH_MODE=entra
VITE_ENTRA_CLIENT_ID=<SPA_CLIENT_ID>
VITE_ENTRA_TENANT_ID=<TENANT_ID>
VITE_ENTRA_API_SCOPE=api://<API_CLIENT_ID>/access_as_user
```

Restart both processes after environment changes. See `AUTHENTICATION_SETUP.md` for app
registration, redirect URI, scope, role, and group details.

## 17. Automated Verification

### 17.1 Backend

From `backend`:

```powershell
python -m unittest discover -s tests -v
python -m pip check
python evaluation/evaluate.py
```

The evaluator is explicitly provisional/synthetic and is not a production accuracy score.

### 17.2 Frontend

From `frontend`:

```powershell
node --experimental-strip-types --test tests/*.test.mjs
npm run build
```

The production build currently reports a known large-chunk warning; a successful build still
ends with `built`/success output.

## 18. Manual Chatbot Test Script

Use a project that exists in your database. The examples below use
`AGE26AL_S06A_FT_234MW_PPA` / `FY26-P18`; values can change after source synchronization.
Always compare results with the current database rather than treating this guide as a golden
answer.

### 18.1 General and Session Behavior

1. Ask: `Hello. What can you help me with?`
2. Confirm no operational tool is needed for the greeting.
3. Create a second conversation, return to the first, refresh the page, and reopen it.
4. Confirm the canonical transcript remains available.
5. Rename and delete a test conversation.

### 18.2 Corrected P6 Progress

Ask:

```text
What is the progress of AGE26AL_S06A_FT_234MW?
```

Verify:

- The alias resolves to the canonical project.
- Overall progress is P6 duration progress.
- Completed/total activity ratio is not substituted for duration progress.
- Completed, in-progress, and not-started counts match the database.
- P6 data date and last synchronization are disclosed when available.
- Null SPI/CPI remain unavailable.
- The assistant does not classify ahead/behind or health from a fabricated SPI.

Database cross-check:

```powershell
python -c "from database import SessionLocal; import models; d=SessionLocal(); p=d.query(models.P6Project).filter(models.P6Project.project_id=='FY26-P18').first(); print({'name':p.name,'progress_raw':p.duration_percent_complete,'completed':p.completed_activity_count,'in_progress':p.in_progress_activity_count,'not_started':p.not_started_activity_count,'spi':p.schedule_performance_index,'cpi':p.cost_performance_index,'data_date':p.data_date,'last_sync':p.last_synced_at} if p else 'Project not found'); d.close()"
```

### 18.3 Follow-Up Context and Activities

In the same conversation ask:

```text
What activities are in progress for that project?
```

Verify that the prior project is retained, actual activities are listed, pagination/limits
are disclosed when applicable, and no literal `<tool_call>` markup appears.

### 18.4 Risk and Missing Indicators

Ask:

```text
Why is ASEJ6PL_S07_FT_300MW_PPA project at risk?
```

Verify the project is resolved and every stated cause comes from returned tool facts. Missing
indicators must be disclosed. If the provider emits malformed textual tool syntax internally,
the graph should normalize a valid registered call or perform one tool-enabled retry rather
than exposing markup.

### 18.5 Visualization

Ask:

```text
Show an activity-status chart for AGE26AL_S06A_FT_234MW_PPA.
```

Verify an inline chart appears and the accompanying text describes only database-backed chart
data.

### 18.6 Cancellation

Start a broad analytical question and press Stop while it is running. Verify the turn becomes
cancelled, remains visible after reopening, and does not corrupt the next turn.

### 18.7 Project Progress Report MVP

Ask:

```text
Generate a Project Progress Report for AGE26AL_S06A_FT_234MW_PPA.
```

The first answer must be a preview showing:

- Canonical project and latest reporting cutoff.
- PDF and DOCX formats.
- P6, SAP, TC, Pulse, and freshness sections.
- Missing/unmapped source warnings.

Then reply:

```text
Confirm and generate the PDF and DOCX reports.
```

Verify:

- Both authenticated download buttons appear.
- PDF and DOCX download successfully.
- Both display the same deterministic metrics.
- The executive summary contains no model planning/reasoning text.
- Null SPI/CPI and missing sources remain explicit.
- The response states the 24-hour expiry.

Generated files are ignored by Git and normally stored under
`backend/report_artifacts/`.

## 19. Daily Startup

Backend terminal:

```powershell
Set-Location <PATH_TO_AKASHA>\backend
& ".venv\Scripts\Activate.ps1"
python run.py
```

Frontend terminal:

```powershell
Set-Location <PATH_TO_AKASHA>\frontend
npm run dev
```

After pulling updates:

```powershell
Set-Location <PATH_TO_AKASHA>
git switch feature/langgraph-refactor
git pull --ff-only origin feature/langgraph-refactor

Set-Location backend
& ".venv\Scripts\Activate.ps1"
python -m pip install -r requirements.txt
psql -h localhost -U postgres -d akasha_local -v ON_ERROR_STOP=1 -f migrations/phase1_chat_ownership.sql
psql -h localhost -U postgres -d akasha_local -v ON_ERROR_STOP=1 -f migrations/phase2_langgraph_context.sql
psql -h localhost -U postgres -d akasha_local -v ON_ERROR_STOP=1 -f migrations/phase5_mvp_reports.sql
python scripts/setup_langgraph_checkpoint.py

Set-Location ..\frontend
npm ci
```

Only rerun `npm ci` after a fresh clone or lock-file/dependency change.

## 20. Troubleshooting

### Backend says `DATABASE_URL` is missing

- Confirm the file is exactly `backend/.env`, not `.env.txt`.
- Run backend commands from `backend`.
- Confirm the URL password is URL-encoded.

### Phase 1 migration says `chat_session` does not exist

Run the Section 8 SQLAlchemy bootstrap first, then rerun migrations in order.

### LangGraph checkpoint storage is unavailable

- Confirm PostgreSQL is running.
- Confirm `DATABASE_URL` or `AKASHA_LANGGRAPH_CHECKPOINT_DSN` is PostgreSQL.
- Run `python scripts/setup_langgraph_checkpoint.py`.
- Verify the checkpoint tables in Section 11.

### OpenRouter startup fails while validating models

- Confirm the API key and exact model IDs.
- Confirm the primary and every fallback supports `tools` and `tool_choice`.
- Remove unavailable fallback IDs or set `OPENROUTER_FALLBACK_MODELS=`.
- Do not use `AKASHA_MODEL_CONTEXT_WINDOW` to hide an invalid/nonexistent model.

### `InvalidModelResponse` appears intermittently

The graph repairs empty, malformed native, and XML-like tool responses once. Restart after
pulling the latest branch. If it persists, capture the request ID and safe server log category;
do not log or paste full sensitive prompts/tool payloads.

### Frontend is blank or API requests return 404

- Open `http://localhost:5173/akasha/`, including the trailing application path.
- Confirm backend port 3510 and Vite port 5173.
- Confirm the Vite proxy is running through `npm run dev`.

### `npm run dev` fails after interrupted `npm ci`

Run `npm ci` again and let it finish before starting Vite.

### Chat sessions work but data answers are empty

Schema setup does not load P6/SAP/TC/Pulse facts. Check Section 12 counts and obtain an
approved snapshot or source credentials.

### Report preview works but generation fails

- Install `reportlab` and `python-docx` via `requirements.txt`.
- Apply `phase5_mvp_reports.sql`.
- Confirm the artifact directory is writable.
- Recreate a preview after backend restart; preview tokens are process-local and expire in
  one hour.

### Report download returns 404 or 410

- Ensure the same development/Entra user that generated it is signed in.
- Artifacts expire after 24 hours.
- Local files disappear if the artifact directory is manually cleared.

## 21. Security and Operational Notes

- Never commit `.env`, PATs, provider keys, passwords, source tokens, database dumps, or
  generated reports.
- Treat `AKASHA_AUTH_MODE=development` as local-only.
- Use approved provider privacy terms for project data.
- Keep TLS verification enabled; configure the corporate CA through standard CA-bundle
  environment variables.
- Do not use `AUTO_SETUP_DB=true` against shared/UAT/production databases.
- Do not claim measured business accuracy until a business-validated evaluation suite exists.
- The report MVP is synchronous and local-file based; it is not the full durable Phase 5
  worker architecture.

## 22. Architecture References

- Implemented design: `CHATBOT_ARCHITECTURE.md`
- Program roadmap and phase ledger: `CHATBOT_IMPLEMENTATION_PLAN.md`
- Entra setup: `AUTHENTICATION_SETUP.md`
- Historical pre-LangGraph path: `backend/ACTIVE_CHATBOT_PATH.md`
