"""
Project progress — one definition, used by every screen.

    progress = Σ actual non-labour units / Σ planned (budgeted) non-labour units

summed over every resource assignment on every activity of the project
(p6_resource_assignment, resource_type = 'Nonlabor'). Non-labour resources
are the equipment / machinery lines; Labor and Material are separate P6
types and are not included.

Why this exists: four places (project_service, dashboard ×2, metrics) each
carried the same formula on the PROJECT-level P6 summary fields —
actual_non_labor_units / at_completion_non_labor_units — and each fell
through to duration_percent_complete because at_completion_non_labor_units
is 0 on all 67 projects. The screens were showing "share of schedule
duration elapsed" under the label "progress" and nobody could tell, because
the first fallback (construction_percent_complete) is a column that does not
exist and the drop to duration % was silent. The assignment table has the
budget the summary lacks: planned_units is populated on 127k of 132k
non-labour rows, and every project has some.

The fallback is still duration %, but it is now reported as the basis so
the UI can label it — never presented as the same thing.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

import models

NONLABOR = "Nonlabor"


def nonlabor_units_by_project(db: Session, project_object_ids: Optional[list] = None) -> Dict[int, Tuple[float, float]]:
    """project_object_id → (Σ actual_units, Σ planned_units) for non-labour assignments."""
    q = db.query(
        models.P6ResourceAssignment.project_object_id,
        func.coalesce(func.sum(models.P6ResourceAssignment.actual_units), 0.0),
        func.coalesce(func.sum(models.P6ResourceAssignment.planned_units), 0.0),
    ).filter(models.P6ResourceAssignment.resource_type == NONLABOR)
    if project_object_ids:
        q = q.filter(models.P6ResourceAssignment.project_object_id.in_(project_object_ids))
    return {pid: (float(a or 0), float(p or 0)) for pid, a, p in q.group_by(models.P6ResourceAssignment.project_object_id).all() if pid is not None}


def project_progress(p6_proj, units: Dict[int, Tuple[float, float]]) -> Tuple[float, str, dict]:
    """Returns (progress 0..1, basis, detail).

    basis is 'nonlabor_units' when the ratio could be computed, otherwise
    'duration_pct'. detail carries the numerator/denominator so the UI can
    show the figures behind the percentage."""
    if p6_proj is None:
        return 0.0, "none", {}
    actual, planned = units.get(p6_proj.p6_object_id, (0.0, 0.0))
    if planned > 0:
        # An assignment can run over its plan (3.6k rows do); the project
        # ratio is capped so the tile never reads above 100%.
        return max(0.0, min(1.0, actual / planned)), "nonlabor_units", {"actual_units": round(actual), "planned_units": round(planned)}
    raw = p6_proj.duration_percent_complete or 0.0
    raw = float(raw) if raw <= 1.0 else float(raw) / 100.0
    return max(0.0, min(1.0, raw)), "duration_pct", {"duration_percent_complete": round(raw * 100, 1)}
