"""
/api/v1 — the standardised surface.

Mounted alongside the existing routes, which keep working unchanged. Everything
here follows one contract so a client can predict a URL and a payload without
reading the docs:

  * one canonical identifier          `project_id`, resolved from any alias
  * one filter vocabulary             portfolio / phase / project / page
  * one envelope                      { data, meta }
  * filters are never silently dropped — meta.filters_applied says what the
    server actually scoped by

That last point exists because of a real bug: the UI sends `phase` to six
endpoints and only one of them declares it, so FastAPI discards it and the
dashboard shows Ongoing KPIs beside unfiltered financials.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from services import project_identity

router = APIRouter(prefix="/api/v1", tags=["v1"])

PHASES = ("ongoing", "commissioned", "all")
MAX_PAGE_SIZE = 200


def envelope(
    data: Any,
    *,
    filters: dict | None = None,
    sources: list[str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
) -> dict:
    """The single response shape.

    `filters_applied` is the contract that makes a silently-ignored filter
    impossible: whatever the server scoped by is stated back to the caller.
    """
    meta: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters_applied": filters or {},
        "sources": sources or [],
    }
    if page is not None:
        meta.update({"page": page, "page_size": page_size, "total": total})
    return {"data": data, "meta": meta}


def normalise_phase(phase: Optional[str]) -> str:
    """Default is `all` — a client-facing API must not filter silently.

    The UI treats Ongoing as its default and passes `phase=ongoing` explicitly.
    Defaulting to that here would mean an integrator calling /api/v1/projects
    silently receives 48 of 63 projects with nothing in the response to say so,
    which is the single most common cause of "why is our data missing" reports.
    Whatever is applied is always echoed back in meta.filters_applied.
    """
    # Tolerates being handed an unresolved Query() default, which happens when
    # backend code calls these handlers directly rather than over HTTP.
    if not isinstance(phase, str):
        phase = None
    value = (phase or "all").strip().lower()
    if value not in PHASES:
        raise HTTPException(
            status_code=422,
            detail=f"phase must be one of {', '.join(PHASES)} (got {phase!r})",
        )
    return value


@router.get("/projects")
def list_projects(
    portfolio: Optional[str] = None,
    phase: Optional[str] = Query(None, description="ongoing | commissioned | all (default: all)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """Every project, one canonical id each, with its source-system linkage."""
    normalised = normalise_phase(phase)
    identities = project_identity.resolve_all(db, portfolio=portfolio, phase=normalised)
    identities.sort(key=lambda i: i.name.lower())

    start = (page - 1) * page_size
    window = identities[start : start + page_size]

    return envelope(
        [i.to_dict() for i in window],
        filters={"portfolio": portfolio, "phase": normalised},
        sources=["P6", "SAP", "TC", "Pulse"],
        page=page,
        page_size=page_size,
        total=len(identities),
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    """One project by canonical id.

    `project_id` is tolerant: the canonical ProjectMapping.project_id, the
    numeric mapping id, a P6 object id, or the project name all resolve here.
    The response always answers with the canonical id.
    """
    identity = project_identity.resolve(db, project_id)
    if identity is None:
        raise HTTPException(status_code=404, detail=f"No project matching {project_id!r}")
    return envelope(identity.to_dict(), sources=["P6", "SAP", "TC", "Pulse"])


@router.get("/projects/{project_id}/identity")
def get_project_identity(project_id: str, db: Session = Depends(get_db)):
    """The key map for one project — what to call it in each source system.

    Useful to an integrator building their own joins, and the honest answer to
    "why is quality empty for this project": it will be listed under `unlinked`.
    """
    identity = project_identity.resolve(db, project_id)
    if identity is None:
        raise HTTPException(status_code=404, detail=f"No project matching {project_id!r}")

    data = identity.to_dict()
    data["keys"] = {
        "canonical": identity.project_id,
        "p6": {"project_id": identity.p6_project_id, "object_id": identity.p6_object_id},
        "sap": {"plant_code": identity.sap_plant_code, "wbs_prefixes": identity.sap_wbs_prefixes,
                "agel_wbs": identity.agel_wbs, "age6l_wbs": identity.age6l_wbs,
                "module_wbs": identity.module_wbs},
        "tc": {"mapping_id": identity.tc_mapping_id},
        "pulse": {"project_name": identity.pulse_project_name},
    }
    return envelope(data, sources=["P6", "SAP", "TC", "Pulse"])


@router.get("/coverage")
def get_coverage(
    portfolio: Optional[str] = None,
    phase: Optional[str] = Query(None, description="ongoing | commissioned | all (default: all)"),
    db: Session = Depends(get_db),
):
    """How much of the portfolio actually links to each source system.

    Worth calling before trusting an aggregate. Pulse in particular resolves for
    roughly a third of projects, because it stores a free-text project name
    rather than a key — so an empty quality response usually means "not linked",
    not "no non-conformances".
    """
    normalised = normalise_phase(phase)
    identities = project_identity.resolve_all(db, portfolio=portfolio, phase=normalised)
    total = len(identities)

    breakdown = {}
    for system in project_identity.SOURCE_SYSTEMS:
        linked = sum(1 for i in identities if system in i.linked)
        breakdown[system] = {
            "linked": linked,
            "total": total,
            "pct": round((linked / total) * 100) if total else 0,
            "unlinked_project_ids": [
                i.project_id for i in identities if system not in i.linked
            ][:50],
        }

    return envelope(
        {"total_projects": total, "systems": breakdown},
        filters={"portfolio": portfolio, "phase": normalised},
        sources=["P6", "SAP", "TC", "Pulse"],
    )


@router.get("/dictionary")
def get_dictionary(db: Session = Depends(get_db)):
    """Field meanings, units and allowed values for /api/v1, read live from the
    data where a value list exists. `basis` says how each answer is known:
    "verified" (checked against the data), "observed" (seen in the data, the
    business meaning still to be confirmed) or "source" (the system does not
    provide it)."""
    from sqlalchemy import text

    def values(sql):
        return [{"value": r[0], "label": r[1] if len(r) > 2 else None, "count": r[-1]}
                for r in db.execute(text(sql)).fetchall()]

    return envelope({
        "units": {
            "p6.planned_duration / actual_duration / remaining_duration / baseline_duration / *_variance":
                {"unit": "hours", "basis": "verified",
                 "note": "Activity calendars run 8 h a day (e.g. 96 h = 11.3 calendar days). Divide by 8 for working days."},
            "p6.finish_variance_days_derived / start_variance_days_derived":
                {"unit": "calendar days", "basis": "verified",
                 "note": "Baseline date minus current date; negative = later than baseline. Derived because P6's own variance fields are filled for few projects."},
            "p6.*_activity_count": {"unit": "count of activities", "basis": "verified"},
            "resources (Labor, Nonlabor)": {"unit": "hours", "basis": "verified", "note": "Labor also carries mandays = hours / 8."},
            "resources (Material)": {"unit": "the P6 resource unit of measure (row field `unit`)", "basis": "verified"},
            "activities.planned_duration": {"unit": "hours", "basis": "verified"},
            "sap.net_order_value_inr / still_to_deliver_inr": {"unit": "INR", "basis": "verified"},
            "sap.delivered_value_inr_cr": {"unit": "INR crore", "basis": "verified"},
            "pulse_nc.debit": {"unit": "INR (penalty on the contractor)", "basis": "observed",
                               "note": "Set on few NCs; blank means no debit was raised."},
            "transmission.mw": {"unit": "MW", "basis": "observed", "note": "Same on every row of a pooling substation: the substation capacity."},
            "transmission.breakup": {"unit": "MW", "basis": "observed",
                                     "note": "The project block's capacity connected at that substation. Totals per substation do not reconcile with `mw`; confirm with the TC team."},
            "trial_run.tr_quantity_mw": {"unit": "MW", "basis": "observed", "note": "Capacity put on trial run in that activity."},
        },
        "values": {
            "pulse_nc.status (status_label)": values("select status, status_label, count(*) from pulse_nc group by 1,2 order by 3 desc"),
            "pulse_rfi.status (status_label)": values("select status, status_label, count(*) from pulse_rfi group by 1,2 order by 3 desc"),
            "pulse_nc.category": values("select category, count(*) from pulse_nc group by 1 order by 2 desc"),
            "einvoice.stage (statusDesc)": values('select stage, "statusDesc", count(*) from einvoice_records group by 1,2 order by 1,2'),
            "trial_run.portfolio_type (column unit_of_measure)": values("select unit_of_measure, count(*) from mt_trialrun group by 1 order by 2 desc"),
            "transmission.phase": values("select phase, count(*) from tc_project_entry group by 1 order by 1"),
            "slr.type": values("select type, count(*) from mt_slr_data group by 1 order by 2 desc"),
        },
        "definitions": {
            "pulse status vs status_label": {"basis": "verified",
                "text": "`status` is the workflow key, `status_label` its display name. raised -> submitted (In Review EE) -> approved (In Review QI: engineer approved, quality inspector pending) -> completed (Approved); rejected sends it back to the contractor."},
            "pulse version": {"basis": "observed", "text": "Revision number of the NC (1-7 seen; 295 NCs above 1). Every newly raised NC is version 1, consistent with a new version per resubmission - confirm with the Pulse team."},
            "pulse_project_uuid": {"basis": "verified", "text": "Pulse's own project id. Mapped to the canonical project in project_mapping.pulse_project_uuid; the API joins on it."},
            "rfi_label": {"basis": "observed", "text": "RFI-<site/project>-<capacity or package>-<block or WTG>-<discipline, e.g. CIV>-<running number>. Confirm the convention with the Pulse team."},
            "einvoice stage": {"basis": "observed", "text": "Approval level, as seen against statusDesc: 0 only with Cancelled; 1 with Pending for Approval / Rejected; 2 mostly Completed (202 of 217); 3 seen once, Completed. 96 rows carry neither stage nor statusDesc. Confirm the level names with the e-invoice team."},
            "slr blank type": {"basis": "verified", "text": "2 logistics commitment lines with no reference category; PReq lines have no vendor until a PO is placed."},
            "sap order_quantity vs po_quantities": {"basis": "verified", "text": "Identical by construction (both = commitment + actual quantity); po_quantities is kept for older clients."},
            "inventory quantity_inv vs unrestricted_qty": {"basis": "verified", "text": "Equal on every row: the MB52 unrestricted stock."},
            "activities total_float": {"basis": "verified", "text": "Blank only on completed activities - P6 does not compute float for finished work."},
            "activities is_critical": {"basis": "verified", "text": "P6's own critical flag, populated on all but 66 of 141k activities. Every activity with total float <= 0 is flagged (3,415), and so are 740 with positive float, so P6 is set to a longest-path or float-threshold rule - confirm the setting with the planning team before deriving it from float."},
            "projects linked / unlinked": {"basis": "verified", "text": "The source systems the project could be joined to. An empty result for an unlinked system means 'not connected', not 'no data'."},
            "coverage pct": {"basis": "verified", "text": "Share of projects in scope that link to each system (linked / total)."},
            "projects portfolio": {"basis": "verified", "text": "The project_mapping cluster (Solar Khavda, Solar Rajasthan, Wind, BESS); a Wind project with no cluster takes it from its category."},
        },
    }, sources=["P6", "SAP", "TC", "Pulse"])
