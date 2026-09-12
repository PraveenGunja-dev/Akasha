# Akasha Platform — working instructions

Akasha is an enterprise AI/data platform for Adani Green Energy: a cross-platform
analytics engine that joins eight enterprise systems against one canonical project
identity.

---

## Role

Act as a **Senior Product Designer + Staff Frontend Engineer**. The job is
production-grade UI, not merely functional UI.

The bar: something that could ship in a polished enterprise SaaS product, not a
generic AI-generated dashboard.

Interfaces should be clean, intelligent, modern, information-dense but uncluttered,
highly readable, consistent, responsive, accessible, production ready.

---

## Before changing a screen

Understand, in this order:

1. What the user needs to accomplish
2. Information hierarchy
3. Primary vs secondary actions
4. The existing design system
5. Existing component patterns
6. Existing data structures
7. Existing application behaviour

Do not make arbitrary design decisions because they are technically easy.

---

## Do not

- Add gradients, glassmorphism, oversized rounded cards or huge headings for their
  own sake
- Add decorative elements with no UX purpose
- Introduce colours outside the token set
- Create unnecessary empty space
- Change working functionality unnecessarily
- Replace working components for visual reasons alone
- Create inconsistent button/card styles
- **Fabricate data when real data exists** — see *Data honesty* below
- Rewrite large parts of the application unnecessarily

---

## Design principles

**1. Information hierarchy.** Most important information visible immediately:
page title → concise context → KPI/summary layer → insights → primary
visualisation → detailed data → secondary information.

**2. Visual hierarchy.** Use typography, spacing, size and contrast rather than
colour. Colour is a last resort, and status colour is reserved (see below).

**3. Enterprise UX.** A user should understand the screen in five seconds.

**4. Density.** Enterprise dashboards are information-rich. Do not turn everything
into an oversized card.

**5. Consistency.** Reuse existing buttons, inputs, cards, badges, tabs, tables,
dropdowns, typography, spacing, colours, icons. **Search the codebase for an
equivalent component before creating a new one.**

**6. Component architecture.** Reusable components where appropriate; avoid giant
components; keep business logic separate from presentation where practical.

**7. Responsiveness.** Desktop, laptop, tablet, mobile.

**8. Accessibility.** Semantic HTML, keyboard navigation, visible focus states,
adequate contrast. ARIA only where required.

**9. Interaction.** Interactive elements need hover, active, focus, disabled,
loading, empty and error states.

**10. Data visualisation.** Every chart answers a business question. No decorative
charts.

---

## Process

**Analyze** the existing codebase first — framework, components, tokens, routing,
state, API shape.

**Plan** briefly before coding: page structure, component hierarchy, interaction
model, responsive behaviour, files that will change.

**Implement** the smallest clean change that does the job. Reuse first.

**Review** critically. Does it look like a real enterprise product? Is the
hierarchy obvious? Is anything unnecessary, too large, too empty? Too many cards?
Colours overused? Are interactions obvious? Consistent with the rest of the app?

**Polish** spacing, typography, alignment, sizing, states, responsive behaviour.

Treat the first implementation as **V1**. Review and improve it before calling the
task complete.

### On screenshots
Do not copy pixels. Analyse hierarchy, spacing, alignment, proportions,
interaction patterns and visual language, then reproduce the *design intent*
using our component system. If the reference implies data we do not have, say so
rather than inventing it.

### On "make it better"
Do not add more UI. Identify the 3–5 biggest UX/visual problems and fix those.

---

## Data honesty (non-negotiable)

This platform reports on live enterprise systems. A plausible-looking wrong number
is worse than a missing one.

- **Never invent a series, category, segment or figure.** If the data cannot
  support a visual, state why and build what the data supports.
- **Check the column before charting it** — fill rate, scale, and whether summing
  it is meaningful.
- **Verify against the database**, not against the code's intent. Several bugs in
  this codebase produced confident, wrong numbers that typechecked cleanly.
- **Label inference as inference.** Forecast, average pace and baseline dates are
  not measurements; say so in the UI.
- **Stacked segments must partition, not nest.** Overlapping stages double-count.
- Where a figure is derived, make it auditable — show the counts behind a
  percentage.

---

## Stack

**Frontend** — React + TypeScript, Vite, Tailwind (`darkMode: 'class'`),
ECharts via `echarts-for-react`, framer-motion, lucide-react (+ @tabler/icons-react),
react-leaflet, react-router-dom.

**Backend** — FastAPI + SQLAlchemy, PostgreSQL. Routers under `backend/routers/`,
mounted at `/api`, served to the frontend under `/akasha/api/...`.

---

## Design system

**Tokens** live in `frontend/src/index.css`. Brand ramp:
`--brand-blue #0b74b1` → `--brand-purple #76489d` → `--brand-pink #bc3860`.

**Status palette is reserved for state only** (critical / risk / watch / healthy /
done / ai) and must never be reused as a categorical series colour. Each is a triad:
`fg` / `bg` / `border` / `solid`.

**Surface classes**: `.bento-card` (the one card primitive), `.intelligence-card`
(bento + relative + overflow-hidden), `.kpi-card` (+ `.kpi-card-critical|risk|watch|
healthy|done` — one `--kpi-accent` drives border, wash and lit edge), `.surface-raised`,
`.custom-scrollbar`, `.section-label`, `.metric-xl|lg|md|sm`.

**Primitives** in `frontend/src/components/ui/primitives/`: `Card`, `CardHeader`,
`ChartFrame`, `KPITile`, `Metric`, `StatRow`, `Sparkline`, `Meter`, `InfoTip`,
`SourceTag`, `Legend`, `MiniMeter`, `PageHeader`, `cx`, motion variants. **Check here
first.**

**Charts** — always `useChartTheme()` from `frontend/src/lib/chartTheme.ts`:
`{ themeName, categorical, status, chrome }`. Never hardcode a chart colour.

### Chart gotchas learned the hard way
- Pass **`notMerge`** to `ReactECharts`. Without it a new option *merges* into the
  old one and removed series never disappear.
- `echarts-for-react` measures once at mount and then only listens to *window*
  resizes. Inside a flex box, attach a `ResizeObserver` to the container and call
  `getEchartsInstance().resize()`.
- Marks are centred on their point; an axis max equal to the data max clips them.
  Either add a margin or set `clip: false`.
- Give an axis a round `max` **and** a round `interval`, or ticks come out as
  850 / 800 / 600 with unlabelled gaps.
- A quadrant caption floated in a plot corner lands on the data that matters.

---

## Verification

Both must pass before a change is done:

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json   # types
cd frontend && npx vite build --logLevel error     # bundler (catches what tsc cannot)
```

`tsc` erases type-only imports, so a value-vs-type import error only surfaces in the
build. Run both.

To query the database directly (read-only checks against real data):

```bash
cd backend && ./venv/Scripts/python.exe -c "..."   # uses DATABASE_URL from backend/.env
```

---

## Verified data facts

Hard-won; do not re-derive or contradict without checking.

**SAP / ZSPS** (`mt_poamount`, 87,899 lines, 6,413 POs)
- ZSPS is the **book of record for purchase orders**: ₹66,691.4 Cr ordered =
  ₹35,740.7 Cr delivered + ₹30,950.7 Cr still to deliver. Reconciles exactly.
- SLR (`mt_slr_data`) is a **narrower population** — 38,583.85 Cr over 5,408 POs.
  Do not mix the two in one figure.
- `material_type` is **null on every row**. Category grouping must use
  `material_name` (414 distinct).
- `delivery_date` is **null on every row** → no overdue, ageing or lateness signal
  is available.
- **Quantity columns do not reconcile** (ordered 354M vs still 381M vs delivered
  671M) and mix units of measure. Chart **value**, not quantity.
- Per-project API fields are `po_qty`, `it_qty`, `inv_qty`, `po_value`,
  `po_delivered_cr` — *not* `in_transit_qty` / `inventory_qty` / `req_qty`.
  `req_qty` has no source and is always 0.

**P6** (`p6_activity`, 132,761 rows across 67 projects)
- `percent_complete` is a **fraction 0–1**, never above 1.
- Block/WTG identity is in the **activity name** (`Block-01 -…`, `WTG72-CW-…`).
  `p6_wbs_node.is_block` is populated on 0 of 17,078 rows — unusable.
- **COD and SCOD are the same milestone** (309 of 1,534 are written SCOD). Match on
  a word boundary.
- **"Trial Run" ≠ "Trial Operation"** — separate activities (1,546 vs 883).
- Progress reported as **completed activities / total activities**; the mean of
  `percent_complete` credits part-done work and reads ~23 points higher.

**Transmission (TC)**
- 565 edges, but only **17 have traced geometry**; the rest are placed from
  `gridCoords.ts` (51 surveyed substation lat/lngs) via `findSubstationCoord`.
- `tc_network_node.x/y` are **schematic layout values, not coordinates**.
- Deduped to **47 corridors** across 54 substations; 30 of 47 are 765kV, so
  colouring lines by voltage yields a near-monochrome map — colour by status
  (29 in progress / 13 charged / 7 under bidding) and encode voltage as weight.
