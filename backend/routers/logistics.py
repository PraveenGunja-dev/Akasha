from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional
from database import get_db
import models
import time
from services.project_catalog_service import AmbiguousProjectError, ProjectCatalogService, has_portfolio_filter
from services.sap_project_data_service import get_sap_projects_data
from services.freshness_service import cache_version_token


def _scoped_mappings(db: Session, project_name: str | None, portfolio: str | None):
    try:
        return ProjectCatalogService.list_scoped_mappings(
            db,
            portfolio=portfolio,
            project_name=project_name,
        )
    except AmbiguousProjectError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

_LOG_CACHE = {}
_LOG_TTL = 300  # 5 minutes


def clear_logistics_cache():
    """Clear logistics responses derived from SAP data."""
    _LOG_CACHE.clear()

router = APIRouter(prefix="/api")

@router.get("/logistics")
def get_logistics(project_name: Optional[str] = None, portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"log_{project_name or 'All'}_{portfolio or 'All'}"
    cache_version = cache_version_token(db, ("SAP", "Mapping"))
    if not nocache and cache_key in _LOG_CACHE:
        entry = _LOG_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _LOG_TTL and entry.get("version") == cache_version:
            return entry["data"]

    mappings = _scoped_mappings(db, project_name, portfolio)
    scoped = (project_name and project_name != "All") or has_portfolio_filter(portfolio)
    if scoped:
        project_ids = list(dict.fromkeys(mapping.project_id for mapping in mappings if mapping.project_id))
        sap_results = list(get_sap_projects_data(db, project_ids).values())
        delivered = sum(result["totals"]["inventory"]["quantity"] for result in sap_results)
        in_transit = sum(result["totals"]["purchase_orders"]["pending_quantity"] for result in sap_results)
    else:
        delivered = db.query(func.sum(models.MTInventory.quantity_inv)).scalar() or 0
        in_transit = db.query(func.sum(models.MTPOAmount.still_to_deliver_qty)).scalar() or 0
        
    result = [
        { "category": "Delivered", "count": round(delivered, 2), "color": "#0B74B0" },
        { "category": "In Transit", "count": round(in_transit, 2), "color": "#75479C" }
    ]
    _LOG_CACHE[cache_key] = {"data": result, "timestamp": time.time(), "version": cache_version}
    return result

@router.get("/logistics/details")
def get_logistics_details(project_name: Optional[str] = None, portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"log_det_{project_name or 'All'}_{portfolio or 'All'}"
    cache_version = cache_version_token(db, ("SAP", "Mapping"))
    if not nocache and cache_key in _LOG_CACHE:
        entry = _LOG_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _LOG_TTL and entry.get("version") == cache_version:
            return entry["data"]

    mappings = _scoped_mappings(db, project_name, portfolio)
    scoped = (project_name and project_name != "All") or has_portfolio_filter(portfolio)
    if scoped:
        records = {}
        project_ids = list(dict.fromkeys(mapping.project_id for mapping in mappings if mapping.project_id))
        for result in get_sap_projects_data(db, project_ids).values():
            for record in result["purchase_orders"]:
                if (record.still_to_deliver_qty or 0) > 0:
                    records[record.id] = record
        results = sorted(records.values(), key=lambda row: row.still_to_deliver_qty or 0, reverse=True)[:100]
    else:
        results = db.query(models.MTPOAmount).filter(
            models.MTPOAmount.still_to_deliver_qty > 0
        ).order_by(models.MTPOAmount.still_to_deliver_qty.desc()).limit(100).all()
    _LOG_CACHE[cache_key] = {"data": results, "timestamp": time.time(), "version": cache_version}
    return results
