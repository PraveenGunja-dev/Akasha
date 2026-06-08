from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from database import get_db
import models

router = APIRouter(prefix="/api")

@router.get("/financials")
def get_financials(project_name: Optional[str] = None, db: Session = Depends(get_db)):
    po_query = db.query(func.sum(models.MTPOAmount.net_order_value))
    
    if project_name and project_name != "All":
        mappings = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_name_from_p6 == project_name).all()
        plant_codes = [m.spv_plant_code for m in mappings]
        if plant_codes:
            po_query = po_query.filter(models.MTPOAmount.plant_code.in_(plant_codes))

    total_po_value = po_query.scalar() or 0
    return [
        {
            "quarter": "Total",
            "plannedCapex": 0,
            "actualCapex": total_po_value,
            "cashFlowVariancePercent": 0
        }
    ]

@router.get("/financials/details")
def get_financials_details(project_name: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.MTPOAmount)
    if project_name and project_name != "All":
        mappings = db.query(models.ProjectMapping).filter(models.ProjectMapping.p6_project_name == project_name).all()
        plant_codes = [m.spv_plant_code for m in mappings]
        if plant_codes:
            query = query.filter(models.MTPOAmount.plant_code.in_(plant_codes))
            
    results = query.order_by(models.MTPOAmount.po_quantities_mw.desc()).limit(100).all()
    return results
