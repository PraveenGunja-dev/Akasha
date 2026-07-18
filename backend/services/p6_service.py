import os
import requests
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET

load_dotenv()

logger = logging.getLogger(__name__)

# ==========================================
# P6 Field Constants — Construction Focused
# ==========================================

# Constants
WIND_PROJECTS = {
    3074: 5.2,
    4707: 5.0,
    3075: 5.2,
    3076: 5.2,
    3072: 5.2,
    3073: 5.2,
    6733: 5.2,
    3105: 3.3,
}
DEFAULT_WIND_MW = 5.2

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
    "SummaryActualNonLaborUnits,SummaryBudgetAtCompletionByLaborUnits,"
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
    "WBSObjectId,WBSName,WBSCode,ProjectObjectId,"
    "BaselineStartDate,BaselineFinishDate"
)

# WBS fields
WBS_FIELDS = "ObjectId,ParentObjectId,ProjectObjectId,Name,Code"

# Resource Assignment fields
RESOURCE_ASSIGNMENT_FIELDS = "ObjectId,ActivityObjectId,ProjectObjectId,ResourceName,ResourceType,PlannedUnits,ActualUnits"

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
    "SummaryActualNonLaborUnits": "actual_non_labor_units",
    "SummaryBaselineNonLaborUnits": "baseline_non_labor_units",
    "SummaryBudgetAtCompletionByLaborUnits": "budget_labor_units",
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


ACTIVITY_FIELD_MAP: Dict[str, str] = {
    'ObjectId': 'p6_object_id',
    'Id': 'activity_id',
    'Name': 'name',
    'Status': 'status',
    'Type': 'type',
    'StartDate': 'start_date',
    'FinishDate': 'finish_date',
    'PlannedStartDate': 'planned_start_date',
    'PlannedFinishDate': 'planned_finish_date',
    'ActualStartDate': 'actual_start_date',
    'ActualFinishDate': 'actual_finish_date',
    'PlannedDuration': 'planned_duration',
    'ActualDuration': 'actual_duration',
    'RemainingDuration': 'remaining_duration',
    'PercentComplete': 'percent_complete',
    'TotalFloat': 'total_float',
    'IsCritical': 'is_critical',
    'WBSObjectId': 'wbs_object_id',
    'WBSName': 'wbs_name',
    'WBSCode': 'wbs_code',
    'ProjectObjectId': 'project_object_id',
    'BaselineStartDate': 'baseline_start_date',
    'BaselineFinishDate': 'baseline_finish_date',
}

DATE_FIELDS_ACTIVITY = {
    'start_date', 'finish_date', 'planned_start_date', 'planned_finish_date',
    'actual_start_date', 'actual_finish_date',
    'baseline_start_date', 'baseline_finish_date'
}

WBS_FIELD_MAP: Dict[str, str] = {
    'ObjectId': 'p6_object_id',
    'ParentObjectId': 'parent_object_id',
    'ProjectObjectId': 'project_object_id',
    'Name': 'wbs_name',
    'Code': 'wbs_code'
}

RESOURCE_ASSIGNMENT_FIELD_MAP: Dict[str, str] = {
    'ObjectId': 'p6_object_id',
    'ActivityObjectId': 'activity_object_id',
    'ProjectObjectId': 'project_object_id',
    'ResourceName': 'resource_name',
    'ResourceType': 'resource_type',
    'PlannedUnits': 'planned_units',
    'ActualUnits': 'actual_units'
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
        elif db_column == 'is_critical':
            if isinstance(value, str):
                mapped[db_column] = value.lower() == 'true'
            else:
                mapped[db_column] = bool(value)
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
        
        self.proxies = {
            "http": os.getenv("HTTP_PROXY") or os.getenv("http_proxy"),
            "https": os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
        }
        
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
        if self.auth_token_b64 and self.auth_token_b64.startswith("eyJ"):
            return self.auth_token_b64
            
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
            
            response = requests.post(self.token_url, data=data, headers=headers, timeout=15, verify=False, proxies=self.proxies)
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
    def fetch_projects(self, status_filter: str = None, project_object_id: int = None) -> List[Dict[str, Any]]:
        """
        Fetch construction projects from P6 with all 39 fields.
        Returns raw P6 API response as list of dicts.
        """
        endpoint = f"{self.base_url}/project"
        params = {"Fields": PROJECT_FIELDS}

        filters = []
        if status_filter:
            filters.append(f"Status='{status_filter}'")
        if project_object_id:
            filters.append(f"ObjectId={project_object_id}")

        if filters:
            params["Filter"] = " and ".join(filters)

        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=180, verify=False, proxies=self.proxies)

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
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=180, verify=False, proxies=self.proxies)
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
    # 4. Map & Store Projects to Database
    # ------------------------------------------
    def sync_projects_to_db(self, db: Session, project_object_id: int = None) -> int:
        """
        Fetch all projects from P6, map fields, and upsert into the database.
        Returns the number of projects synced.
        """
        from models import P6Project, ProjectMapping

        raw_projects_list = self.fetch_projects(project_object_id=project_object_id)
        if not raw_projects_list:
            logger.warning("No projects returned from P6 API")
            return 0
            
        mapped_ids = {m.project_id for m in db.query(ProjectMapping).all()}
            
        # Deduplicate by ObjectId in case P6 returns duplicates, and filter by mapped projects
        raw_projects = {}
        for proj in raw_projects_list:
            if "ObjectId" in proj and proj.get("Id") in mapped_ids:
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
                from models import Notification
                for key, value in mapped.items():
                    if key in DATE_FIELDS_PROJECT and value is not None:
                        old_val = getattr(existing, key)
                        old_date = getattr(old_val, "date", lambda: old_val)() if old_val else None
                        new_date = getattr(value, "date", lambda: value)() if value else None
                        if old_date != new_date:
                            notif = Notification(
                                project_name=existing.name or str(existing.project_id),
                                module="P6",
                                change_type="Date Change",
                                message=f"Project '{existing.name}' {key} changed from {old_date} to {new_date}",
                                activity_name=key,
                                old_value=str(old_date),
                                new_value=str(new_date),
                                reason="Project schedule updated in Primavera P6.",
                                action_status="Pending",
                                category="Dates",
                                p6_object_id=existing.p6_object_id,
                                p6_type="Project"
                            )
                            db.add(notif)
                            db.flush()

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

            # Check budget exceeded for both existing and new
            from models import Notification
            actual_cost = mapped.get("actual_total_cost")
            budget_val = mapped.get("current_budget") or mapped.get("planned_cost")
            if actual_cost is not None and budget_val is not None:
                if float(actual_cost) > float(budget_val):
                    proj_name = mapped.get("name") or str(mapped.get("project_id"))
                    msg = f"Project '{proj_name}' actual cost ({actual_cost}) exceeds budget ({budget_val})"
                    exists = db.query(Notification).filter(
                        Notification.project_name == proj_name,
                        Notification.message == msg
                    ).first()
                    if not exists:
                        notif = Notification(
                            project_name=proj_name,
                            module="P6",
                            change_type="Budget Exceeded",
                            message=msg,
                            activity_name="Project Cost",
                            old_value=str(budget_val),
                            new_value=str(actual_cost),
                            reason="Actual costs have exceeded the planned budget for this project.",
                            action_status="Pending",
                            category="Budgets",
                            p6_object_id=mapped.get("p6_object_id"),
                            p6_type="Project"
                        )
                        db.add(notif)
                        db.flush()

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
        from models import P6BaselineProject, P6Project, ProjectMapping

        raw_baselines_list = self.fetch_baseline_projects(project_object_id)
        if not raw_baselines_list:
            logger.warning("No baseline projects returned from P6 API")
            return 0

        mapped_ids = {m.project_id for m in db.query(ProjectMapping).all()}
        mapped_p6_objs = {p.p6_object_id for p in db.query(P6Project).filter(P6Project.project_id.in_(mapped_ids)).all()}

        # Deduplicate and filter by mapped projects
        raw_baselines = {}
        for base in raw_baselines_list:
            if "ObjectId" in base and base.get("OriginalProjectObjectId") in mapped_p6_objs:
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
    # 7. Map & Store WBS to DB
    # ------------------------------------------
    def fetch_wbs(self, project_object_id: int = None) -> List[Dict[str, Any]]:
        endpoint = f"{self.base_url}/wbs"
        params = {
            "Fields": WBS_FIELDS,
            "Filter": f"ProjectObjectId={project_object_id}"
        }
        
        logger.info(f"[REAL P6 API] Fetching WBS for Project {project_object_id}")
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            logger.error(f"[REAL P6 API] Error fetching WBS: {e}")
            return []

    def fetch_resource_assignments(self, project_object_id: int) -> List[Dict[str, Any]]:
        """
        Fetches all Resource Assignments for a given project from Oracle Primavera P6.
        """
        endpoint = f"{self.base_url}/resourceAssignment"
        params = {
            "Fields": RESOURCE_ASSIGNMENT_FIELDS,
            "Filter": f"ProjectObjectId={project_object_id}"
        }
        
        logger.info(f"[REAL P6 API] Fetching Resource Assignments for Project {project_object_id}")
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            logger.error(f"[REAL P6 API] Error fetching Resource Assignments: {e}")
            return []

    def sync_wbs_to_db(self, db: Session, project_object_id: int) -> int:
        from models import P6WBSNode

        raw_wbs = self.fetch_wbs(project_object_id)
        if not raw_wbs:
            return 0

        synced_count = 0
        for raw in raw_wbs:
            mapped = _map_p6_response(raw, WBS_FIELD_MAP, set())
            p6_object_id = mapped.get("p6_object_id")

            if not p6_object_id:
                continue

            existing = db.query(P6WBSNode).filter(P6WBSNode.p6_object_id == p6_object_id).first()

            if existing:
                for key, value in mapped.items():
                    setattr(existing, key, value)
                existing.upload_time = datetime.utcnow()
            else:
                mapped["upload_time"] = datetime.utcnow()
                new_node = P6WBSNode(**mapped)
                db.add(new_node)

            synced_count += 1
            if synced_count % 100 == 0:
                db.flush()

        db.commit()
        logger.info(f"Finished syncing {len(raw_wbs)} WBS nodes for project {project_object_id}.")
        return synced_count

    def sync_resource_assignments_to_db(self, db: Session, project_object_id: int):
        """
        Fetches resource assignments from Oracle P6 and saves them to the database.
        Aggregates units to check for project-level budget exceeded notifications.
        """
        from models import P6ResourceAssignment
        
        raw_assignments = self.fetch_resource_assignments(project_object_id)
        if not raw_assignments:
            logger.warning(f"No resource assignments found for project {project_object_id}.")
            return
            
        material_actual = 0.0
        material_planned = 0.0
        labor_actual = 0.0
        labor_planned = 0.0
            
        for raw_ass in raw_assignments:
            p6_object_id = raw_ass.get('ObjectId')
            if not p6_object_id:
                continue
                
            ass_node = db.query(P6ResourceAssignment).filter(P6ResourceAssignment.p6_object_id == p6_object_id).first()
            if not ass_node:
                ass_node = P6ResourceAssignment(p6_object_id=p6_object_id)
                
            for p6_field, db_col in RESOURCE_ASSIGNMENT_FIELD_MAP.items():
                if p6_field in raw_ass:
                    value = raw_ass[p6_field]
                    if hasattr(ass_node, db_col):
                        setattr(ass_node, db_col, value)
            
            # Only count Material and Labor resources for Scope check (exclude Nonlabor)
            r_type = (ass_node.resource_type or "").lower()
            if r_type == 'material':
                if ass_node.actual_units:
                    material_actual += float(ass_node.actual_units)
                if ass_node.planned_units:
                    material_planned += float(ass_node.planned_units)
            elif r_type == 'labor':
                if ass_node.actual_units:
                    labor_actual += float(ass_node.actual_units)
                if ass_node.planned_units:
                    labor_planned += float(ass_node.planned_units)
            
            db.add(ass_node)
            
        # Project-level scope check (Material + Labor separately)
        from models import Notification, P6Project
        proj = db.query(P6Project).filter(P6Project.p6_object_id == project_object_id).first()
        proj_name = proj.name if proj else f"Project-{project_object_id}"
        
        for res_type, act_val, plan_val in [("Material", material_actual, material_planned), ("Labor", labor_actual, labor_planned)]:
            if plan_val > 0 and act_val > plan_val:
                variance = round(act_val - plan_val, 2)
                msg = f"Scope Exceeded ({res_type}): '{proj_name}' actual units ({round(act_val, 2)}) exceed budgeted units ({round(plan_val, 2)}). Variance: {variance}"
                
                exists = db.query(Notification).filter(
                    Notification.project_name == proj_name,
                    Notification.change_type == "Scope Exceeded",
                    Notification.activity_name == f"Project Level - {res_type} Resources"
                ).first()
                
                if not exists:
                    notif = Notification(
                        project_name=proj_name,
                        module="P6",
                        change_type="Scope Exceeded",
                        message=msg,
                        activity_name=f"Project Level - {res_type} Resources",
                        old_value=str(round(plan_val, 2)),
                        new_value=str(round(act_val, 2)),
                        reason=f"Total {res_type.lower()} actual units exceed budgeted scope by {variance} units.",
                        action_status="Pending",
                        category="Scope",
                        p6_object_id=project_object_id,
                        p6_type="Project"
                    )
                    db.add(notif)
                    db.flush()
            
        db.commit()
        logger.info(f"Finished syncing {len(raw_assignments)} Resource Assignments for project {project_object_id}.")

    # ------------------------------------------
    # 8. Map & Store Activities to DB
    # ------------------------------------------
    def fetch_activities(self, project_object_id: int = None) -> List[Dict[str, Any]]:
        endpoint = f"{self.base_url}/activity"
        params = {
            "Fields": ACTIVITY_FIELDS
        }
        if project_object_id:
            params["Filter"] = f"ProjectObjectId={project_object_id}"
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=180, verify=False, proxies=self.proxies)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching activities from P6: {e}")
            return []

    def sync_activities_to_db(self, db: Session, project_object_id: int = None) -> int:
        from models import P6Activity

        raw_activities = self.fetch_activities(project_object_id)
        if not raw_activities:
            return 0

        synced_count = 0
        from collections import defaultdict
        block_notifications = defaultdict(list)

        for raw in raw_activities:
            mapped = _map_p6_response(raw, ACTIVITY_FIELD_MAP, DATE_FIELDS_ACTIVITY)
            p6_object_id = mapped.get("p6_object_id")

            if not p6_object_id:
                continue

            existing = db.query(P6Activity).filter(P6Activity.p6_object_id == p6_object_id).first()

            if existing:
                # Collect all date changes for this activity first
                date_changes = []
                for key, value in mapped.items():
                    if key in DATE_FIELDS_ACTIVITY and value is not None:
                        old_val = getattr(existing, key)
                        old_date = getattr(old_val, "date", lambda: old_val)() if old_val else None
                        new_date = getattr(value, "date", lambda: value)() if value else None
                        if old_date != new_date:
                            date_changes.append((key, old_date, new_date))
                
                if date_changes:
                    name_lower = (existing.name or "").lower()
                    is_cod = "cod" in name_lower or "scod" in name_lower
                    p6_is_critical = mapped.get("is_critical", existing.is_critical)
                    is_critical_flag = is_cod or p6_is_critical
                    
                    # Skip notifications for non-critical activities
                    if is_critical_flag:
                        block_name = existing.name.split('-')[0].strip() if existing.name and '-' in existing.name else "Other"
                        cat_val = "COD" if is_cod else ("Critical Path" if p6_is_critical else "Trials")
                        
                        block_notifications[block_name].append({
                            "activity_name": existing.name,
                            "is_cod": is_cod,
                            "cat_val": cat_val,
                            "project_object_id": existing.project_object_id
                        })

                for key, value in mapped.items():
                    setattr(existing, key, value)
                existing.last_synced_at = datetime.utcnow()
            else:
                mapped["last_synced_at"] = datetime.utcnow()
                new_activity = P6Activity(**mapped)
                db.add(new_activity)

            synced_count += 1
            if synced_count % 100 == 0:
                db.flush()

        # Process aggregated block notifications
        from models import Notification, P6Project, ProjectMapping
        for block_name, changes in block_notifications.items():
            if not changes: continue
            
            has_cod = any(c['is_cod'] for c in changes)
            primary_cat = "COD" if has_cod else changes[0]['cat_val']
            
            activity_names = [c['activity_name'] for c in changes]
            highlight = ", ".join(activity_names[:2])
            if len(activity_names) > 2:
                highlight += f" and {len(activity_names) - 2} others"
                
            msg = f"🚨 CRITICAL SLIP: {len(changes)} activities changed dates in '{block_name}' (e.g., {highlight})."
            
            proj_obj_id = changes[0]['project_object_id']
            proj_name = str(proj_obj_id)
            try:
                p = db.query(P6Project).filter(P6Project.p6_object_id == proj_obj_id).first()
                if p and p.name: proj_name = p.name
            except Exception:
                pass
                
            exists_notif = db.query(Notification).filter(
                Notification.project_name == proj_name,
                Notification.block == (block_name if block_name != "Other" else None),
                Notification.message == msg
            ).first()
            
            if not exists_notif:
                notif = Notification(
                    project_name=proj_name,
                    module="P6",
                    change_type="Critical Date Slip",
                    message=msg,
                    block=block_name if block_name != "Other" else None,
                    activity_name="Multiple Activities",
                    old_value=str(len(changes)),
                    new_value="Activities",
                    reason=f"Batch update: {len(changes)} critical activities shifted dates.",
                    action_status="Pending",
                    category=primary_cat,
                    p6_object_id=proj_obj_id,
                    p6_type="Project"
                )
                db.add(notif)
                db.flush()

        db.commit()

        # Check Trial Run -> COD gap > 15 days
        try:
            from models import Notification, P6Project, ProjectMapping, P6Activity
            if project_object_id:
                cods = db.query(P6Activity).filter(P6Activity.project_object_id == project_object_id, P6Activity.name.ilike('%cod%')).all()
                trials = db.query(P6Activity).filter(P6Activity.project_object_id == project_object_id, (P6Activity.name.ilike('%trial run certificate%') | P6Activity.name.ilike('%trail run certificate%'))).all()
                
                mw_str = ""
                if cods:
                    p = db.query(P6Project).filter(P6Project.p6_object_id == project_object_id).first()
                    if p:
                        m = db.query(ProjectMapping).filter(ProjectMapping.project_id == p.project_id).first()
                        if m:
                            is_wind = m.category and 'wind' in m.category.lower()
                            if not is_wind:
                                mw_str = " Impact: ~12.5 MW."
                            else:
                                wtg_mw = WIND_PROJECTS.get(project_object_id, DEFAULT_WIND_MW)
                                mw_str = f" Impact: ~{wtg_mw} MW."

                for cod in cods:
                    if not cod.wbs_object_id: continue
                    matching_trial = next((t for t in trials if t.wbs_object_id == cod.wbs_object_id), None)
                    if matching_trial and cod.actual_start_date and matching_trial.actual_start_date and not cod.actual_finish_date:
                        diff = (cod.actual_start_date - matching_trial.actual_start_date).days
                        if diff > 7:
                            block_name = cod.name.split('-')[0].strip() if '-' in cod.name else cod.name
                            msg = f"Schedule Anomaly: Gap between actual start of Trial Run and COD for '{block_name}' exceeds 7 days ({diff} days delay).{mw_str}"
                            exists = db.query(Notification).filter(Notification.message == msg).first()
                            if not exists:
                                try:
                                    proj_name = str(project_object_id)
                                    from models import P6Project
                                    p_obj = db.query(P6Project).filter(P6Project.p6_object_id == project_object_id).first()
                                    if p_obj and p_obj.name: proj_name = p_obj.name
                                except:
                                    proj_name = str(project_object_id)

                                notif = Notification(
                                    project_name=proj_name,
                                    module="P6",
                                    change_type="Schedule Anomaly",
                                    message=msg,
                                    block=block_name,
                                    activity_name=cod.name,
                                    old_value=str(matching_trial.actual_start_date.date()),
                                    new_value=str(cod.actual_start_date.date()),
                                    reason=f"Gap between Trial Run and COD actual starts is {diff} days (limit is 7). COD is not yet completed.",
                                    action_status="Pending",
                                    category="COD",
                                    p6_object_id=cod.p6_object_id,
                                    p6_type="Activity"
                                )
                                db.add(notif)
                                db.flush()
                db.commit()
        except Exception as e:
            logger.error(f"Error calculating Trial-COD gap: {e}")

        # Recalculate Project Activity Counts
        try:
            from models import P6Project, P6Activity
            logger.info("Recalculating project activity counts from synced activities...")
            if project_object_id:
                projects = db.query(P6Project).filter(P6Project.p6_object_id == project_object_id).all()
            else:
                projects = db.query(P6Project).all()
                
            for p in projects:
                activities = db.query(P6Activity).filter_by(project_object_id=p.p6_object_id).all()
                if not activities: continue
                total = len(activities)
                completed = sum(1 for a in activities if a.status == 'Completed')
                in_progress = sum(1 for a in activities if a.status == 'In Progress')
                not_started = sum(1 for a in activities if a.status == 'Not Started')
                p.activity_count = total
                p.completed_activity_count = completed
                p.in_progress_activity_count = in_progress
                p.not_started_activity_count = not_started
                if total > 0:
                    total_percent = sum((a.percent_complete or 0.0) for a in activities)
                    p.duration_percent_complete = total_percent / total
                    
                    # Calculate construction-specific progress
                    construction_acts = [a for a in activities if a.wbs_name and 'construction' in str(a.wbs_name).lower()]
                    if construction_acts:
                        const_percent = sum((a.percent_complete or 0.0) for a in construction_acts)
                        p.construction_percent_complete = const_percent / len(construction_acts)
                    else:
                        p.construction_percent_complete = p.duration_percent_complete
            db.commit()
        except Exception as e:
            logger.error(f"Error recalculating activity counts: {e}")

        logger.info(f"Successfully synced {synced_count} activities to database")
        return synced_count

    def fetch_activity_risks(self, project_object_id: int = None) -> List[Dict[str, Any]]:
        endpoint = f"{self.base_url}/activityRisk"
        params = {
            "Fields": "ActivityId,RiskId,RiskName,ActivityObjectId,ProjectObjectId,RiskObjectId,ActivityName"
        }
        if project_object_id:
            params["Filter"] = f"ProjectObjectId={project_object_id}"
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=180, verify=False, proxies=self.proxies)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching ActivityRisk from P6: {e}")
            return []

    def sync_activity_risks_to_db(self, db: Session, project_object_id: int = None) -> int:
        from models import P6ActivityRisk

        raw_risks = self.fetch_activity_risks(project_object_id)
        if not raw_risks:
            return 0

        synced_count = 0
        for raw in raw_risks:
            act_obj_id = raw.get("ActivityObjectId")
            proj_obj_id = raw.get("ProjectObjectId")
            risk_id = raw.get("RiskId")
            
            if not act_obj_id or not proj_obj_id:
                continue

            existing = db.query(P6ActivityRisk).filter(
                P6ActivityRisk.activity_object_id == act_obj_id,
                P6ActivityRisk.risk_id == risk_id
            ).first()

            if existing:
                existing.risk_name = raw.get("RiskName")
                existing.risk_object_id = raw.get("RiskObjectId")
                existing.activity_id = raw.get("ActivityId")
                existing.activity_name = raw.get("ActivityName")
                existing.last_synced_at = datetime.utcnow()
            else:
                new_risk = P6ActivityRisk(
                    activity_object_id=act_obj_id,
                    project_object_id=proj_obj_id,
                    risk_id=risk_id,
                    risk_name=raw.get("RiskName"),
                    risk_object_id=raw.get("RiskObjectId"),
                    activity_id=raw.get("ActivityId"),
                    activity_name=raw.get("ActivityName"),
                    last_synced_at=datetime.utcnow()
                )
                db.add(new_risk)
                db.flush()
                
                # Generate Notification for new risk assignment
                from models import Notification, P6Project
                proj = db.query(P6Project).filter(P6Project.p6_object_id == proj_obj_id).first()
                proj_name = proj.name if proj else str(proj_obj_id)
                msg = f"⚠️ NEW RISK: Activity '{raw.get('ActivityName')}' is now threatened by '{raw.get('RiskName')}'"
                
                notif = Notification(
                    project_name=proj_name,
                    module="P6",
                    change_type="New Risk Assignment",
                    message=msg,
                    activity_name=raw.get("ActivityName"),
                    old_value="",
                    new_value=raw.get("RiskName"),
                    reason=f"Risk '{raw.get('RiskName')}' was mapped to this activity in P6.",
                    action_status="Pending",
                    category="Risk",
                    p6_object_id=act_obj_id,
                    p6_type="Activity"
                )
                db.add(notif)

            synced_count += 1
            if synced_count % 100 == 0:
                db.flush()

        db.commit()
        logger.info(f"Finished syncing {synced_count} ActivityRisks.")
        return synced_count

    # ------------------------------------------
    # 6. Full Sync: Projects + Baselines + Activities + Risks
    # ------------------------------------------
    def full_sync(self, db: Session) -> Dict[str, int]:
        """
        Run a full sync of both Projects and Baseline Projects.
        Returns a summary dict with counts.
        """
        logger.info("Starting full P6 sync...")

        projects_synced = self.sync_projects_to_db(db)
        baselines_synced = self.sync_baselines_to_db(db)
        
        from models import P6Project, ProjectMapping
        mapped_project_ids = [m.project_id for m in db.query(ProjectMapping).all()]
        projects = db.query(P6Project).filter(P6Project.project_id.in_(mapped_project_ids)).all()
        
        wbs_synced = 0
        activities_synced = 0
        
        for proj in projects:
            wbs_synced += self.sync_wbs_to_db(db, proj.p6_object_id)
            activities_synced += self.sync_activities_to_db(db, proj.p6_object_id)
            self.sync_resource_assignments_to_db(db, proj.p6_object_id)
            self.sync_activity_risks_to_db(db, proj.p6_object_id)
        
        # New: Post-sync check for Trial Run vs COD discrepancy
        self.check_trial_cod_discrepancy(db)

        result = {
            "projects_synced": projects_synced,
            "baselines_synced": baselines_synced,
            "wbs_synced": wbs_synced,
            "activities_synced": activities_synced,
            "synced_at": datetime.utcnow().isoformat()
        }
        logger.info(f"Full P6 sync complete: {result}")
        return result

    def check_trial_cod_discrepancy(self, db: Session) -> None:
        """
        Check if any Trial Run Certificate is 'Completed', but the corresponding COD activity
        is NOT completed ('In Progress' or 'Not Started') and the 7-day window has passed.
        Generates notifications in the 'Trials' category.
        """
        from models import P6Activity, Notification, P6Project, ProjectMapping
        
        import re
        
        # Find all completed Trial Runs
        trials = db.query(P6Activity).filter(
            (P6Activity.name.ilike('%trial run certificate%')) | 
            (P6Activity.name.ilike('%trail run certificate%')) |
            (P6Activity.name.ilike('%WTG Trial Run%')) |
            (P6Activity.name.ilike('%Trial Operation%')) 
        ).filter(P6Activity.status == 'Completed').all()
        
        for t in trials:
            if not t.name: continue
            
            match = re.search(r'(Block-\d+|WTG\d+)', t.name, re.IGNORECASE)
            block_name = match.group(1) if match else None
            
            if not block_name:
                continue
                
            # Find matching COD for the same block
            cods = db.query(P6Activity).filter(
                P6Activity.project_object_id == t.project_object_id,
                P6Activity.name.ilike(f'{block_name}%cod%')
            ).all()
            
            for c in cods:
                if c.status != 'Completed':
                    finish_date = t.actual_finish_date or t.actual_start_date
                    if finish_date:
                        # Check 7 day gap
                        gap = (datetime.utcnow().date() - finish_date.date()).days
                        if gap > 7:
                            proj_name = str(t.project_object_id)
                            p = db.query(P6Project).filter(P6Project.p6_object_id == t.project_object_id).first()
                            if p and p.name:
                                proj_name = p.name
                                
                            mw_str = ""
                            try:
                                if p:
                                    m = db.query(ProjectMapping).filter(ProjectMapping.project_id == p.project_id).first()
                                    if m:
                                        is_wind = m.category and 'wind' in m.category.lower()
                                        if not is_wind:
                                            mw_str = " (~12.5 MW)"
                                        else:
                                            wtg_mw = WIND_PROJECTS.get(t.project_object_id, DEFAULT_WIND_MW)
                                            mw_str = f" (~{wtg_mw} MW)"
                            except Exception:
                                pass
                                
                            msg = f"🚨 DELAY WARNING{mw_str}: '{block_name}' Trial Run was completed {gap} days ago, but COD is currently {c.status}!"
                            
                            exists = db.query(Notification).filter(
                                Notification.project_name == proj_name,
                                Notification.activity_name == c.name,
                                Notification.message == msg
                            ).first()
                            
                            if not exists:
                                notif = Notification(
                                    project_name=proj_name,
                                    module="P6",
                                    change_type="COD Delay Post-Trial",
                                    message=msg,
                                    block=block_name,
                                    activity_name=c.name,
                                    old_value=t.status,
                                    new_value=c.status,
                                    reason=f"Trial Run completed on {finish_date.date()}, but COD is still pending after 7 days.",
                                    action_status="Pending",
                                    category="Trials",
                                    p6_object_id=c.p6_object_id,
                                    p6_type="Activity"
                                )
                                db.add(notif)
                                db.flush()
        db.commit()

    # ------------------------------------------
    # 6.5. Individual Sync: Project + Baseline + Activities
    # ------------------------------------------
    def individual_sync(self, db: Session, project_object_id: int) -> Dict[str, int]:
        """
        Run an individual sync of Project, Baseline Project, and Activities for a specific project.
        Returns a summary dict with counts.
        """
        logger.info(f"Starting individual P6 sync for project {project_object_id}...")

        projects_synced = self.sync_projects_to_db(db, project_object_id=project_object_id)
        baselines_synced = self.sync_baselines_to_db(db, project_object_id=project_object_id)
        wbs_synced = self.sync_wbs_to_db(db, project_object_id=project_object_id)
        activities_synced = self.sync_activities_to_db(db, project_object_id=project_object_id)
        self.sync_resource_assignments_to_db(db, project_object_id=project_object_id)
        self.sync_activity_risks_to_db(db, project_object_id=project_object_id)

        result = {
            "projects_synced": projects_synced,
            "baselines_synced": baselines_synced,
            "wbs_synced": wbs_synced,
            "activities_synced": activities_synced,
            "synced_at": datetime.utcnow().isoformat()
        }
        logger.info(f"Individual P6 sync complete for project {project_object_id}: {result}")
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

    def update_activity_in_p6(self, db: Session, p6_object_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pushes updated activity data back to the real Primavera P6 API and updates the local cache.
        """
        from models import P6Activity
        
        activity = db.query(P6Activity).filter(P6Activity.p6_object_id == p6_object_id).first()
        if not activity:
            return {"success": False, "message": f"Activity '{p6_object_id}' not found in local cache."}
            
        logger.info(f"[REAL P6 API] Preparing to push updates for Activity {p6_object_id}")
        
        # Reverse map database column names back to P6 API field names
        reverse_map = {v: k for k, v in ACTIVITY_FIELD_MAP.items()}
        
        # Pop resources from update_data so they don't break activity update mapping
        resources_data = update_data.pop('resources', None)
        
        p6_payload = {"ObjectId": p6_object_id}
        for key, value in update_data.items():
            if key in reverse_map:
                p6_field = reverse_map[key]
                    
                # Oracle P6 Status enum only accepts: Not Started, In Progress, Completed
                if p6_field == "Status":
                    if value not in ["Not Started", "In Progress", "Completed"]:
                        # try to map
                        if value == "On Track" or value == "Delayed":
                            p6_payload["Status"] = "In Progress"
                        else:
                            p6_payload["Status"] = value
                    else:
                        p6_payload["Status"] = value
                    continue
                    
                # Convert datetime to ISO 8601 string
                if isinstance(value, datetime):
                    p6_payload[p6_field] = value.strftime("%Y-%m-%dT%H:%M:%S")
                elif value is not None:
                    p6_payload[p6_field] = value
                
        # Send to P6 API
        endpoint = f"{self.base_url}/activity"
        try:
            # Send array of objects for bulk endpoint
            response = requests.put(endpoint, headers=self.headers, json=[p6_payload], timeout=30)
            
            # If 405 Method Not Allowed, fallback to POST
            if response.status_code == 405:
                response = requests.post(endpoint, headers=self.headers, json=p6_payload, timeout=30)
                
            response.raise_for_status()
            logger.info(f"[REAL P6 API] Successfully pushed updates for Activity {p6_object_id} to Oracle P6")
            
        except requests.exceptions.HTTPError as e:
            error_msg = e.response.text if hasattr(e, 'response') and e.response else str(e)
            logger.error(f"[REAL P6 API] Failed to push activity to P6: {error_msg}")
            # Fallback to single object PUT
            if e.response and e.response.status_code in (400, 404, 405):
                single_endpoint = f"{self.base_url}/activity/{p6_object_id}"
                single_payload = {k: v for k, v in p6_payload.items() if k != "ObjectId"}
                try:
                    fallback_res = requests.put(single_endpoint, headers=self.headers, json=single_payload, timeout=30)
                    fallback_res.raise_for_status()
                    logger.info(f"[REAL P6 API] Fallback successful for Activity {p6_object_id}")
                except Exception as ex:
                    fallback_msg = getattr(ex, 'response', None)
                    fallback_text = fallback_msg.text if fallback_msg else str(ex)
                    return {"success": False, "message": f"P6 API Error: {error_msg}. Fallback also failed: {fallback_text}"}
            else:
                return {"success": False, "message": f"P6 API Error: {error_msg}"}
        except Exception as e:
            logger.error(f"[REAL P6 API] Failed to push to P6: {e}")
            return {"success": False, "message": f"Connection Error: {str(e)}"}
        
        # If Activity API push successful, update local DB
        for key, value in update_data.items():
            if hasattr(activity, key):
                setattr(activity, key, value)
                
        # Now update resources if provided
        if resources_data:
            from models import P6ResourceAssignment
            for res_type, res_vals in resources_data.items():
                res_obj_id = res_vals.get("p6ObjectId")
                if not res_obj_id:
                    continue
                    
                # Prepare payload for /resourceAssignment endpoint
                res_payload = {"ObjectId": res_obj_id}
                if "plannedUnits" in res_vals:
                    res_payload["PlannedUnits"] = res_vals["plannedUnits"]
                if "actualUnits" in res_vals:
                    res_payload["ActualUnits"] = res_vals["actualUnits"]
                    
                if len(res_payload) > 1: # More than just ObjectId
                    res_endpoint = f"{self.base_url}/resourceAssignment"
                    try:
                        logger.info(f"[REAL P6 API] Pushing Resource {res_obj_id} updates: {res_payload}")
                        res_resp = requests.put(res_endpoint, headers=self.headers, json=[res_payload], timeout=30)
                        if res_resp.status_code == 405:
                            # Fallback single PUT
                            res_resp = requests.put(f"{res_endpoint}/{res_obj_id}", headers=self.headers, json={k: v for k, v in res_payload.items() if k != "ObjectId"}, timeout=30)
                        res_resp.raise_for_status()
                        
                        # Update local DB for resource
                        local_res = db.query(P6ResourceAssignment).filter(P6ResourceAssignment.p6_object_id == res_obj_id).first()
                        if local_res:
                            if "plannedUnits" in res_vals:
                                local_res.planned_units = res_vals["plannedUnits"]
                            if "actualUnits" in res_vals:
                                local_res.actual_units = res_vals["actualUnits"]
                            local_res.last_synced_at = datetime.utcnow()
                            
                    except Exception as e:
                        logger.error(f"[REAL P6 API] Failed to push resource {res_obj_id}: {e}")
                        # Not failing the whole request if a resource fails, but could handle this better
                        
        activity.last_synced_at = datetime.utcnow()
        db.commit()
        
        return {"success": True, "message": f"Successfully updated activity {p6_object_id} in P6."}

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
