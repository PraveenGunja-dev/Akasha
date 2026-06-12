from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
import json
import time

from database import get_db
import models
from services.project_service import filter_tc_edges_by_kps

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Simple in-memory cache to prevent 6-8s load times from N+1 queries
_KG_CACHE = {"data": None, "timestamp": 0}
_SUMMARY_CACHE = {"data": None, "timestamp": 0}
_CACHE_TTL = 300  # 5 minutes

@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """
    Returns a global portfolio summary and a unified list of all mapped projects
    with data from P6, SAP, and Transmission. Includes all P6 projects even if unmapped.
    """
    global _SUMMARY_CACHE
    if _SUMMARY_CACHE["data"] and time.time() - _SUMMARY_CACHE["timestamp"] < _CACHE_TTL:
        return _SUMMARY_CACHE["data"]
        
    raw_mappings = db.query(models.ProjectMapping).all()
    raw_p6_projects = db.query(models.P6Project).all()
    
    def is_valid_project(name: str, proj_id: str, eps: str) -> bool:
        name_lower = (name or "").lower()
        id_lower = (proj_id or "").lower()
        
        if "bees" in name_lower or "bees" in id_lower or "infra" in name_lower or "infra" in id_lower:
            return False
        if " pr" in id_lower or "pr " in id_lower or id_lower == "pr":
            return False
        if " pr" in name_lower or "pr " in name_lower or name_lower == "pr":
            return False
            
        if "fy" in id_lower or "fy" in name_lower or eps in ("Other (Outside Khavda)", "Khavda"):
            return True
        return False

    p6_projects = [p for p in raw_p6_projects if is_valid_project(p.name, p.project_id, p.parent_eps_name)]
    valid_p6_ids = {p.project_id for p in p6_projects}
    
    mappings = []
    for m in raw_mappings:
        if m.project_id in valid_p6_ids:
            mappings.append(m)
        else:
            if is_valid_project(m.project_name_from_p6 or m.project, m.project_id, "Unassigned"):
                mappings.append(m)
    
    portfolio_summary = {
        "total_mw": 0,
        "total_projects": 0,
        "delayed_projects": 0,
        "on_track_projects": 0,
        "total_inventory_mw": 0,
        "total_po_mw": 0
    }
    
    project_list = []
    mapped_p6_ids = set()
    
    for m in mappings:
        portfolio_summary["total_mw"] += (m.capacity_mwac or 0)
        
        # P6 Data
        p6_data = next((p for p in p6_projects if p.project_id == m.project_id), None)
        is_delayed = False
        schedule_health = "Unknown"
        progress = 0
        
        if p6_data:
            mapped_p6_ids.add(p6_data.project_id)
            progress = p6_data.duration_percent_complete or 0
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
                
        # SAP Data Mapping
        # 1. Inventory Mapping (MB52)
        inv_query = db.query(func.sum(models.MTInventory.quantity_mw))
        req_query = db.query(func.sum(models.MTRequirement.budgeted_units_mw))
        it_query = db.query(func.sum(models.MTInTransit.quantity_mw))
        
        # Priority: Map strictly by WBS if provided in Master Mapping
        if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', ''):
            clean_wbs = str(m.module_wbs).strip()
            inv_query = inv_query.filter(models.MTInventory.wbs_element.ilike(f"%{clean_wbs}%"))
            it_query = it_query.filter(models.MTInTransit.wbs_element.ilike(f"%{clean_wbs}%"))
            # Requirement usually only has plant code or project name
            req_query = req_query.filter(models.MTRequirement.spv_plant_code == str(m.spv_plant_code).strip())
        else:
            # Fallback to Plant Code mapping if no WBS is mapped
            inv_query = inv_query.filter(models.MTInventory.plant_code == str(m.spv_plant_code).strip())
            it_query = it_query.filter(models.MTInTransit.plant_code == str(m.spv_plant_code).strip())
            req_query = req_query.filter(models.MTRequirement.spv_plant_code == str(m.spv_plant_code).strip())
            
        # Calculate allocation ratio
        plant_code_str = str(m.spv_plant_code).strip()
        total_capacity = db.query(func.sum(models.ProjectMapping.capacity_mwac)).filter(
            models.ProjectMapping.spv_plant_code == plant_code_str
        ).scalar() or 1.0
        
        project_capacity = m.capacity_mwac or 0
        allocation_ratio = project_capacity / total_capacity if total_capacity > 0 else 1.0

        inv_mw = (inv_query.scalar() or 0) * (1.0 if m.module_wbs else allocation_ratio)
        it_mw = (it_query.scalar() or 0) * (1.0 if m.module_wbs else allocation_ratio)
        req_mw = (req_query.scalar() or 0) * allocation_ratio
        
        # 2. PO Amount Mapping (ME2M) - only has Plant Code available
        po_mw = (db.query(func.sum(models.MTPOAmount.po_quantities_mw)).filter(
            models.MTPOAmount.plant_code == plant_code_str
        ).scalar() or 0) * allocation_ratio
        
        po_value = (db.query(func.sum(models.MTPOAmount.net_order_value)).filter(
            models.MTPOAmount.plant_code == plant_code_str
        ).scalar() or 0) * allocation_ratio
        
        portfolio_summary["total_inventory_mw"] += inv_mw
        portfolio_summary["total_po_mw"] += po_mw
        
        # TC Data
        # A master mapping is linked to TcProjectEntry, which has a "phase".
        # We need to find TcNetworkEdges that contain this phase in their "projects" JSON array.
        project_entries = db.query(models.TcProjectEntry).filter(models.TcProjectEntry.mapping_id == m.id).all()
        phases = set(pe.phase for pe in project_entries if pe.phase)
        
        tc_khavda = []
        tc_rajasthan = []
        
        if phases:
            for p in phases:
                # Search Khavda
                edges_k = db.query(models.TcNetworkEdge).filter(
                    models.TcNetworkEdge.region == "Khavda",
                    models.TcNetworkEdge.projects.like(f'%"{p}"%')
                ).all()
                tc_khavda.extend(edges_k)
                
                # Search Rajasthan
                edges_r = db.query(models.TcNetworkEdge).filter(
                    models.TcNetworkEdge.region == "Rajasthan",
                    models.TcNetworkEdge.projects.like(f'%"{p}"%')
                ).all()
                tc_rajasthan.extend(edges_r)
        
        # Also include any direct mappings (fallback)
        direct_tc_khavda = db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == m.id, models.TcNetworkEdge.region == "Khavda").all()
        direct_tc_rajasthan = db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == m.id, models.TcNetworkEdge.region == "Rajasthan").all()
        tc_khavda.extend(direct_tc_khavda)
        tc_rajasthan.extend(direct_tc_rajasthan)
        
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
            "capacity_mwac": m.capacity_mwac,
            "spv_plant_code": m.spv_plant_code,
            "p6": {
                "id": p6_data.project_id if p6_data else None,
                "health": schedule_health,
                "progress": progress,
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
                "req_mw": round(req_mw, 2),
                "po_mw": round(po_mw, 2),
                "it_mw": round(it_mw, 2),
                "inventory_mw": round(inv_mw, 2),
                "po_value": round(po_value, 2)
            },
            "tc": {
                "status": tc_summary,
                "has_data": bool(tc_khavda or tc_rajasthan),
                "data": {
                    "khavda": [{"project": m.project or m.project_name_from_p6, "phase": json.loads(t.projects)[0] if t.projects and json.loads(t.projects) else "Unknown Phase", "voltage": t.voltage, "status": t.status} for t in tc_khavda],
                    "rajasthan": [{"project": m.project or m.project_name_from_p6, "phase": json.loads(t.projects)[0] if t.projects and json.loads(t.projects) else "Unknown Phase", "voltage": t.voltage, "status": t.status} for t in tc_rajasthan]
                }
            }
        })
        
    # ... inside get_dashboard_summary ...
    portfolio_summary["total_projects"] = len(project_list)
    
    result = {
        "summary": portfolio_summary,
        "projects": project_list
    }
    
    _SUMMARY_CACHE["data"] = result
    _SUMMARY_CACHE["timestamp"] = time.time()
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
        inv_query = inv_query.filter(models.MTInventory.plant_code == str(m.spv_plant_code).strip())
    inventory = inv_query.all()
    
    # 2. PO Items (ME2M) - only has Plant Code
    po_items = db.query(models.MTPOAmount).filter(
        models.MTPOAmount.plant_code == str(m.spv_plant_code).strip()
    ).all()
    
    # 3. In-Transit Mapping (ZIBDSESREP)
    in_transit_query = db.query(models.MTInTransit)
    if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', ''):
        clean_wbs = str(m.module_wbs).strip()
        in_transit_query = in_transit_query.filter(models.MTInTransit.wbs_element.ilike(f"%{clean_wbs}%"))
    else:
        in_transit_query = in_transit_query.filter(models.MTInTransit.plant_code == str(m.spv_plant_code).strip())
    in_transit = in_transit_query.all()
    
    # TC
    project_entries = db.query(models.TcProjectEntry).filter(models.TcProjectEntry.mapping_id == m.id).all()
    phases = set(pe.phase for pe in project_entries if pe.phase)
    
    tc_khavda = []
    tc_rajasthan = []
    
    if phases:
        for p in phases:
            edges_k = db.query(models.TcNetworkEdge).filter(
                models.TcNetworkEdge.region == "Khavda",
                models.TcNetworkEdge.projects.like(f'%"{p}"%')
            ).all()
            tc_khavda.extend(edges_k)
            
            edges_r = db.query(models.TcNetworkEdge).filter(
                models.TcNetworkEdge.region == "Rajasthan",
                models.TcNetworkEdge.projects.like(f'%"{p}"%')
            ).all()
            tc_rajasthan.extend(edges_r)
            
    # Fallback
    direct_tc_khavda = db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == m.id, models.TcNetworkEdge.region == "Khavda").all()
    direct_tc_rajasthan = db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == m.id, models.TcNetworkEdge.region == "Rajasthan").all()
    tc_khavda.extend(direct_tc_khavda)
    tc_rajasthan.extend(direct_tc_rajasthan)
    
    tc_khavda = list({e.id: e for e in tc_khavda}.values())
    tc_rajasthan = list({e.id: e for e in tc_rajasthan}.values())
    
    tc_khavda = filter_tc_edges_by_kps(tc_khavda, project_entries)
    tc_rajasthan = filter_tc_edges_by_kps(tc_rajasthan, project_entries)
    
    # Extract project name from the JSON array in 'projects' column and convert to dict
    tc_k_dicts = []
    for t in tc_khavda:
        d = {c: getattr(t, c) for c in t.__table__.columns.keys()}
        d["project"] = m.project or m.project_name_from_p6
        d["phase"] = json.loads(t.projects)[0] if t.projects and json.loads(t.projects) else "Unknown Phase"
        tc_k_dicts.append(d)
        
    tc_r_dicts = []
    for t in tc_rajasthan:
        d = {c: getattr(t, c) for c in t.__table__.columns.keys()}
        d["project"] = m.project or m.project_name_from_p6
        d["phase"] = json.loads(t.projects)[0] if t.projects and json.loads(t.projects) else "Unknown Phase"
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
    
    # Search Projects (P6Project)
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
        
    # Search Purchase Orders (MTPOAmount)
    pos = db.query(models.MTPOAmount).filter(
        func.lower(models.MTPOAmount.purchasing_document).contains(q_lower) |
        func.lower(models.MTPOAmount.vendor_name).contains(q_lower) |
        func.lower(models.MTPOAmount.material_code).contains(q_lower)
    ).limit(10).all()
    
    for po in pos:
        results.append({
            "id": f"po_{po.id}",
            "type": "Purchase Order",
            "title": f"PO-{po.purchasing_document}",
            "snippet": f"Vendor: {po.vendor_name}. Value: ${po.net_order_value or 0:,.2f}. Material: {po.material_code}",
            "raw": po.purchasing_document
        })
        
    # Search Inventory/Materials (MTInventory)
    materials = db.query(models.MTInventory).filter(
        func.lower(models.MTInventory.material_code).contains(q_lower) |
        func.lower(models.MTInventory.vendor_code).contains(q_lower) |
        func.lower(models.MTInventory.wbs_element).contains(q_lower)
    ).limit(10).all()
    
    for m in materials:
        results.append({
            "id": f"mat_{m.id}",
            "type": "Material Component",
            "title": m.material_code,
            "snippet": f"Inventory: {m.quantity_inv} at Plant {m.plant_code}. WBS: {m.wbs_element}",
            "raw": m.material_code
        })
        
    # Vendors (unique from POs)
    vendors = db.query(models.MTPOAmount.vendor_name, models.MTPOAmount.vendor_code).filter(
        func.lower(models.MTPOAmount.vendor_name).contains(q_lower) |
        func.lower(models.MTPOAmount.vendor_code).contains(q_lower)
    ).distinct().limit(5).all()
    
    for idx, v in enumerate(vendors):
        results.append({
            "id": f"vend_{idx}_{v.vendor_code}",
            "type": "Vendor",
            "title": v.vendor_name or v.vendor_code,
            "snippet": f"Vendor Code: {v.vendor_code}",
            "raw": v.vendor_code
        })
        
    return results

@router.get("/knowledge-graph")
def get_knowledge_graph(db: Session = Depends(get_db)):
    """
    Returns a single unified knowledge graph with rich detail data per project:
    Root → EPS Regions → Projects (with P6/SAP/TC details) → Key Vendors
    """
    global _KG_CACHE
    if _KG_CACHE["data"] and time.time() - _KG_CACHE["timestamp"] < _CACHE_TTL:
        return _KG_CACHE["data"]
        
    nodes = []
    links = []
    seen_vendors = {}
    
    # Root node
    nodes.append({
        "id": "root", "name": "Adani Green Energy", "category": 0,
        "symbolSize": 70, "value": "Enterprise Root"
    })
    
    all_mappings = db.query(models.ProjectMapping).all()
    eps_groups = {}
    
    # Pre-load TC data for exact project association
    import json
    all_tc_edges = db.query(models.TcNetworkEdge).all()
    all_tc_project_entries = db.query(models.TcProjectEntry).all()
    parsed_edge_phases = {}
    for edge in all_tc_edges:
        parsed_edge_phases[edge.id] = set()
        if edge.projects:
            try:
                parsed_edge_phases[edge.id] = set(json.loads(edge.projects))
            except:
                pass
    
    for m in all_mappings:
        p6 = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).first()
        eps = (p6.parent_eps_name if p6 else None) or "Unassigned"
        
        if eps not in eps_groups:
            eps_groups[eps] = []
        
        # ── P6 Schedule Data ──
        health = "unknown"
        progress = 0
        p6_data = None
        if p6:
            progress = round((p6.duration_percent_complete or 0) * 100)
            health = "delayed" if (p6.finish_date_variance and p6.finish_date_variance < 0) else "on_track"
            p6_data = {
                "start_date": str(p6.start_date) if p6.start_date else None,
                "finish_date": str(p6.finish_date) if p6.finish_date else None,
                "planned_finish": str(p6.scheduled_finish_date) if p6.scheduled_finish_date else None,
                "variance_days": round(p6.finish_date_variance) if p6.finish_date_variance else 0,
                "duration_pct": progress,
                "schedule_pct": round((p6.duration_percent_complete or 0) * 100),
                "status": p6.status or "N/A",
                "eps_name": p6.parent_eps_name or ""
            }
        
        # ── SAP Data ──
        plant_code = str(m.spv_plant_code or "").strip()
        sap_data = None
        if plant_code:
            # Calculate allocation ratio
            total_capacity = db.query(func.sum(models.ProjectMapping.capacity_mwac)).filter(
                models.ProjectMapping.spv_plant_code == plant_code
            ).scalar() or 1.0
            
            project_capacity = m.capacity_mwac or 0
            allocation_ratio = project_capacity / total_capacity if total_capacity > 0 else 1.0
            
            po_count = db.query(models.MTPOAmount.purchasing_document).filter(
                models.MTPOAmount.plant_code == plant_code
            ).distinct().count()
            
            po_total = db.query(func.sum(models.MTPOAmount.net_order_value)).filter(
                models.MTPOAmount.plant_code == plant_code
            ).scalar() or 0
            po_mw = db.query(func.sum(models.MTPOAmount.po_quantities_mw)).filter(
                models.MTPOAmount.plant_code == plant_code
            ).scalar() or 0
            
            req_count = db.query(models.MTRequirement).filter(models.MTRequirement.spv_plant_code == plant_code).count()
            req_total_mw = db.query(func.sum(models.MTRequirement.budgeted_units_mw)).filter(
                models.MTRequirement.spv_plant_code == plant_code
            ).scalar() or 0
            
            if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', ''):
                inv_count = db.query(models.MTInventory).filter(models.MTInventory.wbs_element.ilike(f"%{str(m.module_wbs).strip()}%")).count()
                transit_count = db.query(models.MTInTransit).filter(models.MTInTransit.wbs_element.ilike(f"%{str(m.module_wbs).strip()}%")).count()
                transit_mw = db.query(func.sum(models.MTInTransit.quantity_mw)).filter(
                    models.MTInTransit.wbs_element.ilike(f"%{str(m.module_wbs).strip()}%")
                ).scalar() or 0
                inv_alloc = 1.0
            else:
                inv_count = db.query(models.MTInventory).filter(models.MTInventory.plant_code == plant_code).count()
                transit_count = db.query(models.MTInTransit).filter(models.MTInTransit.plant_code == plant_code).count()
                transit_mw = db.query(func.sum(models.MTInTransit.quantity_mw)).filter(
                    models.MTInTransit.plant_code == plant_code
                ).scalar() or 0
                inv_alloc = allocation_ratio
            
            top_vendors = db.query(
                models.MTPOAmount.vendor_name, func.sum(models.MTPOAmount.net_order_value).label("total")
            ).filter(
                models.MTPOAmount.plant_code == plant_code
            ).group_by(models.MTPOAmount.vendor_name).order_by(func.sum(models.MTPOAmount.net_order_value).desc()).limit(3).all()
            
            top_vendors_list = []
            for v in top_vendors:
                vname = (v[0] or "Unknown").strip()
                parts = vname.split(" ", 1)
                if len(parts) == 2 and parts[0].isdigit():
                    vname = parts[1].strip()
                top_vendors_list.append({
                    "name": vname[:25], 
                    "value_cr": round((v[1] * allocation_ratio) / 10000000, 2) if v[1] else 0
                })
            
            sap_data = {
                "plant_code": plant_code,
                "po_count": round(po_count * allocation_ratio),
                "po_total_cr": round((po_total * allocation_ratio) / 10000000, 2) if po_total else 0,
                "po_mw": round(po_mw * allocation_ratio, 1) if po_mw else 0,
                "requirement_count": round(req_count * allocation_ratio),
                "requirement_mw": round(req_total_mw * allocation_ratio, 1) if req_total_mw else 0,
                "inventory_items": round(inv_count * inv_alloc),
                "in_transit_count": round(transit_count * inv_alloc),
                "in_transit_mw": round(transit_mw * inv_alloc, 1) if transit_mw else 0,
                "top_vendors": top_vendors_list
            }
        
        # ── Transmission Data ──
        tc_data = None
        if m.id:
            project_entries = [pe for pe in all_tc_project_entries if pe.mapping_id == m.id]
            phases = set(pe.phase for pe in project_entries if pe.phase)
            
            project_edges = []
            if phases:
                for edge in all_tc_edges:
                    if phases.intersection(parsed_edge_phases.get(edge.id, set())):
                        project_edges.append(edge)
                        
                # Filter by KPS if applicable
                from services.project_service import filter_tc_edges_by_kps
                project_edges = filter_tc_edges_by_kps(project_edges, project_entries)
            
            for edge in all_tc_edges:
                if edge.mapping_id == m.id and edge not in project_edges:
                    project_edges.append(edge)
            
            node_names = set()
            for edge in project_edges:
                if edge.from_node: node_names.add(edge.from_node)
                if edge.to_node: node_names.add(edge.to_node)
            
            tc_nodes_count = len(node_names)
            tc_edges_count = len(project_edges)
            
            regions = list(set(e.region for e in project_edges if e.region))
            
            def _p(val, status):
                if status and status.lower() in ['charged', 'completed']:
                    return 100.0
                if not val: return 0
                val_str = str(val).strip()
                if '/' in val_str:
                    parts = val_str.split('/')
                    try:
                        num = float(parts[0])
                        den = float(parts[1])
                        return round((num / den) * 100, 1) if den > 0 else 0
                    except: return 0
                try: return round(float(val_str.replace('%','')), 1)
                except: return 0
                
            lines_detail = []
            for e in project_edges:
                lines_detail.append({
                    "from": e.from_node or e.from_label,
                    "to": e.to_node or e.to_label,
                    "status": e.status,
                    "expected_date": str(e.expected_date) if e.expected_date else None,
                    "foundation": _p(e.foundation, e.status),
                    "erection": _p(e.erection, e.status),
                    "stringing": _p(e.stringing, e.status)
                })
            
            tc_data = {
                "total_substations": tc_nodes_count,
                "total_lines": tc_edges_count,
                "region": ", ".join(regions) if regions else "Unknown",
                "substations": list(node_names),
                "lines": lines_detail
            }
        
        eps_groups[eps].append({
            "id": m.id, "name": (m.project_name_from_p6 or m.project or "?")[:28],
            "capacity": m.capacity_mwac or 0, "health": health,
            "progress": progress, "spv": m.spv_name or "?",
            "plant_code": plant_code,
            "p6": p6_data, "sap": sap_data, "tc": tc_data
        })
    
    # Add EPS region nodes
    for eps_name, projects in eps_groups.items():
        eps_id = f"eps_{eps_name}"
        total_mw = sum(p["capacity"] for p in projects)
        delayed = sum(1 for p in projects if p["health"] == "delayed")
        
        nodes.append({
            "id": eps_id, "name": eps_name, "category": 1,
            "symbolSize": max(35, min(55, total_mw / 150)),
            "value": f"{len(projects)} projects · {round(total_mw)} MW",
            "delayed": delayed, "on_track": len(projects) - delayed,
            "projects_list": [{"id": p["id"], "name": p["name"], "capacity": p["capacity"], "health": p["health"], "progress": p["progress"]} for p in projects]
        })
        links.append({"source": "root", "target": eps_id})
        
        for p in projects:
            proj_id = f"proj_{p['id']}"
            nodes.append({
                "id": proj_id, "name": p["name"], "category": 2 if p["health"] == "on_track" else 3,
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
                            "id": vendor_id, "name": vname, "category": 4,
                            "symbolSize": 22,
                            "value": f"Vendor · {vcode}"
                        })
                    
                    links.append({
                        "source": proj_id, "target": seen_vendors[vcode],
                        "lineStyle": {"type": "dashed", "width": 1, "color": "rgba(245,158,11,0.3)"}
                    })
    
    result = {"nodes": nodes, "links": links}
    _KG_CACHE["data"] = result
    _KG_CACHE["timestamp"] = time.time()
    return result

