from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from database import get_db
import models

router = APIRouter(prefix="/api")

@router.get("/logistics")
def get_logistics(project_name: Optional[str] = None, db: Session = Depends(get_db)):
    inv_query = db.query(func.sum(models.MTInventory.quantity_mw))
    transit_query = db.query(func.sum(models.MTInTransit.quantity_mw))
    
    if project_name and project_name != "All":
        mappings = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_name_from_p6 == project_name).all()
        plant_codes = [m.spv_plant_code for m in mappings]
        if plant_codes:
            inv_query = inv_query.filter(models.MTInventory.plant_code.in_(plant_codes))
            transit_query = transit_query.filter(models.MTInTransit.plant_code.in_(plant_codes))
            
    delivered = inv_query.scalar() or 0
    in_transit = transit_query.scalar() or 0
        
    return [
        { "category": "Delivered", "count": round(delivered, 2), "color": "#0B74B0" },
        { "category": "In Transit", "count": round(in_transit, 2), "color": "#75479C" }
    ]

@router.get("/logistics/details")
def get_logistics_details(project_name: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.MTInTransit)
    if project_name and project_name != "All":
        mappings = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_name_from_p6 == project_name).all()
        plant_codes = [m.spv_plant_code for m in mappings]
        if plant_codes:
            query = query.filter(models.MTInTransit.plant_code.in_(plant_codes))
            
    results = query.order_by(models.MTInTransit.quantity_mw.desc()).limit(100).all()
    return results
