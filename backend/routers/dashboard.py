from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
import json

from database import get_db
import models
from services.project_service import filter_tc_edges_by_kps

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """
    Returns a global portfolio summary and a unified list of all mapped projects
    with data from P6, SAP, and Transmission. Includes all P6 projects even if unmapped.
    """
    mappings = db.query(models.ProjectMapping).all()
    p6_projects = db.query(models.P6Project).all()
    
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
            if p6_data.finish_date_variance and p6_data.finish_date_variance < 0:
                is_delayed = True
                schedule_health = "Delayed"
                portfolio_summary["delayed_projects"] += 1
            else:
                schedule_health = "On Track"
                portfolio_summary["on_track_projects"] += 1
                
        # SAP Data Mapping
        # 1. Inventory Mapping (MB52)
        inv_query = db.query(func.sum(models.MTInventory.quantity_mw))
        
        # Priority: Map strictly by WBS if provided in Master Mapping
        if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', ''):
            clean_wbs = str(m.module_wbs).strip()
            inv_query = inv_query.filter(models.MTInventory.wbs_element.ilike(f"%{clean_wbs}%"))
        else:
            # Fallback to Plant Code mapping if no WBS is mapped
            inv_query = inv_query.filter(models.MTInventory.plant_code == str(m.spv_plant_code).strip())
            
        inv_mw = inv_query.scalar() or 0
        
        # 2. PO Amount Mapping (ME2M) - only has Plant Code available
        po_mw = db.query(func.sum(models.MTPOAmount.po_quantities_mw)).filter(
            models.MTPOAmount.plant_code == str(m.spv_plant_code).strip()
        ).scalar() or 0
        
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
                "planned_duration": p6_data.planned_duration if p6_data else 0,
                "actual_duration": p6_data.actual_duration if p6_data else 0,
                "planned_cost": p6_data.planned_cost if p6_data else 0,
                "current_budget": p6_data.current_budget if p6_data else 0,
            },
            "sap": {
                "inventory_mw": round(inv_mw, 2),
                "po_mw": round(po_mw, 2)
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
        
    # Add unmapped P6 Projects
    for p in p6_projects:
        if p.project_id not in mapped_p6_ids:
            progress = p.duration_percent_complete or 0
            if p.finish_date_variance and p.finish_date_variance < 0:
                schedule_health = "Delayed"
                portfolio_summary["delayed_projects"] += 1
            else:
                schedule_health = "On Track"
                portfolio_summary["on_track_projects"] += 1
                
            project_list.append({
                "mapping_id": None,
                "project_name": "Unmapped Entity",
                "p6_project_name": p.name,
                "capacity_mwac": 0,
                "spv_plant_code": None,
                "p6": {
                    "id": p.project_id,
                    "health": schedule_health,
                    "progress": progress,
                    "start_date": p.start_date,
                    "finish_date": p.finish_date,
                    "planned_start_date": p.planned_start_date,
                    "scheduled_finish_date": p.scheduled_finish_date,
                    "data_date": p.data_date,
                    "must_finish_by_date": p.must_finish_by_date,
                    "baseline_start_date": p.baseline_start_date,
                    "baseline_finish_date": p.baseline_finish_date,
                    "planned_duration": p.planned_duration or 0,
                    "actual_duration": p.actual_duration or 0,
                    "planned_cost": p.planned_cost or 0,
                    "current_budget": p.current_budget or 0,
                },
                "sap": {"inventory_mw": 0, "po_mw": 0},
                "tc": {"status": "Unmapped", "has_data": False, "data": {"khavda": [], "rajasthan": []}}
            })
            
    portfolio_summary["total_projects"] = len(project_list)
    
    return {
        "summary": portfolio_summary,
        "projects": project_list
    }

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
    nodes = [{"id": "Adani Green Energy", "name": "Adani Green Energy", "category": 0, "symbolSize": 60, "value": "Root Enterprise"}]
    links = []

    # Get SPVs as Level 1
    spvs = db.query(models.ProjectMapping.spv_name).filter(models.ProjectMapping.spv_name.isnot(None)).distinct().all()
    spv_list = [s[0] for s in spvs if s[0]]
    if not spv_list:
        spv_list = ["Default SPV"]

    for spv in spv_list:
        nodes.append({"id": spv, "name": spv, "category": 1, "symbolSize": 45, "value": "SPV Entity"})
        links.append({"source": "Adani Green Energy", "target": spv})

    # Get Projects and map to SPV
    projects = db.query(models.ProjectMapping).limit(15).all() # limit to 15 to keep graph clean
    
    for p in projects:
        proj_id = f"Proj_{p.id}"
        proj_name = p.project_name_from_p6 or p.project
        spv = p.spv_name or "Default SPV"
        
        nodes.append({"id": proj_id, "name": proj_name, "category": 2, "symbolSize": 35, "value": f"{p.capacity_mwac or 0} MW", "raw_id": p.project})
        links.append({"source": spv, "target": proj_id})
        
        # Add Domains (Level 3)
        p6_node = f"{proj_id}_P6"
        sap_node = f"{proj_id}_SAP"
        tc_node = f"{proj_id}_TC"
        ai_node = f"{proj_id}_AI"
        
        nodes.append({"id": p6_node, "name": "P6 Schedule", "category": 3, "symbolSize": 20, "value": "Project Controls", "raw_id": p.project})
        nodes.append({"id": sap_node, "name": "SAP Material", "category": 4, "symbolSize": 20, "value": "Logistics & PR/PO", "raw_id": p.project})
        nodes.append({"id": tc_node, "name": "Transmission", "category": 5, "symbolSize": 20, "value": "Substation & Lines", "raw_id": p.project})
        nodes.append({"id": ai_node, "name": "AI Insight", "category": 6, "symbolSize": 25, "value": "Executive Summary", "raw_id": p.project})
        
        links.append({"source": proj_id, "target": p6_node})
        links.append({"source": proj_id, "target": sap_node})
        links.append({"source": proj_id, "target": tc_node})
        links.append({"source": proj_id, "target": ai_node})

    return {"nodes": nodes, "links": links}
