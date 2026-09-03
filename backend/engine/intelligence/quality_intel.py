"""
Akasha Intelligence Engine — Quality Intelligence

Analyzes Pulse NC/RFI data to produce:
- Quality-to-schedule impact linking
- Contractor quality scorecard
- Defect pattern detection
- Quality health scoring
- Quality-specific insights and next steps

Read-only: never modifies existing data.
"""

import logging
from datetime import datetime, timezone
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)


def analyze_quality(db: Session, ctx: dict) -> dict:
    """Full quality intelligence analysis."""
    mapping = ctx.get("mapping")
    project_name = ctx["project_name"]

    if not mapping:
        return {
            "has_data": False, "health_score": None,
            "insights": [], "next_steps": [],
        }

    project_id = ctx.get("project_id", "")
    from sqlalchemy import or_, and_, func

    search_name = project_name
    mapping_name = mapping.project if mapping else None
    
    query_filter_nc = models.PulseNC.project_name.ilike(f"%{search_name}%")
    query_filter_rfi = models.PulseRFI.project_name.ilike(f"%{search_name}%")
    
    if mapping_name:
        query_filter_nc = or_(query_filter_nc, models.PulseNC.project_name.ilike(f"%{mapping_name}%"))
        query_filter_rfi = or_(query_filter_rfi, models.PulseRFI.project_name.ilike(f"%{mapping_name}%"))

    parts = search_name.split('_')
    if len(parts) > 1:
        spv_part = parts[0]
        proj_part = parts[1]
        nc_proj_clean = func.replace(models.PulseNC.project_name, '-', '')
        rfi_proj_clean = func.replace(models.PulseRFI.project_name, '-', '')
        query_filter_nc = or_(query_filter_nc, and_(
            models.PulseNC.spv_name.ilike(f"%{spv_part}%"),
            nc_proj_clean.ilike(f"%{proj_part}%")
        ))
        query_filter_rfi = or_(query_filter_rfi, and_(
            models.PulseRFI.spv_name.ilike(f"%{spv_part}%"),
            rfi_proj_clean.ilike(f"%{proj_part}%")
        ))

    if "-" in project_id and "_" in project_id:
        try:
            site_part = project_id.split('-')[1].split('_')[0]
            if len(site_part) >= 4:
                query_filter_nc = or_(query_filter_nc, models.PulseNC.project_name.ilike(f"%{site_part}%"))
                query_filter_rfi = or_(query_filter_rfi, models.PulseRFI.project_name.ilike(f"%{site_part}%"))
        except:
            pass

    if len(project_id) >= 6 and "_" not in project_id:
        query_filter_nc = or_(query_filter_nc, models.PulseNC.spv_name.ilike(f"%{project_id}%"))
        query_filter_rfi = or_(query_filter_rfi, models.PulseRFI.spv_name.ilike(f"%{project_id}%"))

    ncs = db.query(models.PulseNC).filter(query_filter_nc).all()
    rfis = db.query(models.PulseRFI).filter(query_filter_rfi).all()

    if not ncs and not rfis:
        return {
            "has_data": False, "health_score": None,
            "insights": [{
                "severity": "info",
                "domain": "quality",
                "title": f"No quality data (NC/RFI) found for {project_name}",
                "description": "No Pulse NC or RFI records mapped to this project.",
                "impact": "Cannot assess quality health",
            }],
            "next_steps": [],
        }

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # ═══════════════════════════════════════════════════════
    # 1. NC ANALYSIS
    # ═══════════════════════════════════════════════════════
    total_ncs = len(ncs)
    open_ncs = [nc for nc in ncs if nc.status != "completed"]
    critical_open = [nc for nc in open_ncs if nc.category == "Critical"]
    completed_ncs = [nc for nc in ncs if nc.status == "completed"]
    closure_rate = round(len(completed_ncs) / max(total_ncs, 1) * 100, 1)

    # NC by category
    by_category = defaultdict(int)
    for nc in ncs:
        by_category[nc.category or "Unknown"] += 1

    # NC by status
    by_status = defaultdict(int)
    for nc in ncs:
        by_status[nc.status or "unknown"] += 1

    # NC by handler (who needs to act)
    by_handler = defaultdict(int)
    for nc in open_ncs:
        by_handler[nc.current_handler or "unknown"] += 1

    # ═══════════════════════════════════════════════════════
    # 2. CONTRACTOR QUALITY SCORECARD
    # ═══════════════════════════════════════════════════════
    contractor_stats = defaultdict(lambda: {
        "total_ncs": 0, "critical": 0, "open": 0,
        "total_debit": 0, "defect_types": set(), "blocks": set(),
    })

    for nc in ncs:
        contractor = nc.vendor_name or nc.contractor_name or "Unknown"
        cs = contractor_stats[contractor]
        cs["total_ncs"] += 1
        if nc.category == "Critical":
            cs["critical"] += 1
        if nc.status != "completed":
            cs["open"] += 1
        cs["total_debit"] += float(nc.debit or 0)
        if nc.defect_type:
            cs["defect_types"].add(nc.defect_type)
        if nc.workarea_name:
            cs["blocks"].add(nc.workarea_name)

    contractor_scorecards = []
    for contractor, cs in contractor_stats.items():
        critical_rate = round(cs["critical"] / max(cs["total_ncs"], 1) * 100, 1)
        contractor_scorecards.append({
            "contractor": contractor,
            "total_ncs": cs["total_ncs"],
            "critical": cs["critical"],
            "open": cs["open"],
            "critical_rate_pct": critical_rate,
            "total_debit": round(cs["total_debit"], 2),
            "defect_types": len(cs["defect_types"]),
            "blocks_affected": len(cs["blocks"]),
            "quality_rating": "POOR" if critical_rate > 40 or cs["total_ncs"] > 20
                             else "FAIR" if critical_rate > 20
                             else "GOOD",
        })
    contractor_scorecards.sort(key=lambda x: x["total_ncs"], reverse=True)

    # ═══════════════════════════════════════════════════════
    # 3. DEFECT PATTERN DETECTION
    # ═══════════════════════════════════════════════════════
    defect_counts = defaultdict(lambda: {"count": 0, "blocks": set(), "critical": 0})
    for nc in ncs:
        defect = nc.defect_type or "Unknown"
        dc = defect_counts[defect]
        dc["count"] += 1
        if nc.workarea_name:
            dc["blocks"].add(nc.workarea_name)
        if nc.category == "Critical":
            dc["critical"] += 1

    recurring_defects = []
    for defect, dc in defect_counts.items():
        if dc["count"] >= 3:  # Recurring threshold
            recurring_defects.append({
                "defect_type": defect,
                "occurrences": dc["count"],
                "blocks_affected": len(dc["blocks"]),
                "critical_count": dc["critical"],
                "is_systemic": dc["count"] >= 5 and len(dc["blocks"]) >= 2,
            })
    recurring_defects.sort(key=lambda x: x["occurrences"], reverse=True)

    # ═══════════════════════════════════════════════════════
    # 4. RFI ANALYSIS
    # ═══════════════════════════════════════════════════════
    total_rfis = len(rfis)
    rfis_completed = len([r for r in rfis if r.status == "completed"])
    rfis_rejected = len([r for r in rfis if r.status == "rejected"])
    rfis_pending = total_rfis - rfis_completed - rfis_rejected
    rfi_pass_rate = round(rfis_completed / max(total_rfis, 1) * 100, 1)

    # ═══════════════════════════════════════════════════════
    # 5. AGING ANALYSIS (open NCs)
    # ═══════════════════════════════════════════════════════
    aging = {"0-7d": 0, "8-15d": 0, "16-30d": 0, ">30d": 0}
    for nc in open_ncs:
        if nc.created_at:
            age_days = (now - nc.created_at).days
            if age_days <= 7:
                aging["0-7d"] += 1
            elif age_days <= 15:
                aging["8-15d"] += 1
            elif age_days <= 30:
                aging["16-30d"] += 1
            else:
                aging[">30d"] += 1

    # ═══════════════════════════════════════════════════════
    # 6. HEALTH SCORE
    # ═══════════════════════════════════════════════════════
    critical_penalty = min(len(critical_open) * 8, 40)
    closure_score = closure_rate * 0.4  # Max 40 points
    open_penalty = min(len(open_ncs) * 1.5, 20)
    health_score = round(max(0, min(100, closure_score + 60 - critical_penalty - open_penalty)), 1)

    # ═══════════════════════════════════════════════════════
    # 7. INSIGHTS
    # ═══════════════════════════════════════════════════════
    insights = []

    if critical_open:
        insights.append({
            "severity": "critical" if len(critical_open) > 5 else "high",
            "domain": "quality",
            "title": f"{len(critical_open)} Critical NCs are open — may be blocking work",
            "description": f"Critical NCs in blocks: {', '.join(set(nc.workarea_name or 'Unknown' for nc in critical_open[:5]))}. "
                          f"Defect types include: {', '.join(list(set(nc.defect_type for nc in critical_open if nc.defect_type))[:3])}.",
            "impact": "Critical NCs may stop construction activities until resolved",
        })

    if recurring_defects:
        systemic = [d for d in recurring_defects if d["is_systemic"]]
        if systemic:
            worst = systemic[0]
            insights.append({
                "severity": "high",
                "domain": "quality",
                "title": f"Systemic defect detected: '{worst['defect_type']}' ({worst['occurrences']} times across {worst['blocks_affected']} blocks)",
                "description": f"This defect has occurred {worst['occurrences']} times. "
                              f"This suggests a methodological issue, not isolated incidents.",
                "impact": "Recommend changing construction method or equipment for this activity",
            })

    poor_contractors = [c for c in contractor_scorecards if c["quality_rating"] == "POOR"]
    if poor_contractors:
        worst_c = poor_contractors[0]
        insights.append({
            "severity": "high",
            "domain": "quality",
            "title": f"Contractor '{worst_c['contractor']}' has poor quality record",
            "description": f"{worst_c['total_ncs']} NCs ({worst_c['critical']} critical), "
                          f"affecting {worst_c['blocks_affected']} blocks. "
                          f"Total debit: ₹{worst_c['total_debit']:,.0f}",
            "impact": "Consider enhanced inspection or contractor replacement",
        })

    if rfi_pass_rate < 70 and total_rfis > 10:
        insights.append({
            "severity": "medium",
            "domain": "quality",
            "title": f"Low RFI pass rate: {rfi_pass_rate}%",
            "description": f"{rfis_completed} passed, {rfis_rejected} rejected out of {total_rfis} inspections. "
                          f"{rfis_pending} still pending.",
            "impact": "High rejection rate indicates workmanship issues",
        })

    # ═══════════════════════════════════════════════════════
    # 8. NEXT STEPS
    # ═══════════════════════════════════════════════════════
    next_steps = []

    if critical_open:
        next_steps.append({
            "priority": "P1",
            "category": "quality",
            "action": f"Close {len(critical_open)} critical NCs — "
                      f"they may be blocking construction work",
            "reason": f"Critical NCs in: {', '.join(set(nc.workarea_name or '?' for nc in critical_open[:3]))}",
            "assigned_role": "quality_head",
        })

    if poor_contractors:
        next_steps.append({
            "priority": "P2",
            "category": "quality",
            "action": f"Escalate quality issues with contractor '{poor_contractors[0]['contractor']}'",
            "reason": f"{poor_contractors[0]['total_ncs']} NCs, {poor_contractors[0]['critical_rate_pct']}% critical rate",
            "assigned_role": "site_pm",
        })

    return {
        "has_data": True,
        "health_score": health_score,

        "summary": {
            "total_ncs": total_ncs,
            "open_ncs": len(open_ncs),
            "critical_open": len(critical_open),
            "closure_rate": closure_rate,
            "total_rfis": total_rfis,
            "rfi_pass_rate": rfi_pass_rate,
            "rfis_pending": rfis_pending,
        },

        "by_status": dict(by_status),
        "by_category": dict(by_category),
        "by_handler": dict(by_handler),
        "aging": aging,
        "contractor_scorecards": contractor_scorecards[:10],
        "recurring_defects": recurring_defects[:10],

        "insights": insights,
        "next_steps": next_steps,
    }
