from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
import json
import time

from database import get_db
import models
from services.project_catalog_service import has_portfolio_filter, list_project_mappings
from services.capacity_milestone_service import CapacityMilestoneService
from services.schedule_metrics_service import ScheduleMetricsService, calculate_schedule_metrics
from services.sap_project_data_service import get_sap_project_data, get_sap_projects_data
from services.quality_analytics_service import QualityAnalyticsService
from services.freshness_service import cache_version_token
from services import transmission_service

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


def clear_dashboard_caches():
    """Clear dashboard responses derived from synchronized source data."""
    _KG_CACHE.clear()
    _SUMMARY_CACHE.clear()


def _serialize_dashboard_quality(overview, scorecard, snapshots, mappings):
    """Adapt canonical quality DTOs to the established dashboard contract."""
    mapping_by_project = {mapping.project_id: mapping for mapping in mappings if mapping.project_id}
    mappings_by_name = {
        str(name).strip().casefold(): mapping
        for mapping in mappings
        for name in (mapping.project, mapping.project_name_from_p6)
        if name
    }
    projects_by_contractor = {}
    for snapshot in snapshots:
        mapping = mapping_by_project.get(snapshot.project_id)
        if mapping is None and snapshot.project_name:
            mapping = mappings_by_name.get(snapshot.project_name.strip().casefold())
        open_by_contractor = {}
        for nc in snapshot.ncs:
            if nc.status == "completed":
                continue
            name = " ".join(str(nc.vendor_name or "Unknown").strip().split()) or "Unknown"
            key = name.casefold()
            open_by_contractor[key] = open_by_contractor.get(key, 0) + 1
        for contractor, count in open_by_contractor.items():
            projects_by_contractor.setdefault(contractor, []).append({
                "project_name": (mapping.project if mapping else snapshot.project_name) or "Unknown Project",
                "p6_name": (mapping.project_name_from_p6 if mapping else snapshot.project_name) or "Unknown Project",
                "mapping_id": mapping.id if mapping else None,
                "p6_id": snapshot.project_id,
                "open_ncs": count,
            })

    contractors = sorted(
        (contractor for contractor in scorecard.contractors if contractor.open),
        key=lambda contractor: (-contractor.open, contractor.name.casefold()),
    )[:15]
    provenance = overview.provenance
    return {
        "total_ncs": overview.total_ncs,
        "open_ncs": overview.open_ncs,
        "resolved_ncs": overview.completed_ncs,
        "closure_rate": overview.closure_rate,
        "total_rfis": overview.total_rfis,
        "completed_rfis": overview.rfis_completed,
        "top_contractors": [
            {
                "name": contractor.name,
                "value": contractor.open,
                "projects": sorted(
                    projects_by_contractor.get(contractor.name.casefold(), []),
                    key=lambda project: project["open_ncs"],
                    reverse=True,
                ),
            }
            for contractor in contractors
        ],
        "freshness": {
            "data_as_of": provenance.data_as_of,
            "nc_last_synced_at": provenance.nc_last_synced_at,
            "rfi_last_synced_at": provenance.rfi_last_synced_at,
        },
        "warnings": [
            {
                "source": warning.source,
                "source_id": warning.source_id,
                "reason": warning.reason,
                "candidates": list(warning.candidates),
            }
            for warning in overview.warnings
        ],
    }


def _serialize_knowledge_graph_schedule(schedule):
    """Adapt canonical schedule metrics to the established graph payload."""
    if not schedule.p6_available:
        return "unknown", 0, None, "Unassigned"

    progress = round(schedule.progress_pct or 0)
    eps = getattr(schedule, "parent_eps_name", None) or "Unassigned"
    return (
        "delayed" if schedule.is_delayed else "on_track",
        progress,
        {
            "start_date": str(schedule.start_date) if schedule.start_date else None,
            "finish_date": str(schedule.finish_date) if schedule.finish_date else None,
            "planned_finish": str(schedule.scheduled_finish) if schedule.scheduled_finish else None,
            "variance_days": round(schedule.finish_date_variance or 0),
            "duration_pct": progress,
            "construction_pct": progress,
            "schedule_pct": progress,
            "status": schedule.status or "N/A",
            "eps_name": eps if eps != "Unassigned" else "",
        },
        eps,
    )


def _serialize_knowledge_graph_sap(mapping, snapshot):
    """Adapt canonical project SAP aggregates to the legacy graph contract."""
    plant_code = str(mapping.spv_plant_code or "").strip()
    agel_code = str(mapping.agel or "").strip()
    if not plant_code and not agel_code:
        return None

    totals = snapshot["totals"]
    purchase_orders = totals["purchase_orders"]
    logistics = totals["logistics"]
    vendors = []
    for vendor in snapshot["vendors"][:3]:
        name = vendor["name"].strip()
        parts = name.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            name = parts[1].strip()
        vendors.append({
            "name": name[:25],
            "value_cr": round(vendor["order_value"] / 10000000, 2),
        })

    return {
        "plant_code": plant_code,
        "po_count": round(logistics["purchase_order_count"]),
        "po_total_cr": round(purchase_orders["order_value"] / 10000000, 2),
        "po_mw": round(logistics["ordered_mw"], 1),
        "requirement_count": 0,
        "requirement_mw": 0,
        "inventory_items": round(logistics["inventory_item_count"]),
        "inventory_mw": round(logistics["inventory_mw"], 1),
        "in_transit_count": round(logistics["in_transit_count"]),
        "in_transit_mw": round(logistics["in_transit_mw"], 1),
        "top_vendors": vendors,
    }


def _serialize_knowledge_graph_transmission(mapping, edges):
    """Adapt canonical transmission line DTOs and mapped overrides."""
    progress = mapping.tc_progress or {}
    lines_charged = progress.get("linesCharged", {})
    if not edges and not progress:
        return None
    return {
        "total_lines": lines_charged.get("total", len(edges)),
        "charged_lines": lines_charged.get(
            "count", sum(line["canonical_status"] == "completed" for line in edges)
        ),
        "delayed_lines": progress.get("delayed", {}).get(
            "count", sum(bool(line["is_delayed"]) for line in edges)
        ),
        "lines": [
            {
                "name": f'{line["from_label"]} \u2192 {line["to_label"]}',
                "status": line["status"],
                "normalized_status": line["normalized_status"],
                "foundation": line["foundation"],
                "erection": line["erection"],
                "stringing": line["stringing"],
                "expected_date": line["expected_date"],
            }
            for line in edges
        ],
    }

@router.get("/summary")
def get_dashboard_summary(portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    """
    Returns a global portfolio summary and a unified list of all mapped projects
    with optional data from P6, SAP, and Transmission.
    """
    global _SUMMARY_CACHE
    cache_key = str(portfolio).lower() if portfolio else "all"
    cache_version = cache_version_token(db, ("P6", "SAP", "TC", "Pulse", "Mapping", "Capacity"))
    
    if not nocache and cache_key in _SUMMARY_CACHE:
        entry = _SUMMARY_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _CACHE_TTL and entry.get("version") == cache_version:
            return entry["data"]
            
    mappings = list_project_mappings(db, portfolio)
    sap_by_project = get_sap_projects_data(
        db, [m.project_id for m in mappings if m.project_id], mappings=list_project_mappings(db)
    )
    tc_snapshot = transmission_service.build_transmission_snapshot(db)
    raw_p6_projects = db.query(models.P6Project).all()

    if has_portfolio_filter(portfolio):
        mapped_ids = [m.project_id for m in mappings if m.project_id]
        raw_p6_projects = [p for p in raw_p6_projects if p.project_id in mapped_ids]

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
    
    # Requirements are not WBS-addressable; retain the legacy requirement source
    # while all project-addressable SAP tables come from the shared snapshot.
    req_by_plant = {str(r[0]).strip(): r[1] for r in db.query(models.MTRequirement.spv_plant_code, func.sum(models.MTRequirement.budgeted_units_mw)).group_by(models.MTRequirement.spv_plant_code).all() if r[0]}
    # Pre-fetch Capacity Overview to get accurate COD and Trial Run MW (and dynamically computed WTG capacity)
    cap_data = get_capacity_overview(portfolio, db)
    proj_cap_dict = {p["project_id"]: p for p in cap_data.get("projects", []) if p["project_id"]}
    
    portfolio_summary["achieved_mw"] = sum(cap_data.get("totals", {}).values())

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

        schedule = calculate_schedule_metrics(p6_data)
        is_delayed = bool(schedule.is_delayed)
        schedule_health = "Unknown"
        progress = schedule.progress_pct if schedule.progress_pct is not None else 0

        if schedule.p6_available:
            mapped_p6_ids.add(p6_data.project_id)
            if is_delayed:
                schedule_health = "Delayed"
                portfolio_summary["delayed_projects"] += 1
            else:
                schedule_health = "On Track"
                portfolio_summary["on_track_projects"] += 1
        else:
            schedule_health = "On Track"
            portfolio_summary["on_track_projects"] += 1
                
        # SAP Data Mapping
        sap_data = sap_by_project.get(m.project_id or f"mapping:{m.id}")
        sap_po = sap_data["totals"]["purchase_orders"]
        sap_inventory = sap_data["totals"]["inventory"]
        plant_code_str = str(m.spv_plant_code).strip() if m.spv_plant_code else ""
        agel_code_str = str(m.agel).strip() if m.agel else ""
        
        allocation_ratio = sap_data["scope"]["allocation_ratio"]

        # We will use whichever code has the data (often AGEL code for PO/Inventory)
        req_mw = req_by_plant.get(plant_code_str, 0) or req_by_plant.get(agel_code_str, 0)
        
        inv_qty = sap_inventory["quantity"]
        it_qty = sap_po["pending_quantity"]
        po_qty = sap_po["ordered_quantity"]
        po_value = sap_po["order_value"]
        po_delivered_cr = sap_po["delivered_value_inr_cr"]
        req_qty = (req_mw or 0) * allocation_ratio

        portfolio_summary["total_inventory_qty"] += inv_qty
        portfolio_summary["total_po_qty"] += po_qty

        # TC Data
        _, project_entries, tc_edges = transmission_service.project_edges(db, m.project_id, tc_snapshot)
        tc_khavda = [e for e in tc_edges if transmission_service.normalize_region(e.region) == "Khavda"]
        tc_rajasthan = [e for e in tc_edges if transmission_service.normalize_region(e.region) == "Rajasthan"]
        
        tc_summary = "0 Edges"
        if tc_khavda and tc_rajasthan:
            tc_summary = f"{len(tc_khavda)} Khavda, {len(tc_rajasthan)} Rajasthan Edges"
        elif tc_khavda:
            tc_summary = f"{len(tc_khavda)} Khavda Edges"
        elif tc_rajasthan:
            tc_summary = f"{len(tc_rajasthan)} Rajasthan Edges"
            
        project_list.append({
            "mapping_id": m.id,
            "project_id": m.project_id,
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
                "p6_available": schedule.p6_available,
                "progress_unit": schedule.progress_units,
                "progress_formula_version": schedule.progress_formula_version,
                "finish_date_variance_unit": schedule.finish_date_variance_units,
                "last_synced_at": schedule.last_synced_at,
            },
            "sap": {
                "req_qty": round(req_qty, 2),
                "po_qty": round(po_qty, 2),
                "in_transit_qty": round(it_qty, 2),
                "inventory_qty": round(inv_qty, 2),
                "po_value": round(po_value, 2),
                "po_delivered_cr": round(po_delivered_cr, 2),
                "scope": sap_data["scope"],
                "units": sap_data["units"],
                "freshness": sap_data["freshness"],
                "warnings": sap_data["warnings"],
                "po_row_count": sap_data["counts"]["po_row_count"],
                "distinct_po_count": sap_data["counts"]["distinct_po_count"],
            },
            "tc": {
                "status": tc_summary,
                "has_data": bool(tc_khavda or tc_rajasthan),
                "data": {
                    "khavda": [{"id": t.id, "project": m.project or m.project_name_from_p6, "phase": _safe_parse_phase(t.projects), "voltage": t.voltage, "status": t.status} for t in tc_khavda],
                    "rajasthan": [{"id": t.id, "project": m.project or m.project_name_from_p6, "phase": _safe_parse_phase(t.projects), "voltage": t.voltage, "status": t.status} for t in tc_rajasthan]
                },
                "freshness": transmission_service.freshness(db, snapshot=tc_snapshot),
            }
        })
        
    # ... inside get_dashboard_summary ...
    portfolio_summary["total_projects"] = len(project_list)
    
    quality_overview = QualityAnalyticsService.portfolio_overview(db, portfolio)
    quality_scorecard = QualityAnalyticsService.contractor_scorecard(db, portfolio)
    quality_projects = QualityAnalyticsService.project_snapshots(db, portfolio)
    portfolio_summary["quality"] = _serialize_dashboard_quality(
        quality_overview, quality_scorecard, quality_projects, mappings
    )
    
    result = {
        "summary": portfolio_summary,
        "projects": project_list
    }
    
    _SUMMARY_CACHE[cache_key] = {"data": result, "timestamp": time.time(), "version": cache_version}
    return result

@router.get("/projects/{mapping_id}")
def get_project_details(mapping_id: int, db: Session = Depends(get_db)):
    """Get full 360 view for a single project"""
    m = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == mapping_id).first()
    if not m:
        return {"error": "Project not found"}
        
    p6_data = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).first()
    
    sap_data = get_sap_project_data(db, m.project_id)
    inventory = sap_data["inventory"]
    po_items = sap_data["purchase_orders"]
    in_transit = [po for po in po_items if (po.still_to_deliver_qty or 0) > 0]

    _, _, tc_edges = transmission_service.project_edges(db, m.project_id)
    
    tc_k_dicts = []
    tc_r_dicts = []
    
    for t in tc_edges:
        d = {c: getattr(t, c) for c in t.__table__.columns.keys()}
        d["project"] = m.project or m.project_name_from_p6
        d["phase"] = _safe_parse_phase(t.projects)
        if transmission_service.normalize_region(t.region) == "Khavda":
            tc_k_dicts.append(d)
        elif transmission_service.normalize_region(t.region) == "Rajasthan":
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
            "inventory_summary": sap_data["totals"]["inventory"]["quantity"],
            "po_summary": sap_data["totals"]["purchase_orders"]["ordered_quantity"],
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
    cache_version = cache_version_token(db, ("P6", "SAP", "TC", "Pulse", "Mapping", "Capacity"))
    
    if not nocache and cache_key in _KG_CACHE:
        entry = _KG_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _CACHE_TTL and entry.get("version") == cache_version:
            return entry["data"]
        
    nodes = []
    links = []
    seen_vendors = {}
    
    # Root node
    nodes.append({
        "id": "root", "name": "Adani Green Energy", "category": 0,
        "symbolSize": 70, "value": "Enterprise Root"
    })
    
    all_mappings = list_project_mappings(db, portfolio)
    catalog_mappings = list_project_mappings(db)
    sap_by_project = get_sap_projects_data(
        db,
        [mapping.project_id for mapping in all_mappings if mapping.project_id],
        mappings=catalog_mappings,
    )
    tc_snapshot = transmission_service.build_transmission_snapshot(db)
    portfolio_groups = {}
    cap_data = CapacityMilestoneService.get_portfolio_overview(db, portfolio)
    capacity_by_mapping = {
        project.get("source_facts", {}).get("mapping_id"): project
        for project in cap_data.get("projects", [])
    }
    schedules = {
        project_id: ScheduleMetricsService.get_by_project_id(db, project_id)
        for project_id in dict.fromkeys(
            mapping.project_id for mapping in all_mappings if mapping.project_id
        )
    }
    
    for m in all_mappings:
        schedule = schedules.get(m.project_id, calculate_schedule_metrics(None))
        health, progress, p6_data, eps = _serialize_knowledge_graph_schedule(schedule)
        
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
        
        sap_snapshot = sap_by_project.get(m.project_id or f"mapping:{m.id}")
        sap_data = _serialize_knowledge_graph_sap(m, sap_snapshot)
        top_vendor = next(iter(sap_snapshot["vendors"]), None)
        _, _, tc_edges = transmission_service.project_edges(db, m.project_id, tc_snapshot)
        tc_data = _serialize_knowledge_graph_transmission(
            m, [transmission_service.edge_dict(edge) for edge in tc_edges]
        )

        pm_cap = capacity_by_mapping.get(m.id, {})
        cod_mw = pm_cap.get("cod_mw", 0)
        tr_mw = pm_cap.get("tr_mw", 0)
        computed_capacity = pm_cap.get("total_capacity", m.capacity_mwac or 0)

        portfolio_groups[port_name][eps].append({
            "id": m.id, "project_id": m.project_id, "name": (m.project_name_from_p6 or m.project or "?")[:28],
            "capacity": computed_capacity, "health": health,
            "progress": progress, "spv": m.spv_name or "?",
            "vendor_key": (top_vendor or {}).get("vendor_code") or (top_vendor or {}).get("name"),
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
                
                top_vendor = next(iter((p["sap"] or {}).get("top_vendors", [])), None)
                if top_vendor:
                    vcode = p["vendor_key"] or top_vendor["name"]
                    if vcode not in seen_vendors:
                        vendor_id = f"vendor_{len(seen_vendors)}"
                        seen_vendors[vcode] = vendor_id
                        nodes.append({
                            "id": vendor_id, "name": top_vendor["name"][:22], "category": 5,
                            "symbolSize": 22,
                            "value": f"Vendor · {vcode}"
                        })

                    links.append({
                        "source": proj_id, "target": seen_vendors[vcode],
                        "lineStyle": {"type": "dashed", "width": 1, "color": "rgba(245,158,11,0.3)"}
                    })
    
    result = {"nodes": nodes, "links": links}
    _KG_CACHE[cache_key] = {"data": result, "timestamp": time.time(), "version": cache_version}
    return result

@router.get("/capacity-overview")
def get_capacity_overview(portfolio: Optional[str] = None, db: Session = Depends(get_db)):
    """Return the canonical capacity overview using the existing route contract."""
    return CapacityMilestoneService.get_portfolio_overview(db, portfolio)
