# Akasha Platform — Knowledge Transfer & Handover Document

**Prepared for:** Incoming engineering / support team
**Repository:** `d:\Akasha_Platform` (branch `main`)
**Document date:** 7 September 2026
**Build history:** 181 commits, 8 June 2026 → 5 September 2026

---

## 1. What Akasha Is

Akasha is a **cross-platform intelligence system for AGEL's renewable-energy project portfolio**. It does one thing no single source system can do: it joins **eight independent enterprise systems** against **one canonical project identity**, then reasons over the joined data — with dashboards, an intelligence engine, and a tool-calling AI copilot.

Without Akasha, answering *"is Khavda Phase IV going to hit COD, and what's blocking it?"* means opening Primavera P6 for the schedule, SAP for POs and material, Pulse for quality NCs, the transmission portal for evacuation readiness, a SharePoint folder for yesterday's Excel dumps, and a drone-survey portal for what is actually built on site. Akasha answers it on one screen, and can explain the answer.

**Scale of the codebase**

| | |
|---|---|
| Backend | 192 Python files, ~36,600 lines (FastAPI) |
| Frontend | 79 TypeScript/TSX files, ~25,500 lines (React 19 + Vite) |
| Database | PostgreSQL, 31 tables |
| REST endpoints | ~115 across 19 routers |
| Source systems integrated | 8 |
| Projects under management | 64 canonical project mappings |

---

## 2. Architecture

### 2.1 Stack

| Layer | Technology |
|---|---|
| Backend | Python, **FastAPI**, SQLAlchemy ORM, Uvicorn |
| Database | **PostgreSQL** (schema auto-migrated on boot) |
| Frontend | **React 19**, TypeScript, Vite 8, Tailwind CSS 3, Zustand |
| Charts / Viz | ECharts, Recharts, D3, deck.gl, Leaflet, Three.js |
| AI / LLM | Ollama (local GPU), Azure OpenAI, Groq, OpenRouter — provider-switchable |
| Integrations | Microsoft Graph (MSAL), Oracle P6 REST, SAP BTP OData, REST APIs |
| Docs / export | ExcelJS, PyMuPDF, openpyxl, pandas |

### 2.2 Deployment topology

The whole platform ships as **one process**. FastAPI serves the API *and* the built React SPA:

```
                       ┌──────────────────────────────┐
   Browser ── /akasha ─▶│  FastAPI (Uvicorn)           │
                       │   ├─ /api/**  → 19 routers   │
                       │   └─ /*       → frontend/dist│──▶ PostgreSQL
                       └──────────────┬───────────────┘
                                      │ outbound sync
        ┌────────┬────────┬───────────┼──────────┬─────────┬──────────┐
     Oracle    Share-     SAP       Pulse    Transmission Spectra   LLM
       P6       Point   (Excel)  (BTP OData)   (Unada)   (drone)  provider
```

**Three deployment facts that will bite you if missed:**

1. **`root_path="/akasha"`** — the app sits behind a reverse proxy at `/akasha`. `AkashaPathRewriteMiddleware` in [main.py](backend/main.py) rewrites `/akasha/api/*` → `/api/*`. It is written as **pure ASGI middleware, not `@app.middleware`** — `BaseHTTPMiddleware` buffers the entire response body, which killed token-by-token SSE streaming in the chat endpoint. Do not "simplify" it back.
2. **Corporate proxy / SSL** — `main.py` monkey-patches `requests.Session.request` to force `verify=False` globally, because the corporate proxy breaks certificate verification against every external integration. This is deliberate; removing it breaks all eight integrations at once.
3. **Auto-migration on boot** — `auto_migrate.auto_upgrade_schema()` runs at import time, creating tables and adding missing columns dynamically. Alembic was removed on 18 July 2026 in favour of this. Adding a column to `models.py` is enough; no migration file needed.

### 2.3 Repository layout

```
Akasha_Platform/
├── backend/
│   ├── main.py               FastAPI app, middleware, router mounting, SPA serving
│   ├── models.py             All 31 SQLAlchemy models (843 lines)
│   ├── database.py           Engine + session factory
│   ├── auto_migrate.py       Schema auto-upgrade on boot
│   ├── run.py                Entrypoint — creates DB if absent, then serves
│   ├── slr_rules.py          Procurement business rules (see §9)
│   ├── routers/              19 REST routers (~115 endpoints)
│   ├── services/             Integration clients + heavy business services
│   ├── engine/               AI: ReAct agent, tools, intelligence modules
│   ├── scripts/              Ingestion + ops scripts
│   └── tasks/                Background AI suggestion task
├── frontend/
│   ├── src/features/         Feature modules (dashboard, projects, quality, …)
│   ├── src/pages/            Route-level pages (CEO, PMAG, Admin, Landing, Login)
│   ├── src/components/       Layout, dashboards, UI primitives
│   ├── src/services/         API clients
│   └── dist/                 Built SPA — served by FastAPI
├── Data/NEW31/               Source Excel/JSON drops for file-based ingestion
├── USER_MANUAL.md            End-user manual (roles, screens, workflows)
├── FIGMA_UI_PROMPT.md        UI/design specification
└── latestakasha_dump.sql     Latest DB dump (16 MB)
```

---

## 3. Canonical Project Identity — Read This First

**This is the single most important concept in the platform.** Everything else is downstream of it. It lives in [project_identity.py](backend/services/project_identity.py).

Five source systems each key projects differently:

| System | Key | Example |
|---|---|---|
| Canonical | `ProjectMapping.project_id` | `AHEJ5L`, `FY26-P16` |
| Surrogate | `ProjectMapping.id` | `1779` (transmission FK) |
| P6 | `P6Project.project_id` | `FY26-P16` |
| P6 internal | `P6Project.p6_object_id` | `5119` (activity FK) |
| SAP | WBS element prefixes | `H-9712-01-01-04` |
| SAP plant | `plant_code` | `9712` |
| Pulse | `project_name` (free text) | `MSEDCL PPA Ph-3` |

Before this module existed, every endpoint picked whichever key suited it, so the API exposed **six different "project ids"** — `project_id`, `mapping_id`, `project_name`, `p6_object_id`, `project_object_id`, and a bare name path segment. A client had to know which endpoint wanted which.

**The contract, and it is Postel's Law:** accept *any* identifier the platform has ever exposed, always answer with the canonical `project_id`, and state explicitly which source systems a project actually links to rather than returning silent empties. `ProjectIdentity.linked` returns the list of systems (`p6`, `sap`, `tc`, `pulse`) the project genuinely resolves into.

`ProjectMapping.project_id` is canonical because it is unique and non-null across all 64 mappings, and it is already what the frontend routes on.

**When debugging "why is data missing for project X", start here:** call `GET /api/v1/projects/{project_id}/identity` and see which systems the project is actually linked to.

---

## 4. Integrations — All Eight

Every integration follows the same shape: a service class in `backend/services/`, a sync endpoint in [sync.py](backend/routers/sync.py), and target tables in `models.py`. The **"Sync All Data"** button in the app header fires them in sequence.

### 4.1 Oracle Primavera P6 Cloud — Schedule

| | |
|---|---|
| Service | [p6_service.py](backend/services/p6_service.py) — 72 KB, the largest service |
| Base URL | `https://sin1.p6.oraclecloud.com/adani/p6ws/restapi` |
| Auth | OAuth token endpoint; `ORACLE_P6_OAUTH_TOKEN` is **base64 of `username:password`**. The token endpoint sometimes returns a raw JWT string instead of JSON — the client handles both shapes. |
| Endpoints used | `/project` (39 mapped fields), `/baselineProject`, `/activity`, `/wbs`, `/resourceAssignment`, `/activityRisk` |
| Sync | `POST /api/p6/sync` (full), `POST /api/p6/sync/{project_object_id}` (single) |
| Tables | `p6_project`, `p6_baseline_project`, `p6_activity`, `p6_wbs_node`, `p6_resource_assignment`, `p6_activity_risk` |
| **Write-back** | **P6 is the only two-way integration.** `update_project_in_p6()` and `update_activity_in_p6()` PUT changes back, with a bulk-array-then-single-object fallback because the P6 bulk endpoint is inconsistent. Resource assignments write back too. |

**Operational gotcha — the P6 password expires every 45 days.** There is a dedicated flow:

- `GET /api/p6/config-status` → days remaining; `is_expiring_soon` when ≤ 7 days
- `POST /api/p6/update-password` → re-encodes `username:password` to base64, writes it into `.env` **and** the live process environment, and stamps `ORACLE_P6_PASSWORD_LAST_UPDATED`

If P6 data goes stale silently, **check this first.** It is the most common operational failure on the platform.

### 4.2 SharePoint / Microsoft Graph — SAP file exchange

| | |
|---|---|
| Service | [sharepoint_service.py](backend/services/sharepoint_service.py) |
| Auth | Azure AD **client-credentials** flow via MSAL, scope `https://graph.microsoft.com/.default` |
| Site | `adaniltd.sharepoint.com/sites/AGEL-Automation` |
| Folder | `…/Bots/Akasha PlatForm/<DD.MM.YYYY>` — **date-stamped, resolved at runtime for today** |
| Sync | `POST /api/sharepoint/sync` — lists today's folder, downloads to `backend/downloads/`, then immediately runs `ingest_sap_data()` |

SAP has no direct API in this architecture. SAP raw extracts (MB51, MB52, ME2M/ME2J, ZIBDSESREP, ZPSPS007) are dropped daily into the dated SharePoint folder by an upstream bot, and Akasha pulls and ingests them. **If SAP data looks like yesterday's, check whether today's folder exists and has files** — an empty folder returns success with *"No files found to sync today."*

### 4.3 SAP (via Excel extracts) — Procurement, materials, inventory

| Extract | File | Target table | Content |
|---|---|---|---|
| ZPSPS007 (SLR) | `ZPSPS0071.xlsx` | `mt_poamount`, `mt_slr_data` | PO commitment + actual amounts by WBS |
| ME2J | `ME2J 2.xlsx` | supplements ZSPS, `mt_einvoice_po_lookup` | PO metadata |
| MB52 | `MB52_Khavda_Live_Inventry 2.xlsx` | `mt_inventory` | Live stock |
| MB51 | `MB51_Khavda_Mat_Consumption_221_222 4.XLSX` | `mt_materialdocument` | Material consumption (movement types 221/222) |
| Master | `AKASHA SAP MASTER FILE (2).xlsx` | drives WBS→project mapping | The join key source |

Ingestion is [ingest_sap_data.py](backend/scripts/ingest_sap_data.py). It handles SAP's formatting quirks explicitly: **trailing-minus negatives** (`100.00-` → `-100.00`), thousands separators, and pandas' `.0` float suffix on IDs.

`build_wbs_mapping()` reads the master file and extracts WBS codes from **six columns** — SPV / AGEL / AGE6L in both `H-xxxx` and numeric plant-code form — because different SAP extracts key on different ones. This is why the mapping logic looks over-elaborate. It is not.

### 4.4 Pulse (SAP BTP) — Quality: NCs and RFIs

| | |
|---|---|
| Service | [pulse_service.py](backend/services/pulse_service.py) |
| API | `https://pulse.cfapps.ap11.hana.ondemand.com/pulse-api` (OData) |
| Endpoints | `/Ncs`, `/Rfis` — paginated `$top` / `$skip`, page size 200, with `$expand` |
| Sync | `POST /api/pulse/sync` |
| Tables | `pulse_nc`, `pulse_rfi` |

**Volume matters here: RFIs outnumber NCs roughly 76:1 — over 43,000 RFI rows.** In [quality.py](backend/routers/quality.py), NC breakdowns are computed in Python but **RFI aggregates are grouped in SQL**, deliberately, so the Quality Command Center doesn't pull 43k rows into memory per request. Keep that pattern.

Pulse keys projects by free-text name, so `link_pulse_projects.py` reconciles them into the canonical mapping. Unseen Pulse projects are injected into the mapping rather than dropped.

### 4.5 Transmission (Unada / Powerback) — Grid connectivity

| | |
|---|---|
| Service | [tc_sync.py](backend/services/tc_sync.py) |
| Auth | `https://powerback-api.unada.in/api/v1/user/login` |
| Data API | `https://transmission-api-v3.unada.in` |
| Sync | `POST /api/tc/sync` (all — **runs in a background thread**), `POST /api/tc/sync/{project_id}` (single — **synchronous**) |
| Tables | `tc_project_entry`, `tc_network_node`, `tc_network_edge`, `tc_line_geometry` |

Two regions are modelled: **Khavda** and **Rajasthan**, served by `GET /api/khavda/network` and `/api/rajasthan/network`.

The per-project sync is deliberately **synchronous** — the Sync button triggers a page reload, and a background thread would have the page render stale data. The full sync is threaded because it is slow. Per-project sync runs fast: 2 topology calls + 2 targeted per-project calls.

**Note:** the frontend also talks to the transmission API *directly* via [apiClient.ts](frontend/src/services/apiClient.ts), caching the token in `localStorage`. This is the one integration with a browser-side path as well as a server-side one.

### 4.6 E-Invoice (SAP BTP UAT) — Invoice approval intelligence

| | |
|---|---|
| Auth | OAuth client-credentials — `EINVOICE_TOKEN_URL`, `EINVOICE_CLIENT_ID`, `EINVOICE_CLIENT_SECRET` (InvoiceChatBotService) |
| Sync | `POST /api/einvoice/sync` → [sync_einvoice_live.py](backend/scripts/sync_einvoice_live.py) |
| Tables | `einvoice_records`, `mt_einvoice_po_lookup` |
| API | `GET /api/einvoice/global` |

Invoices carry a work-order / PO number but no project. `mt_einvoice_po_lookup` — populated from **both ZSPS and ME2J, ZSPS winning on conflict** — resolves PO → project, which is how invoices land against the right project. BESS projects are inferred from `packageName` / `projectType` / `workDescription`, because the source system doesn't classify them.

Migrated from a static JSON file to live DB-backed sync on 5 August 2026.

### 4.7 Spectra Insights — Drone survey verification

| | |
|---|---|
| Service | [spectra_service.py](backend/services/spectra_service.py) — **async, `httpx`** |
| API | `https://dpr.spectra-insights.com/api` |
| Purpose | **DPR vs. Drone verification** — reported progress against what drones actually see on site |

Only **three sites are flown**: Baiya (1), Khavda (2), Bandha (3). Khavda is split into exactly four blocks. `resolve_spectra_project_id()` returns `None` for anything else, deliberately — **a wrong ID would report another site's drone progress against this project**, which is worse than reporting nothing.

Activity names are matched to drone metrics by regex (e.g. `mms\s*erection.*purlin|purlin` → `purlin_total` / `purlin_current`). Consumed by `engine/intelligence/drone_intel.py` and `engine/tools/drone_tools.py`.

### 4.8 LLM providers — the AI brain

Provider-switchable via `AI_PROVIDER`:

| Provider | Use |
|---|---|
| **Ollama** (local GPU) | Default for local development |
| **Azure OpenAI** | Production / VM deployment |
| **Groq** | Fast inference alternative |
| **OpenRouter** | Fallback |

Vision is supported — `analyze_image_context()` accepts base64 images, so a user can paste a screenshot into the copilot and ask about it.

---

## 5. Data Model — 31 Tables by Domain

| Domain | Tables |
|---|---|
| **Identity** | `project_mapping` (the canonical join table), `akasha_user` |
| **P6 / Schedule** | `p6_project`, `p6_baseline_project`, `p6_activity`, `p6_wbs_node`, `p6_resource_assignment`, `p6_activity_risk` |
| **SAP / Materials** | `mt_poamount`, `mt_slr_data`, `mt_inventory`, `mt_materialdocument`, `mt_trialrun`, `mt_einvoice_po_lookup` |
| **Transmission** | `tc_project_entry`, `tc_network_node`, `tc_network_edge`, `tc_line_geometry` |
| **Quality** | `pulse_nc`, `pulse_rfi` |
| **Compliance** | `statutory_compliance`, `epc_statutory_status`, `insurance_policy` |
| **Finance** | `einvoice_records` |
| **AI** | `chat_session`, `chat_message`, `chat_feedback` |
| **Platform** | `notification`, `notification_thread`, `metrics_cache` |

`project_mapping` is the hub — it carries `project_id`, `spv_plant_code`, `agel`, `age6l`, `module_wbs`, `cluster`, `category`, `capacity_mwac`, and commissioning state. Everything joins through it.

---

## 6. Backend API Surface

### 6.1 The `/api/v1` contract — use this for anything new

[v1.py](backend/routers/v1.py) and [v1_sources.py](backend/routers/v1_sources.py) are the **standardised surface**, and Swagger is deliberately filtered to show **only `/api/v1`** (`custom_openapi()` in `main.py`). Legacy routes still work unchanged, but new integrators get one contract:

- **One identifier** — `project_id`, resolved from any alias
- **One filter vocabulary** — `portfolio` / `phase` / `project` / `page`
- **One envelope** — `{ data, meta }`
- **Filters are never silently dropped** — `meta.filters_applied` states what the server actually scoped by

That last rule exists because of a real, painful bug: the UI sent `phase` to six endpoints and only one declared it, so FastAPI silently discarded it and the dashboard showed Ongoing KPIs beside unfiltered financials.

Related: `normalise_phase()` **defaults to `all`, not `ongoing`**. Defaulting to `ongoing` would mean an integrator calling `/api/v1/projects` silently receives 48 of 63 projects with nothing in the response saying so — the single most common cause of *"why is our data missing"* reports.

**v1 endpoints:** `/projects`, `/projects/{id}`, `/projects/{id}/identity`, `/coverage`, plus per-source reads: `/p6`, `/sap`, `/slr`, `/pulse`, `/transmission`, `/inventory`, `/material-documents`, `/trial-run`, `/einvoice`, `/activities`.

### 6.2 All 19 routers

| Router | Prefix | Purpose |
|---|---|---|
| `v1`, `v1_sources` | `/api/v1` | Standardised public surface |
| `dashboard` | `/api/dashboard` | Executive summary, search, knowledge graph, capacity overview (64 KB — largest router) |
| `projects` | `/api` | Master projects, Project 360, P6 detail + write-back, TC network |
| `ai` | `/api` | Chat (SSE streaming), briefing, Simulation Lab, project diagnostic |
| `ai_v2_2` | `/api` | Accuracy pipeline: validation, confidence, clarification, health score, semantic analysis |
| `intelligence` | `/api/intelligence` | Per-project + portfolio intelligence, insights, next steps, predictions, narrative |
| `quality` | `/api/quality` | NC/RFI overview, contractors, by-project, trends |
| `statutory` | `/api/statutory` | Compliance, EPC status, insurance, P6 approvals |
| `einvoice` | `/api/einvoice` | Invoice analytics |
| `financials`, `logistics` | `/api` | SAP financial + material views |
| `metrics` | `/api/metrics` | KPI time-series history |
| `notifications` | `/api/notifications` | Alerts, threads, AI suggestions, push-to-P6 |
| `pmag` | `/api/pmag` | PMAG governance dashboard |
| `mappings` | `/api/mappings` | Project mapping CRUD |
| `sync` | `/api` | All integration sync triggers + P6 credential management |
| `tc_router` | `/api` | Khavda / Rajasthan network |
| `auth` | `/api/auth` | Login, me, seed |

### 6.3 KPI history — reconstructed, not snapshotted

[metrics.py](backend/routers/metrics.py) is worth reading as a piece of design. The platform had no time series for any headline figure, so every KPI tile fell back to a proportion bar instead of a sparkline. **No snapshot table was added.** The underlying records are already timestamped, so monthly series are reconstructed directly:

| Metric | Derived from |
|---|---|
| `po_value` | `MTPOAmount.document_date`, cumulative |
| `open_ncs` | `PulseNC` created vs. approved — raised minus resolved |
| `total_projects` / `completed_projects` | `P6Project.start_date` / `finish_date`, cumulative |
| `portfolio_capacity` | `ProjectMapping.capacity_mwac`, cumulative at COD |

**`delayed_projects` is deliberately absent.** Delay is computed against the *current* baseline, so a historical value cannot be derived from stored records — only a real snapshot would give it. Rather than fabricate a plausible line, the key is omitted and the tile keeps its proportion bar. **Do not "fix" this by inventing the series.**

Series shorter than 4 points render as a proportion bar rather than a sparkline — the threshold is matched on both sides (`MIN_POINTS` / `MIN_SERIES_POINTS`).

---

## 7. The AI & Intelligence Engine

### 7.1 ReAct agent — the chat pipeline

[agent.py](backend/engine/agent.py) (44 KB) implements a true **ReAct (Reasoning + Acting) loop**. Rather than gathering all data upfront, it hands the LLM a tool catalogue and lets it decide what to call, read the results, and reason through multi-step questions.

**Deep Analysis is now the default for all chat.** The client-side toggle can no longer downgrade it — every question gets grounded tool access instead of the limited fast pipeline.

**Tool catalogue** (`engine/tools/`):

| Module | Tools |
|---|---|
| `portfolio_tools` | `resolve_project_id` (**always called first** for fuzzy names), `get_riskiest_projects`, `get_notifications` |
| `p6_tools` | project summary (SPI/CPI/float), critical activities, delayed activities, status breakdown, WBS tree |
| `sap_tools` | PO summary, material gaps, vendor performance, inventory, consumption |
| `tc_tools` | project lines, at-risk lines, network summary |
| `simulation_tools` | activity productivity, duration what-if, monsoon impact, material bottlenecks, forecast completion |
| `drone_tools` | Spectra drone progress |
| `weather_tools` | weather impact |
| `viz_tools` | `build_chart` — the agent emits **live ECharts specs** into the chat stream |

**Streaming:** `POST /api/chat` returns SSE with three event types — `token` (text), `visualization` (ECharts spec, rendered inline in the chat), and `metadata` (message id, `data_as_of`, latency, intent, sources, follow-up suggestions). Every message is persisted to `chat_message` with its intent type, project IDs, data domains, source tables and latency.

**Self-improving memory:** `POST /api/chat/feedback` stores user corrections in `chat_feedback`.

### 7.2 Intelligence Engine — the deterministic path

`engine/intelligence/` is **not** the LLM path. It is deterministic domain analysis, orchestrated by `core.py`, and it is **strictly read-only**:

```
get_project_intelligence(project_id)
  ├─ schedule_intel      P6 variance, float, critical path
  ├─ material_intel      POs, inventory, consumption gaps
  ├─ transmission_intel  evacuation readiness
  ├─ financial_intel     spend vs. commitment
  ├─ quality_intel       NC/RFI posture
  ├─ drone_intel         DPR vs. drone reality
  ├─ weather_intel       site weather impact
  ├─ risk_intel          cross-domain risk synthesis
  ├─ prediction_engine   forecasts
  ├─ action_engine       ranked next steps
  └─ narrative_engine    executive briefing prose
```

Insights are ranked (`_rank_insights`) and surfaced through `/api/intelligence/*`. `get_portfolio_intelligence()` runs `_quick_project_scan` across the portfolio to find hotspots.

### 7.3 Simulation Lab

`POST /api/simulation-lab` → `/strategies` → `/simulate` → `/execute` → `/report`. A guided what-if workflow: pick a scenario, generate mitigation strategies, simulate outcomes, execute actions, export a report. Backed by `monte_carlo.py` and `simulation_tools`.

### 7.4 The v2.2 accuracy pipeline

[ai_v2_2.py](backend/routers/ai_v2_2.py) plus `orchestrator_v2_2.py`, `accuracy_engines.py`, `intent_v2.py`, `response_formatter.py` — semantic validation, confidence scoring, clarification prompts, health scoring.

**Status: built and working in the backend, but no shipped screen calls it.** Live chat uses the standard pipeline. It should either be wired to a UI or retired — that decision is outstanding. Documented in `backend/CHATBOT_V2_2_*.md`.

---

## 8. Frontend

### 8.1 Routes

React Router with `basename="/akasha"`:

| Route | Screen |
|---|---|
| `/` | Landing |
| `/ceo-dashboard` | Executive Dashboard (the main product) |
| `/ceo-dashboard/project/:projectId` | Project Workspace |
| `/ceo-dashboard/knowledge-graph` | Knowledge Graph |
| `/pmag` | PMAG governance dashboard |
| `/projects`, `/tc-ordering`, `/tc-stores` | **Placeholders — all currently render PMAG** |
| `/admin/*` | Admin |

### 8.2 Executive Dashboard modules

Tab-driven, with the active tab persisted across reloads. Sidebar groups:

- **Dashboard** — Overview, Capacity Overview, Project 360
- **Data & Insights** — SAP Intelligence, E-Invoice Intelligence, Transmission, Quality, Approval, P6 & DPR
- **Platform Tools** — Project Map, Knowledge Graph, Simulation Lab
- **Administration** — Admin

Additional built modules reachable in code: Portfolio Health, Procurement Intelligence, Material Intelligence, Risk Command Center, Predictive Analytics, Decision Center, Reports & Insights, Executive Briefing, Smart Search, Portfolio Intelligence. Some are commented out of the sidebar rather than deleted.

**Global controls** (top header): project selector, portfolio filter, phase filter (Ongoing / Commissioned / All), **Sync All Data**, **Ask Akasha**, notification bell, theme toggle, user-guide download.

### 8.3 Architecture rules (enforced — see [ARCHITECTURE.md](frontend/ARCHITECTURE.md))

1. No monolithic pages · 2. Components ≤ 500 lines · 3. Pages ≤ 1000 lines · 4. Reuse before creating · 5. Separate UI / logic / API / state / types · 6. Independent feature modules · 7. Strict TypeScript · 8. Feature-based architecture.

Shared primitives live in `components/ui/primitives/`: `Card`, `ChartFrame`, `KPITile`, `Meter`, `Metric`, `Sparkline`, `Status`, `PageHeader`, `InfoTip`, plus `chartTheme.ts` for consistent light/dark charting. **Reuse these** — the design system depends on it.

**Build note:** `npm run build` sets `NODE_OPTIONS=--max-old-space-size=8192`. The build OOMs at the default heap size.

---

## 9. Business Rules You Must Not "Simplify"

These encode real domain decisions, each with a documented reason. Changing them changes the numbers executives see.

### 9.1 SLR / procurement rules — [slr_rules.py](backend/slr_rules.py)

Two rules decide whether an SLR (ZPSPS007) row counts as a purchase order:

1. **Document type must be `POrd` or `PReq`.** Blank-type rows are cost/budget lines, not procurement — Land Cost, Modules Supply (FOB), Piling, Financing Costs, site setup. Only 21 of 100 blank-type rows carry a PO document at all, and several hold large negative actuals (Land Cost −₹2,989 Cr, Modules Supply FOB −₹3,525 Cr) that would otherwise net against genuine spend.
2. **Description must not be an overhead or consolidated service line** — SPGS supply/services, PMC charges and margin, ISA charges. These are few but enormous: **60 of 4,119 rows carry 63.6% of gross actual spend (₹10,816 Cr of ₹17,009 Cr).** Leaving them in lets a handful of contract lines dominate every procurement figure.

Descriptions are matched as **case-insensitive prefixes, not substrings** — so "visa" or "misaligned" are not caught by the `ISA` rule by accident.

### 9.2 Progress calculation

Progress uses `actual_non_labor_units / baseline_non_labor_units` strictly, with `SummaryAtCompletionNonLaborUnits` as the denominator source, falling back to duration percent complete only when budget labor units are zero. This was tightened repeatedly (17–18 July 2026) — the earlier fallbacks were producing wrong numbers.

### 9.3 RAG classification (PMAG)

Schedule variance in days: `≥ 0` green · `≥ −7` amber · `< −7` red.

### 9.4 Other rules worth knowing

- **EVM** — `calculate_dynamic_evm` / `build_evm_index` in `project_service.py`
- **Portfolio filtering** tolerates split words across cluster and category names, and URL-decodes `+` as space
- **Transmission edge filtering** by KPS via `filter_tc_edges_by_kps`
- **Trial-run vs. COD discrepancy** detection — `check_trial_cod_discrepancy()` raises notifications automatically

---

## 10. Notifications & Workflow

`notification` + `notification_thread` power an alert feed generated from P6 sync (COD discrepancies), AI analysis, and project events.

| Endpoint | Purpose |
|---|---|
| `GET /api/notifications` | Feed (unread badge refreshes ~once a minute) |
| `POST /{id}/read`, `/read-all` | Read state |
| `POST /{id}/action` | Action status |
| `GET /{id}/ai-suggestion` | LLM-generated recommended action (`tasks/ai_suggestion_task.py`) |
| `GET` / `POST /{id}/thread` | Threaded discussion on an alert |
| `POST /{id}/push` | **Push the resolution back into P6** |

That last one closes the loop: an alert raised from a P6 discrepancy can be discussed, resolved, and written straight back to P6.

---

## 11. Operations Runbook

### 11.1 Running it

```bash
# Backend
cd backend
source venv/bin/activate      # Windows: venv\Scripts\activate
python run.py                 # creates DB if absent, auto-migrates, serves

# Frontend (development)
cd frontend
npm install
npm run dev

# Frontend (production — output is served by FastAPI)
npm run build                 # → frontend/dist
```

`run.py` connects to the `postgres` database with `AUTOCOMMIT` to issue `CREATE DATABASE` if the target doesn't exist, then starts Uvicorn.

### 11.2 Environment configuration (`backend/.env`)

Grouped and commented in the file itself:

| Group | Keys |
|---|---|
| 1. AI / LLM | `AI_PROVIDER`, `OLLAMA_ENDPOINT`, `OLLAMA_MODEL`, `AKASHA_AI_API_KEY` (Groq), `AZURE_OPENAI_*`, `OPENROUTER_API_KEY` |
| 2. SharePoint | `SHAREPOINT_TENANT_ID`, `_SITE_URL`, `_CLIENT_ID`, `_CLIENT_SECRET`, `_BASE_FOLDER` |
| 3. Oracle P6 | `ORACLE_P6_OAUTH_TOKEN`, `_AUTH_TOKEN`, `_TOKEN_URL`, `_BASE_URL`, `_PASSWORD_LAST_UPDATED` |
| 4. Auth | `JWT_SECRET`, `REFRESH_TOKEN_SECRET` |
| 5. Database | `DATABASE_URL`, `AUTO_SETUP_DB` |
| 6. Quality / Invoice | `PULSE_BASE_URL`, `PULSE_NC_ENDPOINT`, `PULSE_RFI_ENDPOINT`, `EINVOICE_TOKEN_URL`, `EINVOICE_CLIENT_ID`, `EINVOICE_CLIENT_SECRET` |
| 7. Drone | `SPECTRA_BASE_URL`, `SPECTRA_API_KEY` |

`.env.uat` holds the VM Azure OpenAI overrides. **Secrets live in `.env` files, not in the repo — keep it that way.**

### 11.3 Sync sequence

`Sync All Data` runs: SharePoint (→ SAP ingest) → Transmission → P6 → Mapping → Capacity → Pulse → E-Invoice.

Individual triggers: `POST /api/{sharepoint|p6|tc|mapping|capacity|pulse|einvoice}/sync`.

### 11.4 Useful scripts (`backend/scripts/`)

| Script | Use |
|---|---|
| `vm_emergency_sync.py` | **Full recovery sync on the VM** — bypasses normal flow, adds columns, populates transmission phase/node data. Your break-glass tool. |
| `ingest_sap_data.py` / `ingest_slr_data.py` | SAP Excel ingestion |
| `ingest_statutory.py` | Statutory status, EPC BOCW/CLRA/GST, insurance master |
| `ingest_einvoice.py` / `sync_einvoice_live.py` | E-Invoice |
| `sync_perfect_mapping.py` | Rebuild project mappings from `perfect_mapping.json` (wipes TC tables first to avoid FK violations) |
| `deduplicate_mappings.py` | Fix duplicate project mappings |
| `link_pulse_projects.py` | Reconcile Pulse free-text project names |
| `sync_capacity_milestones.py` | Capacity milestones (includes wind MW-per-WTG multipliers) |
| `export_schema_docs.py` / `build_api_doc.py` | Regenerate schema + API documentation |

### 11.5 Triage guide

| Symptom | Check |
|---|---|
| P6 data stale | `GET /api/p6/config-status` — **the password expires every 45 days** |
| SAP data stale | Does today's dated SharePoint folder exist, and does it have files? |
| A project shows empty data | `GET /api/v1/projects/{id}/identity` → which systems is it actually linked to? |
| Filters seem ignored | Read `meta.filters_applied` in the v1 response |
| Duplicate projects | `deduplicate_mappings.py` |
| Chat not streaming | Confirm the ASGI middleware wasn't converted to `BaseHTTPMiddleware`; check `X-Accel-Buffering: no` survives the proxy |
| SSL errors on integrations | Confirm the `requests` monkey-patch in `main.py` is intact |
| Frontend build OOM | `NODE_OPTIONS=--max-old-space-size=8192` |
| Everything broken on the VM | `vm_emergency_sync.py` |

---

## 12. Existing Documentation

| Document | Contents |
|---|---|
| [USER_MANUAL.md](USER_MANUAL.md) | 15-section end-user manual — roles, every screen, workflows, glossary, FAQ |
| [ARCHITECTURE.md](frontend/ARCHITECTURE.md) | Frontend rules and structure |
| `backend/engine/DATA_DICTIONARY.md` | Field-level data dictionary |
| `backend/engine/ACCURACY_IMPROVEMENTS.md` | Chatbot accuracy work |
| `backend/engine/CHATBOT_ENHANCEMENT_GUIDE.md` | Chatbot design |
| `backend/CHATBOT_V2_2_*.md` | v2.2 delivery, integration, exec summary, quick reference |
| `backend/Akasha_API_v1_Reference.docx` | API reference |
| `Akasha_Data_Schema.docx` / `.xlsx` | Data schema |
| `FIGMA_UI_PROMPT.md` | UI / design specification |
| `brd.txt` / `sow.txt` | Business requirements & scope of work |

---

## 13. Known Gaps — Stated Honestly

These are real and current, and should be inherited with eyes open.

| Area | Current state | What's needed |
|---|---|---|
| **Role-based access enforcement** | Role only decides the landing page. No route guard stops a user typing another role's URL | Server-side authorization + frontend route guards |
| **API authentication** | Login issues a `secrets.token_hex(32)` token; **protected routes do not verify it**. Passwords are plain unsalted SHA-256 | Move to Azure AD / OAuth2 with real token verification before production. **Top hardening item.** |
| **Projects / TC Ordering / TC Stores dashboards** | All three land on PMAG as a placeholder | Build dedicated screens |
| **Admin: User Management & System Settings** | Placeholder screens | Build user CRUD, role assignment, password reset |
| **Admin: Data Integrations tab** | Placeholder; a fuller `DataIntegrationHub` exists but isn't wired in | Connect the existing hub |
| **Decision Center approve/delegate** | Buttons present, no backend action | Wire to an approval workflow + audit trail |
| **PMAG Add Member / Permissions** | Buttons present, not functional | Connect once user management exists |
| **v2.2 chatbot pipeline** | Fully built backend, no UI calls it | Wire a UI or retire it |
| **PMAG DPR submission tracker** | Partly mock data | Connect to a real DPR source |
| **CORS** | `allow_origins=["*"]` | Restrict before production |
| **Repo hygiene** | ~15 `scratch_*` / `_*.py` files, several `all_edits.json` / `extracted_*.json` artefacts, and duplicate `project_service_profile{,2}.py` | Clean up — they are dead weight, not dependencies |

---

## 14. Suggested KT Session Plan

**Session 1 — Concepts (60 min).** §1 What it is → §2 Architecture → **§3 Canonical Identity (spend real time here)** → §5 Data model. Then walk the running app: Executive Dashboard → Project 360 → a single Project Workspace.

**Session 2 — Integrations (90 min).** §4, one system at a time. For each: open the service file, trace the sync endpoint, look at the target table, run the sync. Do **P6** and **SharePoint→SAP** hands-on, since they cause the most operational issues.

**Session 3 — AI & Intelligence (60 min).** §7. Read the `TOOLS` array in `agent.py`, then run live chat questions and watch which tools fire. Contrast with the deterministic `engine/intelligence/` path.

**Session 4 — Frontend (60 min).** §8. Component primitives, feature structure, the architecture rules. Make one small change end-to-end and build it.

**Session 5 — Operations (60 min).** §9 business rules → §11 runbook → §13 gaps. Do a full `Sync All Data`, rotate the P6 password on a test credential, and walk the triage table.

**First tasks for a new joiner, in order:**

1. Get it running locally against the DB dump (`latestakasha_dump.sql`).
2. Trace one project end-to-end: `/api/v1/projects/{id}/identity` → each source endpoint → the Project Workspace screen.
3. Run each of the eight syncs and read the logs.
4. Pick one item from §13 — the Admin Data Integrations wiring is the smallest genuinely useful one.

---

## 15. Build Timeline

| Period | Work delivered |
|---|---|
| **Jun 2026** | Foundation — deployment setup, SharePoint auto-ingest, DB auto-create, P6 integration, core dashboards |
| **Jul 2026** | Pulse quality integration; project mapping overhaul (`perfect_mapping`); progress-formula corrections; Alembic removed for auto-migration; portfolio/phase filtering; wind project support; Chatbot v2.2 accuracy engine; AICopilot rewrite; Simulation Lab |
| **Aug 2026** | E-Invoice migrated to live DB sync; ECharts analytics; transmission viewer; SLR business rules; RFI data surfaced in Quality; mapping deduplication; live notifications backend; **Intelligence Engine + dashboard**; user guide shipped |
| **Sep 2026** | Swagger filtered to v1; Statutory Compliance module; CEO Dashboard refinements; Schedule Intelligence redesign with RFI integration; Approvals tab |

---

*Prepared as the handover record for the Akasha Platform. The authoritative detail always lives in the code — this document tells you where to look and, more usefully, **why** things are the way they are.*
