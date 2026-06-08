from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import models
import logging
import json

logger = logging.getLogger(__name__)

def filter_tc_edges_by_kps(edges, project_entries):
    kps_mapping = {'1': 'I', '2': 'II', '3': 'III', '4': 'IV', '5': 'V'}
    kps_nodes = set()
    for pe in project_entries:
        if pe.kps:
            kps_upper = pe.kps.upper()
            if '-' in kps_upper:
                parts = kps_upper.split('-')
                if len(parts) == 2 and parts[1] in kps_mapping:
                    kps_nodes.add(f"KPS-{kps_mapping[parts[1]]}")
                else:
                    kps_nodes.add(kps_upper)
            else:
                num = kps_upper.replace("KPS", "").strip()
                if num in kps_mapping:
                    kps_nodes.add(f"KPS-{kps_mapping[num]}")
                else:
                    kps_nodes.add(kps_upper)
    if not kps_nodes:
        return edges
    touching_edges = []
    for edge in edges:
        labels = [
            str(edge.from_label).upper() if edge.from_label else "",
            str(edge.to_label).upper() if edge.to_label else "",
            str(edge.from_node).upper() if edge.from_node else "",
            str(edge.to_node).upper() if edge.to_node else ""
        ]
        if any(kps in label for label in labels for kps in kps_nodes):
            touching_edges.append(edge)
    return touching_edges if touching_edges else edges

def calculate_project_360_metrics(db: Session):
    mappings = db.query(models.ProjectMapping).all()
    all_tc_edges = db.query(models.TcNetworkEdge).all()
    
    # Pre-parse edge phases ONCE for extreme performance
    parsed_edge_phases = {}
    for edge in all_tc_edges:
        parsed_edge_phases[edge.id] = set()
        if edge.projects:
            try:
                parsed_edge_phases[edge.id] = set(json.loads(edge.projects))
            except:
                pass
                
    results = []

    for m in mappings:
        # 1. P6 Data
        p6_proj = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).first()
        if not p6_proj:
            continue
            
        spi = p6_proj.schedule_performance_index or 1.0
        cpi = p6_proj.cost_performance_index or 1.0
        sched_var = p6_proj.finish_date_variance or 0
        cost_var = p6_proj.total_cost_variance or 0
        progress = p6_proj.duration_percent_complete or 0
        
        # 2. SAP Data
        codes = [c for c in [m.spv_plant_code, m.agel] if c]
        
        # Calculate Total Plant Capacity for Pro-Rata Allocation
        total_capacity = db.query(func.sum(models.ProjectMapping.capacity_mwac)).filter(
            or_(
                models.ProjectMapping.spv_plant_code.in_(codes),
                models.ProjectMapping.agel.in_(codes)
            )
        ).scalar() or 1.0
        
        project_capacity = m.capacity_mwac or 0
        allocation_ratio = project_capacity / total_capacity
        
        raw_po_vol_plant = db.query(func.sum(models.MTPOAmount.po_quantities_mw)).filter(models.MTPOAmount.plant_code.in_(codes)).scalar() or 0
        raw_transit_vol_plant = db.query(func.sum(models.MTInTransit.quantity_mw)).filter(models.MTInTransit.plant_code.in_(codes)).scalar() or 0
        raw_inv_vol_plant = db.query(func.sum(models.MTInventory.quantity_mw)).filter(models.MTInventory.plant_code.in_(codes)).scalar() or 0
        
        # Always use Pro-Rata Allocation for PO Volume (since ME2M has no WBS)
        raw_po_vol = raw_po_vol_plant * allocation_ratio
        
        # Hybrid Exact WBS Mapping for Inventory and In-Transit
        if m.module_wbs:
            raw_inv_vol = db.query(func.sum(models.MTInventory.quantity_mw)).filter(models.MTInventory.wbs_element == m.module_wbs).scalar() or 0
            raw_transit_vol = db.query(func.sum(models.MTInTransit.quantity_mw)).filter(models.MTInTransit.wbs_element == m.module_wbs).scalar() or 0
        else:
            raw_inv_vol = raw_inv_vol_plant * allocation_ratio
            raw_transit_vol = raw_transit_vol_plant * allocation_ratio
        
        inv_vol = raw_inv_vol
        transit_vol = raw_transit_vol
        po_vol = raw_po_vol
        
        # Simple material availability calculation
        mat_avail = 0
        if po_vol > 0:
            mat_avail = round(((inv_vol + transit_vol) / po_vol) * 100)
        elif inv_vol > 0:
            mat_avail = 100
            
        # 3. Business Logic — Intelligence-Grade Enrichment
        # ─────────────────────────────────────────────────

        # Fallback for sched_var if None
        if sched_var == 0 and p6_proj.baseline_finish_date:
            compare_date = p6_proj.scheduled_finish_date or p6_proj.finish_date
            if compare_date:
                sched_var = (p6_proj.baseline_finish_date - compare_date).days

        # Fallback for SPI if None
        if spi == 1.0 and p6_proj.schedule_performance_index is None:
            if p6_proj.actual_duration and p6_proj.planned_duration and p6_proj.actual_duration > 0:
                spi = p6_proj.planned_duration / p6_proj.actual_duration

        # ── Multi-dimensional Risk Flags ──
        has_material_risk   = mat_avail < 80 and po_vol > 0
        has_schedule_risk   = sched_var < -10 or spi < 0.95
        has_vendor_risk     = transit_vol == 0 and po_vol > 0
        has_financial_risk  = cost_var < -1000000
        has_procurement_risk = po_vol == 0 and progress < 50
        
        # COD Risk Detection
        cod_at_risk = False
        delay_days = abs(round(sched_var)) if sched_var < 0 else 0
        if delay_days > 14 or (has_material_risk and mat_avail < 50) or has_vendor_risk:
            cod_at_risk = True

        # ── Risk Score (0-100) ──
        base_risk = 0
        abs_var = abs(sched_var) if sched_var < 0 else 0
        if abs_var > 0: base_risk += min(40, abs_var)
        if spi < 1.0: base_risk += (1.0 - spi) * 100
        if mat_avail < 100 and po_vol > 0: base_risk += (100 - mat_avail) * 0.5
        if has_vendor_risk: base_risk += 15
        if has_financial_risk: base_risk += 10
        risk_score = min(100, round(base_risk))
        health_score = max(0, 100 - risk_score)
        
        # ── 5-Tier Status Classification ──
        pct_complete = progress * 100 if progress < 1 else progress
        if pct_complete >= 99:
            status_tier = "Completed"
        elif risk_score >= 60 or (sched_var < -30 and spi < 0.8) or (mat_avail < 30 and po_vol > 0):
            status_tier = "Critical"
        elif risk_score >= 40 or sched_var < -20 or (mat_avail < 50 and po_vol > 0) or has_vendor_risk:
            status_tier = "High Risk"
        elif risk_score >= 20 or sched_var < -10 or (mat_avail < 80 and po_vol > 0):
            status_tier = "Watchlist"
        else:
            status_tier = "Healthy"

        # ── Primary Issue (intelligence-first labeling) ──
        primary_issue = "On Track"
        if mat_avail < 50 and po_vol > 0:
            primary_issue = "Supply Chain Risk"
        elif transit_vol == 0 and po_vol > 0:
            primary_issue = "Vendor Execution Risk"
        elif sched_var < -30:
            primary_issue = "Schedule Variance"
        elif cost_var < -1000000:
            primary_issue = "Budget Variance"
        elif has_procurement_risk:
            primary_issue = "Procurement Delay"
        elif spi < 0.9:
            primary_issue = "Resource Constraint"
        elif sched_var < -10:
            primary_issue = "Schedule Variance"

        # ── Risk Categories (for smart filters) ──
        risk_categories = []
        if has_material_risk: risk_categories.append("Material Risk")
        if has_schedule_risk: risk_categories.append("Schedule Risk")
        if has_vendor_risk: risk_categories.append("Vendor Risk")
        if has_financial_risk: risk_categories.append("Financial Risk")
        if has_procurement_risk: risk_categories.append("Procurement Risk")
        if cod_at_risk: risk_categories.append("COD Risk")
        if spi < 0.9: risk_categories.append("Resource Risk")
        if not risk_categories:
            risk_categories.append("No Active Risks")

        # ── Impact Analysis ──
        impact_lines = []
        if delay_days > 0:
            impact_lines.append(f"Expected delay: {delay_days} days")
        if cost_var < -100000:
            cost_cr = abs(round(cost_var / 10000000, 2))
            impact_lines.append(f"Potential cost impact: ₹{cost_cr} Cr")
        if cod_at_risk:
            impact_lines.append("COD risk detected")
        if has_material_risk and po_vol > 0:
            gap_mw = round(po_vol - inv_vol - transit_vol, 1)
            if gap_mw > 0:
                impact_lines.append(f"Supply gap: {gap_mw} MW pending")
        if not impact_lines:
            impact_lines.append("No significant impact detected")

        # ── Confidence Score ──
        # Higher confidence when we have more data points
        confidence = 70
        if p6_proj.schedule_performance_index is not None: confidence += 8
        if p6_proj.cost_performance_index is not None: confidence += 5
        if p6_proj.baseline_finish_date is not None: confidence += 5
        if po_vol > 0: confidence += 7
        if p6_proj.activity_count and p6_proj.activity_count > 0: confidence += 5
        confidence = min(98, confidence)

        # ── AI Recommendation ──
        if primary_issue == "Material Bottleneck":
            gap_mw = round(po_vol - inv_vol - transit_vol, 1)
            ai_recommendation = f"Expedite vendor dispatch for {gap_mw} MW shortfall. Prioritize critical path materials."
            ai_insight = f"Only {mat_avail}% of ordered materials available. {round(inv_vol, 1)} MW received against {round(po_vol, 1)} MW ordered — commissioning timeline at risk."
        elif primary_issue == "Vendor Delay":
            ai_recommendation = f"Escalate vendor follow-up for {round(po_vol, 1)} MW on order. Evaluate backup suppliers."
            ai_insight = f"No material dispatched despite {round(po_vol, 1)} MW on order. Zero in-transit volume indicates vendor execution failure."
        elif primary_issue == "Schedule Slippage":
            ai_recommendation = "Fast-track critical path activities. Authorize overtime or resource reallocation from healthy projects."
            ai_insight = f"Project is {delay_days} days behind baseline with SPI at {round(spi, 2)}, indicating systemic scheduling breakdown."
        elif primary_issue == "Cost Overrun":
            cost_cr = abs(round(cost_var / 10000000, 2))
            ai_recommendation = "Initiate cost audit. Review change orders and scope creep. Freeze non-critical procurement."
            ai_insight = f"Cost variance of ₹{cost_cr} Cr detected. Financial controls require immediate attention."
        elif primary_issue == "Procurement Gap":
            ai_recommendation = f"Release pending POs immediately. Project at {round(pct_complete, 0)}% with zero procurement activity."
            ai_insight = "No purchase orders placed despite project being in execution phase. Procurement pipeline is empty."
        elif primary_issue == "Resource Shortage":
            ai_recommendation = "Approve resource augmentation. Deploy additional workforce to recover SPI."
            ai_insight = f"SPI at {round(spi, 2)} suggests resource constraint. Current pace insufficient to meet baseline schedule."
        elif primary_issue == "Engineering Delay":
            ai_recommendation = "Expedite engineering approvals. Review pending technical submissions."
            ai_insight = f"Schedule slipping by {delay_days} days, likely driven by engineering or approval bottlenecks."
        else:
            ai_recommendation = "Continue standard monitoring. No intervention required."
            ai_insight = f"Project progressing at {round(pct_complete, 1)}% with healthy performance indicators. No material risks detected."

        # ── Exact TC Data Summary ──
        project_entries = db.query(models.TcProjectEntry).filter(models.TcProjectEntry.mapping_id == m.id).all()
        phases = set(pe.phase for pe in project_entries if pe.phase)
        
        tc_network_edges = []
        if phases:
            filtered_edges = []
            for edge in all_tc_edges:
                if phases.intersection(parsed_edge_phases[edge.id]):
                    filtered_edges.append(edge)
                    
            tc_network_edges = filter_tc_edges_by_kps(filtered_edges, project_entries)
            
        direct_tc_edges = [e for e in all_tc_edges if e.mapping_id == m.id]
        tc_network_edges.extend(direct_tc_edges)
        tc_edges_count = len({e.id: e for e in tc_network_edges})

        forecast_finish = p6_proj.scheduled_finish_date.strftime("%Y-%m-%d") if p6_proj.scheduled_finish_date else "N/A"
        forecast_month = p6_proj.scheduled_finish_date.strftime("%b %Y") if p6_proj.scheduled_finish_date else "TBD"

        results.append({
            # Identifiers
            "projectId": p6_proj.project_id,
            "projectName": p6_proj.name,
            "sapPlantCode": m.spv_plant_code,
            "agelCode": m.agel,
            "capacityMW": project_capacity,
            # Intelligence Fields (card-facing)
            "statusTier": status_tier,
            "primaryIssue": primary_issue,
            "impactLines": impact_lines,
            "confidence": confidence,
            "aiRecommendation": ai_recommendation,
            "aiInsight": ai_insight,
            "riskCategories": risk_categories,
            "codAtRisk": cod_at_risk,
            "delayDays": delay_days,
            # Underlying Metrics (drill-down only)
            "progress": round(progress, 3),
            "spi": round(spi, 2),
            "cpi": round(cpi, 2),
            "scheduleVariance": round(sched_var),
            "costVariance": round(cost_var, 2),
            "poVolumeMW": round(po_vol, 1),
            "inTransitMW": round(transit_vol, 1),
            "inventoryMW": round(inv_vol, 1),
            "materialAvailability": mat_avail,
            "riskScore": risk_score,
            "healthScore": health_score,
            "tcEdgesCount": tc_edges_count,
            "forecastFinish": forecast_finish,
            "forecastMonth": forecast_month,
            "health": status_tier,  # alias for backward compat
            "keyIssue": primary_issue,  # alias for backward compat
            "recommendedAction": ai_recommendation,  # alias for backward compat
            # Date & Duration
            "startDate": p6_proj.start_date.strftime("%Y-%m-%d") if p6_proj.start_date else None,
            "finishDate": p6_proj.finish_date.strftime("%Y-%m-%d") if p6_proj.finish_date else None,
            "baselineFinishDate": p6_proj.baseline_finish_date.strftime("%Y-%m-%d") if p6_proj.baseline_finish_date else None,
            "status": p6_proj.status,
            "durationPercentComplete": round(pct_complete, 1),
            # Activity
            "activityCount": p6_proj.activity_count or 0,
            "completedActivities": p6_proj.completed_activity_count or 0,
            "inProgressActivities": p6_proj.in_progress_activity_count or 0,
            "notStartedActivities": p6_proj.not_started_activity_count or 0,
            "plannedDuration": p6_proj.planned_duration,
            "actualDuration": p6_proj.actual_duration,
            "remainingDuration": p6_proj.remaining_duration,
            "parentEPS": p6_proj.parent_eps_name,
        })

    return sorted(results, key=lambda x: x['riskScore'], reverse=True)


def get_project_360_detail(db: Session, project_id: str):
    """
    Returns enriched per-project intelligence detail:
    - All P6 fields (dates, floats, costs, baselines)
    - SAP vendor breakdown (from MTPOAmount) — pro-rata allocated to this project
    - SAP in-transit details (from MTInTransit) — WBS-filtered or pro-rata
    - SAP inventory details (from MTInventory) — WBS-filtered or pro-rata
    """
    # 1. Resolve mapping
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()
    
    if not mapping:
        return {"error": "Project not found in mapping"}

    p6_proj = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()

    if not p6_proj:
        return None

    # SAP Data
    codes = [c for c in [mapping.spv_plant_code, mapping.agel] if c]
    
    # Calculate Total Plant Capacity for Pro-Rata Allocation
    total_capacity = db.query(func.sum(models.ProjectMapping.capacity_mwac)).filter(
        or_(
            models.ProjectMapping.spv_plant_code.in_(codes),
            models.ProjectMapping.agel.in_(codes)
        )
    ).scalar() or 1.0

    project_capacity = mapping.capacity_mwac or 0
    allocation_ratio = project_capacity / total_capacity if total_capacity > 0 else 1.0

    # ── SAP: Purchase Orders (ME2M) — POs don't have WBS, always pro-rata ──
    po_records_all = db.query(models.MTPOAmount).filter(
        models.MTPOAmount.plant_code.in_(codes)
    ).all() if codes else []

    # Apply pro-rata: multiply MW and value by allocation ratio
    sap_vendors = []
    vendor_summary = {}
    for po in po_records_all:
        vendor_name = po.vendor_name or "Unknown Vendor"
        vendor_code = po.vendor_code or ""
        
        # Parse "105791 AMBUJA CEMENTS LTD" into code and name
        if not vendor_code and vendor_name != "Unknown Vendor":
            parts = vendor_name.split(" ", 1)
            if len(parts) == 2 and parts[0].isdigit():
                vendor_code = parts[0]
                vendor_name = parts[1]
                
        allocated_mw = round((po.po_quantities_mw or 0) * allocation_ratio, 2)
        allocated_value = round((po.net_order_value or 0) * allocation_ratio, 2)
        sap_vendors.append({
            "poNumber": po.purchasing_document,
            "vendorCode": vendor_code,
            "vendorName": vendor_name,
            "materialCode": po.material_code,
            "materialType": po.material_type,
            "poQuantity": po.po_quantities,
            "poQuantityMW": allocated_mw,
            "netOrderValue": allocated_value,
            "companyCode": po.company_code,
            "plantCode": po.plant_code,
        })
        if vendor_name not in vendor_summary:
            vendor_summary[vendor_name] = {
                "vendorName": vendor_name,
                "vendorCode": vendor_code,
                "totalMW": 0,
                "totalValue": 0,
                "poCount": 0,
                "materials": set(),
            }
        vendor_summary[vendor_name]["totalMW"] += allocated_mw
        vendor_summary[vendor_name]["totalValue"] += allocated_value
        vendor_summary[vendor_name]["poCount"] += 1
        if po.material_code:
            vendor_summary[vendor_name]["materials"].add(po.material_code)

    # Format vendor summary
    vendor_breakdown = []
    for v in vendor_summary.values():
        vendor_breakdown.append({
            "vendorName": v["vendorName"],
            "vendorCode": v["vendorCode"],
            "totalMW": round(v["totalMW"], 2),
            "totalValue": round(v["totalValue"], 2),
            "poCount": v["poCount"],
            "materialCount": len(v["materials"]),
        })
    vendor_breakdown.sort(key=lambda x: x["totalMW"], reverse=True)

    # ── SAP: In-Transit (MIGO) — WBS-filtered if available, else pro-rata ──
    if mapping.module_wbs:
        transit_records = db.query(models.MTInTransit).filter(
            models.MTInTransit.wbs_element == mapping.module_wbs
        ).all()
        transit_allocation = 1.0  # exact match, no pro-rata needed
    else:
        transit_records = db.query(models.MTInTransit).filter(
            models.MTInTransit.plant_code.in_(codes)
        ).all() if codes else []
        transit_allocation = allocation_ratio

    sap_intransit = []
    for t in transit_records:
        sap_intransit.append({
            "materialCode": t.material_code,
            "vendorCode": t.vendor_code,
            "vendorName": t.vendor_name,
            "poNumber": t.po_number,
            "quantity": t.inbound_delivery_quantity,
            "quantityMW": round((t.quantity_mw or 0) * transit_allocation, 2),
            "grPostingDate": t.gr_posting_date.strftime("%Y-%m-%d") if t.gr_posting_date else None,
            "aribaInvoiceDate": t.ariba_invoice_date.strftime("%Y-%m-%d") if t.ariba_invoice_date else None,
            "wbsElement": t.wbs_element,
            "plantCode": t.plant_code,
            "companyCode": t.company_code,
        })

    # ── SAP: Inventory (MB52) — WBS-filtered if available, else pro-rata ──
    if mapping.module_wbs:
        inv_records = db.query(models.MTInventory).filter(
            models.MTInventory.wbs_element == mapping.module_wbs
        ).all()
        inv_allocation = 1.0  # exact match
    else:
        inv_records = db.query(models.MTInventory).filter(
            models.MTInventory.plant_code.in_(codes)
        ).all() if codes else []
        inv_allocation = allocation_ratio

    sap_inventory = []
    for inv in inv_records:
        sap_inventory.append({
            "materialCode": inv.material_code,
            "vendorCode": inv.vendor_code,
            "purchaseOrder": inv.purchase_order,
            "quantity": inv.quantity_inv,
            "quantityMW": round((inv.quantity_mw or 0) * inv_allocation, 2),
            "postingDate": inv.posting_date.strftime("%Y-%m-%d") if inv.posting_date else None,
            "wbsElement": inv.wbs_element,
            "storageLocation": inv.storage_location_mapping,
            "movementType": inv.movement_type_validation,
            "plantCode": inv.plant_code,
            "companyCode": inv.company_code,
        })

    # ── Material Type Breakdown (pro-rata allocated) ──
    material_types = {}
    for po in po_records_all:
        mt = po.material_type or "Unknown"
        if mt not in material_types:
            material_types[mt] = {"type": mt, "totalMW": 0, "count": 0}
        material_types[mt]["totalMW"] += (po.po_quantities_mw or 0) * allocation_ratio
        material_types[mt]["count"] += 1
    material_breakdown = sorted(material_types.values(), key=lambda x: x["totalMW"], reverse=True)

    # ── Compute allocated totals for summary ──
    total_po_mw = round(sum(po.po_quantities_mw or 0 for po in po_records_all) * allocation_ratio, 2)
    total_transit_mw = round(sum((t.quantity_mw or 0) * transit_allocation for t in transit_records), 2)
    total_inv_mw = round(sum((inv.quantity_mw or 0) * inv_allocation for inv in inv_records), 2)
    total_net_value = round(sum(po.net_order_value or 0 for po in po_records_all) * allocation_ratio, 2)

    # ── P6: Full Project Data ──
    p6_full = {
        "projectId": p6_proj.project_id,
        "name": p6_proj.name,
        "status": p6_proj.status,
        "p6ObjectId": p6_proj.p6_object_id,
        # Schedule Dates
        "startDate": p6_proj.start_date.strftime("%Y-%m-%d") if p6_proj.start_date else None,
        "finishDate": p6_proj.finish_date.strftime("%Y-%m-%d") if p6_proj.finish_date else None,
        "plannedStartDate": p6_proj.planned_start_date.strftime("%Y-%m-%d") if p6_proj.planned_start_date else None,
        "scheduledFinishDate": p6_proj.scheduled_finish_date.strftime("%Y-%m-%d") if p6_proj.scheduled_finish_date else None,
        "dataDate": p6_proj.data_date.strftime("%Y-%m-%d") if p6_proj.data_date else None,
        "mustFinishByDate": p6_proj.must_finish_by_date.strftime("%Y-%m-%d") if p6_proj.must_finish_by_date else None,
        # Progress & Duration
        "durationPercentComplete": p6_proj.duration_percent_complete,
        "plannedDuration": p6_proj.planned_duration,
        "actualDuration": p6_proj.actual_duration,
        "remainingDuration": p6_proj.remaining_duration,
        # Activity Counts
        "activityCount": p6_proj.activity_count,
        "completedActivities": p6_proj.completed_activity_count,
        "inProgressActivities": p6_proj.in_progress_activity_count,
        "notStartedActivities": p6_proj.not_started_activity_count,
        # Float & Variance
        "totalFloat": p6_proj.total_float,
        "finishDateVariance": p6_proj.finish_date_variance,
        "startDateVariance": p6_proj.start_date_variance,
        "durationVariance": p6_proj.duration_variance,
        # Cost
        "actualTotalCost": p6_proj.actual_total_cost,
        "plannedCost": p6_proj.planned_cost,
        "cpi": p6_proj.cost_performance_index,
        "spi": p6_proj.schedule_performance_index,
        "currentBudget": p6_proj.current_budget,
        "totalCostVariance": p6_proj.total_cost_variance,
        # Location
        "locationName": p6_proj.location_name,
        "parentEPSName": p6_proj.parent_eps_name,
        # Baseline
        "baselineStartDate": p6_proj.baseline_start_date.strftime("%Y-%m-%d") if p6_proj.baseline_start_date else None,
        "baselineFinishDate": p6_proj.baseline_finish_date.strftime("%Y-%m-%d") if p6_proj.baseline_finish_date else None,
        "baselineDuration": p6_proj.baseline_duration,
        "baselineTotalCost": p6_proj.baseline_total_cost,
        "baselineCompletedActivities": p6_proj.baseline_completed_activity_count,
        "baselineInProgressActivities": p6_proj.baseline_in_progress_activity_count,
        "baselineNotStartedActivities": p6_proj.baseline_not_started_activity_count,
        # Metadata
        "lastSyncedAt": p6_proj.last_synced_at.strftime("%Y-%m-%d %H:%M") if p6_proj.last_synced_at else None,
    }

    # ── Mapping info ──
    mapping_info = {
        "spvPlantCode": mapping.spv_plant_code,
        "agelCode": mapping.agel,
        "moduleWBS": mapping.module_wbs,
        "capacityMW": mapping.capacity_mwac,
        "p6ProjectName": mapping.project_name_from_p6 or mapping.project,
        "tcProjectName": mapping.project_name_from_p6 or mapping.project,
    }

    # ── TC Data ──
    project_entries = db.query(models.TcProjectEntry).filter(models.TcProjectEntry.mapping_id == mapping.id).all()
    phases = set(pe.phase for pe in project_entries if pe.phase)
    
    tc_network_edges = []
    if phases:
        all_edges = db.query(models.TcNetworkEdge).all()
        filtered_edges = []
        for edge in all_edges:
            edge_phases = set()
            if edge.projects:
                try:
                    edge_phases = set(json.loads(edge.projects))
                except:
                    pass
            if phases.intersection(edge_phases):
                filtered_edges.append(edge)
                
        tc_network_edges = filter_tc_edges_by_kps(filtered_edges, project_entries)
        
    # Also include any direct mappings (fallback)
    direct_tc_edges = db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == mapping.id).all()
    tc_network_edges.extend(direct_tc_edges)
    tc_network_edges = list({e.id: e for e in tc_network_edges}.values())

    tc_khavda = []
    tc_rajasthan = []
    
    for edge in tc_network_edges:
        edge_data = {
            "edgeId": edge.edge_id,
            "fromNode": edge.from_node,
            "fromLabel": edge.from_label,
            "toNode": edge.to_node,
            "toLabel": edge.to_label,
            "project": mapping.project or mapping.project_name_from_p6,
            "phase": json.loads(edge.projects)[0] if edge.projects and json.loads(edge.projects) else "Unknown Phase",
            "projects": edge.projects,
            "contractor": edge.contractor,
            "voltage": edge.voltage,
            "length": edge.length,
            "status": edge.status,
            "normalizedStatus": edge.normalized_status,
            "erection": edge.erection,
            "foundation": edge.foundation,
            "stringing": edge.stringing,
            "expectedDate": edge.expected_date,
            "region": edge.region,
        }
        if edge.region == "Khavda":
            tc_khavda.append(edge_data)
        elif edge.region == "Rajasthan":
            tc_rajasthan.append(edge_data)

    return {
        "mapping": mapping_info,
        "p6": p6_full,
        "sap": {
            "purchaseOrders": sap_vendors,
            "vendorBreakdown": vendor_breakdown,
            "inTransit": sap_intransit,
            "inventory": sap_inventory,
            "materialBreakdown": material_breakdown,
            "allocation": {
                "projectCapacityMW": project_capacity,
                "totalPlantCapacityMW": round(total_capacity, 1),
                "allocationRatio": round(allocation_ratio, 4),
                "wbsFilter": mapping.module_wbs,
            },
            "summary": {
                "totalPOs": round(len(po_records_all) * allocation_ratio),
                "totalVendors": round(len(vendor_breakdown) * allocation_ratio),
                "totalPOMW": total_po_mw,
                "totalInTransitMW": total_transit_mw,
                "totalInventoryMW": total_inv_mw,
                "totalNetValue": total_net_value,
            }
        },
        "tc": {
            "khavdaEdges": tc_khavda,
            "rajasthanEdges": tc_rajasthan,
            "summary": {
                "totalKhavdaEdges": len(tc_khavda),
                "totalRajasthanEdges": len(tc_rajasthan),
                "hasData": len(tc_khavda) > 0 or len(tc_rajasthan) > 0,
            }
        }
    }
