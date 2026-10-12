# Ordering Schedule AI

Rule engine (benchmark) + ML (prediction) + LLM (explanation) for module ordering, TC delivery and priority.

```
data/raw/            Ordering Schedule workbook exports (input, never edited)
data/interim/        tidy tables + project snapshot the API matches requests against
data/processed/      per-use-case train/test sets, schema.json, DATASET_REPORT.md
src/parsers.py       raw sheet -> tidy table
src/build_datasets.py  tidy tables -> labelled, split datasets
src/features.py      model features - one function for training AND the API (parity-tested)
src/rules.py         the current planning engine's deterministic logic (benchmark)
src/train.py         tuning, grouped CV, rule baselines, MLflow registry -> models/
service/             FastAPI: engine.py (rule + ML), explain.py (LLM / template), app.py
tests/               parity, response contract, guardrail, error handling
```

## Run

```bash
pip install -r requirements.txt
cd src && python build_datasets.py && python train.py && cd ..
cp .env.example .env                       # fill in; AI_PROVIDER=groq locally, azure on the VM
python -m uvicorn service.app:app --port 8000           # API + Swagger at /docs
python -m mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000   # runs, metrics, model registry
AI_PROVIDER=none python -m pytest tests -q
```

Demo script with talking points and limitations: [DEMO.md](DEMO.md).

The Akasha frontend's beta panel (`features/modules_beta/AIPredictionPanels.tsx`) already calls these routes
through the Vite proxy: run the frontend with `AI_API_TARGET=http://localhost:8000`.

| Route | Use case |
|---|---|
| `POST /api/ai/v1/order-tc-forecast?explain=true` | UC1 order date, TC date (P50/P90), projected FTC, root cause |
| `POST /api/ai/v1/priority-predict?explain=true` | UC2 P1 / P2 / STANDARD with probabilities and score |
| `POST /api/ai/v1/batch/module-deliveries/csv` | Upload a Module Deliveries CSV → the same CSV with UC1 + UC2 AI columns appended |
| `POST /api/ai/v1/batch/module-deliveries/json` | The same from JSON rows keyed by the sheet's headers → JSON rows + `ai_detail` + summary |
| `POST /api/ai/v1/batch/akasha-dashboard` (file) or `/akasha-dashboard/json` (body) | Dashboard export `akasha_ordering_schedule_full.json` → the same JSON with `ai_priority` + `ai_monthly_order_tc_forecast` on every project; saved to `data/output/AIAkashaOrderingSchedule_final.json` |
| `GET /api/ai/v1/monthly-plan?epc=Amara Raja` | UC1 Month-wise Module Requirement at Site (MWp / MWac) per contractor, rule vs AI, vendor quota check |
| `GET /api/ai/v1/health`, `/model-info` | status; models, metrics, label provenance |

## Batch: a whole Module Deliveries file (dashboard)

Input is the Module Deliveries sheet. The CSV endpoint takes the export as-is (title rows, two-row header, EPC
group rows). The JSON endpoint takes `{"as_of": "...", "rows": [{"Project": ..., "P6 Name": ..., "Capacity
(MWac)": ..., "FTC Date": ..., "EPC Group": ...}]}`, keyed by the same headers. Samples:
`samples/Module Deliveries.json` (input) and `samples/Module Deliveries - AI.csv` (output).

Every pending FTC phase is scored with the single-project code. Each project row gets these columns:

| Column | Level | Source |
|---|---|---|
| AI Status | project | scored / why not: all phases charged, no FTC, unknown Type, not in the snapshot |
| AI Priority, AI Priority Set By, AI Priority Score (model), Rule Priority (P6 dates), AI Priority Reasons | project: highest phase | UC2 |
| AI Module Order Date, AI Order Now, AI TC Date, AI TC Date (P90), AI FTC (projected), AI Risk Level, AI Days After Deadline, AI Root Cause | one line per phase (`Ph-I: 27-Jan-27`) | UC1 |
| AI Lead Time (P50 / P90 days), AI Confidence | lead phase | UC1 |
| AI Month wise Module Requirement at Site (MWp / MWac) | project | UC1 monthly plan, `Jun-27: [ 136 / 100 ] order by 27-Jan-27` |
| AI Explanation - Order & TC (UC1), AI Explanation - Priority (UC2) | lead phase | copilot text |

`?explain=template` (default) is instant. `?explain=llm` asks the copilot for each project's lead phase; on
the Groq free tier that is about 10 s per project, so use it on a filtered file. `?explain=none` leaves the
explanation columns empty. Site Productivity (P6 pace, planned %) is not in this sheet, so it is joined from the
training snapshot by P6 name. A project the snapshot does not know is still scored, and AI Status says so.

## Batch: the Akasha dashboard export

Input is the JSON the Ordering Schedule dashboard renders (`meta`, `ordering_schedule.projects`, `block_plan`).
Each project in `ordering_schedule.projects` is scored with the UC1 code (`order-tc-forecast?explain=true`) and
the UC2 code (`priority-predict?explain=true`). These are called in-process, the same functions as the HTTP
endpoints. The rest of the document is returned unchanged. Each project gets exactly two fields:

| Field | Content |
|---|---|
| `ai_priority` | UC2 response (`priority-predict?explain=true`) for the most urgent phase: `priority_class`, `priority_score`, `reasons`, `rule_engine`, `class_probabilities`, `realistic_ftc_date`, `guardrail`, `model`, `explanation`, plus `phase`, `notes` and a `phases` summary |
| `ai_monthly_order_tc_forecast` | UC1 response (`order-tc-forecast?explain=true`) for the lead phase (first one still to order): order / TC / FTC dates, `root_cause`, `lead_time`, `monthly_requirement`, `explanation`, plus `phase`, `notes` and a `phases` summary |

Each field has a `status`: `"scored"`, or `"not_scored"` with a `reason` (all phases charged, or a type with no
lead time).

`meta.ai` carries the run time, summary counts and field list. The balance is shared out across phases in the
Planning Rules sequence, so each phase is ordered as its own lot. The measured lead time is read at that lot
size (SECI VIII: 68 MWp phases, about 67 d typical / 93 d P90). This is shorter than the single-endpoint demo,
which orders all 408 MWp at once.

```bash
curl -X POST 'http://localhost:8000/api/ai/v1/batch/akasha-dashboard' \
  -F 'file=@data/raw/akasha_ordering_schedule_full.json' -o AIAkashaOrderingSchedule_final.json
```

## How a prediction is made

**UC1.** The rule engine gives TC = FTC − 45 d and order = TC − lead (China/SEA 136 d, ALMM/DCR 98 d).
The ML adds what the rule assumes away:
* **Site-readiness shift** (LightGBM): days the site pushes FTC past P6.
* **Supplier lead time** (LightGBM quantile, conformal-calibrated): measured from Ariba dispatch/GRN dates.

**Month-wise Module Requirement at Site** (`monthly_requirement` in the UC1 response, `src/monthly.py`).
The sheet places each phase's requirement (phase MWac × OL) in its **TC month**: 43 of 43 planned cells match.
The balance is shared out across phases in order-date sequence. The rule plan reproduces that from P6 dates. The
AI plan uses one of two timings, picked by the planner's own "timed by" column:
* **FTC date**: each funded phase lands in the TC month of its AI effective FTC.
* **Site speed**: P6 measures a structure pace. Inventory and in-transit stock are used first, then modules
  are needed as structures are finished.

Every month carries its order-by date, which is the need date minus the measured P90 lead time.

The planner rule "LTA after the deadline → the phase can wait" is applied on top. The order-by date is set so
that even a P90 delivery meets the need date. The root cause splits the FTC shift into progress, material and
transmission parts that add up to the total. Weather is reported as "no data".

**UC2.** A CatBoost classifier (chosen over XGBoost by grouped CV) is stacked on UC1: it gets the predicted site
delay and the realistic deadline margin. One hard business rule sits over it: a PPA phase that will charge
after SCOD is P1 (penalty). If the LTA came after SCOD, the phase may wait for transmission, but only until the
LTA. The training label had "LTA after SCOD → can wait" with no end date, so the model gives P2 to PPA phases
that charge long after a passed LTA (TPL-D, MSEDCL). The rule overrides 7 of the 70 phases in the current
sheet. When it does, the response says so (`guardrail`, batch column `AI Priority Set By`). Retraining UC2 on
the corrected label would remove the need for most of these overrides.

**Explanation.** Key drivers, risks, impact and recommended actions are computed. The LLM (Groq / Azure)
writes only the summary and the rule-vs-AI paragraph, from labelled facts. Any number it states that is not
in the facts is listed in `unverified_numbers`. Any LLM failure falls back to the template.

## Results (grouped CV on train; held-out test; vs the rule engine)

| Model | Metric | Model | Rule engine | Other baseline |
|---|---|---|---|---|
| UC1 site shift | CV MAE (days) | 138 | 175 (P6 FTC holds) | 125 (portfolio median) |
| UC1 lead time P50 | test MAE (days) | 30 | 70 (136 / 98 d) | — |
| UC1 lead time P90 | test coverage | 78 % (target 90 %) | — | — |
| UC2 priority | CV macro-F1 | 0.91 | 0.87 (rule on P6 dates) | — |
| UC2 priority | test macro-F1 | 1.00 (21 phases) | 0.87 | — |

Read these against the data behind them (`data/processed/DATASET_REPORT.md`, `models/metadata.json`):
* **The site-shift model does not beat the portfolio median** in grouped CV: about 20 projects, one at +720 d,
  and the label is the sheet's own site-pace extrapolation, not an actual FTC. The response's `confidence` (~0.2)
  reflects that. Its predictions move noticeably between retrains.
* **Lead time is the one model trained on measured outcomes**, and it beats the rule. No domestic PO in the
  Ariba history exceeds ~82 MWp, so larger domestic orders are read at that size and the response says so.
* **UC2's label is the business rule on the realistic FTC.** Only 4 projects (10 phases) disagree with the rule
  on P6 dates, so the perfect test score rests on very little.

The fastest improvement is real labels: actual FTC from P6 (`p6_activity.actual_finish_date`), nightly P6
snapshots for FTC revision history, and planner-recorded P1/P2.
