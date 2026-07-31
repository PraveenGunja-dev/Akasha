from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import os
from security import get_auth_mode, require_ceo_or_pmag

# Import Routers
from routers import projects, logistics, financials, ai, sync, tc_router, dashboard, mappings, auth, chat_feedback, chat_sessions, pmag, notifications, quality, reports_mvp, risk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Corporate proxy trust must be configured with REQUESTS_CA_BUNDLE/SSL_CERT_FILE.
# TLS verification is never disabled process-wide.

@asynccontextmanager
async def lifespan(_app: FastAPI):
    from engine.graph import chat_graph_service
    chat_graph_service.startup()
    try:
        yield
    finally:
        chat_graph_service.shutdown()

app = FastAPI(
    title="Akasha Intelligence API",
    description="Cross-Platform Intelligence System Backend",
    version="1.0.0",
    root_path="/akasha",
    lifespan=lifespan,
)
if get_auth_mode() == "development":
    logger.warning("AKASHA DEVELOPMENT AUTH IS ENABLED: any browser user can select CEO or PMAG access.")

# Rewrite /akasha/api -> /api. Implemented as PURE ASGI middleware, NOT @app.middleware
# (BaseHTTPMiddleware): BaseHTTPMiddleware buffers the whole response body before sending,
# which broke token-by-token SSE streaming in the chat endpoint. Pure ASGI passes the
# stream straight through.
class AkashaPathRewriteMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path.startswith("/akasha/api/"):
                new_path = path.replace("/akasha/api/", "/api/", 1)
                scope["path"] = new_path
                if scope.get("raw_path"):
                    scope["raw_path"] = new_path.encode("utf-8")
        await self.app(scope, receive, send)

app.add_middleware(AkashaPathRewriteMiddleware)

# Bearer-token API access does not require credentialed wildcard CORS.
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "AKASHA_ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:3510",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Akasha-Dev-User", "X-Akasha-Dev-Role"],
    expose_headers=["X-Request-ID", "X-Session-ID"],
)


# Include Routers
protected_api = [Depends(require_ceo_or_pmag)]
app.include_router(auth.router)
app.include_router(chat_sessions.router, dependencies=protected_api)
app.include_router(chat_feedback.router, dependencies=protected_api)
app.include_router(projects.router, dependencies=protected_api)
app.include_router(logistics.router, dependencies=protected_api)
app.include_router(financials.router, dependencies=protected_api)
app.include_router(ai.router, dependencies=protected_api)
app.include_router(sync.router, dependencies=protected_api)
app.include_router(tc_router.router, dependencies=protected_api)
app.include_router(dashboard.router, dependencies=protected_api)
app.include_router(mappings.router, dependencies=protected_api)
app.include_router(pmag.router, dependencies=protected_api)
app.include_router(notifications.router, dependencies=protected_api)
app.include_router(quality.router, dependencies=protected_api)
app.include_router(reports_mvp.router, dependencies=protected_api)
app.include_router(risk.router, dependencies=protected_api)

# Mount Frontend static files
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    
    # Catch-all route to serve index.html and assets for SPA routing
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # If accessed locally without a proxy, strip the akasha prefix
        if full_path.startswith("akasha/"):
            full_path = full_path[len("akasha/"):]
        elif full_path == "akasha":
            full_path = ""
            
        # Prevent API routes from being swallowed if they somehow fall through
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
            
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
            
        return FileResponse(os.path.join(frontend_dist, "index.html"))
