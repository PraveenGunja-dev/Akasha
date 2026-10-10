"""
Step 6 - module order plan per project: when modules are needed, whether what
is ordered covers it, and if not, when to order - and why not earlier.

    training_model\\.venv\\Scripts\\python.exe training_model\\models\\order_planner.py

The logic, in planner order (every step is shown with the plan as a reason):

1. NEED, per block (P6). A block needs its module MWp (P6 "Module Installation"
   Material units) on site SITE_BUFFER_DAYS before its module installation
   starts. Start = P6 baseline start shifted by the model's P20 slip for that
   block's module installation - the EARLY side of the forecast, so modules
   are never the reason a block waits, but a site that is clearly behind its
   baseline does not get modules months before it can use them.
2. SUPPLY, per project (SAP - project level only). On site now = SAP received
   minus P6 installed. In the pipeline = ordered minus received, expected at
   PO date + P80 lead time (+ the typical delivery span) for its origin.
3. COVERAGE. Blocks are taken in need-by order against supply arriving by
   each need-by date; the first block it cannot cover is where a shortfall
   starts.
4. ORDER-BY, for the MW nothing covers: latest safe date = need-by of the
   first uncovered block - P80 lead time - typical delivery span. Import and
   domestic each get their own date.
5. WHY NOT EARLIER. Ordering more than HOLD_WINDOW_DAYS before the latest
   safe date parks modules in stores (capital, space, handling damage, price
   risk), so the plan says "hold until" with the date the window opens.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (HOLD_WINDOW_DAYS, LEAD_TIME_QUANTILE, RAW, REGISTRY,  # noqa: E402
                    SITE_BUFFER_DAYS)

D = lambda n: pd.Timedelta(days=int(n))  # noqa: E731


def lead(lt, origin):
    o = lt["by_origin"][origin]
    first = o["po_to_first_receipt"][LEAD_TIME_QUANTILE]
    span = o["delivery_span"]["p50"] or 0
    return first, span, o["po_to_first_receipt"]["n"]


def latest_forecast():
    versions = sorted((REGISTRY / "ftc_slip").glob("v*/forecast.csv"))
    return pd.read_csv(versions[-1]) if versions else None


def main():
    acts = pd.read_csv(RAW / "p6_activities.csv.gz",
                       parse_dates=["baseline_start_date", "actual_start_date", "actual_finish_date"])
    proj = pd.read_csv(RAW / "p6_projects.csv.gz", parse_dates=["data_date"])
    mwp = pd.read_csv(RAW / "module_install_mwp.csv.gz")
    po = pd.read_csv(RAW / "module_po_lines.csv.gz", parse_dates=["document_date", "po_first_release"])
    links = pd.read_csv(RAW / "project_wbs.csv.gz")
    lt = json.loads((REGISTRY / "lead_time" / "lead_times.json").read_text())
    fc = latest_forecast()
    # Forecast shifts are used only where the model was tested (confidence
    # "tested"); further out the plan stays on the P6 baseline.
    slip20 = {} if fc is None else {
        (r.project_id, int(r.block)): r.slip_p20 for r in fc[(fc.kind == "module_installation")
                                                              & (fc.confidence == "tested")].itertuples()}

    mi = acts[acts.kind == "module_installation"].merge(mwp, on=["project_object_id", "activity_id"]) \
        .merge(proj[["project_object_id", "project_id", "data_date"]], on="project_object_id")
    share = links.groupby(["project_id", "wbs_key"]).share.sum().reset_index()
    po["po_date"] = po.document_date.fillna(po.po_first_release)
    pol = po.merge(share, on="wbs_key")
    pol["ordered"], pol["received"] = pol.ordered_mw * pol.share, pol.delivered_mw_now.fillna(0) * pol.share

    started_blocks = set(map(tuple, acts[acts.block.notna() & acts.actual_start_date.notna()]
                             [["project_object_id", "block"]].drop_duplicates().values))
    wbs_of = links.groupby("project_id").wbs_key.apply(lambda s: ", ".join(sorted(set(s)))).to_dict()
    plans, block_rows = [], []
    for pid, g in mi.groupby("project_id"):
        # Progress is as of the P6 data date; ordering decisions are as of
        # today - a "hold until" date already gone is an order-now.
        as_of = max(g.data_date.iloc[0].normalize(), pd.Timestamp.today().normalize())
        installed = float(g.installed_mwp.fillna(0).sum())
        p = pol[pol.project_id == pid]
        ordered, received = float(p.ordered.sum()), float(p.received.sum())
        stock = max(0.0, received - installed)
        reasons = []

        # 1. Need per open block.
        need = []
        for b in g.itertuples():
            planned = float(b.planned_mwp or 0)
            remaining = planned - float(b.installed_mwp or 0)
            # P6 installed units end fractionally short of planned on finished
            # blocks; that residue is rounding, not modules still to fit.
            if pd.isna(b.block) or pd.notna(b.actual_finish_date) or remaining <= max(0.5, 0.02 * planned):
                continue
            s = slip20.get((pid, int(b.block)), 0)
            start = b.actual_start_date if pd.notna(b.actual_start_date) else b.baseline_start_date + D(s)
            need_by = start - D(SITE_BUFFER_DAYS) if pd.notna(start) else pd.NaT
            # A block already past its start date needs its modules now.
            overdue = pd.notna(need_by) and need_by < as_of
            need_by = max(need_by, as_of) if pd.notna(need_by) else pd.NaT
            need.append({"block": int(b.block), "mwp": remaining,
                         "site_started": (b.project_object_id, b.block) in started_blocks, "baseline_start": b.baseline_start_date,
                         "forecast_shift_days": int(s), "need_by": need_by, "overdue": overdue})
        need = sorted(need, key=lambda x: (pd.isna(x["need_by"]), x["need_by"]))
        remaining_need = sum(x["mwp"] for x in need)

        # 2. Supply arriving over time.
        arrivals = [(as_of, stock, "on site")]
        for _, r in p.groupby("po").agg(ordered=("ordered", "sum"), received=("received", "sum"),
                                        po_date=("po_date", "min"), origin=("origin", "first")).iterrows():
            open_mw = r.ordered - r.received
            if open_mw <= 0.01:
                continue
            origin = r.origin if r.origin in lt["by_origin"] else "import"
            first, span, _ = lead(lt, origin)
            eta = r.po_date + D(first + span) if pd.notna(r.po_date) else pd.NaT
            late = pd.notna(eta) and eta < as_of
            if late:
                transit = lt["by_origin"][origin]["transit"][LEAD_TIME_QUANTILE]
                reasons.append(f"PO {r.name}: {open_mw:.1f} MW still open past its typical lead time "
                               f"- assumed on site within {transit} days (P80 transit).")
                eta = as_of + D(transit)
            arrivals.append((eta, open_mw, f"PO {r.name}"))
        arrivals.sort(key=lambda a: (pd.isna(a[0]), a[0]))
        pipeline = sum(a[1] for a in arrivals[1:])

        # 3. Coverage, block by block.
        cum_need, short_from, short_block = 0.0, None, None
        for x in need:
            cum_need += x["mwp"]
            avail = sum(m for d, m, _ in arrivals if pd.notna(d) and pd.notna(x["need_by"]) and d <= x["need_by"])
            x["covered"] = avail >= cum_need - 0.01
            x["supply_by_need_by"] = avail
            if not x["covered"] and short_from is None:
                short_from, short_block = x["need_by"], x["block"]
            block_rows.append({"project_id": pid, **x})
        uncovered = max(0.0, remaining_need - stock - pipeline)

        # 4-5. Order-by and hold.
        plan = {"project_id": pid, "as_of": as_of.date(), "p6_data_date": g.data_date.iloc[0].date(), "remaining_need_mwp": round(remaining_need, 1),
                "installed_mwp": round(installed, 1), "ordered_mwp": round(ordered, 1),
                "received_mwp": round(received, 1), "stock_on_site_mwp": round(stock, 1),
                "pipeline_mwp": round(pipeline, 1), "uncovered_mwp": round(uncovered, 1),
                "shortfall_from": short_from.date() if short_from is not None and pd.notna(short_from) else None,
                "shortfall_block": short_block, "no_sap_po": ordered <= 0.01}
        if ordered <= 0.01:
            keys = wbs_of.get(pid)
            reasons.append("SAP has no module PO on this project's WBS"
                           + (f" ({keys})" if keys else " (no WBS mapped in the register)")
                           + ". Either modules are not ordered yet, or they come from a PO booked to "
                             "another WBS - map it in the register and the plan will count it.")
        if not need:
            plan["action"] = "Complete"
            reasons.append("Every block's modules are installed.")
        elif uncovered <= 0.01 and short_from is None:
            plan["action"] = "Covered"
            reasons.append(f"Stock on site ({stock:.1f} MW) and open POs ({pipeline:.1f} MW) cover all "
                           f"{remaining_need:.1f} MW still to install, each before its block needs it.")
        else:
            # The first block nothing covers - the MW beyond stock + pipeline.
            cum, first_uncov = 0.0, None
            for x in need:
                cum += x["mwp"]
                if cum > stock + pipeline + 0.01:
                    first_uncov = x
                    break
            target = first_uncov or next(x for x in need if not x["covered"])
            if pd.isna(target["need_by"]):
                plan["action"] = "No P6 dates"
                reasons.append(f"Block {target['block']} has no baseline module installation date in P6, "
                               "so no need-by date can be worked out.")
                plan["why"] = " ".join(reasons)
                plans.append(plan)
                continue
            if not target["site_started"]:
                reasons.append(f"No work has started on block {target['block']} yet, so its P6 date "
                               "may be optimistic; the forecast adjusts it once the model is applied.")
            for origin in ("import", "domestic"):
                first, span, n = lead(lt, origin)
                plan[f"order_by_{origin}"] = (target["need_by"] - D(first + span)).date() \
                    if pd.notna(target["need_by"]) else None
                plan[f"lead_{origin}_days"] = first + span
            ob_i, ob_d = plan["order_by_import"], plan["order_by_domestic"]
            today = as_of.date()
            hold_until = (pd.Timestamp(ob_i) - D(HOLD_WINDOW_DAYS)).date() if ob_i else None
            reasons.append(f"Block {target['block']} needs modules on site by {target['need_by'].date()} "
                           f"(module installation start {SITE_BUFFER_DAYS} days later"
                           + (f", forecast {target['forecast_shift_days']:+d} days vs P6 baseline" if
                              target["forecast_shift_days"] else ", on the P6 baseline") + ").")
            if uncovered > 0.01:
                reasons.append(f"{uncovered:.1f} MW is not on any PO yet.")
            else:
                reasons.append(f"Enough is ordered in total, but block {short_block} needs modules before "
                               f"open POs are expected ({short_from}).")
            if ob_i and today < hold_until:
                plan["action"] = f"Hold until {hold_until}"
                reasons.append(f"Import order-by is {ob_i} ({plan['lead_import_days']} days P80 lead + span). "
                               f"Ordering before {hold_until} parks modules in stores for over "
                               f"{HOLD_WINDOW_DAYS} days.")
            elif ob_i and today <= ob_i:
                plan["action"] = "Order now (import)"
                reasons.append(f"Inside the order window: import order-by is {ob_i}.")
            elif ob_d and today <= ob_d:
                plan["action"] = "Order now (domestic)"
                reasons.append(f"Import is too late (order-by was {ob_i}); domestic order-by is {ob_d} "
                               f"({plan['lead_domestic_days']} days lead).")
            else:
                plan["action"] = "Not ordered - needed now" if ordered <= 0.01 else "Late - expedite"
                reasons.append(f"Even domestic (order-by {ob_d}) arrives after block {target['block']} "
                               f"needs it; expect the block to wait for modules.")
        plan["why"] = " ".join(reasons)
        plans.append(plan)

    out = REGISTRY / "order_plan"
    out.mkdir(parents=True, exist_ok=True)
    plans = pd.DataFrame(plans)
    plans.to_csv(out / "order_plan.csv", index=False)
    pd.DataFrame(block_rows).to_csv(out / "block_need.csv", index=False)
    print(plans.action.value_counts().to_string())
    print(plans[["project_id", "action", "remaining_need_mwp", "stock_on_site_mwp", "pipeline_mwp",
                 "uncovered_mwp"]].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
