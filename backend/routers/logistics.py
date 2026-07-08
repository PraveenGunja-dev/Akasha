from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional
from database import get_db
import models

router = APIRouter(prefix="/api")

@router.get("/logistics")
def get_logistics(project_name: Optional[str] = None, db: Session = Depends(get_db)):
    inv_query = db.query(func.sum(models.MTInventory.quantity_inv))
    transit_query = db.query(func.sum(models.MTPOAmount.still_to_deliver_qty))
    
    if project_name and project_name != "All":
        mappings = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_name_from_p6 == project_name).all()
        wbs_exacts = [
            str(m.module_wbs).strip()
            for m in mappings
            if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', '')
        ]
        if wbs_exacts:
            inv_conditions = [models.MTInventory.wbs_element == p for p in wbs_exacts]
            transit_conditions = [models.MTPOAmount.wbs_element == p for p in wbs_exacts]
            inv_query = inv_query.filter(or_(*inv_conditions))
            transit_query = transit_query.filter(or_(*transit_conditions))
        else:
            return [
                { "category": "Delivered", "count": 0, "color": "#0B74B0" },
                { "category": "In Transit", "count": 0, "color": "#75479C" }
            ]
            
    delivered = inv_query.scalar() or 0
    in_transit = transit_query.scalar() or 0
        
    return [
        { "category": "Delivered", "count": round(delivered, 2), "color": "#0B74B0" },
        { "category": "In Transit", "count": round(in_transit, 2), "color": "#75479C" }
    ]

@router.get("/logistics/details")
def get_logistics_details(project_name: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.MTPOAmount).filter(models.MTPOAmount.still_to_deliver_qty > 0)
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
            
    results = query.order_by(models.MTPOAmount.still_to_deliver_qty.desc()).limit(100).all()
    return results
