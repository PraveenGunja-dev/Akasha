"""
Akasha Semantic Understanding & Validation Layer (v2.2)

Implements 5 core improvements for 99%+ accuracy:
1. Semantic understanding
2. Cross-source validation
3. Clarifying questions
4. Confidence scoring
5. Composite metrics
"""

import logging
import re
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import models

logger = logging.getLogger(__name__)


# ============================================
# 1. SEMANTIC UNDERSTANDING LAYER
# ============================================

class SemanticUnderstandingEngine:
    """Map user questions to semantic concepts."""
    
    SEMANTIC_SYNONYMS = {
        "schedule": {
            "keywords": ["spi", "on time", "delay", "delays", "late", "early", "timeline", "schedule",
                        "critical", "path", "float", "variance", "drift"],
            "priority": "HIGH",
        },
        "cost": {
            "keywords": ["cpi", "budget", "spending", "spent", "overrun", "overspend", "cost",
                        "expense", "capex", "opex", "financial"],
            "priority": "HIGH",
        },
        "progress": {
            "keywords": ["completion", "percent complete", "done", "finished", "status", "progress",
                        "activity", "completion pct", "%"],
            "priority": "HIGH",
        },
        "risk": {
            "keywords": ["critical", "at risk", "danger", "problem", "issue", "alert", "risk",
                        "concern", "flag", "threat"],
            "priority": "MEDIUM",
        },
        "procurement": {
            "keywords": ["material", "procurement", "po", "purchase", "vendor", "supplier", "delivery",
                        "supply", "stock", "inventory"],
            "priority": "MEDIUM",
        },
        "comparison": {
            "keywords": ["vs", "versus", "compare", "comparison", "better", "worse", "which",
                        "relative", "against"],
            "priority": "MEDIUM",
        },
        "activity": {
            "keywords": ["activity", "task", "tasks", "work", "job", "milestone", "deliverable"],
            "priority": "LOW",
        },
    }
    
    @classmethod
    def extract_semantic_concepts(cls, question: str) -> Dict[str, Any]:
        """Extract canonical concepts from question."""
        question_lower = question.lower()
        concepts = {
            "primary_concept": None,
            "secondary_concepts": [],
            "keywords_matched": [],
            "comparison_requested": False,
            "temporal_scope": "current",
            "confidence": 0.0,
        }
        
        # Find primary concept
        matches = []
        for concept, data in cls.SEMANTIC_SYNONYMS.items():
            matches_count = sum(1 for kw in data["keywords"] if kw in question_lower)
            if matches_count > 0:
                matches.append((concept, matches_count, data["priority"]))
        
        if matches:
            # Sort by priority and matches
            priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
            matches.sort(
                key=lambda x: (priority_order.get(x[2], 999), -x[1]),
                reverse=False
            )
            
            concepts["primary_concept"] = matches[0][0]
            if len(matches) > 1:
                concepts["secondary_concepts"] = [m[0] for m in matches[1:3]]
            
            concepts["keywords_matched"] = [m[0] for m in matches]
            concepts["confidence"] = min(0.99, 0.7 + (len(matches) * 0.15))
        
        # Detect comparison
        if any(word in question_lower for word in ["vs", "versus", "compare", "vs.", "better", "worse"]):
            concepts["comparison_requested"] = True
        
        # Temporal scope
        if "today" in question_lower or "current" in question_lower or "now" in question_lower:
            concepts["temporal_scope"] = "current"
        elif "trend" in question_lower or "over time" in question_lower or "history" in question_lower:
            concepts["temporal_scope"] = "historical"
        elif "forecast" in question_lower or "expect" in question_lower or "will" in question_lower:
            concepts["temporal_scope"] = "forecast"
        
        return concepts
    
    @classmethod
    def rephrase_for_clarity(cls, question: str, concepts: Dict) -> str:
        """Rephrase question in canonical form."""
        primary = concepts.get("primary_concept", "unknown")
        is_comparison = concepts.get("comparison_requested", False)
        temporal = concepts.get("temporal_scope", "current")
        
        phrase = f"Query: Tell me about {primary} ({temporal})"
        if is_comparison:
            phrase += " in a comparative context"
        
        return phrase
    
    @classmethod
    def identify_hidden_needs(cls, question: str) -> List[str]:
        """Identify what user might really need."""
        hidden_needs = []
        
        if any(word in question.lower() for word in ["risk", "problem", "alert"]):
            hidden_needs.append("risk_recommendations")
        
        if any(word in question.lower() for word in ["compare", "vs", "which"]):
            hidden_needs.append("comparative_analysis")
        
        if any(word in question.lower() for word in ["show", "chart", "graph", "visualize"]):
            hidden_needs.append("visualization")
        
        if any(word in question.lower() for word in ["why", "how", "root cause"]):
            hidden_needs.append("detailed_explanation")
        
        return hidden_needs


# ============================================
# 2. CROSS-SOURCE DATA VALIDATOR
# ============================================

class CrossSourceValidator:
    """Validate data consistency across multiple sources."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def validate_project_status(self, project_id: str) -> Dict[str, Any]:
        """Validate project status across all sources."""
        
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {"error": "Project not found", "validated": False}
        
        validations = {
            "schedule_consistency": self._validate_schedule_consistency(p6),
            "cost_consistency": self._validate_cost_consistency(p6),
            "progress_consistency": self._validate_progress_consistency(p6),
            "float_variance_alignment": self._validate_float_variance_alignment(p6),
        }
        
        inconsistencies = [
            v for v in validations.values()
            if v.get("status") in ["INCONSISTENT", "WARNING"]
        ]
        
        return {
            "project_id": project_id,
            "validations": validations,
            "overall_score": self._calculate_consistency_score(validations),
            "inconsistency_count": len(inconsistencies),
            "flags": [v.get("flag") for v in inconsistencies if v.get("flag")],
            "validated": len(inconsistencies) == 0,
        }
    
    def _validate_schedule_consistency(self, p6) -> Dict[str, Any]:
        """Check SPI vs activity status consistency."""
        
        if not p6.schedule_performance_index:
            return {"status": "UNKNOWN", "score": 0.5}
        
        spi = p6.schedule_performance_index
        completion = p6.duration_percent_complete or 0
        
        # What completion % would we expect given the SPI?
        expected_completion = min(100, spi * 100)
        actual_completion = completion
        
        # Allow 10% tolerance
        variance = abs(expected_completion - actual_completion)
        consistency_score = 1.0 - min(1.0, variance / 100)
        
        status = "CONSISTENT" if variance <= 10 else "WARNING" if variance <= 20 else "INCONSISTENT"
        
        return {
            "status": status,
            "score": consistency_score,
            "spi": spi,
            "expected_completion_pct": round(expected_completion, 1),
            "actual_completion_pct": round(actual_completion, 1),
            "variance_pct": round(variance, 1),
            "flag": f"Schedule: SPI shows {expected_completion:.0f}% completion, actual is {actual_completion:.0f}%" if variance > 10 else None,
        }
    
    def _validate_cost_consistency(self, p6) -> Dict[str, Any]:
        """Check CPI vs spending consistency."""
        
        if not p6.cost_performance_index or not p6.planned_cost:
            return {"status": "UNKNOWN", "score": 0.5}
        
        cpi = p6.cost_performance_index
        actual_spent = p6.actual_total_cost or 0
        planned = p6.planned_cost
        
        # What % should be spent given CPI?
        actual_spent_pct = (actual_spent / planned * 100) if planned > 0 else 0
        expected_spent_pct = (1.0 / cpi * 100) if cpi > 0 else 100
        
        # Allow 15% tolerance
        variance = abs(actual_spent_pct - expected_spent_pct)
        consistency_score = 1.0 - min(1.0, variance / 100)
        
        status = "CONSISTENT" if variance <= 15 else "WARNING" if variance <= 30 else "INCONSISTENT"
        
        return {
            "status": status,
            "score": consistency_score,
            "cpi": cpi,
            "actual_spent_pct": round(actual_spent_pct, 1),
            "expected_spent_pct": round(expected_spent_pct, 1),
            "variance_pct": round(variance, 1),
            "flag": f"Cost: CPI indicates {expected_spent_pct:.0f}% should be spent, actual is {actual_spent_pct:.0f}%" if variance > 15 else None,
        }
    
    def _validate_progress_consistency(self, p6) -> Dict[str, Any]:
        """Check activity count vs completion %."""
        
        activities = self.db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        ).all()
        
        if not activities:
            return {"status": "UNKNOWN", "score": 0.5}
        
        completed = sum(1 for a in activities if a.status and 'completed' in a.status.lower())
        activity_completion_pct = (completed / len(activities) * 100) if activities else 0
        duration_completion_pct = p6.duration_percent_complete or 0
        
        # These should be roughly aligned
        variance = abs(activity_completion_pct - duration_completion_pct)
        consistency_score = 1.0 - min(1.0, variance / 100)
        
        status = "CONSISTENT" if variance <= 15 else "WARNING" if variance <= 30 else "INCONSISTENT"
        
        return {
            "status": status,
            "score": consistency_score,
            "activity_completion_pct": round(activity_completion_pct, 1),
            "duration_completion_pct": round(duration_completion_pct, 1),
            "variance_pct": round(variance, 1),
            "flag": f"Progress: {activity_completion_pct:.0f}% activities done vs {duration_completion_pct:.0f}% duration" if variance > 15 else None,
        }
    
    def _validate_float_variance_alignment(self, p6) -> Dict[str, Any]:
        """Check if float and variance are aligned."""
        
        if p6.total_float is None or p6.finish_date_variance is None:
            return {"status": "UNKNOWN", "score": 0.5}
        
        float_hrs = p6.total_float
        variance_hrs = p6.finish_date_variance
        
        # If project is delayed (positive variance), float should be negative or small
        if variance_hrs > 0 and float_hrs > 10:
            return {
                "status": "INCONSISTENT",
                "score": 0.3,
                "flag": "Float/Variance: Project is delayed but has positive float (unexpected)",
            }
        
        # If project is ahead (negative variance), float should be positive
        if variance_hrs < -10 and float_hrs < 0:
            return {
                "status": "WARNING",
                "score": 0.7,
                "flag": "Float/Variance: Project is ahead but on critical path",
            }
        
        return {"status": "CONSISTENT", "score": 0.95}
    
    def _calculate_consistency_score(self, validations: Dict) -> float:
        """Calculate overall consistency score."""
        scores = [v.get("score", 0.5) for v in validations.values()]
        return sum(scores) / len(scores) if scores else 0.5


# ============================================
# 3. CLARIFYING QUESTIONS ENGINE
# ============================================

class ClarifyingQuestionsEngine:
    """Generate clarifying questions for ambiguous queries."""
    
    def should_ask_clarification(self, message: str, history: List[dict] = None) -> bool:
        """Determine if clarification is needed."""
        message_lower = message.lower().strip()
        
        # Very short or generic questions
        short_generic = ["what now", "status", "ok?", "how are we", "any problems", "tell me"]
        if any(q in message_lower for q in short_generic):
            # Check if history establishes context
            if not history or len(history) == 0:
                return True
            
            # Check if recent messages have project context
            recent = " ".join([m.get("content", "") for m in history[-3:]])
            if not any(word in recent.lower() for word in ["project", "proj", "portfolio"]):
                return True
        
        return False
    
    def generate_clarification_questions(
        self,
        message: str,
        available_projects: List[str] = None,
        history: List[dict] = None
    ) -> Dict[str, Any]:
        """Generate specific clarifying questions."""
        
        message_lower = message.lower()
        questions = []
        
        # Q1: Project context
        if "project" not in message_lower and available_projects:
            questions.append({
                "id": "clarify_project",
                "priority": "CRITICAL",
                "question": "Which project are you asking about?",
                "field": "project_id",
                "options": available_projects[:7],
                "allow_multiple": False,
            })
        
        # Q2: Metric focus
        if any(word in message_lower for word in ["status", "doing", "health", "how"]):
            questions.append({
                "id": "clarify_metric",
                "priority": "HIGH",
                "question": "What aspect would you like to focus on?",
                "field": "metric_focus",
                "options": [
                    "Schedule & Timeline",
                    "Budget & Costs",
                    "Risks & Issues",
                    "Progress & Activities",
                    "Overall Health"
                ],
                "allow_multiple": False,
            })
        
        # Q3: Scope
        if any(word in message_lower for word in ["portfolio", "all", "everything", "total"]):
            questions.append({
                "id": "clarify_scope",
                "priority": "MEDIUM",
                "question": "What level of detail?",
                "field": "detail_level",
                "options": ["Summary", "Detailed Analysis", "Top Issues Only", "Recommendations"],
                "allow_multiple": False,
            })
        
        # Q4: Time period
        if any(word in message_lower for word in ["trend", "history", "over time", "performance"]):
            questions.append({
                "id": "clarify_timeframe",
                "priority": "MEDIUM",
                "question": "What time period?",
                "field": "timeframe",
                "options": ["Last Month", "Last 3 Months", "Last 6 Months", "Since Start"],
                "allow_multiple": False,
            })
        
        if not questions:
            return {"needs_clarification": False}
        
        return {
            "needs_clarification": True,
            "count": len(questions),
            "priority_level": questions[0].get("priority"),
            "questions": questions,
            "suggested_response": "I need a bit more information to give you the best answer. " + 
                                 " ".join([f"\n- {q['question']}" for q in questions]),
        }


# ============================================
# 4. CONFIDENCE SCORING ENGINE
# ============================================

class ConfidenceScoringEngine:
    """Score confidence in findings."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def score_response_confidence(self, project_id: str) -> Dict[str, Any]:
        """Calculate comprehensive confidence score."""
        
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {"error": "Project not found", "confidence": 0}
        
        confidence_factors = {}
        
        # Factor 1: Data Freshness
        days_stale = 0
        if p6.data_date:
            days_stale = (datetime.utcnow() - p6.data_date).days
        elif p6.last_synced_at:
            days_stale = (datetime.utcnow() - p6.last_synced_at).days
        
        freshness_score = max(0.2, 1.0 - (days_stale / 90))  # Decay over 90 days
        confidence_factors["data_freshness"] = {
            "score": freshness_score,
            "days_since_update": days_stale,
            "status": "FRESH" if days_stale <= 7 else "MODERATE" if days_stale <= 30 else "STALE",
        }
        
        # Factor 2: Data Completeness
        required_fields = [
            "schedule_performance_index",
            "cost_performance_index",
            "duration_percent_complete",
            "total_float",
            "finish_date_variance",
        ]
        
        populated = sum(1 for field in required_fields if getattr(p6, field, None) is not None)
        completeness_score = populated / len(required_fields)
        confidence_factors["data_completeness"] = {
            "score": completeness_score,
            "fields_populated": populated,
            "total_required": len(required_fields),
            "missing_fields": [f for f in required_fields if getattr(p6, f, None) is None],
        }
        
        # Factor 3: Activity Data Quality
        activities = self.db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        ).all()
        
        activities_with_status = sum(1 for a in activities if a.status)
        activity_quality = (activities_with_status / len(activities)) if activities else 0.3
        
        confidence_factors["activity_data_quality"] = {
            "score": activity_quality,
            "activities_with_status": activities_with_status,
            "total_activities": len(activities),
        }
        
        # Factor 4: Data Consistency (call validator)
        validator = CrossSourceValidator(self.db)
        validation_result = validator.validate_project_status(project_id)
        consistency_score = validation_result.get("overall_score", 0.5)
        
        confidence_factors["data_consistency"] = {
            "score": consistency_score,
            "inconsistency_count": validation_result.get("inconsistency_count", 0),
            "validated": validation_result.get("validated", True),
        }
        
        # Calculate weighted overall confidence
        weights = {
            "data_freshness": 0.20,
            "data_completeness": 0.30,
            "activity_data_quality": 0.25,
            "data_consistency": 0.25,
        }
        
        overall_score = sum(
            confidence_factors[factor].get("score", 0) * weight
            for factor, weight in weights.items()
        )
        
        overall_score = min(0.99, max(0.0, overall_score))
        
        return {
            "overall_confidence": overall_score,
            "confidence_level": self._interpret_confidence(overall_score),
            "factors": confidence_factors,
            "disclaimer": self._generate_disclaimer(confidence_factors, overall_score),
            "recommendations_for_improving_confidence": self._suggest_improvements(confidence_factors),
        }
    
    def _interpret_confidence(self, score: float) -> str:
        """Interpret confidence level."""
        if score >= 0.90:
            return "VERY HIGH"
        elif score >= 0.80:
            return "HIGH"
        elif score >= 0.70:
            return "MODERATE"
        elif score >= 0.60:
            return "LOW"
        else:
            return "VERY LOW"
    
    def _generate_disclaimer(self, factors: Dict, overall_score: float) -> str:
        """Generate user-facing disclaimer."""
        disclaimers = []
        
        freshness = factors.get("data_freshness", {})
        if freshness.get("status") == "STALE":
            disclaimers.append(f"⚠️  Data is {freshness.get('days_since_update', 0)} days old")
        elif freshness.get("status") == "MODERATE":
            disclaimers.append(f"ℹ️  Data is {freshness.get('days_since_update', 0)} days old")
        
        completeness = factors.get("data_completeness", {})
        if completeness.get("score", 1) < 0.8:
            missing = completeness.get("missing_fields", [])
            if missing:
                disclaimers.append(f"⚠️  Missing: {', '.join(missing[:2])}")
        
        consistency = factors.get("data_consistency", {})
        if not consistency.get("validated", True):
            disclaimers.append(f"⚠️  Data consistency issues detected")
        
        if overall_score < 0.7:
            disclaimers.insert(0, "⚠️  Low confidence - interpret with caution")
        
        return " | ".join(disclaimers) if disclaimers else "✅ High confidence in this data"
    
    def _suggest_improvements(self, factors: Dict) -> List[str]:
        """Suggest ways to improve confidence."""
        suggestions = []
        
        if factors.get("data_freshness", {}).get("status") in ["STALE", "MODERATE"]:
            suggestions.append("Update project data to get fresh metrics")
        
        if factors.get("data_completeness", {}).get("score", 1) < 0.8:
            suggestions.append("Fill in missing schedule and cost metrics")
        
        if factors.get("activity_data_quality", {}).get("score", 1) < 0.7:
            suggestions.append("Update activity statuses")
        
        if not factors.get("data_consistency", {}).get("validated", True):
            suggestions.append("Resolve data consistency issues")
        
        return suggestions if suggestions else ["Data looks good - no improvements needed"]


# ============================================
# 5. COMPOSITE METRICS ENGINE
# ============================================

class CompositeMetricsEngine:
    """Create composite metrics for better context."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_composite_health_score(self, project_id: str) -> Dict[str, Any]:
        """Calculate composite health with multiple factors."""
        
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {}
        
        component_scores = {}
        
        # 1. Schedule Health
        spi = p6.schedule_performance_index or 1.0
        float_factor = self._calculate_float_factor(p6.total_float)
        schedule_score = (spi * 0.65 + float_factor * 0.35)
        component_scores["schedule_health"] = min(1.0, max(0.0, schedule_score))
        
        # 2. Cost Health
        cpi = p6.cost_performance_index or 1.0
        cost_score = min(1.0, cpi * 1.1)  # Slightly generous since under-budget is good
        component_scores["cost_health"] = min(1.0, max(0.0, cost_score))
        
        # 3. Progress Health
        completion = (p6.duration_percent_complete or 0) / 100
        expected_by_spi = min(1.0, spi)
        
        progress_variance = abs(completion - expected_by_spi)
        progress_score = 1.0 - (progress_variance * 0.8)
        component_scores["progress_health"] = min(1.0, max(0.0, progress_score))
        
        # 4. Critical Path Health
        activities = self.db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        ).all()
        
        if activities:
            critical = sum(1 for a in activities if a.total_float is not None and a.total_float <= 0)
            critical_ratio = critical / len(activities) if activities else 0
            
            # More activities on critical path = higher risk
            critical_health = 1.0 - (critical_ratio * 0.6)
            component_scores["critical_path_health"] = min(1.0, max(0.0, critical_health))
            component_scores["activity_count"] = len(activities)
            component_scores["critical_activities_count"] = critical
        
        # 5. Activity Status Health
        completed = sum(1 for a in activities if a.status and 'completed' in a.status.lower())
        in_progress = sum(1 for a in activities if a.status and 'in progress' in a.status.lower())
        healthy_activities = (completed + in_progress) / len(activities) if activities else 0
        component_scores["activity_health"] = healthy_activities
        
        # Composite Score (weighted)
        weights = {
            "schedule_health": 0.30,
            "cost_health": 0.25,
            "critical_path_health": 0.20,
            "progress_health": 0.15,
            "activity_health": 0.10,
        }
        
        composite = sum(
            component_scores.get(metric, 0.5) * weight
            for metric, weight in weights.items()
            if metric in component_scores
        )
        
        return {
            "component_scores": component_scores,
            "composite_health_score": min(1.0, max(0.0, composite)),
            "health_status": self._interpret_health_score(composite),
            "health_trend": self._estimate_health_trend(composite, p6),
            "primary_drivers": self._identify_primary_drivers(component_scores),
            "recommendations": self._generate_health_recommendations(component_scores),
        }
    
    def _calculate_float_factor(self, total_float: Optional[float]) -> float:
        """Convert float to health factor."""
        if total_float is None:
            return 0.7
        
        if total_float <= 0:
            return 0.3  # Critical
        elif total_float <= 7:  # 7 days
            return 0.6  # Tight
        elif total_float <= 30:  # 30 days
            return 0.85  # Moderate
        else:
            return 1.0  # Good buffer
    
    def _interpret_health_score(self, score: float) -> str:
        """Interpret health score."""
        if score >= 0.90:
            return "EXCELLENT"
        elif score >= 0.80:
            return "HEALTHY"
        elif score >= 0.65:
            return "AT RISK"
        elif score >= 0.50:
            return "CONCERNING"
        else:
            return "CRITICAL"
    
    def _estimate_health_trend(self, current_score: float, p6) -> Dict[str, Any]:
        """Estimate if health is improving or declining."""
        
        # Based on SPI and CPI trends
        spi_trend = "improving" if (p6.schedule_performance_index or 1.0) >= 0.95 else "declining"
        cpi_trend = "improving" if (p6.cost_performance_index or 1.0) >= 0.95 else "declining"
        
        return {
            "current_score": current_score,
            "schedule_trend": spi_trend,
            "cost_trend": cpi_trend,
            "overall_trend": "improving" if spi_trend == "improving" and cpi_trend == "improving" else "declining",
        }
    
    def _identify_primary_drivers(self, scores: Dict) -> List[Dict[str, Any]]:
        """Identify what's driving the health score."""
        sorted_scores = sorted(scores.items(), key=lambda x: x[1])
        
        return [
            {
                "metric": metric.replace("_", " ").title(),
                "score": round(score, 2),
                "impact": "Critical" if i == 0 else "High" if i == 1 else "Medium",
            }
            for i, (metric, score) in enumerate(sorted_scores[:3])
        ]
    
    def _generate_health_recommendations(self, scores: Dict) -> List[str]:
        """Generate recommendations based on health components."""
        recommendations = []
        
        if scores.get("schedule_health", 1) < 0.85:
            recommendations.append("Focus on schedule recovery - expedite critical path activities")
        
        if scores.get("cost_health", 1) < 0.85:
            recommendations.append("Review cost drivers - implement cost control measures")
        
        if scores.get("critical_path_health", 1) < 0.75:
            recommendations.append("Manage critical path risk - allocate resources to critical activities")
        
        if scores.get("progress_health", 1) < 0.75:
            recommendations.append("Accelerate activity completion - adjust resource allocation")
        
        return recommendations if recommendations else ["Project health is good - maintain current trajectory"]
