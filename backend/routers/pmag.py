from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import P6Project, P6BaselineProject, ProjectMapping, TcProjectEntry, TcNetworkEdge, MTTrialRun
from datetime import datetime, timedelta
from services.project_service import calculate_dynamic_evm, build_evm_index

router = APIRouter(prefix="/api/pmag", tags=["PMAG Dashboard"])


def _classify_rag(sv_days: float) -> str:
    """Classify RAG status from schedule variance in days."""
    if sv_days is None:
        return "grey"
    if sv_days >= 0:
        return "green"
    elif sv_days >= -7:
        return "amber"
    else:
        return "red"


def _safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


@router.get("/dashboard")
def get_pmag_dashboard(portfolio: str = None, db: Session = Depends(get_db)):
    """
    Returns the full PMAG dashboard data:
    - Portfolio summary KPIs
    - Project health table
    - Schedule variance chart data
    - Critical path panel
    - DPR submission tracker (mock for now)
    - Connectivity readiness
    - Alerts feed
    """

    raw_projects = db.query(P6Project).all()
    p6_map = {p.project_id: p for p in raw_projects if p.project_id}

    query = db.query(ProjectMapping)
    if portfolio and portfolio != "All Portfolios":
        query = query.filter(
            (ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
            (ProjectMapping.category.ilike(f"%{portfolio}%"))
        )
    mappings_raw = query.all()
    
    dedup = {}
    for m in mappings_raw:
        if m.project_id:
            if m.project_id not in dedup:
                dedup[m.project_id] = m
            else:
                existing = dedup[m.project_id]
                if len(m.spv_plant_code or '') > len(existing.spv_plant_code or ''):
                    dedup[m.project_id] = m
    mappings = list(dedup.values())

    now = datetime.utcnow()
    week_start = now - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=7)

    # ─── Portfolio Summary ───
    total_projects = len(mappings)
    on_track = 0
    at_risk = 0
    delayed = 0
    total_completion = 0.0
    milestones_due_this_week = 0
    milestones_overdue = 0

    project_rows = []

    # Same fix as /api/summary: fold the SAP tables once rather than issuing
    # three table-scanning queries per project inside the loop below.
    evm_index = build_evm_index(db)

    for m in mappings:
        p = p6_map.get(m.project_id)
        if not p:
            continue  # Only include mapped projects that actually exist in P6

        pct = _safe_float(p.duration_percent_complete, 0)
        if pct <= 1.0 and pct > 0:
            pct = pct * 100
        total_completion += pct

        sv_days = _safe_float(p.finish_date_variance, None)
        rag = _classify_rag(sv_days)

        if rag == "green":
            on_track += 1
        elif rag == "amber":
            at_risk += 1
        else:
            delayed += 1

        p_type = "Solar"
        if m.category:
            p_type = m.category if m.category in ["Solar", "Wind"] else "Solar"

        # Check finish dates for milestone tracking
        if p.finish_date:
            if week_start.date() <= p.finish_date.date() <= week_end.date():
                milestones_due_this_week += 1
            if p.finish_date.date() < now.date() and pct < 100:
                milestones_overdue += 1

        baseline_finish = None
        if p.baseline_finish_date:
            baseline_finish = p.baseline_finish_date.strftime("%Y-%m-%d")
        elif p.scheduled_finish_date:
            baseline_finish = p.scheduled_finish_date.strftime("%Y-%m-%d")

        actual_finish = None
        if p.finish_date:
            actual_finish = p.finish_date.strftime("%Y-%m-%d")

        # Use P6 native names as requested by the user
        project_name = p.name or m.project_name_from_p6 or "Unknown"
        display_name = f"{m.project_id} - {project_name}" if m.project_id else project_name
        
        planned_pct = 100
        if p.start_date and p.finish_date:
            try:
                total_days = (p.finish_date.date() - p.start_date.date()).days
                if total_days > 0:
                    elapsed = (now.date() - p.start_date.date()).days
                    planned_pct = max(0, min(100, (elapsed / total_days) * 100))
                else:
                    planned_pct = 100 if now.date() >= p.start_date.date() else 0
            except:
                pass
        elif p.duration_percent_complete is not None:
            # Fallback if no dates, assume planned is at least the actual to avoid 100% giant bars
            p6_pct = p.duration_percent_complete
            if p6_pct <= 1.0 and p6_pct > 0:
                p6_pct *= 100
            planned_pct = min(100, p6_pct + 5)
            
        dynamic_spi, _ = calculate_dynamic_evm(db, p, m, index=evm_index)
            
        project_rows.append({
            "name": display_name,
            "project_id": m.project_id or "-",
            "eps": p.parent_eps_name,
            "type": p_type,
            "pct_complete": round(pct, 1),
            "planned_pct": round(planned_pct, 1),
            "baseline_finish": baseline_finish,
            "actual_finish": actual_finish,
            "sv_days": round(sv_days, 1) if sv_days is not None else None,
            "rag": rag,
            "activity_count": p.activity_count or 0,
            "completed": p.completed_activity_count or 0,
            "in_progress": p.in_progress_activity_count or 0,
            "not_started": p.not_started_activity_count or 0,
            "spi": round(dynamic_spi, 2),
        })

    total_projects = len(project_rows)
    avg_completion = round(total_completion / total_projects, 1) if total_projects else 0

    # ─── Schedule Variance Chart ───
    sv_chart = []
    for row in project_rows:
        sv_chart.append({
            "name": row["name"][:30],
            "planned": row.get("planned_pct", 100),
            "actual": row["pct_complete"],
            "sv_days": row["sv_days"],
            "rag": row["rag"],
        })

    # ─── Critical Path Panel ───
    # Activities with negative total float or high schedule variance
    critical_activities = []
    for m in mappings:
        p = p6_map.get(m.project_id)
        if not p:
            continue
        tf = _safe_float(p.total_float, 999)
        sv = _safe_float(p.finish_date_variance, 0)
        if tf <= 0 or sv < -3:
            critical_activities.append({
                "project": p.name or m.project_id,
                "activity": f"Project-level critical path ({m.project_id})",
                "planned_date": p.finish_date.strftime("%Y-%m-%d") if p.finish_date else "-",
                "delay_days": abs(round(sv, 0)) if sv < 0 else 0,
                "total_float": round(tf, 1),
                "impact": "High" if sv < -7 else "Medium" if sv < -3 else "Low",
                "cascades_to_milestone": sv < -5,
            })

    critical_activities.sort(key=lambda x: -x["delay_days"])

    # ─── DPR Submission Tracker (mock with realistic structure) ───
    dpr_sites = []
    for m in mappings[:10]:
        days = []
        for d in range(7):
            dt = now - timedelta(days=6 - d)
            # Simulate: most days submitted, some pending/missing
            import random
            random.seed(hash(m.project or "") + d)
            r = random.random()
            status = "submitted" if r > 0.2 else ("pending" if r > 0.1 else "missing")
            days.append({"date": dt.strftime("%Y-%m-%d"), "day": dt.strftime("%a"), "status": status})
        dpr_sites.append({
            "project": (p6_map.get(m.project_id).name if p6_map.get(m.project_id) else m.project_name_from_p6 or "Site")[:35],
            "days": days,
        })

    # ─── Connectivity Readiness ───
    connectivity = []
    tc_entries = db.query(TcProjectEntry).limit(20).all()
    edges = db.query(TcNetworkEdge).all()
    edge_map = {}
    for e in edges:
        if e.from_label:
            edge_map[e.from_label] = e

    for entry in tc_entries:
        edge = edge_map.get(entry.pss) or edge_map.get(entry.project)
        conn_status = "Unknown"
        expected = "-"
        delay_risk = False
        if edge:
            conn_status = edge.normalized_status or edge.status or "Unknown"
            expected = edge.expected_date or "-"
            delay_risk = conn_status.lower() not in ["completed", "commissioned", "energized"]

        connectivity.append({
            "project": entry.project or "-",
            "block": entry.block or "-",
            "mw": entry.mw or 0,
            "scd_status": conn_status,
            "ecod_projection": expected,
            "delay_risk": delay_risk,
        })

    # ─── Alerts Feed ───
    alerts = []
    for row in project_rows:
        if row["rag"] == "red":
            alerts.append({
                "project": row["name"],
                "type": "Schedule Delay",
                "severity": "high",
                "message": f"Schedule variance: {row['sv_days']} days behind baseline",
                "timestamp": now.strftime("%Y-%m-%d %H:%M"),
            })
    for ca in critical_activities[:5]:
        if ca["cascades_to_milestone"]:
            alerts.append({
                "project": ca["project"],
                "type": "Critical Path",
                "severity": "high",
                "message": f"{ca['activity']} delayed by {ca['delay_days']} days — cascades to milestone",
                "timestamp": now.strftime("%Y-%m-%d %H:%M"),
            })
    for site in dpr_sites:
        missing = sum(1 for d in site["days"] if d["status"] == "missing")
        if missing >= 2:
            alerts.append({
                "project": site["project"],
                "type": "Missing DPR",
                "severity": "medium",
                "message": f"{missing} DPR submissions missing in last 7 days",
                "timestamp": now.strftime("%Y-%m-%d %H:%M"),
            })
    for c in connectivity:
        if c["delay_risk"]:
            alerts.append({
                "project": c["project"],
                "type": "Connectivity Risk",
                "severity": "medium",
                "message": f"Grid connectivity not yet ready — SCD: {c['scd_status']}",
                "timestamp": now.strftime("%Y-%m-%d %H:%M"),
            })

    alerts = alerts[:20]

    return {
        "summary": {
            "total_projects": total_projects,
            "on_track": on_track,
            "at_risk": at_risk,
            "delayed": delayed,
            "avg_completion": avg_completion,
            "milestones_due_this_week": milestones_due_this_week,
            "milestones_overdue": milestones_overdue,
        },
        "project_health": sorted(project_rows, key=lambda x: x["sv_days"] or 0),
        "sv_chart": sv_chart,
        "critical_path": critical_activities[:15],
        "dpr_tracker": dpr_sites,
        "connectivity": connectivity,
        "alerts": alerts,
    }


@router.get("/reports")
def get_pmag_reports():
    """Mock endpoint for PMAG Tab 3 (Reports & Analytics)"""
    return {
        "kpis": {
            "generated_this_month": 42,
            "scheduled_tasks": 8,
            "storage_used_gb": 1.2
        },
        "reports": [
            {"date": "2023-10-27", "name": "Weekly Governance Review - W43", "category": "Governance", "format": "PDF", "status": "Ready"},
            {"date": "2023-10-25", "name": "Monthly Progress Report - Sep '23", "category": "Progress", "format": "PDF", "status": "Ready"},
            {"date": "2023-10-24", "name": "Q4 Financial Forecasts - Revised", "category": "Financial", "format": "XLSX", "status": "Processing"},
            {"date": "2023-10-20", "name": "Weekly Governance Review - W42", "category": "Governance", "format": "PDF", "status": "Ready"},
            {"date": "2023-10-18", "name": "Grid Stability Analysis - Q3", "category": "Analysis", "format": "PDF", "status": "Ready"},
        ],
        "schedules": [
            {"name": "Weekly Governance", "schedule": "Every Monday, 08:00", "active": True},
            {"name": "Monthly Progress", "schedule": "Last Day of Month, 17:00", "active": True},
        ]
    }


@router.get("/team")
def get_pmag_team():
    """Mock endpoint for PMAG Tab 4 (Team Management)"""
    return {
        "kpis": {
            "total_personnel": 142,
            "active_projects": 18,
            "avg_allocation_pct": 86,
            "dpr_submission_rate_pct": 94
        },
        "members": [
            {"name": "Sarah Jenkins", "email": "s.jenkins@akasha.com", "role": "Project Director", "level": "L4 Management", "assignment": "Alpha Grid Expansion", "allocation": 100, "status": "Active"},
            {"name": "David Chen", "email": "d.chen@akasha.com", "role": "Lead Engineer", "level": "L3 Technical", "assignment": "Beta Substation", "allocation": 60, "status": "Active"},
            {"name": "Maria Rodriguez", "email": "m.rodriguez@akasha.com", "role": "Risk Analyst", "level": "L2 Analyst", "assignment": "Multi-Project", "allocation": 110, "status": "Overallocated"},
            {"name": "James Lin", "email": "j.lin@akasha.com", "role": "Field Inspector", "level": "L1 Operations", "assignment": "Gamma Wind Farm", "allocation": 80, "status": "Leave Pending"}
        ],
        "activity_log": [
            {"user": "System Admin", "action": "updated permissions", "target": "David Chen", "details": "Granted write access to 'Beta Substation' financial modules.", "time": "10 mins ago", "type": "admin"},
            {"user": "Sarah Jenkins", "action": "allocated", "target": "Maria Rodriguez", "details": "Allocation set to 30% for Phase 1 Risk Assessment.", "time": "2 hours ago", "type": "assignment"},
            {"user": "Automated Alert", "action": "detected conflict", "target": "Field Ops", "details": "Field Ops team allocation exceeds 100% capacity for Week 2.", "time": "Yesterday", "type": "alert"}
        ]
    }


@router.get("/site-monitoring")
def get_pmag_site_monitoring():
    """Mock endpoint for PMAG Tab 5 (Site Monitoring)"""
    return {
        "telemetry": {
            "total_output_mw": 428.5,
            "avg_irradiance_wm2": 840,
            "wind_speed_ms": 12.4,
            "grid_sync_pct": 99.8
        },
        "equipment_health": [
            {"id": "SF-A-001", "type": "Solar", "focus": "Inverter Array B", "efficiency": 98.2, "status": "OPERATIONAL"},
            {"id": "WP-B-042", "type": "Wind", "focus": "Turbine T-14 Gearbox", "efficiency": 72.0, "status": "MAINTENANCE REQ"},
            {"id": "HE-C-011", "type": "Hydro", "focus": "Generator Unit 2", "efficiency": 94.5, "status": "DEGRADED"},
            {"id": "SF-A-088", "type": "Solar", "focus": "Tracker Sys Sub-Z", "efficiency": 99.1, "status": "OPERATIONAL"},
            {"id": "WP-B-015", "type": "Wind", "focus": "Turbine T-02 Blades", "efficiency": 0.0, "status": "OFFLINE"}
        ],
        "alerts": [
            {"title": "Turbine Pitch Fault", "time": "10:42 AM", "desc": "WP-B-042: Pitch angle mismatch detected on blade A. Auto-curtailment initiated to prevent stress.", "level": "critical"},
            {"title": "Inverter Temp High", "time": "09:15 AM", "desc": "SF-A-001: Inv-B ambient temp approaching upper threshold (42°C). Cooling sys active.", "level": "warning"},
            {"title": "Scheduled Maintenance", "time": "Yesterday", "desc": "HE-C-011: Generator unit 2 scheduled for routine lubrication check at 14:00 UTC tomorrow.", "level": "info"}
        ]
    }
