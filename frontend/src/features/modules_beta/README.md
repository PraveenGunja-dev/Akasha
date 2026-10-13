# Ordering Schedule · Beta

A standalone copy of the **Ordering Schedule** page where new features are tried
before they reach the live page. The first feature trialled here is a pair of
AI forms: **Module Ordering & TC Delivery Forecasting** and **Priority
Prediction**.

The live page (`features/modules/`) is untouched. Nothing in this folder is
imported by it.

---

## Opening it

1. Open **Ordering Schedule** from the left sidebar.
2. Click **Beta** in the top header, left of the phase dropdown.
3. The banner changes to *Ordering Schedule · Beta* and the Beta button stays
   highlighted. Click it again, or the sidebar item, to return to the live page.

The Beta button appears only on the Ordering Schedule (live or Beta). It is
hidden on every other page and inside an opened project.

---

## What's in this folder

| File | Purpose |
| --- | --- |
| `OrderingPlannerBeta.tsx` | Entry point. Same *Current schedule / Block plan* tabs as the live page. |
| `ModuleDeliveriesPage.tsx` | Copy of the live page, with `AIPredictionPanels` added under **AI Procurement Strategy**. |
| `AIPredictionPanels.tsx` | **New.** The two AI forms and their results. |
| `BlockPlanView.tsx`, `export.ts`, `planningRules.ts`, `types.ts` | Unchanged copies of the live files. |

### Wiring outside this folder

| File | Change |
| --- | --- |
| `pages/CEODashboard.tsx` | Registers the `installation_planner_beta` tab and banner, and passes `betaToggle` to the header only on the Ordering Schedule. Keeps the sidebar's Ordering Schedule item highlighted while Beta is open. |
| `components/layout/TopHeader.tsx` | Renders the **Beta** button when `betaToggle` is passed. |
| `vite.config.ts` | Dev proxy `/akasha/ai-api` → AI service `/api/ai/v1`. |

Beta reads the same backend data as the live page
(`/akasha/api/module-deliveries/...`), so both show the same figures until the
code diverges.

---

## AI prediction forms

Both forms live under **AI Procurement Strategy** in the Beta page. They send
the form values to a separate FastAPI service and show the response. All
output is labelled as model prediction, not plan or SAP data.

### 1. Module Ordering & TC Delivery Forecasting

`POST /api/ai/v1/order-tc-forecast?explain=true`

Request:

```json
{
  "project_id": "ARE55L_S03",
  "project_name": "MSEDCL PPA Ph-3",
  "phase": "PH-1",
  "vendor_type": "ALMM",
  "priority": "STANDARD",
  "capacity_mwp": 203,
  "balance_ordering": 203,
  "inventory": 0,
  "receipt": 0,
  "under_transit": 0,
  "lta_date": "2028-06-30",
  "scod_date": "2027-04-29",
  "ftc_date": "2027-05-19"
}
```

What the result shows:

- **Header line:** the matched P6 project, risk level, confidence, and *Order now* when flagged.
- **Order by (AI):** compared with the rule engine's date (`order_by_shift_vs_rule_days`).
- **Predicted TC:** with the P90 (latest likely) date and the rule engine's TC date.
- **Projected FTC:** with days after or ahead of the deadline (`deadline_breach_days`, rounded).
- **AI priority:** with the current priority and the criticality score.
- **Explanation:** summary, rule vs AI, key drivers, risks, business impact and recommended actions.

### 2. Priority Prediction

`POST /api/ai/v1/priority-predict?explain=true`

Request:

```json
{
  "project_id": "ARE55L_S03",
  "project_name": "MSEDCL PPA Ph-3",
  "phase": "Ph-1",
  "category": "PPA",
  "capacity_mwp": 675,
  "balance_ordering": 675,
  "inventory": 0,
  "receipt": 0,
  "under_transit": 0,
  "lta_date": "2026-10-08",
  "scod_date": "2026-10-08",
  "ftc_date": "2026-10-08",
  "ftc_risk_flag": false,
  "current_priority": "STANDARD"
}
```

What the result shows:

- **AI priority:** flagged when it differs from the current priority.
- **Score** out of 100.
- **Rule engine priority** and its basis.
- **Realistic FTC** compared with the FTC used.
- **Reasons**, and the **probability** of each priority class.
- **Explanation** sections. Key drivers are left out because they repeat the reasons.

### Form behaviour

- **Fill sample** loads example values. **Clear** resets the form and the result.
- Every field is required. Dates are sent as `YYYY-MM-DD` and MWp fields as numbers.
- While a request runs, the button shows a spinner and cannot be clicked again.
- API errors show in the result area. FastAPI 422 validation errors are listed by
  field, e.g. `lta_date: invalid date`.
- Empty or `null` response fields are skipped. Nothing is filled in on the client.
- If the response lists `unverified_numbers`, a warning is shown under the explanation.

---

## Running locally

```bash
cd frontend
npm install
npm run dev
```

The browser calls `/akasha/ai-api/...`. The Vite dev server forwards those
calls to the AI service, so there are no CORS issues.

| Setting | Where | Default |
| --- | --- | --- |
| AI service address (dev proxy) | `AI_API_TARGET` env var, or edit `vite.config.ts` | Value in `vite.config.ts` |
| Base path the browser calls | `VITE_AI_API_BASE` env var | `/akasha/ai-api` |

Point the proxy at a different service:

```powershell
# PowerShell
$env:AI_API_TARGET = "http://localhost:8000"; npm run dev
```

```bash
# bash
AI_API_TARGET=http://localhost:8000 npm run dev
```

**ngrok:** the proxy sends `ngrok-skip-browser-warning: true`. Without it,
ngrok's free plan returns its HTML warning page instead of the API response.
Free ngrok URLs change whenever the tunnel restarts, so update
`AI_API_TARGET` and restart `npm run dev` when that happens.

**Production:** the Vite proxy only runs in dev. Do one of these:

- Add the same rule to the production reverse proxy (`/akasha/ai-api/*` → `<service>/api/ai/v1/*`).
- Build with `VITE_AI_API_BASE` set to the service's `/api/ai/v1` URL. The service must then allow CORS from the app's origin.

### Checks before committing

```bash
cd frontend
npx tsc --noEmit -p tsconfig.json
npx vite build --logLevel error
```

Run both. `tsc` misses some import errors that only the build catches.

---

## Promoting Beta changes to the live page

Beta is a copy, so changes do not flow either way automatically.

1. Diff the Beta file against its live twin, e.g.
   `git diff --no-index src/features/modules/ModuleDeliveriesPage.tsx src/features/modules_beta/ModuleDeliveriesPage.tsx`.
2. Move the change into `features/modules/`. For AI forms, also copy
   `AIPredictionPanels.tsx`.
3. Re-run both checks.

Fixes made to the live page after this copy was taken do **not** appear in
Beta. Apply them to both folders while Beta exists.

### Removing Beta

1. Delete `features/modules_beta/`.
2. In `CEODashboard.tsx`, remove the `OrderingPlannerBeta` import, the
   `installation_planner_beta` entries (modules list, banner and render line),
   the sidebar mapping and the `betaToggle` prop.
3. In `TopHeader.tsx`, remove the `betaToggle` prop and the Beta button.
4. In `vite.config.ts`, remove the `/akasha/ai-api` proxy rule if nothing else uses it.
