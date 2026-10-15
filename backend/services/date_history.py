"""LTA / SCOD change history (models.ProjectDateChange).

record()  - called wherever the dates change: the transmission portal sync
            (services/tc_sync.py) and manual edits (routers/mappings.py)
for_mappings() - each project's recent changes and whether a date changed
            today (IST), for the Ordering Schedule
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional

IST = timedelta(hours=5, minutes=30)
FIELDS = ("lta", "scod")
SOURCE_LABEL = {"portal": "Transmission portal sync", "manual": "Edited in Akasha"}


def _day(v) -> Optional[datetime]:
    if v is None:
        return None
    return datetime(v.year, v.month, v.day)


def record(db, mapping, field: str, old, new, source: str, by: Optional[str] = None) -> bool:
    """Add a history row when the date really changed (by calendar day)."""
    old_d, new_d = _day(old), _day(new)
    if old_d == new_d:
        return False
    import models
    db.add(models.ProjectDateChange(mapping_id=mapping.id, project_id=mapping.project_id, field=field,
                                    old_value=old_d, new_value=new_d, source=source, changed_by=by,
                                    changed_at=datetime.utcnow()))
    return True


def _fmt(d: Optional[datetime]) -> str:
    return d.strftime("%d-%b-%y") if d else ""


def for_mappings(db, mapping_ids: Iterable[int], per_field: int = 20) -> Dict[int, dict]:
    """{mapping_id: {"lta": [...], "scod": [...], "lta_changed_today": bool, "scod_changed_today": bool}}
    Newest change first. 'Today' is the IST calendar day."""
    import models
    ids = list(mapping_ids)
    if not ids:
        return {}
    today_ist = (datetime.utcnow() + IST).date()
    rows = (db.query(models.ProjectDateChange)
            .filter(models.ProjectDateChange.mapping_id.in_(ids))
            .order_by(models.ProjectDateChange.changed_at.desc(), models.ProjectDateChange.id.desc()).all())
    out: Dict[int, dict] = defaultdict(lambda: {"lta": [], "scod": [], "lta_changed_today": False, "scod_changed_today": False})
    for r in rows:
        h = out[r.mapping_id]
        if r.field not in FIELDS or len(h[r.field]) >= per_field:
            continue
        when_ist = r.changed_at + IST
        delta = (r.new_value - r.old_value).days if r.old_value and r.new_value else None
        h[r.field].append({
            "from": _fmt(r.old_value), "to": _fmt(r.new_value), "days": delta,
            "source": SOURCE_LABEL.get(r.source, r.source), "by": r.changed_by or "",
            "at": r.changed_at.isoformat() + "Z", "at_ist": when_ist.strftime("%d-%b-%y %H:%M IST"),
        })
        if when_ist.date() == today_ist:
            h[f"{r.field}_changed_today"] = True
    return dict(out)
