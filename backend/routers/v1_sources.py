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

Omit `project_id` and the endpoint returns the whole portfolio under the
standard portfolio/phase scoping.
"""

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


def _page(rows: list, page: int, page_size: int):
    start = (page - 1) * page_size
    return rows[start : start + page_size], len(rows)


def _dict(row) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


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
        data.append(item)
    return envelope(
        data, filters=sc.filters, sources=["P6"],
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
        data, filters=sc.filters, sources=["SAP"],
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
        data, filters=sc.filters, sources=["SAP"],
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
        data, filters={**sc.filters, "kind": kind}, sources=["Pulse"],
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
    window, total = _page(sorted(rows, key=lambda r: r.id), page, page_size)
    data = []
    for row in window:
        item = _dict(row)
        item["project_id"] = owners.get(row.mapping_id)
        data.append(item)
    return envelope(
        data, filters=sc.filters, sources=["TC"],
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
        data, filters=sc.filters, sources=["SAP"],
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
        data, filters=sc.filters, sources=["SAP"],
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
    by_name, by_plant = {}, {}
    for identity in sc.identities:
        if identity.name:
            by_name[identity.name] = identity.project_id
        if identity.sap_plant_code:
            by_plant[identity.sap_plant_code] = identity.project_id

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
        data.append(item)
    return envelope(
        data, filters=sc.filters, sources=["SAP"],
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
        data, filters=sc.filters, sources=["SAP"],
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
        data.append(item)
    return envelope(
        data, filters=sc.filters, sources=["P6"],
        page=page, page_size=page_size, total=total,
    )
