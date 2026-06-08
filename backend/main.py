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

# Create tables if not exists
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Akasha Intelligence API",
    description="Cross-Platform Intelligence System Backend",
    version="1.0.0",
    root_path="/akasha"
)

# CORS config to allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to Akasha Intelligence API"}

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
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
    
    # Catch-all route to serve index.html for SPA routing
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Prevent API routes from being swallowed if they somehow fall through
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
            
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
