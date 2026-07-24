"""
Akasha Engine — Data Schema Understanding Module

Deeply analyzes your database and data structures to provide accurate context for LLM responses.
Builds a detailed understanding of:
- Available metrics and their definitions
- Data relationships and hierarchies
- Historical context and trends
- Quality and completeness of data
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import models

logger = logging.getLogger(__name__)


class DataSchemaAnalyzer:
    """Deep data understanding for accurate, intelligent responses."""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ============================================
    # P6 Schedule Metrics & Context
    # ============================================
    
    def get_p6_project_context(self, project_id: str) -> dict:
        """Get comprehensive P6 project context with metrics definitions."""
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {}
        
        # Activity breakdown
        activities = self.db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        ).all()
        
        activity_statuses = self._analyze_activity_status(activities)
        
        # Schedule analysis
        schedule_analysis = {
            "baseline_vs_current": self._analyze_baseline_variance(p6),
            "critical_path": self._analyze_critical_path(p6, activities),
            "float_analysis": self._interpret_float(p6.total_float),
            "variance_interpretation": self._interpret_schedule_variance(p6),
        }
        
        # Cost analysis
        cost_analysis = {
            "cost_performance": self._interpret_cpi(p6.cost_performance_index),
            "schedule_performance": self._interpret_spi(p6.schedule_performance_index),
            "variance_interpretation": self._interpret_cost_variance(p6),
            "budget_status": self._analyze_budget_status(p6),
        }
        
        return {
            "project_id": project_id,
            "project_name": p6.name,
            "status": p6.status,
            "overall_health": self._determine_project_health(p6, activity_statuses),
            "schedule_metrics": {
                "planned_duration_days": int(p6.planned_duration) if p6.planned_duration else None,
                "actual_duration_days": int(p6.actual_duration) if p6.actual_duration else None,
                "remaining_duration_days": int(p6.remaining_duration) if p6.remaining_duration else None,
                "percent_complete": round(p6.duration_percent_complete, 1) if p6.duration_percent_complete else None,
                "scheduled_finish": p6.scheduled_finish_date,
                "contractual_deadline": p6.must_finish_by_date,
            },
            "activity_breakdown": activity_statuses,
            "schedule_analysis": schedule_analysis,
            "cost_analysis": cost_analysis,
            "last_update": p6.data_date or p6.last_synced_at,
            "data_quality": self._assess_p6_data_quality(p6),
        }
    
    def _analyze_activity_status(self, activities: list) -> dict:
        """Analyze activity status distribution with insights."""
        completed = [a for a in activities if a.status and 'completed' in a.status.lower()]
        in_progress = [a for a in activities if a.status and 'in progress' in a.status.lower()]
        not_started = [a for a in activities if a.status and 'not started' in a.status.lower()]
        
        total = len(activities)
        completion_pct = (len(completed) / total * 100) if total > 0 else 0
        
        return {
            "total_activities": total,
            "completed": len(completed),
            "in_progress": len(in_progress),
            "not_started": len(not_started),
            "completion_percentage": round(completion_pct, 1),
            "in_progress_percentage": round(len(in_progress) / total * 100, 1) if total > 0 else 0,
            "is_on_track": completion_pct >= 50,  # Simple heuristic
        }
    
    def _analyze_baseline_variance(self, p6) -> dict:
        """Analyze variation from baseline schedule."""
        if not p6.baseline_start_date or not p6.start_date:
            return {"status": "No baseline available"}
        
        start_variance = (p6.start_date - p6.baseline_start_date).days
        finish_variance = (p6.scheduled_finish_date - p6.baseline_finish_date).days if p6.baseline_finish_date else None
        
        return {
            "start_variance_days": start_variance,
            "finish_variance_days": finish_variance,
            "interpretation": self._interpret_date_variance(start_variance, finish_variance),
        }
    
    def _analyze_critical_path(self, p6, activities: list) -> dict:
        """Analyze critical path health."""
        critical = [a for a in activities if a.total_float is not None and a.total_float <= 0]
        
        return {
            "total_critical_activities": len(critical),
            "critical_percentage": round(len(critical) / len(activities) * 100, 1) if activities else 0,
            "risk_level": "HIGH" if len(critical) > 10 else "MEDIUM" if len(critical) > 5 else "LOW",
        }
    
    def _interpret_float(self, total_float) -> str:
        """Interpret what float value means."""
        if total_float is None:
            return "Float data not available"
        if total_float <= 0:
            return "CRITICAL: Project is on critical path, no buffer"
        elif total_float <= 7:  # 7 days
            return "TIGHT: Minimal schedule buffer (< 7 days)"
        elif total_float <= 30:
            return "MODERATE: Some schedule flexibility (1-4 weeks)"
        else:
            return "COMFORTABLE: Adequate schedule buffer (> 4 weeks)"
    
    def _interpret_schedule_variance(self, p6) -> str:
        """Interpret schedule performance."""
        if not p6.schedule_performance_index:
            return "Schedule performance data not available"
        
        spi = p6.schedule_performance_index
        if spi < 0.9:
            return f"BEHIND SCHEDULE: {round((1-spi)*100, 1)}% behind"
        elif spi < 1.0:
            return f"Slightly behind: {round((1-spi)*100, 1)}% behind"
        elif spi > 1.0:
            return f"AHEAD OF SCHEDULE: {round((spi-1)*100, 1)}% ahead"
        else:
            return "On schedule"
    
    def _interpret_cpi(self, cpi) -> str:
        """Interpret Cost Performance Index."""
        if not cpi:
            return "Cost performance data not available"
        
        if cpi < 0.9:
            return f"OVER BUDGET: Spending {round(100/cpi * 100, 1)}% of budgeted costs"
        elif cpi < 1.0:
            return f"Slightly over budget: {round((1-cpi)*100, 1)}% over"
        elif cpi > 1.0:
            return f"UNDER BUDGET: {round((cpi-1)*100, 1)}% under budget"
        else:
            return "On budget"
    
    def _interpret_spi(self, spi) -> str:
        """Interpret Schedule Performance Index."""
        if not spi:
            return "Schedule performance data not available"
        
        if spi < 0.9:
            return f"SIGNIFICANTLY DELAYED: {round((1-spi)*100, 1)}% behind"
        elif spi < 1.0:
            return f"Slightly behind schedule: {round((1-spi)*100, 1)}% behind"
        elif spi >= 1.0:
            return f"Ahead/on schedule: {round((spi-1)*100, 1)}% ahead"
        else:
            return "On schedule"
    
    def _analyze_budget_status(self, p6) -> dict:
        """Analyze budget consumption and forecast."""
        if not p6.planned_cost or not p6.actual_total_cost:
            return {"status": "Budget data not available"}
        
        spent_pct = (p6.actual_total_cost / p6.planned_cost * 100) if p6.planned_cost > 0 else 0
        
        return {
            "planned_budget": p6.planned_cost,
            "actual_spent": p6.actual_total_cost,
            "spent_percentage": round(spent_pct, 1),
            "remaining_budget": p6.planned_cost - p6.actual_total_cost,
            "status": "OVERSPEND" if spent_pct > 100 else "ON TRACK" if spent_pct > 80 else "UNDER BUDGET",
        }
    
    def _interpret_date_variance(self, start_var, finish_var) -> str:
        """Interpret date variance."""
        if finish_var is None:
            return f"Start drifted {start_var} days from baseline"
        
        if abs(finish_var) <= 3:
            return f"Minor finish date drift: {finish_var} days"
        elif finish_var > 0:
            return f"DELAYED: {finish_var} days behind baseline finish"
        else:
            return f"Early: {abs(finish_var)} days ahead of baseline"
    
    def _determine_project_health(self, p6, activity_statuses) -> str:
        """Determine overall project health status."""
        risks = 0
        
        # Check schedule
        if p6.schedule_performance_index and p6.schedule_performance_index < 0.95:
            risks += 2
        
        # Check cost
        if p6.cost_performance_index and p6.cost_performance_index < 0.95:
            risks += 2
        
        # Check float
        if p6.total_float is not None and p6.total_float <= 0:
            risks += 1
        
        # Check completion
        if activity_statuses.get("completion_percentage", 0) < 25:
            risks += 1
        
        if risks >= 4:
            return "CRITICAL"
        elif risks >= 2:
            return "AT RISK"
        else:
            return "HEALTHY"
    
    def _assess_p6_data_quality(self, p6) -> dict:
        """Assess the quality and completeness of data."""
        completeness_score = 0
        total_checks = 0
        
        checks = [
            (p6.start_date is not None, "start_date"),
            (p6.finish_date is not None, "finish_date"),
            (p6.planned_duration is not None, "planned_duration"),
            (p6.actual_duration is not None, "actual_duration"),
            (p6.duration_percent_complete is not None, "duration_percent_complete"),
            (p6.cost_performance_index is not None, "cost_performance_index"),
            (p6.schedule_performance_index is not None, "schedule_performance_index"),
        ]
        
        for check, name in checks:
            total_checks += 1
            if check:
                completeness_score += 1
        
        quality_pct = (completeness_score / total_checks * 100) if total_checks > 0 else 0
        
        return {
            "completeness_percentage": round(quality_pct, 1),
            "fields_populated": completeness_score,
            "total_fields": total_checks,
            "quality_rating": "EXCELLENT" if quality_pct > 90 else "GOOD" if quality_pct > 70 else "FAIR" if quality_pct > 50 else "POOR",
        }
    
    # ============================================
    # SAP Procurement Metrics & Context
    # ============================================
    
    def get_sap_procurement_context(self, project_id: str) -> dict:
        """Get comprehensive SAP procurement context."""
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {}
        
        # Get material and vendor data
        materials = self._get_material_analysis(project_id)
        vendors = self._get_vendor_analysis(project_id)
        inventory = self._get_inventory_context(project_id)
        
        return {
            "project_id": project_id,
            "material_summary": materials,
            "vendor_summary": vendors,
            "inventory_summary": inventory,
            "procurement_health": self._determine_procurement_health(materials, vendors),
            "last_update": datetime.utcnow(),
        }
    
    def _get_material_analysis(self, project_id: str) -> dict:
        """Analyze material status and gaps."""
        # This would query actual material data from SAP models
        # Placeholder for now
        return {
            "total_materials": "To be calculated",
            "delivered_percentage": "To be calculated",
            "at_risk_materials": "To be calculated",
        }
    
    def _get_vendor_analysis(self, project_id: str) -> dict:
        """Analyze vendor performance."""
        return {
            "total_vendors": "To be calculated",
            "on_time_percentage": "To be calculated",
            "at_risk_vendors": "To be calculated",
        }
    
    def _get_inventory_context(self, project_id: str) -> dict:
        """Analyze current inventory status."""
        return {
            "total_inventory_value": "To be calculated",
            "stock_status": "To be calculated",
        }
    
    def _determine_procurement_health(self, materials, vendors) -> str:
        """Determine procurement health status."""
        # Placeholder logic
        return "HEALTHY"
    
    # ============================================
    # Comparative Analytics
    # ============================================
    
    def compare_projects(self, project_ids: list) -> dict:
        """Compare multiple projects side by side."""
        comparisons = {}
        
        for pid in project_ids:
            project = self.db.query(models.P6Project).filter(
                models.P6Project.project_id == pid
            ).first()
            
            if project:
                comparisons[pid] = {
                    "name": project.name,
                    "completion_pct": project.duration_percent_complete,
                    "spi": project.schedule_performance_index,
                    "cpi": project.cost_performance_index,
                    "health": self._determine_project_health(project, {}),
                }
        
        return comparisons
    
    # ============================================
    # Trend Analysis
    # ============================================
    
    def get_project_trends(self, project_id: str, days: int = 30) -> dict:
        """Get historical trends for a project."""
        # This would query historical snapshots if available
        # For now, placeholder
        return {
            "days_analyzed": days,
            "trends": "Historical data to be analyzed",
        }
    
    # ============================================
    # Risk & Insight Generation
    # ============================================
    
    def generate_risk_insights(self, project_id: str) -> list[dict]:
        """Generate actionable risk insights."""
        project_context = self.get_p6_project_context(project_id)
        insights = []
        
        # Schedule risk
        if project_context.get("schedule_analysis", {}).get("float_analysis"):
            float_interp = project_context["schedule_analysis"]["float_analysis"]
            if "CRITICAL" in float_interp or "TIGHT" in float_interp:
                insights.append({
                    "type": "SCHEDULE_RISK",
                    "severity": "HIGH",
                    "insight": float_interp,
                    "recommendation": "Review critical path activities and expedite where possible",
                })
        
        # Cost risk
        cpi = project_context.get("cost_analysis", {}).get("cost_performance")
        if cpi and "OVER" in cpi:
            insights.append({
                "type": "COST_RISK",
                "severity": "HIGH",
                "insight": cpi,
                "recommendation": "Review cost drivers and implement cost control measures",
            })
        
        # Progress risk
        completion = project_context.get("schedule_metrics", {}).get("percent_complete", 0)
        if completion < 25:
            insights.append({
                "type": "PROGRESS_RISK",
                "severity": "MEDIUM",
                "insight": f"Project only {completion}% complete",
                "recommendation": "Accelerate resource allocation to critical activities",
            })
        
        return insights
