"""
Module Deliveries & Forecast API
─────────────────────────────────
Aggregates SAP PO, Inventory, Trial Run, and P6 data into a single
per-project view that mirrors the CEO's static PDF tracker.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, text, or_
from typing import Optional
import re
from datetime import datetime

from database import get_db
import models

router = APIRouter(prefix="/api/module-deliveries", tags=["Module Deliveries"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_wattage_from_text(short_text: str) -> Optional[float]:
    """Extract wattage (e.g. 620W) from SAP short_text and convert to MW."""
    if not short_text:
        return None
    m = re.search(r'(\d{3,4})\s*(?:W|Wp|w)', short_text)
    return float(m.group(1)) / 1_000_000 if m else None


def _wbs_key(wbs: str) -> Optional[str]:
    """The exact WBS element, normalised for matching.

    For H- codes (e.g. H-51XS-01-01), this cuts the prefix to 6 characters (H-51XS) 
    because the rest of the string represents block/sub-elements, but the PO belongs 
    to the project level.
    For non-H codes (e.g. GWL64.2303.M.00001), it leaves them intact so dot-delimited
    codes don't improperly collapse.
    """
    if not wbs:
        return None
    key = wbs.strip().upper()
    if key.startswith('H-'):
        return key[:6]
    return key or None


def _safe_float(v, default=0.0):
    try:
        return float(v) if v else default
    except (ValueError, TypeError):
        return default


# p6_project.parent_eps_name (Primavera's ParentEPSName) doubles as an EPC
# contractor field for most projects, but these values are region/status
# folders in the P6 EPS hierarchy, not contractors.
NON_EPC_EPS_LABELS = {"Khavda", "Rajasthan", "AGEL Projects", "Superseded", "Other (Outside Khavda)"}


# ── Main Endpoint ────────────────────────────────────────────────────────────

@router.get("/summary")
def get_module_deliveries_summary(db: Session = Depends(get_db)):
    """
    Returns per-project module delivery data aligned to the PDF tracker columns.
    Every row represents one project_mapping entry that has a valid capacity.
    """

    # 1. Load all solar projects with capacity (modules are a solar-only concept;
    #    Wind entries have no module tracking and pollute this view).
    mappings = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.capacity_mwac.isnot(None),
        models.ProjectMapping.capacity_mwac > 0,
        models.ProjectMapping.category != 'Wind',
        models.ProjectMapping.mms_type != 'Wind',
    ).all()

    # 2. Pre-fetch all SAP PO data for modules, keyed by WBS prefix
    #    We query once and bucket in Python to avoid N+1.
    all_module_pos = db.execute(text("""
        SELECT wbs_element,
               SUM(po_quantities_mw)                                AS ordered_mw,
               SUM(delivered_qty * mw_multiplication_factor)        AS delivered_mw,
               SUM(still_to_deliver_qty * mw_multiplication_factor) AS in_transit_mw
        FROM mt_poamount
        WHERE (material_name ILIKE '%module%' OR short_text ILIKE '%module%')
          AND mw_multiplication_factor IS NOT NULL
          AND mw_multiplication_factor > 0
        GROUP BY wbs_element
    """)).fetchall()

    # Build a dict keyed by the exact WBS element -> aggregated values
    po_by_wbs: dict[str, dict] = {}
    for row in all_module_pos:
        key = _wbs_key(row[0] or "")
        if not key:
            continue
        bucket = po_by_wbs.setdefault(key, {"ordered": 0, "delivered": 0, "in_transit": 0})
        bucket["ordered"] += _safe_float(row[1])
        bucket["delivered"] += _safe_float(row[2])
        bucket["in_transit"] += _safe_float(row[3])

    # 2b. Several projects can carry the SAME WBS element (e.g. H-54S2-01-01 is
    #     on both ARE55L_A01 150MW and ARE55L_A02 125MW), and SAP cannot tell
    #     them apart. Giving each the full bucket double-counted the portfolio
    #     by ~21% ordered / ~24% received, so the bucket is apportioned by
    #     capacity instead (user decision 2026-09-19). One project on a WBS
    #     keeps 100% of it, so the common case is unaffected.
    cap_share_by_wbs: dict[str, float] = {}
    for m in mappings:
        for wbs_col in (m.module_wbs, m.age6l, m.spv_plant_code):
            key = _wbs_key(wbs_col)
            if key and key in po_by_wbs:
                cap = _safe_float(m.capacity_mwdc) or _safe_float(m.capacity_mwac) * _safe_float(m.ol or "1.35", 1.35)
                cap_share_by_wbs[key] = cap_share_by_wbs.get(key, 0.0) + cap

    # 3. Pre-fetch inventory for modules
    all_module_inv = db.execute(text("""
        SELECT plant_code, SUM(quantity_mw) AS inv_mw
        FROM mt_inventory
        WHERE (material_description ILIKE '%module%' OR material_description ILIKE '%pv%')
          AND quantity_mw IS NOT NULL
          AND quantity_mw > 0
        GROUP BY plant_code
    """)).fetchall()
    inv_by_plant: dict[str, float] = {}
    for row in all_module_inv:
        pc = (row[0] or "").strip()
        inv_by_plant[pc] = inv_by_plant.get(pc, 0) + _safe_float(row[1])

    # 4. Pre-fetch max COD dates from trial runs
    all_tr = db.execute(text("""
        SELECT project_name_p6, MAX(trial_run_finish) AS max_cod
        FROM mt_trialrun
        GROUP BY project_name_p6
    """)).fetchall()
    cod_by_p6: dict[str, datetime] = {}
    for row in all_tr:
        if row[0] and row[1]:
            cod_by_p6[row[0]] = row[1]

    # Both P6 lookups below join on p6_project.project_id, NOT p.name. P6's
    # project names have inconsistent spacing and suffixes against the
    # mapping sheet ("250MW" vs "250 MW", extra "_Commissioned", "A01e" vs
    # "A01- E"), so a name join silently drops real matches — verified this
    # cost 15 of 17 "missing" AOP projects, all recoverable via project_id
    # (user found 2026-09-19). project_id is the stable key both tables share.
    #
    # SCOD is NOT sourced from a P6 milestone at all (user decision
    # 2026-09-19, after the milestone's own planned_finish_date checked ~3
    # weeks off the reference tracker): SCOD is user-entered (manual_scod)
    # falling back only to a real measured trial-run finish or transmission's
    # charging date, never a P6 plan.

    # 5b. Pre-fetch EPC contractor from Primavera's ParentEPSName (p6_project.parent_eps_name).
    #     Some EPS values are region/status groupings, not contractors — exclude those.
    all_p6_epc = db.execute(text("""
        SELECT project_id, parent_eps_name FROM p6_project
        WHERE parent_eps_name IS NOT NULL AND project_id IS NOT NULL
    """)).fetchall()
    p6_epc_by_pid: dict[str, str] = {}
    for row in all_p6_epc:
        if row[0] and row[1] and row[1] not in NON_EPC_EPS_LABELS:
            p6_epc_by_pid[row[0]] = row[1]

    # 5c. Pre-fetch AOP (Plan) from P6's project-level COD Finish Milestones
    #     (e.g. "COD Certification Finish", "COD 50 MW", "COD - Phase-I
    #     (50MW)") — the baseline finish date is a fixed commitment, distinct
    #     from the trial-run / COD cascade used for SCOD. Excludes block-level
    #     "Block-01 - COD" activities by requiring the name to start with COD.
    #     A multi-phase project takes its LATEST phase's date (user decision
    #     2026-09-19, same rule as Connectivity Phase).
    all_p6_aop = db.execute(text("""
        SELECT p.project_id, MAX(a.baseline_finish_date) AS aop
        FROM p6_activity a
        JOIN p6_project p ON p.p6_object_id = a.project_object_id
        WHERE a.name ILIKE 'COD%' AND a.type = 'Finish Milestone'
          AND a.baseline_finish_date IS NOT NULL AND p.project_id IS NOT NULL
        GROUP BY p.project_id
    """)).fetchall()
    aop_by_pid: dict[str, datetime] = {row[0]: row[1] for row in all_p6_aop if row[0]}

    # 5d. Pre-fetch FTC (First Time Charging) from P6. Used to compute
    #     the TC Date (-45 days) and Module Date (-lead time).
    #     Restricted to the project's Milestones WBS branch (wbs_name
    #     'MILESTONE(S)' or a 'PHASE-n (xx MW)' sub-node under it) — P6 also
    #     carries a per-block "Block-NN - First Time Charging" Finish Milestone
    #     under the CONSTRUCTION-COMMISSIONING WBS for every block, which is
    #     construction-progress tracking, not the project/phase FTC commitment,
    #     and was inflating this into a list of per-block dates (user report
    #     2026-09-20).
    all_p6_ftc = db.execute(text("""
        SELECT p.project_id, a.name, a.planned_finish_date, a.actual_finish_date, a.wbs_name, a.wbs_object_id
        FROM p6_activity a
        JOIN p6_project p ON p.p6_object_id = a.project_object_id
        WHERE (a.name ILIKE '%First Time Charging%' OR a.name ILIKE '%FTC%')
          AND a.type = 'Finish Milestone'
          AND (a.wbs_name ILIKE '%MILESTONE%' OR a.wbs_name ILIKE 'PHASE-%')
          AND p.project_id IS NOT NULL
        ORDER BY COALESCE(a.planned_finish_date, a.actual_finish_date) ASC
    """)).fetchall()
    
    import re
    # Dictionary mapping project_id -> wbs_object_id -> list of phase dicts
    ftc_phases_by_pid: dict[str, dict[int, list[dict]]] = {}
    for row in all_p6_ftc:
        pid, name, p_dt, a_dt, wbs_name, wbs_id = row[0], row[1], row[2], row[3], row[4], row[5]
        
        # Determine the working date (actual if completed, else planned)
        dt = a_dt if a_dt else p_dt
        if not dt:
            continue
            
        # Parse phase
        match = re.search(r'(Phase[\s\-]*[IV]+)', name, re.IGNORECASE)
        phase = ""
        if match:
            phase_num = match.group(1).upper().replace('PHASE', '').replace('-', '').strip()
            phase = f"Ph-{phase_num}"
            
        # Parse MWac capacity from name or wbs_name
        mw_ac = 0.0
        mw_match = re.search(r'(\d+(?:\.\d+)?)\s*MW', name + " " + wbs_name, re.IGNORECASE)
        if mw_match:
            mw_ac = float(mw_match.group(1))
            
        if pid not in ftc_phases_by_pid:
            ftc_phases_by_pid[pid] = {}
        if wbs_id not in ftc_phases_by_pid[pid]:
            ftc_phases_by_pid[pid][wbs_id] = []
            
        ftc_phases_by_pid[pid][wbs_id].append({
            "phase": phase,
            "dt": dt,
            "is_completed": a_dt is not None,
            "mw_ac": mw_ac
        })

    # 6. Pre-fetch transmission SCOD (last-resort fallback for the SCOD cascade)
    all_tc = db.execute(text("""
        SELECT mapping_id, MAX(scd) AS scod
        FROM tc_network_edge
        WHERE mapping_id IS NOT NULL
        GROUP BY mapping_id
    """)).fetchall()
    tc_scod_by_mapping: dict[int, str] = {row[0]: row[1] for row in all_tc if row[1]}

    # 6b. Connectivity phase from the transmission portal. A project's
    #     transmission often spans more than one Khavda phase; the last phase
    #     governs, since that is when the project is fully connected
    #     (user decision 2026-09-19: Phase II + III -> Phase III).
    all_tc_phase = db.execute(text("""
        SELECT DISTINCT mapping_id, phase
        FROM tc_project_entry
        WHERE mapping_id IS NOT NULL AND phase IS NOT NULL AND phase <> ''
    """)).fetchall()
    phase_by_mapping: dict[int, set] = {}
    for row in all_tc_phase:
        phase_by_mapping.setdefault(row[0], set()).add((row[1] or "").strip())

    PHASE_ORDER = {"Phase I": 1, "Phase II": 2, "Phase III": 3, "Phase IV": 4, "Phase V": 5}

    def _phase_label(mapping_id: int) -> str:
        """The latest phase the project's transmission spans."""
        found = {p for p in phase_by_mapping.get(mapping_id, set()) if p}
        if not found:
            return ""
        return max(found, key=lambda p: PHASE_ORDER.get(p, 0))

    # 7. Build per-project rows
    projects = []
    totals = {
        "total_mwac": 0, "total_mwp": 0,
        "ordered_mwp": 0, "balance_ordering_mwp": 0,
        "received_mwp": 0, "erection_mwp": 0,
        "inventory_mwp": 0, "under_transit_mwp": 0,
        "balance_dispatch_mwp": 0, "completed_ftc_mwp": 0,
    }

    # Type breakdown accumulators
    type_breakdowns: dict[str, dict] = {}

    for i, m in enumerate(mappings):
        cap_mwac = _safe_float(m.capacity_mwac)
        cap_mwp = _safe_float(m.capacity_mwdc) or cap_mwac * _safe_float(m.ol or "1.35", 1.35)

        # SAP PO data, apportioned by this project's share of the capacity on
        # its WBS element (share == 1.0 whenever it is the only project there).
        ordered = 0.0
        delivered = 0.0
        in_transit = 0.0
        po_shared = False
        share = 0.0
        
        for wbs_col in (m.module_wbs, m.age6l, m.spv_plant_code):
            wbs_key = _wbs_key(wbs_col)
            po_data = po_by_wbs.get(wbs_key, {}) if wbs_key else {}
            if po_data:
                wbs_total_cap = cap_share_by_wbs.get(wbs_key, 0.0) if wbs_key else 0.0
                curr_share = (cap_mwp / wbs_total_cap) if wbs_total_cap > 0 else 0.0
                
                ordered += _safe_float(po_data.get("ordered", 0)) * curr_share
                delivered += _safe_float(po_data.get("delivered", 0)) * curr_share
                in_transit += _safe_float(po_data.get("in_transit", 0)) * curr_share
                
                if wbs_total_cap > 0 and abs(curr_share - 1.0) > 1e-9:
                    po_shared = True
                    share = curr_share

        # Inventory
        plant_codes = []
        if m.spv_plant_code:
            plant_codes = [pc.strip() for pc in m.spv_plant_code.split(',')]
        inv = sum(inv_by_plant.get(pc, 0) for pc in plant_codes)

        # Balance calculations
        balance_ordering = max(cap_mwp - ordered, 0) if ordered > 0 else cap_mwp
        balance_dispatch = max(ordered - delivered, 0) if delivered > 0 else ordered

        # SCOD: manual override (user-entered in this tracker) takes precedence
        # over the fallback cascade trial_run -> TC. No P6 milestone fallback —
        # see note above.
        p6_name = m.project_name_from_p6 or ""
        scod = None
        scod_source = None
        if m.manual_scod:
            scod = m.manual_scod
            scod_source = "manual_lta" if m.manual_scod_is_lta else "manual"
        elif p6_name in cod_by_p6:
            scod = cod_by_p6[p6_name]
            scod_source = "trial_run"
        elif m.id in tc_scod_by_mapping:
            scod = tc_scod_by_mapping[m.id]
            scod_source = "tc"

        # AOP (Plan): baseline finish of the "COD Certification Finish" P6
        # milestone. No fallback — a transmission ECOD is a different
        # commitment and would misrepresent this specific date.
        aop_plan = aop_by_pid.get(m.project_id)

        # Determine delivery status
        if ordered > 0 and delivered >= ordered * 0.95:
            status = "delivered"
        elif ordered > 0 and delivered > 0:
            status = "in_progress"
        elif ordered > 0:
            status = "ordered"
        else:
            status = "pending"

        # Source type (for breakdown)
        source_type = m.source_of_origin or "Unknown"
        if source_type == "India":
            source_type = "ALMM"  # Default mapping, user can refine

        # FTC, TC, and Module Date logic (multi-phase)
        from datetime import timedelta
        
        # Deduplicate FTC phases if multiple WBS exist
        wbs_dict = ftc_phases_by_pid.get(m.project_id, {})
        wbs_sums = {wid: sum(x["mw_ac"] for x in milestones) for wid, milestones in wbs_dict.items()}
        total_all_wbs = sum(wbs_sums.values())
        
        ftc_list = []
        if total_all_wbs <= cap_mwac * 1.05:
            # Additive WBS: Project spans multiple WBS blocks (e.g. FY26-P14)
            for milestones in wbs_dict.values():
                ftc_list.extend(milestones)
        elif wbs_sums:
            # Mutually exclusive WBS (e.g. duplicates like Baiya or Bandha): 
            # Pick the WBS group closest to the project's capacity
            best_wid = min(wbs_sums.keys(), key=lambda wid: abs(wbs_sums[wid] - cap_mwac))
            ftc_list = wbs_dict[best_wid]
            
        # Sort milestones by date so Phase 1 is first
        ftc_list.sort(key=lambda x: x["dt"])
            
        lead_time = 136 if source_type in ("China", "SEA") else 98
        
        ftc_strs, tc_strs, mod_strs = [], [], []
        completed_ftc_mwac = 0.0
        for idx, phase_info in enumerate(ftc_list):
            ph_name = phase_info["phase"]
            dt = phase_info["dt"]
            
            if phase_info["is_completed"]:
                completed_ftc_mwac += phase_info["mw_ac"]
                # Skip showing dates for completed phases since they are no longer pending
                continue
                
            prefix = ph_name if ph_name else (f"Ph-{idx+1}" if len(ftc_list) > 1 else "")
            prefix = f"{prefix}: " if prefix else ""
            
            tc_dt = dt - timedelta(days=45)
            mod_dt = tc_dt - timedelta(days=lead_time)
            
            ftc_strs.append(f"{prefix}{dt.strftime('%d-%b-%y')}")
            tc_strs.append(f"{prefix}{tc_dt.strftime('%d-%b-%y')}")
            mod_strs.append(f"{prefix}{mod_dt.strftime('%d-%b-%y')}")
            
        # Convert completed MWac to MWp
        completed_ftc_mwp = completed_ftc_mwac * _safe_float(m.ol or "1.35", 1.35)
            
        ftc_date_str = ", ".join(ftc_strs)
        tc_date_str = ", ".join(tc_strs)
        module_date_str = ", ".join(mod_strs)

        # SPV: the mapping sheet often has a literal '-' placeholder instead of
        # leaving it blank. Fall back to the SPV code embedded in the P6 name
        # (e.g. "ARE8L_LUDBAY_FT_150MW_PPA" -> "ARE8L").
        spv = (m.spv_name or "").strip()
        if spv in ("", "-") and "_" in p6_name:
            spv = p6_name.split("_")[0]
        elif spv in ("", "-"):
            spv = ""

        row = {
            "sr": i + 1,
            "id": m.id,
            "project_name": m.project or p6_name,
            "spv": spv,
            "plot": m.plot_no or "",
            "category": m.category or "",
            "type": source_type,
            "mms_type": m.mms_type or "",
            "epc": p6_epc_by_pid.get(m.project_id, ""),
            "ol": _safe_float(m.ol or "0"),
            "capacity_mwac": round(cap_mwac, 1),
            "capacity_mwp": round(cap_mwp, 1),
            "connectivity_phase": _phase_label(m.id),
            "lta": m.lta_date.strftime("%d-%b-%y") if isinstance(m.lta_date, datetime) else "",
            "scod": scod.strftime("%d-%b-%y") if isinstance(scod, datetime) else (str(scod) if scod else ""),
            "scod_lta_diff_days": (scod - m.lta_date).days if isinstance(scod, datetime) and isinstance(m.lta_date, datetime) else None,
            "scod_source": scod_source,
            "aop_plan": aop_plan.strftime("%d-%b-%y") if isinstance(aop_plan, datetime) else "",
            "ftc_date": ftc_date_str,
            "tc_date": tc_date_str,
            "module_date": module_date_str,
            "ordered_mwp": round(ordered, 1),
            "balance_ordering_mwp": round(balance_ordering, 1),
            "total_receipt_mwp": round(delivered, 1),
            "erection_done_mwp": 0,  # Need MB51 data with proper movement types
            "module_inventory_mwp": round(inv, 1),
            "under_transit_mwp": round(in_transit, 1),
            "balance_dispatch_mwp": round(balance_dispatch, 1),
            "completed_ftc_mwp": round(completed_ftc_mwp, 1),
            "status": status,
            "p6_name": p6_name,
            "remarks": "",
            # Scope fields. The printed tracker covers Khavda projects that are
            # not yet commissioned (exactly 33 rows); this view is wider, so the
            # UI offers that scope as a filter rather than hiding the rest.
            "cluster": (m.cluster or "").strip(),
            "is_commissioned": bool(m.is_commissioned) or "_Commissioned" in p6_name,
            # True when this WBS element is shared with other projects, so the
            # SAP figures above are this project's capacity share of it rather
            # than a measured per-project number. Surfaced so the UI can say so.
            "po_apportioned": po_shared,
            "po_share_pct": round(share * 100, 1) if po_shared else None,
        }
        projects.append(row)

        # Accumulate totals
        totals["total_mwac"] += cap_mwac
        totals["total_mwp"] += cap_mwp
        totals["ordered_mwp"] += ordered
        totals["balance_ordering_mwp"] += balance_ordering
        totals["received_mwp"] += delivered
        totals["inventory_mwp"] += inv
        totals["under_transit_mwp"] += in_transit
        totals["balance_dispatch_mwp"] += balance_dispatch
        totals["completed_ftc_mwp"] += completed_ftc_mwp

        # Type breakdown
        tb = type_breakdowns.setdefault(source_type, {"mwac": 0, "mwp": 0, "ordered": 0, "received": 0})
        tb["mwac"] += cap_mwac
        tb["mwp"] += cap_mwp
        tb["ordered"] += ordered
        tb["received"] += delivered

    # Round totals
    for k in totals:
        totals[k] = round(totals[k], 1)

    # Round type breakdowns
    for t in type_breakdowns.values():
        for k in t:
            t[k] = round(t[k], 1)

    # Sort projects by SPV then plot
    projects.sort(key=lambda p: (p["epc"] or "ZZZZ", p["spv"], p["plot"]))
    for i, p in enumerate(projects):
        p["sr"] = i + 1

    return {
        "generated_at": datetime.now().isoformat(),
        "totals": totals,
        "projects": projects,
        "type_breakdowns": type_breakdowns,
        "data_coverage": {
            "total_projects": len(mappings),
            "with_sap_data": sum(1 for p in projects if p["ordered_mwp"] > 0),
            "with_scod": sum(1 for p in projects if p["scod"]),
            "with_epc": sum(1 for p in projects if p["epc"]),
        },
    }
