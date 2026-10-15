"""
Canonical project identity.

The platform joins five source systems that each key projects differently:

    canonical   ProjectMapping.project_id      'AHEJ5L', 'FY26-P16'
    surrogate   ProjectMapping.id              1779              (TC foreign key)
    P6          P6Project.project_id           'FY26-P16'
    P6 internal P6Project.p6_object_id         5119              (activity FK)
    SAP         wbs_element prefixes           'H-9712-01-01-04'
    SAP plant   plant_code                     '9712'
    Pulse       project_name (free text)       'MSEDCL PPA Ph-3'

Before this module every endpoint picked whichever of those suited it, so the
API exposed six different "project ids" — `project_id`, `mapping_id`,
`project_name`, `p6_object_id`, `project_object_id` and a bare name path
segment. A client had to know which endpoint wanted which.

ProjectMapping.project_id is the canonical key: it is unique and non-null
across all 64 mappings, and it is already what the frontend routes on.

The contract here is the usual one for this problem — POSTEL'S LAW: accept any
identifier the platform has ever exposed, always answer with the canonical one,
and state explicitly which source systems the project actually links to rather
than returning silent empties.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from sqlalchemy.orm import Session

import models
from services import portfolio as portfolio_svc

SOURCE_SYSTEMS = ("p6", "sap", "tc", "pulse")


@dataclass
class ProjectIdentity:
    """One project, and every key needed to reach it in a source system."""

    # ── canonical ──
    project_id: str
    mapping_id: int
    name: str

    # ── attributes ──
    portfolio: Optional[str] = None
    is_commissioned: bool = False
    capacity_mwac: Optional[float] = None

    # ── project master (ProjectMapping), exposed as-is ──
    project_name: Optional[str] = None       # business name, e.g. "MSEDCL PPA Ph-3"
    p6_project_name: Optional[str] = None    # P6's name; `name` above prefers it
    spv_name: Optional[str] = None
    cluster: Optional[str] = None
    subcluster: Optional[str] = None
    category: Optional[str] = None           # PPA / Merchant / ...
    plot_no: Optional[str] = None
    mms_type: Optional[str] = None           # HSAT / fixed tilt / ...
    capacity_mwdc: Optional[float] = None
    dc_ac_ratio: Optional[float] = None      # master column "OL"
    priority: Optional[str] = None
    source_of_origin: Optional[str] = None
    lta_date: Optional[str] = None
    manual_scod: Optional[str] = None
    manual_scod_is_lta: Optional[bool] = None
    # Transmission readiness from the TC tracker: foundation / erection /
    # stringing %, lines charged (project_mapping.tc_progress, set by the TC sync).
    tc_progress: Optional[dict] = None

    # ── SAP / WBS keys from the master ──
    spv_plant_code: Optional[str] = None
    agel_wbs: Optional[str] = None
    age6l_wbs: Optional[str] = None
    module_wbs: Optional[str] = None

    # ── per-system keys; None means the project is not linked there ──
    p6_project_id: Optional[str] = None
    p6_object_id: Optional[int] = None
    sap_plant_code: Optional[str] = None
    sap_wbs_prefixes: list[str] = field(default_factory=list)
    pulse_project_name: Optional[str] = None
    pulse_project_uuid: Optional[str] = None
    tc_mapping_id: Optional[int] = None

    @property
    def linked(self) -> list[str]:
        out = []
        if self.p6_object_id is not None:
            out.append("p6")
        if self.sap_wbs_prefixes or self.sap_plant_code:
            out.append("sap")
        if self.tc_mapping_id is not None:
            out.append("tc")
        if self.pulse_project_uuid or self.pulse_project_name:
            out.append("pulse")
        return out

    @property
    def unlinked(self) -> list[str]:
        return [s for s in SOURCE_SYSTEMS if s not in self.linked]

    def context(self) -> dict:
        """The compact project block carried on every /api/v1 source row, so a
        row can be read without a second call. Always from the project master,
        so it is identical on every endpoint."""
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "p6_project_name": self.p6_project_name,
            "spv_name": self.spv_name,
            "cluster": self.cluster,
            "subcluster": self.subcluster,
            "category": self.category,
            "plot_no": self.plot_no,
            "capacity_mwac": self.capacity_mwac,
            "capacity_mwdc": self.capacity_mwdc,
            "is_commissioned": self.is_commissioned,
            "sap_wbs_prefixes": self.sap_wbs_prefixes,
            "p6_project_id": self.p6_project_id,
        }

    def to_dict(self) -> dict:
        """Wire format. `linked` / `unlinked` are the important part: they let a
        caller tell "no non-conformances" apart from "not connected to Pulse",
        which are currently both an empty list."""
        d = asdict(self)
        d["linked"] = self.linked
        d["unlinked"] = self.unlinked
        return d


def _wbs_prefixes(m: models.ProjectMapping) -> list[str]:
    """SAP prefixes, derived the way dashboard.py derives them: any H-XXXX token
    in spv_plant_code / agel / age6l, truncated to six characters."""
    codes: list[str] = []
    for value in (m.spv_plant_code, m.agel, m.age6l):
        if not value:
            continue
        for token in re.findall(r"H-\S+", str(value).strip()):
            token = token.strip()[:6]
            if len(token) >= 6:
                codes.append(token)
    return sorted(set(codes))


def _clean(v) -> str:
    return str(v).strip() if v is not None else ""


_BLANKS = {"", "-", "--", "na", "n/a", "nan", "none", "null"}


def _text(v) -> Optional[str]:
    """Master text value, or None for the placeholders the sheet uses for
    blank ("-", "NA", ...), so an API caller never has to special-case them."""
    t = _clean(v)
    return None if t.lower() in _BLANKS else t


def _num(v) -> Optional[float]:
    """Master numerics are sometimes stored as text ("1.35")."""
    try:
        return float(str(v).strip()) if v not in (None, "") else None
    except ValueError:
        return None


def resolve(db: Session, ref: str | int) -> Optional[ProjectIdentity]:
    """Resolve any known project reference to one canonical identity.

    Accepted, in priority order:
      1. ProjectMapping.project_id   — canonical
      2. ProjectMapping.id           — surrogate, used by TC foreign keys
      3. P6Project.p6_object_id      — P6 internal id
      4. project_name_from_p6 / project — exact, then case-insensitive

    Returns None if nothing matches; callers should answer 404.
    """
    ref_s = _clean(ref)
    if not ref_s:
        return None

    mapping = (
        db.query(models.ProjectMapping)
        .filter(models.ProjectMapping.project_id == ref_s)
        .first()
    )

    if mapping is None and ref_s.isdigit():
        as_int = int(ref_s)
        mapping = (
            db.query(models.ProjectMapping)
            .filter(models.ProjectMapping.id == as_int)
            .first()
        )
        if mapping is None:
            p6 = (
                db.query(models.P6Project)
                .filter(models.P6Project.p6_object_id == as_int)
                .first()
            )
            if p6 is not None and p6.project_id:
                mapping = (
                    db.query(models.ProjectMapping)
                    .filter(models.ProjectMapping.project_id == p6.project_id)
                    .first()
                )

    if mapping is None:
        mapping = (
            db.query(models.ProjectMapping)
            .filter(
                (models.ProjectMapping.project_name_from_p6 == ref_s)
                | (models.ProjectMapping.project == ref_s)
            )
            .first()
        )

    if mapping is None:
        mapping = (
            db.query(models.ProjectMapping)
            .filter(models.ProjectMapping.project_name_from_p6.ilike(ref_s))
            .first()
        )

    if mapping is None:
        return None

    return _build(db, mapping)


def _build(db: Session, m: models.ProjectMapping) -> ProjectIdentity:
    identity = ProjectIdentity(
        project_id=_clean(m.project_id),
        mapping_id=m.id,
        name=_clean(m.project_name_from_p6) or _clean(m.project) or _clean(m.project_id),
        # Same rule as every dashboard filter: a Wind project left without a
        # cluster takes it from its category (services/portfolio.py).
        portfolio=portfolio_svc.mapping_cluster(m),
        is_commissioned=bool(m.is_commissioned),
        capacity_mwac=m.capacity_mwac,
        sap_plant_code=m.spv_plant_code,
        sap_wbs_prefixes=_wbs_prefixes(m),
        project_name=_text(m.project),
        p6_project_name=_text(m.project_name_from_p6),
        spv_name=_text(m.spv_name),
        cluster=_text(m.cluster),
        subcluster=_text(m.subcluster),
        category=_text(m.category),
        plot_no=_text(m.plot_no),
        mms_type=_text(m.mms_type),
        capacity_mwdc=m.capacity_mwdc,
        dc_ac_ratio=_num(m.ol),
        priority=_text(m.priority),
        source_of_origin=_text(m.source_of_origin),
        lta_date=m.lta_date.isoformat() if hasattr(m.lta_date, "isoformat") else (_text(m.lta_date)),
        manual_scod=m.manual_scod.isoformat() if hasattr(m.manual_scod, "isoformat") else (_text(m.manual_scod)),
        manual_scod_is_lta=m.manual_scod_is_lta,
        spv_plant_code=_text(m.spv_plant_code),
        agel_wbs=_text(m.agel),
        age6l_wbs=_text(m.age6l),
        module_wbs=_text(m.module_wbs),
        tc_progress=m.tc_progress if isinstance(m.tc_progress, dict) and m.tc_progress else None,
    )

    p6 = (
        db.query(models.P6Project)
        .filter(models.P6Project.project_id == m.project_id)
        .first()
    )
    if p6 is not None:
        identity.p6_project_id = p6.project_id
        identity.p6_object_id = p6.p6_object_id

    if db.query(models.TcProjectEntry.id).filter(
        models.TcProjectEntry.mapping_id == m.id
    ).first():
        identity.tc_mapping_id = m.id

    # Pulse stamps its own UUID on every NC and RFI. When the mapping carries
    # that UUID the join is an indexed equality — no name matching at all.
    identity.pulse_project_uuid = getattr(m, "pulse_project_uuid", None)
    if identity.pulse_project_uuid:
        row = (
            db.query(models.PulseNC.project_name)
            .filter(models.PulseNC.project_id == identity.pulse_project_uuid)
            .first()
        )
        identity.pulse_project_name = row[0] if row else None
        return identity

    # Fallback for mappings whose UUID has not been filled in yet: match the
    # free-text project name, exact then case-insensitive. Nothing fuzzier — a
    # wrong match here attributes one site's non-conformances to another.
    for candidate in (m.project_name_from_p6, m.project):
        name = _clean(candidate)
        if not name:
            continue
        hit = (
            db.query(models.PulseNC.project_name)
            .filter(models.PulseNC.project_name == name)
            .first()
            or db.query(models.PulseNC.project_name)
            .filter(models.PulseNC.project_name.ilike(name))
            .first()
        )
        if hit:
            identity.pulse_project_name = hit[0]
            break

    return identity


def resolve_all(db: Session, portfolio: str = None, phase: str = None) -> list[ProjectIdentity]:
    """Every project, scoped by the standard filters.

    `phase` omitted means every phase. Callers that want the dashboard's
    default scoping pass "ongoing" explicitly.
    """
    query = db.query(models.ProjectMapping)

    query = portfolio_svc.filter_mappings(query, portfolio)

    normalised = (phase or "all").strip().lower()
    if normalised == "ongoing":
        query = query.filter(models.ProjectMapping.is_commissioned.is_(False))
    elif normalised == "commissioned":
        query = query.filter(models.ProjectMapping.is_commissioned.is_(True))

    # Same dedup rule the dashboard applies: drop demo rows, then keep the row
    # with the most complete SAP code per project_id.
    dedup: dict[str, models.ProjectMapping] = {}
    for m in query.all():
        label = f"{m.project_name_from_p6 or ''} {m.project or ''}"
        if "demo" in label.lower() or not m.project_id:
            continue
        current = dedup.get(m.project_id)
        if current is None or len(_clean(m.spv_plant_code)) > len(_clean(current.spv_plant_code)):
            dedup[m.project_id] = m

    return [_build(db, m) for m in dedup.values()]
