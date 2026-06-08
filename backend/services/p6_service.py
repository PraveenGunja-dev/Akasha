import os
import requests
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv()

logger = logging.getLogger(__name__)


# ==========================================
# P6 Field Constants — Construction Focused
# ==========================================

# 39 fields for Project endpoint (Core + Schedule + Progress + Cost + Baseline)
PROJECT_FIELDS = (
    # Core Identification
    "ObjectId,Id,Name,Status,"
    # Schedule Dates
    "StartDate,FinishDate,PlannedStartDate,ScheduledFinishDate,"
    "DataDate,MustFinishByDate,"
    # Progress & Duration
    "SummaryDurationPercentComplete,SummaryPlannedDuration,"
    "SummaryActualDuration,SummaryRemainingDuration,"
    # Activity Counts
    "SummaryActivityCount,SummaryCompletedActivityCount,"
    "SummaryInProgressActivityCount,SummaryNotStartedActivityCount,"
    # Float & Variance (Critical Path)
    "SummaryTotalFloat,SummaryFinishDateVariance,"
    "SummaryStartDateVariance,SummaryDurationVariance,"
    # Cost
    "SummaryActualTotalCost,SummaryPlannedCost,"
    "SummaryCostPerformanceIndexByCost,SummarySchedulePerformanceIndexByCost,"
    "CurrentBudget,SummaryTotalCostVariance,"
    # Location & Organization
    "LocationName,ParentEPSName,"
    # Baseline Reference & Summary
    "CurrentBaselineProjectObjectId,"
    "SummaryBaselineStartDate,SummaryBaselineFinishDate,"
    "SummaryBaselineDuration,SummaryBaselineTotalCost,"
    "SummaryBaselineCompletedActivityCount,"
    "SummaryBaselineInProgressActivityCount,"
    "SummaryBaselineNotStartedActivityCount"
)

# Fields for BaselineProject endpoint
BASELINE_PROJECT_FIELDS = (
    "ObjectId,OriginalProjectObjectId,BaselineTypeName,Name,"
    "PlannedStartDate,FinishDate,ScheduledFinishDate,StartDate,"
    "SummaryPlannedDuration,SummaryActualDuration,SummaryRemainingDuration,"
    "SummaryPlannedCost,SummaryActualTotalCost,SummaryRemainingTotalCost,"
    "SummaryBaselineTotalCost,"
    "SummaryActivityCount,SummaryCompletedActivityCount,"
    "SummaryInProgressActivityCount,SummaryNotStartedActivityCount,"
    "CurrentBudget,OriginalBudget,Status"
)

# Activity fields for drill-down
ACTIVITY_FIELDS = (
    "ObjectId,Id,Name,Status,Type,"
    "StartDate,FinishDate,PlannedStartDate,PlannedFinishDate,"
    "ActualStartDate,ActualFinishDate,"
    "PlannedDuration,ActualDuration,RemainingDuration,AtCompletionDuration,"
    "PercentComplete,DurationPercentComplete,PhysicalPercentComplete,"
    "TotalFloat,FreeFloat,IsCritical,IsLongestPath,"
    "PlannedTotalCost,ActualTotalCost,RemainingTotalCost,"
    "CostPerformanceIndex,SchedulePerformanceIndex,"
    "WBSObjectId,WBSName,WBSCode,ProjectObjectId"
)


# ==========================================
# P6 → Database Field Mapping
# ==========================================

# Maps P6 API response field names → P6Project model column names
PROJECT_FIELD_MAP: Dict[str, str] = {
    "ObjectId": "p6_object_id",
    "Id": "project_id",
    "Name": "name",
    "Status": "status",
    # Schedule Dates
    "StartDate": "start_date",
    "FinishDate": "finish_date",
    "PlannedStartDate": "planned_start_date",
    "ScheduledFinishDate": "scheduled_finish_date",
    "DataDate": "data_date",
    "MustFinishByDate": "must_finish_by_date",
    # Progress & Duration
    "SummaryDurationPercentComplete": "duration_percent_complete",
    "SummaryPlannedDuration": "planned_duration",
    "SummaryActualDuration": "actual_duration",
    "SummaryRemainingDuration": "remaining_duration",
    # Activity Counts
    "SummaryActivityCount": "activity_count",
    "SummaryCompletedActivityCount": "completed_activity_count",
    "SummaryInProgressActivityCount": "in_progress_activity_count",
    "SummaryNotStartedActivityCount": "not_started_activity_count",
    # Float & Variance
    "SummaryTotalFloat": "total_float",
    "SummaryFinishDateVariance": "finish_date_variance",
    "SummaryStartDateVariance": "start_date_variance",
    "SummaryDurationVariance": "duration_variance",
    # Cost
    "SummaryActualTotalCost": "actual_total_cost",
    "SummaryPlannedCost": "planned_cost",
    "SummaryCostPerformanceIndexByCost": "cost_performance_index",
    "SummarySchedulePerformanceIndexByCost": "schedule_performance_index",
    "CurrentBudget": "current_budget",
    "SummaryTotalCostVariance": "total_cost_variance",
    # Location & Organization
    "LocationName": "location_name",
    "ParentEPSName": "parent_eps_name",
    # Baseline Reference
    "CurrentBaselineProjectObjectId": "current_baseline_project_object_id",
    # Baseline Summary
    "SummaryBaselineStartDate": "baseline_start_date",
    "SummaryBaselineFinishDate": "baseline_finish_date",
    "SummaryBaselineDuration": "baseline_duration",
    "SummaryBaselineTotalCost": "baseline_total_cost",
    "SummaryBaselineCompletedActivityCount": "baseline_completed_activity_count",
    "SummaryBaselineInProgressActivityCount": "baseline_in_progress_activity_count",
    "SummaryBaselineNotStartedActivityCount": "baseline_not_started_activity_count",
}

# Maps P6 API field names → P6BaselineProject model column names
BASELINE_FIELD_MAP: Dict[str, str] = {
    "ObjectId": "p6_object_id",
    "OriginalProjectObjectId": "original_project_object_id",
    "BaselineTypeName": "baseline_type_name",
    "Name": "name",
    "PlannedStartDate": "planned_start_date",
    "FinishDate": "finish_date",
    "ScheduledFinishDate": "scheduled_finish_date",
    "StartDate": "start_date",
    "SummaryPlannedDuration": "planned_duration",
    "SummaryActualDuration": "actual_duration",
    "SummaryRemainingDuration": "remaining_duration",
    "SummaryPlannedCost": "planned_cost",
    "SummaryActualTotalCost": "actual_total_cost",
    "SummaryRemainingTotalCost": "remaining_total_cost",
    "SummaryBaselineTotalCost": "baseline_total_cost",
    "SummaryActivityCount": "activity_count",
    "SummaryCompletedActivityCount": "completed_activity_count",
    "SummaryInProgressActivityCount": "in_progress_activity_count",
    "SummaryNotStartedActivityCount": "not_started_activity_count",
    "CurrentBudget": "current_budget",
    "OriginalBudget": "original_budget",
    "Status": "status",
}

# Date fields that need ISO parsing
DATE_FIELDS_PROJECT = {
    "start_date", "finish_date", "planned_start_date", "scheduled_finish_date",
    "data_date", "must_finish_by_date",
    "baseline_start_date", "baseline_finish_date",
}

DATE_FIELDS_BASELINE = {
    "planned_start_date", "finish_date", "scheduled_finish_date", "start_date",
}


# ==========================================
# Helper: Parse P6 date strings
# ==========================================
def _parse_p6_date(value: Any) -> Optional[datetime]:
    """Parse P6 ISO datetime strings into Python datetime objects."""
    if not value or value == "":
        return None
    try:
        # P6 returns dates like "2026-03-18T15:14:20.264Z" or "2026-03-18"
        if isinstance(value, str):
            value = value.replace("Z", "+00:00")
            # Try full ISO format first
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                # Try date-only format
                return datetime.strptime(value[:10], "%Y-%m-%d")
        return None
    except Exception:
        logger.warning(f"Could not parse date: {value}")
        return None


def _map_p6_response(raw: Dict[str, Any], field_map: Dict[str, str], date_fields: set) -> Dict[str, Any]:
    """
    Map a single P6 API response object to database model column names.
    Also parses date strings into datetime objects.
    """
    mapped = {}
    for p6_field, db_column in field_map.items():
        value = raw.get(p6_field)
        if db_column in date_fields:
            mapped[db_column] = _parse_p6_date(value)
        else:
            mapped[db_column] = value
    return mapped


# ==========================================
# P6 Service Class
# ==========================================
class P6Service:
    def __init__(self):
        self.base_url = os.getenv("ORACLE_P6_BASE_URL", "https://sin1.p6.oraclecloud.com/adani/p6ws/restapi")
        self.auth_token_b64 = os.getenv("ORACLE_P6_AUTH_TOKEN")
        self.token_url = os.getenv("ORACLE_P6_TOKEN_URL", "https://sin1.p6.oraclecloud.com/adani/p6ws/oauth/token")
        
        # We need to fetch an OAuth token using the basic auth credentials
        self.access_token = self._get_oauth_token()
        
        if self.access_token == self.auth_token_b64:
            auth_header = f"Basic {self.auth_token_b64}"
        else:
            auth_header = f"Bearer {self.access_token}"
        
        self.headers = {
            "Authorization": auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _get_oauth_token(self) -> str:
        """Fetches a fresh OAuth access token from P6."""
        import base64
        try:
            # Decode base64 token to get username and password
            decoded = base64.b64decode(self.auth_token_b64).decode("utf-8")
            username, password = decoded.split(":", 1)
            
            # Request token using password grant
            data = {
                "grant_type": "password",
                "username": username,
                "password": password
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            
            response = requests.post(self.token_url, data=data, headers=headers, timeout=15, verify=False)
            response.raise_for_status()
            
            # P6 token endpoint sometimes returns the raw JWT string directly instead of JSON
            text = response.text.strip()
            if text.startswith("eyJ"):
                return text
            else:
                return response.json().get("access_token", "")
        except Exception as e:
            logger.error(f"Failed to fetch P6 OAuth token: {e}")
            # Fallback to returning the basic token just in case
            return self.auth_token_b64


    # ------------------------------------------
    # 1. Fetch Projects from P6 API
    # ------------------------------------------
    def fetch_projects(self, status_filter: str = None) -> List[Dict[str, Any]]:
        """
        Fetch construction projects from P6 with all 39 fields.
        Returns raw P6 API response as list of dicts.
        """
        endpoint = f"{self.base_url}/project"
        params = {"Fields": PROJECT_FIELDS}

        if status_filter:
            params["Filter"] = f"Status='{status_filter}'"

        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=60, verify=False)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Fetched {len(data)} projects from P6")
            return data
        except requests.exceptions.HTTPError as e:
            logger.error(f"P6 HTTP Error fetching projects: {e} - {e.response.text if hasattr(e, 'response') and e.response else ''}")
            return []
        except Exception as e:
            logger.error(f"Error fetching P6 projects: {e}")
            return []

    # ------------------------------------------
    # 2. Fetch Baseline Projects from P6 API
    # ------------------------------------------
    def fetch_baseline_projects(self, project_object_id: int = None) -> List[Dict[str, Any]]:
        """
        Fetch baseline project snapshots from P6.
        Optionally filter by a specific project's ObjectId.
        """
        endpoint = f"{self.base_url}/baselineProject"
        params = {"Fields": BASELINE_PROJECT_FIELDS}

        if project_object_id:
            params["Filter"] = f"OriginalProjectObjectId={project_object_id}"

        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Fetched {len(data)} baseline projects from P6")
            return data
        except requests.exceptions.HTTPError as e:
            logger.error(f"P6 HTTP Error fetching baselines: {e} - {e.response.text if hasattr(e, 'response') and e.response else ''}")
            return []
        except Exception as e:
            logger.error(f"Error fetching P6 baseline projects: {e}")
            return []

    # ------------------------------------------
    # 3. Fetch Activities for a Project
    # ------------------------------------------
    def fetch_activities(self, project_object_id: int) -> List[Dict[str, Any]]:
        """Fetch activities for a specific project with construction-relevant fields."""
        endpoint = f"{self.base_url}/activity"
        params = {
            "Fields": ACTIVITY_FIELDS,
            "Filter": f"ProjectObjectId={project_object_id}"
        }

        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Fetched {len(data)} activities for project {project_object_id}")
            return data
        except requests.exceptions.HTTPError as e:
            logger.error(f"P6 HTTP Error fetching activities: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching P6 activities for project {project_object_id}: {e}")
            return []

    # ------------------------------------------
    # 4. Map & Store Projects to Database
    # ------------------------------------------
    def sync_projects_to_db(self, db: Session) -> int:
        """
        Fetch all projects from P6, map fields, and upsert into the database.
        Returns the number of projects synced.
        """
        from models import P6Project

        raw_projects_list = self.fetch_projects()
        if not raw_projects_list:
            logger.warning("No projects returned from P6 API")
            return 0
            
        # Deduplicate by ObjectId in case P6 returns duplicates
        raw_projects = {}
        for proj in raw_projects_list:
            if "ObjectId" in proj:
                raw_projects[proj["ObjectId"]] = proj

        synced_count = 0
        for raw in raw_projects.values():
            mapped = _map_p6_response(raw, PROJECT_FIELD_MAP, DATE_FIELDS_PROJECT)
            p6_object_id = mapped.get("p6_object_id")

            if not p6_object_id:
                logger.warning(f"Skipping project without ObjectId: {raw}")
                continue

            # Upsert: update if exists, insert if new
            existing = db.query(P6Project).filter(
                P6Project.p6_object_id == p6_object_id
            ).first()

            if existing:
                # Update all fields
                for key, value in mapped.items():
                    setattr(existing, key, value)
                existing.last_synced_at = datetime.utcnow()
                logger.debug(f"Updated project: {mapped.get('project_id')} - {mapped.get('name')}")
            else:
                # Insert new record
                mapped["last_synced_at"] = datetime.utcnow()
                new_project = P6Project(**mapped)
                db.add(new_project)
                logger.debug(f"Inserted project: {mapped.get('project_id')} - {mapped.get('name')}")

            synced_count += 1
            # Flush periodically to ensure existing objects are visible to queries
            if synced_count % 50 == 0:
                db.flush()

        db.commit()
        logger.info(f"Successfully synced {synced_count} projects to database")
        return synced_count

    # ------------------------------------------
    # 5. Map & Store Baseline Projects to DB
    # ------------------------------------------
    def sync_baselines_to_db(self, db: Session, project_object_id: int = None) -> int:
        """
        Fetch baseline projects from P6, map fields, and upsert into the database.
        Returns the number of baselines synced.
        """
        from models import P6BaselineProject

        raw_baselines_list = self.fetch_baseline_projects(project_object_id)
        if not raw_baselines_list:
            logger.warning("No baseline projects returned from P6 API")
            return 0

        # Deduplicate
        raw_baselines = {}
        for base in raw_baselines_list:
            if "ObjectId" in base:
                raw_baselines[base["ObjectId"]] = base

        synced_count = 0
        for raw in raw_baselines.values():
            mapped = _map_p6_response(raw, BASELINE_FIELD_MAP, DATE_FIELDS_BASELINE)
            p6_object_id = mapped.get("p6_object_id")

            if not p6_object_id:
                logger.warning(f"Skipping baseline without ObjectId: {raw}")
                continue

            # Upsert: update if exists, insert if new
            existing = db.query(P6BaselineProject).filter(
                P6BaselineProject.p6_object_id == p6_object_id
            ).first()

            if existing:
                for key, value in mapped.items():
                    setattr(existing, key, value)
                existing.last_synced_at = datetime.utcnow()
            else:
                mapped["last_synced_at"] = datetime.utcnow()
                new_baseline = P6BaselineProject(**mapped)
                db.add(new_baseline)

            synced_count += 1
            if synced_count % 50 == 0:
                db.flush()

        db.commit()
        logger.info(f"Successfully synced {synced_count} baselines to database")
        return synced_count

    # ------------------------------------------
    # 6. Full Sync: Projects + Baselines
    # ------------------------------------------
    def full_sync(self, db: Session) -> Dict[str, int]:
        """
        Run a full sync of both Projects and Baseline Projects.
        Returns a summary dict with counts.
        """
        logger.info("Starting full P6 sync...")

        projects_synced = self.sync_projects_to_db(db)
        baselines_synced = self.sync_baselines_to_db(db)

        result = {
            "projects_synced": projects_synced,
            "baselines_synced": baselines_synced,
            "synced_at": datetime.utcnow().isoformat()
        }
        logger.info(f"Full P6 sync complete: {result}")
        return result

    # ------------------------------------------
    # 7. Get Dashboard-Ready Project Data
    # ------------------------------------------
    @staticmethod
    def get_dashboard_projects(db: Session, project_name: str = None) -> List[Dict[str, Any]]:
        """
        Read stored P6 projects from database and format for the CEO Dashboard.
        Maps DB fields → frontend expected format.
        """
        from models import P6Project

        query = db.query(P6Project)
        if project_name and project_name != "All":
            query = query.filter(P6Project.name == project_name)

        projects = query.all()

        dashboard_data = []
        for p in projects:
            # Derive status from total float and variance
            if p.total_float is not None and p.total_float <= 0:
                derived_status = "Critical"
            elif p.finish_date_variance is not None and p.finish_date_variance < -7:
                derived_status = "Delayed"
            else:
                derived_status = "On Track"

            # Calculate planned progress from baseline
            planned_progress = 0
            if p.baseline_duration and p.baseline_duration > 0 and p.actual_duration is not None:
                planned_progress = min(round((p.actual_duration / p.baseline_duration) * 100, 1), 100)

            dashboard_data.append({
                "id": p.project_id,
                "name": p.name,
                "status": p.status or derived_status,
                # Progress (for the Planned vs Actual chart)
                "plannedProgress": planned_progress,
                "actualProgress": round(p.duration_percent_complete, 1) if p.duration_percent_complete else 0,
                # Critical Path
                "criticalPathDelayDays": abs(int(p.finish_date_variance)) if p.finish_date_variance else 0,
                "totalFloat": p.total_float,
                # Dates
                "startDate": p.start_date.isoformat() if p.start_date else None,
                "finishDate": p.finish_date.isoformat() if p.finish_date else None,
                "plannedStartDate": p.planned_start_date.isoformat() if p.planned_start_date else None,
                "scheduledFinishDate": p.scheduled_finish_date.isoformat() if p.scheduled_finish_date else None,
                "baselineStartDate": p.baseline_start_date.isoformat() if p.baseline_start_date else None,
                "baselineFinishDate": p.baseline_finish_date.isoformat() if p.baseline_finish_date else None,
                "dataDate": p.data_date.isoformat() if p.data_date else None,
                # Duration
                "plannedDuration": p.planned_duration,
                "actualDuration": p.actual_duration,
                "remainingDuration": p.remaining_duration,
                "baselineDuration": p.baseline_duration,
                "durationVariance": p.duration_variance,
                # Activity Counts
                "activityCount": p.activity_count,
                "completedActivities": p.completed_activity_count,
                "inProgressActivities": p.in_progress_activity_count,
                "notStartedActivities": p.not_started_activity_count,
                # Cost & EVM
                "actualTotalCost": p.actual_total_cost,
                "plannedCost": p.planned_cost,
                "currentBudget": p.current_budget,
                "cpi": p.cost_performance_index,
                "spi": p.schedule_performance_index,
                "costVariance": p.total_cost_variance,
                "baselineTotalCost": p.baseline_total_cost,
                # Location
                "locationName": p.location_name,
                "parentEPSName": p.parent_eps_name,
                # Sync info
                "lastSyncedAt": p.last_synced_at.isoformat() if p.last_synced_at else None,
            })

        return dashboard_data

    # ------------------------------------------
    # 8. Real Push to P6 API (Update DB + API)
    # ------------------------------------------
    def update_project_in_p6(self, db: Session, project_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pushes updated data back to the real Primavera P6 API and updates the local cache.
        """
        from models import P6Project
        
        project = db.query(P6Project).filter(P6Project.project_id == project_id).first()
        if not project:
            return {"success": False, "message": f"Project '{project_id}' not found in local cache."}
            
        logger.info(f"[REAL P6 API] Preparing to push updates for {project_id} (ObjectId: {project.p6_object_id})")
        
        # Reverse map database column names back to P6 API field names
        reverse_map = {v: k for k, v in PROJECT_FIELD_MAP.items()}
        
        p6_payload = {"ObjectId": project.p6_object_id}
        for key, value in update_data.items():
            if key in reverse_map:
                p6_field = reverse_map[key]
                
                # 1. Oracle P6 rejects or ignores updates to read-only "Summary" fields
                if p6_field.startswith("Summary"):
                    continue
                    
                # 2. Oracle P6 Status enum only accepts: Planned, Active, Inactive, What-If, Requested
                if p6_field == "Status":
                    if value == "Completed":
                        p6_payload["Status"] = "Inactive"
                    elif value in ["On Track", "Delayed", "Critical"]:
                        p6_payload["Status"] = "Active"
                    else:
                        p6_payload["Status"] = value
                    continue
                    
                # 4. Convert datetime to ISO 8601 string
                if isinstance(value, datetime):
                    p6_payload[p6_field] = value.strftime("%Y-%m-%dT%H:%M:%S")
                elif value is not None:
                    p6_payload[p6_field] = value
                
        # Send to P6 API
        endpoint = f"{self.base_url}/project"
        try:
            # Send array of objects for bulk endpoint
            response = requests.put(endpoint, headers=self.headers, json=[p6_payload], timeout=30)
            
            # If 405 Method Not Allowed, fallback to POST
            if response.status_code == 405:
                response = requests.post(endpoint, headers=self.headers, json=p6_payload, timeout=30)
                
            response.raise_for_status()
            logger.info(f"[REAL P6 API] Successfully pushed updates for {project_id} to Oracle P6")
            
        except requests.exceptions.HTTPError as e:
            error_msg = e.response.text if hasattr(e, 'response') and e.response else str(e)
            logger.error(f"[REAL P6 API] Failed to push to P6: {error_msg}")
            # If the bulk PUT array fails with 400 or 404, fallback to single object PUT
            if e.response and e.response.status_code in (400, 404, 405):
                single_endpoint = f"{self.base_url}/project/{project.p6_object_id}"
                single_payload = {k: v for k, v in p6_payload.items() if k != "ObjectId"}
                try:
                    fallback_res = requests.put(single_endpoint, headers=self.headers, json=single_payload, timeout=30)
                    fallback_res.raise_for_status()
                    logger.info(f"[REAL P6 API] Fallback successful for {project_id}")
                except Exception as ex:
                    fallback_msg = getattr(ex, 'response', None)
                    fallback_text = fallback_msg.text if fallback_msg else str(ex)
                    return {"success": False, "message": f"P6 API Error: {error_msg}. Fallback also failed: {fallback_text}"}
            else:
                return {"success": False, "message": f"P6 API Error: {error_msg}"}
        except Exception as e:
            logger.error(f"[REAL P6 API] Failed to push to P6: {e}")
            return {"success": False, "message": f"Connection Error: {str(e)}"}
        
        # If API push successful, update local DB
        for key, value in update_data.items():
            if hasattr(project, key):
                setattr(project, key, value)
                
        project.last_synced_at = datetime.utcnow()
        db.commit()
        
        return {"success": True, "message": f"Successfully updated project {project_id} in P6.", "project_id": project_id}

if __name__ == "__main__":
    # Quick test — fetch and print
    logging.basicConfig(level=logging.INFO)
    p6 = P6Service()

    print("\n=== Testing P6 Project Fetch (39 fields) ===")
    projects = p6.fetch_projects()
    print(f"Found {len(projects)} projects")
    if projects:
        print(f"Sample project keys: {list(projects[0].keys())}")
        print(f"First project: {projects[0]}")

    print("\n=== Testing P6 Baseline Fetch ===")
    baselines = p6.fetch_baseline_projects()
    print(f"Found {len(baselines)} baseline projects")
    if baselines:
        print(f"Sample baseline keys: {list(baselines[0].keys())}")
        print(f"First baseline: {baselines[0]}")
