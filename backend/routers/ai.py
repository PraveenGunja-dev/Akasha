from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import os
import json
import logging
from openai import AzureOpenAI
from groq import Groq
from database import get_db
from services.project_service import calculate_project_360_metrics

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []

def get_ai_client():
    from dotenv import load_dotenv
    load_dotenv(override=True)
    provider = os.environ.get("AI_PROVIDER", "groq").lower()
    
    if provider == "azure":
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
        if not all([endpoint, api_key, api_version]):
            raise HTTPException(status_code=500, detail="Azure OpenAI credentials missing from environment.")
        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version
        ), "azure"
    else:
        api_key = os.environ.get("AKASHA_AI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="AKASHA_AI_API_KEY environment variable not set.")
        return Groq(api_key=api_key), "groq"

@router.post("/chat")
def chat_with_copilot(req: ChatRequest, db: Session = Depends(get_db)):
    client, provider = get_ai_client()
    try:
        project_data = calculate_project_360_metrics(db)
        context_str = "Live Portfolio Context (Top 5 Riskiest Projects):\n"
        for p in project_data[:5]:
            context_str += f"- Project {p['projectName']}: Health={p['health']}, SPI={p['spi']}, CPI={p['cpi']}, RiskScore={p['riskScore']}, Issue={p['keyIssue']}\n"
    except Exception as e:
        context_str = "Context unavailable."

    system_prompt = f"""You are AKASHA Copilot, an elite AI Executive Assistant for the CEO of a Fortune 500 infrastructure company. 
You have deep expertise in Primavera P6 and SAP R/3. Keep responses concise, highly analytical, and strictly business-focused.

CRITICAL INSTRUCTION: You MUST base your answers STRICTLY and EXCLUSIVELY on the Live Portfolio Context provided below. 
Do NOT use outside knowledge, and do NOT hallucinate or guess information. 
If the user's question cannot be fully answered using the provided context, respond professionally with a message similar to: 
"I apologize, but this query falls outside the scope of my current dataset. As an AI Executive Assistant, my insights are strictly grounded in the live portfolio context provided. If you have additional data you would like me to analyze, please let me know."

Live Portfolio Context:
{context_str}
"""
    messages = [{"role": "system", "content": system_prompt}]
    for h in req.history[-10:]:
        role = "assistant" if h.get("type") == "bot" else "user"
        messages.append({"role": role, "content": h.get("content")})
    messages.append({"role": "user", "content": req.message})

    try:
        model_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME") if provider == "azure" else "llama-3.3-70b-versatile"
        response = client.chat.completions.create(
            messages=messages,
            model=model_name,
            temperature=0.3,
            max_tokens=800
        )
        return {"response": response.choices[0].message.content}
    except Exception as e:
        logger.error(f"AKASHA AI API Error: {e}")
        error_msg = str(e).replace("groq", "ai").replace("Groq", "AKASHA AI Provider")
        raise HTTPException(status_code=500, detail=error_msg)

@router.get("/generate-briefing")
def generate_executive_briefing(db: Session = Depends(get_db)):
    client, provider = get_ai_client()
    try:
        project_data = calculate_project_360_metrics(db)
        context_str = json.dumps(project_data[:10], indent=2)
    except Exception as e:
        context_str = "[]"

    prompt = f"""You are an elite AI Executive Analyst. Analyze the following live project portfolio data.

You MUST output your response in JSON format. Generate an Executive Briefing consisting of:
1. "toplineSummary": A 2-3 sentence overarching summary of the portfolio health and immediate critical risks.
2. "keyActions": An array of exactly 3 most critical action items. Each item must have:
   - "type": (e.g., "Critical Bottleneck", "Financial Risk", "Schedule Milestone")
   - "title": A short title
   - "description": A detailed explanation of the issue and recommended action
   - "color": Hex color code (e.g., "#EF4444" for red/critical, "#F59E0B" for yellow/financial, "#10B981" for green/milestone)
3. "deepDive": An array of 2 detailed analytical paragraphs uncovering hidden correlations (e.g., how a vendor delay is causing a schedule slip). Each item must have:
   - "title": Topic title
   - "description": The detailed analysis paragraph

You MUST output ONLY valid json in the exact structure below, with no markdown formatting or extra text:
{{
  "toplineSummary": "...",
  "keyActions": [
    {{ "type": "...", "title": "...", "description": "...", "color": "..." }}
  ],
  "deepDive": [
    {{ "title": "...", "description": "..." }}
  ]
}}

Data:
{context_str}
"""
    try:
        model_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME") if provider == "azure" else "llama-3.3-70b-versatile"
        kwargs = {
            "messages": [{"role": "user", "content": prompt}],
            "model": model_name,
            "temperature": 0.2,
            "max_tokens": 1500
        }
        if provider == "groq":
            kwargs["response_format"] = {"type": "json_object"}
            
        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        logger.error(f"AKASHA AI API Error: {e}")
        error_msg = str(e).replace("groq", "ai").replace("Groq", "AKASHA AI Provider")
        raise HTTPException(status_code=500, detail=error_msg)

@router.post("/project-diagnostic")
def generate_project_diagnostic(project: dict):
    client, provider = get_ai_client()
    prompt = f"""You are an elite AI Project Manager. Analyze the following live project data.
Provide a concise, highly analytical, 2-3 sentence diagnostic of the project's health. 
Highlight the biggest risk (e.g., schedule delay, low material availability, bad SPI/CPI) and recommend a mitigation step.
Be completely factual and strict. No fluff.

Project Data:
{json.dumps(project, indent=2)}
"""
    try:
        model_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME") if provider == "azure" else "llama-3.3-70b-versatile"
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            temperature=0.2,
            max_tokens=200
        )
        return {"diagnostic": response.choices[0].message.content}
    except Exception as e:
        logger.error(f"AKASHA AI API Error: {e}")
        raise HTTPException(status_code=500, detail="Diagnostic generation failed.")
