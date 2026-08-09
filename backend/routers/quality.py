"""
Quality Router — REST API endpoints for Pulse NC/RFI data.
Serves the Quality Command Center and per-project Quality tabs.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, distinct
from datetime import datetime, timezone
from typing import Optional
import logging

from database import get_db
import models

router = APIRouter(prefix="/api/quality")
logger = logging.getLogger(__name__)


@router.get("/overview")
def get_quality_overview(
    cluster: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Portfolio-wide quality KPIs for the Quality Command Center."""
    q = db.query(models.PulseNC)
    if cluster:
        q = q.filter(models.PulseNC.cluster_name == cluster)

    all_ncs = q.all()
    total = len(all_ncs)

    # ── RFI aggregates ──
    # RFIs outnumber NCs ~76:1 (43k+ rows), so these are grouped in SQL rather
    # than loaded into memory the way the NC breakdowns below are.
    rfi_status_q = db.query(models.PulseRFI.status, func.count(models.PulseRFI.id))
    rfi_handler_q = db.query(models.PulseRFI.current_handler, func.count(models.PulseRFI.id)) \
        .filter(models.PulseRFI.status != "completed")
    if cluster:
        rfi_status_q = rfi_status_q.filter(models.PulseRFI.cluster_name == cluster)
        rfi_handler_q = rfi_handler_q.filter(models.PulseRFI.cluster_name == cluster)

    rfi_by_status = {
        (s or "unknown"): c
        for s, c in rfi_status_q.group_by(models.PulseRFI.status).all()
    }
    rfi_by_handler = {
        (h or "unknown"): c
        for h, c in rfi_handler_q.group_by(models.PulseRFI.current_handler).all()
    }

    total_rfis = sum(rfi_by_status.values())
    rfis_completed = rfi_by_status.get("completed", 0)
    rfis_rejected = rfi_by_status.get("rejected", 0)
    # In-flight: raised/submitted/approved — awaiting someone's sign-off.
    rfis_in_flight = total_rfis - rfis_completed - rfis_rejected

    rfi_stats = {
        "total_rfis": total_rfis,
        "rfis_completed": rfis_completed,
        "rfis_rejected": rfis_rejected,
        "rfis_in_flight": rfis_in_flight,
        "rfi_pass_rate": round((rfis_completed / total_rfis) * 100, 1) if total_rfis else 0,
        "rfi_by_status": rfi_by_status,
        "rfi_by_handler": rfi_by_handler,
    }

    if total == 0:
        return {
            "total_ncs": 0, "open_ncs": 0, "critical_open": 0,
            "closure_rate": 0, "avg_resolution_days": 0,
            "total_debit": 0, "debit_count": 0,
            "by_status": {}, "by_category": {}, "by_cluster": {},
            "by_handler": {}, "by_package": {},
            "aging": {}, "trend": [], "top_defects": [],
            **rfi_stats,
        }

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Status counts
    by_status = {}
    for nc in all_ncs:
        key = nc.status or "unknown"
        by_status[key] = by_status.get(key, 0) + 1

    open_ncs = total - by_status.get("completed", 0)
    completed = by_status.get("completed", 0)
    closure_rate = round((completed / total) * 100, 1) if total > 0 else 0

    # Critical open
    critical_open = sum(
        1 for nc in all_ncs
        if nc.category == "Critical" and nc.status != "completed"
    )

    # Avg resolution time (for completed NCs)
    resolution_times = []
    for nc in all_ncs:
        if nc.status == "completed" and nc.approved_at and nc.created_at:
            delta = (nc.approved_at - nc.created_at).total_seconds() / 86400
            if delta >= 0:
                resolution_times.append(delta)
    avg_resolution = round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else 0

    # Debit
    debit_ncs = [nc for nc in all_ncs if nc.debit is not None and nc.debit > 0]
    total_debit = sum(nc.debit for nc in debit_ncs)

    # Category breakdown
    by_category = {}
    for nc in all_ncs:
        key = nc.category or "Unknown"
        by_category[key] = by_category.get(key, 0) + 1

    # Cluster breakdown
    by_cluster = {}
    for nc in all_ncs:
        key = nc.cluster_name or "Unknown"
        by_cluster[key] = by_cluster.get(key, 0) + 1

    # Handler breakdown
    by_handler = {}
    for nc in all_ncs:
        if nc.status != "completed":
            key = nc.current_handler or "unknown"
            by_handler[key] = by_handler.get(key, 0) + 1

    # Package breakdown
    by_package = {}
    for nc in all_ncs:
        key = nc.package_name or "Unknown"
        by_package[key] = by_package.get(key, 0) + 1

    # Aging buckets (open NCs only)
    aging = {"0-3": 0, "3-7": 0, "7-14": 0, "14-30": 0, "30+": 0}
    for nc in all_ncs:
        if nc.status == "completed":
            continue
        if nc.created_at:
            days = (now - nc.created_at).days
            if days <= 3:
                aging["0-3"] += 1
            elif days <= 7:
                aging["3-7"] += 1
            elif days <= 14:
                aging["7-14"] += 1
            elif days <= 30:
                aging["14-30"] += 1
            else:
                aging["30+"] += 1

    # Monthly trend
    monthly = {}
    for nc in all_ncs:
        if nc.created_at:
            key = nc.created_at.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0) + 1
    trend = [{"month": k, "count": v} for k, v in sorted(monthly.items())]

    # Top defect types
    defect_counts = {}
    for nc in all_ncs:
        if nc.defect_type:
            defect_counts[nc.defect_type] = defect_counts.get(nc.defect_type, 0) + 1
    top_defects = sorted(defect_counts.items(), key=lambda x: -x[1])[:10]
    top_defects = [{"type": d, "count": c} for d, c in top_defects]

    return {
        "total_ncs": total,
        "open_ncs": open_ncs,
        "critical_open": critical_open,
        "closure_rate": closure_rate,
        "avg_resolution_days": avg_resolution,
        "total_debit": total_debit,
        "debit_count": len(debit_ncs),
        "by_status": by_status,
        "by_category": by_category,
        "by_cluster": by_cluster,
        "by_handler": by_handler,
        "by_package": by_package,
        "aging": aging,
        "trend": trend,
        "top_defects": top_defects,
        **rfi_stats,
    }


@router.get("/contractors")
def get_contractor_scorecard(db: Session = Depends(get_db)):
    """Contractor quality scorecard — NCs, critical ratio, debits, avg resolution."""
    all_ncs = db.query(models.PulseNC).all()

    vendors = {}
    for nc in all_ncs:
        vname = nc.vendor_name or "Unknown"
        if vname not in vendors:
            vendors[vname] = {
                "name": vname,
                "code": nc.vendor_code,
                "total": 0, "critical": 0, "open": 0,
                "rejected": 0, "completed": 0,
                "debit_total": 0, "debit_count": 0,
                "resolution_days": [],
            }
        v = vendors[vname]
        v["total"] += 1
        if nc.category == "Critical":
            v["critical"] += 1
        if nc.status != "completed":
            v["open"] += 1
        if nc.status == "rejected":
            v["rejected"] += 1
        if nc.status == "completed":
            v["completed"] += 1
        if nc.debit and nc.debit > 0:
            v["debit_total"] += nc.debit
            v["debit_count"] += 1
        if nc.status == "completed" and nc.approved_at and nc.created_at:
            delta = (nc.approved_at - nc.created_at).total_seconds() / 86400
            if delta >= 0:
                v["resolution_days"].append(delta)

    result = []
    for v in vendors.values():
        if v["total"] == 0:
            continue
        avg_res = round(sum(v["resolution_days"]) / len(v["resolution_days"]), 1) if v["resolution_days"] else None
        closure_rate = round(v["completed"] / v["total"] * 100, 1) if v["total"] > 0 else 0
        critical_ratio = v["critical"] / v["total"] if v["total"] > 0 else 0
        rejection_rate = v["rejected"] / v["total"] if v["total"] > 0 else 0

        # Quality Score (0-100, higher is better)
        score = 100
        score -= critical_ratio * 30        # Penalize critical ratio
        score -= rejection_rate * 20        # Penalize rejection rate
        score -= min((v["open"] / max(v["total"], 1)) * 25, 25)  # Penalize open ratio
        if avg_res and avg_res > 7:
            score -= min((avg_res - 7) * 2, 20)  # Penalize slow resolution
        score = max(0, round(score))

        result.append({
            "name": v["name"],
            "code": v["code"],
            "total_ncs": v["total"],
            "critical": v["critical"],
            "open": v["open"],
            "rejected": v["rejected"],
            "completed": v["completed"],
            "closure_rate": closure_rate,
            "debit_total": v["debit_total"],
            "debit_count": v["debit_count"],
            "avg_resolution_days": avg_res,
            "quality_score": score,
        })

    result.sort(key=lambda x: x["total_ncs"], reverse=True)
    return result


@router.get("/project/{project_name}")
def get_project_quality(project_name: str, db: Session = Depends(get_db)):
    """Per-project quality details for the ProjectWorkspace Quality tab."""
    from sqlalchemy import or_, and_, func
    
    # The frontend passes p.projectId (like FY25-BANDHA_500MW or AGE27CL_PSS12_FINAL) as project_name.
    # We should look up the actual P6 project name (like AGE25BL_BANDHA_FT_500MW_PPA)
    p6_proj = db.query(models.P6Project).filter(models.P6Project.project_id == project_name).first()
    search_name = p6_proj.name if p6_proj and p6_proj.name else project_name
    
    query_filter_nc = models.PulseNC.project_name.ilike(f"%{search_name}%")
    query_filter_rfi = models.PulseRFI.project_name.ilike(f"%{search_name}%")

    # Heuristic 1: SPV prefix pattern on the actual name (e.g. AGE25BL_BANDHA_FT...)
    parts = search_name.split('_')
    if len(parts) > 1:
        spv_part = parts[0]
        proj_part = parts[1]
        
        nc_proj_clean = func.replace(models.PulseNC.project_name, '-', '')
        rfi_proj_clean = func.replace(models.PulseRFI.project_name, '-', '')

        query_filter_nc = or_(
            query_filter_nc,
            and_(
                models.PulseNC.spv_name.ilike(f"%{spv_part}%"),
                nc_proj_clean.ilike(f"%{proj_part}%")
            )
        )
        query_filter_rfi = or_(
            query_filter_rfi,
            and_(
                models.PulseRFI.spv_name.ilike(f"%{spv_part}%"),
                rfi_proj_clean.ilike(f"%{proj_part}%")
            )
        )

    # Heuristic 2: Site name pattern (e.g. FY25-BANDHA_500MW) directly on project_name
    if "-" in project_name and "_" in project_name:
        try:
            site_part = project_name.split('-')[1].split('_')[0]
            if len(site_part) >= 4:
                query_filter_nc = or_(query_filter_nc, models.PulseNC.project_name.ilike(f"%{site_part}%"))
                query_filter_rfi = or_(query_filter_rfi, models.PulseRFI.project_name.ilike(f"%{site_part}%"))
        except:
            pass

    # Heuristic 3: Direct SPV matching if SPV matches exactly and is unique enough
    # If the project name is just the SPV (like "AGE26AL")
    if len(project_name) >= 6 and "_" not in project_name:
        query_filter_nc = or_(query_filter_nc, models.PulseNC.spv_name.ilike(f"%{project_name}%"))
        query_filter_rfi = or_(query_filter_rfi, models.PulseRFI.spv_name.ilike(f"%{project_name}%"))

    ncs = db.query(models.PulseNC).filter(query_filter_nc).all()
    rfis = db.query(models.PulseRFI).filter(query_filter_rfi).all()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    total_ncs = len(ncs)
    total_rfis = len(rfis)
    rfis_completed = sum(1 for r in rfis if r.status == "completed")
    rfis_rejected = sum(1 for r in rfis if r.status == "rejected")
    rfis_in_flight = total_rfis - rfis_completed - rfis_rejected

    # Who is holding the open RFIs on this project
    rfi_by_handler = {}
    for r in rfis:
        if r.status != "completed":
            key = r.current_handler or "unknown"
            rfi_by_handler[key] = rfi_by_handler.get(key, 0) + 1

    # NC status breakdown
    by_status = {}
    for nc in ncs:
        key = nc.status or "unknown"
        by_status[key] = by_status.get(key, 0) + 1

    # Handler breakdown (open NCs only)
    by_handler = {}
    for nc in ncs:
        if nc.status != "completed":
            key = nc.current_handler or "unknown"
            by_handler[key] = by_handler.get(key, 0) + 1

    # Block quality map
    blocks = {}
    for nc in ncs:
        block = nc.workarea_name or "Unknown"
        if block not in blocks:
            blocks[block] = {"name": block, "total": 0, "critical_open": 0, "open": 0}
        blocks[block]["total"] += 1
        if nc.status != "completed":
            blocks[block]["open"] += 1
            if nc.category == "Critical":
                blocks[block]["critical_open"] += 1

    # Quality score
    completed = by_status.get("completed", 0)
    closure_rate = round((completed / total_ncs) * 100, 1) if total_ncs > 0 else 100
    critical_open = sum(1 for nc in ncs if nc.category == "Critical" and nc.status != "completed")
    critical_ratio = critical_open / max(total_ncs, 1)
    rejected = by_status.get("rejected", 0)
    rejection_rate = rejected / max(total_ncs, 1)

    quality_score = 100
    quality_score -= (1 - closure_rate / 100) * 30
    quality_score -= critical_ratio * 25
    quality_score -= rejection_rate * 15
    quality_score = max(0, round(quality_score))

    # NC list (sorted by age, newest first for display)
    nc_list = []
    for nc in sorted(ncs, key=lambda x: x.created_at or now, reverse=True):
        age_days = (now - nc.created_at).days if nc.created_at else 0
        nc_list.append({
            "id": nc.pulse_id,
            "nc_label": nc.nc_label,
            "status": nc.status,
            "status_label": nc.status_label,
            "category": nc.category,
            "defect_type": nc.defect_type,
            "current_handler": nc.current_handler,
            "contractor_name": nc.contractor_name,
            "vendor_name": nc.vendor_name,
            "workarea_name": nc.workarea_name,
            "package_name": nc.package_name,
            "age_days": age_days,
            "debit": nc.debit,
            "created_at": nc.created_at.isoformat() if nc.created_at else None,
        })

    return {
        "project_name": project_name,
        "total_ncs": total_ncs,
        "total_rfis": total_rfis,
        "rfis_completed": rfis_completed,
        "rfis_rejected": rfis_rejected,
        "rfis_in_flight": rfis_in_flight,
        "rfi_by_handler": rfi_by_handler,
        "quality_score": quality_score,
        "closure_rate": closure_rate,
        "by_status": by_status,
        "by_handler": by_handler,
        "blocks": list(blocks.values()),
        "ncs": nc_list,
    }


@router.get("/ncs")
def get_nc_list(
    status: Optional[str] = None,
    category: Optional[str] = None,
    cluster: Optional[str] = None,
    project: Optional[str] = None,
    package: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Paginated NC list with filters."""
    q = db.query(models.PulseNC)
    if status:
        q = q.filter(models.PulseNC.status == status)
    if category:
        q = q.filter(models.PulseNC.category == category)
    if cluster:
        q = q.filter(models.PulseNC.cluster_name == cluster)
    if project:
        q = q.filter(models.PulseNC.project_name.ilike(f"%{project}%"))
    if package:
        q = q.filter(models.PulseNC.package_name == package)

    total = q.count()
    ncs = q.order_by(models.PulseNC.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    items = []
    for nc in ncs:
        age_days = (now - nc.created_at).days if nc.created_at else 0
        items.append({
            "id": nc.pulse_id,
            "nc_label": nc.nc_label,
            "status": nc.status,
            "status_label": nc.status_label,
            "category": nc.category,
            "defect_type": nc.defect_type,
            "description": nc.description,
            "current_handler": nc.current_handler,
            "contractor_name": nc.contractor_name,
            "vendor_name": nc.vendor_name,
            "engineer_name": nc.engineer_name,
            "quality_name": nc.quality_name,
            "project_name": nc.project_name,
            "cluster_name": nc.cluster_name,
            "worklocation_name": nc.worklocation_name,
            "workarea_name": nc.workarea_name,
            "package_name": nc.package_name,
            "subactivity_name": nc.subactivity_name,
            "debit": nc.debit,
            "debit_reason": nc.debit_reason,
            "age_days": age_days,
            "created_at": nc.created_at.isoformat() if nc.created_at else None,
            "approved_at": nc.approved_at.isoformat() if nc.approved_at else None,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/trends")
def get_quality_trends(db: Session = Depends(get_db)):
    """Monthly NC creation and closure trends."""
    all_ncs = db.query(models.PulseNC).all()

    monthly_created = {}
    monthly_closed = {}
    for nc in all_ncs:
        if nc.created_at:
            key = nc.created_at.strftime("%Y-%m")
            monthly_created[key] = monthly_created.get(key, 0) + 1
        if nc.status == "completed" and nc.approved_at:
            key = nc.approved_at.strftime("%Y-%m")
            monthly_closed[key] = monthly_closed.get(key, 0) + 1

    all_months = sorted(set(list(monthly_created.keys()) + list(monthly_closed.keys())))
    trend = []
    for month in all_months:
        trend.append({
            "month": month,
            "created": monthly_created.get(month, 0),
            "closed": monthly_closed.get(month, 0),
        })

    return trend
