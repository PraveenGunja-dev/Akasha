from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Dict, Any, Optional
import json
import time
from datetime import datetime

from database import get_db
import models
from slr_rules import exclude_overhead_lines, po_lines_only, zsps_po_lines_only
from services.project_service import filter_tc_edges_by_kps
from services.progress import nonlabor_units_by_project, project_progress

def _tc_line(t, m):
    """One transmission line as the project drawer shows it. `status` is the raw
    sheet value and is polluted with serial numbers ('8', '16'); consumers must
    read `normalized_status`. Stage fields are 'done/total' strings."""
    return {
        "id": t.id,
        "project": m.project or m.project_name_from_p6,
        "phase": _safe_parse_phase(t.projects),
        "voltage": t.voltage,
        "status": t.status,
        "normalized_status": t.normalized_status,
        "from_label": t.from_label,
        "to_label": t.to_label,
        "length": t.length,
        "foundation": t.foundation,
        "erection": t.erection,
        "stringing": t.stringing,
        "expected_date": t.expected_date,
        "scd": t.scd,
        "charged_date": t.charged_date,
        "contractor": t.contractor,
        "is_delayed": t.is_delayed,
    }


def _safe_parse_phase(projects_json):
    if not projects_json:
        return "Unknown Phase"
    
    if isinstance(projects_json, str):
        if not projects_json.strip().startswith('{') and not projects_json.strip().startswith('['):
            return str(projects_json).strip()
            
        try:
            parsed = json.loads(projects_json)
            if isinstance(parsed, dict):
                phases = parsed.get("phases", [])
                if phases:
                    return phases[0]
            elif isinstance(parsed, list):
                if parsed:
                    return parsed[0]
        except Exception:
            try:
                import ast
                parsed = ast.literal_eval(projects_json)
                if isinstance(parsed, dict):
                    phases = parsed.get("phases", [])
                    if phases:
                        return phases[0]
                elif isinstance(parsed, list):
                    if parsed:
                        return parsed[0]
            except Exception:
                import re
                m = re.search(r'[\'"]phases[\'"]\s*:\s*\[\s*[\'"]([^\'"]+)[\'"]', projects_json)
                if m:
                    return m.group(1)
    return "Unknown Phase"

import re
def _extract_wbs_prefixes(m: models.ProjectMapping) -> list[str]:
    codes = []
    for val in [m.spv_plant_code, m.agel, m.age6l]:
        if val:
            # Extract anything looking like H-XXXX... and take first 6 chars
            matches = [c.strip()[:6] for c in re.findall(r'H-\S+', str(val).strip()) if len(c.strip()) >= 6]
            codes.extend(matches)
    return list(set(codes))

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Simple in-memory cache to prevent 6-8s load times from N+1 queries
_KG_CACHE = {"data": None, "timestamp": 0}
_SUMMARY_CACHE = {"data": None, "timestamp": 0}
_CACHE_TTL = 300  # 5 minutes

@router.get("/summary")
def get_dashboard_summary(portfolio: Optional[str] = None, phase: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    """
    Returns a global portfolio summary and a unified list of all mapped projects
    with data from P6, SAP, and Transmission. Includes all P6 projects even if unmapped.
    """
    global _SUMMARY_CACHE
    cache_key = f"{str(portfolio).lower() if portfolio else 'all'}_{str(phase).lower() if phase else 'all'}"
    
    if not nocache and cache_key in _SUMMARY_CACHE:
        entry = _SUMMARY_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _CACHE_TTL:
            return entry["data"]
            
    query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        p_clean = portfolio.replace('+', ' ').strip().lower()
        # Make filtering robust by splitting into words
        parts = p_clean.split()
        for part in parts:
            query = query.filter(
                (func.lower(models.ProjectMapping.cluster).contains(part)) |
                (func.lower(models.ProjectMapping.category).contains(part)) |
                (func.lower(models.ProjectMapping.project).contains(part))
            )
            
    if phase and phase != "ALL":
        is_comm = True if phase == "Commissioned" else False
        query = query.filter(models.ProjectMapping.is_commissioned == is_comm)
        
    raw_mappings = query.all()
    raw_p6_projects = db.query(models.P6Project).all()
    
    # Filter out Demo projects
    filtered_mappings = []
    for m in raw_mappings:
        name_check = m.project_name_from_p6 or m.project or ""
        if "demo" not in name_check.lower():
            filtered_mappings.append(m)
            
    # Deduplicate mappings to prevent double counting
    dedup = {}
    for m in filtered_mappings:
        if m.project_id:
            if m.project_id not in dedup:
                dedup[m.project_id] = m
            else:
                existing = dedup[m.project_id]
                if len(m.spv_plant_code or '') > len(existing.spv_plant_code or ''):
                    dedup[m.project_id] = m
    filtered_mappings = list(dedup.values())

    if portfolio and portfolio.lower() != "all portfolios":
        mapped_ids = [m.project_id for m in filtered_mappings if m.project_id]
        raw_p6_projects = [p for p in raw_p6_projects if p.project_id in mapped_ids]
    
    mappings = filtered_mappings
    p6_projects = raw_p6_projects
    
    portfolio_summary = {
        "total_mw": 0,
        "achieved_mw": 0,
        "total_projects": 0,
        "delayed_projects": 0,
        "on_track_projects": 0,
        "total_inventory_qty": 0,
        "total_po_qty": 0
    }
    
    project_list = []
    mapped_p6_ids = set()
    
    # --- PRE-FETCH DATA FOR N+1 OPTIMIZATION ---
    cap_data = db.query(models.ProjectMapping.spv_plant_code, func.sum(models.ProjectMapping.capacity_mwac)).group_by(models.ProjectMapping.spv_plant_code).all()
    capacity_by_plant = {str(row[0]).strip(): (row[1] or 1.0) for row in cap_data if row[0]}
    
    inv_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTInventory.plant_code, func.sum(models.MTInventory.quantity_inv)).group_by(models.MTInventory.plant_code).all() if r[0]}

    # We will compute in-transit QTY inline
    it_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTPOAmount.plant_code, func.sum(models.MTPOAmount.still_to_deliver_qty)).filter(zsps_po_lines_only()).group_by(models.MTPOAmount.plant_code).all() if r[0]}
    
    po_qty_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTPOAmount.plant_code, func.sum(models.MTPOAmount.order_quantity)).filter(zsps_po_lines_only()).group_by(models.MTPOAmount.plant_code).all() if r[0]}
    po_val_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTPOAmount.plant_code, func.sum(models.MTPOAmount.net_order_value_inr)).filter(zsps_po_lines_only()).group_by(models.MTPOAmount.plant_code).all() if r[0]}
    po_delivered_val_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTPOAmount.plant_code, func.sum(models.MTPOAmount.delivered_value_inr_cr)).filter(zsps_po_lines_only()).group_by(models.MTPOAmount.plant_code).all() if r[0]}

    # ZSPS (mt_poamount) is the book of record for purchase orders, so the
    # PORTFOLIO figure is read straight off it. Summing the per-project values
    # below instead silently drops every PO whose WBS element matches no
    # project prefix - measured at 59,753 Cr against a ZSPS total of 66,691 Cr,
    # i.e. ~6,938 Cr (10.4%) of committed spend missing from the headline.
    # PO value counts POrd documents only (the SLR definition); PReq
    # requisitions are not orders.
    po_grand = db.query(
        func.sum(models.MTPOAmount.net_order_value_inr),
        func.sum(models.MTPOAmount.delivered_value_inr_cr),
        func.count(func.distinct(models.MTPOAmount.purchasing_document)),
    ).filter(zsps_po_lines_only()).one()
    portfolio_summary["total_po_value"] = round(po_grand[0] or 0, 2)
    portfolio_summary["total_po_delivered_cr"] = round(po_grand[1] or 0, 2)
    portfolio_summary["total_po_count"] = po_grand[2] or 0

    all_inv_wbs = db.query(models.MTInventory.wbs_element, func.sum(models.MTInventory.quantity_inv)).group_by(models.MTInventory.wbs_element).all()
    all_it_wbs = db.query(models.MTPOAmount.wbs_element, func.sum(models.MTPOAmount.still_to_deliver_qty)).filter(zsps_po_lines_only()).group_by(models.MTPOAmount.wbs_element).all()
    # PO aggregates grouped by WBS element. The plant_code join below is unreliable — a
    # project's spv_plant_code (e.g. 'H-51PA') is NOT the SAP plant_code (e.g. '51Y1'), so
    # plant lookups returned 0 for every project (PO value tiles showed ₹0). WBS element
    # matches on both sides (mapping.module_wbs 'H-51Y1-01-01' == mt_poamount.wbs_element).
    all_po_qty_wbs = db.query(models.MTPOAmount.wbs_element, func.sum(models.MTPOAmount.order_quantity)).filter(zsps_po_lines_only()).group_by(models.MTPOAmount.wbs_element).all()
    all_po_val_wbs = db.query(models.MTPOAmount.wbs_element, func.sum(models.MTPOAmount.net_order_value_inr)).filter(zsps_po_lines_only()).group_by(models.MTPOAmount.wbs_element).all()
    all_po_delivered_wbs = db.query(models.MTPOAmount.wbs_element, func.sum(models.MTPOAmount.delivered_value_inr_cr)).filter(zsps_po_lines_only()).group_by(models.MTPOAmount.wbs_element).all()
    all_consumed_wbs = db.query(models.MTMaterialDocument.wbs_element, func.sum(models.MTMaterialDocument.quantity)).group_by(models.MTMaterialDocument.wbs_element).all()

    all_tc_entries = db.query(models.TcProjectEntry).all()
    all_tc_edges = db.query(models.TcNetworkEdge).all()
    
    parsed_edge_phases = {}
    for edge in all_tc_edges:
        parsed_edge_phases[edge.id] = set()
        if edge.projects:
            phase_val = _safe_parse_phase(edge.projects)
            if phase_val and phase_val != "Unknown Phase":
                parsed_edge_phases[edge.id] = {str(phase_val).strip().upper()}
    # Pre-fetch Capacity Overview to get accurate COD and Trial Run MW (and dynamically computed WTG capacity)
    cap_data = get_capacity_overview(portfolio, db)
    proj_cap_dict = {p["project_id"]: p for p in cap_data.get("projects", []) if p["project_id"]}
    
    portfolio_summary["achieved_mw"] = sum(cap_data.get("totals", {}).values())

    _nl_units = nonlabor_units_by_project(db)  # one query, every project
    for m in mappings:
        pm_cap = proj_cap_dict.get(m.project_id, {})
        
        # Try to extract capacity from name as fallback
        fallback_cap = 0
        p6_name_for_cap = str(m.project_name_from_p6 or m.project or "").upper()
        import re
        mw_match = re.search(r'(\d+(?:\.\d+)?)[\s_]*MW', p6_name_for_cap)
        if mw_match:
            fallback_cap = float(mw_match.group(1))
            
        base_cap = m.capacity_mwac if (m.capacity_mwac and m.capacity_mwac > 0) else fallback_cap
        computed_capacity = pm_cap.get("total_capacity", base_cap)
        if computed_capacity == 0:
            computed_capacity = base_cap
            
        portfolio_summary["total_mw"] += computed_capacity
        
        # P6 Data
        p6_data = next((p for p in p6_projects if p.project_id == m.project_id), None)
        if not p6_data and m.project_name_from_p6:
            clean_name = str(m.project_name_from_p6).strip().lower()
            p6_data = next((p for p in p6_projects if p.name and clean_name == str(p.name).strip().lower()), None)
            if not p6_data:
                p6_data = next((p for p in p6_projects if p.name and clean_name in str(p.name).strip().lower()), None)

        is_delayed = False
        schedule_health = "Unknown"
        progress = 0
        
        if p6_data:
            mapped_p6_ids.add(p6_data.project_id)
            # Progress = Σ actual non-labour units / Σ planned non-labour units
            # over every resource assignment (see services/progress.py).
            p6_pct = project_progress(p6_data, _nl_units)[0] * 100
            progress = p6_pct
            is_delayed_proj = False
            
            if p6_data.finish_date_variance and p6_data.finish_date_variance < 0:
                is_delayed_proj = True
            elif p6_data.finish_date and progress < 100:
                if p6_data.baseline_finish_date and p6_data.finish_date.date() > p6_data.baseline_finish_date.date():
                    is_delayed_proj = True
                elif p6_data.scheduled_finish_date and p6_data.finish_date.date() > p6_data.scheduled_finish_date.date():
                    is_delayed_proj = True
                    
            if is_delayed_proj:
                is_delayed = True
                schedule_health = "Delayed"
                portfolio_summary["delayed_projects"] += 1
            else:
                schedule_health = "On Track"
                portfolio_summary["on_track_projects"] += 1
        else:
            schedule_health = "On Track"
            portfolio_summary["on_track_projects"] += 1
                
        # SAP Data Mapping
        # SAP Data Mapping
        wbs_prefixes = _extract_wbs_prefixes(m)
        
        req_qty = 0
        inv_qty = 0
        it_qty = 0
        po_qty = 0
        po_value = 0
        po_delivered_cr = 0
        consumed_qty = 0
        
        if wbs_prefixes:
            for p in wbs_prefixes:
                p_clean = p.lower().replace('-', '')
                if not p_clean: continue
                
                inv_qty += sum(qty for wbs, qty in all_inv_wbs if wbs and qty and str(wbs).lower().replace('-', '').startswith(p_clean))
                it_qty += sum(qty for wbs, qty in all_it_wbs if wbs and qty and str(wbs).lower().replace('-', '').startswith(p_clean))
                po_qty += sum(v for wbs, v in all_po_qty_wbs if wbs and v and str(wbs).lower().replace('-', '').startswith(p_clean))
                po_value += sum(v for wbs, v in all_po_val_wbs if wbs and v and str(wbs).lower().replace('-', '').startswith(p_clean))
                po_delivered_cr += sum(v for wbs, v in all_po_delivered_wbs if wbs and v and str(wbs).lower().replace('-', '').startswith(p_clean))
                consumed_qty -= sum(qty for wbs, qty in all_consumed_wbs if wbs and qty and str(wbs).lower().replace('-', '').startswith(p_clean))

        portfolio_summary["total_inventory_qty"] += inv_qty
        portfolio_summary["total_po_qty"] += po_qty

        # TC Data
        tc_khavda = []
        tc_rajasthan = []
        
        # Direct mappings only
        for edge in all_tc_edges:
            if edge.mapping_id == m.id:
                if edge.region == "Khavda":
                    tc_khavda.append(edge)
                elif edge.region == "Rajasthan":
                    tc_rajasthan.append(edge)
        
        tc_summary = "0 Edges"
        if tc_khavda and tc_rajasthan:
            tc_summary = f"{len(tc_khavda)} Khavda, {len(tc_rajasthan)} Rajasthan Edges"
        elif tc_khavda:
            tc_summary = f"{len(tc_khavda)} Khavda Edges"
        elif tc_rajasthan:
            tc_summary = f"{len(tc_rajasthan)} Rajasthan Edges"
            
        project_list.append({
            "mapping_id": m.id,
            "project_name": m.project or "Unknown Entity",
            "p6_project_name": m.project_name_from_p6 or (p6_data.name if p6_data else "Unknown P6 Name"),
            "capacity_mwac": computed_capacity,
            "cod_mw": pm_cap.get("cod_mw", 0),
            "tr_mw": pm_cap.get("tr_mw", 0),
            "spv_plant_code": m.spv_plant_code,
            "is_commissioned": m.is_commissioned,
            "p6": {
                "id": p6_data.project_id if p6_data else None,
                # Activities key off p6_object_id, so the block/WTG rollup
                # needs it alongside the human-facing project_id.
                "object_id": p6_data.p6_object_id if p6_data else None,
                "health": schedule_health,
                "progress": progress,
                "construction_progress": getattr(p6_data, 'construction_percent_complete', None),
                "start_date": p6_data.start_date if p6_data else None,
                "finish_date": p6_data.finish_date if p6_data else None,
                "planned_start_date": p6_data.planned_start_date if p6_data else None,
                "scheduled_finish_date": p6_data.scheduled_finish_date if p6_data else None,
                "data_date": p6_data.data_date if p6_data else None,
                "must_finish_by_date": p6_data.must_finish_by_date if p6_data else None,
                "baseline_start_date": p6_data.baseline_start_date if p6_data else None,
                "baseline_finish_date": p6_data.baseline_finish_date if p6_data else None,
                "parent_eps_name": p6_data.parent_eps_name if p6_data else None,
                "planned_duration": p6_data.planned_duration if p6_data else 0,
                "actual_duration": p6_data.actual_duration if p6_data else 0,
                "planned_cost": p6_data.planned_cost if p6_data else 0,
                "current_budget": p6_data.current_budget if p6_data else 0,
                "finish_date_variance": p6_data.finish_date_variance if p6_data else 0,
            },
            "sap": {
                "req_qty": round(req_qty, 2),
                "inv_qty": round(inv_qty, 2),
                "it_qty": round(it_qty, 2),
                "po_qty": round(po_qty, 2),
                "po_value": round(po_value, 2),
                "po_delivered_cr": round(po_delivered_cr, 2),
                "consumed_qty": round(consumed_qty, 2),
            },
            "tc": {
                "status": tc_summary,
                "has_data": bool(tc_khavda or tc_rajasthan),
                "data": {
                    "khavda": [_tc_line(t, m) for t in tc_khavda],
                    "rajasthan": [_tc_line(t, m) for t in tc_rajasthan]
                }
            }
        })
        
    # ... inside get_dashboard_summary ...
    portfolio_summary["total_projects"] = len(project_list)
    
    # Global Quality (Pulse) Metrics
    total_ncs = db.query(func.count(models.PulseNC.id)).scalar() or 0
    resolved_ncs = db.query(func.count(models.PulseNC.id)).filter(models.PulseNC.status == 'completed').scalar() or 0
    total_rfis = db.query(func.count(models.PulseRFI.id)).scalar() or 0
    completed_rfis = db.query(func.count(models.PulseRFI.id)).filter(models.PulseRFI.status == 'completed').scalar() or 0
    
    closure_rate = 0
    if total_ncs > 0:
        closure_rate = round((resolved_ncs / total_ncs) * 100, 1)
        
    vendor_col = func.coalesce(models.PulseNC.vendor_name, models.PulseNC.contractor_name, 'Unknown Contractor')
    open_ncs_query = db.query(
        vendor_col, func.count(models.PulseNC.id)
    ).filter(
        models.PulseNC.status != 'completed'
    ).group_by(vendor_col).order_by(func.count(models.PulseNC.id).desc()).limit(15).all()
    
    top_contractor_names = [r[0] for r in open_ncs_query]
    
    contractor_project_ncs = {}
    if top_contractor_names:
        project_ncs_query = db.query(
            vendor_col, models.PulseNC.project_name, func.count(models.PulseNC.id)
        ).filter(
            models.PulseNC.status != 'completed',
            vendor_col.in_(top_contractor_names)
        ).group_by(vendor_col, models.PulseNC.project_name).all()
        
        for vendor, proj, count in project_ncs_query:
            if vendor not in contractor_project_ncs:
                contractor_project_ncs[vendor] = []
                
            matched_mapping = None
            if proj:
                p_lower = proj.lower().strip()
                # Try exact match
                for m in raw_mappings:
                    m_name = (m.project or "").lower().strip()
                    m_p6_name = (m.project_name_from_p6 or "").lower().strip()
                    if (m_name and p_lower == m_name) or (m_p6_name and p_lower == m_p6_name):
                        matched_mapping = m
                        break
                # Try partial match if no exact match
                if not matched_mapping:
                    for m in raw_mappings:
                        m_name = (m.project or "").lower().strip()
                        m_p6_name = (m.project_name_from_p6 or "").lower().strip()
                        if (m_name and m_name in p_lower) or (m_p6_name and m_p6_name in p_lower):
                            matched_mapping = m
                            break

            mapping_id = matched_mapping.id if matched_mapping else None
            p6_id = matched_mapping.project_id if matched_mapping else None
            
            p6_name = proj
            if matched_mapping:
                if matched_mapping.project_name_from_p6:
                    p6_name = matched_mapping.project_name_from_p6
                else:
                    p6_proj = next((p for p in raw_p6_projects if p.project_id == matched_mapping.project_id), None)
                    if p6_proj and p6_proj.name:
                        p6_name = p6_proj.name

            contractor_project_ncs[vendor].append({
                "project_name": proj or "Unknown Project",
                "p6_name": p6_name or "Unknown Project",
                "mapping_id": mapping_id,
                "p6_id": p6_id,
                "open_ncs": count
            })
            
    top_contractors = [
        {
            "name": r[0], 
            "value": r[1],
            "projects": sorted(contractor_project_ncs.get(r[0], []), key=lambda x: x["open_ncs"], reverse=True)
        } for r in open_ncs_query
    ]
        
    portfolio_summary["quality"] = {
        "total_ncs": total_ncs,
        "open_ncs": total_ncs - resolved_ncs,
        "resolved_ncs": resolved_ncs,
        "closure_rate": closure_rate,
        "total_rfis": total_rfis,
        "completed_rfis": completed_rfis,
        "top_contractors": top_contractors
    }
    
    result = {
        "summary": portfolio_summary,
        "projects": project_list
    }
    
    _SUMMARY_CACHE[cache_key] = {"data": result, "timestamp": time.time()}
    return result

@router.get("/projects/{mapping_id}")
def get_project_details(mapping_id: str, db: Session = Depends(get_db)):
    """Get full 360 view for a single project"""
    m = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == mapping_id).first()
    if not m:
        return {"error": "Project not found"}
        
    p6_data = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).first()
    
    # SAP Items
    # Extract WBS prefixes
    wbs_prefixes = _extract_wbs_prefixes(m)

    # 1. Inventory Mapping (MB52)
    inv_query = db.query(models.MTInventory)
    if wbs_prefixes:
        query_conditions = [models.MTInventory.wbs_element.startswith(p) for p in wbs_prefixes]
        from sqlalchemy import or_
        inv_query = inv_query.filter(or_(*query_conditions))
    else:
        inv_query = inv_query.filter(
            (models.MTInventory.plant_code == str(m.spv_plant_code).strip()) |
            (models.MTInventory.plant_code == str(m.agel).strip()) | (models.MTInventory.plant_code == str(m.age6l).strip())
        )
    inventory = inv_query.all()
    
    # 2. PO Items (ME2M) - using wbs_prefixes if available
    po_query = db.query(models.MTPOAmount)
    if wbs_prefixes:
        query_conditions = [models.MTPOAmount.wbs_element.startswith(p) for p in wbs_prefixes]
        from sqlalchemy import or_
        po_query = po_query.filter(or_(*query_conditions))
    else:
        po_query = po_query.filter(
            (models.MTPOAmount.plant_code == str(m.spv_plant_code).strip()) |
            (models.MTPOAmount.plant_code == str(m.agel).strip()) | (models.MTPOAmount.plant_code == str(m.age6l).strip())
        )
    po_items = po_query.all()
    
    # 3. In-Transit Mapping (ME2K Still to Deliver)
    in_transit = [po for po in po_items if (po.still_to_deliver_qty or 0) > 0]
    
    # TC Data from Local DB (Exactly mapped by mapping_id)
    tc_edges = db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == m.id).all()
    
    tc_k_dicts = []
    tc_r_dicts = []
    
    for t in tc_edges:
        d = {c: getattr(t, c) for c in t.__table__.columns.keys()}
        d["project"] = m.project or m.project_name_from_p6
        d["phase"] = _safe_parse_phase(t.projects)
        if t.region == "Khavda":
            tc_k_dicts.append(d)
        elif t.region == "Rajasthan":
            tc_r_dicts.append(d)
    
    return {
        "mapping": {
            "id": m.id,
            "name": m.project or m.project_name_from_p6,
            "capacity_mwac": m.capacity_mwac,
            "project_id": m.project_id,
            "spv_plant_code": m.spv_plant_code,
            "module_wbs": m.module_wbs
        },
        "p6": p6_data,
        "sap": {
            "inventory_summary": round(sum((i.value_unrestricted or 0) for i in inventory) / 10000000, 2),
            "po_summary": round(sum((p.net_order_value or 0) for p in po_items) / 10000000, 2),
            "inventory": inventory,
            "po": po_items,
            "in_transit": in_transit
        },
        "tc": {
            "khavda_edges": tc_k_dicts,
            "rajasthan_edges": tc_r_dicts
        }
    }

@router.get("/search")
def global_search(q: str, db: Session = Depends(get_db)):
    if not q or len(q.strip()) < 2:
        return []
    
    q_lower = q.lower().strip()
    results = []
    
    # 1. Search Projects
    projects = db.query(models.P6Project).filter(
        func.lower(models.P6Project.name).contains(q_lower) | 
        func.lower(models.P6Project.project_id).contains(q_lower)
    ).limit(10).all()
    
    for p in projects:
        results.append({
            "id": f"proj_{p.id}",
            "type": "Project",
            "title": p.name or p.project_id,
            "snippet": f"Status: {p.status}. Start: {p.start_date.strftime('%Y-%m-%d') if p.start_date else 'N/A'}",
            "raw": p.project_id
        })
        
    # Helper to resolve plant_code to project_id
    def get_project_id_from_plant(plant_code):
        if not plant_code: return None
        mapping = db.query(models.ProjectMapping).filter(
            (models.ProjectMapping.spv_plant_code == plant_code) | 
            (models.ProjectMapping.agel == plant_code)
        ).first()
        return mapping.project_id if mapping else None

    # 2. Search Purchase Orders
    pos = db.query(models.MTPOAmount).filter(
        func.lower(models.MTPOAmount.purchasing_document).contains(q_lower) |
        func.lower(models.MTPOAmount.vendor_name).contains(q_lower) |
        func.lower(models.MTPOAmount.material_code).contains(q_lower)
    ).limit(10).all()
    
    for po in pos:
        proj_id = get_project_id_from_plant(po.plant_code)
        results.append({
            "id": f"po_{po.id}",
            "type": "Purchase Order",
            "title": f"PO-{po.purchasing_document}",
            "snippet": f"Vendor: {po.vendor_name}. Value: INR {po.net_order_value or 0:,.2f}. Material: {po.material_code}",
            "raw": proj_id or po.purchasing_document # Fallback if unmapped
        })
        
    # 3. Search Inventory/Materials
    materials = db.query(models.MTInventory).filter(
        func.lower(models.MTInventory.material_code).contains(q_lower) |
        func.lower(models.MTInventory.vendor_code).contains(q_lower) |
        func.lower(models.MTInventory.wbs_element).contains(q_lower)
    ).limit(10).all()
    
    for m in materials:
        proj_id = get_project_id_from_plant(m.plant_code)
        results.append({
            "id": f"mat_{m.id}",
            "type": "Material Component",
            "title": m.material_code,
            "snippet": f"Inventory: {m.quantity_inv} at Plant {m.plant_code}. WBS: {m.wbs_element}",
            "raw": proj_id or m.material_code
        })
        
    # 4. Vendors (unique from POs)
    vendors = db.query(models.MTPOAmount).filter(
        func.lower(models.MTPOAmount.vendor_name).contains(q_lower) |
        func.lower(models.MTPOAmount.vendor_code).contains(q_lower)
    ).limit(5).all()
    
    seen_vendors = set()
    for v in vendors:
        v_key = v.vendor_code or v.vendor_name
        if v_key in seen_vendors:
            continue
        seen_vendors.add(v_key)
        
        proj_id = get_project_id_from_plant(v.plant_code)
        results.append({
            "id": f"vend_{v.id}",
            "type": "Vendor",
            "title": v.vendor_name or v.vendor_code,
            "snippet": f"Vendor Code: {v.vendor_code} (Plant: {v.plant_code})",
            "raw": proj_id or v.vendor_code
        })
        
    return results

@router.get("/knowledge-graph")
def get_knowledge_graph(portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    """
    Returns a single unified knowledge graph with rich detail data per project:
    Root → EPS Regions → Projects (with P6/SAP/TC details) → Key Vendors
    """
    global _KG_CACHE
    cache_key = str(portfolio).lower() if portfolio else "all"
    
    if not nocache and cache_key in _KG_CACHE:
        entry = _KG_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _CACHE_TTL:
            return entry["data"]
        
    nodes = []
    links = []
    seen_vendors = {}
    
    # Root node
    nodes.append({
        "id": "root", "name": "Adani Green Energy", "category": 0,
        "symbolSize": 70, "value": "Enterprise Root"
    })
    
    query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        query = query.filter(
            (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
            (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
        )
    
    all_mappings = query.all()
    portfolio_groups = {}
    
    # Pre-load Capacity Overview to get accurate COD and Trial Run MW
    cap_data = get_capacity_overview(portfolio, db)
    proj_cap_dict = {p["project_id"]: p for p in cap_data.get("projects", []) if p["project_id"]}
    
    # Pre-load TC data for exact project association
    import json
    all_tc_edges = db.query(models.TcNetworkEdge).all()
    all_tc_project_entries = db.query(models.TcProjectEntry).all()
    parsed_edge_phases = {}
    for edge in all_tc_edges:
        parsed_edge_phases[edge.id] = set()
        if edge.projects:
            try:
                parsed = json.loads(edge.projects)
                if isinstance(parsed, dict):
                    parsed_edge_phases[edge.id] = set(str(p).strip().upper() for p in parsed.get("phases", []))
                elif isinstance(parsed, list):
                    parsed_edge_phases[edge.id] = set()
            except:
                pass

    _nl_units = nonlabor_units_by_project(db)
    for m in all_mappings:
        p6 = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).first()
        eps = (p6.parent_eps_name if p6 else None) or "Unassigned"
        
        raw_port = m.cluster or m.category or "Other"
        p_lower = raw_port.lower()
        if "khavda" in p_lower: port_name = "Solar Khavda"
        elif "rajasthan" in p_lower: port_name = "Solar Rajasthan"
        elif "wind" in p_lower: port_name = "Wind"
        elif "bess" in p_lower: port_name = "BESS"
        else: port_name = raw_port
        
        if port_name not in portfolio_groups:
            portfolio_groups[port_name] = {}
            
        if eps not in portfolio_groups[port_name]:
            portfolio_groups[port_name][eps] = []
        
        # ── P6 Schedule Data ──
        health = "unknown"
        progress = 0
        p6_data = None
        if p6:
            progress = round(project_progress(p6, _nl_units)[0] * 100)
            # Multi-signal delay detection:
            # 1. finish_date_variance < 0 (if available)
            # 2. scheduled finish date has passed and project is not complete
            # 3. significant number of delayed activities
            is_delayed = False
            if p6.finish_date_variance and p6.finish_date_variance < 0:
                is_delayed = True
            elif p6.scheduled_finish_date and p6.scheduled_finish_date < datetime.now() and progress < 100:
                is_delayed = True
            else:
                # Check for delayed activities (in progress past planned finish)
                delayed_act_count = db.query(models.P6Activity).filter(
                    models.P6Activity.project_object_id == p6.p6_object_id,
                    models.P6Activity.status == 'In Progress',
                    models.P6Activity.planned_finish_date < datetime.now()
                ).count()
                total_act_count = db.query(models.P6Activity).filter(
                    models.P6Activity.project_object_id == p6.p6_object_id
                ).count()
                if total_act_count > 0 and delayed_act_count / total_act_count > 0.05:
                    is_delayed = True
            health = "delayed" if is_delayed else "on_track"
            p6_data = {
                "start_date": str(p6.start_date) if p6.start_date else None,
                "finish_date": str(p6.finish_date) if p6.finish_date else None,
                "planned_finish": str(p6.scheduled_finish_date) if p6.scheduled_finish_date else None,
                "variance_days": round(p6.finish_date_variance) if p6.finish_date_variance else 0,
                "duration_pct": progress,
                "construction_pct": progress,
                "schedule_pct": progress,
                "status": p6.status or "N/A",
                "eps_name": p6.parent_eps_name or ""
            }
        
        # ── SAP Data ──
        wbs_prefixes = _extract_wbs_prefixes(m)
        sap_data = None
        
        if wbs_prefixes:
            from sqlalchemy import or_, and_
            wbs_filters_po = [models.MTPOAmount.wbs_element.startswith(p) for p in wbs_prefixes]
            wbs_filters_inv = [models.MTInventory.wbs_element.startswith(p) for p in wbs_prefixes]
            po_scope = and_(or_(*wbs_filters_po), zsps_po_lines_only())
            
            po_count = db.query(models.MTPOAmount.purchasing_document).filter(po_scope).distinct().count()
            po_total = db.query(func.sum(models.MTPOAmount.net_order_value)).filter(po_scope).scalar() or 0
            # Delivered value is already stored in crores by the ZSPS ingest.
            po_delivered_cr = db.query(func.sum(models.MTPOAmount.delivered_value_inr_cr)).filter(po_scope).scalar() or 0

            inv_count = db.query(models.MTInventory).filter(or_(*wbs_filters_inv)).count()
            inv_value = db.query(func.sum(models.MTInventory.value_unrestricted)).filter(or_(*wbs_filters_inv)).scalar() or 0

            transit_count = db.query(models.MTPOAmount).filter(
                or_(*wbs_filters_po),
                models.MTPOAmount.still_to_deliver_qty > 0
            ).count()
            
            transit_value = db.query(func.sum(models.MTPOAmount.still_to_deliver_inr)).filter(
                po_scope,
                models.MTPOAmount.still_to_deliver_qty > 0
            ).scalar() or 0

            # Approved demand not yet converted into a purchase order — SLR requisition
            # lines (Type = PReq) carry commitment but no actual. Distinct from po_* (already
            # ordered) and from in_transit (ordered but undelivered).
            wbs_filters_slr = [models.MTSLRData.wbs_element.startswith(p) for p in wbs_prefixes]
            preq_count, preq_value = db.query(
                func.count(models.MTSLRData.id),
                func.sum(models.MTSLRData.commitment_amount)
            ).filter(
                or_(*wbs_filters_slr),
                models.MTSLRData.type == "PReq",
                exclude_overhead_lines(),
            ).first()

            top_vendors = db.query(
                models.MTPOAmount.vendor_name, func.sum(models.MTPOAmount.net_order_value).label("total")
            ).filter(po_scope).group_by(models.MTPOAmount.vendor_name).order_by(func.sum(models.MTPOAmount.net_order_value).desc()).limit(3).all()
            
            top_vendors_list = []
            for v in top_vendors:
                vname = (v[0] or "Unknown").strip()
                parts = vname.split(" ", 1)
                if len(parts) == 2 and parts[0].isdigit():
                    vname = parts[1].strip()
                top_vendors_list.append({
                    "name": vname[:25], 
                    "value_cr": round(v[1] / 10000000, 2) if v[1] else 0
                })
            
            sap_data = {
                "plant_code": ",".join(wbs_prefixes),
                "po_count": round(po_count),
                "po_total_cr": round(po_total / 10000000, 2) if po_total else 0,
                "po_delivered_cr": round(po_delivered_cr, 2) if po_delivered_cr else 0,
                "requirement_count": round(preq_count or 0),
                "requirement_value_cr": round((preq_value or 0) / 10000000, 2),
                "inventory_items": round(inv_count),
                "inventory_value_cr": round(inv_value / 10000000, 2) if inv_value else 0,
                "in_transit_count": round(transit_count),
                "in_transit_cr": round(transit_value / 10000000, 2) if transit_value else 0,
                "top_vendors": top_vendors_list
            }
        
        # ── Transmission Data (Local DB) ──
        tc_data = None
        if m.id:
            tc_progress = m.tc_progress or {}
            lines_charged = tc_progress.get("linesCharged", {})
            
            tc_edges = db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == m.id).all()
            if tc_edges or tc_progress:
                tc_data = {
                    "total_lines": lines_charged.get("total", len(tc_edges)),
                    "charged_lines": lines_charged.get("count", sum(1 for e in tc_edges if str(e.status).strip().lower() == "charged")),
                    "delayed_lines": tc_progress.get("delayed", {}).get("count", sum(1 for e in tc_edges if str(e.status).strip().lower() == "delayed")),
                    "lines": [
                        {
                            "name": f"{e.from_label} \u2192 {e.to_label}", 
                            "status": e.status,
                            "normalized_status": e.normalized_status,
                            "foundation": e.foundation,
                            "erection": e.erection,
                            "stringing": e.stringing,
                            "expected_date": e.expected_date
                        } for e in tc_edges
                    ]
                }
        
        # ── Capacity COD & TR ──
        pm_cap = proj_cap_dict.get(m.project_id, {})
        cod_mw = pm_cap.get("cod_mw", 0)
        tr_mw = pm_cap.get("tr_mw", 0)
        
        fallback_cap = 0
        p6_name_for_cap = str(m.project_name_from_p6 or m.project or "").upper()
        import re
        mw_match = re.search(r'(\d+(?:\.\d+)?)[\s_]*MW', p6_name_for_cap)
        if mw_match:
            fallback_cap = float(mw_match.group(1))
            
        base_cap = m.capacity_mwac if (m.capacity_mwac and m.capacity_mwac > 0) else fallback_cap
        computed_capacity = pm_cap.get("total_capacity", base_cap)
        if computed_capacity == 0:
            computed_capacity = base_cap

        portfolio_groups[port_name][eps].append({
            "id": m.id, "project_id": m.project_id, "name": (m.project_name_from_p6 or m.project or "?")[:28],
            "capacity": computed_capacity, "health": health,
            "progress": progress, "spv": m.spv_name or "?",
            "plant_code": m.spv_plant_code or "?",
            "cod_mw": cod_mw, "tr_mw": tr_mw,
            "p6": p6_data, "sap": sap_data, "tc": tc_data
        })
    
    # Add Portfolio and EPS nodes
    for port_name, eps_dict in portfolio_groups.items():
        port_id = f"port_{port_name.replace(' ', '_')}"
        total_mw_port = sum(sum(p["capacity"] for p in projs) for projs in eps_dict.values())
        cod_mw_port = sum(sum(p.get("cod_mw", 0) for p in projs) for projs in eps_dict.values())
        tr_mw_port = sum(sum(p.get("tr_mw", 0) for p in projs) for projs in eps_dict.values())
        
        nodes.append({
            "id": port_id, "name": port_name, "category": 1,
            "symbolSize": 50,
            "value": f"{len(eps_dict)} Regions",
            "mw_stats": {"total": round(total_mw_port), "cod": round(cod_mw_port), "trial": round(tr_mw_port)}
        })
        links.append({"source": "root", "target": port_id})
        
        for eps_name, projects in eps_dict.items():
            eps_id = f"eps_{port_id}_{eps_name.replace(' ', '_')}"
            total_mw = sum(p["capacity"] for p in projects)
            cod_mw = sum(p.get("cod_mw", 0) for p in projects)
            tr_mw = sum(p.get("tr_mw", 0) for p in projects)
            delayed = sum(1 for p in projects if p["health"] == "delayed")
            
            nodes.append({
                "id": eps_id, "name": eps_name, "category": 2,
                "symbolSize": max(35, min(55, total_mw / 150)),
                "value": f"{len(projects)} projects",
                "mw_stats": {"total": round(total_mw), "cod": round(cod_mw), "trial": round(tr_mw)},
                "delayed": delayed, "on_track": len(projects) - delayed,
                "projects_list": [{"id": p["id"], "name": p["name"], "capacity": p["capacity"], "health": p["health"], "progress": p["progress"]} for p in projects]
            })
            links.append({"source": port_id, "target": eps_id})
            
            for p in projects:
                proj_id = f"proj_{p['id']}"
                nodes.append({
                    "id": proj_id, "project_id": p.get("project_id"), "name": p["name"], "category": 3 if p["health"] == "on_track" else 4,
                    "symbolSize": max(15, min(35, p["capacity"] / 30)),
                    "value": f"{p['capacity']} MW · {p['progress']}%",
                    "health": p["health"], "progress": p["progress"],
                    "spv": p["spv"], "capacity": p["capacity"],
                    "p6": p["p6"], "sap": p["sap"], "tc": p["tc"]
                })
                links.append({"source": eps_id, "target": proj_id})
                
                # Top vendor per project
                if p["plant_code"]:
                    top_po = db.query(models.MTPOAmount).filter(
                        models.MTPOAmount.plant_code == p["plant_code"]
                    ).order_by(models.MTPOAmount.net_order_value.desc()).first()
                    
                    if top_po and top_po.vendor_name:
                        vcode = top_po.vendor_code or top_po.vendor_name
                        vname = (top_po.vendor_name or "Unknown").strip()[:22]
                        
                        if vcode not in seen_vendors:
                            vendor_id = f"vendor_{len(seen_vendors)}"
                            seen_vendors[vcode] = vendor_id
                            nodes.append({
                                "id": vendor_id, "name": vname, "category": 5,
                                "symbolSize": 22,
                                "value": f"Vendor · {vcode}"
                            })
                        
                        links.append({
                            "source": proj_id, "target": seen_vendors[vcode],
                            "lineStyle": {"type": "dashed", "width": 1, "color": "rgba(245,158,11,0.3)"}
                        })
    
    result = {"nodes": nodes, "links": links}
    _KG_CACHE[cache_key] = {"data": result, "timestamp": time.time()}
    return result

@router.get("/capacity-overview")
def get_capacity_overview(portfolio: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Returns Capacity overview based on actual COD and Trial Run milestones.
    Logic:
      - All block/WTG data comes from P6 (MTTrialRun)
      - Solar total capacity from ProjectMapping
      - Wind total capacity = total WTGs from P6 × MW per WTG multiplier
      - If a block has COD → count as COD only (ignore its Trial Run)
      - If a block has Trial Run but NO COD → count as Trial Run only
    """
    # Wind MW per WTG multipliers keyed by p6_object_id
    WIND_MW_PER_WTG = {
        "3074": 5.2, "4707": 5.0, "3075": 5.2, "3076": 5.2,
        "3072": 5.2, "3073": 5.2, "6733": 5.2, "3105": 3.3,
    }
    DEFAULT_WIND_MW = 3.3

    import re

    # Source 1: ProjectMapping for source of truth
    query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        query = query.filter(
            (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
            (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
        )
            
    mappings = query.all()
    
    # Filter out demo projects
    filtered_mappings = []
    for m in mappings:
        name_check = m.project_name_from_p6 or m.project or ""
        if "demo" not in name_check.lower():
            filtered_mappings.append(m)
            
    mappings = filtered_mappings
    
    p6_projs = db.query(models.P6Project).all()
    
    project_map = {}
    obj_id_to_p_name = {}
    
    for pm in mappings:
        # Find corresponding P6 project using robust project_id match
        matching_p6 = next((p for p in p6_projs if p.project_id and pm.project_id and p.project_id.strip() == pm.project_id.strip()), None)
        
        # Fallback to name matching
        if not matching_p6:
            name_to_match = pm.project_name_from_p6 or pm.project
            if name_to_match:
                matching_p6 = next((p for p in p6_projs if p.name and p.name.strip().lower() == name_to_match.strip().lower()), None)
                
        if not matching_p6:
            continue
            
        obj_id = str(matching_p6.p6_object_id)
        display_name = matching_p6.name or pm.project_name_from_p6 or pm.project
        obj_id_to_p_name[obj_id] = display_name
        
        # Type by CLUSTER, not project name — wind projects are named like "AGE25CL PSS-11",
        # with no "wind" text, so name-matching mis-typed them as Solar (capacity came out 0).
        p_type = 'Wind' if 'wind' in str(pm.cluster or '').lower() else 'Solar'
        total_cap = float(pm.capacity_mwac or 0)
        # Fallback: many projects (e.g. Rajasthan BANDHA_500MW) have capacity_mwac=0 but carry
        # the MW in their name. Extract it so their COD capacity isn't computed as zero.
        if total_cap <= 0:
            mw_match = re.search(r'(\d+(?:\.\d+)?)[\s_]*MW', str(pm.project_name_from_p6 or pm.project or ''), re.IGNORECASE)
            if mw_match:
                total_cap = float(mw_match.group(1))
        wtg_mw = WIND_MW_PER_WTG.get(obj_id, DEFAULT_WIND_MW) if p_type == 'Wind' else 0
        
        project_map[obj_id] = {
            'project_id': pm.project_id or '-',
            'project_name': display_name,
            'type': p_type,
            'total_capacity': total_cap,
            'total_blocks': 0,
            'tr_blocks': 0,
            'tr_mw': 0,
            'cod_blocks': 0,
            'cod_mw': 0,
            '_wtg_mw': wtg_mw
        }

    # Source 3: All block/WTG data from P6 (P6Activity table)
    from models import P6Activity
    activities = db.query(P6Activity).filter(
        (
            (P6Activity.name.ilike('%trial run certificate%')) |
            (P6Activity.name.ilike('%trail run certificate%')) |
            (P6Activity.name.ilike('%cod%'))
        ),
        # COD/Trial-Run milestones are taken per project type: Solar from the CONSTRUCTION WBS
        # ('CONSTRUCTION-COMMISSIONING'), Wind from the TESTING & COMMISSIONING WBS (wind files
        # no CODs under a construction WBS). Fetch both branches here; the per-type filter that
        # decides which branch applies to each project is enforced in the loop below.
        (P6Activity.wbs_name.ilike('%construction%') | P6Activity.wbs_name.ilike('%testing%')),
        ~P6Activity.type.ilike('%milestone%')
    ).all()

    # Step 1: Group into unique blocks per project
    block_map = {}
    for act in activities:
        obj_id = str(act.project_object_id)
        
        # CRUCIAL: ONLY process activities for tracked projects in ProjectMapping
        if obj_id not in project_map:
            continue

        # Per-type WBS rule: Solar CODs come from the CONSTRUCTION WBS, Wind CODs from the
        # TESTING & COMMISSIONING WBS. Skip activities that aren't in this project's branch.
        wbs_lc = (act.wbs_name or '').lower()
        if project_map[obj_id]['type'] == 'Wind':
            if 'testing' not in wbs_lc:
                continue
        elif 'construction' not in wbs_lc:
            continue

        p_name = obj_id_to_p_name.get(obj_id)
        act_name = (act.name or "").lower()
        
        # Parse Block/WTG name
        b_name = "Unknown Block"
        block_match = re.search(r'(Block-\d+|WTG\d+)', act.name, re.IGNORECASE)
        if block_match:
            b_name = block_match.group(1).upper()
        else:
            continue # Skip project-level CODs that aren't tied to a specific block/WTG
            
        b_key = f"{obj_id}::{b_name}"
        actual_dt = act.actual_finish_date or act.actual_start_date or act.start_date
        is_cod = "cod" in act_name
        is_tr = "trial run certificate" in act_name or "trail run certificate" in act_name
        is_completed = (act.status == 'Completed')
        
        if b_key not in block_map:
            block_map[b_key] = {
                "_obj_id": obj_id,
                "project": p_name,
                "block": b_name,
                "type": project_map[obj_id]['type'],
                "capacity": 0, # Distributed later
                "has_tr": False,
                "has_cod": False,
                "tr_start": None,
                "tr_finish": None,
                "cod_start": None,
                "cod_finish": None,
                "latest_date": actual_dt
            }

        b = block_map[b_key]
        if actual_dt and (b["latest_date"] is None or actual_dt > b["latest_date"]):
            b["latest_date"] = actual_dt

        if is_cod and is_completed and actual_dt:
            b["has_cod"] = True
            b["cod_start"] = act.actual_start_date or actual_dt
            b["cod_finish"] = act.actual_finish_date or actual_dt
        elif is_tr and is_completed and actual_dt:
            b["has_tr"] = True
            b["tr_start"] = act.actual_start_date or actual_dt
            b["tr_finish"] = act.actual_finish_date or actual_dt

    # Group blocks by project to distribute capacity
    projects_blocks = {}
    for b_key, b in block_map.items():
        obj_id = b["_obj_id"]
        if obj_id not in projects_blocks:
            projects_blocks[obj_id] = []
        projects_blocks[obj_id].append(b)

    # Step 2: Aggregate into project-level and FY-level data
    fy_data = {}
    recent = []
    
    for obj_id, blocks in projects_blocks.items():
        blocks.sort(key=lambda x: x["block"])
        pm = project_map[obj_id]

        # Distribute capacity to blocks
        if pm['type'] == 'Solar':
            import math
            total_cap = pm['total_capacity']
            expected_blocks = math.ceil(total_cap / 12.5) if total_cap > 0 else 0
            cap_per_block = (total_cap / expected_blocks) if expected_blocks > 0 else 0
            
            pm['total_blocks'] = expected_blocks
            for b in blocks:
                b["capacity"] = cap_per_block
        else:
            for b in blocks:
                b["capacity"] = pm['_wtg_mw']
                
        # Now process the blocks for aggregation
        for b in blocks:
            cap = b["capacity"]
            if pm['type'] == 'Wind':
                pm['total_blocks'] += 1

            # Determine the FY for this block based on its milestone date
            actual_dt = b["cod_finish"] or b["cod_start"] or b["tr_finish"] or b["tr_start"]

            # STRICT LOGIC: COD takes priority
            if b["has_cod"]:
                pm['cod_blocks'] += 1
                pm['cod_mw'] += cap

                if actual_dt:
                    fy = f"FY{str(actual_dt.year)[-2:]}" if actual_dt.month >= 4 else f"FY{str(actual_dt.year - 1)[-2:]}"
                    if fy not in fy_data:
                        fy_data[fy] = {"name": fy, "solar_cod": 0, "solar_tr": 0, "wind_cod": 0, "wind_tr": 0}
                    if pm['type'] == 'Solar':
                        fy_data[fy]["solar_cod"] += cap
                    else:
                        fy_data[fy]["wind_cod"] += cap

            elif b["has_tr"]:
                # ONLY if NO COD
                pm['tr_blocks'] += 1
                pm['tr_mw'] += cap

                if actual_dt:
                    fy = f"FY{str(actual_dt.year)[-2:]}" if actual_dt.month >= 4 else f"FY{str(actual_dt.year - 1)[-2:]}"
                    if fy not in fy_data:
                        fy_data[fy] = {"name": fy, "solar_cod": 0, "solar_tr": 0, "wind_cod": 0, "wind_tr": 0}
                    if pm['type'] == 'Solar':
                        fy_data[fy]["solar_tr"] += cap
                    else:
                        fy_data[fy]["wind_tr"] += cap

            # Build recent milestones list
            tr_duration = None
            cod_duration = None
            gap_days = None
            if b["tr_start"] and b["tr_finish"]:
                tr_duration = (b["tr_finish"] - b["tr_start"]).days
            if b["cod_start"] and b["cod_finish"]:
                cod_duration = (b["cod_finish"] - b["cod_start"]).days
            if b["tr_finish"] and b["cod_start"]:
                gap_days = (b["cod_start"] - b["tr_finish"]).days

            status = "Pending"
            if b["has_cod"]:
                status = "COD"
            elif b["has_tr"]:
                status = "Trial Run"

            recent.append({
                "project": b["project"],
                "block": b["block"],
                "type": b["type"],
                "capacity": b["capacity"],
                "status": status,
                "tr_start": b["tr_start"].strftime("%Y-%m-%d") if b["tr_start"] else None,
                "tr_finish": b["tr_finish"].strftime("%Y-%m-%d") if b["tr_finish"] else None,
                "cod_start": b["cod_start"].strftime("%Y-%m-%d") if b["cod_start"] else None,
                "cod_finish": b["cod_finish"].strftime("%Y-%m-%d") if b["cod_finish"] else None,
                "tr_duration": tr_duration,
                "cod_duration": cod_duration,
                "gap_days": gap_days,
                "raw_date": b["latest_date"]
            })

    # Post-processing: Calculate capacity and clean up
    for p in project_map.values():
        # For wind projects with parsed blocks, update total capacity based on WTG count dynamically
        if p['type'] == 'Wind' and p['total_blocks'] > 0:
            p['total_capacity'] = round(p['total_blocks'] * p['_wtg_mw'], 2)
            
        p['remaining_capacity'] = max(0, round(p['total_capacity'] - p['cod_mw'] - p['tr_mw'], 2))
        p['remaining_blocks'] = p['total_blocks'] - p['cod_blocks'] - p['tr_blocks']
        del p['_wtg_mw']

    # Sort FYs
    sorted_fys = sorted(list(fy_data.values()), key=lambda x: x["name"])

    # Calculate Monthly Trends across ALL data, plotting TR and COD events independently
    monthly_data_map = {}
    for b in block_map.values():
        if b["has_tr"]:
            dt = b["tr_finish"] or b["tr_start"]
            if dt:
                month_str = dt.strftime("%Y-%m")
                type_key = 'Solar Trial Run' if b['type'] == 'Solar' else 'Wind Trial Run'
                if month_str not in monthly_data_map:
                    monthly_data_map[month_str] = {"Solar COD": 0, "Solar Trial Run": 0, "Wind COD": 0, "Wind Trial Run": 0}
                monthly_data_map[month_str][type_key] += b["capacity"]
                
        if b["has_cod"]:
            dt = b["cod_finish"] or b["cod_start"]
            if dt:
                month_str = dt.strftime("%Y-%m")
                type_key = 'Solar COD' if b['type'] == 'Solar' else 'Wind COD'
                if month_str not in monthly_data_map:
                    monthly_data_map[month_str] = {"Solar COD": 0, "Solar Trial Run": 0, "Wind COD": 0, "Wind Trial Run": 0}
                monthly_data_map[month_str][type_key] += b["capacity"]

    sorted_months = sorted(monthly_data_map.keys())
    cum_solar_cod = cum_solar_tr = cum_wind_cod = cum_wind_tr = 0
    monthly_trends = []
    for m in sorted_months:
        cum_solar_cod += monthly_data_map[m]["Solar COD"]
        cum_solar_tr += monthly_data_map[m]["Solar Trial Run"]
        cum_wind_cod += monthly_data_map[m]["Wind COD"]
        cum_wind_tr += monthly_data_map[m]["Wind Trial Run"]
        monthly_trends.append({
            "name": m,
            "Solar COD": round(cum_solar_cod, 2),
            "Solar Trial Run": round(cum_solar_tr, 2),
            "Wind COD": round(cum_wind_cod, 2),
            "Wind Trial Run": round(cum_wind_tr, 2)
        })

    # Sort blocks descending by latest date for the recent feed
    recent.sort(key=lambda x: x["raw_date"].isoformat() if x["raw_date"] else "", reverse=True)
    for r in recent:
        del r["raw_date"]

    # Totals
    totals = {
        "solar_cod": sum(f["solar_cod"] for f in sorted_fys),
        "solar_tr": sum(f["solar_tr"] for f in sorted_fys),
        "wind_cod": sum(f["wind_cod"] for f in sorted_fys),
        "wind_tr": sum(f["wind_tr"] for f in sorted_fys)
    }

    # Project-level breakdown
    projects_list = sorted(project_map.values(), key=lambda x: x['total_capacity'], reverse=True)

    return {
        "financial_years": sorted_fys,
        "monthly_trends": monthly_trends,
        "recent_milestones": recent[:50],
        "totals": totals,
        "projects": projects_list
    }


@router.get("/api/projects/{mapping_id}/slr")
def get_project_slr_data(
    mapping_id: str, 

    filter_code: str = "ALL", 
    db: Session = Depends(get_db)
):
    """
    Fetches SLR data (from ZPSPS007) for a specific project based on its mappings.
    filter_code can be "ALL", "SPV", "AGEL", or "AGE6L".
    Groups by unique PO (C.Document) and determines open/closed status.
    """
    m = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == mapping_id).first()
    if not m:
        return {"error": "Project not found"}
        
    spv_code = str(m.spv_plant_code).strip() if m.spv_plant_code else ""
    agel_code = str(m.agel).strip() if m.agel else ""
    age6l_code = str(m.age6l).strip() if m.age6l else ""
    
    import re
    def get_prefixes(val):
        if not val: return []
        # Extract the alphanumeric parts after 'H-' or 'H', e.g., 'H-603M H-603B' -> ['603M', '603B']
        # The database (MTSLRData) stores plant_code without the H- prefix.
        return [c.upper() for c in re.findall(r'H-?\s*([A-Za-z0-9]+)', str(val).strip())]
        
    # Determine which plant codes to query
    codes_to_query = []
    if filter_code == "ALL":
        codes_to_query.extend(get_prefixes(spv_code))
        codes_to_query.extend(get_prefixes(agel_code))
        codes_to_query.extend(get_prefixes(age6l_code))
    elif filter_code == "SPV":
        codes_to_query.extend(get_prefixes(spv_code))
    elif filter_code == "AGEL":
        codes_to_query.extend(get_prefixes(agel_code))
    elif filter_code == "AGE6L":
        codes_to_query.extend(get_prefixes(age6l_code))
        
    codes_to_query = list(set(codes_to_query))
    if not codes_to_query:
        return {
            "total_pos": 0, "open_pos": 0, "closed_pos": 0, 
            "total_amount": 0, "actual_amount": 0, "commitment_amount": 0,
            "data": []
        }
        
    # Query SLR data. Only POrd/PReq rows count as procurement — blank-type rows
    # are cost lines (Land Cost, Piling, financing) — and overhead/service
    # descriptions (SPGS, PMC, ISA) are consolidated contract charges, not POs.
    slr_query = db.query(models.MTSLRData).filter(
        models.MTSLRData.plant_code.in_(codes_to_query),
        po_lines_only(),
    )
    records = slr_query.all()
    
    # Group by unique PO document (C.Document)
    po_groups = {}
    for r in records:
        act = r.actual_amount or 0.0
        comm = r.commitment_amount or 0.0
        
        # Skip rows where both are zero
        if abs(act) < 0.01 and abs(comm) < 0.01:
            continue

        # Skip rows with no type - not a real POrd/PReq record
        if not r.type or not str(r.type).strip():
            continue

        # Records with no PO document number must not be merged together -
        # they're unrelated line items (often different WBS/plant codes) that
        # happen to share an empty key, not the same purchase order.
        po_key = r.po_document or f"__unassigned_{r.id}"
        if po_key not in po_groups:
            po_groups[po_key] = {
                "po_document": po_key,
                "description": r.description,
                "vendor_name": r.vendor_name,
                "type": r.type,
                "wbs_element": r.wbs_element,
                "total_actual": 0.0,
                "total_commitment": 0.0,
                "plant_code": r.plant_code,
                "line_items": []
            }
        
        po_groups[po_key]["total_actual"] += act
        po_groups[po_key]["total_commitment"] += comm
        po_groups[po_key]["line_items"].append({
            "description": r.description,
            "type": r.type,
            "wbs_element": r.wbs_element,
            "actual": act,
            "commitment": comm,
            "total": act + comm,
            "plant_code": r.plant_code
        })
    
    # Build result with open/closed status per unique PO
    result_data = []
    open_pos = 0
    closed_pos = 0
    total_actual = 0.0
    total_comm = 0.0
    
    for po_key, group in po_groups.items():
        act_sum = group["total_actual"]
        comm_sum = group["total_commitment"]
        total = act_sum + comm_sum
        
        # Open: has commitment > 0 (regardless of actual)
        # Closed: commitment == 0 and actual > 0
        if abs(comm_sum) > 0.01:
            status = "Open"
            open_pos += 1
        else:
            status = "Closed"
            closed_pos += 1
            
        total_actual += act_sum
        total_comm += comm_sum
            
        result_data.append({
            "po_document": None if po_key.startswith("__unassigned_") else po_key,
            "description": group["description"],
            "vendor_name": group["vendor_name"],
            "type": group["type"],
            "wbs_element": group["wbs_element"],
            "total": total,
            "actual": act_sum,
            "commitment": comm_sum,
            "status": status,
            "plant_code": group["plant_code"],
            "line_count": len(group["line_items"]),
            "line_items": group["line_items"]
        })
    
    # Sort by total amount descending
    result_data.sort(key=lambda x: abs(x["total"]), reverse=True)
        
    return {
        "total_pos": len(po_groups),
        "open_pos": open_pos,
        "closed_pos": closed_pos,
        "total_amount": total_actual + total_comm,
        "actual_amount": total_actual,
        "commitment_amount": total_comm,
        "data": result_data
    }



@router.get("/api/projects/{mapping_id}/installation-progress")
def get_project_installation_progress(mapping_id: str, db: Session = Depends(get_db)):
    """Module installation for one project, planned vs completed, by month.

    Everything here is a direct read of P6, not a calculation:
      - status comes from p6_activity.status (Completed / In Progress / Not
        Started), which P6 itself maintains;
      - the plan line buckets planned_finish_date, the actual line buckets
        actual_finish_date of Completed activities — both real P6 dates.
    Block identity lives in the activity name ("Block-04 - Module
    Installation"), not in wbs_code (which is '1' on every row), so the
    activity is matched on its name, the same convention the rest of the P6
    code in this app relies on.

    Wind / BESS / transmission-only projects have no module-installation
    activities at all; they get not_applicable=True rather than an empty
    chart that would read as "nothing installed yet".
    """
    m = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == mapping_id).first()
    if not m:
        return {"error": "Project not found"}
    p6_rows = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).all()
    if not p6_rows:
        return {"not_applicable": True, "reason": "No P6 project mapped to this project."}
    p6_proj = p6_rows[0]

    A = models.P6Activity
    # All P6 objects that share this project id (a re-sync can create a second one).
    scope = [A.project_object_id.in_([r.p6_object_id for r in p6_rows]), A.name.ilike("%module installation%")]

    by_status = dict(db.query(A.status, func.count(A.id)).filter(*scope).group_by(A.status).all())
    planned = sum(by_status.values())
    if planned == 0:
        return {"not_applicable": True,
                "reason": "This project has no module-installation activities in P6 (wind, BESS or transmission scope)."}
    completed = by_status.get("Completed", 0)
    in_progress = by_status.get("In Progress", 0)
    not_started = by_status.get("Not Started", 0)

    month = lambda col: func.to_char(func.date_trunc("month", col), "YYYY-MM")
    plan_rows = db.query(month(A.planned_finish_date), func.count(A.id)) \
        .filter(*scope, A.planned_finish_date.isnot(None)).group_by(month(A.planned_finish_date)).all()
    baseline_rows = db.query(month(A.baseline_finish_date), func.count(A.id)) \
        .filter(*scope, A.baseline_finish_date.isnot(None)).group_by(month(A.baseline_finish_date)).all()
    actual_rows = db.query(month(A.actual_finish_date), func.count(A.id)) \
        .filter(*scope, A.status == "Completed", A.actual_finish_date.isnot(None)) \
        .group_by(month(A.actual_finish_date)).all()

    buckets: Dict[str, dict] = {}
    def get(k):
        return buckets.setdefault(k, {"month": k, "planned": 0, "baseline": 0, "completed": 0})
    for k, n in plan_rows: get(k)["planned"] = n
    for k, n in baseline_rows: get(k)["baseline"] = n
    for k, n in actual_rows: get(k)["completed"] = n
    series = [buckets[k] for k in sorted(buckets)]

    # Cumulative view for the S-curve; running totals over the same buckets.
    cp = cb = cc = 0
    for r in series:
        cp += r["planned"]; cb += r["baseline"]; cc += r["completed"]
        r["planned_cum"], r["baseline_cum"], r["completed_cum"] = cp, cb, cc

    return {
        "not_applicable": False,
        "p6_project_id": p6_proj.project_id,
        "p6_project_name": p6_proj.name,
        "summary": {
            "planned": planned, "completed": completed, "in_progress": in_progress,
            "not_started": not_started, "remaining": in_progress + not_started,
            "pct_complete": round(completed / planned * 100, 1),
            "basis": "count of P6 'Module Installation' activities by p6_activity.status",
        },
        "monthly": series,
    }


@router.get("/installation-planner")
def get_installation_planner(portfolio: Optional[str] = None, phase: Optional[str] = None, db: Session = Depends(get_db)):
    """Portfolio-wide module installation: every scoped project by month,
    plan vs completed, plus the SAP value and ECOD/TC context a planner needs
    beside it. Same scoping as the dashboard summary (portfolio/phase from the
    top bar). Four grouped queries in total — no per-project round trips.

    'behind' is defined once here: cumulative planned through the current
    month minus cumulative completed to date, floored at 0, in blocks.
    """
    from routers.sap import WBS_PREFIX

    query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        for part in portfolio.replace('+', ' ').strip().lower().split():
            query = query.filter(
                (func.lower(models.ProjectMapping.cluster).contains(part)) |
                (func.lower(models.ProjectMapping.category).contains(part)) |
                (func.lower(models.ProjectMapping.project).contains(part)))
    if phase and phase != "ALL":
        query = query.filter(models.ProjectMapping.is_commissioned == (phase == "Commissioned"))
    # The mapping sync leaves duplicate project_ids (72 rows, 64 ids); keep one
    # per id, preferring the row that carries WBS codes — same rule as project_service.
    seen: Dict[str, models.ProjectMapping] = {}
    for m in query.all():
        if "demo" in (m.project_name_from_p6 or m.project or "").lower():
            continue
        pid = m.project_id or ""
        cur = seen.get(pid)
        score = lambda x: sum(1 for w in (x.spv_plant_code, x.agel, x.age6l) if w) + (1 if x.cluster else 0)
        if cur is None or score(m) > score(cur):
            seen[pid] = m
    mappings = list(seen.values())

    # A P6 project id can map to more than one P6 object (the 12-Sep sync added
    # a second object for BAIYA and BANDHA). Activities are aggregated across
    # all of them; the newest object supplies the project-level dates.
    p6_objs: Dict[str, list] = {}
    for p in db.query(models.P6Project).order_by(models.P6Project.data_date.asc().nullsfirst()).all():
        p6_objs.setdefault(p.project_id, []).append(p)
    scoped = [(m, p6_objs.get(m.project_id) or []) for m in mappings]
    obj_ids = [o.p6_object_id for _, ps in scoped for o in ps]

    A = models.P6Activity
    base = [A.name.ilike("%module installation%"), A.project_object_id.in_(obj_ids or [-1])]
    month = lambda col: func.to_char(func.date_trunc("month", col), "YYYY-MM")

    by_status = {}
    monthly: Dict[int, Dict[str, dict]] = {}
    
    def bucket(oid, k):
        return monthly.setdefault(oid, {}).setdefault(k, {"planned": 0, "baseline": 0, "completed": 0, "activities": []})

    def fmt(d):
        return d.strftime("%Y-%m-%d") if d else None

    for act in db.query(A).filter(*base).all():
        oid = act.project_object_id
        st = act.status
        by_status.setdefault(oid, {})[st] = by_status.setdefault(oid, {}).get(st, 0) + 1
        
        item = {
            "name": act.name,
            "status": st,
            "planned": fmt(act.planned_finish_date),
            "baseline": fmt(act.baseline_finish_date),
            "actual": fmt(act.actual_finish_date)
        }
        
        if act.planned_finish_date:
            b = bucket(oid, act.planned_finish_date.strftime("%Y-%m"))
            b["planned"] += 1
            if item not in b["activities"]: b["activities"].append(item)
            
        if act.baseline_finish_date:
            b = bucket(oid, act.baseline_finish_date.strftime("%Y-%m"))
            b["baseline"] += 1
            if item not in b["activities"]: b["activities"].append(item)
            
        if act.actual_finish_date and st == "Completed":
            b = bucket(oid, act.actual_finish_date.strftime("%Y-%m"))
            b["completed"] += 1
            if item not in b["activities"]: b["activities"].append(item)

    # SAP value per 4-char WBS prefix (the same key SAP Intelligence attributes by), POrd only.
    PO = models.MTPOAmount
    po_by_prefix = {p: (float(v or 0), float(d or 0)) for p, v, d in
                    db.query(WBS_PREFIX, func.sum(PO.net_order_value_inr), func.sum(PO.delivered_value_inr_cr))
                      .filter(zsps_po_lines_only()).group_by(WBS_PREFIX)}
    def codes(m):
        out = []
        for val in (m.spv_plant_code, m.agel, m.age6l):
            out += [c.upper()[:4] for c in re.findall(r'H-?\s*([A-Za-z0-9]+)', str(val or ""))]
        return set(out)

    tc_by_map = {}
    E = models.TcNetworkEdge
    from sqlalchemy import case
    for mid, n, charged in db.query(E.mapping_id, func.count(E.id), func.sum(case((E.normalized_status == "charged", 1), else_=0))).filter(E.mapping_id.isnot(None)).group_by(E.mapping_id):
        tc_by_map[mid] = (n, int(charged or 0))

    today = datetime.utcnow().strftime("%Y-%m")
    projects, all_months = [], set()
    tot = {"planned": 0, "completed": 0, "in_progress": 0, "not_started": 0, "this_month": {"planned": 0, "completed": 0},
           "behind_projects": 0, "ordered_cr": 0.0, "delivered_cr": 0.0}
    for m, ps in scoped:
        p = ps[-1] if ps else None          # newest object for dates
        oids = [o.p6_object_id for o in ps]
        cs = codes(m)
        ordered = sum(po_by_prefix.get(c, (0, 0))[0] for c in cs) / 1e7
        delivered = sum(po_by_prefix.get(c, (0, 0))[1] for c in cs)
        sched = p.scheduled_finish_date if p else None
        basel = p.baseline_finish_date if p else None
        slip = (sched.date() - basel.date()).days if sched and basel else None
        lines, charged = tc_by_map.get(m.id, (0, 0))
        row = {
            "project_id": m.project_id, "name": m.project_name_from_p6 or m.project, "cluster": m.cluster,
            "capacity_mwac": round(m.capacity_mwac or 0, 1), "is_commissioned": bool(m.is_commissioned),
            "ordered_cr": round(ordered, 1), "delivered_cr": round(delivered, 1),
            "ecod": {"scheduled": sched.strftime("%Y-%m-%d") if sched else None,
                     "baseline": basel.strftime("%Y-%m-%d") if basel else None, "slip_days": slip},
            "tc": {"lines": lines, "charged": charged},
        }
        st: Dict[str, int] = {}
        for oid in oids:
            for k, v in by_status.get(oid, {}).items():
                st[k] = st.get(k, 0) + v
        planned = sum(st.values())
        if not p or planned == 0:
            row.update({"not_applicable": True, "summary": None, "monthly": {}, "behind": 0, "next_due": None})
            projects.append(row); continue
        completed, inprog, notst = st.get("Completed", 0), st.get("In Progress", 0), st.get("Not Started", 0)
        mo: Dict[str, dict] = {}
        for oid in oids:
            for k, v in monthly.get(oid, {}).items():
                cell = mo.setdefault(k, {"planned": 0, "baseline": 0, "completed": 0, "activities": []})
                for f in ["planned", "baseline", "completed"]: cell[f] += v[f]
                for act in v.get("activities", []):
                    if act not in cell["activities"]: cell["activities"].append(act)
        all_months.update(mo)
        planned_cum = sum(v["planned"] for k, v in mo.items() if k <= today)
        completed_cum = sum(v["completed"] for v in mo.values())
        behind = max(0, planned_cum - completed_cum)
        future = sorted(k for k, v in mo.items() if k >= today and v["planned"] > 0)
        row.update({
            "not_applicable": False,
            "summary": {"planned": planned, "completed": completed, "in_progress": inprog, "not_started": notst,
                        "pct_complete": round(completed / planned * 100, 1)},
            "monthly": mo, "behind": behind, "next_due": future[0] if future else None,
        })
        tot["planned"] += planned; tot["completed"] += completed; tot["in_progress"] += inprog; tot["not_started"] += notst
        tm = mo.get(today, {})
        tot["this_month"]["planned"] += tm.get("planned", 0); tot["this_month"]["completed"] += tm.get("completed", 0)
        if behind > 0: tot["behind_projects"] += 1
        projects.append(row)

    # Portfolio ₹ is computed once over the UNION of scoped prefixes. Per-project
    # rows attribute shared AGEL/AGE6L codes to every project that carries them,
    # so summing rows would double-count (58,963 vs a true 52,974 when tested).
    union = set().union(*(codes(m) for m, _ in scoped)) if scoped else set()
    tot["ordered_cr"] = round(sum(po_by_prefix.get(c, (0, 0))[0] for c in union) / 1e7, 1)
    tot["delivered_cr"] = round(sum(po_by_prefix.get(c, (0, 0))[1] for c in union), 1)
    projects.sort(key=lambda r: (-r["behind"], r["not_applicable"], r["name"] or ""))
    return {"months": sorted(all_months), "today": today, "totals": tot, "projects": projects,
            "basis": "count of P6 'Module Installation' activities by status; months from planned/baseline/actual finish dates"}



@router.get("/api/projects/{mapping_id}/delay-reasons")
def get_project_delay_reasons(mapping_id: str, db: Session = Depends(get_db)):
    """Why a project is behind, from what the platform can actually verify —
    never a guess. Three independent signals, each labelled by source:

      1. Every SAP purchase order for this project with value still to
         deliver, owner (buyer/vendor) from ME2J (mt_me2j_po). Flagged
         overdue when SAP's own contract validity date has passed — that
         flag, not a colour choice, is what "responsible for a slow order"
         means here.
      2. Open Pulse non-conformances for this project (quality holds that can
         block handover to installation).
      3. Transmission lines this project depends on that are not yet charged,
         with SAP's own expected date.

    No inference beyond that: this does not claim WHY a PO is late (SAP has no
    such field), only THAT it is open, since when its validity lapsed if it
    has, and who owns it.
    """
    m = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == mapping_id).first()
    if not m:
        return {"error": "Project not found"}

    prefixes = _extract_wbs_prefixes(m)
    now = datetime.utcnow()

    # 1. Every open PO (value still to deliver), owner from ME2J. Overdue is a
    # flag on this list, not a separate one — "pending" is the real scope.
    PO, ME = models.MTPOAmount, models.MTME2JPO
    pending_pos = []
    if prefixes:
        rows = (db.query(PO, ME)
                .outerjoin(ME, ME.purchasing_document == PO.purchasing_document)
                .filter(PO.doc_type == "POrd",
                        or_(*[PO.wbs_element.ilike(f"H-{p}%") for p in prefixes]),
                        (PO.net_order_value_inr - func.coalesce(PO.delivered_value_inr_cr, 0) * 10000000) > 1000)
                .all())
        seen = set()
        for po, me in rows:
            if po.purchasing_document in seen:
                continue
            seen.add(po.purchasing_document)
            validity = me.validity_end if me else None
            overdue_days = (now - validity).days if validity and validity < now else None
            pending_pos.append({
                "po": po.purchasing_document, "material": po.material_name, "vendor": po.vendor_name or (me.vendor_name if me else None),
                "buyer": me.buyer_name if me else None, "buyer_email": me.buyer_email if me else None,
                "ordered_cr": round((po.net_order_value_inr or 0) / 10000000, 2),
                "remaining_cr": round((po.net_order_value_inr or 0) / 10000000 - (po.delivered_value_inr_cr or 0), 2),
                "validity_end": validity.strftime("%Y-%m-%d") if validity else None,
                "overdue_days": overdue_days, "overdue": overdue_days is not None,
                "doc_type": me.doc_type if me else None,
            })
        pending_pos.sort(key=lambda r: (-(r["overdue_days"] or -1), -r["remaining_cr"]))

    # 2. Open Pulse quality holds.
    open_ncs = []
    if m.pulse_project_uuid:
        NC = models.PulseNC
        for r in db.query(NC).filter(NC.project_id == m.pulse_project_uuid, ~NC.status.in_(["completed", "rejected"])).order_by(NC.created_at.asc()).limit(20):
            open_ncs.append({"id": r.id, "status": r.status, "category": getattr(r, "category", None),
                              "created_at": r.created_at.strftime("%Y-%m-%d") if r.created_at else None,
                              "age_days": (now - r.created_at).days if r.created_at else None})

    # 3. Transmission lines this project depends on, not yet charged.
    E = models.TcNetworkEdge
    pending_tc = [{"from": e.from_label, "to": e.to_label, "voltage": e.voltage, "status": e.normalized_status, "expected_date": e.expected_date}
                  for e in db.query(E).filter(E.mapping_id == m.id, E.normalized_status != "charged")]

    overdue_pos = [p for p in pending_pos if p["overdue"]]
    return {
        "project_id": mapping_id,
        "pending_pos": pending_pos, "pending_pos_count": len(pending_pos),
        "pending_pos_value_cr": round(sum(p["remaining_cr"] for p in pending_pos), 1),
        "overdue_pos_count": len(overdue_pos),
        "overdue_pos_value_cr": round(sum(p["remaining_cr"] for p in overdue_pos), 1),
        "open_ncs": open_ncs, "open_ncs_count": len(open_ncs),
        "pending_tc": pending_tc, "pending_tc_count": len(pending_tc),
    }


@router.get("/api/projects/{mapping_id}/installation-blocks")
def get_project_installation_blocks(mapping_id: str, db: Session = Depends(get_db)):
    """Every 'Module Installation' block for one project, named, with its
    baseline / current-plan / actual dates and status — the detail behind a
    planner grid cell's aggregate count. Same duplicate-P6-object handling as
    installation-progress (a re-sync can leave a second P6 object per id).

    'Planned' is P6's own current forecast (planned_finish_date); there is no
    separate 'forecast' field in P6 to show alongside it, so this does not
    invent a fourth date — baseline, planned/forecast, and actual (when done)
    are the three real dates P6 carries per activity.
    """
    m = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == mapping_id).first()
    if not m:
        return {"error": "Project not found"}
    p6_rows = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).all()
    if not p6_rows:
        return {"project_id": mapping_id, "blocks": []}

    A = models.P6Activity
    rows = db.query(A).filter(
        A.project_object_id.in_([r.p6_object_id for r in p6_rows]),
        A.name.ilike("%module installation%"),
    ).order_by(A.planned_finish_date.asc().nullslast()).all()

    fmt = lambda d: d.strftime("%Y-%m-%d") if d else None
    blocks = [{
        "name": a.name, "status": a.status,
        "baseline_finish": fmt(a.baseline_finish_date),
        "planned_finish": fmt(a.planned_finish_date),
        "actual_finish": fmt(a.actual_finish_date),
        "planned_month": a.planned_finish_date.strftime("%Y-%m") if a.planned_finish_date else None,
        "actual_month": a.actual_finish_date.strftime("%Y-%m") if a.actual_finish_date else None,
    } for a in rows]
    return {"project_id": mapping_id, "blocks": blocks}