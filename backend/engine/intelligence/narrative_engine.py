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
    
    # Extract top insights to feed to the LLM
    insights_text = "\n".join(
        f"- [{i.get('severity', 'info').upper()}] {i.get('title')}: {i.get('impact')}"
        for i in intel.get("top_insights", [])[:5]
    )
    
    # Extract next steps
    actions_text = "\n".join(
        f"- {a.get('action')} (Assigned to: {a.get('assigned_role')})"
        for a in intel.get("next_steps", [])[:3]
    )

    prompt = f"""You are an Executive AI Assistant for a large renewable energy and transmission portfolio.
Your task is to write a concise, highly professional 2-3 paragraph executive briefing for project: {project_name}.

Here is the raw intelligence data computed by the Akasha Engine:
- Current Status: {status}
- Overall Health Score: {health.get('overall', 'N/A')}/100
- Schedule Delay: {delay} days
- Primary Bottleneck Domain: {bottleneck}

Key Insights:
{insights_text}

Recommended Actions:
{actions_text}

Instructions:
1. Write a direct, hard-hitting executive summary of the project's current state. No fluff.
2. Highlight the main reason for any delays or critical issues (the root cause).
3. Conclude with what needs to happen next based on the recommended actions.
4. Do NOT use overly flowery language. Use project management and engineering terminology.
5. Format the output in Markdown with bold text for emphasis where appropriate, but DO NOT use headers (#).
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

