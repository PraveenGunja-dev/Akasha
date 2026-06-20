from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import models
from database import get_db

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

class ProjectMappingCreate(ProjectMappingBase):
    pass

class ProjectMappingUpdate(ProjectMappingBase):
    pass

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
def update_mapping(mapping_id: int, mapping: ProjectMappingUpdate, db: Session = Depends(get_db)):
    """Update an existing project mapping"""
    db_mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == mapping_id).first()
    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    update_data = mapping.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_mapping, key, value)
        
    db.commit()
    db.refresh(db_mapping)
    return db_mapping

@router.delete("/{mapping_id}")
def delete_mapping(mapping_id: int, db: Session = Depends(get_db)):
    """Delete a project mapping"""
    db_mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == mapping_id).first()
    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
        
    db.delete(db_mapping)
    db.commit()
    return {"message": "Mapping deleted successfully"}
