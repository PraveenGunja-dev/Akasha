"""Roles, permissions, dashboards and portfolio scope.

The PERMISSION catalogue and the DASHBOARDS are code: each names a screen or
an API capability that exists in this codebase. Portfolios are data - the
clusters in project_mapping - assigned per user, not per role, so a role is a
job (PMAG, Projects, TC ...) and the same role serves every portfolio.

Which ROLE holds which permission is data (akasha_role), seeded once
from DEFAULT_ROLES and edited by a superadmin from the admin console. Seeding
never overwrites a role that already exists, so console edits survive restarts.

Enforcement is on the server (middleware/auth_guard.py):
  1. every /api call needs a signed-in session;
  2. calls in ROUTE_POLICIES need the named permission;
  3. a user with portfolios assigned (akasha_user.portfolios) is
     portfolio-scoped: only the calls in SCOPED_ROUTES are open to them, each
     checked against their portfolios (services/portfolio.py decides which
     portfolio a project belongs to).
     Anything not listed there is refused - deny by default, because an
     endpoint that does not filter by portfolio would show every portfolio.
The UI hides what a user cannot open, but that is a convenience, not the control.
"""
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

SUPERADMIN = "superadmin"


@dataclass(frozen=True)
class Permission:
    key: str
    label: str
    group: str
    description: str


@dataclass(frozen=True)
class Dashboard:
    key: str
    label: str
    route: str
    description: str

    @property
    def permission(self) -> str:
        return f"dashboard.{self.key}"


DASHBOARDS: list[Dashboard] = [
    Dashboard("executive", "Executive", "/ceo-dashboard",
              "Portfolio command centre: projects, SAP, P6, transmission, modules"),
    Dashboard("pmag", "PMAG", "/pmag", "Portfolio Management & Governance"),
    Dashboard("projects", "Projects", "/projects", "Project execution view"),
    Dashboard("tc_ordering", "TC Ordering", "/tc-ordering", "Transmission & connectivity ordering"),
    Dashboard("tc_stores", "TC Stores", "/tc-stores", "Transmission & connectivity stores"),
]

PERMISSIONS: list[Permission] = [
    *[Permission(d.permission, f"{d.label} dashboard", "Dashboards", d.description) for d in DASHBOARDS],
    Permission("data.edit", "Edit project data", "Data",
               "Project mappings, SCOD / LTA / priority, P6 edits, CPAG manual entries and uploads, EAC settings, statutory uploads"),
    Permission("data.sync", "Run data syncs", "Data",
               "Trigger SharePoint / SAP / P6 / TC / e-invoice syncs and change sync schedules and source credentials"),
    Permission("users.manage", "Manage users", "Administration",
               "Create users, assign roles, reset passwords, unlock and deactivate accounts, end sessions"),
    Permission("roles.manage", "Manage roles", "Administration",
               "Create roles and change the permissions each role grants"),
    Permission("audit.view", "View audit log", "Administration",
               "Sign-ins, failed attempts, lockouts and every change to users and roles"),
]
PERMISSION_KEYS = {p.key for p in PERMISSIONS}
ALL_DASHBOARDS = [d.permission for d in DASHBOARDS]

# Seed only: written when a role is missing, never over an existing one.
DEFAULT_ROLES = [
    {"key": SUPERADMIN, "name": "Super Admin", "is_system": True,
     "description": "Full access to every dashboard, all data and administration",
     "permissions": sorted(PERMISSION_KEYS)},
    {"key": "executive", "name": "Executive (CEO)", "is_system": True,
     "description": "All five dashboards and project data edits",
     "permissions": ALL_DASHBOARDS + ["data.edit"]},
    {"key": "pmag", "name": "PMAG", "is_system": True,
     "description": "PMAG governance dashboard", "permissions": ["dashboard.pmag"]},
    {"key": "projects", "name": "Projects", "is_system": True,
     "description": "Projects execution dashboard", "permissions": ["dashboard.projects"]},
    {"key": "tc_ordering", "name": "TC Ordering", "is_system": True,
     "description": "Techno-commercial ordering dashboard", "permissions": ["dashboard.tc_ordering"]},
    {"key": "tc_stores", "name": "TC Stores", "is_system": True,
     "description": "Techno-commercial stores dashboard", "permissions": ["dashboard.tc_stores"]},
]
# Roles from the first design (portfolio as a role), replaced by per-user
# portfolios. Removed on start-up only while no user holds them.
RETIRED_ROLES = {"pmag_solar", "pmag_wind", "pmag_bess"}

# ── Permission rules for API calls ──────────────────────────────────────────
# (methods, path regex on the /api path, permission). First match wins; a call
# matching none needs only a signed-in session. Admin endpoints check their own
# permission in routers/admin.py.
_WRITE = {"POST", "PUT", "PATCH", "DELETE"}
ROUTE_POLICIES: list[tuple[set, re.Pattern, str]] = [(m, re.compile(p), perm) for m, p, perm in [
    (_WRITE, r"^/api/(sharepoint|p6|tc|mapping|capacity|pulse|einvoice)/sync(/|$)", "data.sync"),
    (_WRITE, r"^/api/p6/update-password$", "data.sync"),
    (_WRITE, r"^/api/integrations/", "data.sync"),
    (_WRITE, r"^/api/bess/(cpag/baselines/sync|eac/reload)$", "data.sync"),
    (_WRITE, r"^/api/mappings(/|$)", "data.edit"),
    (_WRITE, r"^/api/p6/(projects|activities)/", "data.edit"),
    (_WRITE, r"^/api/bess/cpag/manual(/|$)", "data.edit"),
    (_WRITE, r"^/api/bess/[^/]+/eac/", "data.edit"),
    (_WRITE, r"^/api/statutory/upload$", "data.edit"),
]]

# Reachable without a session.
PUBLIC_PATHS = {"/api/auth/login", "/api/auth/logout"}
# Reachable while a password change is pending.
PASSWORD_CHANGE_PATHS = {"/api/auth/me", "/api/auth/password", "/api/auth/logout"}

# ── Portfolio-scoped access ─────────────────────────────────────────────────
# The only calls open to a portfolio-scoped user, and how each is checked:
#   "portfolio" - honours ?portfolio= (clusters, comma-separated): any cluster
#                 outside the user's is refused, a missing one is set to all of
#                 the user's clusters;
#                 ?project_name= must name a project in the user's portfolios
#   "project"   - the named group `pid` is a project_id in the user's portfolios
#   "v1project" - like "project", but `pid` may be any reference /api/v1
#                 resolves (canonical id, mapping id, P6 object id, name)
#   "mapping"   - the named group `mid` is a project_mapping row in them
#   "namespace" - a portfolio's own API (/api/bess/...): open when the user
#                 holds every cluster it serves (NAMESPACE_CLUSTERS)
#   "open"      - carries no project data (identity, static placeholders)
# Each entry was checked against its handler; add one only after doing the same.
SCOPED_ROUTES: list[tuple[re.Pattern, str]] = [(re.compile(p), kind) for p, kind in [
    (r"^/api/auth/", "open"),
    # Portfolio lists and summaries (each handler filters with services/portfolio.py)
    (r"^/api/pmag/dashboard$", "portfolio"),
    (r"^/api/dashboard/summary$", "portfolio"),
    (r"^/api/dashboard/capacity-overview$", "portfolio"),
    (r"^/api/summary$", "portfolio"),
    (r"^/api/financials(/details)?$", "portfolio"),
    (r"^/api/project-360$", "portfolio"),
    (r"^/api/quality/(overview|contractors|by-project|ncs|trends)$", "portfolio"),
    (r"^/api/statutory/(dashboard-summary|compliance|epc-status|insurance)$", "portfolio"),
    (r"^/api/module-deliveries/summary$", "portfolio"),
    (r"^/api/intelligence/portfolio/(summary|hotspots)$", "portfolio"),   # before the per-project rule
    # One project (path segment `pid` is its project_id)
    (r"^/api/project-360/(?P<pid>[^/]+)/detail$", "project"),
    (r"^/api/dashboard/api/projects/(?P<pid>[^/]+)/(slr|installation-progress|delay-reasons|installation-blocks)$", "project"),
    (r"^/api/intelligence/(?P<pid>[^/]+)(/.*)?$", "project"),
    (r"^/api/quality/project/(?P<pid>[^/]+)$", "project"),
    (r"^/api/statutory/(compliance|epc-status|p6-approvals)/(?P<pid>[^/]+)$", "project"),
    (r"^/api/tc-network/project/(?P<pid>[^/]+)$", "project"),
    (r"^/api/p6/projects/(?P<pid>[^/]+)$", "project"),                    # edit: also needs data.edit
    (r"^/api/mappings/(?P<mid>\d+)$", "mapping"),                          # edit: also needs data.edit
    # The integration API (/api/v1). ?project_id= is checked like a path id.
    (r"^/api/v1/projects/(?P<pid>[^/]+)(/identity)?$", "v1project"),
    (r"^/api/v1/(projects|coverage|p6|p6-baselines|sap|slr|pulse|transmission|inventory|material-documents"
     r"|trial-run|einvoice|activities|resources|wbs|notifications)$", "portfolio"),
    (r"^/api/v1/dictionary$", "open"),
    # A portfolio's own API
    (r"^/api/(?P<ns>solar|wind|bess)(/|$)", "namespace"),
]]

# Reachable with an API key: the read-only integration API, nothing else.
API_KEY_PATH = re.compile(r"^/api/v1/")


def required_permission(method: str, path: str) -> str | None:
    for methods, pattern, perm in ROUTE_POLICIES:
        if method in methods and pattern.search(path):
            return perm
    return None


# Changes the auth guard records in the activity trail (sign-in and admin
# actions are recorded by their own handlers, with more detail). Any write
# that needs a data permission is a change; the others are listed here.
_AUDITED_EXTRA: list[tuple[re.Pattern, str]] = [(re.compile(p), a) for p, a in [
    (r"^/api/notifications/[^/]+/(action|thread|push)$", "notification.action"),
]]


def audited_write(method: str, path: str) -> str | None:
    """The audit action for a write call, or None when it is not recorded."""
    if method not in _WRITE:
        return None
    perm = required_permission(method, path)
    if perm == "data.sync":
        return "data.sync"
    if perm == "data.edit":
        return "data.change"
    for pattern, action in _AUDITED_EXTRA:
        if pattern.search(path):
            return action
    return None


# The clusters whose projects each portfolio API serves. A scoped user may use
# the API only if they hold every one of them - otherwise it would show them a
# project outside their portfolios. Checked against the routers:
#   /api/solar - the Solar CPAG pack: Bandha + Baiya, both Solar Rajasthan
#   /api/wind  - the Wind CPAG pack: Mundra North (Wind)
#   /api/bess  - BESS projects and their CPAG
NAMESPACE_CLUSTERS = {"solar": {"solar rajasthan"}, "wind": {"wind"}, "bess": {"bess"}}


def namespace_open(ns: str, scope: list[str]) -> bool:
    return ns in NAMESPACE_CLUSTERS and NAMESPACE_CLUSTERS[ns] <= {c.strip().lower() for c in scope}


def user_scope(user) -> list[str] | None:
    """The clusters a user may see; None = every portfolio."""
    if user.role == SUPERADMIN:
        return None
    clusters = [c for c in (user.portfolios or []) if isinstance(c, str) and c.strip()]
    return clusters or None


def seed_roles(db: Session) -> None:
    from models import AkashaRole
    from models import AkashaUser
    for key in RETIRED_ROLES:
        role = db.query(AkashaRole).filter(AkashaRole.key == key).first()
        if role and not db.query(AkashaUser).filter(AkashaUser.role == key).count():
            db.delete(role)
    # "PMAG Head" was the all-portfolio PMAG role of the first design; with
    # portfolios on the user it is simply PMAG. Only an unedited name changes.
    pmag = db.query(AkashaRole).filter(AkashaRole.key == "pmag", AkashaRole.name == "PMAG Head").first()
    if pmag:
        pmag.name, pmag.description = "PMAG", "PMAG governance dashboard"
    # A permission removed from the catalogue (e.g. portfolio.* when portfolios
    # moved to the user) is dropped from every stored role.
    for role in db.query(AkashaRole).all():
        kept = [p for p in (role.permissions or []) if p in PERMISSION_KEYS]
        if kept != list(role.permissions or []):
            role.permissions = kept
    existing = {r.key for r in db.query(AkashaRole.key)}
    for r in DEFAULT_ROLES:
        if r["key"] not in existing:
            db.add(AkashaRole(key=r["key"], name=r["name"], description=r["description"],
                              permissions=r["permissions"], is_system=r["is_system"],
                              created_at=datetime.utcnow()))
    db.commit()


# Role permissions are read on every API call; cache them briefly. An edit in
# the console calls invalidate(), so this process sees it at once and any
# other worker within _TTL seconds.
_TTL = 30.0
_cache: dict[str, tuple[float, frozenset]] = {}
_lock = threading.Lock()


def invalidate() -> None:
    with _lock:
        _cache.clear()


def role_permissions(db: Session, role_key: str) -> frozenset:
    if role_key == SUPERADMIN:
        return frozenset(PERMISSION_KEYS)   # always everything, including permissions added later
    now = time.monotonic()
    with _lock:
        hit = _cache.get(role_key)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    from models import AkashaRole
    role = db.query(AkashaRole).filter(AkashaRole.key == role_key).first()
    perms = frozenset(p for p in (role.permissions or []) if p in PERMISSION_KEYS) if role else frozenset()
    with _lock:
        _cache[role_key] = (now, perms)
    return perms


def dashboards_for(perms: frozenset) -> list[dict]:
    return [{"key": d.key, "label": d.label, "route": d.route, "description": d.description}
            for d in DASHBOARDS if d.permission in perms]


def portfolio_access(db: Session, user) -> dict:
    """What the UI needs to scope its portfolio selector."""
    from services import portfolio
    scope = user_scope(user)
    every = portfolio.all_clusters(db)
    return {
        "all": scope is None,
        "clusters": every if scope is None else [c for c in every if c in scope],
        # Portfolio APIs (CPAG packs) the user may open: solar / wind / bess.
        "apis": [ns for ns in NAMESPACE_CLUSTERS if scope is None or namespace_open(ns, scope)],
    }
