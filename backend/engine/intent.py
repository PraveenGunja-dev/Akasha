"""
Akasha Engine — Intent Classifier (Step 1 of Pipeline)

Lightweight pre-flight that extracts structured intent from user's question.
Uses a fast LLM call (Groq preferred for speed ~200ms) to determine:
  - Which project(s) are being asked about
  - What type of question (factual/analytical/advisory)
  - Which data domains are needed (p6/sap/tc)

This is NOT the main LLM call — it's a cheap routing decision.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChatIntent:
    """Structured intent extracted from user's question."""
    projects: list[str] = field(default_factory=list)  # Project names/IDs mentioned
    intent_type: str = "advisory"  # factual | analytical | advisory | document
    domains: list[str] = field(default_factory=lambda: ["p6"])  # p6, sap, tc
    is_portfolio: bool = False  # True if asking about all/multiple projects
    raw_question: str = ""


# Keywords that indicate each intent type — used as fallback if LLM classification fails
FACTUAL_KEYWORDS = [
    "what is", "what's", "how many", "how much", "show me the",
    "give me the", "tell me the", "current", "value of", "count of",
    "list", "date", "when", "status of",
]

ANALYTICAL_KEYWORDS = [
    "analyze", "analysis", "compare", "comparison", "trend",
    "breakdown", "performance", "why", "root cause", "impact",
    "correlation", "variance", "deviation", "risk assessment",
]

ADVISORY_KEYWORDS = [
    "recommend", "suggest", "should", "strategy", "action",
    "brief", "report", "draft", "generate", "executive",
    "board", "recovery", "mitigation", "plan",
]

DOCUMENT_KEYWORDS = [
    "definition", "define", "what does", "policy", "procedure",
    "formula", "kpi", "metric definition", "how is.*calculated",
    "specification", "brd", "sow",
]

# Domain detection keywords
SAP_KEYWORDS = [
    "material", "procurement", "purchase order", "po ", "vendor",
    "supplier", "inventory", "stock", "consumption", "delivery",
    "supply", "sap", "mb51", "mb52", "me2m",
]

TC_KEYWORDS = [
    "transmission", "grid", "substation", "line", "kps", "pss",
    "stringing", "erection", "foundation", "connectivity",
    "charging", "tc", "evacuation",
]

PORTFOLIO_KEYWORDS = [
    "all projects", "portfolio", "across all", "every project",
    "overall", "entire", "riskiest projects", "top", "worst",
]


def classify_intent_local(message: str, history: list = None) -> ChatIntent:
    """Fast local classification using keyword matching.
    
    This is the fallback when LLM classification is not available or too slow.
    ~1ms execution time.
    """
    msg_lower = message.lower().strip()
    intent = ChatIntent(raw_question=message)
    
    # Detect intent type
    if any(kw in msg_lower for kw in DOCUMENT_KEYWORDS):
        intent.intent_type = "document"
    elif any(kw in msg_lower for kw in FACTUAL_KEYWORDS):
        intent.intent_type = "factual"
    elif any(kw in msg_lower for kw in ANALYTICAL_KEYWORDS):
        intent.intent_type = "analytical"
    else:
        intent.intent_type = "advisory"
    
    # Detect domains
    domains = ["p6"]  # Always include P6 as baseline
    if any(kw in msg_lower for kw in SAP_KEYWORDS):
        domains.append("sap")
    if any(kw in msg_lower for kw in TC_KEYWORDS):
        domains.append("tc")
    intent.domains = domains
    
    # Detect portfolio-level questions
    if any(kw in msg_lower for kw in PORTFOLIO_KEYWORDS):
        intent.is_portfolio = True
    
    return intent


def classify_intent_llm(message: str, history: list = None, project_names: list = None) -> ChatIntent:
    """LLM-powered classification for higher accuracy.
    
    Uses Ollama (fast ~200ms) to extract structured intent.
    Falls back to local classification if LLM fails.
    """
    from routers.ai import call_ollama, call_azure_openai_curl, get_ai_provider
    
    project_list_hint = ""
    if project_names:
        # Give the LLM a hint about valid project names
        sample = project_names[:20]
        project_list_hint = f"\nKnown project names (use these to match): {', '.join(sample)}"
    
    history_context = ""
    if history and len(history) > 0:
        last_msgs = history[-3:]  # Last 3 messages for context
        history_context = "\nRecent conversation:\n" + "\n".join(
            f"- {m.get('role', 'user')}: {m.get('content', '')[:100]}" for m in last_msgs
        )
    
    prompt = f"""You are an intent classifier for a project management chatbot. Extract structured information from the user's question.
{project_list_hint}
{history_context}

User question: "{message}"

Classify and extract:
1. "projects": List of specific project names mentioned. Empty [] if asking about portfolio/all projects.
2. "type": One of "factual" (asking for a specific number/date/status), "analytical" (asking for comparison/trend/root-cause), "advisory" (asking for recommendations/reports/strategy), "document" (asking about definitions/policies/formulas)
3. "domains": Which data systems are needed. Choose from: "p6" (schedule/activities/progress), "sap" (materials/procurement/inventory/vendors), "tc" (transmission lines/grid connectivity)
4. "is_portfolio": true if asking about all/multiple projects, false if about a specific one

Output valid JSON only:
{{"projects":[],"type":"","domains":[],"is_portfolio":false}}"""

    try:
        messages = [{"role": "user", "content": prompt}]
        provider = get_ai_provider()
        if provider == "azure":
            result = call_azure_openai_curl(
                messages=messages,
                temperature=0,
                max_tokens=200,
                json_response=True,
            )
        else:
            result = call_ollama(
                messages=messages,
                temperature=0,
                max_tokens=200,
                json_response=True,
            )
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:-3].strip()
        elif result.startswith("```"):
            result = result[3:-3].strip()
        
        parsed = json.loads(result)
        
        intent = ChatIntent(
            projects=parsed.get("projects", []),
            intent_type=parsed.get("type", "advisory"),
            domains=parsed.get("domains", ["p6"]),
            is_portfolio=parsed.get("is_portfolio", False),
            raw_question=message,
        )
        
        # Validate intent_type
        if intent.intent_type not in ("factual", "analytical", "advisory", "document"):
            intent.intent_type = "advisory"
        
        # Ensure at least one domain
        if not intent.domains:
            intent.domains = ["p6"]
        
        logger.info(f"LLM intent: type={intent.intent_type}, projects={intent.projects}, domains={intent.domains}")
        return intent
        
    except Exception as e:
        logger.warning(f"LLM intent classification failed: {e}, falling back to local")
        return classify_intent_local(message, history)


def classify_intent(message: str, history: list = None, project_names: list = None, use_llm: bool = True) -> ChatIntent:
    """Main entry point for intent classification.
    
    Tries LLM first (if enabled), falls back to keyword-based classification.
    """
    if use_llm:
        try:
            return classify_intent_llm(message, history, project_names)
        except Exception:
            pass
    
    return classify_intent_local(message, history)
