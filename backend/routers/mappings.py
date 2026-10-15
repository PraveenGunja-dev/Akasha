from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import models
from database import get_db
from routers.auth import current_user

router = APIRouter(prefix="/api/mappings", tags=["mappings"])

# Schemas
class ProjectMappingBase(BaseModel):
    project: Optional[str] = None
    spv_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name_from_p6: Optional[str] = None
    plot_no: Optional[str] = None
    category: Optional[str] = None
    mms_type: Optional[str] = None
    capacity_mwac: Optional[float] = None
    ol: Optional[str] = None
    capacity_mwdc: Optional[float] = None
    spv_plant_code: Optional[str] = None
    agel: Optional[str] = None
    module_wbs: Optional[str] = None
    age6l: Optional[str] = None
    cluster: Optional[str] = None
    not_allocated: Optional[str] = None
    source_of_origin: Optional[str] = None
    priority: Optional[str] = None
    # Optional, not bool: the column is nullable and 63 of 87 rows are
    # actually NULL, not False. A non-optional bool here made every read AND
    # write of those rows 500 with a Pydantic validation error — including
    # the existing SCOD save and the LTA save this schema now also carries,
    # discovered while wiring the latter up (2026-09-25).
    is_commissioned: Optional[bool] = False
    manual_scod: Optional[datetime] = None
    # The LTA date: read from the connectivity export where it exists, but
    # several projects have no ECOD there at all (see MANUAL_LTA in
    # scripts/update_lta_from_123.py), so planning needs to set or correct it
    # by hand from the Ordering Schedule table.
    lta_date: Optional[datetime] = None
    is_tracked: Optional[bool] = True

class ProjectMappingCreate(ProjectMappingBase):
    pass

class ProjectMappingUpdate(ProjectMappingBase):
    # Why the LTA / SCOD is being changed - required when either changes; it
    # is kept in the date history and sent in the schedule-change email.
    remarks: Optional[str] = None

class ProjectMappingResponse(ProjectMappingBase):
    id: int

    class Config:
        from_attributes = True

# Endpoints
@router.get("/", response_model=List[ProjectMappingResponse])
def get_mappings(db: Session = Depends(get_db)):
    """Retrieve all project mappings"""
    mappings = db.query(models.ProjectMapping).all()
    return mappings
import json

@router.get("/unmapped/options")
def get_unmapped_options(db: Session = Depends(get_db)):
    """Retrieve lists of available transmission projects and P6 projects that are NOT yet mapped."""
    # Mapped Transmission Names
    mapped_transmission = db.query(models.ProjectMapping.project).filter(models.ProjectMapping.project.isnot(None)).all()
    mapped_transmission_names = {t[0] for t in mapped_transmission if t[0]}
    
    # All Transmission Names
    all_transmission_names = set()
    tc_entries = db.query(models.TcProjectEntry.project).filter(models.TcProjectEntry.project.isnot(None)).distinct().all()
    for t in tc_entries:
        if t[0]: all_transmission_names.add(t[0])
        
    tc_edges = db.query(models.TcNetworkEdge.projects).filter(models.TcNetworkEdge.projects.isnot(None)).all()
    for e in tc_edges:
        if e[0]:
            try:
                parsed = json.loads(e[0])
                if isinstance(parsed, dict) and "projects" in parsed:
                    for p in parsed["projects"]:
                        if p: all_transmission_names.add(p)
                elif isinstance(parsed, list):
                    for p in parsed:
                        if p: all_transmission_names.add(p)
            except:
                pass
                
    unmapped_transmission = list(all_transmission_names - mapped_transmission_names)
    unmapped_transmission.sort()
    
    # Mapped P6 Names
    mapped_p6 = db.query(models.ProjectMapping.project_name_from_p6).filter(models.ProjectMapping.project_name_from_p6.isnot(None)).all()
    mapped_p6_names = {p[0] for p in mapped_p6 if p[0]}
    
    # All P6 Names
    p6_projects = db.query(models.P6Project.name).filter(models.P6Project.name.isnot(None)).distinct().all()
    all_p6_names = {p[0] for p in p6_projects if p[0]}
    
    unmapped_p6 = list(all_p6_names - mapped_p6_names)
    unmapped_p6.sort()
    
    return {
        "unmapped_transmission": unmapped_transmission,
        "unmapped_p6": unmapped_p6
    }
@router.get("/{mapping_id}", response_model=ProjectMappingResponse)
def get_mapping(mapping_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific mapping by ID"""
    mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return mapping

@router.post("/", response_model=ProjectMappingResponse)
def create_mapping(mapping: ProjectMappingCreate, db: Session = Depends(get_db)):
    """Create a new project mapping"""
    db_mapping = models.ProjectMapping(**mapping.model_dump())
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)
    return db_mapping

@router.put("/{mapping_id}", response_model=ProjectMappingResponse)
def update_mapping(mapping_id: int, mapping: ProjectMappingUpdate, background: BackgroundTasks,
                   db: Session = Depends(get_db), user: models.AkashaUser = Depends(current_user)):
    """Update an existing project mapping. A change to LTA or SCOD needs a
    reason; it is kept in the date history (services/date_history.py) with
    who made it, and the schedule-change email goes out straight away."""
    db_mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == mapping_id).first()
    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    update_data = mapping.model_dump(exclude_unset=True)
    remarks = (update_data.pop("remarks", None) or "").strip()
    from services import date_history
    label = {"lta": "LTA", "scod": "SCOD"}
    changing = [f for k, f in (("lta_date", "lta"), ("manual_scod", "scod"))
                if k in update_data and date_history._day(getattr(db_mapping, k)) != date_history._day(update_data[k])]
    if changing and len(remarks) < 5:
        raise HTTPException(status_code=400,
                            detail=f"Give the reason for changing the {' and '.join(label[f] for f in changing)} (at least 5 characters)")
    changed = False
    for key, field in (("lta_date", "lta"), ("manual_scod", "scod")):
        if key in update_data:
            changed |= date_history.record(db, db_mapping, field, getattr(db_mapping, key), update_data[key], "manual",
                                           getattr(user, "display_name", None) or getattr(user, "username", None),
                                           remarks[:1000])
    for key, value in update_data.items():
        setattr(db_mapping, key, value)

    db.commit()
    db.refresh(db_mapping)
    if changed:
        from services.email_notify import engine as email_engine
        background.add_task(email_engine.notify_date_changes, f"edit by {user.username}")
    return db_mapping

@router.delete("/{mapping_id}")
def delete_mapping(mapping_id: int, db: Session = Depends(get_db), user: models.AkashaUser = Depends(current_user)):
    """Delete a project mapping - the project leaves the Ordering Schedule and
    every dashboard. Its open module-order approvals are cancelled (releasing
    any freeze) and its open email alerts closed, so nothing is left waiting
    on a project that is gone; their history stays."""
    db_mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == mapping_id).first()
    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    from datetime import datetime
    from services import security
    who = getattr(user, "display_name", None) or getattr(user, "username", None)
    reason = f"Project removed from Akasha (mapping deleted by {who})"
    cancelled = 0
    for a in db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.mapping_id == mapping_id,
                                                          models.ModuleOrderApproval.status.in_(["pending", "approved"])).all():
        a.status = "cancelled"
        db.add(models.ModuleOrderApprovalEvent(approval_id=a.id, at=datetime.utcnow(), kind="cancelled", actor=who, detail=reason))
        cancelled += 1
    closed = 0
    still_mapped = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == db_mapping.project_id,
                                                          models.ProjectMapping.id != mapping_id).first()
    if db_mapping.project_id and not still_mapped:
        from services.email_notify import alerts as email_alerts
        for al in db.query(models.EmailAlert).filter(models.EmailAlert.project_id == db_mapping.project_id,
                                                      models.EmailAlert.status == "open").all():
            email_alerts.resolve(db, al, reason, who or "Akasha")
            closed += 1
    security.audit(db, "mapping.deleted", actor=user, target=(db_mapping.project if (db_mapping.project_id or "") in (db_mapping.project or "")
                           else f"{db_mapping.project} ({db_mapping.project_id})"),
                   detail={"mapping_id": mapping_id, "approvals_cancelled": cancelled, "alerts_closed": closed})
    db.delete(db_mapping)
    db.commit()
    return {"message": "Mapping deleted successfully", "approvals_cancelled": cancelled, "alerts_closed": closed}
