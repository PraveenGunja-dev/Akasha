from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
import os, shutil, tempfile
from datetime import datetime

from database import get_db
import models

router = APIRouter(
    prefix="/api/statutory",
    tags=["statutory"],
    responses={404: {"description": "Not found"}},
)

def _filter_statutory(query, model, portfolio: Optional[str], phase: Optional[str]):
    if (portfolio and portfolio.lower() != "all portfolios") or (phase and phase.lower() not in ("all", "")):
        query = query.join(models.ProjectMapping, model.project_id == models.ProjectMapping.project_id)
        if portfolio and portfolio.lower() != "all portfolios":
            query = query.filter(models.ProjectMapping.cluster == portfolio)
        normalised = (phase or "all").strip().lower()
        if normalised == "ongoing":
            query = query.filter(models.ProjectMapping.is_commissioned.is_(False))
        elif normalised == "commissioned":
            query = query.filter(models.ProjectMapping.is_commissioned.is_(True))
    return query

@router.get("/compliance")
def get_statutory_compliance(portfolio: Optional[str] = None, phase: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all statutory compliance dashboard summary records."""
    query = db.query(models.StatutoryCompliance)
    return _filter_statutory(query, models.StatutoryCompliance, portfolio, phase).all()

@router.get("/compliance/{project_id}")
def get_project_statutory_compliance(project_id: str, db: Session = Depends(get_db)):
    """Get statutory compliance for a specific project."""
    records = db.query(models.StatutoryCompliance).filter(models.StatutoryCompliance.project_id == project_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="Project not found")
    return records

@router.get("/epc-status")
def get_epc_status(portfolio: Optional[str] = None, phase: Optional[str] = None, db: Session = Depends(get_db)):
    """Get detailed EPC BOCW, CLRA, and GST statuses."""
    query = db.query(models.EPCStatutoryStatus)
    return _filter_statutory(query, models.EPCStatutoryStatus, portfolio, phase).all()

@router.get("/epc-status/{project_id}")
def get_project_epc_status(project_id: str, db: Session = Depends(get_db)):
    """Get detailed EPC statuses for a specific project."""
    records = db.query(models.EPCStatutoryStatus).filter(models.EPCStatutoryStatus.project_id == project_id).all()
    return records

@router.get("/insurance")
def get_insurance_policies(portfolio: Optional[str] = None, phase: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all insurance policies with expiry and premium details."""
    query = db.query(models.InsurancePolicy)
    return _filter_statutory(query, models.InsurancePolicy, portfolio, phase).all()

@router.get("/dashboard-summary")
def get_dashboard_summary(portfolio: Optional[str] = None, phase: Optional[str] = None, db: Session = Depends(get_db)):
    """Get aggregated stats for the Compliance dashboard widget."""
    comp_q = _filter_statutory(db.query(models.StatutoryCompliance), models.StatutoryCompliance, portfolio, phase)
    ins_q = _filter_statutory(db.query(models.InsurancePolicy), models.InsurancePolicy, portfolio, phase)

    total_compliance = comp_q.count()
    
    # Calculate % of documents available
    docs_available = 0
    total_docs = total_compliance * 6 # 6 doc types per project
    
    if total_compliance > 0:
        compliance_records = comp_q.all()
        for r in compliance_records:
            docs_available += sum(1 for status in [
                r.gst_status, r.bocw_status, r.clra_status, 
                r.spcb_status, r.sub_lease_status, r.insurance_status
            ] if status == "Available")
    
    completion_rate = (docs_available / total_docs * 100) if total_docs > 0 else 0
    
    # Expiries or pending renewals
    renewals_pending = ins_q.filter(models.InsurancePolicy.renewal_alert == "Renewal").count()
    
    # CLRA offline count
    clra_pending = comp_q.filter(models.StatutoryCompliance.clra_status == "Not Available").count()

    # BOCW missing count
    bocw_pending = comp_q.filter(models.StatutoryCompliance.bocw_status == "Not Available").count()

    # SPCB missing count
    spcb_pending = comp_q.filter(models.StatutoryCompliance.spcb_status == "Not Available").count()

    return {
        "total_projects_tracked": total_compliance,
        "overall_compliance_percent": round(completion_rate, 1),
        "insurance_renewals_pending": renewals_pending,
        "clra_missing_count": clra_pending,
        "bocw_missing_count": bocw_pending,
        "spcb_missing_count": spcb_pending,
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


UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../Data/uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_statutory_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload an Excel file to refresh statutory / EPC / insurance data.

    The endpoint inspects the filename to decide which tables to refresh:
      - Contains 'statutory' or 'status' → statutory_compliance
      - Contains 'bocw' or 'epc'         → epc_statutory_status
      - Contains 'insurance'             → insurance_policy
      - Otherwise                        → all three tables
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx / .xls files are accepted.")

    # Save uploaded file
    dest = os.path.join(UPLOAD_DIR, file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    fname_lower = file.filename.lower()
    total = 0

    try:
        from scripts.ingest_statutory import (
            load_sap_mapping,
            ingest_statutory_compliance,
            ingest_epc_bocw,
            ingest_insurance,
        )

        sap_map = load_sap_mapping()

        if "statutory" in fname_lower or "status" in fname_lower:
            db.query(models.StatutoryCompliance).delete()
            db.commit()
            total += ingest_statutory_compliance(db, sap_map, filepath=dest)
        elif "bocw" in fname_lower or "epc" in fname_lower:
            db.query(models.EPCStatutoryStatus).delete()
            db.commit()
            total += ingest_epc_bocw(db, sap_map, filepath=dest)
        elif "insurance" in fname_lower:
            db.query(models.InsurancePolicy).delete()
            db.commit()
            total += ingest_insurance(db, sap_map, filepath=dest)
        else:
            # Ambiguous — refresh all three
            db.query(models.StatutoryCompliance).delete()
            db.query(models.EPCStatutoryStatus).delete()
            db.query(models.InsurancePolicy).delete()
            db.commit()
            total += ingest_statutory_compliance(db, sap_map, filepath=dest)
            total += ingest_epc_bocw(db, sap_map, filepath=dest)
            total += ingest_insurance(db, sap_map, filepath=dest)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    return {"status": "ok", "records_imported": total, "filename": file.filename}
