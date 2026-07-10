from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional
from database import get_db
import models
import time

_FIN_CACHE = {}
_FIN_TTL = 300  # 5 minutes

router = APIRouter(prefix="/api")

@router.get("/financials")
def get_financials(project_name: Optional[str] = None, portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"fin_{project_name or 'All'}_{portfolio or 'All'}"
    if not nocache and cache_key in _FIN_CACHE:
        entry = _FIN_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _FIN_TTL:
            return entry["data"]

    po_query = db.query(func.sum(models.MTPOAmount.net_order_value))
    
    # 1. Global Portfolio Filter
    map_query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        map_query = map_query.filter(
            (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
            (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
        )
    
    # 2. Local Project Filter
    if project_name and project_name != "All":
        map_query = map_query.filter(models.ProjectMapping.project_name_from_p6 == project_name)
        
    mappings = map_query.all()
    
    if (project_name and project_name != "All") or (portfolio and portfolio.lower() != "all portfolios"):
        wbs_exacts = [
            str(m.module_wbs).strip()
            for m in mappings
            if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', '')
        ]
        if wbs_exacts:
            wbs_conditions = [models.MTPOAmount.wbs_element == p for p in wbs_exacts]
            po_query = po_query.filter(or_(*wbs_conditions))
        else:
            return [{"quarter": "Total", "plannedCapex": 0, "actualCapex": 0, "cashFlowVariancePercent": 0}]

    total_po_value = po_query.scalar() or 0
    # Convert from raw INR to Crores (1 Cr = 10,000,000)
    total_po_value_cr = round(total_po_value / 10000000, 2)
    result = [
        {
            "quarter": "Total",
            "plannedCapex": 0,
            "actualCapex": total_po_value_cr,
            "cashFlowVariancePercent": 0
        }
    ]
    _FIN_CACHE[cache_key] = {"data": result, "timestamp": time.time()}
    return result

@router.get("/financials/details")
def get_financials_details(project_name: Optional[str] = None, portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"fin_det_{project_name or 'All'}_{portfolio or 'All'}"
    if not nocache and cache_key in _FIN_CACHE:
        entry = _FIN_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _FIN_TTL:
            return entry["data"]

    query = db.query(models.MTPOAmount)
    
    map_query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        map_query = map_query.filter(
            (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
            (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
        )
            
    if project_name and project_name != "All":
        map_query = map_query.filter(models.ProjectMapping.project_name_from_p6 == project_name)
        
    mappings = map_query.all()
    
    if (project_name and project_name != "All") or (portfolio and portfolio.lower() != "all portfolios"):
        wbs_exacts = [
            str(m.module_wbs).strip()
            for m in mappings
            if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', '')
        ]
        if wbs_exacts:
            wbs_conditions = [models.MTPOAmount.wbs_element == p for p in wbs_exacts]
            query = query.filter(or_(*wbs_conditions))
        else:
            return []
            
    results = query.order_by(models.MTPOAmount.net_order_value.desc()).limit(100).all()
    _FIN_CACHE[cache_key] = {"data": results, "timestamp": time.time()}
    return results

