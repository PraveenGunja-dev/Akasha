
# Akasha local setup guide

This guide is for a developer who has just cloned the main branch and wants to run Akasha on a Windows laptop.

The repository has two applications:

- backend/: Python FastAPI API, SQLAlchemy models, and Alembic database migrations.
- frontend/: React + TypeScript application built with Vite.

The normal local setup runs the backend on port 3510, the Vite frontend on port 5173, and PostgreSQL on port 5432.

## 1. Clone the main branch

Open PowerShell or Command Prompt and run:

~~~powershell
git clone <repository-url> Akasha
cd Akasha
git switch main
git pull --ff-only origin main
~~~

Replace <repository-url> with the repository URL supplied by the project owner.

Confirm that the correct branch is checked out:

~~~powershell
git branch --show-current
git status
~~~

The branch should be main. Do not copy generated folders such as node_modules, Python virtual environments, or a .env file from another machine.

## 2. Install the required software

Install these applications before installing project dependencies:

1. Git - required to clone and update the repository.
2. Python 3.12 - used by the backend. Python 3.11 or newer may work, but Python 3.12 is the recommended local version for this project.
3. Node.js - install Node.js 20.19 or newer. Node.js 22.13+ or 24+ also satisfies the dependency requirements in the lock file. npm is included with Node.js.
4. PostgreSQL 17 - the database server. Use the default port 5432 unless another local PostgreSQL installation is already using it.
5. DBeaver Community - the database GUI used in this guide.

Optional:

- Ollama if local AI/chat functionality is required. The backend can start without Ollama, but AI requests need either a local Ollama server or credentials for another configured provider.
- VS Code or another editor for editing backend/.env and source code.

Check that the command-line tools are available:

~~~powershell
git --version
python --version
node --version
npm --version
~~~

If PowerShell blocks npm.ps1, use npm.cmd instead, for example npm.cmd --version and npm.cmd run dev.

## 3. Install and configure PostgreSQL

### 3.1 Install PostgreSQL

During PostgreSQL installation:

- Keep the PostgreSQL service enabled.
- Keep the default port as 5432.
- Keep the default administrative username as postgres.
- Choose a local password and remember it. This password is not defined by the repository.
The PostgreSQL password chosen during installation is the password used by the backend in DATABASE_URL and by DBeaver when connecting to PostgreSQL.

### 3.2 Create the Akasha database with DBeaver

Use DBeaver to create and verify the local PostgreSQL database.

1. Open DBeaver and select New Database Connection.
2. Select PostgreSQL.
3. Enter:
   - Host: localhost
   - Port: 5432
   - Database: postgres
   - Username: postgres
   - Password: The password chosen during PostgreSQL installation
4. Click Test Connection, then save the connection.
5. Open a SQL editor for the connection and run:

~~~sql
CREATE DATABASE akasha_local OWNER postgres;
~~~

6. Create a second DBeaver connection using database akasha_local, or edit the connection to use that database.

If the database already exists, do not run the CREATE DATABASE statement again.

## 4. Create the Python environment and install backend packages

All backend dependency installation, scripts, tests, and server commands must use
`backend/.venv`. Do not install Akasha dependencies into the system or user-level
Python environment. When automation cannot activate the environment, invoke
`backend/.venv/Scripts/python.exe` explicitly.

Open a new terminal at the repository root and run:

~~~powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

If py -3.12 is not available, use the installed Python executable:

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

If PowerShell refuses to activate the virtual environment, run this once as the current Windows user and then retry:

~~~powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
~~~

The backend must be run from the backend directory. This matters because the code loads backend/.env using the current working directory.

## 5. Install frontend packages

Open a second terminal at the repository root and run:

~~~powershell
cd frontend
npm ci
~~~

npm ci uses the committed package-lock.json and is the preferred command after a fresh clone. If PowerShell blocks npm scripts, use:

~~~powershell
npm.cmd ci
~~~

No frontend .env file is required for the normal local run. The Vite configuration in frontend/vite.config.ts proxies /akasha/api requests to http://localhost:3510.

## 6. Create the database schema

Make sure PostgreSQL is running and that backend/.env contains a working DATABASE_URL.

In the backend terminal, from the backend directory with the virtual environment active, run:

~~~powershell
alembic upgrade head
~~~

This applies the database migrations tracked in backend/alembic/versions/ and creates the tables in akasha_local. The migration history is loaded from backend/.env; do not edit the placeholder sqlalchemy.url in backend/alembic.ini for normal local setup.

You can confirm that the database connection works with:

~~~powershell
python -c "from sqlalchemy import text; from database import engine; print(engine.connect().execute(text('SELECT 1')).scalar())"
~~~

The command should print 1.

In DBeaver, refresh the akasha_local database and look under the public schema. You should see the application tables and an alembic_version table.

### 6.1 Prepare Phase 2 chat persistence

Run `backend/migrations/phase2_langgraph_context.sql` against the Akasha PostgreSQL
database using pgAdmin, DBeaver, or `psql`. This creates the application-owned
`chat_run` table and adds the Phase 2 lifecycle columns and indexes to the chat tables.

Then provision the separate LangGraph-owned checkpoint tables from the `backend`
directory. Use the project virtual environment explicitly:

~~~powershell
.\.venv\Scripts\python.exe scripts\setup_langgraph_checkpoint.py
~~~

The setup command requires `DATABASE_URL` or `AKASHA_LANGGRAPH_CHECKPOINT_DSN` to
reference PostgreSQL. `AKASHA_LANGGRAPH_CHECKPOINT_DSN` takes precedence when both are
configured. The selected database user must be allowed to create and migrate tables.
API startup does not run checkpoint DDL.

The command is idempotent and creates or upgrades these LangGraph tables in the selected
database's default schema, normally `public`:

- `checkpoint_migrations`
- `checkpoints`
- `checkpoint_blobs`
- `checkpoint_writes`

To verify the result in pgAdmin, open the database used by the selected connection string,
then refresh `Schemas > public > Tables`. The four checkpoint tables should be visible.
They can also be verified in the pgAdmin query tool:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name IN (
    'checkpoint_migrations',
    'checkpoints',
    'checkpoint_blobs',
    'checkpoint_writes'
)
ORDER BY table_schema, table_name;
~~~

Creating the LangGraph tables does not replace
`backend/migrations/phase2_langgraph_context.sql`; both setup steps are required before
enabling `canary` or `langgraph` chat traffic.

Keep the legacy engine active while validating the deployment:

~~~dotenv
AKASHA_CHAT_ENGINE=legacy
AKASHA_LANGGRAPH_ROLLOUT_PERCENT=0
~~~

The LangGraph context budget is resolved automatically from the selected model. Recognized
OpenAI/Azure models use LangChain model-profile metadata; OpenRouter, Ollama, and Groq use
their provider model metadata. `AKASHA_MODEL_CONTEXT_WINDOW` is optional and should only
be set as an explicit override for a custom deployment that cannot report its input limit.
Unknown limits fail LangGraph startup rather than silently assuming a potentially unsafe
window size. For Azure deployments with a custom deployment name, set `AZURE_OPENAI_MODEL`
to the underlying model name so its profile can be resolved.

### 6.2 OpenRouter model fallbacks

When `AI_PROVIDER=openrouter`, Akasha sends an ordered OpenRouter-native model fallback
list. OpenRouter tries the primary `OPENROUTER_MODEL` first and then the configured
fallbacks when a model is rate-limited, unavailable, moderated, or rejects the request.
The same `OPENROUTER_API_KEY` is used for every model.

The default fallback order is:

1. `google/gemma-4-31b-it:free`
2. `poolside/laguna-m.1:free`
3. `nvidia/nemotron-3-super-120b-a12b:free`

Override the order with a comma-separated value, or set an empty value to disable
cross-model fallbacks:

~~~dotenv
OPENROUTER_FALLBACK_MODELS=google/gemma-4-31b-it:free,poolside/laguna-m.1:free,nvidia/nemotron-3-super-120b-a12b:free
~~~

Startup validates that every configured model exists, supports `tools` and `tool_choice`,
and reports a context window. The conversation context budget uses the smallest window
across the primary and fallback models. OpenRouter is also instructed to route only to
endpoints that support all requested parameters.

The selected response model is stored on `chat_run.model` and `chat_message.model`.
After updating to a version containing this feature, rerun
`backend/migrations/phase2_langgraph_context.sql`; it adds these columns idempotently.

Security warning: the configured defaults are free endpoints. Their provider terms may
permit prompt/output logging or use for model improvement, and NVIDIA explicitly advises
against sending confidential information to its free endpoint. Do not enable these
fallbacks for sensitive project data without organizational privacy and security approval.
An OpenRouter account-wide credit or key-level rate limit can still affect every fallback;
model fallback primarily addresses model-specific and upstream-provider limits.

For a stable canary rollout, set `AKASHA_CHAT_ENGINE=canary` and increase
`AKASHA_LANGGRAPH_ROLLOUT_PERCENT` from 0 to 100. Setting
`AKASHA_CHAT_ENGINE=legacy` is the immediate rollback switch. Use
`AKASHA_CHAT_ENGINE=langgraph` only after checkpoint and configured-model smoke tests
pass. The client cannot select or override the engine.

### Alternative: let run.py create the database

backend/run.py contains an optional automatic setup path. If you have not created akasha_local manually, you can set:

~~~dotenv
AUTO_SETUP_DB=true
~~~

Then start the backend with python run.py. The script connects to the default postgres database, creates akasha_local if it does not exist, and performs automatic table/column setup. The PostgreSQL user must have permission to create databases.

For a predictable team setup, manual database creation plus alembic upgrade head is preferred. Do not run automatic setup against a shared or production database.

## 7. Start the backend

In the backend terminal:

~~~powershell
cd backend
.\.venv\Scripts\Activate.ps1
python run.py
~~~

Expected behavior:

- The backend listens on http://localhost:3510.
- Uvicorn reload mode is enabled, so code changes restart the server.
- The FastAPI API documentation is available at http://localhost:3510/docs.

Keep this terminal open. Stop the backend with Ctrl+C.

## 8. Seed local application users

The database schema does not automatically contain login users. After the backend is running, open another PowerShell window and run:

~~~powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:3510/api/auth/seed"
~~~

The endpoint is idempotent: existing users are skipped.

The local demo accounts defined by the main branch are:

| Username | Password | Role |
|---|---|---|
| praveen | akasha@2026 | Executive |
| pmag_lead | akasha@2026 | PMAG |
| site_lead | akasha@2026 | Projects |
| tc_ordering | akasha@2026 | TC Ordering |
| tc_stores | akasha@2026 | TC Stores |

These are demo credentials for local development only. Do not use them in a shared, UAT, or production environment. The seed endpoint should also be protected or removed before exposing the application outside a local machine.

## 9. Start the frontend

In the frontend terminal:

~~~powershell
cd frontend
npm run dev
~~~

If necessary on PowerShell:

~~~powershell
npm.cmd run dev
~~~

Open the URL printed by Vite. With the current repository configuration, the application path is normally:

    http://localhost:5173/akasha/

Use the seeded username and password to sign in. Keep both the backend and frontend terminals running at the same time.

The request flow is:

    Browser: http://localhost:5173/akasha/api/...
            -> Vite proxy
    Backend: http://localhost:3510/api/...
            -> PostgreSQL: localhost:5432/akasha_local

## 10. Optional: load the repository's sample SAP data

A fresh database contains the schema but not necessarily the business data needed to populate every dashboard. The main branch includes sample files under Data/ and a loader at backend/scripts/ingest_sap_data.py.

After running the migrations and while backend/.env is configured, run this from the backend directory:

~~~powershell
python scripts/ingest_sap_data.py
~~~

The script reads the sample Excel files from the repository's Data/ directory and loads selected SAP inventory, purchase-order, and material-document tables. It clears the existing records in those tables before loading, so do not run it against a database whose data must be preserved.

The repository does not include a general PostgreSQL dump that automatically fills every dashboard. SharePoint, Oracle P6, TC, and other integration data require the appropriate source files or credentials from the project owner.

The tracked Data/akasha.db file is an old SQLite data file and is not the PostgreSQL database used by the normal backend setup. Do not use it as the value of DATABASE_URL for this guide.

## 11. Daily startup after the first setup

After the first setup, the normal routine is:

**Terminal 1 - backend**

~~~powershell
cd <path-to-Akasha>\backend
.\.venv\Scripts\Activate.ps1
python run.py
~~~

**Terminal 2 - frontend**

~~~powershell
cd <path-to-Akasha>\frontend
npm run dev
~~~

Then open http://localhost:5173/akasha/.

To update the code later:

~~~powershell
cd <path-to-Akasha>
git switch main
git pull --ff-only origin main
~~~

After a dependency or migration change, repeat the relevant setup commands:

~~~powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
cd ..\frontend
npm ci
~~~

## 12. Common problems

### DATABASE_URL environment variable is not set

Check all of the following:

- The file is named exactly .env, not .env.txt.
- It is located at backend/.env.
- The command is being run from the backend directory.
- The line starts with DATABASE_URL=.
- The database password is correct and URL-encoded if necessary.

### connection refused or could not connect to server

PostgreSQL is probably stopped, using a different port, or blocked by another local installation. Start the PostgreSQL service and verify that the host and port are localhost and 5432.

### password authentication failed for user postgres

The password in backend/.env does not match the password assigned to the PostgreSQL postgres user. Test the same credentials in DBeaver first, then update DATABASE_URL.

### database akasha_local does not exist

Create the database in DBeaver, or set AUTO_SETUP_DB=true and start the backend as a PostgreSQL user with permission to create databases.

### Alembic cannot import database or cannot find the .env values

Activate the virtual environment and run Alembic from backend, not from the repository root:

~~~powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
~~~

### The frontend is blank or API calls return 404

Check that:

- The backend is running on port 3510.
- The frontend is running with npm run dev.
- The browser URL includes /akasha/.
- The backend terminal does not show import or database errors.

### Login says Invalid username or password

Run the seed command after starting the backend:

~~~powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:3510/api/auth/seed"
~~~

Then use one of the demo accounts listed above.

### AI/chat requests fail but the dashboards load

This usually means Ollama is not running, the configured model is missing, or the selected cloud provider credentials are absent. Check AI_PROVIDER, OLLAMA_ENDPOINT, and OLLAMA_MODEL in backend/.env, or ask the project owner for the required Azure/Groq credentials.

### Dashboards load but show little or no data

Database setup creates the schema; it does not guarantee that all business data has been loaded. Run the optional SAP loader for the included sample files, or obtain the approved data-sync credentials/files for SharePoint, P6, TC, and related integrations.

## 13. Security reminders

- Never commit backend/.env.
- Never paste passwords, API keys, SharePoint secrets, P6 tokens, or cloud credentials into this document or into the frontend.
- Use a separate local PostgreSQL password, not a production password.
- Treat the seeded demo accounts and /api/auth/seed endpoint as local-development-only functionality.
- Do not set AUTO_SETUP_DB=true against a shared or production database.
