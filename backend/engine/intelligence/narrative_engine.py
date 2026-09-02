"""
Akasha Intelligence Engine — Narrative Generation

Uses the configured LLM (Ollama, Groq, or Azure) to generate
a human-readable executive briefing from the structured intelligence data.

Read-only: never modifies existing data.
"""

import logging
import json
import os
from typing import Dict, Any

from routers.ai import get_ai_provider, call_ollama, call_groq, call_azure_openai_curl

logger = logging.getLogger(__name__)


def generate_executive_briefing(intel: Dict[str, Any]) -> str:
    """
    Takes the computed intelligence report (insights, health scores, delays, etc.)
    and uses the configured LLM to generate a 2-3 paragraph narrative summary.
    """
    if not intel or not intel.get("has_data"):
        return "Not enough data available to generate an executive briefing."

    project_name = intel.get("project_name", "the project")
    status = intel.get("overall_status", "UNKNOWN")
    delay = intel.get("total_delay_days", 0)
    health = intel.get("health_scores", {})
    bottleneck = intel.get("primary_bottleneck", "None")
    
    # Extract top insights to feed to the LLM (expanded to ensure we don't miss anything)
    all_insights = intel.get("top_insights", [])[:10]
    insights_text = "\n".join(
        f"- [{i.get('severity', 'info').upper()}] {i.get('title')}: {i.get('description', '')} -> {i.get('impact')}"
        for i in all_insights
    )
    
    # Extract next steps
    actions_text = "\n".join(
        f"- {a.get('title', a.get('action'))} (Assigned to: {a.get('assigned_role')}) Reason: {a.get('description', a.get('reason', ''))}"
        for a in intel.get("next_steps", [])[:4]
    )

    quality = intel.get("quality", {})
    materials = intel.get("materials", {})
    
    q_summary = f"Open Critical NCs: {quality.get('summary', {}).get('critical_open', 0)}. Pending RFIs: {quality.get('summary', {}).get('rfis_pending', 0)}."
    m_summary = f"Overdue POs: {materials.get('summary', {}).get('overdue_po_count', 0)}. Fulfillment: {materials.get('summary', {}).get('fulfillment_pct', 0)}%."

    prompt = f"""You are an Executive AI Assistant for a large renewable energy and transmission portfolio.
Your task is to write a concise, highly professional 2-3 paragraph executive briefing for project: {project_name}.

Here is the raw intelligence data computed by the Akasha Engine:
- Current Status: {status}
- Overall Health Score: {health.get('overall', 'N/A')}/100
- Schedule Delay: {delay} days
- Primary Bottleneck Domain: {bottleneck}
- Quality Pulse: {q_summary}
- Supply Chain Pulse: {m_summary}

Key Insights & Root Causes:
{insights_text}

Recommended Actions & Accountability:
{actions_text}

Instructions:
1. Act as an advanced Intelligence Engine. Provide a highly structured, hard-hitting flash-briefing.
2. Structure the output using EXACTLY these three bold inline headers:
   **STATUS:** [1 sentence summary of health & delay. Note: Health Score (0-100) measures overall vitality.]
   **ROOT CAUSE (WHY):** [2 sentences on exactly why the project is lagging. You MUST explicitly name specific Vendors, Contractors, or exact NC/RFI counts if they are causing delays. Do not be vague.]
   **ACCOUNTABILITY (WHO):** [1-2 sentences on exactly what must be done next and WHO is assigned to do it (e.g. Site PM, Procurement Head)]
3. Extreme brevity is required. Keep the entire response under 100 words.
4. Do NOT use markdown headers (#) or conversational filler.
5. Use executive terminology. No fluff.
"""

    messages = [
        {"role": "system", "content": "You are a senior project director providing clear, data-driven executive updates."},
        {"role": "user", "content": prompt}
    ]

    provider = get_ai_provider()
    
    try:
        if provider == "azure":
            logger.info(f"Generating narrative via Azure OpenAI for {project_name}")
            return call_azure_openai_curl(messages, temperature=0.3, max_tokens=500)
        elif provider == "groq":
            logger.info(f"Generating narrative via Groq for {project_name}")
            return call_groq(messages, temperature=0.3, max_tokens=500)
        else:
            logger.info(f"Generating narrative via Ollama (Local) for {project_name}")
            return call_ollama(messages, temperature=0.3, max_tokens=500)
    except Exception as e:
        logger.error(f"Failed to generate narrative: {e}")
        return f"*(AI Narrative Generation Failed: {str(e)})*\n\nBased on raw data, the project is in {status} status and is {delay} days behind schedule. The primary bottleneck is {bottleneck}."

