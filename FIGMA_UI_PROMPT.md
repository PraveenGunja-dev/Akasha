# Akasha Platform — UI Redesign Prompt (for Figma / Figma Make / any design AI)

> **How to use this file**
> - **Master Prompt** (§A) = paste this whole block first. It gives the AI the product, the people, the vocabulary, and the taste rules.
> - **Screen Prompts** (§B) = paste one at a time, after the master prompt, to generate each screen.
> - **Refinement Prompts** (§C) = use these to push back when output looks generic.
> Figma Make works best one screen per request. Don't ask for 20 screens in one shot.

---

# §A — MASTER PROMPT (paste this first)

## Your role

You are a senior product designer specialising in **enterprise intelligence platforms** — the category of Bloomberg Terminal, Palantir Foundry, Linear, Vercel Observability, Stripe Dashboard. You are not designing a marketing site, a startup landing page, or an "AI chat app". You are designing the operating surface that a **billion-dollar renewable energy portfolio is run from**.

Design for a user who stares at this screen for six hours a day and makes capital decisions from it. Density, hierarchy and trust matter more than delight. Every pixel must justify itself with information.

## The product

**Akasha** is the cross-platform intelligence system for **AGEL (Adani Green Energy Ltd)**. It fuses five previously disconnected enterprise source systems into a single decision surface, with an AI copilot layered on top.

**The five source systems it unifies:**

| System | What it contributes |
|---|---|
| **Primavera P6** | Project schedule — activities, milestones, critical path, planned vs actual duration, SPI |
| **SAP** | Financials & procurement — CAPEX planned vs actual, purchase orders, vendors, material logistics, e-invoicing, CPI |
| **Transmission (TC)** | Grid connectivity — substations, transmission lines, evacuation readiness, voltage tiers |
| **SharePoint** | Document and file exchange between site and HQ |
| **Pulse** | Site quality — Non-Conformances (NCs) and their review workflow |

**The core problem it solves:** before Akasha, a delayed project looked fine in P6, its money looked fine in SAP, and its grid connection looked fine in the transmission tracker — because nobody could see all three joined against the same project at the same time. Akasha joins them (via a Project Mapping layer that reconciles a transmission project name ↔ a P6 project ID ↔ an SAP SPV code) and then reasons over the joined picture.

**The scale it must feel like it handles:** an entire national renewable portfolio — dozens of solar and wind projects, thousands of P6 activities, thousands of purchase orders, hundreds of vendors, gigawatts of capacity, live site telemetry.

## Who uses it (design for these people, by name of role)

### 1. The Executive (CEO / CXO) — the primary persona
- **Lands on:** Executive Dashboard.
- **Wants:** in 10 seconds, "is my portfolio on track, what's bleeding, what do I decide today?"
- **Behaviour:** scans, doesn't read. Skips to red. Clicks a KPI expecting the story behind it. Often on a large monitor, sometimes projecting to a board room.
- **Design implication:** the top fold must answer "how are we doing" with zero scrolling. Everything else is drill-down. This screen will be shown to a board — it must look expensive.

### 2. The PMAG Lead (Portfolio Management & Governance)
- **Lands on:** PMAG Dashboard.
- **Wants:** governance control — which sites are slipping, who owns it, is the DPR (Daily Progress Report) in, is the grid connection ready, which milestone is overdue.
- **Behaviour:** works the screen all day. Compares projects side by side. Lives in tables and RAG (Red/Amber/Green) status.
- **Design implication:** highest information density of any role. Tables are the hero, not the cards.

### 3. The Project / Site Lead
- **Wants:** their one project, deeply — schedule activities they can edit inline, material arriving, NCs raised against their work.
- **Design implication:** single-project workspace; must be usable on a laptop at a site office, possibly on poor connectivity.

### 4. TC Ordering & TC Stores (transmission material roles)
- **Want:** what's ordered, what's at port, what's in transit, what's landed at which substation.
- **Design implication:** logistics-pipeline thinking — funnel and ledger views, not KPI cards.

### 5. The Admin
- **Wants:** the project mapping table (the thing that makes the whole join work), users, integrations, credential health.
- **Design implication:** clarity and safety. Destructive actions must look destructive.

> **Note on current state:** roles 3, 4 and 5 currently fall back to other dashboards — part of this redesign is giving them a real, distinct home. Design them as first-class, not as leftovers.

## Screen inventory (what already exists and must be redesigned)

### Entry
1. **Landing / splash** — animated brand entry, Login + Documentation, theme toggle.
2. **Login** — username/password, role-based redirect after sign-in.

### Executive Dashboard (route `/ceo-dashboard`) — sidebar-grouped
**Dashboard group**
- **Overview** — headline KPIs (total projects, delayed vs on-track, total MW, COD vs Trial-Run MW, PO value vs delivered value, average progress), project-stage funnel, transmission network summary, AI topline briefing. Every KPI tile opens a detail modal. Top / Low / Delayed project lists.
- **Capacity Overview** — COD and Trial-Run capacity by financial year, solar vs wind split, block-level milestones with gap-day tracking, per-project capacity, monthly trend sparklines.
- **Project 360** — searchable card grid of every project, status pills (Critical / High Risk / Watchlist / Healthy / Completed), risk-type filters (Material, Schedule, Vendor, Financial, Procurement, COD, Resource).
- **Quality** — portfolio-wide Quality Command Center.

**Analysis group**
- **Portfolio Health** — top projects' schedule progress + logistics status.
- **P6 View (Schedule)** — planned vs actual duration, most-delayed by variance.
- **SAP View (Financial)** — quarterly planned vs actual CAPEX, cash-flow variance, logistics funnel (At Port → In Transit → Delivered), top-vendor value breakdown.
- **Procurement Intelligence** — vendor scorecard, active POs, vendor-concentration risk %, full PO pipeline ledger.
- **Material Intelligence** — in-transit quantity, active shipments, delivered history, volume by destination, live shipment ledger.
- **Transmission Data Explorer** — raw network data + the cross-system mapping table.
- **Risk Command Center** — schedule risks (>30-day slips), financial risks (PO concentration), overall risk score, probability-vs-impact heatmap, ranked risk tables.
- **Predictive Analytics** — forecast slippage with an AI confidence score.
- **Decision Center** — auto-generated recommended interventions with Approve / Delegate actions.
- **Reports & Insights** — printable Executive Brief, PDF export, share.

**AI / Platform Tools group**
- **Ask Akasha** — full-screen AI copilot (also a floating panel available on every screen).
- **Briefing** — AI executive briefing: topline, 3 key-action cards, deep-dive narrative.
- **Search** — global search over projects, POs, vendors, materials.
- **Project Map** — interactive geographic map of substations/sites, colour-coded by voltage tier, live weather overlay.
- **Knowledge Graph** — explorable portfolio → project → vendor graph, coloured by health.
- **Simulation Lab** — 3-step what-if wizard (Detect → Strategies → Execute) producing a Monte-Carlo recovery timeline.

### Project Workspace (route `/ceo-dashboard/project/:id`)
Tabs: **Overview** (progress, SPI/CPI gauges, key facts) · **Schedule** (inline-editable activity table) · **SAP Intelligence** · **P6 Deep Dive** · **Transmission** · **Quality (NC tracker)**.

### PMAG Dashboard (route `/pmag`)
**Portfolio** (KPIs, projects grouped by EPS with RAG status, schedule-variance chart, critical-path panel, DPR tracker, connectivity status, alerts feed) · **Site Monitoring** (live telemetry: output MW, irradiance, wind speed, grid-sync %, asset map, equipment health) · **Grid Status** (target ECOD, substation readiness %) · **Reports** library · **Team** (roster, allocation %, DPR submission rate, activity log).

### Admin (route `/admin`)
**Project Mappings** (the transmission ↔ P6 ↔ SAP cross-reference table, with a side-drawer create/edit form) · **User Management** · **System Settings** · **Data Integrations** (source health, last sync, P6 credential expiry status).

### Global chrome (present on every screen)
Left icon-rail sidebar (collapsible, grouped) · top header with project selector, portfolio filter, phase filter (Ongoing / Commissioned / All), **Sync All Data**, **Ask Akasha**, notification bell, theme toggle · floating AI copilot · toast notifications · notification dropdown with per-alert comment threads.

## Domain vocabulary — use these exact terms, never invent placeholders

`P6` (Primavera schedule) · `SAP` · `TC` (Transmission Connectivity) · `SPV` (Special Purpose Vehicle — the legal entity SAP records hang off) · `COD` (Commercial Operation Date) · `TR` (Trial Run) · `ECOD` (target COD) · `SPI` / `CPI` (Schedule / Cost Performance Index) · `DPR` (Daily Progress Report) · `EPS` (portfolio grouping level) · `NC` (Non-Conformance) · `EE` / `QI` (Execution Engineer / Quality Inspector — the two NC review stages) · `PMAG` · `Pulse` (site quality source system) · `PO` (Purchase Order) · `RAG` status · `MW` / `GW` capacity.

**Never** use lorem ipsum, "Project Alpha", "Acme Corp", "$1,234", "Lorem", or generic dummy labels. Use realistic Indian renewable-energy content: project names in the style of *Khavda Solar Block 4*, *Rajasthan Wind SPV-12*, *Bhadla Phase III*; vendor names in an industrial-supplier register style; capacities like *250 MW*, *1.2 GW*; values in **₹ Crore**; dates in **DD MMM YYYY**; substations like *400kV Khavda PS-2*.

## Design direction — the single most important section

### The feeling to hit
**"Institutional intelligence."** Quiet, precise, confident, expensive. The interface of a system that knows things. Restraint is the aesthetic. It should feel like a control room instrument, not a consumer app and not a template.

Reference points for *quality bar and restraint* (not for copying): Bloomberg Terminal's density discipline, Linear's typographic precision, Stripe's data clarity, Vercel/Observability dashboards' calm dark surfaces, Palantir's seriousness.

### Hard bans — output that looks like this is a failed design
Do **not** produce any of the following. These are the tells of generic AI-generated UI and are unacceptable here:
- ❌ Purple-to-blue or pink-to-orange gradient hero blocks, gradient-filled buttons, gradient text.
- ❌ Glowing orbs, radial "aurora" blurs, mesh gradients, floating blurred circles as background decoration.
- ❌ Glassmorphism everywhere — frosted translucent cards stacked on a blurry photo.
- ❌ Emoji as UI iconography (🚀 ⚡ 📊 ✨) or sparkle icons to signify "AI".
- ❌ Oversized rounded corners (>12px) on data cards; pill-shaped everything.
- ❌ Big empty hero sections with a centred headline and a lot of nothing. Screen real estate is expensive.
- ❌ Generic SaaS marketing copy ("Unlock powerful insights", "Supercharge your workflow", "Powered by AI ✨").
- ❌ Drop shadows layered on drop shadows; heavy neumorphism.
- ❌ Every card the same size in an undifferentiated 3×3 grid with no visual hierarchy.
- ❌ Random dashboard filler charts that carry no meaning.
- ❌ Cartoon 3D illustrations, isometric people, stock avatars.
- ❌ Making the AI copilot look like a consumer chatbot — no cute mascot, no bouncing dots, no "Hi! 👋 How can I help you today?".

### What to do instead
- **Hierarchy through typography and spacing**, not through colour and decoration. One clear focal number per zone.
- **Colour carries meaning only.** Neutral greys and near-blacks/whites are the interface; brand and status colours are reserved for data, state and action. If a colour doesn't encode information, it shouldn't be there.
- **Borders and elevation-1 surfaces** over shadows and blur. A 1px hairline border in the right value does more work than a shadow.
- **Density with breathing room.** Tight rows (36–44px), generous section spacing. It should look full but never cramped.
- **Numbers are the design.** Tabular figures, right-aligned numerics, consistent decimal precision, units always visible, deltas with direction (▲ ▼) and semantic colour.
- **Every element earns its place.** If you can delete it and lose no information, delete it.
- **The AI must look like an analyst, not a chatbot.** Structured answers, cited source-system tags (P6 / SAP / TC) with data-freshness stamps, inline charts rendered into the response, follow-up chips, an explicit "Deep Analysis" mode. Confidence and provenance are visible design elements. It should feel like a research desk replying, not a bot.

### Status colour system (define these as Figma variables)
- **Critical / Delayed** — red
- **High Risk / At Risk** — amber
- **Watchlist** — soft orange or neutral-warning
- **Healthy / On Track** — green
- **Completed / Commissioned** — blue or neutral-success
- **Info / AI-generated** — a distinct low-saturation accent that never competes with status colours

Status must be readable without colour alone — pair with a shape, icon, label or position (accessibility, and board projectors wash colour out).

## Brand & technical constraints (non-negotiable — the design must be buildable)

**Brand identity — Adani Green Energy.** Three brand colours already in the system, keep these as the anchor:
- Brand Blue `#0B74B1` — primary
- Brand Purple `#76489D` — secondary
- Brand Pink/Magenta `#BC3860` — accent

Extend these into full 50–950 tonal ramps plus a neutral ramp. Use brand blue for primary action and identity; use purple/pink sparingly, mostly for AI and secondary emphasis — do not turn the UI into a purple gradient.

**Typography:** the product ships a corporate typeface, *Adani* (variable, weights 100–900). Design with a clean geometric/neo-grotesque sans as its stand-in (Inter, Söhne, or similar). Numeric data must use tabular lining figures.

**Themes:** full **light and dark** parity is mandatory — both are used daily; dark in control-room settings, light for board decks and print/PDF export. Design both, don't auto-invert.

**Implementation reality — design only what these can render:**
- React 19 + TypeScript, **Tailwind CSS 3** with CSS-variable-driven tokens (`--primary-500`, `--background-900`, etc.), `class`-based dark mode
- **Recharts** and **ECharts** for charts · **deck.gl** and **Leaflet/react-leaflet** for maps · **D3** for the knowledge graph
- **Framer Motion** for animation · **lucide-react** for icons (design with the lucide set — outline, 1.5px stroke, 16/20/24px)
- Sonner for toasts

So: no effects that need WebGL shaders or bespoke canvas work outside those libraries, and no icon style lucide can't supply.

**Motion:** functional only. 120–200ms ease-out transitions, subtle. Data updating, panels sliding, a value ticking. No parallax, no scroll-jacking, no decorative looping animation. The one place expressive motion is allowed is the landing/splash entry.

**Responsive targets:** 1920×1080 primary (and 2560 wide — the layout must use the extra width, not centre a narrow column in an ocean of margin), 1440 secondary, 1024 tablet for site users. Not mobile-first; mobile is graceful degradation only.

**Accessibility:** WCAG AA contrast in both themes, visible focus rings, 44px minimum hit targets for primary controls, never colour as the sole signal.

## Component system to deliver

Build these as proper Figma components with variants and auto-layout — this is a system, not a set of pictures:

`KPI Tile` (variants: default / with delta / with sparkline / clickable / loading) · `Data Table` (sortable header, sticky first column, row density variants, inline-edit cell, row status accent, pagination, empty state) · `Status Pill` (all 5 states) · `RAG Indicator` · `Project Card` (Project 360 grid) · `Chart Frames` (line, stacked bar, donut, funnel, heatmap, sparkline, gauge for SPI/CPI) · `Filter Bar` (project selector, portfolio, phase) · `Left Sidebar` (grouped, expanded + collapsed rail) · `Top Header` · `Side Drawer` (create/edit forms) · `Modal` (KPI detail) · `AI Message` (user turn, assistant turn, with chart, with source tags, with follow-up chips, thinking state) · `AI Input Bar` (text, voice, image attach, Deep Analysis toggle) · `Notification Item` (collapsed, expanded, with thread) · `Alert / Toast` · `Buttons` (primary, secondary, ghost, destructive; sm/md/lg; icon-only) · `Form controls` (input, select, combobox with autocomplete, date, toggle, checkbox) · `Tabs` · `Breadcrumb` · `Empty state` · `Skeleton loader` · `Map marker / legend` · `Graph node` (knowledge graph).

Set up **Figma variables** for colour (light + dark modes), spacing scale, radius, and type styles. Everything on a **4px spacing grid**, 12-column layout with a fluid max width.

## Deliverable structure in Figma

Organise the file as:
1. **Cover**
2. **Foundations** — colour ramps (light/dark), type scale, spacing, radius, elevation, iconography, motion notes
3. **Components** — the library above, with variants documented
4. **Patterns** — data table anatomy, chart anatomy, KPI anatomy, AI response anatomy, empty/loading/error states
5. **Screens — Executive** · 6. **Screens — PMAG** · 7. **Screens — Project Workspace** · 8. **Screens — Admin** · 9. **Screens — AI & Simulation** · 10. **Entry (Landing / Login)**
11. **Dark mode** variants of every key screen
12. **Flows** — login → role landing; KPI → drill-down → project; alert → simulation; question → AI answer → chart → follow-up

## How I will judge the result

1. Could an experienced portfolio manager use this to run a ₹-thousand-crore programme without a manual?
2. Does the Executive Overview answer "how are we doing" above the fold, with no scrolling?
3. Does it look like it was designed by a person with taste — or like a template with the brand colour swapped in?
4. Is every colour carrying information?
5. Does the AI read as an analyst with sources, not a chatbot with sparkles?
6. Is dark mode a real design, or an inversion?
7. Would this survive being projected in a board room?

Start with **Foundations + the Executive Overview screen**. Show me those before going wider.

---

# §B — PER-SCREEN PROMPTS (paste one at a time, after §A)

**B1 · Executive Overview**
> Design the Executive Overview at 1920×1080, light mode. Top fold: a row of 6 KPI tiles — Total Projects, Delayed vs On-Track, Total Capacity (MW), COD vs Trial-Run MW, PO Value vs Delivered Value, Average Progress % — each with a delta and a sparkline, each clickable. Below: a project-stage funnel, a transmission network summary panel, and an AI topline briefing block that reads like a written analyst note with source tags (P6 / SAP / TC) and a data-freshness stamp. Right rail: switchable Top / Low / Delayed project lists. No scrolling required for the KPI row and briefing. No gradients, no decorative blur.

**B2 · Project 360**
> A searchable card grid of ~40 projects. Each card: project name, SPV, capacity MW, status pill (Critical / High Risk / Watchlist / Healthy / Completed), progress bar, COD date, and up to 3 risk-type chips (Material, Schedule, Vendor, Financial, Procurement, COD, Resource). Sticky filter bar with search, status filter and risk-type filter. Show the grid with a realistic mix — mostly healthy, a few critical. Include hover and selected states, plus the empty-search state.

**B3 · Risk Command Center**
> Overall portfolio risk score as the focal element, a probability-vs-impact heatmap, and two ranked risk tables — schedule risks (slips >30 days) and financial risks (PO concentration). Table rows carry a status accent and drill into a project. Density over decoration.

**B4 · Procurement & Material Intelligence**
> Vendor performance scorecard, active PO count, vendor count, vendor-concentration risk %, and a full PO pipeline ledger table. Second frame: the logistics funnel At Port → In Transit → Delivered, in-transit volume by destination, and a live shipment ledger. Funnel must read as a real pipeline with counts and values, not a decorative triangle.

**B5 · Ask Akasha (AI copilot)**
> Two frames: (a) full-screen page with a left thread list, (b) the floating panel over a dashboard. Show a real multi-turn exchange: user asks "Which projects are delayed this month and what's driving it?"; the assistant answers with a short structured written analysis, an inline bar chart of delay days by project, source tags (P6 · SAP · TC) with "data as of" timestamps, and 3 follow-up chips. Include the Deep Analysis toggle, voice and image-attach controls in the input bar, thumbs up/down on the answer, and a thinking/streaming state. It must read as an analyst desk — no mascot, no sparkles, no "Hi there! 👋".

**B6 · PMAG Portfolio**
> The densest screen in the product. KPI strip (on-track / at-risk / delayed, avg completion, milestones due vs overdue), projects grouped by EPS in an expandable table with RAG status, a schedule-variance chart, a critical-path panel, a DPR submission tracker, connectivity status, and an alerts feed. This is a working screen — optimise for scanning many rows and comparing projects.

**B7 · Site Monitoring**
> Live telemetry: output MW, irradiance, wind speed, grid-sync %, an asset map with equipment health markers, and an equipment alerts list. Region and project-type filters. Should feel like a control room — real-time, calm, legible from a distance.

**B8 · Project Workspace**
> Single-project deep dive with tabs: Overview (progress, SPI and CPI gauges, key facts), Schedule (inline-editable activity table with status, dates, resources), SAP Intelligence, P6 Deep Dive, Transmission, Quality. Design the Overview and Schedule tabs fully; show the inline-edit interaction states on the activity table.

**B9 · Quality Command Center**
> KPI cards (total NCs, open, critical-open, closure rate, avg resolution days, total debit amount), a workflow funnel Raised → In Review (Execution Engineer) → In Review (Quality Inspector) → Approved with a Rejected branch, contractor breakdown, and a filterable NC list showing current owner per item.

**B10 · Simulation Lab**
> A 3-step wizard — Detect (auto-scan risk, SPI, critical path), Strategies (AI-proposed recovery options with adjustable parameters: priority, weather severity, additional crew, overtime), Execute (Monte Carlo recovery timeline + resolvable action checklist). Show the probabilistic output as a range, not a single date.

**B11 · Admin — Project Mappings**
> The cross-reference table joining Transmission project name ↔ P6 project name/ID ↔ SAP SPV name/code/capacity. Search, New Mapping side-drawer with autocomplete for unmapped P6 projects, edit, and a delete confirmation that looks appropriately destructive. Plus a Data Integrations panel: five source systems with last-sync time, health state, and a P6 credential-expiry warning.

**B12 · Landing + Login**
> The one screen allowed expressive motion. Brand-led entry for Adani Green's Akasha, Login and Documentation actions, theme toggle. Serious and cinematic — the opening of an institutional system, not a SaaS marketing page. Then the login screen with role-based sign-in.

**B13 · Dark mode pass**
> Produce dark-mode versions of B1, B5, B6 and B7. A designed dark palette — layered near-black surfaces, deliberate elevation, adjusted status colours that stay AA-legible. Not an inversion.

---

# §C — REFINEMENT PROMPTS (when output looks generic)

- *"This looks like a template. Strip every decorative element that isn't carrying information, then raise the typographic hierarchy to compensate."*
- *"Too much colour. Restrict colour to status, data series and primary action. Everything else neutral."*
- *"The density is too low — this is a professional tool used for six hours a day, not a landing page. Tighten rows, reduce padding, fit more information per fold."*
- *"Remove the gradients and the glow. Use a 1px hairline border and one elevation level instead."*
- *"The AI panel reads like a consumer chatbot. Make it read like an analyst: structured answer, cited source systems, data-freshness stamp, confidence, inline chart."*
- *"The numbers aren't the hero. Increase the focal metric, use tabular figures, right-align numerics, show units and deltas with direction."*
- *"At 2560px this centres a narrow column. Use the full width with a real 12-column layout."*
- *"Show me the loading, empty and error states for this screen — a real product is mostly those."*

---

# §D — FILL IN BEFORE SENDING (project-specific, I couldn't infer these)

Add these to §A if you want the design AI to have them:
- **Team & credits** — who built Akasha (names/roles), and who the design stakeholders are.
- **Any existing brand guideline PDF** from Adani Green (logo lockups, clear space, approved secondary palette).
- **Real screenshots** of the current UI — attach 3–5; "here is what exists today, raise it to the bar above" produces markedly better output than a description alone.
- **Real (or anonymised) data samples** — an actual project list, PO ledger extract, or NC list, so the design is populated with true-shaped content.
- **Deployment context** — board-room projector? control-room video wall? both? It changes the density and contrast targets.
