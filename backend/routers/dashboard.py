from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
import json
import time
from datetime import datetime

from database import get_db
import models
from services.project_service import filter_tc_edges_by_kps

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

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Simple in-memory cache to prevent 6-8s load times from N+1 queries
_KG_CACHE = {"data": None, "timestamp": 0}
_SUMMARY_CACHE = {"data": None, "timestamp": 0}
_CACHE_TTL = 300  # 5 minutes

@router.get("/summary")
def get_dashboard_summary(portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    """
    Returns a global portfolio summary and a unified list of all mapped projects
    with data from P6, SAP, and Transmission. Includes all P6 projects even if unmapped.
    """
    global _SUMMARY_CACHE
    cache_key = str(portfolio).lower() if portfolio else "all"
    
    if not nocache and cache_key in _SUMMARY_CACHE:
        entry = _SUMMARY_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _CACHE_TTL:
            return entry["data"]
            
    query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        p_clean = portfolio.replace('+', ' ').strip().lower()
        query = query.filter(
            (func.lower(models.ProjectMapping.cluster).contains(p_clean)) |
            (func.lower(models.ProjectMapping.category).contains(p_clean))
        )
            
    raw_mappings = query.all()
    raw_p6_projects = db.query(models.P6Project).all()
    
    # Filter out Demo projects
    filtered_mappings = []
    for m in raw_mappings:
        name_check = m.project_name_from_p6 or m.project or ""
        if "demo" not in name_check.lower():
            filtered_mappings.append(m)
            
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
    req_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTRequirement.spv_plant_code, func.sum(models.MTRequirement.budgeted_units_mw)).group_by(models.MTRequirement.spv_plant_code).all() if r[0]}
    
    # We will compute in-transit QTY inline
    it_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTPOAmount.plant_code, func.sum(models.MTPOAmount.still_to_deliver_qty)).group_by(models.MTPOAmount.plant_code).all() if r[0]}
    
    po_qty_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTPOAmount.plant_code, func.sum(models.MTPOAmount.order_quantity)).group_by(models.MTPOAmount.plant_code).all() if r[0]}
    po_val_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTPOAmount.plant_code, func.sum(models.MTPOAmount.net_order_value_inr)).group_by(models.MTPOAmount.plant_code).all() if r[0]}
    po_delivered_val_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTPOAmount.plant_code, func.sum(models.MTPOAmount.delivered_value_inr_cr)).group_by(models.MTPOAmount.plant_code).all() if r[0]}

    all_inv_wbs = db.query(models.MTInventory.wbs_element, func.sum(models.MTInventory.quantity_inv)).group_by(models.MTInventory.wbs_element).all()
    all_it_wbs = db.query(models.MTPOAmount.wbs_element, func.sum(models.MTPOAmount.still_to_deliver_qty)).group_by(models.MTPOAmount.wbs_element).all()

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

    for m in mappings:
        pm_cap = proj_cap_dict.get(m.project_id, {})
        computed_capacity = pm_cap.get("total_capacity", m.capacity_mwac or 0)
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
            p6_pct = getattr(p6_data, 'construction_percent_complete', None)
            if p6_pct is None:
                p6_pct = p6_data.duration_percent_complete or 0
            if p6_pct <= 1.0 and p6_pct > 0:
                p6_pct *= 100
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
        plant_code_str = str(m.spv_plant_code).strip() if m.spv_plant_code else ""
        agel_code_str = str(m.agel).strip() if m.agel else ""
        
        # Calculate allocation ratio using primary spv_plant_code
        total_capacity = capacity_by_plant.get(plant_code_str, 1.0)
        project_capacity = m.capacity_mwac or 0
        allocation_ratio = project_capacity / total_capacity if total_capacity > 0 else 1.0

        # We will use whichever code has the data (often AGEL code for PO/Inventory)
        req_mw = req_by_plant.get(plant_code_str, 0) or req_by_plant.get(agel_code_str, 0)
        
        if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', ''):
            clean_wbs = str(m.module_wbs).strip().lower()
            inv_qty = sum(qty for wbs, qty in all_inv_wbs if wbs and qty and clean_wbs in str(wbs).lower())
            it_qty = sum(qty for wbs, qty in all_it_wbs if wbs and qty and clean_wbs in str(wbs).lower())
            allocation_ratio_inv = 1.0
        else:
            inv_qty = (inv_by_plant.get(plant_code_str, 0) or inv_by_plant.get(agel_code_str, 0)) or 0
            it_qty = (it_by_plant.get(plant_code_str, 0) or it_by_plant.get(agel_code_str, 0)) or 0
            allocation_ratio_inv = allocation_ratio
            
        inv_qty *= allocation_ratio_inv
        it_qty *= allocation_ratio_inv
        req_qty = (req_mw or 0) * allocation_ratio

        po_qty = ((po_qty_by_plant.get(plant_code_str, 0) or po_qty_by_plant.get(agel_code_str, 0)) or 0) * allocation_ratio
        po_value = ((po_val_by_plant.get(plant_code_str, 0) or po_val_by_plant.get(agel_code_str, 0)) or 0) * allocation_ratio
        po_delivered_cr = ((po_delivered_val_by_plant.get(plant_code_str, 0) or po_delivered_val_by_plant.get(agel_code_str, 0)) or 0) * allocation_ratio

        portfolio_summary["total_inventory_qty"] += inv_qty
        portfolio_summary["total_po_qty"] += po_qty

        # TC Data
        project_entries = [pe for pe in all_tc_entries if pe.mapping_id == m.id]
        phases = set(str(pe.phase).strip().upper() for pe in project_entries if pe.phase)
        
        tc_khavda = []
        tc_rajasthan = []
        
        if phases:
            for edge in all_tc_edges:
                if phases.intersection(parsed_edge_phases.get(edge.id, set())):
                    if edge.region == "Khavda":
                        tc_khavda.append(edge)
                    elif edge.region == "Rajasthan":
                        tc_rajasthan.append(edge)
                        
        # Direct mappings
        for edge in all_tc_edges:
            if edge.mapping_id == m.id:
                if edge.region == "Khavda":
                    tc_khavda.append(edge)
                elif edge.region == "Rajasthan":
                    tc_rajasthan.append(edge)

        # Deduplicate
        tc_khavda = list({e.id: e for e in tc_khavda}.values())
        tc_rajasthan = list({e.id: e for e in tc_rajasthan}.values())
        
        tc_khavda = filter_tc_edges_by_kps(tc_khavda, project_entries)
        tc_rajasthan = filter_tc_edges_by_kps(tc_rajasthan, project_entries)
        
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
            "p6": {
                "id": p6_data.project_id if p6_data else None,
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
                "po_qty": round(po_qty, 2),
                "in_transit_qty": round(it_qty, 2),
                "inventory_qty": round(inv_qty, 2),
                "po_value": round(po_value, 2),
                "po_delivered_cr": round(po_delivered_cr, 2)
            },
            "tc": {
                "status": tc_summary,
                "has_data": bool(tc_khavda or tc_rajasthan),
                "data": {
                    "khavda": [{"project": m.project or m.project_name_from_p6, "phase": _safe_parse_phase(t.projects), "voltage": t.voltage, "status": t.status} for t in tc_khavda],
                    "rajasthan": [{"project": m.project or m.project_name_from_p6, "phase": _safe_parse_phase(t.projects), "voltage": t.voltage, "status": t.status} for t in tc_rajasthan]
                }
            }
        })
        
    # ... inside get_dashboard_summary ...
    portfolio_summary["total_projects"] = len(project_list)
    
    result = {
        "summary": portfolio_summary,
        "projects": project_list
    }
    
    _SUMMARY_CACHE[cache_key] = {"data": result, "timestamp": time.time()}
    return result

@router.get("/projects/{mapping_id}")
def get_project_details(mapping_id: int, db: Session = Depends(get_db)):
    """Get full 360 view for a single project"""
    m = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == mapping_id).first()
    if not m:
        return {"error": "Project not found"}
        
    p6_data = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).first()
    
    # SAP Items
    # 1. Inventory Mapping (MB52)
    inv_query = db.query(models.MTInventory)
    if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', ''):
        clean_wbs = str(m.module_wbs).strip()
        inv_query = inv_query.filter(models.MTInventory.wbs_element.ilike(f"%{clean_wbs}%"))
    else:
        inv_query = inv_query.filter(
            (models.MTInventory.plant_code == str(m.spv_plant_code).strip()) |
            (models.MTInventory.plant_code == str(m.agel).strip())
        )
    inventory = inv_query.all()
    
    # 2. PO Items (ME2M) - only has Plant Code
    po_items = db.query(models.MTPOAmount).filter(
        (models.MTPOAmount.plant_code == str(m.spv_plant_code).strip()) |
        (models.MTPOAmount.plant_code == str(m.agel).strip())
    ).all()
    
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
            "inventory_summary": sum((i.quantity_mw or 0) for i in inventory),
            "po_summary": sum((p.po_quantities_mw or 0) for p in po_items),
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
            raw_progress = getattr(p6, 'construction_percent_complete', None)
            if raw_progress is None:
                raw_progress = p6.duration_percent_complete or 0
            progress = round(raw_progress * 100)
            # Multi-signal delay detection:
            # 1. finish_date_variance < 0 (if available)
            # 2. scheduled finish date has passed and project is not complete
            # 3. significant number of delayed activities
            is_delayed = False
            if p6.finish_date_variance and p6.finish_date_variance < 0:
                is_delayed = True
            elif p6.scheduled_finish_date and p6.scheduled_finish_date < datetime.now() and (p6.duration_percent_complete or 0) < 1.0:
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
        wbs_str = str(m.module_wbs or "").strip()
        sap_data = None
        plant_code = str(m.spv_plant_code or "").strip()
        agel_code = str(m.agel or "").strip()
        if plant_code or agel_code:
            # Calculate allocation ratio
            total_capacity = db.query(func.sum(models.ProjectMapping.capacity_mwac)).filter(
                models.ProjectMapping.spv_plant_code == plant_code
            ).scalar() or 1.0
            project_capacity = m.capacity_mwac or 0
            
            if project_capacity == 0:
                mapping_count = db.query(models.ProjectMapping).filter(models.ProjectMapping.spv_plant_code == plant_code).count()
                allocation_ratio = (1.0 / mapping_count) if mapping_count > 0 else 1.0
            else:
                allocation_ratio = project_capacity / total_capacity if total_capacity > 0 else 1.0
            
            if wbs_str and wbs_str.lower() not in ('nan', 'none', 'null', ''):
                wbs_prefix = wbs_str[:6]
                po_count = db.query(models.MTPOAmount.purchasing_document).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code),
                    models.MTPOAmount.wbs_element.startswith(wbs_prefix)
                ).distinct().count()
                
                po_total = db.query(func.sum(models.MTPOAmount.net_order_value)).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code),
                    models.MTPOAmount.wbs_element.startswith(wbs_prefix)
                ).scalar() or 0
                
                po_mw = db.query(func.sum(models.MTPOAmount.po_quantities_mw)).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code),
                    models.MTPOAmount.wbs_element.startswith(wbs_prefix)
                ).scalar() or 0
            else:
                po_count = db.query(models.MTPOAmount.purchasing_document).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code)
                ).distinct().count() * allocation_ratio
                
                po_total = (db.query(func.sum(models.MTPOAmount.net_order_value)).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code)
                ).scalar() or 0) * allocation_ratio
                
                po_mw = (db.query(func.sum(models.MTPOAmount.po_quantities_mw)).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code)
                ).scalar() or 0) * allocation_ratio
            
            req_count = db.query(models.MTRequirement).filter(
                (models.MTRequirement.spv_plant_code == plant_code) | (models.MTRequirement.spv_plant_code == agel_code)
                # Requirement doesn't have wbs_element mapped usually, but we can set to 0 or leave as is. We'll set to 0 since it's not WBS specific yet.
            ).count() * 0 # Hardcoded to 0 since we can't reliably filter by WBS without a WBS column in MTRequirement.
            
            req_total_mw = 0
            
            if wbs_str and wbs_str.lower() not in ('nan', 'none', 'null', ''):
                inv_count = db.query(models.MTInventory).filter(
                    (models.MTInventory.plant_code == plant_code) | (models.MTInventory.plant_code == agel_code),
                    models.MTInventory.wbs_element.startswith(wbs_prefix)
                ).count()
                
                inv_mw = db.query(func.sum(models.MTInventory.quantity_mw)).filter(
                    (models.MTInventory.plant_code == plant_code) | (models.MTInventory.plant_code == agel_code),
                    models.MTInventory.wbs_element.startswith(wbs_prefix)
                ).scalar() or 0

                
                transit_count = db.query(models.MTPOAmount).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code),
                    models.MTPOAmount.wbs_element.startswith(wbs_prefix),
                    models.MTPOAmount.still_to_deliver_qty > 0
                ).count()
                
                transit_mw = db.query(func.sum(models.MTPOAmount.still_to_deliver_qty * models.MTPOAmount.mw_multiplication_factor)).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code),
                    models.MTPOAmount.wbs_element.startswith(wbs_prefix)
                ).scalar() or 0
                
                top_vendors = db.query(
                    models.MTPOAmount.vendor_name, func.sum(models.MTPOAmount.net_order_value).label("total")
                ).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code),
                    models.MTPOAmount.wbs_element.startswith(wbs_prefix)
                ).group_by(models.MTPOAmount.vendor_name).order_by(func.sum(models.MTPOAmount.net_order_value).desc()).limit(3).all()
                inv_alloc = 1.0
            else:
                inv_count = db.query(models.MTInventory).filter(
                    (models.MTInventory.plant_code == plant_code) | (models.MTInventory.plant_code == agel_code)
                ).count() * allocation_ratio
                
                inv_mw = (db.query(func.sum(models.MTInventory.quantity_mw)).filter(
                    (models.MTInventory.plant_code == plant_code) | (models.MTInventory.plant_code == agel_code)
                ).scalar() or 0) * allocation_ratio
                
                transit_count = db.query(models.MTPOAmount).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code),
                    models.MTPOAmount.still_to_deliver_qty > 0
                ).count() * allocation_ratio
                
                transit_mw = (db.query(func.sum(models.MTPOAmount.still_to_deliver_qty * models.MTPOAmount.mw_multiplication_factor)).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code)
                ).scalar() or 0) * allocation_ratio
                
                top_vendors = db.query(
                    models.MTPOAmount.vendor_name, func.sum(models.MTPOAmount.net_order_value).label("total")
                ).filter(
                    (models.MTPOAmount.plant_code == plant_code) | (models.MTPOAmount.plant_code == agel_code)
                ).group_by(models.MTPOAmount.vendor_name).order_by(func.sum(models.MTPOAmount.net_order_value).desc()).limit(3).all()
                inv_alloc = allocation_ratio
            
            top_vendors_list = []
            for v in top_vendors:
                vname = (v[0] or "Unknown").strip()
                parts = vname.split(" ", 1)
                if len(parts) == 2 and parts[0].isdigit():
                    vname = parts[1].strip()
                top_vendors_list.append({
                    "name": vname[:25], 
                    "value_cr": round((v[1] * inv_alloc) / 10000000, 2) if v[1] else 0
                })
            
            sap_data = {
                "plant_code": plant_code,
                "po_count": round(po_count),
                "po_total_cr": round(po_total / 10000000, 2) if po_total else 0,
                "po_mw": round(po_mw, 1) if po_mw else 0,
                "requirement_count": 0,
                "requirement_mw": 0,
                "inventory_items": round(inv_count),
                "inventory_mw": round(inv_mw, 1) if inv_mw else 0,
                "in_transit_count": round(transit_count),
                "in_transit_mw": round(transit_mw, 1) if transit_mw else 0,
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
        # Use capacity overview's computed total_capacity (accounts for dynamic Wind WTG calculation)
        computed_capacity = pm_cap.get("total_capacity", m.capacity_mwac or 0)

        portfolio_groups[port_name][eps].append({
            "id": m.id, "name": (m.project_name_from_p6 or m.project or "?")[:28],
            "capacity": computed_capacity, "health": health,
            "progress": progress, "spv": m.spv_name or "?",
            "plant_code": plant_code,
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
                    "id": proj_id, "name": p["name"], "category": 3 if p["health"] == "on_track" else 4,
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
        
        p_type = 'Wind' if 'wind' in str(pm.project).lower() else 'Solar'
        total_cap = float(pm.capacity_mwac or 0)
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
        ~P6Activity.wbs_name.ilike('%milestone%'),
        ~P6Activity.type.ilike('%milestone%')
    ).all()

    # Step 1: Group into unique blocks per project
    block_map = {}
    for act in activities:
        obj_id = str(act.project_object_id)
        
        # CRUCIAL: ONLY process activities for tracked projects in ProjectMapping
        if obj_id not in project_map: 
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
