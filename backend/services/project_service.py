from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import models
import logging
import json
import re
import ast
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

def calculate_dynamic_evm(db: Session, p6_proj, mapping=None):
    if not p6_proj:
        return 1.0, 1.0
        
    if not mapping:
        mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == p6_proj.project_id).first()
        
    budget_inr = 0.0
    expenditure_inr = 0.0
    
    if mapping and mapping.module_wbs and str(mapping.module_wbs).strip().lower() not in ('nan', 'none', 'null', ''):
        wbs_exact = str(mapping.module_wbs).strip()
        wbs_clean = wbs_exact.replace('-', '')
        pos = db.query(models.MTPOAmount).filter(
            or_(
                models.MTPOAmount.wbs_element.ilike(f"%{wbs_exact}%"),
                models.MTPOAmount.wbs_element.ilike(f"%{wbs_clean}%")
            )
        ).all()
        po_materials = set()
        for po in pos:
            budget_inr += (po.net_order_value_inr or 0.0)
            if po.material_code:
                mat_str = str(po.material_code).strip().lstrip('0')
                if mat_str:
                    po_materials.add(mat_str)
                    
        mb51 = db.query(models.MTMaterialDocument).filter(
            or_(
                models.MTMaterialDocument.wbs_element.ilike(f"%{wbs_exact}%"),
                models.MTMaterialDocument.wbs_element.ilike(f"%{wbs_clean}%")
            )
        ).all()
        for rec in mb51:
            mat_str = str(rec.material_code).strip().lstrip('0') if rec.material_code else ''
            if not mapping.module_wbs and mat_str not in po_materials:
                continue
            expenditure_inr -= (rec.amount_in_lc or 0.0)
            
    total_budget_evm = budget_inr if budget_inr > 0 else (getattr(p6_proj, 'planned_cost', 0) or 0)
    actual_cost_evm = expenditure_inr if expenditure_inr > 0 else (getattr(p6_proj, 'actual_total_cost', 0) or 0)
    
    progress_val = getattr(p6_proj, 'duration_percent_complete', 0) or 0
    pct_complete = (progress_val / 100.0) if progress_val > 1.0 else progress_val
    
    planned_pct = pct_complete
    import datetime
    today = datetime.datetime.now().date()
    start_dt = p6_proj.baseline_start_date or p6_proj.start_date
    finish_dt = p6_proj.baseline_finish_date or p6_proj.scheduled_finish_date or p6_proj.finish_date
    
    if start_dt and finish_dt:
        start_d = start_dt.date() if isinstance(start_dt, datetime.datetime) else start_dt
        finish_d = finish_dt.date() if isinstance(finish_dt, datetime.datetime) else finish_dt
        if finish_d > start_d:
            total_days = (finish_d - start_d).days
            elapsed_days = (today - start_d).days
            planned_pct = min(1.0, max(0.0, elapsed_days / total_days))
            
    ev = pct_complete * total_budget_evm
    pv = planned_pct * total_budget_evm
    ac = actual_cost_evm
    
    dynamic_spi = (ev / pv) if pv > 0 else ((pct_complete / planned_pct) if planned_pct > 0 else 1.0)
    dynamic_cpi = (ev / ac) if ac > 0 else 1.0
    
    return dynamic_spi, dynamic_cpi

def calculate_project_360_metrics(db: Session, portfolio_type: str = None):
    query = db.query(models.ProjectMapping)
    if portfolio_type and portfolio_type.lower() != "all portfolios":
        portfolio_type = re.sub(r'[\+]+', ' ', portfolio_type).strip()
        portfolio_type = re.sub(r'\s+', ' ', portfolio_type)
        query = query.filter(
            (models.ProjectMapping.cluster.ilike(f"%{portfolio_type}%")) |
            (models.ProjectMapping.category.ilike(f"%{portfolio_type}%"))
        )
    mappings = query.all()
    all_tc_edges = db.query(models.TcNetworkEdge).all()
    
    # Pre-calculate activity stats for exact progress
    from sqlalchemy import func
    activity_stats_raw = db.query(
        models.P6Activity.project_object_id,
        models.P6Activity.status,
        models.P6Activity.is_critical,
        func.count(models.P6Activity.id),
        func.sum(models.P6Activity.percent_complete)
    ).group_by(models.P6Activity.project_object_id, models.P6Activity.status, models.P6Activity.is_critical).all()
    
    act_stats = {}
    for pid, status, is_critical, count, sum_pct in activity_stats_raw:
        if pid not in act_stats:
            act_stats[pid] = {'Completed': 0, 'CompletedCritical': 0, 'In Progress': 0, 'Not Started': 0, 'Total': 0, 'SumPct': 0.0}
        act_stats[pid][status] += count
        if status == 'Completed' and is_critical is True:
            act_stats[pid]['CompletedCritical'] += count
        act_stats[pid]['Total'] += count
        if sum_pct:
            act_stats[pid]['SumPct'] += sum_pct
    # Bulk calculate activity completion timeline and delayed activities
    timeline_stats = {}
    import calendar
    from datetime import date, datetime
    from sqlalchemy import case
    
    now = datetime.utcnow()
    this_month = now.month
    this_year = now.year
    start_this = date(this_year, this_month, 1)
    end_this = date(this_year, this_month, calendar.monthrange(this_year, this_month)[1])
    
    next_month = this_month + 1 if this_month < 12 else 1
    next_year = this_year if this_month < 12 else this_year + 1
    start_next = date(next_year, next_month, 1)
    end_next = date(next_year, next_month, calendar.monthrange(next_year, next_month)[1])
    
    activity_timeline_query = db.query(
        models.P6Activity.project_object_id,
        func.sum(case(((models.P6Activity.status != 'Completed') & (models.P6Activity.is_critical == True) & (models.P6Activity.planned_finish_date >= start_this) & (models.P6Activity.planned_finish_date <= end_this), 1), else_=0)).label('this_month'),
        func.sum(case(((models.P6Activity.status != 'Completed') & (models.P6Activity.is_critical == True) & (models.P6Activity.planned_finish_date >= start_next) & (models.P6Activity.planned_finish_date <= end_next), 1), else_=0)).label('next_month'),
        func.sum(case(((models.P6Activity.status != 'Completed') & (models.P6Activity.is_critical == True) & (models.P6Activity.planned_finish_date > end_next), 1), else_=0)).label('later'),
        func.sum(case(((models.P6Activity.status != 'Completed') & (models.P6Activity.is_critical == True) & (models.P6Activity.total_float < 0), 1), else_=0)).label('delayed')
    ).group_by(models.P6Activity.project_object_id).all()
    
    for row in activity_timeline_query:
        timeline_stats[row.project_object_id] = {
            'this_month': row.this_month or 0,
            'next_month': row.next_month or 0,
            'later': row.later or 0,
            'delayed': row.delayed or 0
        }
    
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

    # Preload P6 projects and SAP tables ONCE instead of per-project queries.
    p6_projects = db.query(models.P6Project).all()
    p6_by_pid = {p.project_id: p for p in p6_projects if p.project_id}

    # WBS matching below is always startswith() on a fixed 6-char prefix, which
    # is equivalent to grouping every row by its own wbs_element[:6] - so this
    # index gives identical results to the old per-project OR/startswith query
    # without the ~190 extra DB round-trips that made this endpoint take 4-10s.
    mtpo_aggs = db.query(
        func.substr(models.MTPOAmount.wbs_element, 1, 6).label('prefix'),
        func.sum(models.MTPOAmount.order_quantity).label('ordered_qty'),
        func.sum(models.MTPOAmount.net_order_value_inr).label('budget_inr'),
        func.sum(models.MTPOAmount.still_to_deliver_qty).label('in_transit_qty')
    ).group_by(func.substr(models.MTPOAmount.wbs_element, 1, 6)).all()

    mtpo_by_prefix = {row.prefix: row for row in mtpo_aggs if row.prefix}

    mb51_aggs = db.query(
        func.substr(models.MTMaterialDocument.wbs_element, 1, 6).label('prefix'),
        func.sum(models.MTMaterialDocument.quantity).label('consumed_qty'),
        func.sum(models.MTMaterialDocument.amount_in_lc).label('expenditure_inr')
    ).group_by(func.substr(models.MTMaterialDocument.wbs_element, 1, 6)).all()

    mb51_by_prefix = {row.prefix: row for row in mb51_aggs if row.prefix}

    mb52_aggs = db.query(
        func.substr(models.MTInventory.wbs_element, 1, 6).label('prefix'),
        func.sum(models.MTInventory.quantity_inv).label('inventory_qty'),
        func.sum(models.MTInventory.value_unrestricted).label('inventory_value_inr')
    ).filter(models.MTInventory.quantity_inv > 0).group_by(func.substr(models.MTInventory.wbs_element, 1, 6)).all()

    mb52_by_prefix = {row.prefix: row for row in mb52_aggs if row.prefix}

    results = []

    for m in mappings:
        # 1. P6 Data
        p6_proj = p6_by_pid.get(m.project_id)
        
        proj_name_check = p6_proj.name if p6_proj else (m.project_name_from_p6 or m.project or "")
        if "demo" in proj_name_check.lower():
            continue
            
        spi = 1.0
        cpi = 1.0
        sched_var = p6_proj.finish_date_variance if p6_proj and p6_proj.finish_date_variance is not None else 0
        cost_var = p6_proj.total_cost_variance if p6_proj and p6_proj.total_cost_variance is not None else 0
        
        # Exact activity tracking
        activity_info = act_stats.get(p6_proj.p6_object_id, {'Completed': 0, 'CompletedCritical': 0, 'In Progress': 0, 'Not Started': 0, 'Total': 0, 'SumPct': 0.0}) if p6_proj else {'Completed': 0, 'CompletedCritical': 0, 'In Progress': 0, 'Not Started': 0, 'Total': 0, 'SumPct': 0.0}

        
        # STRICT user-requested formula:
        # Progress = SummaryActualNonLaborUnits / SummaryAtCompletionNonLaborUnits
        if p6_proj and getattr(p6_proj, 'at_completion_non_labor_units', 0) and p6_proj.at_completion_non_labor_units > 0:
            progress = (getattr(p6_proj, 'actual_non_labor_units', 0) or 0.0) / p6_proj.at_completion_non_labor_units
        elif p6_proj:
            # Fallback for projects that don't have labor units tracked yet
            raw_pct = getattr(p6_proj, 'construction_percent_complete', None)
            if raw_pct is None:
                raw_pct = p6_proj.duration_percent_complete or 0.0
            progress = float(raw_pct) if raw_pct <= 1.0 else float(raw_pct) / 100.0
        else:
            progress = 0.0
            
        # Cap progress between 0 and 1 to prevent exceeding 100% in UI
        progress = max(0.0, min(1.0, float(progress)))

        # 2. SAP Data - WBS Only Mapping
        allocation_ratio = 1.0

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
        
        wbs_prefixes = []
        for val in [m.spv_plant_code, m.agel, m.age6l]:
            if val:
                matches = [c.strip()[:6] for c in re.findall(r'H-\S+', str(val).strip()) if len(c.strip()) >= 6]
                wbs_prefixes.extend(matches)
                wbs_prefixes.extend([m_prefix.replace('-', '') for m_prefix in matches])
        wbs_prefixes = list(set(wbs_prefixes))

        if wbs_prefixes:
            for p in wbs_prefixes:
                # mtpo
                mtpo_row = mtpo_by_prefix.get(p)
                if mtpo_row:
                    ordered_qty += (mtpo_row.ordered_qty or 0.0) * allocation_ratio
                    budget_inr += (mtpo_row.budget_inr or 0.0) * allocation_ratio
                    in_transit_qty += (mtpo_row.in_transit_qty or 0.0) * allocation_ratio
                    
                # mb51
                mb51_row = mb51_by_prefix.get(p)
                if mb51_row:
                    consumed_qty -= (mb51_row.consumed_qty or 0.0) * allocation_ratio
                    expenditure_inr -= (mb51_row.expenditure_inr or 0.0) * allocation_ratio
                    
                # mb52
                mb52_row = mb52_by_prefix.get(p)
                if mb52_row:
                    inventory_qty += (mb52_row.inventory_qty or 0.0) * allocation_ratio
                    inventory_value_inr += (mb52_row.inventory_value_inr or 0.0) * allocation_ratio

        # --- STEP C: ZSPS Purchase Orders ---
        # Already processed above

        # --- STEP D: In-Transit (ZSPS Still to Deliver) ---

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

        # ── True EVM Calculation (SPI / CPI) ──
        total_budget_evm = budget_inr if budget_inr > 0 else (p6_proj.planned_cost if p6_proj and p6_proj.planned_cost else 0)
        actual_cost_evm = expenditure_inr if expenditure_inr > 0 else (p6_proj.actual_total_cost if p6_proj and p6_proj.actual_total_cost else 0)
        pct_complete = (progress / 100.0) if progress > 1.0 else progress
        
        planned_pct = pct_complete
        if p6_proj:
            import datetime
            today = datetime.datetime.now().date()
            start_dt = p6_proj.baseline_start_date or p6_proj.start_date
            finish_dt = p6_proj.baseline_finish_date or p6_proj.scheduled_finish_date or p6_proj.finish_date
            if start_dt and finish_dt:
                start_d = start_dt.date() if isinstance(start_dt, datetime.datetime) else start_dt
                finish_d = finish_dt.date() if isinstance(finish_dt, datetime.datetime) else finish_dt
                if finish_d > start_d:
                    total_days = (finish_d - start_d).days
                    elapsed_days = (today - start_d).days
                    planned_pct = min(1.0, max(0.0, elapsed_days / total_days))
                    
        ev = pct_complete * total_budget_evm
        pv = planned_pct * total_budget_evm
        ac = actual_cost_evm
        
        if pv > 0:
            spi = ev / pv
        elif planned_pct > 0:
            spi = pct_complete / planned_pct
        else:
            spi = 1.0
            
        if ac > 0:
            cpi = ev / ac
        else:
            cpi = 1.0

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


        
        # ── 5-Tier Status Classification ──
        pct_complete = progress * 100 if progress < 1 else progress
        if pct_complete >= 99:
            status_tier = "Completed"
        elif (sched_var < -30 and spi < 0.8) or (mat_avail < 30 and ordered_qty > 0):
            status_tier = "Critical"
        elif sched_var < -20 or (mat_avail < 50 and ordered_qty > 0) or has_vendor_risk:
            status_tier = "High Risk"
        elif sched_var < -10 or (mat_avail < 80 and ordered_qty > 0):
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

        # ── Exact TC Data Summary (Local DB) ──
        tc_edges_count = 0
        tc_progress = m.tc_progress or {}
        lines_charged = tc_progress.get("linesCharged", {})
        
        # Read exact edges from local DB
        tc_edges = db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == m.id).all()
        tc_edges_count = len(tc_edges)
        
        m.tc_data = {
            "progress": tc_progress,
            "lines": [{"id": e.edge_id, "name": f"{e.from_label} \u2192 {e.to_label}", "status": e.status, "is_delayed": e.is_delayed} for e in tc_edges]
        }

        activities_completing_this_month = 0
        activities_completing_next_month = 0
        activities_completing_later = 0
        delayed_activities = 0
        if p6_proj:
            stats = timeline_stats.get(p6_proj.p6_object_id, {})
            activities_completing_this_month = stats.get('this_month', 0)
            activities_completing_next_month = stats.get('next_month', 0)
            activities_completing_later = stats.get('later', 0)
            delayed_activities = stats.get('delayed', 0)

        forecast_finish = p6_proj.scheduled_finish_date.strftime("%Y-%m-%d") if p6_proj and p6_proj.scheduled_finish_date else "N/A"
        forecast_month = p6_proj.scheduled_finish_date.strftime("%b %Y") if p6_proj and p6_proj.scheduled_finish_date else "TBD"
        
        baseline_finish = p6_proj.baseline_finish_date.strftime("%Y-%m-%d") if p6_proj and p6_proj.baseline_finish_date else None
        baseline_month = p6_proj.baseline_finish_date.strftime("%b %Y") if p6_proj and p6_proj.baseline_finish_date else None

        results.append({
            # Identifiers
            "projectId": p6_proj.project_id if p6_proj else (m.project_id or ""),
            "projectName": p6_proj.name if p6_proj else (m.project_name_from_p6 or m.project or "Unmapped Project"),
            "sapPlantCode": m.spv_plant_code,
            "agelCode": m.agel,
            "age6lCode": m.age6l,
            "capacityMW": round(m.capacity_mwac, 2) if m.capacity_mwac is not None else 0.0,
            "isCommissioned": m.is_commissioned,
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
            "tcEdgesCount": tc_edges_count,
            "integrationCount": sum([1 if p6_proj else 0, 1 if ordered_qty > 0 or inventory_qty > 0 or consumed_qty > 0 else 0, 1 if tc_edges_count > 0 else 0]),
            "forecastFinish": forecast_finish,
            "forecastMonth": forecast_month,
            "baselineFinishDate": baseline_finish,
            "baselineMonth": baseline_month,
            "health": status_tier,  # alias for backward compat
            "keyIssue": primary_issue,  # alias for backward compat
            "recommendedAction": ai_recommendation,  # alias for backward compat
            "tcData": getattr(m, "tc_data", None),
            # Date & Duration
            "startDate": p6_proj.start_date.strftime("%Y-%m-%d") if p6_proj and p6_proj.start_date else None,
            "finishDate": p6_proj.finish_date.strftime("%Y-%m-%d") if p6_proj and p6_proj.finish_date else None,
            "baselineFinishDate": p6_proj.baseline_finish_date.strftime("%Y-%m-%d") if p6_proj and p6_proj.baseline_finish_date else None,
            "status": p6_proj.status if p6_proj else "Not Started",
            "durationPercentComplete": round(pct_complete, 1),
            # Activity
            "activityCount": activity_info.get('Total', 0),
            "completedActivities": activity_info.get('Completed', 0),
            "completedCriticalActivities": activity_info.get('CompletedCritical', 0),
            "inProgressActivities": activity_info.get('In Progress', 0),
            "notStartedActivities": activity_info.get('Not Started', 0),
            "activitiesCompletingThisMonth": activities_completing_this_month,
            "activitiesCompletingNextMonth": activities_completing_next_month,
            "activitiesCompletingLater": activities_completing_later,
            "delayedActivities": delayed_activities,
            "plannedDuration": p6_proj.planned_duration if p6_proj else 0,
            "actualDuration": (p6_proj.planned_duration * progress) if p6_proj and p6_proj.actual_duration == 0 and progress > 0 else (p6_proj.actual_duration if p6_proj else 0),
            "remainingDuration": (p6_proj.planned_duration * (1.0 - progress)) if p6_proj and p6_proj.actual_duration == 0 and progress > 0 else (p6_proj.remaining_duration if p6_proj else 0),
            "parentEPS": p6_proj.parent_eps_name if p6_proj else "",
        })
    # Add unmapped P6 projects logic removed

    return sorted(results, key=lambda x: x.get('integrationCount', 0), reverse=True)

def normalize_block(name):
    name = name.replace(" ", "").upper()
    m = re.match(r'(BLOCK-|WTG-?)0+(\d+)', name)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return name

def get_project_einvoices(db, mapping):
    """
    Reads the static E-invoice JSON file, maps work orders to WBS elements,
    and returns invoices that belong to this project mapping.
    """
    import json
    import os
    import re
    from models import MTPOAmount
    
    file_path = r'd:\Akasha_Platform\Data\NEW31\Get All Invoices Production(E-invoice) json response.txt'
    if not os.path.exists(file_path):
        return {"invoices": [], "summary": {}}
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading einvoice JSON: {e}")
        return {"invoices": [], "summary": {}}
        
    all_invoices = data.get('d', {}).get('results', [])
    work_orders = set(inv.get('workOrderNo') for inv in all_invoices if inv.get('workOrderNo'))
    
    if not work_orders:
        return {"invoices": [], "summary": {}}
        
    # Query WBS for these POs
    pos = db.query(MTPOAmount.purchasing_document, MTPOAmount.wbs_element).filter(
        MTPOAmount.purchasing_document.in_(list(work_orders))
    ).all()
    po_wbs_map = {po[0]: po[1] for po in pos if po[1]}
    
    # Get project prefixes
    prefixes = []
    if mapping:
        for val in [mapping.spv_plant_code, mapping.agel, mapping.age6l]:
            if val:
                matches = [c.strip()[:6] for c in re.findall(r'H-\S+', str(val).strip()) if len(c.strip()) >= 6]
                prefixes.extend(matches)
                prefixes.extend([mx.replace('-', '') for mx in matches])
                
    if not prefixes:
        return {"invoices": [], "summary": {}}
        
    project_pos = set()
    for po_num, wbs in po_wbs_map.items():
        if any(wbs.startswith(p) for p in prefixes):
            project_pos.add(po_num)
            
    # Filter invoices
    project_invoices = [inv for inv in all_invoices if inv.get('workOrderNo') in project_pos]
    
    # Calculate summary
    total_amount = sum(float(inv.get('invoiceAmount') or 0) for inv in project_invoices)
    total_so_amount = sum(float(inv.get('SOAmount') or 0) for inv in project_invoices)
    completed_invoices = [inv for inv in project_invoices if str(inv.get('statusDesc')).lower() == 'completed']
    pending_invoices = [inv for inv in project_invoices if str(inv.get('statusDesc')).lower() != 'completed']
    
    summary = {
        "totalInvoices": len(project_invoices),
        "totalInvoiceAmountINR": total_amount,
        "totalSOAmountINR": total_so_amount,
        "completedCount": len(completed_invoices),
        "pendingCount": len(pending_invoices),
        "completedAmountINR": sum(float(inv.get('invoiceAmount') or 0) for inv in completed_invoices),
        "pendingAmountINR": sum(float(inv.get('invoiceAmount') or 0) for inv in pending_invoices)
    }
    
    return {
        "invoices": project_invoices,
        "summary": summary
    }

def get_project_360_detail(db: Session, project_id: str):
    """
    Returns enriched per-project intelligence detail:
    - All P6 fields (dates, floats, costs, baselines)
    - SAP vendor breakdown (from MTPOAmount) — pro-rata allocated to this project
    - SAP pending delivery details (derived from ZSPS still_to_deliver_qty) — WBS-filtered or pro-rata
    - SAP inventory details (from MTInventory) — WBS-filtered or pro-rata
    """
    # 1. Resolve mapping
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()
    
    from sqlalchemy.orm import selectinload
    p6_proj = db.query(models.P6Project).options(
        selectinload(models.P6Project.activities).selectinload(models.P6Activity.resource_assignments)
    ).filter(
        models.P6Project.project_id == project_id
    ).first()

    if not p6_proj:
        return {"error": "Project not found"}
        
    # Block/WTG Logic
    cod_done = 0
    pending_cod = 0
    tr_done_cod_not = 0
    mw_generated = 0.0
    total_blocks_count = 0
    
    all_blocks = set()
    obj_id = p6_proj.p6_object_id
    
    wbs_nodes = db.query(models.P6WBSNode).filter(models.P6WBSNode.project_object_id == obj_id).all()
    for w in wbs_nodes:
        m = re.search(r'(Block-\d+|WTG\s*\d+)', w.wbs_name or "", re.IGNORECASE)
        if m:
            all_blocks.add(normalize_block(m.group(1)))
            
    cod_acts = db.query(models.P6Activity).filter(models.P6Activity.project_object_id == obj_id, models.P6Activity.name.ilike('%COD%')).all()
    tr_acts = db.query(models.P6Activity).filter(models.P6Activity.project_object_id == obj_id, models.P6Activity.name.ilike('%Trial%')).all()
    
    for a in cod_acts + tr_acts:
        m = re.search(r'(Block-\d+|WTG\s*\d+)', a.name or "", re.IGNORECASE)
        if m:
            all_blocks.add(normalize_block(m.group(1)))
            
    blocks_status = {b: {'cod': 'Not Started', 'tr': 'Not Started', 'cod_forecast_date': None, 'cod_actual_date': None, 'tr_actual_date': None} for b in all_blocks}
    
    for a in cod_acts:
        m = re.search(r'(Block-\d+|WTG\s*\d+)', a.name or "", re.IGNORECASE)
        if m:
            b_name = normalize_block(m.group(1))
            forecast = a.planned_finish_date.strftime("%Y-%m-%d") if a.planned_finish_date else None
            actual = a.actual_finish_date.strftime("%Y-%m-%d") if a.actual_finish_date else None
            if not blocks_status[b_name]['cod_forecast_date']:
                blocks_status[b_name]['cod_forecast_date'] = forecast
                
            if a.status == 'Completed':
                blocks_status[b_name]['cod'] = 'Completed'
                blocks_status[b_name]['cod_actual_date'] = actual
    
    for a in tr_acts:
        m = re.search(r'(Block-\d+|WTG\s*\d+)', a.name or "", re.IGNORECASE)
        if m:
            b_name = normalize_block(m.group(1))
            actual = a.actual_finish_date.strftime("%Y-%m-%d") if a.actual_finish_date else None
            if a.status == 'Completed':
                blocks_status[b_name]['tr'] = 'Completed'
                blocks_status[b_name]['tr_actual_date'] = actual
    
    for b, status in blocks_status.items():
        is_cod = (status['cod'] == 'Completed')
        is_tr = (status['tr'] == 'Completed')
        
        if is_cod:
            cod_done += 1
        else:
            pending_cod += 1
            if is_tr:
                tr_done_cod_not += 1
                
    total_blocks_count = len(all_blocks)
    
    all_trs = db.query(models.MTTrialRun).all()
    proj_name = mapping.project_name_from_p6 if mapping and mapping.project_name_from_p6 else p6_proj.name
    
    is_solar = any('BLOCK' in b for b in all_blocks)
    is_wind = any('WTG' in b for b in all_blocks)
    
    if is_solar:
        total_blocks = len(all_blocks)
        cap = mapping.capacity_mwac if mapping and mapping.capacity_mwac else (mapping.capacity_mwdc if mapping and mapping.capacity_mwdc else 0.0)
        mw_per_unit = cap / total_blocks if total_blocks > 0 else 0.0
        mw_generated = mw_per_unit * cod_done
    elif is_wind:
        proj_name_nospace = proj_name.replace(" ", "").lower() if proj_name else ""
        mw_per_wtg = 0.0
        for tr in all_trs:
            tr_proj_name = (tr.project_name_p6 or tr.project_name or "").replace(" ", "").lower()
            if tr_proj_name == proj_name_nospace:
                if tr.tr_quantity_mw:
                    mw_per_wtg = tr.tr_quantity_mw
                    break
        mw_generated = mw_per_wtg * cod_done
    else:
        proj_name_nospace = proj_name.replace(" ", "").lower() if proj_name else ""
        for tr in all_trs:
            tr_proj_name = (tr.project_name_p6 or tr.project_name or "").replace(" ", "").lower()
            if tr_proj_name == proj_name_nospace:
                if tr.activity_name and 'COD' in tr.activity_name.upper():
                    mw_generated += (tr.tr_quantity_mw or 0.0)

    # SAP Data - WBS Only Mapping
    allocation_ratio = 1.0

    # Extract WBS prefixes from SPV, AGEL, AGE6L
    wbs_prefixes = []
    if mapping:
        for val in [mapping.spv_plant_code, mapping.agel, mapping.age6l]:
            if val:
                matches = [c.strip()[:6] for c in re.findall(r'H-\S+', str(val).strip()) if len(c.strip()) >= 6]
                wbs_prefixes.extend(matches)
                wbs_prefixes.extend([m.replace('-', '') for m in matches])
    wbs_prefixes = list(set(wbs_prefixes))

    # ── Purchase Orders (ZSPS) ──
    po_records_all = []
    if wbs_prefixes:
        query_conditions = [models.MTPOAmount.wbs_element.startswith(p) for p in wbs_prefixes]
        from sqlalchemy import or_
        po_records_all = db.query(models.MTPOAmount).filter(or_(*query_conditions)).all()

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
    if wbs_prefixes:
        query_conditions = [models.MTMaterialDocument.wbs_element.startswith(p) for p in wbs_prefixes]
        mb51_records = db.query(models.MTMaterialDocument).filter(or_(*query_conditions)).all()

    for rec in mb51_records:
        mat_str = str(rec.material_code).strip().lstrip('0') if rec.material_code else ''
        if not wbs_prefixes and mat_str not in po_materials:
            continue
            
        qty = rec.quantity or 0.0
        cost = rec.amount_in_lc or 0.0
        m_type = str(rec.movement_type).strip()
        
        mat_code_raw = str(rec.material_code).strip()
        if mat_code_raw.endswith('.0'):
            mat_code_raw = mat_code_raw[:-2]
            
        sap_consumption.append({
            "materialCode": mat_code_raw,
            "materialDescription": rec.material_description,
            "movementType": m_type,
            "quantity": qty * allocation_ratio,
            "amountINR": cost * allocation_ratio,
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
    sap_intransit = []
    total_transit_qty = 0.0

    for po in po_records_all:
        mat_str = str(po.material_code).strip().lstrip('0') if po.material_code else ''
        
        vendor_name = po.vendor_name or "Unknown Vendor"
        vendor_code = po.vendor_code or ""
        
        if not vendor_code and vendor_name != "Unknown Vendor":
            parts = vendor_name.split(" ", 1)
            if len(parts) == 2 and parts[0].isdigit():
                vendor_code = parts[0]
                vendor_name = parts[1]
                
        mat_code_raw = str(po.material_code).strip()
        if mat_code_raw.endswith('.0'):
            mat_code_raw = mat_code_raw[:-2]

        sap_vendors.append({
            "poNumber": po.purchasing_document,
            "vendorCode": vendor_code,
            "vendorName": vendor_name,
            "materialCode": mat_code_raw,
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
            "documentDate": po.document_date.isoformat() if getattr(po, "document_date", None) else None,
            "wbsElement": getattr(po, "wbs_element", None),
        })
        
        transit_qty = getattr(po, "still_to_deliver_qty", 0.0) * allocation_ratio
        if transit_qty > 0:
            sap_intransit.append({
                "poNumber": po.purchasing_document,
                "materialCode": mat_code_raw,
                "materialName": po.material_name,
                "inTransitQty": transit_qty,
                "inTransitINR": getattr(po, "still_to_deliver_inr", 0.0) * allocation_ratio,
                "plantCode": po.plant_code,
                "wbsElement": getattr(po, "wbs_element", None),
                "vendorName": vendor_name,
            })
            total_transit_qty += transit_qty
        
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

    # ── In-Transit (Calculated from PO still_to_deliver) ──

    # ── Inventory (MB52) ──
    inv_records = []
    if wbs_prefixes:
        query_conditions = [models.MTInventory.wbs_element.startswith(p) for p in wbs_prefixes]
        inv_records = db.query(models.MTInventory).filter(
            or_(*query_conditions),
            models.MTInventory.quantity_inv > 0
        ).all()

    sap_inventory = []
    total_inv_qty = 0.0
    total_inv_inr = 0.0
    
            
    for inv in inv_records:
        mat_str = str(inv.material_code).strip().lstrip('0') if inv.material_code else ''
        mat_code_raw = str(inv.material_code).strip()
        if mat_code_raw.endswith('.0'):
            mat_code_raw = mat_code_raw[:-2]
            
        sap_inventory.append({
            "materialCode": mat_code_raw,
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

    # ── True EVM Calculation (SPI / CPI) ──
    total_budget_evm = total_budget_inr if total_budget_inr > 0 else (p6_proj.planned_cost if p6_proj and p6_proj.planned_cost else 0)
    actual_cost_evm = expenditure_inr if expenditure_inr > 0 else (p6_proj.actual_total_cost if p6_proj and p6_proj.actual_total_cost else 0)
    progress_val = p6_proj.duration_percent_complete if p6_proj and p6_proj.duration_percent_complete is not None else 0
    pct_complete = (progress_val / 100.0) if progress_val > 1.0 else progress_val
    
    planned_pct = pct_complete
    import datetime
    today = datetime.datetime.now().date()
    start_dt = p6_proj.baseline_start_date or p6_proj.start_date
    finish_dt = p6_proj.baseline_finish_date or p6_proj.scheduled_finish_date or p6_proj.finish_date
    if start_dt and finish_dt:
        start_d = start_dt.date() if isinstance(start_dt, datetime.datetime) else start_dt
        finish_d = finish_dt.date() if isinstance(finish_dt, datetime.datetime) else finish_dt
        if finish_d > start_d:
            total_days = (finish_d - start_d).days
            elapsed_days = (today - start_d).days
            planned_pct = min(1.0, max(0.0, elapsed_days / total_days))
            
    ev = pct_complete * total_budget_evm
    pv = planned_pct * total_budget_evm
    ac = actual_cost_evm
    
    dynamic_spi = (ev / pv) if pv > 0 else ((pct_complete / planned_pct) if planned_pct > 0 else 1.0)
    dynamic_cpi = (ev / ac) if ac > 0 else 1.0

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
        "activityCount": len(p6_proj.activities) if p6_proj.activities else p6_proj.activity_count,
        "completedActivities": sum(1 for a in p6_proj.activities if a.status == 'Completed') if p6_proj.activities else 0,
        "inProgressActivities": sum(1 for a in p6_proj.activities if a.status == 'In Progress') if p6_proj.activities else 0,
        "notStartedActivities": sum(1 for a in p6_proj.activities if a.status == 'Not Started') if p6_proj.activities else 0,
        # Float & Variance
        "totalFloat": p6_proj.total_float,
        "finishDateVariance": p6_proj.finish_date_variance,
        "startDateVariance": p6_proj.start_date_variance,
        "durationVariance": p6_proj.duration_variance,
        # Cost
        "actualTotalCost": p6_proj.actual_total_cost,
        "plannedCost": p6_proj.planned_cost,
        "cpi": round(dynamic_cpi, 2),
        "spi": round(dynamic_spi, 2),
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
                "wbsName": act.wbs_name,
                "wbsObjectId": act.wbs_object_id,
                "p6ObjectId": act.p6_object_id,
                "resources": {
                    ass.resource_type: {
                        "p6ObjectId": ass.p6_object_id,
                        "resourceName": ass.resource_name,
                        "plannedUnits": ass.planned_units,
                        "actualUnits": ass.actual_units
                    }
                    for ass in act.resource_assignments
                } if act.resource_assignments else {}
            }
            for act in p6_proj.activities
        ] if p6_proj.activities else [],
        "wbsNodes": sorted(
            [
                {
                    "wbsObjectId": node.p6_object_id,
                    "parentObjectId": node.parent_object_id,
                    "name": node.wbs_name,
                    "code": node.wbs_code
                }
                for node in db.query(models.P6WBSNode).filter(models.P6WBSNode.project_object_id == p6_proj.p6_object_id).all()
            ],
            key=lambda x: int(str(x["name"]).split()[0]) if str(x["name"]).split() and str(x["name"]).split()[0].isdigit() else 999999
        )
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
        "mwGenerated": round(mw_generated, 2),
        "codBlocksDone": cod_done,
        "pendingCodBlocks": pending_cod,
        "trDoneCodPending": tr_done_cod_not,
        "totalBlocksCount": total_blocks_count,
        "unitType": "WTG" if is_wind else "Blocks",
        "cluster": mapping.cluster if mapping else None,
        "blocksStatus": blocks_status,
        "sapPlantCode": mapping.spv_plant_code if mapping else None,
        "agelCode": mapping.agel if mapping else None,
        "moduleWBS": mapping.module_wbs if mapping else None,
    }

    # ── TC Data ──
    tc_network_edges = []
    
    if mapping:
        tc_network_edges = db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == mapping.id).all()

    tc_khavda = []
    tc_rajasthan = []
    
    for edge in tc_network_edges:
        edge_phase = "Unknown Phase"
        edge_project_name = None
        if edge.projects:
            try:
                parsed = json.loads(edge.projects)
                if isinstance(parsed, dict):
                    project_val = parsed.get("project") or parsed.get("projects")
                    if isinstance(project_val, list):
                        edge_project_name = ", ".join(str(p) for p in project_val if p)
                    elif project_val:
                        edge_project_name = str(project_val)
                    phases_list = parsed.get("phases", [])
                    if phases_list:
                        edge_phase = phases_list[0]
                elif isinstance(parsed, list):
                    if parsed:
                        if isinstance(parsed[0], dict):
                            project_val = parsed[0].get("project") or parsed[0].get("projects")
                            if isinstance(project_val, list):
                                edge_project_name = ", ".join(str(p) for p in project_val if p)
                            elif project_val:
                                edge_project_name = str(project_val)
                            phases_list = parsed[0].get("phases", [])
                            if phases_list:
                                edge_phase = phases_list[0]
                        else:
                            edge_phase = str(parsed[0])
            except Exception:
                try:
                    parsed = ast.literal_eval(edge.projects)
                    if isinstance(parsed, dict):
                        project_val = parsed.get("project") or parsed.get("projects")
                        if isinstance(project_val, list):
                            edge_project_name = ", ".join(str(p) for p in project_val if p)
                        elif project_val:
                            edge_project_name = str(project_val)
                        phases_list = parsed.get("phases", [])
                        if phases_list:
                            edge_phase = phases_list[0]
                    elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                        project_val = parsed[0].get("project") or parsed[0].get("projects")
                        if isinstance(project_val, list):
                            edge_project_name = ", ".join(str(p) for p in project_val if p)
                        elif project_val:
                            edge_project_name = str(project_val)
                        phases_list = parsed[0].get("phases", [])
                        if phases_list:
                            edge_phase = phases_list[0]
                except Exception:
                    m = re.search(r'[\'"]phases[\'"]\s*:\s*\[\s*[\'"]([^\'"]+)[\'"]', edge.projects)
                    if m:
                        edge_phase = m.group(1)
                    m2 = re.search(r'[\'"]projects?[\'"]\s*:\s*(?:\[\s*[\'"]([^\'"]+)[\'"]|[\'"]([^\'"]+)[\'"])', edge.projects)
                    if m2:
                        edge_project_name = m2.group(1) or m2.group(2)
            except:
                pass

        edge_data = {
            "edgeId": edge.edge_id,
            "fromNode": edge.from_node,
            "fromLabel": edge.from_label,
            "toNode": edge.to_node,
            "toLabel": edge.to_label,
            "project": edge_project_name or (mapping.project or mapping.project_name_from_p6 if mapping else "Unmapped"),
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
            "scd": getattr(edge, "scd", None),
            "chargedDate": getattr(edge, "charged_date", None),
            "isDelayed": getattr(edge, "is_delayed", False),
            "region": edge.region,
        }
        region_clean = (edge.region or "").strip().lower()
        if region_clean == "rajasthan":
            tc_rajasthan.append(edge_data)
        else:
            tc_khavda.append(edge_data)

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

    total_tc_mw = 0
    if mapping:
        tc_entries = db.query(models.TcProjectEntry).filter(models.TcProjectEntry.mapping_id == mapping.id).all()
        for e in tc_entries:
            try:
                total_tc_mw += float(e.mw)
            except:
                pass

        # Fallback/Additional: If Mapped MW is needed from kV
        # Standard indicative Thermal Capacities for Indian Transmission Lines
        KV_TO_MW = {
            '800': 4000,  # HVDC
            '765': 3000,
            '400': 1000,
            '220': 400,
            '132': 150,
        }
        for edge in tc_network_edges:
            if edge.voltage:
                match = re.search(r'(\d+)', str(edge.voltage))
                if match:
                    kv_str = match.group(1)
                    total_tc_mw += KV_TO_MW.get(kv_str, float(kv_str))

    # Fetch E-invoices for this project
    einvoice_data = get_project_einvoices(db, mapping)

    return {
        "mapping": mapping_info,
        "p6": p6_full,
        "einvoice": einvoice_data,
        "sap": {
            "purchaseOrders": sap_vendors,
            "vendorBreakdown": vendor_breakdown,
            "inTransit": sap_intransit,
            "inventory": sap_inventory,
            "consumption": sap_consumption,
            "materialBreakdown": material_breakdown,
            "summary": {
                "totalPOs": len(set(v.get('poNumber') for v in sap_vendors if v.get('poNumber'))),
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
                "totalMW": total_tc_mw,
                "totalLines": len(tc_khavda) + len(tc_rajasthan),
                "chargedLines": len([e for e in tc_khavda + tc_rajasthan if str(e.get("normalizedStatus", "")).lower() == "charged" or str(e.get("status", "")).lower() == "charged"]),
                "delayedLines": len([e for e in tc_khavda + tc_rajasthan if e.get("isDelayed")]),
                "inProgressLines": len([e for e in tc_khavda + tc_rajasthan if str(e.get("normalizedStatus", "")).lower() in ["in_progress", "in progress"]]),
                "hasData": len(tc_khavda) > 0 or len(tc_rajasthan) > 0 or len(tc_nodes_data) > 0,
            }
        }
    }
