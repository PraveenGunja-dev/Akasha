# Ordering Schedule AI — PoC demo runbook

## 1. Start everything (3 terminals, from `Ordering_Schedule_AI/`)

```bash
# one-time setup
pip install -r requirements.txt
cp .env.example .env            # set AI_PROVIDER=groq + AKASHA_AI_API_KEY (azure works only from the VM)

# (optional) rebuild datasets and retrain - models are already in models/
cd src && python build_datasets.py && python train.py && cd ..

# terminal 1 - prediction API (Swagger UI: http://localhost:8000/docs)
python -m uvicorn service.app:app --port 8000

# terminal 2 - MLflow dashboard: http://localhost:5000
python -m mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

# terminal 3 - Akasha frontend, beta panel calls the API through the Vite proxy
cd ../frontend && AI_API_TARGET=http://localhost:8000 npm run dev
```

PowerShell: `$env:AI_API_TARGET="http://localhost:8000"; npm run dev`.

**MLflow:** open http://localhost:5000 → experiment `ordering-schedule-ai` → 4 runs. Each run has its
tuned parameters and metrics (`cv_*` = grouped cross-validation, `test_*` = held-out projects, `*_rule` = the
current rule engine on the same rows). The **Models** tab lists the 4 registered models.

## 2. The demo story: SECI VIII PPA (300 MWac, Chinese modules, PPA)

P6 says FTC 21-Dec-26 against SCOD 02-Mar-27. The rule engine is comfortable. The site is 29% piled and
1% structured.

### Use case 2 — Priority

```bash
curl -X POST 'http://localhost:8000/api/ai/v1/priority-predict?explain=true' \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"ASEJ6PL_S07","project_name":"SECI VIII PPA","phase":"Ph-I","category":"PPA",
       "capacity_mwp":408,"balance_ordering":408,"inventory":0,"receipt":0,"under_transit":0,
       "lta_date":"2027-01-31","scod_date":"2027-03-02","ftc_date":"2026-12-21",
       "ftc_risk_flag":false,"current_priority":"STANDARD"}'
```

**What it returns:** P1, score 99.6. The rule engine says **P2**.

**What to say:** "The rule engine reads the P6 date, which leaves 71 days before SCOD, so it says P2. The AI
asks when this phase can *really* charge. With structures at 1%, that is 9-Aug-27: 160 days after SCOD, on a
PPA with liquidated damages. Same inputs, different answer, because the AI looks at site reality and not only
the plan."

### Use case 1 — Module ordering and TC

```bash
curl -X POST 'http://localhost:8000/api/ai/v1/order-tc-forecast?explain=true' \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"ASEJ6PL_S07","project_name":"SECI VIII PPA","phase":"Ph-I","vendor_type":"China",
       "priority":"STANDARD","capacity_mwp":408,"balance_ordering":408,"inventory":0,"receipt":0,
       "under_transit":0,"lta_date":"2027-01-31","scod_date":"2027-03-02","ftc_date":"2026-12-21"}'
```

**What it returns:** the rule engine says the order was due 23-Jun-26 (overdue). The AI says order by
27-Jan-27; modules at site ~20-May-27 (latest 25-Jun-27); charging ~9-Aug-27; risk HIGH. Root cause: 231 days of
progress delay, 0 material, 0 transmission.

**What to say:** "The rule engine says 'you are 3 months late, order now'. The AI says that is the wrong lever:
the structures are not ready, so modules ordered today would sit in the yard. Fix construction pace, order by
end-January, and time deliveries to the structures. The lead time it uses is measured from actual Ariba
dispatch and receipt records, not the 136-day assumption."

### Use case 1 — Month-wise Module Requirement at Site

The same UC1 response carries `monthly_requirement`. For SECI VIII:

| | Rule engine (P6 dates, 136 d) | AI (realistic FTC, P90 149 d) |
|---|---|---|
| Months | Nov-26 272 MWp / 200 MWac, Dec-26 136 / 100, both orders overdue | Jun-27 136 / 100 (order by 27-Jan-27), Jul-27 272 / 200 (order by 6-Feb-27) |

By contractor, grouped like the sheet:

```bash
curl 'http://localhost:8000/api/ai/v1/monthly-plan?epc=Amara%20Raja'
```

PowerShell: `Invoke-RestMethod "http://localhost:8000/api/ai/v1/monthly-plan?epc=Amara Raja" | ConvertTo-Json -Depth 8`

**What it returns:** "Amara Raja (4 projects · 641.25 MWp)", the sum of the four projects' MWac × OL. Three
projects have nothing left to order. TPL-D has 30 MWp of balance and is timed by site speed: 137 MWp of yard
stock covers the structures for the next ~6 months, so the AI needs 14.7 MWp in Apr-27 and 15.3 MWp in May-27,
ordered by 31-Dec-26 and 25-Jan-27. The rule engine put all 30 MWp in Sep-26, which is already past.

**What to say:** "The sheet's plan follows the P6 date. The AI follows what the site can absorb. Stock first,
then modules as structures finish. Ordering earlier only adds stock in the yard."

### Whole sheet in, AI columns out (dashboard)

```bash
curl -X POST 'http://localhost:8000/api/ai/v1/batch/module-deliveries/csv' \
  -F 'file=@data/raw/Module Deliveries.csv' -o 'Module Deliveries - AI.csv'
curl -X POST 'http://localhost:8000/api/ai/v1/batch/module-deliveries/json' \
  -H 'Content-Type: application/json' --data-binary '@samples/Module Deliveries.json' -o result.json
```

PowerShell (`curl.exe`, not the `curl` alias):

```powershell
curl.exe -X POST "http://localhost:8000/api/ai/v1/batch/module-deliveries/csv" -F "file=@data/raw/Module Deliveries.csv" -o "Module Deliveries - AI.csv"
$r = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/ai/v1/batch/module-deliveries/json" -ContentType "application/json" -InFile "samples/Module Deliveries.json"
$r.summary
$r.rows | Select-Object Project, "AI Priority", "AI Module Order Date", "AI TC Date", "AI Risk Level" | Format-Table
```

Or use Swagger (http://localhost:8000/docs → *batch* → **Try it out** → choose the file).

**What it returns:** the sheet, row for row, with 20 AI columns. On the current file: 49 projects, 32 scored
(17 have every phase charged), 19 P1 / 3 P2 / 10 STANDARD, 25 high risk, 4 to order now.

### Same calls from Windows PowerShell

In Windows PowerShell `curl` is an alias for `Invoke-WebRequest` and rejects `-H` / `-d`. Use:

```powershell
$uc2 = @'
{"project_id":"ASEJ6PL_S07","project_name":"SECI VIII PPA","phase":"Ph-I","category":"PPA","capacity_mwp":408,"balance_ordering":408,"inventory":0,"receipt":0,"under_transit":0,"lta_date":"2027-01-31","scod_date":"2027-03-02","ftc_date":"2026-12-21","ftc_risk_flag":false,"current_priority":"STANDARD"}
'@
$r = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/ai/v1/priority-predict?explain=true" -ContentType "application/json" -Body $uc2
$r | ConvertTo-Json -Depth 6        # full response
$r.explanation.text                 # the copilot explanation

$uc1 = @'
{"project_id":"ASEJ6PL_S07","project_name":"SECI VIII PPA","phase":"Ph-I","vendor_type":"China","priority":"STANDARD","capacity_mwp":408,"balance_ordering":408,"inventory":0,"receipt":0,"under_transit":0,"lta_date":"2027-01-31","scod_date":"2027-03-02","ftc_date":"2026-12-21"}
'@
$r = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/ai/v1/order-tc-forecast?explain=true" -ContentType "application/json" -Body $uc1
$r | ConvertTo-Json -Depth 6
$r.explanation.text
```

Or use the browser: http://localhost:8000/docs → endpoint → **Try it out** → paste the JSON → **Execute**.

### Point at in either response

* `rule_engine` next to the AI result: the current logic remains the benchmark.
* `root_cause.breakdown`: progress / material / transmission days that add up to the shift.
* `explanation`: written by the Akasha Copilot from computed facts. `unverified_numbers` and
  `consistency_flags` show the checks that keep it honest.
* `guardrail` (UC2): when the PPA penalty rule sets the class over the model, it says so.

## 3. Results to show — and how to say them

| | AI | Rule engine | Say |
|---|---|---|---|
| Supplier lead time (measured on held-out POs) | 30-day error | 70-day error | "Less than half the error of the fixed lead times." |
| Priority (cross-validated) | macro-F1 0.91 | 0.87 | "Agrees with the business rules and catches the cases the plan date hides." |
| Explanations | every number traced to a computed fact | — | |

## 4. Limitations — state them before the client finds them

1. **One snapshot, tens of projects.** 49 projects as of 9 Oct 2026; about 20 have a site-pace FTC. That is a
   PoC data volume, not a production one.
2. **No actual outcomes yet.** The data has no actual FTC, no actual delay and no recorded P1/P2. The FTC
   shift learns from the planner's own site-pace forecast, and priority learns from the business rule applied
   to the realistic date. Supplier lead time is the one model trained on measured history (Ariba).
3. **The site-readiness model is the weakest part.** In cross-validation it does not beat a simple portfolio
   average; the `confidence` field (~0.2) says so. The demo projects are in the snapshot it learned from, so
   their numbers are close to the planner's own forecast. A new or what-if project is a genuine prediction,
   with that uncertainty.
4. **Weather, vendor performance, payment status, transmission line progress** are not in the sources yet;
   weather shows as "no data" in the root cause.
5. **Category comes from the P6 name.** ARE55L_S03 is "MERCHANT" in P6 but shown as PPA. Pass `category` to
   use the business view.
6. **The monthly plan is a forecast, not quota-levelled.** Vendor monthly ceilings are checked and flagged
   (`vendor_quota_check`), not redistributed. Site-speed timing assumes the current P6 structure pace holds,
   and that module MWp ≈ structure MWdc.
7. **Domestic orders above ~82 MWp** are beyond anything in the Ariba history; lead time is read at that size
   and the response says so.

**Next step that makes it production-grade:** connect actual FTC dates from P6, keep nightly P6 snapshots for
FTC revision history, and record planner P1/P2. Then the same pipeline retrains on real outcomes.
