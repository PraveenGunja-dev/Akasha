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

_FIN_CACHE = {}
_FIN_TTL = 300  # 5 minutes


def clear_financial_cache():
    """Clear financial responses derived from SAP data."""
    _FIN_CACHE.clear()

router = APIRouter(prefix="/api")

@router.get("/financials")
def get_financials(project_name: Optional[str] = None, portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"fin_{project_name or 'All'}_{portfolio or 'All'}"
    cache_version = cache_version_token(db, ("SAP", "Mapping"))
    if not nocache and cache_key in _FIN_CACHE:
        entry = _FIN_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _FIN_TTL and entry.get("version") == cache_version:
            return entry["data"]

    mappings = _scoped_mappings(db, project_name, portfolio)
    scoped = (project_name and project_name != "All") or has_portfolio_filter(portfolio)
    evidence = None
    total_po_value = 0.0

    if scoped:
        project_ids = list(dict.fromkeys(mapping.project_id for mapping in mappings if mapping.project_id))
        sap_results = list(get_sap_projects_data(db, project_ids).values())
        total_po_value = sum(result["totals"]["purchase_orders"]["order_value"] for result in sap_results)
        evidence = {
            "source_table": "mt_poamount",
            "project_scopes": [result["scope"] for result in sap_results],
            "freshness": [result["freshness"]["mt_poamount"] for result in sap_results],
        }
    else:
        total_po_value = db.query(func.sum(models.MTPOAmount.net_order_value_inr)).scalar() or 0

    # Convert from raw INR to Crores (1 Cr = 10,000,000)
    total_po_value_cr = round(total_po_value / 10000000, 2)
    result = [
        {
            "quarter": "Total",
            "plannedCapex": 0,
            "actualCapex": total_po_value_cr,
            "cashFlowVariancePercent": 0,
            "currency": "INR",
            "scale": "crore",
            "evidence": evidence,
        }
    ]
    _FIN_CACHE[cache_key] = {"data": result, "timestamp": time.time(), "version": cache_version}
    return result

@router.get("/financials/details")
def get_financials_details(project_name: Optional[str] = None, portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"fin_det_{project_name or 'All'}_{portfolio or 'All'}"
    cache_version = cache_version_token(db, ("SAP", "Mapping"))
    if not nocache and cache_key in _FIN_CACHE:
        entry = _FIN_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _FIN_TTL and entry.get("version") == cache_version:
            return entry["data"]

    mappings = _scoped_mappings(db, project_name, portfolio)
    scoped = (project_name and project_name != "All") or has_portfolio_filter(portfolio)
    if scoped:
        records = {}
        project_ids = list(dict.fromkeys(mapping.project_id for mapping in mappings if mapping.project_id))
        for result in get_sap_projects_data(db, project_ids).values():
            for record in result["purchase_orders"]:
                records[record.id] = record
        results = sorted(records.values(), key=lambda row: row.net_order_value_inr or 0, reverse=True)[:100]
    else:
        results = db.query(models.MTPOAmount).order_by(models.MTPOAmount.net_order_value_inr.desc()).limit(100).all()
    _FIN_CACHE[cache_key] = {"data": results, "timestamp": time.time(), "version": cache_version}
    return results

