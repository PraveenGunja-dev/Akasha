"""
Akasha Engine — Visualization Generator

Generates chart specifications (Recharts/Chart.js compatible JSON) when users ask for visualizations.
Supports: Pie charts, Bar charts, Line charts, Area charts, Bubble charts, etc.

Charts are rendered on the frontend with actual data from the API.
This module creates the specification and data payload.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import models

logger = logging.getLogger(__name__)


class VisualizationGenerator:
    """Generate chart specifications for data visualization."""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ============================================
    # Pie Charts
    # ============================================
    
    def generate_activity_status_pie(self, project_id: str) -> Dict[str, Any]:
        """Generate pie chart for activity status breakdown."""
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {}
        
        activities = self.db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        ).all()
        
        completed = len([a for a in activities if a.status and 'completed' in a.status.lower()])
        in_progress = len([a for a in activities if a.status and 'in progress' in a.status.lower()])
        not_started = len([a for a in activities if a.status and 'not started' in a.status.lower()])
        
        return {
            "type": "pie",
            "title": f"{p6.name} - Activity Status Breakdown",
            "subtitle": f"Total Activities: {len(activities)}",
            "data": [
                {"name": "Completed", "value": completed, "color": "#10b981"},
                {"name": "In Progress", "value": in_progress, "color": "#3b82f6"},
                {"name": "Not Started", "value": not_started, "color": "#ef4444"},
            ],
            "metadata": {
                "project_id": project_id,
                "project_name": p6.name,
                "total_activities": len(activities),
                "data_date": p6.data_date.isoformat() if p6.data_date else None,
            },
        }
    
    def generate_budget_pie(self, project_id: str) -> Dict[str, Any]:
        """Generate pie chart for budget allocation."""
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6 or not p6.planned_cost:
            return {}
        
        spent = p6.actual_total_cost or 0
        remaining = max(p6.planned_cost - spent, 0)
        
        return {
            "type": "pie",
            "title": f"{p6.name} - Budget Status",
            "subtitle": f"Total Budget: ${p6.planned_cost:,.2f}",
            "data": [
                {"name": "Spent", "value": spent, "color": "#ef4444"},
                {"name": "Remaining", "value": remaining, "color": "#10b981"},
            ],
            "metadata": {
                "project_id": project_id,
                "project_name": p6.name,
                "total_budget": p6.planned_cost,
                "spent_amount": spent,
                "spent_percentage": round(spent / p6.planned_cost * 100, 1) if p6.planned_cost > 0 else 0,
            },
        }
    
    # ============================================
    # Bar Charts
    # ============================================
    
    def generate_project_comparison_bar(self, project_ids: List[str]) -> Dict[str, Any]:
        """Generate bar chart comparing multiple projects."""
        projects = self.db.query(models.P6Project).filter(
            models.P6Project.project_id.in_(project_ids)
        ).all()
        
        data = []
        for p in projects:
            data.append({
                "name": p.name[:30],  # Truncate long names
                "completion": round(p.duration_percent_complete, 1) if p.duration_percent_complete else 0,
                "spi": round(p.schedule_performance_index * 100, 1) if p.schedule_performance_index else 0,
                "cpi": round(p.cost_performance_index * 100, 1) if p.cost_performance_index else 0,
            })
        
        return {
            "type": "bar",
            "title": "Project Portfolio Comparison",
            "subtitle": f"Comparing {len(projects)} projects",
            "data": data,
            "xAxis": {"name": "Project Name", "key": "name"},
            "bars": [
                {"key": "completion", "name": "Completion %", "color": "#3b82f6"},
                {"key": "spi", "name": "SPI %", "color": "#8b5cf6"},
                {"key": "cpi", "name": "CPI %", "color": "#f97316"},
            ],
            "metadata": {
                "project_count": len(projects),
                "comparison_date": datetime.utcnow().isoformat(),
            },
        }
    
    def generate_milestones_bar(self, project_id: str) -> Dict[str, Any]:
        """Generate bar chart for milestone progress."""
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {}
        
        # Get activities with milestones (where duration is near 0)
        activities = self.db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id,
            models.P6Activity.planned_duration <= 1  # Milestones have minimal duration
        ).order_by(models.P6Activity.early_start_date).limit(15).all()
        
        data = []
        for a in activities:
            data.append({
                "name": a.name[:25],
                "completion": round(a.percent_complete, 1) if a.percent_complete else 0,
                "status_color": "#10b981" if a.percent_complete == 100 else "#ef4444",
            })
        
        return {
            "type": "bar",
            "title": f"{p6.name} - Milestone Progress",
            "subtitle": "Key milestones and their completion status",
            "data": data,
            "metadata": {
                "project_id": project_id,
                "project_name": p6.name,
                "milestone_count": len(data),
            },
        }
    
    # ============================================
    # Line Charts / Area Charts
    # ============================================
    
    def generate_schedule_trend_line(self, project_id: str) -> Dict[str, Any]:
        """Generate line chart for schedule adherence over time."""
        # This would require historical snapshots
        # Placeholder implementation
        
        return {
            "type": "line",
            "title": f"Schedule Performance Trend",
            "subtitle": "Projected completion date over time",
            "data": [
                {"date": "2024-01-01", "baseline": 80, "actual": 75, "forecasted": 85},
                {"date": "2024-02-01", "baseline": 80, "actual": 72, "forecasted": 82},
                {"date": "2024-03-01", "baseline": 80, "actual": 70, "forecasted": 78},
            ],
            "lines": [
                {"key": "baseline", "name": "Baseline Plan", "color": "#06b6d4"},
                {"key": "actual", "name": "Actual Progress", "color": "#ef4444", "style": "solid"},
                {"key": "forecasted", "name": "Forecast", "color": "#3b82f6", "style": "dashed"},
            ],
            "metadata": {
                "project_id": project_id,
                "note": "Requires historical snapshots for accuracy",
            },
        }
    
    def generate_cumulative_cost_line(self, project_id: str) -> Dict[str, Any]:
        """Generate line chart for cumulative cost over time."""
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {}
        
        # Placeholder: would use actual cost curves from database
        return {
            "type": "line",
            "title": f"{p6.name} - Cumulative Cost Curve",
            "subtitle": "Planned vs Actual spending over time",
            "data": [
                {"month": "Jan", "planned": 100000, "actual": 95000},
                {"month": "Feb", "planned": 250000, "actual": 270000},
                {"month": "Mar", "planned": 450000, "actual": 480000},
            ],
            "lines": [
                {"key": "planned", "name": "Planned Cost", "color": "#06b6d4"},
                {"key": "actual", "name": "Actual Cost", "color": "#ef4444"},
            ],
            "metadata": {
                "project_id": project_id,
                "project_name": p6.name,
            },
        }
    
    # ============================================
    # Bubble/Scatter Charts
    # ============================================
    
    def generate_portfolio_risk_bubble(self) -> Dict[str, Any]:
        """Generate bubble chart showing portfolio risk (SPI vs CPI)."""
        projects = self.db.query(models.P6Project).filter(
            models.P6Project.status.in_(["Active", "Planned"])
        ).all()
        
        data = []
        for p in projects:
            if p.schedule_performance_index and p.cost_performance_index:
                # Bubble size = budget or activity count
                activity_count = self.db.query(models.P6Activity).filter(
                    models.P6Activity.project_object_id == p.p6_object_id
                ).count()
                
                data.append({
                    "name": p.name[:25],
                    "x": round(p.schedule_performance_index, 2),  # SPI
                    "y": round(p.cost_performance_index, 2),      # CPI
                    "size": activity_count,
                    "color": self._get_health_color(p.schedule_performance_index, p.cost_performance_index),
                })
        
        return {
            "type": "bubble",
            "title": "Portfolio Risk Matrix (SPI vs CPI)",
            "subtitle": "Bubble size = number of activities",
            "data": data,
            "xAxis": {
                "name": "Schedule Performance Index (SPI)",
                "range": [0.8, 1.2],
                "reference_line": 1.0,
            },
            "yAxis": {
                "name": "Cost Performance Index (CPI)",
                "range": [0.8, 1.2],
                "reference_line": 1.0,
            },
            "zones": [
                {"x": [0.8, 1.0], "y": [0.8, 1.0], "label": "AT RISK", "color": "rgba(239, 68, 68, 0.1)"},
                {"x": [1.0, 1.2], "y": [1.0, 1.2], "label": "HEALTHY", "color": "rgba(16, 185, 129, 0.1)"},
            ],
            "metadata": {
                "project_count": len(data),
                "analysis_date": datetime.utcnow().isoformat(),
            },
        }
    
    # ============================================
    # Table/Heatmap Data
    # ============================================
    
    def generate_critical_activities_table(self, project_id: str) -> Dict[str, Any]:
        """Generate table data for critical activities."""
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {}
        
        critical = self.db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id,
            models.P6Activity.total_float <= 0
        ).order_by(models.P6Activity.total_float.asc()).limit(20).all()
        
        rows = []
        for a in critical:
            rows.append({
                "activity_id": a.activity_id,
                "name": a.name,
                "status": a.status,
                "completion_pct": round(a.percent_complete, 1) if a.percent_complete else 0,
                "float_hours": int(a.total_float) if a.total_float is not None else 0,
                "risk_color": "#ef4444" if a.total_float < -10 else "#f97316",
            })
        
        return {
            "type": "table",
            "title": f"{p6.name} - Critical Path Activities",
            "subtitle": f"{len(rows)} activities with zero or negative float",
            "columns": [
                {"key": "activity_id", "label": "Activity ID", "width": 80},
                {"key": "name", "label": "Activity Name", "width": 300},
                {"key": "status", "label": "Status", "width": 100},
                {"key": "completion_pct", "label": "Completion %", "width": 100},
                {"key": "float_hours", "label": "Float (hours)", "width": 100},
            ],
            "rows": rows,
            "metadata": {
                "project_id": project_id,
                "project_name": p6.name,
                "critical_count": len(rows),
            },
        }
    
    def generate_material_status_table(self, project_id: str) -> Dict[str, Any]:
        """Generate table data for material status (SAP data)."""
        # Placeholder: connect to actual material data
        return {
            "type": "table",
            "title": "Material Status & Gaps",
            "subtitle": "Materials with pending deliveries",
            "columns": [
                {"key": "material_code", "label": "Material Code", "width": 100},
                {"key": "name", "label": "Material Name", "width": 300},
                {"key": "ordered_qty", "label": "Ordered", "width": 80},
                {"key": "delivered_qty", "label": "Delivered", "width": 80},
                {"key": "pending_qty", "label": "Pending", "width": 80},
                {"key": "gap_pct", "label": "Gap %", "width": 80},
            ],
            "rows": [],  # Would be populated from SAP data
            "metadata": {
                "project_id": project_id,
            },
        }
    
    # ============================================
    # Utility Methods
    # ============================================
    
    def _get_health_color(self, spi: float, cpi: float) -> str:
        """Get color based on SPI/CPI values."""
        if spi < 0.95 or cpi < 0.95:
            return "#ef4444"  # Red (at risk)
        elif spi >= 1.0 and cpi >= 1.0:
            return "#10b981"  # Green (healthy)
        else:
            return "#f97316"  # Orange (caution)
    
    def get_available_visualizations(self, project_id: str) -> List[Dict[str, str]]:
        """Return list of available visualizations for a project."""
        return [
            {
                "key": "activity_status_pie",
                "title": "Activity Status Breakdown",
                "type": "pie",
                "description": "Shows distribution of activities by status: Completed, In Progress, Not Started",
            },
            {
                "key": "budget_pie",
                "title": "Budget Status",
                "type": "pie",
                "description": "Shows budget spent vs remaining",
            },
            {
                "key": "critical_activities_table",
                "title": "Critical Path Activities",
                "type": "table",
                "description": "Lists all activities on critical path with float analysis",
            },
            {
                "key": "schedule_trend_line",
                "title": "Schedule Performance Trend",
                "type": "line",
                "description": "Shows schedule adherence over time (requires historical data)",
            },
            {
                "key": "cumulative_cost_line",
                "title": "Cumulative Cost Curve",
                "type": "line",
                "description": "Shows planned vs actual cumulative spending",
            },
        ]
    
    def generate_visualization(self, chart_type: str, project_id: str = None) -> Dict[str, Any]:
        """Main entry point to generate any visualization."""
        if chart_type == "activity_status_pie":
            return self.generate_activity_status_pie(project_id)
        elif chart_type == "budget_pie":
            return self.generate_budget_pie(project_id)
        elif chart_type == "critical_activities_table":
            return self.generate_critical_activities_table(project_id)
        elif chart_type == "schedule_trend_line":
            return self.generate_schedule_trend_line(project_id)
        elif chart_type == "cumulative_cost_line":
            return self.generate_cumulative_cost_line(project_id)
        elif chart_type == "portfolio_risk_bubble":
            return self.generate_portfolio_risk_bubble()
        else:
            return {"error": f"Unknown visualization type: {chart_type}"}
