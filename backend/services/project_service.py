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
                parsed = json.loads(edge.projects)
                if isinstance(parsed, dict):
                    parsed_edge_phases[edge.id] = set(str(p).strip().upper() for p in parsed.get("phases", []))
                elif isinstance(parsed, list):
                    parsed_edge_phases[edge.id] = set()
            except:
                pass
                
    # Pre-calculate capacity by plant for pro-rata allocation
    cap_data = db.query(models.ProjectMapping.spv_plant_code, func.sum(models.ProjectMapping.capacity_mwac)).group_by(models.ProjectMapping.spv_plant_code).all()
    capacity_by_plant = {str(row[0]).strip(): (row[1] or 1.0) for row in cap_data if row[0]}

    results = []

    for m in mappings:
        # 1. P6 Data
        p6_proj = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).first()
            
        spi = p6_proj.schedule_performance_index if p6_proj and p6_proj.schedule_performance_index is not None else 1.0
        cpi = p6_proj.cost_performance_index if p6_proj and p6_proj.cost_performance_index is not None else 1.0
        sched_var = p6_proj.finish_date_variance if p6_proj and p6_proj.finish_date_variance is not None else 0
        cost_var = p6_proj.total_cost_variance if p6_proj and p6_proj.total_cost_variance is not None else 0
        progress = p6_proj.duration_percent_complete if p6_proj and p6_proj.duration_percent_complete is not None else 0
        # 2. SAP Data - Direct Material Reverse Engineering
        plant_codes = [c for c in [str(m.spv_plant_code).strip() if m.spv_plant_code else None, str(m.agel).strip() if m.agel else None] if c]
        
        # Calculate Plant Capacity for pro-rata allocation
        total_plant_capacity = sum(capacity_by_plant.get(c, 1.0) for c in plant_codes) if plant_codes else 1.0
        project_capacity = m.capacity_mwac or 0
        allocation_ratio = project_capacity / total_plant_capacity if total_plant_capacity > 0 else 1.0

        budget_inr = 0.0
        expenditure_inr = 0.0
        inventory_value_inr = 0.0
        
        ordered_qty = 0.0
        consumed_qty = 0.0
        inventory_qty = 0.0
        in_transit_qty = 0.0
        
        po_vol = 0.0
        inv_vol = 0.0
        transit_vol = 0.0
        
        po_materials = set()
        me2j_records = []
        if plant_codes:
            if m.module_wbs:
                wbs_prefix = m.module_wbs[:5]
                me2j_records = db.query(models.MTPOAmount).filter(
                    models.MTPOAmount.plant_code.in_(plant_codes),
                    models.MTPOAmount.wbs_element.startswith(wbs_prefix)
                ).all()
            else:
                me2j_records = db.query(models.MTPOAmount).filter(
                    models.MTPOAmount.plant_code.in_(plant_codes)
                ).all()
            
            for rec in me2j_records:
                ordered_qty += (rec.order_quantity or 0.0) * allocation_ratio
                budget_inr += (rec.net_order_value_inr or 0.0) * allocation_ratio
                in_transit_qty += (rec.still_to_deliver_qty or 0.0) * allocation_ratio
                if rec.material_code:
                    mat_str = str(rec.material_code).strip().lstrip('0')
                    if mat_str:
                        po_materials.add(mat_str)
        
        # --- STEP A: MB51 Consumption ---
        mb51_records = []
        if plant_codes:
            if m.module_wbs:
                wbs_prefix = m.module_wbs[:5]
                mb51_records = db.query(models.MTMaterialDocument).filter(
                    models.MTMaterialDocument.plant_code.in_(plant_codes),
                    models.MTMaterialDocument.wbs_element.startswith(wbs_prefix)
                ).all()
            else:
                mb51_records = db.query(models.MTMaterialDocument).filter(
                    models.MTMaterialDocument.plant_code.in_(plant_codes)
                ).all()
        
        mb51_materials = set()
        for rec in mb51_records:
            # If falling back to plant, strictly require material to be in POs
            mat_str = str(rec.material_code).strip().lstrip('0') if rec.material_code else ''
            if not m.module_wbs and mat_str not in po_materials:
                continue
                
            qty = rec.quantity or 0.0
            cost = rec.amount_in_lc or 0.0
            m_type = str(rec.movement_type).strip()
            consumed_qty -= (qty * allocation_ratio)
            expenditure_inr -= (cost * allocation_ratio)
            
            if mat_str:
                mb51_materials.add(mat_str)
        
        # (Moved to before MB51 for material matching)

        mb52_records = []
        if plant_codes:
            if m.module_wbs:
                wbs_prefix = m.module_wbs[:5]
                mb52_records = db.query(models.MTInventory).filter(
                    models.MTInventory.plant_code.in_(plant_codes),
                    models.MTInventory.wbs_element.startswith(wbs_prefix),
                    models.MTInventory.quantity_inv > 0
                ).all()
            else:
                mb52_records = db.query(models.MTInventory).filter(
                    models.MTInventory.plant_code.in_(plant_codes),
                    models.MTInventory.quantity_inv > 0
                ).all()
            for rec in mb52_records:
                mat_str = str(rec.material_code).strip().lstrip('0') if rec.material_code else ''
                # Only include inventory for materials that exist in the POs
                if mat_str in po_materials:
                    inventory_qty += (rec.quantity_inv or 0.0) * allocation_ratio
                    inventory_value_inr += (rec.value_unrestricted or 0.0) * allocation_ratio

        # --- STEP C: ME2J Purchase Orders ---
        # Already processed above to get po_materials

        # --- STEP D: In-Transit (ME2J Still to Deliver) ---

        # Map legacy variables to actual SAP values to drive multi-dimensional risk flags dynamically
        po_vol = ordered_qty
        inv_vol = inventory_qty
        transit_vol = in_transit_qty

        # Pending Dispatch Formula: Ordered - Consumed - Inventory - InTransit
        pending_dispatch_qty = max(0.0, ordered_qty - consumed_qty - inventory_qty - in_transit_qty)
        cost_remaining_inr = max(0.0, budget_inr - expenditure_inr)

        # Simple material availability calculation
        mat_avail = 0
        if ordered_qty > 0:
            mat_avail = round(((inventory_qty + in_transit_qty) / ordered_qty) * 100)
            mat_avail = min(100, mat_avail)
        elif inventory_qty > 0:
            mat_avail = 100
            
        # 3. Business Logic — Intelligence-Grade Enrichment
        # ─────────────────────────────────────────────────

        # Fallback for sched_var if None
        if p6_proj and sched_var == 0 and p6_proj.baseline_finish_date:
            compare_date = p6_proj.scheduled_finish_date or p6_proj.finish_date
            if compare_date:
                sched_var = (p6_proj.baseline_finish_date - compare_date).days

        # Fallback for SPI if None
        if p6_proj and spi == 1.0 and p6_proj.schedule_performance_index is None:
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
        if mat_avail < 100 and ordered_qty > 0: base_risk += (100 - mat_avail) * 0.5
        if has_vendor_risk: base_risk += 15
        if has_financial_risk: base_risk += 10
        risk_score = min(100, round(base_risk))
        health_score = max(0, 100 - risk_score)
        
        # ── 5-Tier Status Classification ──
        pct_complete = progress * 100 if progress < 1 else progress
        if pct_complete >= 99:
            status_tier = "Completed"
        elif risk_score >= 60 or (sched_var < -30 and spi < 0.8) or (mat_avail < 30 and ordered_qty > 0):
            status_tier = "Critical"
        elif risk_score >= 40 or sched_var < -20 or (mat_avail < 50 and ordered_qty > 0) or has_vendor_risk:
            status_tier = "High Risk"
        elif risk_score >= 20 or sched_var < -10 or (mat_avail < 80 and ordered_qty > 0):
            status_tier = "Watchlist"
        else:
            status_tier = "Healthy"

        # ── Primary Issue (intelligence-first labeling) ──
        primary_issue = "On Track"
        if mat_avail < 50 and ordered_qty > 0:
            primary_issue = "Material Bottleneck"
        elif in_transit_qty == 0 and ordered_qty > 0:
            primary_issue = "Vendor Delay"
        elif sched_var < -30:
            primary_issue = "Schedule Slippage"
        elif cost_var < -1000000:
            primary_issue = "Cost Overrun"
        elif has_procurement_risk:
            primary_issue = "Procurement Gap"
        elif spi < 0.9:
            primary_issue = "Resource Shortage"
        elif sched_var < -10:
            primary_issue = "Schedule Slippage"

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
        if has_material_risk and ordered_qty > 0:
            if pending_dispatch_qty > 0:
                impact_lines.append(f"Supply gap: {pending_dispatch_qty:,.0f} units pending")
        if not impact_lines:
            impact_lines.append("No significant impact detected")

        # ── Confidence Score ──
        # Higher confidence when we have more data points
        confidence = 50 if not p6_proj else 70
        if p6_proj:
            if p6_proj.schedule_performance_index is not None: confidence += 8
            if p6_proj.cost_performance_index is not None: confidence += 5
            if p6_proj.baseline_finish_date is not None: confidence += 5
            if p6_proj.activity_count and p6_proj.activity_count > 0: confidence += 5
        if ordered_qty > 0: confidence += 7
        confidence = min(98, confidence)

        # ── AI Recommendation ──
        if primary_issue == "Material Bottleneck":
            ai_recommendation = f"Expedite vendor dispatch for {pending_dispatch_qty:,.0f} units shortfall. Prioritize critical path materials."
            ai_insight = f"Only {mat_avail}% of ordered materials available. {consumed_qty:,.0f} units consumed against {ordered_qty:,.0f} units ordered — commissioning timeline at risk."
        elif primary_issue == "Vendor Delay":
            ai_recommendation = f"Escalate vendor follow-up for {ordered_qty:,.0f} units on order. Evaluate backup suppliers."
            ai_insight = f"No material dispatched despite {ordered_qty:,.0f} units on order. Zero in-transit volume indicates vendor execution failure."
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
        phases = set(str(pe.phase).strip().upper() for pe in project_entries if pe.phase)
        
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

        forecast_finish = p6_proj.scheduled_finish_date.strftime("%Y-%m-%d") if p6_proj and p6_proj.scheduled_finish_date else "N/A"
        forecast_month = p6_proj.scheduled_finish_date.strftime("%b %Y") if p6_proj and p6_proj.scheduled_finish_date else "TBD"

        results.append({
            # Identifiers
            "projectId": p6_proj.project_id if p6_proj else (m.project_id or ""),
            "projectName": p6_proj.name if p6_proj else (m.project_name_from_p6 or m.project or "Unmapped Project"),
            "sapPlantCode": m.spv_plant_code,
            "agelCode": m.agel,
            "capacityMW": m.capacity_mwac,
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
            "orderedQty": ordered_qty,
            "consumedQty": consumed_qty,
            "inventoryQty": inventory_qty,
            "inTransitQty": in_transit_qty,
            "pendingDispatchQty": pending_dispatch_qty,
            "budgetINR": budget_inr,
            "expenditureINR": expenditure_inr,
            "inventoryValueINR": inventory_value_inr,
            "costRemainingINR": cost_remaining_inr,
            "materialAvailability": mat_avail,
            "riskScore": risk_score,
            "healthScore": health_score,
            "tcEdgesCount": tc_edges_count,
            "integrationCount": sum([1 if p6_proj else 0, 1 if ordered_qty > 0 or inventory_qty > 0 or consumed_qty > 0 else 0, 1 if tc_edges_count > 0 else 0]),
            "forecastFinish": forecast_finish,
            "forecastMonth": forecast_month,
            "health": status_tier,  # alias for backward compat
            "keyIssue": primary_issue,  # alias for backward compat
            "recommendedAction": ai_recommendation,  # alias for backward compat
            # Date & Duration
            "startDate": p6_proj.start_date.strftime("%Y-%m-%d") if p6_proj and p6_proj.start_date else None,
            "finishDate": p6_proj.finish_date.strftime("%Y-%m-%d") if p6_proj and p6_proj.finish_date else None,
            "baselineFinishDate": p6_proj.baseline_finish_date.strftime("%Y-%m-%d") if p6_proj and p6_proj.baseline_finish_date else None,
            "status": p6_proj.status if p6_proj else "Not Started",
            "durationPercentComplete": round(pct_complete, 1),
            # Activity
            "activityCount": p6_proj.activity_count if p6_proj else 0,
            "completedActivities": p6_proj.completed_activity_count if p6_proj else 0,
            "inProgressActivities": p6_proj.in_progress_activity_count if p6_proj else 0,
            "notStartedActivities": p6_proj.not_started_activity_count if p6_proj else 0,
            "plannedDuration": p6_proj.planned_duration if p6_proj else 0,
            "actualDuration": p6_proj.actual_duration if p6_proj else 0,
            "remainingDuration": p6_proj.remaining_duration if p6_proj else 0,
            "parentEPS": p6_proj.parent_eps_name if p6_proj else "",
        })
    # Add unmapped P6 projects logic removed

    return sorted(results, key=lambda x: (x.get('integrationCount', 0), x['riskScore']), reverse=True)


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
    
    p6_proj = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()

    if not p6_proj:
        return {"error": "Project not found"}

    # SAP Data
    codes = [c for c in [mapping.spv_plant_code if mapping else None, mapping.agel if mapping else None] if c]
    
    # Calculate Total Plant Capacity for Pro-Rata Allocation
    total_capacity = db.query(func.sum(models.ProjectMapping.capacity_mwac)).filter(
        or_(
            models.ProjectMapping.spv_plant_code.in_(codes),
            models.ProjectMapping.agel.in_(codes)
        )
    ).scalar() or 1.0

    project_capacity = mapping.capacity_mwac if mapping else 0
    allocation_ratio = project_capacity / total_capacity if total_capacity > 0 else 1.0

    # ── Purchase Orders (ME2J) ──
    po_records_all = []
    if mapping and mapping.module_wbs:
        wbs_prefix = mapping.module_wbs[:5]
        if codes:
            po_records_all = db.query(models.MTPOAmount).filter(
                models.MTPOAmount.plant_code.in_(codes),
                models.MTPOAmount.wbs_element.startswith(wbs_prefix)
            ).all()
    else:
        if codes:
            po_records_all = db.query(models.MTPOAmount).filter(
                models.MTPOAmount.plant_code.in_(codes)
            ).all()
            
    po_materials = set()
    for po in po_records_all:
        if po.material_code:
            mat_str = str(po.material_code).strip().lstrip('0')
            if mat_str:
                po_materials.add(mat_str)
                
    # ── SAP: Reverse Engineering Logic (MB51) ──
    mb51_materials = set()
    consumed_qty = 0.0
    expenditure_inr = 0.0
    sap_consumption = []

    mb51_records = []
    if mapping and mapping.module_wbs:
        wbs_prefix = mapping.module_wbs[:5]
        if codes:
            mb51_records = db.query(models.MTMaterialDocument).filter(
               models.MTMaterialDocument.plant_code.in_(codes),
               models.MTMaterialDocument.wbs_element.startswith(wbs_prefix)
            ).all()
    else:
        if codes:
            mb51_records = db.query(models.MTMaterialDocument).filter(
               models.MTMaterialDocument.plant_code.in_(codes)
            ).all()

    for rec in mb51_records:
        mat_str = str(rec.material_code).strip().lstrip('0') if rec.material_code else ''
        if not (mapping and mapping.module_wbs) and mat_str not in po_materials:
            continue
            
        qty = rec.quantity or 0.0
        cost = rec.amount_in_lc or 0.0
        m_type = str(rec.movement_type).strip()
        
        sap_consumption.append({
            "materialCode": rec.material_code,
            "materialDescription": rec.material_description,
            "movementType": m_type,
            "quantity": qty,
            "amountINR": cost,
            "wbsElement": rec.wbs_element,
            "plantCode": rec.plant_code,
            "postingDate": rec.posting_date.isoformat() if rec.posting_date else None,
            "baseUnit": getattr(rec, "base_unit", None),
        })
        
        consumed_qty -= (qty * allocation_ratio)
        expenditure_inr -= (cost * allocation_ratio)
        
        if mat_str:
            mb51_materials.add(mat_str)
    
    sap_vendors = []
    vendor_summary = {}
    total_po_qty = 0.0
    total_budget_inr = 0.0
    total_delivered_inr = 0.0

    for po in po_records_all:
        mat_str = str(po.material_code).strip().lstrip('0') if po.material_code else ''
        
        vendor_name = po.vendor_name or "Unknown Vendor"
        vendor_code = po.vendor_code or ""
        
        if not vendor_code and vendor_name != "Unknown Vendor":
            parts = vendor_name.split(" ", 1)
            if len(parts) == 2 and parts[0].isdigit():
                vendor_code = parts[0]
                vendor_name = parts[1]
                
        sap_vendors.append({
            "poNumber": po.purchasing_document,
            "vendorCode": vendor_code,
            "vendorName": vendor_name,
            "materialCode": po.material_code,
            "materialName": po.material_name,
            "materialType": po.material_type,
            "orderedQty": (po.order_quantity or 0) * allocation_ratio,
            "budgetINR": (po.net_order_value_inr or 0) * allocation_ratio,
            "companyCode": po.company_code,
            "plantCode": po.plant_code,
            "deliveredQty": getattr(po, "delivered_qty", 0.0) * allocation_ratio,
            "stillToDeliverQty": getattr(po, "still_to_deliver_qty", 0.0) * allocation_ratio,
            "deliveredINR": (getattr(po, "delivered_value_inr_cr", 0.0) * 10000000 if getattr(po, "delivered_value_inr_cr", None) else 0.0) * allocation_ratio,
            "stillToDeliverINR": getattr(po, "still_to_deliver_inr", 0.0) * allocation_ratio,
            "storageLocation": getattr(po, "storage_location", None),
        })
        
        total_po_qty += (po.order_quantity or 0.0) * allocation_ratio
        total_budget_inr += (po.net_order_value_inr or 0.0) * allocation_ratio
        
        del_cr = getattr(po, "delivered_value_inr_cr", 0.0)
        total_delivered_inr += (del_cr * 10000000 if del_cr else 0.0)
        
        if vendor_name not in vendor_summary:
            vendor_summary[vendor_name] = {
                "vendorName": vendor_name,
                "vendorCode": vendor_code,
                "totalOrderedQty": 0,
                "totalBudgetINR": 0,
                "poCount": 0,
                "materials": set(),
            }
        vendor_summary[vendor_name]["totalOrderedQty"] += (po.order_quantity or 0.0)
        vendor_summary[vendor_name]["totalBudgetINR"] += (po.net_order_value_inr or 0.0)
        vendor_summary[vendor_name]["poCount"] += 1
        if po.material_code:
            vendor_summary[vendor_name]["materials"].add(po.material_code)

    vendor_breakdown = []
    for v in vendor_summary.values():
        vendor_breakdown.append({
            "vendorName": v["vendorName"],
            "vendorCode": v["vendorCode"],
            "totalOrderedQty": v["totalOrderedQty"],
            "totalBudgetINR": v["totalBudgetINR"],
            "poCount": v["poCount"],
            "materialCount": len(v["materials"]),
        })
    vendor_breakdown.sort(key=lambda x: x["totalOrderedQty"], reverse=True)

    # ── In-Transit (ZIBDSESREP) ──
    sap_intransit = []
    total_transit_qty = 0.0

    # ── Inventory (MB52) ──
    inv_records = []
    if mapping and mapping.module_wbs:
        wbs_prefix = mapping.module_wbs[:5]
        if codes:
            inv_records = db.query(models.MTInventory).filter(
                models.MTInventory.plant_code.in_(codes),
                models.MTInventory.wbs_element.startswith(wbs_prefix)
            ).all()
    else:
        if codes:
            inv_records = db.query(models.MTInventory).filter(
                models.MTInventory.plant_code.in_(codes),
                models.MTInventory.quantity_inv > 0
            ).all()

    sap_inventory = []
    total_inv_qty = 0.0
    total_inv_inr = 0.0
    
            
    for inv in inv_records:
        mat_str = str(inv.material_code).strip().lstrip('0') if inv.material_code else ''
        # Filter inventory to only materials that are in POs
        if mat_str in po_materials:
            sap_inventory.append({
                "materialCode": inv.material_code,
                "materialName": inv.material_description or inv.material_name,
                "purchaseOrder": inv.purchase_order,
                "inventoryQty": (inv.quantity_inv or 0.0) * allocation_ratio,
                "inventoryValueINR": (inv.value_unrestricted or 0.0) * allocation_ratio,
                "wbsElement": inv.wbs_element,
                "storageLocation": inv.storage_location_mapping,
                "plantCode": inv.plant_code,
                "baseUnit": getattr(inv, "base_unit", None),
            })
            total_inv_qty += (inv.quantity_inv or 0.0) * allocation_ratio
            total_inv_inr += (inv.value_unrestricted or 0.0) * allocation_ratio

    material_breakdown = []

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
        "durationPercentComplete": (p6_proj.duration_percent_complete * 100) if p6_proj.duration_percent_complete is not None and p6_proj.duration_percent_complete <= 1.0 and p6_proj.duration_percent_complete > 0 else p6_proj.duration_percent_complete,
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
        "allActivities": [
            {
                "activityId": act.activity_id,
                "name": act.name,
                "status": act.status,
                "type": act.type,
                "forecastStartDate": act.start_date.strftime("%Y-%m-%d") if act.start_date else None,
                "forecastFinishDate": act.finish_date.strftime("%Y-%m-%d") if act.finish_date else None,
                "plannedStartDate": act.planned_start_date.strftime("%Y-%m-%d") if act.planned_start_date else None,
                "plannedFinishDate": act.planned_finish_date.strftime("%Y-%m-%d") if act.planned_finish_date else None,
                "actualStartDate": act.actual_start_date.strftime("%Y-%m-%d") if act.actual_start_date else None,
                "actualFinishDate": act.actual_finish_date.strftime("%Y-%m-%d") if act.actual_finish_date else None,
                "baselineStartDate": act.baseline_start_date.strftime("%Y-%m-%d") if act.baseline_start_date else None,
                "baselineFinishDate": act.baseline_finish_date.strftime("%Y-%m-%d") if act.baseline_finish_date else None,
                "wbsName": act.wbs_name
            }
            for act in p6_proj.activities
        ] if p6_proj.activities else []
    }

    # ── Delayed Activities & MW Capacity ──
    delayed_activities = []
    
    WIND_MW_PER_WTG = {
        "3074": 5.2, "4707": 5.0, "3075": 5.2, "3076": 5.2,
        "3072": 5.2, "3073": 5.2, "6733": 5.2, "3105": 3.3,
    }
    DEFAULT_WIND_MW = 3.3

    p_type = 'Solar'
    name_check = (p6_proj.name or "").lower() + " " + (mapping.project_name_from_p6 if mapping and mapping.project_name_from_p6 else "").lower()
    if "wind" in name_check:
        p_type = 'Wind'
        
    wtg_mw = WIND_MW_PER_WTG.get(str(p6_proj.p6_object_id), DEFAULT_WIND_MW)

    if p6_proj.data_date:
        for act in p6_proj.activities:
            # Filter for construction activities only
            act_name = (act.name or "").lower()
            wbs_name = (act.wbs_name or "").lower()
            
            # Allow if it's explicitly construction, or if it's a WTG/Block activity (which are construction by nature)
            is_construction = "construction" in act_name or "construction" in wbs_name or "wtg" in act_name or "wtg" in wbs_name or "block" in act_name or "block" in wbs_name
            if not is_construction:
                continue

            is_delayed = False
            delay_days = 0
            
            if act.status == "In Progress" and act.planned_finish_date:
                if p6_proj.data_date > act.planned_finish_date:
                    is_delayed = True
                    delay_days = (p6_proj.data_date - act.planned_finish_date).days
            elif act.status == "Not Started" and act.planned_start_date:
                if p6_proj.data_date > act.planned_start_date:
                    is_delayed = True
                    delay_days = (p6_proj.data_date - act.planned_start_date).days
                    
            if is_delayed:
                mw_capacity = 0
                act_name = (act.name or "").lower()
                wbs_name = (act.wbs_name or "").lower()
                
                if p_type == 'Wind' and ('wtg' in act_name or 'wtg' in wbs_name):
                    mw_capacity = wtg_mw
                elif p_type == 'Solar' and ('block' in act_name or 'block' in wbs_name):
                    mw_capacity = 12.5 # Default block allocation as per capacity_overview
                    
                delayed_activities.append({
                    "activityId": act.activity_id,
                    "name": act.name,
                    "status": act.status,
                    "plannedStartDate": act.planned_start_date.strftime("%Y-%m-%d") if act.planned_start_date else None,
                    "plannedFinishDate": act.planned_finish_date.strftime("%Y-%m-%d") if act.planned_finish_date else None,
                    "dataDate": p6_proj.data_date.strftime("%Y-%m-%d"),
                    "delayDays": delay_days,
                    "mwCapacity": mw_capacity,
                    "wbsName": act.wbs_name
                })
                
    delayed_activities.sort(key=lambda x: x["delayDays"], reverse=True)
    p6_full["delayedActivities"] = delayed_activities

    # ── Milestones Extraction ──
    p6_milestones = []
    if p6_proj.activities:
        for act in p6_proj.activities:
            act_type = (act.type or "").lower()
            act_name = (act.name or "").lower()
            wbs_name = (act.wbs_name or "").lower()
            if "milestone" in act_type or "milestone" in act_name or "milestone" in wbs_name:
                p6_milestones.append({
                    "activityId": act.activity_id,
                    "name": act.name,
                    "status": act.status,
                    "type": act.type,
                    "plannedStartDate": act.planned_start_date.strftime("%Y-%m-%d") if act.planned_start_date else None,
                    "plannedFinishDate": act.planned_finish_date.strftime("%Y-%m-%d") if act.planned_finish_date else None,
                    "actualStartDate": act.actual_start_date.strftime("%Y-%m-%d") if act.actual_start_date else None,
                    "actualFinishDate": act.actual_finish_date.strftime("%Y-%m-%d") if act.actual_finish_date else None,
                    "wbsName": act.wbs_name
                })
    p6_milestones.sort(key=lambda x: x["plannedFinishDate"] or x["plannedStartDate"] or "9999-12-31")
    p6_full["milestones"] = p6_milestones

    # ── Mapping info ──
    mapping_info = {
        "capacityMW": mapping.capacity_mwac if mapping else 0,
        "p6ProjectName": p6_proj.name,
        "tcProjectName": mapping.project_name_from_p6 or mapping.project if mapping else "Unmapped",
    }

    # ── TC Data ──
    tc_network_edges = []
    
    if mapping:
        project_entries = db.query(models.TcProjectEntry).filter(models.TcProjectEntry.mapping_id == mapping.id).all()
        phases = set(pe.phase for pe in project_entries if pe.phase)
        
        if phases:
            all_edges = db.query(models.TcNetworkEdge).all()
            filtered_edges = []
            for edge in all_edges:
                edge_phases = set()
                if edge.projects:
                    try:
                        parsed = json.loads(edge.projects)
                        if isinstance(parsed, dict):
                            edge_phases = set(parsed.get("phases", []))
                        elif isinstance(parsed, list):
                            edge_phases = set()
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
        edge_phase = "Unknown Phase"
        if edge.projects:
            try:
                parsed = json.loads(edge.projects)
                if isinstance(parsed, dict):
                    phases_list = parsed.get("phases", [])
                    if phases_list:
                        edge_phase = phases_list[0]
                elif isinstance(parsed, list):
                    if parsed:
                        edge_phase = parsed[0]
            except:
                pass

        edge_data = {
            "edgeId": edge.edge_id,
            "fromNode": edge.from_node,
            "fromLabel": edge.from_label,
            "toNode": edge.to_node,
            "toLabel": edge.to_label,
            "project": mapping.project or mapping.project_name_from_p6 if mapping else "Unmapped",
            "phase": edge_phase,
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

    # ── Collect Connected Nodes ──
    connected_node_ids = set()
    for e in tc_network_edges:
        if e.from_node: connected_node_ids.add(e.from_node)
        if e.to_node: connected_node_ids.add(e.to_node)
        
    tc_nodes_data = []
    if connected_node_ids:
        nodes = db.query(models.TcNetworkNode).filter(models.TcNetworkNode.node_id.in_(connected_node_ids)).all()
        for n in nodes:
            tc_nodes_data.append({
                "nodeId": n.node_id,
                "label": n.label,
                "type": n.type,
                "status": n.status,
                "region": n.region
            })

    return {
        "mapping": mapping_info,
        "p6": p6_full,
        "sap": {
            "purchaseOrders": sap_vendors,
            "vendorBreakdown": vendor_breakdown,
            "inTransit": sap_intransit,
            "inventory": sap_inventory,
            "consumption": sap_consumption,
            "materialBreakdown": material_breakdown,
            "summary": {
                "totalPOs": len(sap_vendors),
                "totalVendors": len(vendor_breakdown),
                "totalOrderedQty": total_po_qty,
                "totalInTransitQty": total_transit_qty,
                "totalInventoryQty": total_inv_qty,
                "totalConsumedQty": consumed_qty,
                "totalBudgetINR": total_budget_inr,
                "totalDeliveredINR": total_delivered_inr,
                "totalInventoryValueINR": total_inv_inr,
                "totalExpenditureINR": expenditure_inr,
            }
        },
        "tc": {
            "khavdaEdges": tc_khavda,
            "rajasthanEdges": tc_rajasthan,
            "nodes": tc_nodes_data,
            "summary": {
                "totalKhavdaEdges": len(tc_khavda),
                "totalRajasthanEdges": len(tc_rajasthan),
                "totalNodes": len(tc_nodes_data),
                "hasData": len(tc_khavda) > 0 or len(tc_rajasthan) > 0 or len(tc_nodes_data) > 0,
            }
        }
    }
