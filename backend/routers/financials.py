from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional
from database import get_db
import models

router = APIRouter(prefix="/api")

@router.get("/financials")
def get_financials(project_name: Optional[str] = None, db: Session = Depends(get_db)):
    po_query = db.query(func.sum(models.MTPOAmount.net_order_value))
    
    if project_name and project_name != "All":
        mappings = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_name_from_p6 == project_name).all()
        wbs_exacts = [
            str(m.module_wbs).strip()
            for m in mappings
            if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', '')
        ]
        if wbs_exacts:
            wbs_conditions = [models.MTPOAmount.wbs_element == p for p in wbs_exacts]
            po_query = po_query.filter(or_(*wbs_conditions))
        else:
            # No valid WBS found for this project
            return [{"quarter": "Total", "plannedCapex": 0, "actualCapex": 0, "cashFlowVariancePercent": 0}]

    total_po_value = po_query.scalar() or 0
    # Convert from raw INR to Crores (1 Cr = 10,000,000)
    total_po_value_cr = round(total_po_value / 10000000, 2)
    return [
        {
            "quarter": "Total",
            "plannedCapex": 0,
            "actualCapex": total_po_value_cr,
            "cashFlowVariancePercent": 0
        }
    ]

@router.get("/financials/details")
def get_financials_details(project_name: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.MTPOAmount)
    if project_name and project_name != "All":
        mappings = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_name_from_p6 == project_name).all()
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
    return results

