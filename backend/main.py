from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import logging
import models
import os
from database import engine

# Import Routers
from routers import projects, logistics, financials, ai, sync, tc_router, dashboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FIX FOR CORPORATE PROXIES (SSL CERTIFICATE VERIFY FAILED) ---
import urllib3
import requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
old_request = requests.Session.request
def new_request(self, method, url, **kwargs):
    kwargs['verify'] = False
    return old_request(self, method, url, **kwargs)
requests.Session.request = new_request
# ----------------------------------------------------------------

# Create tables if not exists
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Akasha Intelligence API",
    description="Cross-Platform Intelligence System Backend",
    version="1.0.0",
    root_path="/akasha"
)

# Middleware to rewrite /akasha/api to /api for local testing
from fastapi import Request
@app.middleware("http")
async def rewrite_akasha_api(request: Request, call_next):
    if request.url.path.startswith("/akasha/api/"):
        request.scope["path"] = request.url.path.replace("/akasha/api/", "/api/", 1)
    return await call_next(request)

# CORS config to allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include Routers
app.include_router(projects.router)
app.include_router(logistics.router)
app.include_router(financials.router)
app.include_router(ai.router)
app.include_router(sync.router)
app.include_router(tc_router.router)
app.include_router(dashboard.router)

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
