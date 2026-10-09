"""
/api/v1 — one GET endpoint per data source.

Every source is reached the same way: the same canonical `project_id`, the same
filters, the same envelope. This replaces an arrangement where each source had
several endpoints keyed on different identifiers — `project_name` on financials,
`mapping_id` on transmission, a bare name path segment on quality,
`p6_object_id` on activities.

    GET /api/v1/p6            ?project_id=  schedule
    GET /api/v1/sap           ?project_id=  purchase orders
    GET /api/v1/slr           ?project_id=  SLR ledger
    GET /api/v1/pulse         ?project_id=  quality (kind=nc|rfi)
    GET /api/v1/transmission  ?project_id=  grid entries
    GET /api/v1/resources     ?project_id=  P6 Labor / Nonlabor / Material, with units

Omit `project_id` and the endpoint returns the whole portfolio under the
standard portfolio/phase scoping.
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
from database import get_db
from services import project_identity
from routers.v1 import envelope, normalise_phase, MAX_PAGE_SIZE

router = APIRouter(prefix="/api/v1", tags=["v1-sources"])


class Scope:
    """The set of projects a request applies to, already resolved."""

    def __init__(self, identities, filters):
        self.identities = identities
        self.filters = filters

    def linked(self, system: str):
        return [i for i in self.identities if system in i.linked]

    def attach(self, data: list) -> list:
        """Add the project-master block (`project`) to every row, keyed on the
        row's canonical project_id. Nested so it can never overwrite a source
        column of the same name (Pulse rows carry their own `project_name`)."""
        ctx = {i.project_id: i.context() for i in self.identities}
        for item in data:
            if "project" in item and not isinstance(item["project"], dict):
                # Never overwrite a source column of the same name.
                item["source_project"] = item.pop("project")
            item["project"] = ctx.get(item.get("project_id"))
        return data


def scope(
    project_id: Optional[str] = Query(
        None, description="Canonical project id. Omit for the whole portfolio."
    ),
    portfolio: Optional[str] = None,
    phase: Optional[str] = Query(None, description="ongoing | commissioned | all"),
    db: Session = Depends(get_db),
) -> Scope:
    """Shared filter dependency.

    Every source endpoint takes this, which is what makes it structurally
    impossible for one of them to silently ignore a filter — the bug that had
    five of the six dashboard endpoints discarding `phase`.
    """
    normalised = normalise_phase(phase)
    if project_id:
        identity = project_identity.resolve(db, project_id)
        if identity is None:
            raise HTTPException(status_code=404, detail=f"No project matching {project_id!r}")
        identities = [identity]
    else:
        identities = project_identity.resolve_all(db, portfolio=portfolio, phase=normalised)
    return Scope(
        identities,
        {"project_id": project_id, "portfolio": portfolio, "phase": normalised},
    )


def _day_diff(baseline, current):
    """Calendar days baseline - current (negative = later than baseline)."""
    if not baseline or not current:
        return None
    return (baseline.date() - current.date()).days


def _page(rows: list, page: int, page_size: int):
    start = (page - 1) * page_size
    return rows[start : start + page_size], len(rows)


# Text placeholders some extracts carry instead of a blank ("nan" is what
# pandas writes for an empty Excel cell). The API returns null for all of them,
# so a caller never has to tell "nan" from a real value.
_NULL_TEXT = {"", "nan", "none", "null", "nat"}


def _clean(v):
    if isinstance(v, str) and v.strip().lower() in _NULL_TEXT:
        return None
    return v


def _dict(row) -> dict:
    return {c.name: _clean(getattr(row, c.name)) for c in row.__table__.columns}


def _wbs_owners(sc: Scope) -> dict:
    """WBS prefix → owning project_id.

    A prefix claimed by more than one project is awarded to the most specific
    one. Under the old rule a row matching two prefixes was added to both, which
    is why 9% of purchase-order rows were double-counted and the portfolio PO
    total reads about 6.4% high.
    """
    owners: dict[str, str] = {}
    for identity in sc.linked("sap"):
        for prefix in identity.sap_wbs_prefixes:
            current = owners.get(prefix)
            if current is None or len(prefix) > len(current):
                owners[prefix] = identity.project_id
    return owners


def _by_prefix(db: Session, model, owners: dict, page: int, page_size: int):
    """Fetch rows for each prefix, keeping each row exactly once.

    `LIKE 'H-9712%'` has a trailing wildcard and can use an index. The existing
    endpoints use `ILIKE '%wbs%'`, whose leading wildcard forces a full scan of
    88k rows once per project.
    """
    best: dict[int, tuple] = {}
    for prefix, owner in owners.items():
        for row in db.query(model).filter(model.wbs_element.like(f"{prefix}%")).all():
            current = best.get(row.id)
            if current is None or len(prefix) > len(current[1]):
                best[row.id] = (row, prefix, owner)

    ordered = sorted(best.values(), key=lambda t: t[0].id)
    window, total = _page(ordered, page, page_size)
    data = []
    for row, _prefix, owner in window:
        item = _dict(row)
        item["project_id"] = owner
        data.append(item)
    return data, total


@router.get("/p6")
def get_p6(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """P6 schedule rows, joined on the canonical key directly."""
    wanted = {i.p6_project_id: i.project_id for i in sc.linked("p6") if i.p6_project_id}
    rows = (
        db.query(models.P6Project)
        .filter(models.P6Project.project_id.in_(list(wanted)))
        .all()
        if wanted
        else []
    )
    window, total = _page(sorted(rows, key=lambda r: r.id), page, page_size)
    data = []
    for row in window:
        item = _dict(row)
        item["project_id"] = wanted.get(row.project_id, row.project_id)
        # P6 durations and variances are in working HOURS (8 h a day on the
        # activity calendars). The day-based variances below are derived from
        # the dates themselves - calendar days, negative = later than baseline -
        # because P6's own *_variance fields are filled for few projects.
        item["duration_unit"] = "hours"
        item["hours_per_day"] = 8
        item["finish_variance_days_derived"] = _day_diff(row.baseline_finish_date, row.finish_date)
        item["start_variance_days_derived"] = _day_diff(row.baseline_start_date, row.start_date)
        data.append(item)
    return envelope(
        sc.attach(data), filters=sc.filters, sources=["P6"],
        page=page, page_size=page_size, total=total,
    )


@router.get("/sap")
def get_sap(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """SAP purchase orders. Each row is attributed to exactly one project."""
    data, total = _by_prefix(db, models.MTPOAmount, _wbs_owners(sc), page, page_size)
    return envelope(
        sc.attach(data), filters=sc.filters, sources=["SAP"],
        page=page, page_size=page_size, total=total,
    )


@router.get("/slr")
def get_slr(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """SLR ledger, under the same single-owner WBS rule as /sap."""
    data, total = _by_prefix(db, models.MTSLRData, _wbs_owners(sc), page, page_size)
    return envelope(
        sc.attach(data), filters=sc.filters, sources=["SAP"],
        page=page, page_size=page_size, total=total,
    )


@router.get("/pulse")
def get_pulse(
    sc: Scope = Depends(scope),
    kind: str = Query("nc", description="nc | rfi"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """Quality — non-conformances or RFIs.

    Joined on Pulse's own project UUID, held on the mapping as
    `pulse_project_uuid`. Mappings without that UUID fall back to a project-name
    match, which is why `meta.filters_applied` and the project's `unlinked`
    array matter: an empty list here can mean "not connected to Pulse" rather
    than "no issues".
    """
    if kind not in ("nc", "rfi"):
        raise HTTPException(status_code=422, detail="kind must be 'nc' or 'rfi'")
    model = models.PulseNC if kind == "nc" else models.PulseRFI

    linked = sc.linked("pulse")
    by_uuid = {i.pulse_project_uuid: i.project_id for i in linked if i.pulse_project_uuid}
    by_name = {
        i.pulse_project_name: i.project_id
        for i in linked
        if i.pulse_project_name and not i.pulse_project_uuid
    }

    rows = []
    if by_uuid:
        rows += db.query(model).filter(model.project_id.in_(list(by_uuid))).all()
    if by_name:
        rows += db.query(model).filter(model.project_name.in_(list(by_name))).all()

    seen, unique = set(), []
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        unique.append(row)

    window, total = _page(sorted(unique, key=lambda r: r.id), page, page_size)
    data = []
    for row in window:
        item = _dict(row)
        # Pulse's own id is renamed so `project_id` always means the canonical one.
        item["pulse_project_uuid"] = item.pop("project_id", None)
        item["project_id"] = by_uuid.get(item["pulse_project_uuid"]) or by_name.get(row.project_name)
        data.append(item)

    return envelope(
        sc.attach(data), filters={**sc.filters, "kind": kind}, sources=["Pulse"],
        page=page, page_size=page_size, total=total,
    )


@router.get("/transmission")
def get_transmission(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """Transmission entries for the scoped projects.

    Readiness should be read from `normalized_status` (charged / in_progress /
    under_bidding) on the network edges. The raw `status` column holds unparsed
    values such as '7' and 'Mar-30' and must not be used.
    """
    owners = {i.mapping_id: i.project_id for i in sc.linked("tc")}
    rows = (
        db.query(models.TcProjectEntry)
        .filter(models.TcProjectEntry.mapping_id.in_(list(owners)))
        .all()
        if owners
        else []
    )
    # The tracker load writes some entries twice: rows identical in every
    # column except id (85 groups on 2026-10-09, e.g. 7475/7476). One copy is
    # returned; the ids of its twins are listed so nothing is hidden.
    unique, twins = {}, {}
    for row in sorted(rows, key=lambda r: r.id):
        sig = (row.region, row.project, row.phase, row.kps, row.pss, row.block, row.breakup, row.mw, row.mapping_id)
        if sig in unique:
            twins.setdefault(unique[sig].id, []).append(row.id)
        else:
            unique[sig] = row
    window, total = _page(list(unique.values()), page, page_size)
    data = []
    for row in window:
        item = _dict(row)
        # The tracker's own project name; renamed because `project` on every
        # /api/v1 row is the project-master block (it used to overwrite this).
        item["tc_project_name"] = item.pop("project", None)
        item["project_id"] = owners.get(row.mapping_id)
        item["duplicate_ids"] = twins.get(row.id, [])
        data.append(item)
    return envelope(
        sc.attach(data), filters=sc.filters, sources=["TC"],
        page=page, page_size=page_size, total=total,
    )


# ── Remaining source tables ────────────────────────────────────────────────
# Same contract as above: one endpoint per table, canonical project_id, shared
# filters, shared envelope.


@router.get("/inventory")
def get_inventory(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """SAP inventory / GRN rows, under the single-owner WBS rule."""
    data, total = _by_prefix(db, models.MTInventory, _wbs_owners(sc), page, page_size)
    return envelope(
        sc.attach(data), filters=sc.filters, sources=["SAP"],
        page=page, page_size=page_size, total=total,
    )


@router.get("/material-documents")
def get_material_documents(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """SAP MB51 consumption documents, under the single-owner WBS rule."""
    data, total = _by_prefix(db, models.MTMaterialDocument, _wbs_owners(sc), page, page_size)
    return envelope(
        sc.attach(data), filters=sc.filters, sources=["SAP"],
        page=page, page_size=page_size, total=total,
    )


@router.get("/trial-run")
def get_trial_run(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """Trial-run / COD milestone rows.

    This table carries the P6 project name rather than a code, so it is joined
    on `project_name_p6`, falling back to the SPV plant code.
    """
    by_name, by_plant, plant_of = {}, {}, {}
    for identity in sc.identities:
        if identity.name:
            by_name[identity.name] = identity.project_id
        if identity.sap_plant_code:
            by_plant[identity.sap_plant_code] = identity.project_id
            plant_of[identity.project_id] = identity.sap_plant_code

    rows = []
    if by_name:
        rows += db.query(models.MTTrialRun).filter(
            models.MTTrialRun.project_name_p6.in_(list(by_name))
        ).all()
    if by_plant:
        rows += db.query(models.MTTrialRun).filter(
            models.MTTrialRun.spv_plant_code.in_(list(by_plant))
        ).all()

    seen, unique = set(), []
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        unique.append(row)

    window, total = _page(sorted(unique, key=lambda r: r.id), page, page_size)
    data = []
    for row in window:
        item = _dict(row)
        item["project_id"] = by_name.get(row.project_name_p6) or by_plant.get(row.spv_plant_code)
        # 41% of trial-run rows carry no SPV plant code. Where the row's project
        # is known, the code comes from the project master and is marked so.
        if item.get("spv_plant_code"):
            item["spv_plant_code_source"] = "trial run"
        elif plant_of.get(item["project_id"]):
            item["spv_plant_code"] = plant_of[item["project_id"]]
            item["spv_plant_code_source"] = "project master"
        else:
            item["spv_plant_code_source"] = None
        # The extract's "unit_of_measure" column holds the portfolio (Solar /
        # Wind), not a unit; tr_quantity_mw is the MW put on trial run.
        item["portfolio_type"] = item.get("unit_of_measure")
        data.append(item)
    return envelope(
        sc.attach(data), filters=sc.filters, sources=["SAP"],
        page=page, page_size=page_size, total=total,
    )


@router.get("/einvoice")
def get_einvoice(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """E-invoice records.

    These carry the P6 project name directly, so no WBS resolution is needed.
    """
    by_name = {i.name: i.project_id for i in sc.identities if i.name}
    rows = (
        db.query(models.EInvoiceRecord)
        .filter(models.EInvoiceRecord.p6ProjectName.in_(list(by_name)))
        .all()
        if by_name
        else []
    )
    window, total = _page(sorted(rows, key=lambda r: r.id), page, page_size)
    data = []
    for row in window:
        item = _dict(row)
        item["project_id"] = by_name.get(row.p6ProjectName)
        data.append(item)
    return envelope(
        sc.attach(data), filters=sc.filters, sources=["SAP"],
        page=page, page_size=page_size, total=total,
    )


@router.get("/activities")
def get_activities(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """P6 activities.

    132k rows portfolio-wide, so this one is worth scoping to a single
    `project_id` in practice. Joined on the P6 object id.
    """
    owners = {
        i.p6_object_id: i.project_id
        for i in sc.linked("p6")
        if i.p6_object_id is not None
    }
    rows = (
        db.query(models.P6Activity)
        .filter(models.P6Activity.project_object_id.in_(list(owners)))
        .all()
        if owners
        else []
    )
    window, total = _page(sorted(rows, key=lambda r: r.id), page, page_size)
    data = []
    for row in window:
        item = _dict(row)
        item["project_id"] = owners.get(row.project_object_id)
        item["duration_unit"] = "hours"
        data.append(item)
    return envelope(
        sc.attach(data), filters=sc.filters, sources=["P6"],
        page=page, page_size=page_size, total=total,
    )


# P6 counts Labor and Nonlabor in hours; the BESS schedules run a 7-day x 8-hour
# calendar, so a labour hour / 8 is a manday (see routers/bess.HOURS_PER_DAY).
_TIME_UNITS = {"Labor", "Nonlabor"}
_HOURS_PER_DAY = 8.0
_RESOURCE_TYPES = {"labor": "Labor", "nonlabor": "Nonlabor", "material": "Material"}


@router.get("/resources")
def get_resources(
    sc: Scope = Depends(scope),
    resource_type: Optional[str] = Query(
        None, description="labor | nonlabor | material. Omit for all three."
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """P6 resource assignments - Labor, Nonlabor and Material - per activity.

    Units and their basis are stated on every row rather than left implied:
    Labor and Nonlabor are P6 time units, so `unit` is "h" (Labor also carries
    the manday equivalent); Material takes the resource's own P6 unit of
    measure, which is null where P6 has none set - it is never guessed.
    """
    wanted_type = None
    if resource_type:
        wanted_type = _RESOURCE_TYPES.get(resource_type.strip().lower())
        if wanted_type is None:
            raise HTTPException(status_code=422,
                                detail="resource_type must be labor, nonlabor or material")
    owners = {
        i.p6_object_id: i.project_id
        for i in sc.linked("p6")
        if i.p6_object_id is not None
    }
    R, A = models.P6ResourceAssignment, models.P6Activity
    q = (
        db.query(R, A.activity_id, A.name, A.status)
        .outerjoin(A, A.p6_object_id == R.activity_object_id)
        .filter(R.project_object_id.in_(list(owners)))
    )
    if wanted_type:
        q = q.filter(R.resource_type == wanted_type)
    # Paged in SQL: portfolio-wide this is ~270k rows, and loading them all to
    # slice one page took ~9s per request.
    if owners:
        total = q.order_by(None).count()
        window = q.order_by(R.id).offset((page - 1) * page_size).limit(page_size).all()
    else:
        total, window = 0, []
    data = []
    for r, activity_id, activity_name, status in window:
        timed = r.resource_type in _TIME_UNITS
        item = {
            "project_id": owners.get(r.project_object_id),
            "activity_id": activity_id,
            "activity_name": activity_name,
            "activity_status": status,
            "resource_name": r.resource_name,
            "resource_type": r.resource_type,
            "planned_units": r.planned_units,
            "actual_units": r.actual_units,
            "remaining_units": r.remaining_units,
            "unit": "h" if timed else r.unit_of_measure,
            # resource_object_id is written by the same sync that reads the
            # unit, so a null there means "not synced since the UoM field was
            # added", not "P6 has no unit" - say which.
            "unit_basis": ("P6 time units (hours)" if timed
                           else "P6 resource unit of measure" if r.unit_of_measure
                           else "pending P6 resource sync" if r.resource_object_id is None
                           else "not set in P6"),
        }
        if r.resource_type == "Labor":
            item["planned_mandays"] = (r.planned_units or 0) / _HOURS_PER_DAY
            item["actual_mandays"] = (r.actual_units or 0) / _HOURS_PER_DAY
        data.append(item)
    return envelope(
        sc.attach(data), filters={**sc.filters, "resource_type": wanted_type}, sources=["P6"],
        page=page, page_size=page_size, total=total,
    )


# ── Tables previously reachable only through the SQL dump ───────────────────


@router.get("/p6-baselines")
def get_p6_baselines(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """P6 baseline projects (the plan a schedule is measured against), linked to
    their live project through `original_project_object_id`. Durations in hours."""
    owners = {i.p6_object_id: i.project_id for i in sc.linked("p6") if i.p6_object_id is not None}
    B = models.P6BaselineProject
    rows = db.query(B).filter(B.original_project_object_id.in_(list(owners))).all() if owners else []
    window, total = _page(sorted(rows, key=lambda r: r.id), page, page_size)
    data = []
    for row in window:
        item = _dict(row)
        item["project_id"] = owners.get(row.original_project_object_id)
        item["duration_unit"] = "hours"
        data.append(item)
    return envelope(sc.attach(data), filters=sc.filters, sources=["P6"],
                    page=page, page_size=page_size, total=total)


_BLOCK = re.compile(r"\bblock[\s_-]*0*(\d+)", re.I)


@router.get("/wbs")
def get_wbs(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """P6 WBS tree (code, name, parent) per project.

    P6's own `is_block` flag is not maintained (false on every node), so
    `block_number_derived` reads the block from the WBS name ("Block-07" -> 7)
    and is labelled as derived."""
    owners = {i.p6_object_id: i.project_id for i in sc.linked("p6") if i.p6_object_id is not None}
    W = models.P6WBSNode
    q = db.query(W).filter(W.project_object_id.in_(list(owners))) if owners else None
    total = q.count() if q is not None else 0
    window = q.order_by(W.id).offset((page - 1) * page_size).limit(page_size).all() if q is not None else []
    data = []
    for row in window:
        item = _dict(row)
        item["project_id"] = owners.get(row.project_object_id)
        m = _BLOCK.search(row.wbs_name or "")
        item["block_number_derived"] = int(m.group(1)) if m else None
        data.append(item)
    return envelope(sc.attach(data), filters=sc.filters, sources=["P6"],
                    page=page, page_size=page_size, total=total)


@router.get("/transmission-network")
def get_transmission_network(
    region: Optional[str] = Query(None, description="Khavda | Rajasthan. Omit for both."),
    db: Session = Depends(get_db),
):
    """The transmission network: substations (nodes) and lines (edges), with
    construction progress (foundation / erection / stringing %), voltage, status
    and delay flag. Read readiness from `normalized_status` (charged /
    in_progress / under_bidding); node x/y are schematic layout positions, not
    coordinates. Both Khavda and Rajasthan are included."""
    N, E = models.TcNetworkNode, models.TcNetworkEdge
    nq, eq = db.query(N), db.query(E)
    if region:
        nq, eq = nq.filter(N.region.ilike(region)), eq.filter(E.region.ilike(region))
    edges = [_dict(e) for e in eq.order_by(E.id).all()]
    owners = {i.mapping_id: i.project_id for i in project_identity.resolve_all(db)}
    for e in edges:
        e["project_id"] = owners.get(e.get("mapping_id"))
    return envelope({"nodes": [_dict(n) for n in nq.order_by(N.id).all()], "edges": edges},
                    filters={"region": region}, sources=["TC"])


@router.get("/notifications")
def get_notifications(
    sc: Scope = Depends(scope),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """Change notifications (P6 date / progress changes etc.), newest first,
    with old -> new values, action status and suggestion. Linked to a project
    by its P6 name."""
    by_name = {i.name: i.project_id for i in sc.identities if i.name}
    N = models.Notification
    q = db.query(N).filter(N.project_name.in_(list(by_name))) if by_name else None
    total = q.count() if q is not None else 0
    window = (q.order_by(N.created_at.desc(), N.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
              if q is not None else [])
    data = []
    for row in window:
        item = _dict(row)
        item["project_id"] = by_name.get(row.project_name)
        data.append(item)
    return envelope(sc.attach(data), filters=sc.filters, sources=["P6"],
                    page=page, page_size=page_size, total=total)
