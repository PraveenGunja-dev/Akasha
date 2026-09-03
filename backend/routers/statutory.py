from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any

from database import get_db
import models

router = APIRouter(
    prefix="/api/statutory",
    tags=["statutory"],
    responses={404: {"description": "Not found"}},
)

@router.get("/compliance")
def get_statutory_compliance(db: Session = Depends(get_db)):
    """Get all statutory compliance dashboard summary records."""
    records = db.query(models.StatutoryCompliance).all()
    return records

@router.get("/compliance/{project_id}")
def get_project_statutory_compliance(project_id: str, db: Session = Depends(get_db)):
    """Get statutory compliance for a specific project."""
    records = db.query(models.StatutoryCompliance).filter(models.StatutoryCompliance.project_id == project_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="Project not found")
    return records

@router.get("/epc-status")
def get_epc_status(db: Session = Depends(get_db)):
    """Get detailed EPC BOCW, CLRA, and GST statuses."""
    records = db.query(models.EPCStatutoryStatus).all()
    return records

@router.get("/epc-status/{project_id}")
def get_project_epc_status(project_id: str, db: Session = Depends(get_db)):
    """Get detailed EPC statuses for a specific project."""
    records = db.query(models.EPCStatutoryStatus).filter(models.EPCStatutoryStatus.project_id == project_id).all()
    return records

@router.get("/insurance")
def get_insurance_policies(db: Session = Depends(get_db)):
    """Get all insurance policies with expiry and premium details."""
    records = db.query(models.InsurancePolicy).all()
    return records

@router.get("/dashboard-summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """Get aggregated stats for the Compliance dashboard widget."""
    total_compliance = db.query(func.count(models.StatutoryCompliance.id)).scalar()
    
    # Calculate % of documents available
    docs_available = 0
    total_docs = total_compliance * 6 # 6 doc types per project
    
    if total_compliance > 0:
        compliance_records = db.query(models.StatutoryCompliance).all()
        for r in compliance_records:
            docs_available += sum(1 for status in [
                r.gst_status, r.bocw_status, r.clra_status, 
                r.spcb_status, r.sub_lease_status, r.insurance_status
            ] if status == "Available")
    
    completion_rate = (docs_available / total_docs * 100) if total_docs > 0 else 0
    
    # Expiries or pending renewals
    renewals_pending = db.query(func.count(models.InsurancePolicy.id)).filter(
        models.InsurancePolicy.renewal_alert == "Renewal"
    ).scalar()
    
    # CLRA offline count
    clra_pending = db.query(func.count(models.StatutoryCompliance.id)).filter(
        models.StatutoryCompliance.clra_status == "Not Available"
    ).scalar()
    
    return {
        "total_projects_tracked": total_compliance,
        "overall_compliance_percent": round(completion_rate, 1),
        "insurance_renewals_pending": renewals_pending,
        "clra_missing_count": clra_pending
    }

@router.get("/p6-approvals/{project_id}")
def get_p6_approvals(project_id: str, db: Session = Depends(get_db)):
    """Get statutory-relevant P6 activities (colored rows in PDF) for a project."""
    
    # Join via p6_project to get activities
    p6_project = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    
    if not p6_project:
        return []
        
    activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6_project.p6_object_id
    ).all()
    
    # Filter statutory relevant ones (Main CEO-level milestones only)
    statutory_patterns = [
        "CEA Compliance", "First Time Charging", "COD"
    ]
    
    filtered_activities = []
    for act in activities:
        for pat in statutory_patterns:
            if pat.lower() in (act.name or "").lower():
                filtered_activities.append(act)
                break
                
    return filtered_activities
