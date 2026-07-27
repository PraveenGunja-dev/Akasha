"""
Akasha Chatbot Accuracy Analysis & Strategic Improvements v2.1+

Analysis of current architecture and recommendations for achieving
an unvalidated target of 99%+ accuracy in responses. This historical design
document is not an evaluation result; no executable benchmark supports its
accuracy percentages, and the described v2.2 path is not active.
"""

# ============================================
# CURRENT ACCURACY ASSESSMENT
# ============================================

"""
Current Enhancement (v2.1) Status:
- Intent Classification: 90-95% accuracy (unvalidated estimate)
- Data Understanding: 85-90% accuracy  
- Response Accuracy: 80-85% accuracy
- Visualization Correctness: 95%+ accuracy (unvalidated estimate)

Bottlenecks Identified:
1. Missing context from multi-turn conversations
2. No cross-source data validation
3. Limited edge case handling
4. No semantic understanding beyond keywords
5. Threshold-based logic (not AI-driven)

Current Score: ~85% Overall Accuracy
Unvalidated Target Score: 99%+ Overall Accuracy
"""

# ============================================
# IMPROVEMENT #1: SEMANTIC UNDERSTANDING LAYER
# ============================================

"""
PROBLEM: Current system uses keyword matching + basic patterns
- "Show me CPI" vs "What's our cost performance?" = Different paths
- Misses nuance in questions
- Failed on paraphrasing

SOLUTION: Add semantic layer before intent classification

Implementation:
1. Semantic similarity matching (not keyword matching)
2. Question rewriting/normalization
3. Concept extraction (not just keywords)
4. Hierarchy awareness (SPI = Schedule Performance Index)

Expected Accuracy Gain: +8-10%
"""

class SemanticUnderstandingLayer:
    """Map user questions to canonical queries using semantic understanding."""
    
    # Semantic equivalences
    SEMANTIC_SYNONYMS = {
        "schedule": ["spi", "on time", "delay", "delays", "late", "early", "timeline"],
        "cost": ["cpi", "budget", "spending", "spent", "overrun", "overspend"],
        "progress": ["completion", "percent complete", "done", "finished", "status"],
        "risk": ["critical", "at risk", "danger", "problem", "issue"],
        "activity": ["task", "tasks", "work", "job", "activity"],
        "project": ["initiative", "program", "effort", "endeavor"],
    }
    
    CONCEPT_HIERARCHY = {
        "performance": {
            "schedule": ["spi", "float", "variance", "critical_path"],
            "cost": ["cpi", "budget", "variance", "overrun"],
            "progress": ["completion_percentage", "activity_status"],
        },
        "risk": {
            "high_severity": ["critical", "urgent", "severe"],
            "medium_severity": ["moderate", "caution"],
            "low_severity": ["minor", "watch"],
        },
    }
    
    @classmethod
    def extract_semantic_concepts(cls, question: str) -> dict:
        """Extract canonical concepts from question."""
        question_lower = question.lower()
        concepts = {
            "primary_concept": None,
            "secondary_concepts": [],
            "entities": [],
            "temporal_scope": None,
            "comparison": False,
        }
        
        # Find primary concept
        for concept, keywords in cls.SEMANTIC_SYNONYMS.items():
            if any(kw in question_lower for kw in keywords):
                concepts["primary_concept"] = concept
                break
        
        # Find secondary concepts
        for concept, keywords in cls.SEMANTIC_SYNONYMS.items():
            if concept != concepts["primary_concept"]:
                if any(kw in question_lower for kw in keywords):
                    concepts["secondary_concepts"].append(concept)
        
        # Detect comparison
        if any(word in question_lower for word in ["vs", "versus", "compare", "vs.", "better", "worse"]):
            concepts["comparison"] = True
        
        # Temporal scope
        if "today" in question_lower or "current" in question_lower:
            concepts["temporal_scope"] = "current"
        elif "trend" in question_lower or "over time" in question_lower:
            concepts["temporal_scope"] = "historical"
        else:
            concepts["temporal_scope"] = "current"
        
        return concepts
    
    @classmethod
    def normalize_question_semantically(cls, question: str) -> str:
        """Rewrite question to canonical form."""
        concepts = cls.extract_semantic_concepts(question)
        
        # Build canonical form
        canonical = f"Query about {concepts['primary_concept']}"
        if concepts['secondary_concepts']:
            canonical += f" and {', '.join(concepts['secondary_concepts'])}"
        if concepts['comparison']:
            canonical += " (comparison requested)"
        
        return canonical


# ============================================
# IMPROVEMENT #2: MULTI-SOURCE DATA VALIDATION
# ============================================

"""
PROBLEM: Currently trusts single data source
- P6 says project is 50% complete
- But SAP shows only 30% materials delivered
- Which is correct? No validation!

SOLUTION: Add cross-source validation layer

Features:
1. Validate facts across P6, SAP, TC sources
2. Flag inconsistencies
3. Provide confidence score
4. Suggest corrections

Expected Accuracy Gain: +12-15%
"""

class CrossSourceValidator:
    """Validate data across P6, SAP, TC sources."""
    
    def __init__(self, db):
        self.db = db
    
    def validate_project_status(self, project_id: str) -> dict:
        """Validate project status across all sources."""
        validators = {
            "schedule_consistency": self._validate_schedule_consistency,
            "cost_consistency": self._validate_cost_consistency,
            "material_delivery_consistency": self._validate_material_consistency,
            "progress_consistency": self._validate_progress_consistency,
        }
        
        results = {}
        for check_name, check_func in validators.items():
            results[check_name] = check_func(project_id)
        
        return {
            "project_id": project_id,
            "validations": results,
            "overall_confidence": self._calculate_overall_confidence(results),
            "flags": self._identify_inconsistencies(results),
        }
    
    def _validate_schedule_consistency(self, project_id: str) -> dict:
        """Check P6 schedule against other signals."""
        # Get P6 data
        import models
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {"status": "UNKNOWN", "reason": "No P6 data"}
        
        validations = []
        
        # Check 1: SPI vs actual completion
        spi = p6.schedule_performance_index or 1.0
        completion = p6.duration_percent_complete or 0
        
        expected_completion_by_spi = spi * 100
        actual_completion = completion
        
        consistency_score = 1.0 - abs(expected_completion_by_spi - actual_completion) / 100
        
        validations.append({
            "check": "SPI vs completion alignment",
            "spi_expected": f"{expected_completion_by_spi:.1f}%",
            "actual_completion": f"{actual_completion:.1f}%",
            "consistency_score": consistency_score,
        })
        
        # Check 2: Finish date variance
        if p6.finish_date_variance is not None:
            float_hours = p6.total_float or 0
            
            # If variance is positive but float is negative = inconsistency
            if p6.finish_date_variance > 0 and float_hours < 0:
                validations.append({
                    "check": "Variance vs float consistency",
                    "issue": "Project delayed but on critical path",
                    "severity": "HIGH",
                })
        
        average_score = sum(v.get("consistency_score", 0.5) for v in validations) / len(validations) if validations else 0
        
        return {
            "status": "VALIDATED" if average_score > 0.8 else "WARNING" if average_score > 0.6 else "INCONSISTENT",
            "confidence": average_score,
            "validations": validations,
        }
    
    def _validate_cost_consistency(self, project_id: str) -> dict:
        """Check cost data consistency."""
        import models
        p6 = self.db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6 or not p6.cost_performance_index:
            return {"status": "UNKNOWN"}
        
        cpi = p6.cost_performance_index
        spent_pct = (p6.actual_total_cost / p6.planned_cost * 100) if p6.planned_cost else 0
        
        # CPI should roughly match (actual / planned)
        expected_spent_pct = (1 / cpi * 100) if cpi > 0 else 0
        
        consistency = 1.0 - abs(expected_spent_pct - spent_pct) / 100
        
        return {
            "status": "VALIDATED" if consistency > 0.8 else "WARNING",
            "confidence": consistency,
            "cpi_vs_spending": {
                "cpi": cpi,
                "actual_spent_pct": spent_pct,
                "expected_by_cpi": expected_spent_pct,
            }
        }
    
    def _validate_material_consistency(self, project_id: str) -> dict:
        """Check material delivery vs schedule."""
        # Would compare SAP delivery % with P6 completion %
        return {"status": "PENDING_SAP_DATA"}
    
    def _validate_progress_consistency(self, project_id: str) -> dict:
        """Check overall progress consistency."""
        return {"status": "PENDING_DATA"}
    
    def _calculate_overall_confidence(self, validations: dict) -> float:
        """Calculate overall confidence score."""
        scores = []
        for validation in validations.values():
            if isinstance(validation, dict) and "confidence" in validation:
                scores.append(validation["confidence"])
        
        return sum(scores) / len(scores) if scores else 0.5
    
    def _identify_inconsistencies(self, validations: dict) -> list:
        """Identify flags and inconsistencies."""
        flags = []
        for name, validation in validations.items():
            if isinstance(validation, dict):
                if validation.get("status") == "INCONSISTENT":
                    flags.append({
                        "check": name,
                        "severity": "HIGH",
                        "message": "Data inconsistency detected"
                    })
                elif validation.get("status") == "WARNING":
                    flags.append({
                        "check": name,
                        "severity": "MEDIUM",
                        "message": "Potential data inconsistency"
                    })
        
        return flags


# ============================================
# IMPROVEMENT #3: CLARIFYING QUESTIONS ENGINE
# ============================================

"""
PROBLEM: Missing context in simple questions
- "What's the status?" - Of which project? Which metric?
- User frustration: Generic answers

SOLUTION: Ask clarifying questions before answering

Features:
1. Detect ambiguous queries
2. Ask specific clarifying questions
3. Remember context from conversation
4. Progressive refinement

Expected Accuracy Gain: +5-8%
"""

class ClarifyingQuestionsEngine:
    """Ask clarifying questions when context is ambiguous."""
    
    def should_ask_clarifying_questions(self, message: str, history: list = None) -> bool:
        """Determine if clarification is needed."""
        msg_lower = message.lower()
        
        # Detect ambiguous patterns
        ambiguous_patterns = [
            (r"what.*status", "project context missing"),
            (r"how are we doing", "multiple metrics possible"),
            (r"any problems", "scope unclear"),
            (r"tell me about", "too broad"),
        ]
        
        for pattern, reason in ambiguous_patterns:
            if __import__('re').search(pattern, msg_lower):
                # Check if conversation history provides context
                if not history or len(history) == 0:
                    return True
                
                # Check if previous messages establish context
                context_keywords = ["project", "schedule", "cost", "risk"]
                recent_context = " ".join([m.get("content", "") for m in history[-3:]])
                if not any(kw in recent_context.lower() for kw in context_keywords):
                    return True
        
        return False
    
    def generate_clarifying_questions(self, message: str, available_projects: list = None) -> dict:
        """Generate specific clarifying questions."""
        msg_lower = message.lower()
        questions = []
        
        # Detect what needs clarification
        if "project" not in msg_lower and available_projects:
            questions.append({
                "priority": "HIGH",
                "question": "Which project would you like to know about?",
                "options": available_projects[:5],
                "field": "project_id"
            })
        
        if any(word in msg_lower for word in ["status", "doing", "how"]):
            questions.append({
                "priority": "MEDIUM",
                "question": "Which aspect would you like to focus on?",
                "options": ["Schedule & Timeline", "Budget & Costs", "Risks & Issues", "Progress & Completion"],
                "field": "metric_focus"
            })
        
        if "risk" in msg_lower or "problem" in msg_lower:
            questions.append({
                "priority": "MEDIUM",
                "question": "What level of detail?",
                "options": ["Summary", "Detailed Analysis", "Recommendations"],
                "field": "detail_level"
            })
        
        return {
            "ambiguous": True,
            "clarifying_questions": questions,
            "suggested_rephrasing": f"Please clarify: {', '.join([q['question'] for q in questions])}",
        }


# ============================================
# IMPROVEMENT #4: CONFIDENCE SCORING & UNCERTAINTY
# ============================================

"""
PROBLEM: Chatbot sounds confident even when data is incomplete
- "Project is 50% complete" - but last update was 3 months ago!
- No indication of data quality

SOLUTION: Add confidence scoring to every response

Features:
1. Track data freshness
2. Flag incomplete data
3. Confidence score per metric
4. Uncertainty communication

Expected Accuracy Gain: +4-6%
"""

class ConfidenceScorer:
    """Score confidence in findings."""
    
    def score_response_confidence(self, project_id: str, metrics: dict, db) -> dict:
        """Calculate confidence score for response."""
        import models
        from datetime import datetime, timedelta
        
        p6 = db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        confidence_factors = {}
        
        # Factor 1: Data freshness
        if p6.data_date:
            days_stale = (datetime.utcnow() - p6.data_date).days
            freshness_score = max(0.3, 1.0 - (days_stale / 90))  # Decays over 90 days
            confidence_factors["data_freshness"] = {
                "score": freshness_score,
                "days_since_update": days_stale,
                "status": "FRESH" if days_stale <= 7 else "MODERATE" if days_stale <= 30 else "STALE",
            }
        
        # Factor 2: Data completeness
        required_fields = ["schedule_performance_index", "cost_performance_index", "duration_percent_complete"]
        populated = sum(1 for field in required_fields if getattr(p6, field) is not None)
        completeness_score = populated / len(required_fields)
        confidence_factors["data_completeness"] = {
            "score": completeness_score,
            "fields_populated": populated,
            "total_fields": len(required_fields),
        }
        
        # Factor 3: Consistency (from CrossSourceValidator)
        validator = CrossSourceValidator(db)
        validation = validator.validate_project_status(project_id)
        consistency_score = validation.get("overall_confidence", 0.5)
        confidence_factors["data_consistency"] = {
            "score": consistency_score,
            "flags": validation.get("flags", []),
        }
        
        # Factor 4: Activity data quality
        activities = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        ).all()
        activities_with_status = sum(1 for a in activities if a.status)
        activity_quality = (activities_with_status / len(activities)) if activities else 0.5
        confidence_factors["activity_data_quality"] = {
            "score": activity_quality,
            "activities_with_status": activities_with_status,
            "total_activities": len(activities),
        }
        
        # Calculate overall confidence
        weights = {
            "data_freshness": 0.25,
            "data_completeness": 0.25,
            "data_consistency": 0.25,
            "activity_data_quality": 0.25,
        }
        
        overall_score = sum(
            confidence_factors[factor].get("score", 0) * weight
            for factor, weight in weights.items()
        )
        
        return {
            "overall_confidence": min(0.99, overall_score),
            "confidence_level": "HIGH" if overall_score > 0.85 else "MODERATE" if overall_score > 0.70 else "LOW",
            "factors": confidence_factors,
            "disclaimer": self._generate_disclaimer(confidence_factors),
        }
    
    def _generate_disclaimer(self, factors: dict) -> str:
        """Generate user-facing disclaimer based on confidence factors."""
        disclaimers = []
        
        freshness = factors.get("data_freshness", {})
        if freshness.get("status") == "STALE":
            disclaimers.append(f"Note: Data is {freshness.get('days_since_update', 0)} days old")
        
        completeness = factors.get("data_completeness", {})
        if completeness.get("score", 1) < 0.8:
            missing = completeness.get("total_fields", 0) - completeness.get("fields_populated", 0)
            disclaimers.append(f"Warning: {missing} key metrics are missing")
        
        consistency = factors.get("data_consistency", {})
        if consistency.get("flags"):
            disclaimers.append(f"Alert: Data inconsistencies detected ({len(consistency.get('flags'))} issues)")
        
        return " | ".join(disclaimers) if disclaimers else "Data looks reliable"


# ============================================
# IMPROVEMENT #5: COMPOSITE METRICS ENGINE
# ============================================

"""
PROBLEM: Single metrics don't tell full story
- "SPI is 0.95" - is that good or bad?
- Needs context: baseline, portfolio average, trend

SOLUTION: Build composite metrics

Features:
1. Contextual scoring
2. Relative comparisons
3. Trend analysis
4. Composite health score

Expected Accuracy Gain: +6-8%
"""

class CompositeMetricsEngine:
    """Create composite metrics for better context."""
    
    def calculate_composite_health_score(self, project_id: str, db) -> dict:
        """Calculate composite project health using multiple factors."""
        import models
        
        p6 = db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        
        if not p6:
            return {}
        
        scores = {}
        
        # 1. Schedule Health Score
        spi = p6.schedule_performance_index or 1.0
        float_factor = 1.0
        if p6.total_float is not None:
            if p6.total_float <= 0:
                float_factor = 0.5  # Critical
            elif p6.total_float <= 7:
                float_factor = 0.7  # Tight
            else:
                float_factor = 1.0
        
        schedule_score = (spi * 0.6 + float_factor * 0.4)
        scores["schedule_health"] = min(1.0, schedule_score)
        
        # 2. Cost Health Score
        cpi = p6.cost_performance_index or 1.0
        completion = (p6.duration_percent_complete or 0) / 100
        
        # If project is early in completion but CPI is good, less risk
        cost_risk_factor = 1.0 - abs(cpi - 1.0) * 0.5
        cost_score = cpi * cost_risk_factor
        scores["cost_health"] = min(1.0, cost_score)
        
        # 3. Progress Health Score
        completion_pct = p6.duration_percent_complete or 0
        expected_progress = spi * 100
        progress_variance = abs(completion_pct - expected_progress) / 100
        progress_score = 1.0 - progress_variance
        scores["progress_health"] = min(1.0, max(0, progress_score))
        
        # 4. Activity Status Health
        activities = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        ).all()
        
        if activities:
            completed = sum(1 for a in activities if a.status and 'completed' in a.status.lower())
            in_progress = sum(1 for a in activities if a.status and 'in progress' in a.status.lower())
            
            healthy_activities = completed + in_progress  # Good or in progress
            activity_health = healthy_activities / len(activities)
            scores["activity_health"] = activity_health
        
        # 5. Critical Path Health
        critical_activities = [a for a in activities if a.total_float is not None and a.total_float <= 0]
        if activities:
            critical_pct = len(critical_activities) / len(activities)
            critical_health = 1.0 - (critical_pct * 0.5)  # More critical activities = lower health
            scores["critical_path_health"] = min(1.0, max(0, critical_health))
        
        # Composite Score (weighted average)
        weights = {
            "schedule_health": 0.25,
            "cost_health": 0.25,
            "progress_health": 0.20,
            "activity_health": 0.15,
            "critical_path_health": 0.15,
        }
        
        composite = sum(
            scores.get(metric, 0.5) * weight
            for metric, weight in weights.items()
        )
        
        return {
            "component_scores": scores,
            "composite_health_score": composite,
            "health_status": self._interpret_composite_score(composite),
            "primary_drivers": self._identify_drivers(scores),
        }
    
    def _interpret_composite_score(self, score: float) -> str:
        """Interpret composite score."""
        if score >= 0.90:
            return "EXCELLENT"
        elif score >= 0.75:
            return "HEALTHY"
        elif score >= 0.60:
            return "AT RISK"
        else:
            return "CRITICAL"
    
    def _identify_drivers(self, scores: dict) -> list:
        """Identify what's driving the score."""
        sorted_scores = sorted(scores.items(), key=lambda x: x[1])
        
        return [
            {
                "metric": metric,
                "score": score,
                "impact": "Lowest" if i == 0 else "Low" if i == 1 else "Medium"
            }
            for i, (metric, score) in enumerate(sorted_scores[:3])
        ]


# ============================================
# ARCHITECTURAL RECOMMENDATION
# ============================================

RECOMMENDED_PIPELINE = """
Enhanced Chatbot Pipeline v2.2+ (Unvalidated 99%+ Accuracy Target)

User Question
    ↓
[1] SEMANTIC UNDERSTANDING LAYER
    ├─ Extract semantic concepts
    ├─ Normalize question
    └─ Map to canonical form
    ↓
[2] CLARIFYING QUESTIONS ENGINE
    ├─ Detect ambiguity
    ├─ Ask clarifications if needed
    └─ Gather context
    ↓
[3] ENHANCED INTENT CLASSIFIER v2
    ├─ Classify intent
    ├─ Identify domains
    └─ Detect scope
    ↓
[4] DATA GATHERING & VALIDATION
    ├─ Gather from all sources (P6, SAP, TC)
    ├─ Cross-source validation
    └─ Flag inconsistencies
    ↓
[5] CONFIDENCE SCORING
    ├─ Data freshness check
    ├─ Data completeness check
    └─ Consistency verification
    ↓
[6] COMPOSITE METRICS ENGINE
    ├─ Calculate composite scores
    ├─ Factor in context
    └─ Identify drivers
    ↓
[7] RESPONSE FORMATTER v2
    ├─ Build narrative
    ├─ Include confidence scores
    ├─ Add disclaimer if needed
    └─ Suggest visualizations
    ↓
[8] VISUALIZATION GENERATOR
    ├─ Create charts
    ├─ Add annotations
    └─ Highlight anomalies
    ↓
RESPONSE WITH HIGH CONFIDENCE & TRANSPARENCY

Unvalidated Accuracy Target: 95-99%
"""

print(RECOMMENDED_PIPELINE)
