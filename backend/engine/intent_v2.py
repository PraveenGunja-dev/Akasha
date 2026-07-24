"""
Enhanced Intent Classification v2.1

Improved intent detection that understands:
- All available data domains (P6, SAP, TC, portfolio metrics)
- Query patterns (factual, analytical, advisory, visualization)
- Project scope (specific project, portfolio, cross-project comparison)
- Data requirements and available metrics
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class EnhancedChatIntent:
    """Enhanced structured intent with full context."""
    projects: List[str] = field(default_factory=list)
    intent_type: str = "advisory"  # factual|analytical|advisory|visualization|export
    domains: List[str] = field(default_factory=lambda: ["p6"])
    is_portfolio: bool = False
    is_visualization_requested: bool = False
    requires_comparison: bool = False
    requires_trend_analysis: bool = False
    confidence: float = 0.85
    raw_question: str = ""
    metadata: dict = field(default_factory=dict)


class EnhancedIntentClassifier:
    """Enhanced classifier with deep understanding."""
    
    # ============================================
    # Keyword Definitions
    # ============================================
    
    FACTUAL_PATTERNS = [
        r"what.*is|what's|tell.*me.*the",
        r"how many|how much|how high|how low",
        r"show me|give me|display|current|total|count|list",
        r"when.*(?:is|will|expected)",
        r"where|which|what.*status",
        r"^\w+\s+(?:value|count|number|amount|percentage|pct)",
    ]
    
    ANALYTICAL_PATTERNS = [
        r"(?:compare|comparison|versus|vs\.|vs\s)",
        r"(?:analyze|analysis|why|why.*happening|root cause)",
        r"(?:trend|trending|trend\s+analysis|progression)",
        r"(?:variance|deviation|difference|gap\s+analysis)",
        r"(?:correlation|relationship|impact|influence)",
        r"(?:breakdown|distribution|by.*category)",
        r"(?:performance|efficiency|productivity)",
        r"what.*if|scenario|simulation",
    ]
    
    ADVISORY_PATTERNS = [
        r"(?:recommend|suggestion|advise|should)",
        r"(?:action|mitigate|recover|recovery|strategy)",
        r"(?:brief|report|summary|overview|executive)",
        r"(?:what.*to.*do|how.*to.*fix|how.*to.*improve)",
        r"(?:alert|critical|at risk|help)",
        r"(?:plan|planning|roadmap|forecast)",
    ]
    
    VISUALIZATION_PATTERNS = [
        r"(?:show|display|visuali|picture|chart|graph|plot)",
        r"(?:pie|bar|line|trend|breakdown)",
        r"(?:see|view).*(?:visual|chart|graph|breakdown)",
    ]
    
    P6_KEYWORDS = {
        "schedule": ["schedule", "timeline", "critical", "float", "path", "delay", "delays", "late", "early"],
        "progress": ["progress", "complete", "completion", "percent", "%", "done", "finished"],
        "activities": ["activity", "activities", "activity", "task", "tasks", "work"],
        "cost": ["cost", "budget", "spending", "spent", "expense"],
        "baseline": ["baseline", "variance", "actual", "planned"],
    }
    
    SAP_KEYWORDS = {
        "material": ["material", "materials", "item", "items", "inventory", "stock"],
        "procurement": ["procurement", "po", "purchase", "order", "vendor", "supplier"],
        "delivery": ["delivery", "delivered", "received", "gap", "pending", "outstanding"],
        "supply_chain": ["supply", "chain", "supply chain", "pipeline", "sourcing"],
    }
    
    TC_KEYWORDS = {
        "transmission": ["transmission", "grid", "line", "substation", "connectivity"],
        "readiness": ["ready", "readiness", "ready", "prepared", "operational"],
        "network": ["network", "nodes", "edges", "connection", "connections"],
    }
    
    PORTFOLIO_KEYWORDS = {
        "portfolio": ["all projects", "portfolio", "across", "every project", "portfolio level"],
        "comparison": ["compare", "comparison", "versus", "best", "worst", "riskiest"],
        "aggregate": ["total", "overall", "sum", "aggregate", "portfolio", "summary"],
    }
    
    # ============================================
    # Main Classification
    # ============================================
    
    @classmethod
    def classify(cls, message: str, history: List[dict] = None, project_names: List[str] = None) -> EnhancedChatIntent:
        """Classify user intent with high accuracy."""
        
        intent = EnhancedChatIntent(raw_question=message)
        msg_lower = message.lower().strip()
        
        # Detect intent type (order matters: visualization first)
        if cls._detect_visualization_request(msg_lower):
            intent.intent_type = "visualization"
            intent.is_visualization_requested = True
            intent.confidence = 0.95
        elif cls._detect_analytical(msg_lower):
            intent.intent_type = "analytical"
            intent.requires_comparison = cls._detect_comparison(msg_lower)
            intent.requires_trend_analysis = cls._detect_trend(msg_lower)
            intent.confidence = 0.90
        elif cls._detect_advisory(msg_lower):
            intent.intent_type = "advisory"
            intent.confidence = 0.88
        else:
            intent.intent_type = "factual"
            intent.confidence = 0.92
        
        # Detect domains needed
        intent.domains = cls._detect_domains(msg_lower)
        
        # Detect portfolio scope
        if cls._detect_portfolio_scope(msg_lower):
            intent.is_portfolio = True
        
        # Detect specific projects mentioned
        intent.projects = cls._extract_project_references(msg_lower, project_names)
        
        # Add metadata
        intent.metadata = {
            "message_length": len(message),
            "has_numbers": bool(re.search(r'\d+', message)),
            "has_percentage": bool(re.search(r'\d+\s*%', message)),
            "has_date": bool(re.search(r'\d{4}[-/]\d{2}[-/]\d{2}|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', msg_lower)),
        }
        
        return intent
    
    # ============================================
    # Intent Detection Methods
    # ============================================
    
    @classmethod
    def _detect_visualization_request(cls, msg_lower: str) -> bool:
        """Detect if user wants visualization."""
        for pattern in cls.VISUALIZATION_PATTERNS:
            if re.search(pattern, msg_lower):
                return True
        return False
    
    @classmethod
    def _detect_analytical(cls, msg_lower: str) -> bool:
        """Detect analytical questions."""
        for pattern in cls.ANALYTICAL_PATTERNS:
            if re.search(pattern, msg_lower):
                return True
        return False
    
    @classmethod
    def _detect_advisory(cls, msg_lower: str) -> bool:
        """Detect advisory questions."""
        for pattern in cls.ADVISORY_PATTERNS:
            if re.search(pattern, msg_lower):
                return True
        return False
    
    @classmethod
    def _detect_comparison(cls, msg_lower: str) -> bool:
        """Detect if question involves comparison."""
        comparison_words = ["compare", "vs", "versus", "better", "worse", "which", "most", "least"]
        return any(word in msg_lower for word in comparison_words)
    
    @classmethod
    def _detect_trend(cls, msg_lower: str) -> bool:
        """Detect if question involves trends."""
        trend_words = ["trend", "over time", "progression", "trajectory", "improving", "worsening"]
        return any(word in msg_lower for word in trend_words)
    
    @classmethod
    def _detect_portfolio_scope(cls, msg_lower: str) -> bool:
        """Detect portfolio-level questions."""
        for keyword_list in cls.PORTFOLIO_KEYWORDS.values():
            if any(kw in msg_lower for kw in keyword_list):
                return True
        return False
    
    @classmethod
    def _detect_domains(cls, msg_lower: str) -> List[str]:
        """Detect which data domains are needed."""
        domains = ["p6"]  # P6 is always baseline
        
        # Check for SAP
        if any(keyword in msg_lower for keywords in cls.SAP_KEYWORDS.values() for keyword in keywords):
            domains.append("sap")
        
        # Check for TC
        if any(keyword in msg_lower for keywords in cls.TC_KEYWORDS.values() for keyword in keywords):
            domains.append("tc")
        
        # Check for cost explicitly
        if any(word in msg_lower for word in ["budget", "cost", "spending", "capex", "opex"]):
            if "sap" not in domains:
                domains.append("sap")
        
        return domains
    
    @classmethod
    def _extract_project_references(cls, msg_lower: str, known_projects: List[str] = None) -> List[str]:
        """Extract project references from message."""
        projects = []
        
        if not known_projects:
            return projects
        
        # Fuzzy matching against known projects
        for project_name in known_projects:
            project_lower = project_name.lower()
            
            # Exact match
            if f" {project_lower} " in f" {msg_lower} ":
                projects.append(project_name)
            
            # Partial match (at least 3 consecutive chars)
            elif len(project_lower) >= 3:
                # Extract 3-char substrings and check
                substrings = [project_lower[i:i+3] for i in range(len(project_lower)-2)]
                if all(substr in msg_lower for substr in substrings[:2]):
                    projects.append(project_name)
        
        return list(set(projects))  # Remove duplicates
    
    # ============================================
    # Confidence Analysis
    # ============================================
    
    @classmethod
    def refine_confidence(cls, intent: EnhancedChatIntent, history: List[dict] = None) -> EnhancedChatIntent:
        """Refine confidence based on conversation history."""
        
        if history and len(history) > 0:
            # If previous message was factual, current factual question has higher confidence
            prev_type = history[-1].get("intent_type") if isinstance(history[-1], dict) else None
            
            if prev_type == intent.intent_type:
                intent.confidence = min(0.99, intent.confidence + 0.05)
        
        return intent


# ============================================
# Compatibility Bridge
# ============================================

def enhanced_classify_intent(message: str, history: List[dict] = None, project_names: List[str] = None) -> dict:
    """
    Drop-in replacement for existing classify_intent that returns enhanced intent.
    Converts EnhancedChatIntent to dict for backward compatibility.
    """
    
    intent = EnhancedIntentClassifier.classify(message, history, project_names)
    intent = EnhancedIntentClassifier.refine_confidence(intent, history)
    
    return {
        "projects": intent.projects,
        "intent_type": intent.intent_type,
        "domains": intent.domains,
        "is_portfolio": intent.is_portfolio,
        "raw_question": intent.raw_question,
        "is_visualization_requested": intent.is_visualization_requested,
        "requires_comparison": intent.requires_comparison,
        "requires_trend_analysis": intent.requires_trend_analysis,
        "confidence": intent.confidence,
        "metadata": intent.metadata,
    }
