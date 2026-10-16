"""Demo projects are visible in Module Ordering and Project 360 only.

Demo projects (project-mapping rows in an "Akasha Demo..." portfolio, added
by scripts/demo_email_project.py) exist to test the Ordering Schedule, its
approvals and its emails, and in Project 360 (the list, a project's page and its
data). Everywhere else - the dashboards,
KPIs, CPAG packs - they must not appear, nor their P6 data.

How: every ORM SELECT on ProjectMapping or P6Project gets a criterion that
leaves demo projects out (install(), once, on the session factory). The code
that SHOULD see them opts in:
  - routers: Depends(see_demo) on Module Ordering's routers (the Ordering
    Schedule, approvals, alerts, email admin, project mappings admin)
  - functions: @visible on the Ordering Schedule summary, the syncs, the
    demo / self-test scripts
Raw SQL that lists projects adds DEMO_SQL_CLAUSE itself.
"""
import functools
from contextvars import ContextVar

from sqlalchemy import column, event, func, or_, select, table
from sqlalchemy.orm import Session, with_loader_criteria

DEMO_PREFIX = "akasha demo"
_include: ContextVar[bool] = ContextVar("akasha_include_demo", default=False)

# The P6 ids of demo projects, as a plain-table subquery (not the ORM entity,
# so the ProjectMapping criterion below is not applied to it).
_pm = table("project_mapping", column("project_id"), column("cluster"))
_DEMO_IDS = select(_pm.c.project_id).where(
    func.lower(func.coalesce(_pm.c.cluster, "")).like(DEMO_PREFIX + "%"), _pm.c.project_id.isnot(None))

# For raw SQL on p6_project aliased p6: "AND p6.project_id NOT IN (...)".
DEMO_SQL_CLAUSE = ("p6.project_id NOT IN (SELECT project_id FROM project_mapping "
                   "WHERE lower(coalesce(cluster, '')) LIKE 'akasha demo%' AND project_id IS NOT NULL)")


def is_demo_cluster(cluster) -> bool:
    return str(cluster or "").lower().startswith(DEMO_PREFIX)


def showing() -> bool:
    return _include.get()


def visible(fn):
    """Run `fn` with demo projects visible."""
    @functools.wraps(fn)
    def wrapper(*a, **k):
        token = _include.set(True)
        try:
            return fn(*a, **k)
        finally:
            _include.reset(token)
    return wrapper


def show_all() -> None:
    """For scripts: demo projects visible for the rest of this process."""
    _include.set(True)


async def see_demo() -> None:
    """Router dependency (async, so it runs in the request's own context and
    the endpoint - sync or async - inherits it)."""
    _include.set(True)


def _hide_demo(state) -> None:
    if not state.is_select or _include.get() or state.execution_options.get("include_demo"):
        return
    import models
    state.statement = state.statement.options(
        with_loader_criteria(models.ProjectMapping,
                             lambda cls: ~func.lower(func.coalesce(cls.cluster, "")).like(DEMO_PREFIX + "%"),
                             include_aliases=True, track_closure_variables=False),
        with_loader_criteria(models.P6Project, lambda cls: or_(cls.project_id.is_(None), ~cls.project_id.in_(_DEMO_IDS)),
                             include_aliases=True, track_closure_variables=False),
    )


_installed = False


def install() -> None:
    global _installed
    if not _installed:
        event.listen(Session, "do_orm_execute", _hide_demo)
        _installed = True
