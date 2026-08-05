# Akasha Platform — User Manual

**Akasha** is AGEL's cross-platform intelligence system. It brings together project planning (Primavera P6), financials and procurement (SAP), transmission connectivity, and site quality data into one dashboard, with an AI assistant ("Ask Akasha") that can answer questions, draw charts on demand, and simulate schedule-recovery scenarios.

This manual documents the application **as it is built today**. Where a feature is still a placeholder or in progress, it is marked clearly rather than described as if it were live — so this manual stays trustworthy as the single source of truth for what users can actually do.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Roles & What Each Role Sees](#2-roles--what-each-role-sees)
3. [Platform Navigation Basics](#3-platform-navigation-basics)
4. [Executive Dashboard](#4-executive-dashboard)
5. [Project Workspace (Single-Project Deep Dive)](#5-project-workspace-single-project-deep-dive)
6. [PMAG Dashboard](#6-pmag-dashboard)
7. [Admin Dashboard](#7-admin-dashboard)
8. [Ask Akasha — AI Copilot](#8-ask-akasha--ai-copilot)
9. [Simulation Lab (AI What-If Planning)](#9-simulation-lab-ai-what-if-planning)
10. [Quality Module](#10-quality-module)
11. [Notifications](#11-notifications)
12. [Data Sync & Integrations](#12-data-sync--integrations)
13. [Known Gaps & Roadmap Items](#13-known-gaps--roadmap-items)
14. [Glossary](#14-glossary)
15. [FAQ / Troubleshooting](#15-faq--troubleshooting)

---

## 1. Getting Started

### 1.1 Accessing the platform

Open the Akasha landing page. You'll see an animated splash screen with two buttons:

- **Login** — opens the sign-in form (username/password)
- **Documentation** — opens a short in-app slide presentation introducing the platform

There's also a light/dark theme toggle (sun/moon icon) available on every screen.

### 1.2 Signing in

Enter your username and password and select **Login**. On success, you're taken straight to the dashboard for your role (see §2).

**Demo/UAT accounts** (for testing — these should be rotated to real credentials before any production rollout):

| Username | Password | Role | Lands on |
|---|---|---|---|
| `praveen` | `akasha@2026` | Executive | Executive Dashboard |
| `pmag_lead` | `akasha@2026` | PMAG | PMAG Dashboard |
| `site_lead` | `akasha@2026` | Projects | PMAG Dashboard *(placeholder — see §13)* |
| `tc_ordering` | `akasha@2026` | TC Ordering | PMAG Dashboard *(placeholder — see §13)* |
| `tc_stores` | `akasha@2026` | TC Stores | PMAG Dashboard *(placeholder — see §13)* |

> **Note:** the login screen also has two shortcut buttons, **"Login as CEO"** and **"Login as PMAG"** — these are demo conveniences for quick access during evaluation, not a security bypass of the real login system.

---

## 2. Roles & What Each Role Sees

Every user has one role, set by an administrator, which decides which dashboard you land on after login.

| Role | Dashboard | Status |
|---|---|---|
| **Executive** | Executive Dashboard — full portfolio view: KPIs, financials, procurement, risk, AI tools, decision center, reports | ✅ Fully built |
| **PMAG** | PMAG Dashboard — portfolio governance view: site monitoring, grid status, team, reports | ✅ Fully built |
| **Projects** | *(currently shows PMAG Dashboard)* | 🚧 Dedicated screen not yet built |
| **TC Ordering** | *(currently shows PMAG Dashboard)* | 🚧 Dedicated screen not yet built |
| **TC Stores** | *(currently shows PMAG Dashboard)* | 🚧 Dedicated screen not yet built |

**Important for admins:** today, role only controls *where you land after login*. It does not block you from typing a different dashboard's URL directly into the browser. Full role-based access enforcement is a planned hardening item, not yet in place — see §13.

---

## 3. Platform Navigation Basics

Both the Executive and PMAG dashboards share a common layout pattern:

- **Left sidebar** — icon rail grouping pages by category (Dashboard, Data & Insights, Platform Tools/AI, Administration). Collapsible.
- **Top header** — project selector, portfolio filter, phase filter (Ongoing / Commissioned / All), a **Sync All Data** button, an **Ask Akasha** button, a notification bell, and the theme toggle.
- **Tab content area** — the page changes based on what's selected in the sidebar; your last-used tab is remembered if you reload the page.

### Global controls (available almost everywhere)

| Control | What it does |
|---|---|
| **Project selector** | Switch the dashboard's focus to a single project, or view "All" |
| **Portfolio / Phase filters** | Narrow the view to Ongoing, Commissioned, or All projects |
| **Sync All Data** | Triggers a refresh from SharePoint, transmission, P6, SAP mapping, capacity, and quality (Pulse) sources, then reloads the dashboard |
| **Ask Akasha** | Opens the floating AI chat panel from anywhere |
| **Notification bell** | Shows system-generated alerts (see §11) |

---

## 4. Executive Dashboard

Reached at the **Executive Dashboard** route after logging in as an Executive. Organized into sidebar groups:

### 4.1 Dashboard group

| Page | What it shows | What you can do |
|---|---|---|
| **Overview** | Top-line KPIs: total projects, delayed/on-track counts, total MW, COD vs. TR MW, PO value vs. delivered value, average progress, a project-stage funnel, transmission network summary, and an AI-generated topline briefing | Click any KPI tile to open a detail modal; switch between Top/Low/Delayed project lists |
| **Capacity Overview** | Commissioned (COD) and Trial-Run (TR) capacity by financial year, solar vs. wind split, recent block-level milestones with gap-day tracking, per-project capacity breakdown, monthly trend sparklines | Drill into any KPI card or project |
| **Project 360** | Searchable card grid of every project with status pills (Critical / High Risk / Watchlist / Healthy / Completed) and risk-type filters (Material, Schedule, Vendor, Financial, Procurement, COD, Resource) | Search, filter by status/risk, click a card to open that project's full Project Workspace (§5) |
| **Quality** | Portfolio-wide Quality Command Center | See §10 |

### 4.2 Analysis tabs

| Tab | What it shows |
|---|---|
| **Portfolio Health** | Top-5 projects' schedule progress and overall logistics status |
| **P6 View** (Schedule) | Planned vs. actual duration per project; most-delayed projects by variance |
| **SAP View** (Financial) | Quarterly Planned vs. Actual CAPEX with cash-flow variance, a logistics funnel (At Port → In Transit → Delivered), top-vendor value breakdown |
| **Procurement Intelligence** | Vendor performance scorecard, active-PO count, vendor count, vendor-concentration risk %, full PO pipeline ledger |
| **Material Intelligence** | In-transit material quantity, active shipment count, delivered history, in-transit volume by destination, live shipment ledger |
| **Transmission Data Explorer** | Raw view of the Rajasthan network and Khavda transmission data, plus a mapping table cross-referencing each project's P6/SAP/transmission status. Has a manual **Refresh Data** button. |
| **Risk Command Center** | Schedule risks (>30-day slips) and financial risks (high-value PO concentration), an overall risk score, a probability-vs-impact heatmap, and ranked risk tables |
| **Predictive Analytics** | Forecasted schedule slippage based on current trend, with an AI confidence score |
| **Decision Center** *(sidebar: "Admin")* | Auto-generated recommended interventions (e.g., "Schedule Recovery Required," "Vendor Risk Review") with **Approve Intervention** / **Delegate to PM** buttons *(UI actions — not yet connected to a backend workflow, see §13)* |
| **Reports & Insights** | A formatted, printable Executive Brief document built from live data, with **PDF export** and **Share** |

### 4.3 Platform Tools (AI) group

| Page | What it does |
|---|---|
| **Ask Akasha** | Full-screen AI chat assistant — see §8 |
| **Briefing** | AI-generated Executive Briefing: topline summary, 3 key-action cards, and a deep-dive narrative |
| **Search** | Global search across projects, POs, vendors, and materials, with entity-type filters |
| **Project Map** | Interactive map of substations/sites, color-coded by voltage tier, with live weather overlay |
| **Knowledge Graph** | Visual, explorable map of the whole portfolio hierarchy (portfolio → project → vendor), colored by health status |
| **Simulation** | AI What-If Simulation Lab — see §9 |

---

## 5. Project Workspace (Single-Project Deep Dive)

Opened by clicking any project (from Project 360, Search, the Knowledge Graph, or a notification). Has its own internal tabs:

| Tab | What it shows |
|---|---|
| **Overview** | Progress, SPI/CPI gauges, key project facts |
| **Schedule** | Activity table — status, dates, resources; dates/status/resources can be edited inline by authorized users |
| **SAP Intelligence** | Financial breakdown for this project |
| **P6 Deep Dive** | Full Primavera schedule detail |
| **Transmission** | Transmission line status for this project |
| **Quality** | Project-scoped Quality/NC tracker — see §10 |

---

## 6. PMAG Dashboard

Reached after logging in as a PMAG user. Has its own header (Sync All Data, Ask Akasha, project search, notifications, theme toggle, Sign Out) and sidebar.

| Group | Page | What it shows |
|---|---|---|
| Dashboard | **Portfolio** | Summary KPIs (on-track/at-risk/delayed, avg completion, milestones due/overdue), projects grouped by EPS with RAG status, schedule-variance chart, critical-path panel, DPR tracker, connectivity status, alerts feed |
| Dashboard | **Site Monitoring** | Live telemetry: output MW, irradiance, wind speed, grid-sync %, asset map, equipment health/alerts. Filter by Region and Project Type; manual refresh. |
| Dashboard | **Grid Status** | Target ECOD date, substation readiness %, critical-path and connectivity data; **Generate Report** button |
| Data & Insights | **Briefing**, **Search**, **Project Map** | Same as the Executive Dashboard versions |
| Administration | **Reports** | Report library: reports generated this month, scheduled tasks, storage used, category filter, search, report table |
| Administration | **Team** | Personnel roster and governance: total personnel, active projects, avg allocation %, DPR submission rate, members table, activity log. **Add Member** / **Permissions** buttons are present in the UI *(not yet wired to a backend action, see §13)* |
| — | **Project 360** | Same master project directory as the Executive Dashboard |

---

## 7. Admin Dashboard

A separate control-center screen, reached at the `/admin` route.

| Tab | Status | What it does |
|---|---|---|
| **Project Mappings** | ✅ Fully built | The cross-reference table that ties together a Transmission project name, a P6 project name/ID, and an SAP SPV name/code/capacity, so the platform can join data across the three source systems. Search, **New Mapping** (side drawer form with autocomplete for unmapped P6 projects), **Edit**, and **Delete** (with confirmation). |
| **User Management** | 🚧 Placeholder | Not yet built. |
| **System Settings** | 🚧 Placeholder | Not yet built. |
| **Data Integrations** | 🚧 Placeholder (in this tab) | Not yet built here — but see §12, a more complete Data Integration Hub exists elsewhere in the codebase and is expected to move into this tab. |

---

## 8. Ask Akasha — AI Copilot

**Where to find it:** the full-screen "Ask Akasha" page in the sidebar, or the floating chat panel opened from the **Ask Akasha** button in the header (available on every dashboard).

### What you can ask

Plain-language questions about the portfolio — schedule status, delays, purchase orders and material fulfillment, vendor performance, transmission connectivity, or a specific project's health. Examples:
- "Which projects are delayed this month?"
- "What's blocking Project X's critical path?"
- "Show me vendor performance for the last quarter"
- "What material shortages do we have right now?"

### How to interact

| Feature | How it works |
|---|---|
| **Text chat** | Type your question, get a written answer sourced live from P6, SAP, and transmission data |
| **Deep Analysis toggle** | Switches the assistant into a more autonomous mode that can chain together multiple lookups (e.g., find the riskiest projects → pull their delayed activities → check material gaps → forecast a new completion date) to answer harder, multi-step questions |
| **Voice input** | Microphone button lets you dictate a question |
| **Image attachment** | Attach a photo (e.g., a site photo) and the assistant can analyze it as part of its answer |
| **Inline charts** | The assistant can draw a chart directly in the chat when it's the clearest way to answer — status donuts, delay/comparison bars, vendor or material bar charts, risk rankings |
| **Suggested follow-ups** | After each answer, clickable follow-up-question chips continue the conversation |
| **Thumbs up / down** | Rate any answer; a thumbs-down lets you provide a correction, which is stored to improve future answers |
| **Chat threads** | Keep multiple saved conversations; start a new chat, search past ones, or resume an old thread |
| **Source tags** | Each answer shows which systems (P6/SAP/TC) it drew from and how fresh that data is |

---

## 9. Simulation Lab (AI What-If Planning)

Reached via the **Simulation** sidebar tab, or the **Simulate** action on a notification, or from within Ask Akasha.

A guided 3-step wizard for planning schedule recovery on a delayed project:

1. **Detect** — auto-scans the selected project's risk level, schedule performance (SPI), and critical-path status, or you can describe a custom scenario
2. **Strategies** — the AI proposes recovery strategy options with adjustable parameters: recovery priority, live weather conditions (monsoon/wind severity, pulled automatically for the project's location), additional crew, and overtime
3. **Execute** — runs the simulation and produces a recovery timeline with a resolvable action checklist

Under the hood this uses Monte Carlo (PERT-distribution) scheduling math, so the output timeline reflects a range of likely outcomes rather than a single guess.

---

## 10. Quality Module

Tracks Non-Conformances (NCs) fed from the site quality system ("Pulse"). Available two ways:

- **Quality Command Center** (portfolio-wide, Executive Dashboard "Quality" tab)
- **Project Quality tab** (same tracker, scoped to one project, inside Project Workspace)

### What you'll see

- KPI cards: total/open NCs, critical-open count, closure rate, average resolution days, total debit amount
- A workflow funnel: **Raised → In Review (Execution Engineer) → In Review (Quality Inspector) → Approved**, with a Rejected branch
- Contractor breakdown
- A filterable, searchable NC list, showing who currently owns each item (Contractor / Execution Engineer / Quality Inspector)
- **Sync** button to pull the latest data from Pulse

---

## 11. Notifications

A bell icon in the header (available everywhere) shows system-generated alerts — schedule slips, risk triggers, and similar events.

| Action | What it does |
|---|---|
| Click a notification | Expand for detail |
| **AI Suggestion** | Fetches an AI-generated recommendation for that specific alert |
| **Simulate** | Jumps into the Simulation Lab, pre-loaded with that alert's project/issue |
| **Mark all read** | Clears the unread badge |
| **Thread** | Each notification has its own small comment thread for team discussion |

The unread badge refreshes automatically about once a minute.

---

## 12. Data Sync & Integrations

Akasha pulls data from five source systems: **Primavera P6** (schedule), **SAP** (financials/procurement/logistics), **Transmission** (connectivity), **SharePoint** (file exchange), and **Pulse** (site quality/NC).

- The **Sync All Data** button (in the header of both main dashboards) refreshes all sources and reloads the dashboard.
- Individual sources can also be refreshed on their own screens — e.g., the **Refresh Data** button on Transmission Data Explorer, or **Sync** on the Quality Command Center.
- The **P6 service-account credential** (used for the P6 integration) can expire; there is a dedicated panel for checking its status and updating the password so the sync doesn't silently fail. Today this lives in a Data Integration Hub component that is not yet wired into the main Admin screen — see §13.
- Data freshness is shown on request (e.g., Ask Akasha answers show "data as of…" tags).

---

## 13. Known Gaps & Roadmap Items

Being upfront about this keeps the manual trustworthy — these are real, current gaps, not hidden shortcomings:

| Area | Current state | What's needed |
|---|---|---|
| **Role-based access enforcement** | Role only decides your landing page after login; no route guard stops a user from navigating to another role's dashboard by URL | Add server-side authorization checks and frontend route guards per role |
| **Projects / TC Ordering / TC Stores dashboards** | All three roles currently land on the PMAG Dashboard as a placeholder | Build dedicated screens for each role |
| **User Management (Admin)** | Placeholder screen, no functionality | Build user CRUD, role assignment, password reset |
| **System Settings (Admin)** | Placeholder screen, no functionality | Define and build required settings |
| **Data Integrations (Admin tab)** | Placeholder in this specific tab; a more complete integration hub exists elsewhere in the app but isn't wired into this tab yet | Move/connect the existing Data Integration Hub here |
| **Decision Center approve/delegate buttons** | Present in the UI, not yet connected to a backend action | Wire to an approval workflow and audit trail |
| **Team "Add Member" / "Permissions" buttons (PMAG)** | Present in the UI, not yet functional | Connect to user/role management once built |
| **"v2.2" advanced chatbot pipeline** | Built in the backend (semantic validation, confidence scoring, health scoring) but no shipped screen calls it yet — the live chat uses the standard pipeline | Wire a UI to the v2.2 endpoints once validated, or retire it |
| **API authentication** | Simple token-based login, no formal session/token verification on protected routes yet | Move to a verified auth scheme (e.g., Azure AD/OAuth2) before production |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **P6** | Oracle Primavera P6 — the project scheduling system (activities, milestones, critical path) |
| **SAP** | Enterprise system for procurement, purchase orders, CAPEX, and inventory |
| **TC** | Transmission Connectivity — grid interconnection and evacuation data |
| **DPR** | Daily Progress Report — site-submitted daily execution updates |
| **PMAG** | Portfolio Management & Governance (team/role) |
| **SPV** | Special Purpose Vehicle — the legal project entity used to align SAP records to a project |
| **COD** | Commercial Operation Date |
| **TR** | Trial Run (date) |
| **SPI / CPI** | Schedule Performance Index / Cost Performance Index |
| **RAG status** | Red/Amber/Green health indicator |
| **NC** | Non-Conformance — a quality issue logged against site work |
| **EE / QI** | Execution Engineer / Quality Inspector — the two review stages an NC passes through |
| **Pulse** | The source system feeding the Quality/NC module |
| **EPS** | Grouping level used to organize projects in the PMAG portfolio view |

---

## 15. FAQ / Troubleshooting

**I logged in but I'm not sure what my role can see.**
Check §2 — your role determines your landing dashboard. If you believe you're in the wrong role, contact your administrator (User Management is not yet self-service).

**Data on my dashboard looks out of date.**
Use **Sync All Data** in the header to force a refresh from all source systems. If a specific source (e.g., Transmission) still looks stale, check that screen for its own refresh/sync button.

**Ask Akasha gave me a wrong or incomplete answer.**
Use the thumbs-down button on that answer and provide a correction — this is recorded and used to improve future responses. For complex, multi-step questions, try switching on **Deep Analysis** and re-asking.

**A button doesn't seem to do anything (e.g., "Approve Intervention," "Add Member").**
Check §13 — several buttons are currently UI-only placeholders for functionality still being built, not a bug in your session.

**The P6 sync is failing.**
The P6 integration uses a service-account credential that can expire. An admin should check the P6 credential status panel and update the password if needed (see §12).
