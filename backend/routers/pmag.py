from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import P6Project, P6BaselineProject, ProjectMapping, TcProjectEntry, TcNetworkEdge, MTTrialRun
from datetime import datetime, timedelta

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
def get_pmag_dashboard(db: Session = Depends(get_db)):
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
    mappings = {m.project_id: m for m in db.query(ProjectMapping).all()}

    def is_valid_project(name: str, proj_id: str, eps: str) -> bool:
        name_lower = (name or "").lower()
        id_lower = (proj_id or "").lower()
        if "dummy" in name_lower or " pr " in f" {name_lower} ":
            return False
        if "fy" in id_lower or "fy" in name_lower or eps in ("Other (Outside Khavda)", "Khavda"):
            return True
        return False

    projects = [p for p in raw_projects if is_valid_project(p.name, p.project_id, p.parent_eps_name)]

    now = datetime.utcnow()
    week_start = now - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=7)

    # ─── Portfolio Summary ───
    total_projects = len(projects)
    on_track = 0
    at_risk = 0
    delayed = 0
    total_completion = 0.0
    milestones_due_this_week = 0
    milestones_overdue = 0

    project_rows = []

    for p in projects:
        pct = _safe_float(p.duration_percent_complete, 0)
        total_completion += pct

        sv_days = _safe_float(p.finish_date_variance, None)
        rag = _classify_rag(sv_days)

        if rag == "green":
            on_track += 1
        elif rag == "amber":
            at_risk += 1
        else:
            delayed += 1

        # Determine project type from mapping
        mapping = mappings.get(p.project_id)
        p_type = "Solar"
        if mapping and mapping.category:
            p_type = mapping.category if mapping.category in ["Solar", "Wind"] else "Solar"

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

        project_rows.append({
            "name": p.name or p.project_id or "Unknown",
            "project_id": p.project_id or "-",
            "type": p_type,
            "pct_complete": round(pct, 1),
            "baseline_finish": baseline_finish,
            "actual_finish": actual_finish,
            "sv_days": round(sv_days, 1) if sv_days is not None else None,
            "rag": rag,
            "activity_count": p.activity_count or 0,
            "completed": p.completed_activity_count or 0,
            "in_progress": p.in_progress_activity_count or 0,
            "not_started": p.not_started_activity_count or 0,
            "spi": round(_safe_float(p.schedule_performance_index, 0), 2),
        })

    avg_completion = round(total_completion / total_projects, 1) if total_projects else 0

    # ─── Schedule Variance Chart ───
    sv_chart = []
    for row in project_rows:
        sv_chart.append({
            "name": row["name"][:30],
            "planned": 100,
            "actual": row["pct_complete"],
            "sv_days": row["sv_days"],
            "rag": row["rag"],
        })

    # ─── Critical Path Panel ───
    # Activities with negative total float or high schedule variance
    critical_activities = []
    for p in projects:
        tf = _safe_float(p.total_float, 999)
        sv = _safe_float(p.finish_date_variance, 0)
        if tf <= 0 or sv < -3:
            critical_activities.append({
                "project": p.name or p.project_id,
                "activity": f"Project-level critical path ({p.project_id})",
                "planned_date": p.finish_date.strftime("%Y-%m-%d") if p.finish_date else "-",
                "delay_days": abs(round(sv, 0)) if sv < 0 else 0,
                "total_float": round(tf, 1),
                "impact": "High" if sv < -7 else "Medium" if sv < -3 else "Low",
                "cascades_to_milestone": sv < -5,
            })

    critical_activities.sort(key=lambda x: -x["delay_days"])

    # ─── DPR Submission Tracker (mock with realistic structure) ───
    dpr_sites = []
    for p in projects[:10]:
        days = []
        for d in range(7):
            dt = now - timedelta(days=6 - d)
            # Simulate: most days submitted, some pending/missing
            import random
            random.seed(hash(p.name or "") + d)
            r = random.random()
            status = "submitted" if r > 0.2 else ("pending" if r > 0.1 else "missing")
            days.append({"date": dt.strftime("%Y-%m-%d"), "day": dt.strftime("%a"), "status": status})
        dpr_sites.append({
            "project": (p.name or p.project_id or "Site")[:35],
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
