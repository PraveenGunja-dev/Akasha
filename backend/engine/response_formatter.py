"""
Akasha Engine — Enhanced Response Formatter

Transforms raw data into intelligent, detailed responses with:
- Accurate, crisp answers with proper context
- Actionable insights and recommendations
- Visualization suggestions when data benefits from charts
- Data quality notes and caveats
- Sources and metadata
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from engine.data_schema import DataSchemaAnalyzer
from engine.visualizations import VisualizationGenerator

logger = logging.getLogger(__name__)


class IntelligentResponseFormatter:
    """Formats chatbot responses with intelligence and depth."""
    
    def __init__(self, db: Session):
        self.db = db
        self.schema_analyzer = DataSchemaAnalyzer(db)
        self.viz_generator = VisualizationGenerator(db)
    
    # ============================================
    # Project Status Queries
    # ============================================
    
    def format_project_status_response(self, project_id: str, question: str) -> Dict[str, Any]:
        """Format intelligent response to project status queries."""
        context = self.schema_analyzer.get_p6_project_context(project_id)
        
        if not context:
            return {"error": "Project not found", "project_id": project_id}
        
        # Build narrative answer
        answer = self._build_project_status_narrative(context)
        
        # Identify visualization opportunity
        visualizations = [
            {"type": "activity_status_pie", "reason": "Visual breakdown of activity status"},
            {"type": "critical_activities_table", "reason": "Details on critical path activities"},
        ]
        
        # Generate insights
        insights = self.schema_analyzer.generate_risk_insights(project_id)
        
        return {
            "type": "project_status",
            "project_id": project_id,
            "project_name": context.get("project_name"),
            "answer": answer,
            "health_status": context.get("overall_health"),
            "key_metrics": {
                "completion_percentage": context.get("schedule_metrics", {}).get("percent_complete"),
                "spi": context.get("cost_analysis", {}).get("schedule_performance"),
                "cpi": context.get("cost_analysis", {}).get("cost_performance"),
            },
            "insights": insights,
            "suggested_visualizations": visualizations,
            "data_quality": context.get("data_quality"),
            "last_update": context.get("last_update"),
        }
    
    def _build_project_status_narrative(self, context: Dict) -> str:
        """Build a natural language narrative of project status."""
        project_name = context.get("project_name", "Project")
        health = context.get("overall_health", "UNKNOWN")
        
        lines = [
            f"**Project Status: {health}**",
            "",
            f"**{project_name}** is currently at {context.get('schedule_metrics', {}).get('percent_complete', 0)}% completion.",
        ]
        
        # Schedule status
        schedule_analysis = context.get("schedule_analysis", {})
        if "float_analysis" in schedule_analysis:
            lines.append(f"Schedule: {schedule_analysis['float_analysis']}")
        
        if "variance_interpretation" in schedule_analysis:
            lines.append(f"Variance: {schedule_analysis['variance_interpretation']}")
        
        # Cost status
        cost_analysis = context.get("cost_analysis", {})
        if "cost_performance" in cost_analysis:
            lines.append(f"Cost: {cost_analysis['cost_performance']}")
        
        # Activity breakdown
        activities = context.get("activity_breakdown", {})
        if activities.get("total_activities"):
            lines.append(
                f"\n**Activity Status**: {activities.get('completed', 0)} completed, "
                f"{activities.get('in_progress', 0)} in progress, "
                f"{activities.get('not_started', 0)} not started "
                f"(out of {activities.get('total_activities')} total)"
            )
        
        return "\n".join(lines)
    
    # ============================================
    # Comparative Analysis
    # ============================================
    
    def format_portfolio_comparison(self, project_ids: List[str]) -> Dict[str, Any]:
        """Format response comparing multiple projects."""
        comparisons = self.schema_analyzer.compare_projects(project_ids)
        
        # Build comparison narrative
        answer = self._build_comparison_narrative(comparisons)
        
        return {
            "type": "portfolio_comparison",
            "project_count": len(comparisons),
            "answer": answer,
            "projects": comparisons,
            "suggested_visualizations": [
                {"type": "project_comparison_bar", "reason": "Compare completion, SPI, CPI across projects"},
                {"type": "portfolio_risk_bubble", "reason": "View all projects on risk matrix"},
            ],
            "summary_statistics": self._calculate_portfolio_statistics(comparisons),
        }
    
    def _build_comparison_narrative(self, comparisons: Dict) -> str:
        """Build narrative comparing projects."""
        lines = ["**Portfolio Comparison**", ""]
        
        # Sort by health
        sorted_projects = sorted(
            comparisons.items(),
            key=lambda x: {"HEALTHY": 3, "AT RISK": 2, "CRITICAL": 1}.get(x[1].get("health"), 0),
            reverse=True
        )
        
        for project_id, data in sorted_projects:
            health_icon = "🟢" if data["health"] == "HEALTHY" else "🟡" if data["health"] == "AT RISK" else "🔴"
            lines.append(
                f"{health_icon} **{data['name']}** - {data.get('completion_pct', 0)}% complete "
                f"(SPI: {data.get('spi', 'N/A')}, CPI: {data.get('cpi', 'N/A')})"
            )
        
        return "\n".join(lines)
    
    def _calculate_portfolio_statistics(self, comparisons: Dict) -> Dict[str, Any]:
        """Calculate aggregate portfolio statistics."""
        completions = [d.get("completion_pct", 0) for d in comparisons.values()]
        
        return {
            "total_projects": len(comparisons),
            "average_completion": sum(completions) / len(completions) if completions else 0,
            "critical_count": sum(1 for d in comparisons.values() if d.get("health") == "CRITICAL"),
            "at_risk_count": sum(1 for d in comparisons.values() if d.get("health") == "AT RISK"),
            "healthy_count": sum(1 for d in comparisons.values() if d.get("health") == "HEALTHY"),
        }
    
    # ============================================
    # Risk & Alert Analysis
    # ============================================
    
    def format_risk_analysis_response(self, project_id: str) -> Dict[str, Any]:
        """Format response with risk analysis and recommendations."""
        context = self.schema_analyzer.get_p6_project_context(project_id)
        insights = self.schema_analyzer.generate_risk_insights(project_id)
        
        # Build risk narrative
        answer = self._build_risk_narrative(context, insights)
        
        return {
            "type": "risk_analysis",
            "project_id": project_id,
            "project_name": context.get("project_name"),
            "answer": answer,
            "risks": insights,
            "risk_level": "HIGH" if len([i for i in insights if i.get("severity") == "HIGH"]) > 0 else "MEDIUM" if len(insights) > 0 else "LOW",
            "recommended_actions": self._generate_recommendations(insights),
            "suggested_visualizations": [
                {"type": "critical_activities_table", "reason": "View activities impacting risk"},
            ],
        }
    
    def _build_risk_narrative(self, context: Dict, insights: List[Dict]) -> str:
        """Build narrative describing project risks."""
        project_name = context.get("project_name", "Project")
        
        lines = [f"**Risk Analysis for {project_name}**", ""]
        
        if not insights:
            lines.append("No significant risks identified. Project appears to be on track.")
            return "\n".join(lines)
        
        lines.append(f"**{len(insights)} potential risk(s) identified:**\n")
        
        for insight in insights:
            severity = insight.get("severity", "MEDIUM")
            risk_type = insight.get("type", "UNKNOWN").replace("_", " ")
            insight_text = insight.get("insight", "")
            
            lines.append(f"🔴 **{severity}: {risk_type}**")
            lines.append(insight_text)
            lines.append("")
        
        return "\n".join(lines)
    
    def _generate_recommendations(self, insights: List[Dict]) -> List[str]:
        """Generate actionable recommendations based on risks."""
        recommendations = []
        
        for insight in insights:
            rec = insight.get("recommendation")
            if rec:
                recommendations.append(rec)
        
        return recommendations
    
    # ============================================
    # Activity & Milestone Analysis
    # ============================================
    
    def format_critical_activities_response(self, project_id: str, limit: int = 10) -> Dict[str, Any]:
        """Format response listing critical path activities."""
        import models
        
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {"error": "Project not found"}
        
        critical = self.db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id,
            models.P6Activity.total_float <= 0
        ).order_by(models.P6Activity.total_float.asc()).limit(limit).all()
        
        # Build narrative
        answer = self._build_critical_activities_narrative(p6, critical)
        
        return {
            "type": "critical_activities",
            "project_id": project_id,
            "project_name": p6.name,
            "answer": answer,
            "critical_count": len(critical),
            "activities": [
                {
                    "activity_id": a.activity_id,
                    "name": a.name,
                    "status": a.status,
                    "completion_pct": round(a.percent_complete, 1) if a.percent_complete else 0,
                    "float_hours": int(a.total_float) if a.total_float is not None else 0,
                    "early_start": a.early_start_date.isoformat() if a.early_start_date else None,
                    "early_finish": a.early_finish_date.isoformat() if a.early_finish_date else None,
                }
                for a in critical
            ],
            "suggested_visualizations": [
                {"type": "critical_activities_table", "reason": "Full table of critical activities"},
            ],
        }
    
    def _build_critical_activities_narrative(self, p6, activities: List) -> str:
        """Build narrative describing critical activities."""
        lines = [
            f"**Critical Path Analysis for {p6.name}**",
            "",
            f"Project has **{len(activities)} activities on the critical path** (zero or negative float).",
            "Any delay in these activities will directly delay project completion.",
        ]
        
        if activities:
            lines.append("\n**Top critical activities:**\n")
            for a in activities[:5]:
                status_icon = "✅" if a.percent_complete == 100 else "⏳" if a.percent_complete > 0 else "⏱️"
                completion = round(a.percent_complete, 0) if a.percent_complete else 0
                lines.append(
                    f"{status_icon} {a.name} - {completion}% complete "
                    f"(Float: {int(a.total_float)} hours)" if a.total_float is not None else ""
                )
        
        return "\n".join(lines)
    
    # ============================================
    # What-If / Scenario Analysis
    # ============================================
    
    def format_whatif_scenario_response(self, project_id: str, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Format response to what-if scenario questions."""
        # This would integrate with simulation tools
        
        return {
            "type": "scenario_analysis",
            "project_id": project_id,
            "scenario": scenario,
            "answer": "Scenario analysis feature - to be enhanced with simulation engine",
            "results": {},
            "suggested_visualizations": [],
        }
    
    # ============================================
    # Budget & Cost Analysis
    # ============================================
    
    def format_budget_analysis_response(self, project_id: str) -> Dict[str, Any]:
        """Format response to budget and cost queries."""
        context = self.schema_analyzer.get_p6_project_context(project_id)
        cost_analysis = context.get("cost_analysis", {})
        
        # Build narrative
        answer = self._build_budget_narrative(context)
        
        return {
            "type": "budget_analysis",
            "project_id": project_id,
            "project_name": context.get("project_name"),
            "answer": answer,
            "cost_metrics": cost_analysis.get("budget_status", {}),
            "cost_performance": cost_analysis.get("cost_performance"),
            "suggested_visualizations": [
                {"type": "budget_pie", "reason": "Visual breakdown of spent vs remaining budget"},
                {"type": "cumulative_cost_line", "reason": "Cost trend over time"},
            ],
        }
    
    def _build_budget_narrative(self, context: Dict) -> str:
        """Build narrative about budget status."""
        budget_status = context.get("cost_analysis", {}).get("budget_status", {})
        project_name = context.get("project_name", "Project")
        
        lines = [f"**Budget Analysis for {project_name}**", ""]
        
        total_budget = budget_status.get("total_budget")
        spent = budget_status.get("spent_amount", 0)
        spent_pct = budget_status.get("spent_percentage", 0)
        remaining = budget_status.get("remaining_budget", 0)
        
        lines.append(f"**Total Budget:** ${total_budget:,.2f}")
        lines.append(f"**Spent:** ${spent:,.2f} ({spent_pct}%)")
        lines.append(f"**Remaining:** ${remaining:,.2f}")
        lines.append("")
        lines.append(f"**Status:** {budget_status.get('status', 'UNKNOWN')}")
        
        if spent_pct > 100:
            lines.append(f"⚠️ **Project is OVER BUDGET by ${spent - total_budget:,.2f}**")
        elif spent_pct > 80:
            lines.append("⚠️ Budget is approaching limit - cost control measures recommended")
        else:
            lines.append("✅ Budget is on track")
        
        return "\n".join(lines)
    
    # ============================================
    # Material & Procurement Analysis
    # ============================================
    
    def format_procurement_response(self, project_id: str) -> Dict[str, Any]:
        """Format response to procurement and material queries."""
        context = self.schema_analyzer.get_sap_procurement_context(project_id)
        
        return {
            "type": "procurement",
            "project_id": project_id,
            "answer": "Procurement analysis - connecting to SAP data",
            "material_summary": context.get("material_summary"),
            "vendor_summary": context.get("vendor_summary"),
            "health": context.get("procurement_health"),
            "suggested_visualizations": [
                {"type": "material_status_table", "reason": "View material delivery gaps"},
            ],
        }
    
    # ============================================
    # Utility Methods
    # ============================================
    
    def should_include_visualization(self, question: str) -> bool:
        """Determine if question warrants visualization."""
        viz_keywords = [
            "show", "graph", "chart", "pie", "bar", "line", "visualiz",
            "compare", "breakdown", "distribution", "trend", "over time",
            "picture", "diagram", "plot", "see the", "display"
        ]
        
        return any(kw in question.lower() for kw in viz_keywords)
    
    def enrich_response_with_metadata(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Add metadata to responses."""
        response["generated_at"] = datetime.utcnow().isoformat()
        response["version"] = "2.1"
        response["capabilities"] = [
            "project_status",
            "risk_analysis",
            "budget_tracking",
            "critical_path",
            "portfolio_comparison",
        ]
        
        return response
