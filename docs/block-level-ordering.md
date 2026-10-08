# Block-level (construction-level) module ordering

Branch: `feature/block-level-ordering` · status: engine built, verified on live data, no UI yet.
Endpoint: `GET /akasha/api/module-deliveries/block-plan?portfolio=&phase=ongoing&buffer_days=15`
Engine: `backend/services/block_ordering.py`

## 1. Why change

The live Ordering Schedule times each phase's whole balance against its **FTC
milestone**. That produces bulk orders and misses how the site actually builds:
blocks take modules one after another, as each block's structure goes up.

P6 shows this directly. Example — Baiya 600 MW, Block-07: FTC 17-Mar-26 and COD
25-Mar-26 are done, yet its Module Installation runs to **31-Aug-26**. An FTC plan
treats those modules as past; the site still needs them every week until August.

## 2. What P6 holds (checked 2026-10-07)

Every block is a chain of construction activities, in Activity-ID order:

```
Piling MMS → Pile Capping → Array Earthing → MMS Erection (Torque Tube → Bracing → Purlin)
→ MMS – RFI Completion → Module Installation → Module RFI → DC Cable → MC4 → Voc → … → FTC → COD
```

| Fact | Value |
|---|---|
| Block "Module Installation" activities | 894, across 52 P6 projects |
| Material resource on each | `Module - Construction` (MWp) |
| MWp per block | median 17 (6 – 19) |
| Planned / installed | 14,786 / 4,350 MWp; 205 blocks complete |
| "MMS – RFI Completion" | 894 — one per block, all 52 projects |
| Achieved install pace (completed blocks) | median 35 days per block |
| Planned pace (open blocks) | median 25 days — plans are faster than the site has been |
| MMS start → module start (observed) | median 51 days (portfolio) |

P6 logic links (predecessors) are **not** synced; the chain is read from each
block's own activities, matched by block number.

## 3. The plan, step by step

For every ongoing solar project in the Ordering Schedule (same projects, same SAP
figures as the live view):

1. **Blocks** — each block's MWp, MWp already installed (P6 actual units) and its
   current Module Installation window.
2. **Delays carry through** — a block whose MMS erection has not started cannot take
   modules: its need starts no earlier than *MMS start + observed lag*. Slip against
   the plan baseline is reported per block.
3. **Pace check** — a window faster than the project's achieved pace (×1.25) is
   stretched to that pace. Labelled *pace-adjusted (inferred)*.
4. **Need by month** — each block's remaining MWp spread evenly across its window.
5. **SCOD / LTA** — each block's expected install finish is checked against the
   project's SCOD and LTA; blocks finishing after either are flagged with MWp.
6. **Net against the pipeline (MRP)** — site stock + in transit + ordered-not-dispatched
   (SAP) covers the earliest needs first; the rest is the shortfall.
7. **Order month** = need month − (supplier lead time + 15-day site buffer). A need
   already inside the lead time is ordered *now* and reported as late.
8. **Verify the quantity** two ways that must agree:
   block MWp − installed − pipeline, and block MWp − SAP ordered.

**Block-wise only.** A project with no block activities is listed as *no block
data*, not planned another way, so the gap is visible.

## 4. First results (live data, 2026-10-08, phase = ongoing)

- 35 projects planned block-wise; **2 have no block data**: MLP T1 (497 MWp balance in
  the FTC plan) and NHPC BOO (16 MWp).
- **7 projects the live schedule orders nothing for** — MWac in the master but no
  MWdc/OL, so its MWp reads 0: NHPC EPC Khavda-I, ARE55L_A18, ARE55L_S09, ASEJ6PL_S07,
  AGE26BL_A03, Ludbay, ACL_A01 (2,350 MWac). P6 holds ~2,950 MWp of blocks for them,
  none ordered in SAP. **Fix the master** (MWdc or OL) whichever plan is used.
- Quantity checks disagree on 3 projects, each a record to correct:
  - AGEL Merchant — P6 shows 200 of 202 MWp installed, SAP 149 MWp ordered.
  - ACL_A01 — 68 MWp installed in P6, no module PO found in SAP for its WBS.
  - Group – Port (Hybrid) — 34 MWp installed, no module PO in SAP.
- Most of the new demand falls **inside the lead time already** (needed before
  ~Feb-27 with 98–136 day lead times), so it lands in "order now" — the plan shows
  how late the portfolio is, not just how much to buy.
- Several rows have module source "Unknown"; they take the default 98-day lead time
  until the master names their source.

## 5. Next steps

1. **Screen** — a Block-level view beside the current schedule: per project the
   blocks behind each month's lot, late MWp, SCOD/LTA flags, and the two
   quantity checks; drill-down to blocks.
2. **Quota levelling** — monthly supplier quotas (MWac) applied to the order lots,
   priority first, then SCOD/LTA risk; pull earlier rather than push past LTA.
3. **Lot sizing** — round lots to the supplier's shipment unit when known.
4. **Monthly re-plan** — the plan follows P6's current dates, which change every
   update, so it is recomputed on every P6 sync.

## 6. AI in the planning — proposal

The order quantities and months stay **deterministic and auditable** (sections 3–4);
AI adds what a deterministic rule cannot, in three layers:

### 6.1 Learned forecasts (a trained model, from our own history)
Train on completed blocks (205 module installs, plus every finished piling / MMS
activity across 52 projects) to predict, for each open block:
- **actual start** given its upstream progress (piling %, MMS stage, RFI), and
- **actual duration** given EPC contractor, MMS type (HSAT / fixed tilt), project,
  season (monsoon), block size and the project's recent pace.

Output is a range (P50 / P80 start and finish), not a single date. Need dates use
P50; risk views use P80. The model is retrained on every P6 sync; its accuracy on
last month's blocks is shown next to it. Everything it produces is labelled
*forecast*, never shown as a P6 date.

### 6.2 Allocation optimiser (when supply is short)
When a supplier's monthly quota binds, decide who gets it with an explicit
objective instead of fixed rules: minimise MWp installed after SCOD and after LTA,
weighted by **priority (P1 > P2 > standard)**, PPA penalty exposure and module source
(China / SEA / ALMM / DCR), subject to quotas, lead times, lot sizes and site
storage. A linear/integer optimiser (e.g. OR-Tools) gives the best allocation and
the reason each project got what it did.

### 6.3 Planning copilot (language model)
A copilot that reads the plan and the forecasts — never invents figures — to:
- explain any month's lot block by block;
- run *what-ifs* ("SEA quota +100 MW", "Block-12 slips 30 days", "make NHPC P1");
- write each project's remark and recommended action;
- answer planners' questions with the source of every number.

### Order of work
Screen (5.1) → quota levelling (5.2) → learned forecasts (6.1) → optimiser (6.2)
→ copilot (6.3). Each step is usable on its own and is compared with the current
FTC plan before anything replaces it.
