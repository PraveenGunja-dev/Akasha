# Akasha

Akasha is the project intelligence platform for Adani Green Energy's renewable
portfolio. It joins eight enterprise systems against one project identity and
shows the result as dashboards, an intelligence engine and an AI copilot. The
eight systems are Primavera P6, SAP, SharePoint, Transmission, Pulse quality,
E-Invoice, Spectra drone surveys, and capacity/mapping data.

| Layer | Stack |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind, ECharts, framer-motion, react-router |
| Backend | Python, FastAPI, SQLAlchemy, Uvicorn |
| Database | PostgreSQL |
| AI | Groq or Azure OpenAI (copilot); separate FastAPI service for ordering/priority predictions (Beta) |

---

## Repository layout

```
Akasha-main/
├── backend/                 FastAPI app
│   ├── main.py              App entry: routers, /akasha prefix, serves frontend/dist
│   ├── run.py               Start script: optional DB setup, then Uvicorn on :3510
│   ├── models.py            SQLAlchemy models (schema auto-migrates on start)
│   ├── auto_migrate.py      Creates tables / adds missing columns at start-up
│   ├── routers/             API routes, mounted at /api
│   ├── services/            Integrations (P6, SAP, SharePoint, Pulse, …) and logic
│   ├── engine/              Intelligence engine
│   ├── scripts/             Ingest, sync and maintenance scripts
│   └── requirements.txt
├── frontend/                React app (Vite, base path /akasha/)
│   ├── src/pages/           Top-level pages (CEODashboard, …)
│   ├── src/features/        One folder per module (modules/, modules_beta/, capacity/, …)
│   ├── src/components/      Layout and shared UI primitives
│   └── vite.config.ts       Dev server + API proxies
├── docs/                    Additional documentation
├── KT_HANDOVER.md           Full technical handover — read this next
├── USER_MANUAL.md           End-user guide
└── CLAUDE.md                Design system and engineering rules
```

---

## Prerequisites

| Tool | Version | Check |
| --- | --- | --- |
| Python | 3.12 | `python --version` |
| Node.js | 20.19+ (22 LTS recommended) | `node --version` |
| npm | 10+ | `npm --version` |
| PostgreSQL | 14+ with `psql` / `pg_restore` on PATH | `pg_restore --version` |
| Git | any recent | `git --version` |

On Windows, PostgreSQL's tools are usually in
`C:\Program Files\PostgreSQL\<version>\bin`. Add that folder to `PATH` if
`pg_restore` is not found.

---

## Quick start (local development)

Commands are shown for **Windows PowerShell**. bash/macOS equivalents are
given where they differ.

### 1. Clone

```powershell
git clone https://github.com/PraveenGunja-dev/Akasha.git
cd Akasha
```

### 2. Database

Create an empty database:

```powershell
psql -U postgres -c "CREATE DATABASE \"Akasha\";"
```

**Option A: restore a data dump (recommended).** The dumps in the repo root
(`dump.backup`, `latestakasha_dump.sql`, `aksha_new_10_oct.sql`, …) are
**pg_dump custom-format** files, even the ones named `.sql`. Restore them with
`pg_restore`, not `psql`. Use the most recent dump your team shares:

```powershell
pg_restore -U postgres -d Akasha --no-owner --no-privileges --verbose aksha_new_10_oct.sql
```

**Option B: start empty.** Skip the restore. The backend creates every table
on start-up, and you then load data with **Sync All Data** (needs integration
credentials).

### 3. Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1          # bash: source venv/bin/activate
pip install -r requirements.txt
```

If PowerShell blocks the activate script, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

Create **`backend/.env`**. It is git-ignored, so ask the team for the real
values. Minimum to run locally:

```ini
# Database
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/Akasha
AUTO_SETUP_DB=True            # create the DB if missing + migrate on start

# Auth (any long random strings locally)
JWT_SECRET=<random-string>
REFRESH_TOKEN_SECRET=<random-string>

# AI copilot: 'groq' or 'azure'
AI_PROVIDER=groq
AKASHA_AI_API_KEY=<groq-key>
```

The full list of keys, grouped by integration:

| Group | Keys |
| --- | --- |
| AI / LLM | `AI_PROVIDER`, `AKASHA_AI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME`, `AZURE_OPENAI_API_VERSION`, `OPENROUTER_API_KEY` |
| SharePoint (SAP files) | `SHAREPOINT_TENANT_ID`, `SHAREPOINT_SITE_URL`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET`, `SHAREPOINT_BASE_FOLDER`, `SHAREPOINT_SSL_VERIFY` |
| Oracle P6 | `ORACLE_P6_*` (base64 `username:password` tokens, URLs) |
| Auth | `JWT_SECRET`, `REFRESH_TOKEN_SECRET` |
| Database | `DATABASE_URL`, `AUTO_SETUP_DB` |
| Pulse (quality) | `PULSE_BASE_URL`, `PULSE_NC_ENDPOINT`, `PULSE_RFI_ENDPOINT`, `PULSE_CLIENT_ID`, `PULSE_CLIENT_SECRET`, `PULSE_TOKEN_URL` |
| E-Invoice | `EINVOICE_TOKEN_URL`, `EINVOICE_CLIENT_ID`, `EINVOICE_CLIENT_SECRET` |
| Spectra (drone) | `SPECTRA_BASE_URL`, `SPECTRA_API_KEY` |

Integrations you leave blank simply fail to sync. The dashboards still work on
whatever data is in the database.

Start the backend:

```powershell
python run.py
```

This runs on **http://localhost:3510** with auto-reload. On start it migrates
the schema and creates the default sign-in accounts (see
`backend/routers/auth.py`; ask the team for the credentials).

### 4. Frontend

In a **second terminal**:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173/akasha/** and sign in.

In dev, Vite proxies these paths (`frontend/vite.config.ts`):

| Browser path | Goes to |
| --- | --- |
| `/akasha/api/*` | Backend, `http://localhost:3510` |
| `/akasha/ai-api/*` | AI prediction service, `/api/ai/v1/*` (Ordering Schedule Beta only) |

### 5. AI prediction service (optional)

Only the **Ordering Schedule → Beta** forms (*Module Ordering & TC Delivery
Forecasting* and *Priority Prediction*) use it. It is a separate FastAPI
service. The proxy target is set in `vite.config.ts`, and you can override it
without editing the file:

```powershell
$env:AI_API_TARGET = "http://localhost:8000"; npm run dev
```

```bash
AI_API_TARGET=http://localhost:8000 npm run dev
```

See [`frontend/src/features/modules_beta/README.md`](frontend/src/features/modules_beta/README.md)
for the API contract and details.

---

## Everyday commands

| Task | Command (from) |
| --- | --- |
| Start backend | `python run.py` (`backend/`, venv active) |
| Start frontend | `npm run dev` (`frontend/`) |
| Type-check frontend | `npx tsc --noEmit -p tsconfig.json` (`frontend/`) |
| Bundle-check frontend | `npx vite build --logLevel error` (`frontend/`) |
| Lint frontend | `npm run lint` (`frontend/`) |
| Production build | `npm run build` (`frontend/`) → `frontend/dist` |
| Add a backend dependency | `pip install <pkg>` then add it to `requirements.txt` |
| Sync all integrations | **Sync All Data** in the header, or `POST /akasha/api/{sharepoint,tc,mapping,p6,capacity,pulse,einvoice}/sync` |

Run **both** frontend checks (type-check and bundle-check) before committing.
`tsc` misses some import errors that only the bundler catches.

---

## Production

1. Build the frontend:

   ```powershell
   cd frontend
   npm ci
   npm run build
   ```

   The build already raises Node's memory limit (`--max-old-space-size=8192`).
   It runs out of memory without it.

2. Run the backend. `main.py` serves `frontend/dist` itself, so one process
   serves both the UI and the API:

   ```powershell
   cd backend
   .\venv\Scripts\Activate.ps1
   python run.py
   ```

   The app is then at `http://<host>:3510/akasha/`. Put it behind your reverse
   proxy under `/akasha`. For the chat stream, keep response buffering off
   (`X-Accel-Buffering: no`).

3. For the Beta AI forms in production, route `/akasha/ai-api/*` to the AI
   service's `/api/ai/v1/*` on the reverse proxy, or build with
   `VITE_AI_API_BASE` set to the service URL.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `pg_restore: input file does not appear to be a valid archive` / `psql` errors on a `.sql` dump | The dumps are custom-format. Use `pg_restore`, not `psql -f`. |
| Backend can't connect to DB | Check `DATABASE_URL`, that PostgreSQL is running, and that the database exists (or set `AUTO_SETUP_DB=True`). |
| Frontend shows no data / 502s on `/akasha/api` | The backend is not running on port 3510. |
| Beta AI forms: "could not reach the service" | The AI service or tunnel is down, or `AI_API_TARGET` is stale. Restart `npm run dev` after changing it. |
| P6 data stale | P6 password expires every 45 days. Check `GET /akasha/api/p6/config-status`. |
| SAP data stale | Check that today's dated SharePoint folder exists and has files. |
| `npm run build` runs out of memory | Use `npm run build` (sets the heap size), not plain `vite build`. |
| PowerShell won't run `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

More triage steps are in [KT_HANDOVER.md §11](KT_HANDOVER.md).

---

## Further reading

- [KT_HANDOVER.md](KT_HANDOVER.md): architecture, project identity, every integration, operations runbook
- [USER_MANUAL.md](USER_MANUAL.md): what each screen does, for end users
- [CLAUDE.md](CLAUDE.md): design system, data-honesty rules, verified data facts
- [frontend/ARCHITECTURE.md](frontend/ARCHITECTURE.md): frontend structure
- [frontend/src/features/modules_beta/README.md](frontend/src/features/modules_beta/README.md): Ordering Schedule Beta and the AI forms

---

## Security notes

- Never commit `.env` files. `.gitignore` already excludes them.
- Database dumps contain live project data. Share them through approved channels, not public repos.
