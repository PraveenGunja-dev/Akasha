from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
import models
from services.project_service import calculate_project_360_metrics, get_project_360_detail

router = APIRouter(prefix="/api")

@router.get("/master-projects")
def get_master_projects(db: Session = Depends(get_db)):
    projects = db.query(models.ProjectMapping.project_name_from_p6).distinct().all()
    # Filter out None values and flatten list
    return {"projects": [p[0] for p in projects if p[0]]}

@router.get("/summary")
def get_project_summary(project_name: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.P6Project)
    if project_name and project_name != "All":
        mappings = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_name_from_p6 == project_name).all()
        p6_ids = [m.project_id for m in mappings]
        if p6_ids:
            query = query.filter(models.P6Project.project_id.in_(p6_ids))
        else:
            query = query.filter(models.P6Project.name.ilike(f"%{project_name}%"))
            
    stored_projects = query.all()
    
    result = []
    for p in stored_projects:
        item = {column.name: getattr(p, column.name) for column in p.__table__.columns}
        # Fallback for variance if None
        variance = p.finish_date_variance
        if variance is None and p.baseline_finish_date:
            compare_date = p.scheduled_finish_date or p.finish_date
            if compare_date:
                variance = (p.baseline_finish_date - compare_date).days

        # Inject camelCase properties expected by the frontend
        item["finishDateVariance"] = variance
        item["finish_date_variance"] = variance
        item["plannedDuration"] = p.planned_duration
        item["actualDuration"] = p.actual_duration
        item["actualTotalCost"] = p.actual_total_cost
        # Fallback for SPI if None
        spi = p.schedule_performance_index
        if spi is None and p.actual_duration and p.planned_duration:
            spi = p.planned_duration / p.actual_duration if p.actual_duration > 0 else 1.0

        item["schedulePerformanceIndex"] = spi
        item["schedule_performance_index"] = spi
        item["durationVariance"] = p.duration_variance
        item["plannedCost"] = p.planned_cost
        item["currentBudget"] = p.current_budget
        item["costVariance"] = p.total_cost_variance
        result.append(item)
        
    return result

@router.get("/project-360")
def get_project_360(db: Session = Depends(get_db)):
    return calculate_project_360_metrics(db)

@router.get("/project-360/{project_id}/detail")
def get_project_360_detail_endpoint(project_id: str, db: Session = Depends(get_db)):
    result = get_project_360_detail(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found in mapping")
    return result

@router.get("/p6/baselines")
def get_baselines(project_object_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(models.P6BaselineProject)
    if project_object_id:
        query = query.filter(models.P6BaselineProject.original_project_object_id == project_object_id)
    baselines = query.all()
    if not baselines:
        return {"message": "No baselines found. Run /api/p6/sync first.", "data": []}
    
    return [
        {
            "objectId": b.p6_object_id,
            "originalProjectObjectId": b.original_project_object_id,
            "baselineTypeName": b.baseline_type_name,
            "name": b.name,
            "plannedStartDate": b.planned_start_date.isoformat() if b.planned_start_date else None,
            "finishDate": b.finish_date.isoformat() if b.finish_date else None,
            "plannedDuration": b.planned_duration,
            "plannedCost": b.planned_cost,
            "actualTotalCost": b.actual_total_cost,
            "baselineTotalCost": b.baseline_total_cost,
            "activityCount": b.activity_count,
            "completedActivities": b.completed_activity_count,
            "inProgressActivities": b.in_progress_activity_count,
            "notStartedActivities": b.not_started_activity_count,
            "currentBudget": b.current_budget,
            "originalBudget": b.original_budget,
            "status": b.status,
            "lastSyncedAt": b.last_synced_at.isoformat() if b.last_synced_at else None,
        }
        for b in baselines
    ]

@router.get("/p6/projects/detail")
def get_project_detail(project_id: str, db: Session = Depends(get_db)):
    project = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    baselines = db.query(models.P6BaselineProject).filter(
        models.P6BaselineProject.original_project_object_id == project.p6_object_id
    ).all()

    return {
        "project": {
            "id": project.project_id,
            "name": project.name,
            "status": project.status,
            "p6ObjectId": project.p6_object_id,
            "startDate": project.start_date.isoformat() if project.start_date else None,
            "finishDate": project.finish_date.isoformat() if project.finish_date else None,
            "plannedStartDate": project.planned_start_date.isoformat() if project.planned_start_date else None,
            "scheduledFinishDate": project.scheduled_finish_date.isoformat() if project.scheduled_finish_date else None,
            "dataDate": project.data_date.isoformat() if project.data_date else None,
            "mustFinishByDate": project.must_finish_by_date.isoformat() if project.must_finish_by_date else None,
            "durationPercentComplete": project.duration_percent_complete,
            "plannedDuration": project.planned_duration,
            "actualDuration": project.actual_duration,
            "remainingDuration": project.remaining_duration,
            "activityCount": project.activity_count,
            "completedActivities": project.completed_activity_count,
            "inProgressActivities": project.in_progress_activity_count,
            "notStartedActivities": project.not_started_activity_count,
            "totalFloat": project.total_float,
            "finishDateVariance": project.finish_date_variance,
            "startDateVariance": project.start_date_variance,
            "durationVariance": project.duration_variance,
            "actualTotalCost": project.actual_total_cost,
            "plannedCost": project.planned_cost,
            "cpi": project.cost_performance_index,
            "spi": project.schedule_performance_index,
            "currentBudget": project.current_budget,
            "costVariance": project.total_cost_variance,
            "baselineStartDate": project.baseline_start_date.isoformat() if project.baseline_start_date else None,
            "baselineFinishDate": project.baseline_finish_date.isoformat() if project.baseline_finish_date else None,
            "baselineDuration": project.baseline_duration,
            "baselineTotalCost": project.baseline_total_cost,
            "locationName": project.location_name,
            "parentEPSName": project.parent_eps_name,
            "lastSyncedAt": project.last_synced_at.isoformat() if project.last_synced_at else None,
        },
        "baselines": [
            {
                "objectId": b.p6_object_id,
                "baselineTypeName": b.baseline_type_name,
                "name": b.name,
                "plannedStartDate": b.planned_start_date.isoformat() if b.planned_start_date else None,
                "finishDate": b.finish_date.isoformat() if b.finish_date else None,
                "plannedDuration": b.planned_duration,
                "plannedCost": b.planned_cost,
                "status": b.status,
            }
            for b in baselines
        ]
    }

from pydantic import BaseModel
from services.p6_service import P6Service

from datetime import datetime

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    finish_date: Optional[datetime] = None
    planned_start_date: Optional[datetime] = None
    scheduled_finish_date: Optional[datetime] = None
    data_date: Optional[datetime] = None
    must_finish_by_date: Optional[datetime] = None
    baseline_start_date: Optional[datetime] = None
    baseline_finish_date: Optional[datetime] = None

@router.put("/p6/projects/{project_id}")
def update_project(project_id: str, update_data: ProjectUpdate, db: Session = Depends(get_db)):
    p6_service = P6Service()
    
    # Filter out None values to only update provided fields
    update_dict = {k: v for k, v in update_data.dict().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No valid update fields provided.")
        
    result = p6_service.update_project_in_p6(db, project_id, update_dict)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message"))
        
    return result
