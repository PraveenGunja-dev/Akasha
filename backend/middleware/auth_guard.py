"""Server-side access control for every /api call.

Pure ASGI, like AkashaPathRewriteMiddleware and for the same reason:
BaseHTTPMiddleware buffers the response body and breaks the chat endpoint's
token-by-token streaming. It must sit INSIDE the path rewrite, so it sees
/api/... rather than /akasha/api/....

Order of checks (services/access.py has the rules):
  1. a live session (cookie, or Bearer for API tools)           -> else 401
  2. a pending password change allows only the password screen   -> else 403
  3. the permission a write call needs (ROUTE_POLICIES)          -> else 403
  4. portfolio scope for users without portfolio.all             -> else 403
     (may also pin ?portfolio= to the user's own cluster)

It also keeps the activity trail (akasha_audit_log): every data change that
goes through (who, what, result), every refused call (access.denied) and
calls with a bad API key. Refusals are rate-limited per person and call so a
screen retrying cannot flood the log, and a burst of them from one person is
raised as a critical alert (access.denied_repeated).
"""
import json
import threading
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qsl, unquote, urlencode

from starlette.concurrency import run_in_threadpool

from services import access, portfolio, security


def _api_key(headers: dict) -> str | None:
    """An integration key, sent as `X-API-Key: ak_...` (or `Authorization: Bearer ak_...`)."""
    key = (headers.get("x-api-key") or "").strip()
    if key:
        return key
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and auth[7:].strip().startswith(security.API_KEY_PREFIX):
        return auth[7:].strip()
    return None


def _cookie_token(headers: dict) -> str | None:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and not auth[7:].strip().startswith(security.API_KEY_PREFIX):
        return auth[7:].strip() or None
    raw = headers.get("cookie")
    if not raw:
        return None
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return None
    morsel = jar.get(security.SESSION_COOKIE)
    return morsel.value if morsel else None


def _deny(status: int, detail: str, code: str):
    return status, {"detail": detail, "code": code}, None


def _client_ip(scope, headers: dict) -> str | None:
    fwd = headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else None


# ── Activity trail ───────────────────────────────────────────────────────────
DENY_REPEAT_EVERY = 300              # same person + same call: log a refusal at most every 5 min
BURST_WINDOW, BURST_COUNT = 600, 5   # 5 logged refusals in 10 min -> critical alert
BURST_REALERT = 1800                 # then at most one such alert per person per 30 min
_lock = threading.Lock()
_last_denied: dict = {}
_bursts: dict = {}
_burst_alerted: dict = {}


def _record(action: str, who: dict, target: str, detail: dict, ip: str | None,
            severity: str | None = None) -> None:
    from database import SessionLocal
    db = SessionLocal()
    try:
        security.audit(db, action, target=target, detail=detail, ip=ip, severity=severity,
                       actor_username=who.get("username"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _record_denied(who: dict, method: str, path: str, code: str, ip: str | None) -> None:
    person = who.get("username") or ip or "unknown"
    now = time.monotonic()
    with _lock:
        key = (person, method, path)
        if now - _last_denied.get(key, -1e9) < DENY_REPEAT_EVERY:
            return
        if len(_last_denied) > 5000:     # keep the memory bounded
            _last_denied.clear()
        _last_denied[key] = now
        hits = [t for t in _bursts.get(person, []) if now - t < BURST_WINDOW] + [now]
        _bursts[person] = hits
        burst = len(hits) >= BURST_COUNT and now - _burst_alerted.get(person, -1e9) > BURST_REALERT
        if burst:
            _burst_alerted[person] = now
    if code == "invalid_api_key":
        _record("api_key.invalid", who, who.get("prefix") or "?", {"call": f"{method} {path}"}, ip)
    else:
        _record("access.denied", who, f"{method} {path}", {"code": code, "via": who.get("kind")}, ip)
    if burst:
        _record("access.denied_repeated", who, person,
                {"refused_calls": len(hits), "minutes": BURST_WINDOW // 60}, ip, severity="critical")


def _project_clusters(db, *, project_id: str | None = None, name: str | None = None) -> list:
    """The portfolio of every mapping row for a project id or name (a project
    can have several rows; all must be in scope)."""
    from sqlalchemy import func
    from models import ProjectMapping
    q = db.query(ProjectMapping)
    if project_id is not None:
        q = q.filter(ProjectMapping.project_id == project_id)
    else:
        n = name.strip().lower()
        q = q.filter((func.lower(ProjectMapping.project) == n) | (func.lower(ProjectMapping.project_name_from_p6) == n))
    return [portfolio.mapping_cluster(m) for m in q.all()]


def _v1_clusters(db, ref: str) -> list:
    """Portfolio of a project reference as /api/v1 resolves it (canonical id,
    mapping id, P6 object id or name)."""
    from services import project_identity
    from models import ProjectMapping
    ident = project_identity.resolve(db, unquote(ref))
    if ident is None:
        return []
    row = db.query(ProjectMapping).filter(ProjectMapping.id == ident.mapping_id).first()
    return [portfolio.mapping_cluster(row)] if row else []


def _authorize(method: str, path: str, headers: dict, query: bytes, who: dict):
    """(status, body, new_query) - status 0 means allowed. Fills `who` with
    the caller (kind, id, username) once known, for the activity trail."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        key = _api_key(headers)
        if key:
            # A system reading the integration API: read-only, /api/v1 only.
            api_key = security.resolve_api_key(db, key)
            if not api_key:
                who.update(kind="api_key", prefix=key[:10])
                return _deny(401, "Invalid, expired or revoked API key", "invalid_api_key")
            who.update(kind="api_key", username=f"api-key:{api_key.name}")
            if method != "GET" or not access.API_KEY_PATH.search(path):
                return _deny(403, "API keys can only read /api/v1", "forbidden")
            scope = [c for c in (api_key.portfolios or []) if c] or None
        else:
            user, sess = security.resolve_session(db, _cookie_token(headers))
            if not user:
                return _deny(401, "Your session has ended - please sign in again", "unauthenticated")
            who.update(kind="user", id=user.id, username=user.username)
            view = (headers.get("x-akasha-view") or "").strip()[:120]
            if view and sess is not None and sess.last_view != view:
                sess.last_view = view
                db.commit()
            if user.must_change_password and path not in access.PASSWORD_CHANGE_PATHS:
                return _deny(403, "Set a new password to continue", "password_change_required")

            perms = access.role_permissions(db, user.role)
            need = access.required_permission(method, path)
            if need and need not in perms:
                return _deny(403, "You do not have permission for this action", "forbidden")
            scope = access.user_scope(user)
        if scope is None:
            return 0, None, None

        def in_scope(clusters: list) -> bool:
            return bool(clusters) and all(portfolio.cluster_in(c, scope) for c in clusters)

        for pattern, kind in access.SCOPED_ROUTES:
            m = pattern.search(path)
            if not m:
                continue
            if kind == "open":
                return 0, None, None
            if kind == "namespace":
                if access.namespace_open(m.group("ns"), scope):
                    return 0, None, None
                return _deny(403, "This portfolio is outside your access", "portfolio_forbidden")
            if kind == "mapping":
                from models import ProjectMapping
                row = db.query(ProjectMapping).filter(ProjectMapping.id == int(m.group("mid"))).first()
                if row and portfolio.cluster_in(portfolio.mapping_cluster(row), scope):
                    return 0, None, None
                return _deny(403, "This project is outside your portfolio access", "portfolio_forbidden")
            if kind == "v1project":
                if in_scope(_v1_clusters(db, m.group("pid"))):
                    return 0, None, None
                return _deny(403, "This project is outside your portfolio access", "portfolio_forbidden")
            if kind == "project":
                if in_scope(_project_clusters(db, project_id=unquote(m.group("pid")))):
                    return 0, None, None
                return _deny(403, "This project is outside your portfolio access", "portfolio_forbidden")
            # kind == "portfolio"
            params = parse_qsl(query.decode("latin-1"), keep_blank_values=True)
            name = next((v for k, v in params if k == "project_name" and v.strip() and v != "All"), None)
            if name and not in_scope(_project_clusters(db, name=name)):
                return _deny(403, "This project is outside your portfolio access", "portfolio_forbidden")
            pid = next((v for k, v in params if k == "project_id" and v.strip()), None)
            if pid and path.startswith("/api/v1/") and not in_scope(_v1_clusters(db, pid)):
                return _deny(403, "This project is outside your portfolio access", "portfolio_forbidden")
            asked = portfolio.parse(next((v for k, v in params if k == "portfolio"), None))
            if asked is not None:
                if all(portfolio.cluster_in(c, scope) for c in asked):
                    return 0, None, None
                return _deny(403, "This portfolio is outside your access", "portfolio_forbidden")
            # No portfolio (= every portfolio): narrow the call to the user's own.
            params = [(k, v) for k, v in params if k != "portfolio"] + [("portfolio", ",".join(scope))]
            return 0, None, urlencode(params).encode("latin-1")
        return _deny(403, "Not available with your portfolio access", "portfolio_forbidden")
    finally:
        db.close()


class AuthGuardMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if not path.startswith("/api/") or method == "OPTIONS" or path in access.PUBLIC_PATHS:
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        who: dict = {}
        status, body, new_query = await run_in_threadpool(
            _authorize, method, path, headers, scope.get("query_string", b""), who)
        ip = _client_ip(scope, headers)
        if (status == 403 and body["code"] != "password_change_required") or \
                (status == 401 and body["code"] == "invalid_api_key"):
            query = scope.get("query_string", b"").decode("latin-1")
            await run_in_threadpool(_record_denied, who, method,
                                    f"{path}?{unquote(query)[:200]}" if query else path, body["code"], ip)
        if status:
            payload = json.dumps(body).encode()
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(payload)).encode()),
                                    (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": payload})
            return
        if new_query is not None:
            scope = dict(scope, query_string=new_query)
        action = access.audited_write(method, path)
        if not action:
            return await self.app(scope, receive, send)

        # A change: let it run, then record who made it and how it ended.
        result = {"status": 500}
        started = time.monotonic()

        async def send_capture(message):
            if message["type"] == "http.response.start":
                result["status"] = message["status"]
            await send(message)
        try:
            await self.app(scope, receive, send_capture)
        finally:
            code = result["status"]
            detail = {"method": method, "status": code, "ok": code < 400,
                      "ms": int((time.monotonic() - started) * 1000)}
            query = scope.get("query_string", b"").decode("latin-1")
            if query:
                detail["query"] = query[:300]
            await run_in_threadpool(_record, action, who, path, detail, ip,
                                    "warning" if code >= 500 else None)
