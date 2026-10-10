# How the module forecast and order plan work

For planners and reviewers. Every number the Ordering Schedule shows from this
folder can be traced back to a rule on this page.

---

## The three questions it answers

| Question | Answer comes from | Level |
|---|---|---|
| When will each block really reach FTC? | Trained model on P6 history | Block |
| When will each block start module installation? | Same model | Block |
| Do we have modules in time, and when must we order? | Lead-time statistics + order planner | Project (SAP is project level) |

---

## 1. Where the data comes from

| Source | What we take | Level |
|---|---|---|
| **P6** | Every block activity (piling, MMS, module installation, IDT, cables, FTC application / approval / charging) with baseline and actual dates; module MWp per block (Material units on *Module Installation*) | Block |
| **SAP** (`mt_poamount`) | Module POs - POrd only, PO date, MW ordered, MW delivered | Project (WBS) |
| **SAP ME2J** | PO / PR release dates | PO |
| **Ariba** | Dispatch and goods-receipt dates of module deliveries | PO, allocated to WBS |
| **Register** | Project <-> P6 <-> SAP WBS, capacity, cluster, LTA, SCOD | Project |

Blocks are identified from the P6 activity name (`Block-07 - ...`). SAP does not
record blocks, so supply stays at project level - never split across blocks.

---

## 2. The delay forecast (block milestones)

### What it predicts
**Slip days** = actual finish - P6 baseline finish, for a block's
*Module Installation*, *FTC Application*, *FTC Approval* and *First Time Charging*.
It gives three numbers, not one:

- **P50** - the most likely date (half of similar blocks finished earlier, half later)
- **P20 / P80** - the range: in testing, about 6 in 10 actual dates fell between them

### What it looks at (all "as of today", nothing from the future)
- **The block's own progress vs its baseline** - share of its activities done vs
  due by today; which stages are finished (piling, MMS, modules, IDT, cables,
  SCADA); how many activities are overdue and by how long; how late its finished
  work ran.
- **Earlier steps of the FTC chain** - is the application submitted, approval
  received, module installation finished.
- **How this project's earlier blocks went** - their average FTC delay. The
  single most useful signal once a few blocks have charged.
- **The project overall** - progress vs baseline, number of blocks, the block's
  place in the FTC sequence.
- **Module supply (project level)** - share of capacity ordered and received by
  today, import share.
- **Context** - capacity, cluster, MMS type, LTA and SCOD vs the baseline,
  month (monsoon).

### Why you can trust it - and where not
- **No peeking at the future.** Each training example is rebuilt "as of" a past
  date: only activities finished by then, POs placed by then, receipts posted by
  then count.
- **Copied baselines are removed.** When a project was re-baselined *after* a
  block had already charged, the baseline simply copied the actual date in; those
  97 blocks are dropped, and no example uses a baseline set after its cut-off date.
- **Graded on projects it never saw.** Accuracy is measured by hiding whole
  projects during training (5 groups), then forecasting them.
- **Compared with what you have today** - the P6 baseline date, and a simple
  rule ("same delay as this project's earlier blocks"). The model is only shown
  where it beats both.
- **Every forecast says why** - the three inputs that moved it most, with their
  values, e.g. *"Earlier blocks' FTC delay: 96 days (+41d)"*.

### How accurate it is (model v20261010_1027, LightGBM)
Measured on **projects the model never saw** - 742 FTC forecasts, 121 blocks:

| Average error, days | P6 baseline date | "Same as earlier blocks" | **Model (P50)** |
|---|---|---|---|
| All | 162 | 72 | **42** |
| Block already overdue | 169 | 73 | **35** |
| 0-45 days ahead | 142 | 74 | **44** |
| 46-100 days ahead | 172 | 69 | **51** |
| 100-180 days ahead | 171 | 69 | **44** |
| Within +-30 days | 4% | 24% | **36%** |

CatBoost was trained and graded the same way and came second (49 days).

**This is not "99%".** About 4 in 10 forecasts land within a month; the
average miss is six weeks, against more than five months for the P6 date. That
is the honest level for 134 charged blocks from 18 projects - and it improves
with every block that charges.

### The range (P20-P80) is measured, not assumed
The models' own ranges came out too narrow (they held only 25% of actual
dates). So the range is set from the model's real errors on unseen projects,
per horizon - typically **45 days earlier to 40 days later than P50**. Checked
on held-out projects: **55%** of actual dates fall inside P20-P80 and **77%** on
or before P80 (targets 60% / 80%).

### Tested range
The model was trained and tested on forecasts from 90 days *after* a missed
baseline to 180 days *before* it. Forecasts further out are marked **beyond
tested range**; the order plan keeps the P6 date for those.

### Reading the "why"
Each forecast lists the three inputs that moved it most, starting from a
**typical block** (in this history, a typical block charged ~150 days after its
baseline). *"Earlier blocks' FTC delay: 96 days (+41d)"* means that input moved
this forecast 41 days later than typical. These are **what the model relied
on, not proven causes**: with 18 projects of history, project-level facts such
as the LTA date partly act as a fingerprint for the project.

**Limits, stated plainly**
- Completed solar block FTCs come from **18 projects**. Forecasts for a project
  type with no history (a new cluster, a new MMS type) are less certain - the
  range is the honest signal.
- Nothing in our systems records *why* work is late (approvals, ROW, weather, grid
  availability). The model sees the effect, not the cause.
- Blocks still open past their baseline are not yet in the training set (their
  final date is unknown), which can make forecasts slightly optimistic.

---

## 3. Module lead times (statistics, not a model)

Only 20 module POs have dated receipts (Ariba): 15 import, 5 domestic. That is
too few to train on honestly, so these are measured percentiles, always shown
with their sample size.

| Clock | Meaning |
|---|---|
| **PO -> first receipt** | manufacturing + shipping (+ any call-off) |
| **Transit** | Ariba dispatch -> goods receipt: logistics only |
| **Delivery span** | first -> last receipt of one PO: how long a PO trickles in |

**Early bulk orders** whose first receipt came more than 180 days after the PO
(three import POs: LONGi 422 MW, Jinko 112 MW, Jinko 800 MW) were *called off*
when site needed them - that is planning, not a slow vendor - so they are
listed separately and not averaged into the lead time.

The plan uses the **P80**: 4 in 5 POs arrived sooner.

---

## 4. The order plan (per project)

### Step 1 - When does each block need modules?
`need-by = module installation start - 14 days (site buffer)`

- Installation start = P6 baseline start **shifted by the forecast's P20 slip**
  for that block (only within the tested range; further out it stays on P6). P20 is the *early* side of the forecast: modules are never the
  reason a block waits, but a block that is clearly behind does not get modules
  months before it can use them.
- A block already past its start date needs its modules **now**.
- Quantity = the block's module MWp from P6, minus what is already installed.

### Step 2 - What supply is coming? (project level)
- **On site** = SAP received - P6 installed.
- **In the pipeline** = ordered - received, expected at
  PO date + P80 lead time + typical delivery span for its origin.
- A PO already past its typical lead time is assumed on site within the P80
  transit time - and listed as a reason.

### Step 3 - Is every block covered?
Blocks are taken in need-by order against supply arriving by each need-by
date. The first block that cannot be covered is where a shortfall starts.

### Step 4 - When must we order?
For the MW nothing covers:
`latest safe order date = need-by - (P80 lead time + delivery span)`
calculated separately for import and domestic.

Site progress is read as of the P6 data date; the ordering decision is made as
of **today**, so a "hold until" date that has passed becomes "order now".

### Step 5 - Why not order earlier? (the "hold" rule)
Ordering more than **45 days** before the latest safe date parks modules in
stores: capital tied up, storage space, handling damage, price risk. So the plan
says **Hold until <date>** - the day the order window opens.

### The statuses
| Status | Meaning |
|---|---|
| **Complete** | Every block's modules are installed |
| **Covered** | Stock + open POs reach every block before it needs them |
| **Hold until <date>** | Not needed yet; ordering now would park modules in stores |
| **Order now (import)** | Inside the import order window |
| **Order now (domestic)** | Import can no longer arrive in time; domestic still can |
| **Late - expedite** | POs exist but arrive after a block needs them |
| **Not ordered - needed now** | SAP has no module PO for the project and a block needs modules before any new order could arrive |
| **No P6 dates** | P6 has no module installation baseline for the block |

**"Not ordered"** means *SAP shows no module PO on the project's WBS*. If the
modules come from a bulk PO booked to another WBS, map that WBS to the project
in the register and the plan counts it.

### Assumptions you can change (`config.py`)
| Setting | Value | Why |
|---|---|---|
| `SITE_BUFFER_DAYS` | 14 | unloading, stores, QC, distribution to the block |
| `HOLD_WINDOW_DAYS` | 45 | longest acceptable stay in stores |
| `LEAD_TIME_QUANTILE` | P80 | 4 in 5 POs arrive sooner |

---

## 5. Running it

```powershell
# 1. extract (backend Python - it has the database connection)
backend\venv\Scripts\python.exe training_model\pipelines\extract.py
# 2-6. dataset, training, lead times, forecast, order plan (training Python)
training_model\.venv\Scripts\python.exe training_model\pipelines\build_dataset.py
training_model\.venv\Scripts\python.exe training_model\models\train_ftc.py
training_model\.venv\Scripts\python.exe training_model\models\calibrate.py
training_model\.venv\Scripts\python.exe training_model\models\lead_times.py
training_model\.venv\Scripts\python.exe training_model\models\predict.py
training_model\.venv\Scripts\python.exe training_model\models\order_planner.py
```

Retrain after each P6 sync that closes more blocks: every newly charged block
is a new example, and accuracy is re-measured every time.
