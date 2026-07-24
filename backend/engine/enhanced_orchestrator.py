"""
Akasha Engine — Enhanced Orchestrator (v2.1)

Extends the existing orchestrator with data intelligence and visualization support.
Maintains backward compatibility while adding new capabilities:
- Deep data understanding via schema analyzer
- Intelligent response formatting
- Visualization generation on-demand
- Enhanced data retrieval
"""

import logging
from sqlalchemy.orm import Session
from engine.data_schema import DataSchemaAnalyzer
from engine.visualizations import VisualizationGenerator
from engine.response_formatter import IntelligentResponseFormatter
import models

logger = logging.getLogger(__name__)


class EnhancedChatOrchestrator:
    """Enhanced orchestrator with intelligence and visualization."""
    
    def __init__(self, db: Session):
        self.db = db
        self.schema_analyzer = DataSchemaAnalyzer(db)
        self.viz_generator = VisualizationGenerator(db)
        self.response_formatter = IntelligentResponseFormatter(db)
    
    # ============================================
    # Enhanced Data Gathering
    # ============================================
    
    def gather_comprehensive_project_context(self, project_id: str) -> dict:
        """Gather comprehensive context for accurate responses."""
        try:
            p6_context = self.schema_analyzer.get_p6_project_context(project_id)
            sap_context = self.schema_analyzer.get_sap_procurement_context(project_id)
            
            return {
                "project_id": project_id,
                "p6": p6_context,
                "sap": sap_context,
                "gathered_at": __import__('datetime').datetime.utcnow().isoformat(),
                "data_quality": self._assess_context_quality(p6_context, sap_context),
            }
        except Exception as e:
            logger.error(f"Error gathering context for {project_id}: {str(e)}")
            return {"error": str(e)}
    
    def _assess_context_quality(self, p6_context: dict, sap_context: dict) -> dict:
        """Assess the quality of gathered context."""
        p6_quality = p6_context.get("data_quality", {}).get("quality_rating", "UNKNOWN")
        
        return {
            "p6_quality": p6_quality,
            "sap_quality": "To be assessed",
            "integration_completeness": "Good" if p6_quality in ["EXCELLENT", "GOOD"] else "Fair",
        }
    
    # ============================================
    # Intent-Based Enhanced Processing
    # ============================================
    
    def process_factual_query(self, message: str, project_id: str, context: dict) -> dict:
        """Process factual questions with comprehensive data."""
        
        # Detect what the user is asking for
        question_lower = message.lower()
        
        if any(kw in question_lower for kw in ["status", "how", "what is", "tell me"]):
            response = self.response_formatter.format_project_status_response(project_id, message)
        
        elif any(kw in question_lower for kw in ["critical", "path", "delayed", "at risk"]):
            response = self.response_formatter.format_critical_activities_response(project_id)
        
        elif any(kw in question_lower for kw in ["budget", "cost", "spending", "spent"]):
            response = self.response_formatter.format_budget_analysis_response(project_id)
        
        elif any(kw in question_lower for kw in ["risk", "alert"]):
            response = self.response_formatter.format_risk_analysis_response(project_id)
        
        else:
            # Generic status response
            response = self.response_formatter.format_project_status_response(project_id, message)
        
        # Add visualization support
        if self.response_formatter.should_include_visualization(message):
            response = self._add_visualization_data(response)
        
        return response
    
    def process_analytical_query(self, message: str, project_ids: list, context: dict) -> dict:
        """Process analytical questions comparing/trending data."""
        
        question_lower = message.lower()
        
        if any(kw in question_lower for kw in ["compare", "vs", "which"]):
            response = self.response_formatter.format_portfolio_comparison(project_ids)
        
        elif any(kw in question_lower for kw in ["risk", "riskiest", "worst"]):
            response = self._format_portfolio_risks(project_ids)
        
        elif any(kw in question_lower for kw in ["trend", "over time", "progress"]):
            response = self._format_project_trends(project_ids)
        
        else:
            response = self.response_formatter.format_portfolio_comparison(project_ids)
        
        # Add visualizations
        if self.response_formatter.should_include_visualization(message):
            response = self._add_visualization_data(response)
        
        return response
    
    def process_advisory_query(self, message: str, project_ids: list, context: dict) -> dict:
        """Process advisory questions requiring recommendations."""
        
        response = {
            "type": "advisory",
            "answer": "Generating insights and recommendations...",
            "recommendations": [],
            "suggested_actions": [],
        }
        
        # Analyze risks for all projects
        all_insights = []
        for pid in project_ids:
            insights = self.schema_analyzer.generate_risk_insights(pid)
            all_insights.extend(insights)
        
        response["risks_identified"] = len(all_insights)
        response["insights"] = all_insights[:5]  # Top 5 insights
        response["suggested_actions"] = self.response_formatter._generate_recommendations(all_insights)
        
        return response
    
    # ============================================
    # Visualization Integration
    # ============================================
    
    def _add_visualization_data(self, response: dict) -> dict:
        """Add visualization data to response if applicable."""
        
        if "suggested_visualizations" in response:
            visualizations = []
            project_id = response.get("project_id")
            
            for viz_spec in response["suggested_visualizations"]:
                viz_type = viz_spec.get("type")
                
                try:
                    if project_id and viz_type in ["activity_status_pie", "budget_pie", "critical_activities_table"]:
                        viz_data = self.viz_generator.generate_visualization(viz_type, project_id)
                        visualizations.append({
                            "type": viz_type,
                            "data": viz_data,
                            "reason": viz_spec.get("reason"),
                        })
                    elif viz_type == "portfolio_risk_bubble":
                        viz_data = self.viz_generator.generate_portfolio_risk_bubble()
                        visualizations.append({
                            "type": viz_type,
                            "data": viz_data,
                            "reason": viz_spec.get("reason"),
                        })
                
                except Exception as e:
                    logger.error(f"Error generating visualization {viz_type}: {str(e)}")
            
            response["visualizations"] = visualizations
        
        return response
    
    # ============================================
    # Portfolio Analysis
    # ============================================
    
    def _format_portfolio_risks(self, project_ids: list) -> dict:
        """Format response analyzing portfolio risks."""
        
        all_risks = []
        for pid in project_ids:
            risks = self.schema_analyzer.generate_risk_insights(pid)
            all_risks.extend([(pid, r) for r in risks])
        
        # Sort by severity
        severity_map = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        all_risks.sort(
            key=lambda x: severity_map.get(x[1].get("severity", "LOW"), 0),
            reverse=True
        )
        
        return {
            "type": "portfolio_risks",
            "total_risks": len(all_risks),
            "high_severity": sum(1 for _, r in all_risks if r.get("severity") == "HIGH"),
            "medium_severity": sum(1 for _, r in all_risks if r.get("severity") == "MEDIUM"),
            "top_risks": all_risks[:5],
            "answer": f"Portfolio has {len(all_risks)} identified risks across {len(project_ids)} projects.",
        }
    
    def _format_project_trends(self, project_ids: list) -> dict:
        """Format response analyzing project trends."""
        
        return {
            "type": "trend_analysis",
            "project_count": len(project_ids),
            "answer": "Trend analysis feature - requires historical data snapshots",
            "note": "To enable accurate trend analysis, enable historical metrics snapshots in database",
        }
    
    # ============================================
    # Visualization Discovery
    # ============================================
    
    def get_available_visualizations_for_project(self, project_id: str) -> list:
        """Return list of available visualizations."""
        return self.viz_generator.get_available_visualizations(project_id)
    
    def generate_visualization(self, chart_type: str, project_id: str = None) -> dict:
        """Generate a specific visualization."""
        return self.viz_generator.generate_visualization(chart_type, project_id)
    
    # ============================================
    # Data Export & Reporting
    # ============================================
    
    def export_project_analysis(self, project_id: str, format: str = "json") -> dict:
        """Export comprehensive project analysis."""
        
        context = self.gather_comprehensive_project_context(project_id)
        insights = self.schema_analyzer.generate_risk_insights(project_id)
        visualizations = self.get_available_visualizations_for_project(project_id)
        
        export = {
            "project_id": project_id,
            "generated_at": __import__('datetime').datetime.utcnow().isoformat(),
            "context": context,
            "insights": insights,
            "available_visualizations": visualizations,
        }
        
        if format == "json":
            return export
        elif format == "csv":
            return {"note": "CSV export not yet implemented"}
        else:
            return export


# ============================================
# Integration Point for Existing Orchestrator
# ============================================

def enhance_existing_orchestrator(orchestrator_instance):
    """
    Decorator/mixin to add enhanced capabilities to existing orchestrator.
    Usage:
        orchestrator = ChatOrchestrator()
        enhanced = add_enhancements_to_orchestrator(orchestrator, db)
    """
    
    def wrapper(db: Session):
        enhanced = EnhancedChatOrchestrator(db)
        # Copy existing orchestrator methods
        for attr in dir(orchestrator_instance):
            if not attr.startswith("_") and attr not in dir(enhanced):
                setattr(enhanced, attr, getattr(orchestrator_instance, attr))
        return enhanced
    
    return wrapper
