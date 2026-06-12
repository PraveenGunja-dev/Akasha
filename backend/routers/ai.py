from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import os
import json
import logging
import subprocess
from groq import Groq
from database import get_db
from services.project_service import calculate_project_360_metrics

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []
    projectId: str = None

def call_azure_openai_curl(messages, temperature, max_tokens, json_response=False):
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
    
    if not all([endpoint, api_key, api_version, deployment]):
        raise Exception("Azure OpenAI credentials missing from environment.")
        
    # Strip trailing slash from endpoint if present
    endpoint = endpoint.rstrip("/")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if json_response:
        payload["response_format"] = {"type": "json_object"}
        
    # Write payload to a temporary file to avoid command-line length limits or escaping issues
    import uuid
    temp_file = f"temp_payload_{uuid.uuid4().hex}.json"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)
        
    cmd = [
        "curl.exe",
        "-k",
        "--noproxy", "*",
        "-X", "POST",
        url,
        "-H", "Content-Type: application/json",
        "-H", f"api-key: {api_key}",
        "-d", f"@{temp_file}",
        "-s"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
    if result.returncode != 0:
        raise Exception(f"Curl failed: {result.stderr}")
        
    try:
        data = json.loads(result.stdout)
        if "error" in data:
            raise Exception(f"Azure Error: {data['error'].get('message', str(data['error']))}")
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise Exception(f"Failed to parse Azure response. Output: {result.stdout[:200]}... Error: {str(e)}")


def get_ai_provider():
    from dotenv import load_dotenv
    load_dotenv(override=True)
    return os.environ.get("AI_PROVIDER", "groq").lower()

def call_ollama(messages, temperature, max_tokens, json_response=False):
    import openai
    import os
    
    endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://192.168.0.56:11434/v1")
    model_name = os.environ.get("OLLAMA_MODEL", "llama3")
    
    client = openai.OpenAI(
        base_url=endpoint,
        api_key="ollama" # Ollama doesn't require a strict API key
    )
    
    kwargs = {
        "messages": messages,
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if json_response:
        kwargs["response_format"] = {"type": "json_object"}
        
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


@router.post("/chat")
def chat_with_copilot(req: ChatRequest, db: Session = Depends(get_db)):
    provider = get_ai_provider()
    try:
        if req.projectId:
            from services.project_service import get_project_360_detail
            detail = get_project_360_detail(db, req.projectId)
            if detail and "error" not in detail:
                p6 = detail.get("p6", {})
                sap_vendors = detail.get("sap", {}).get("vendorBreakdown", [])
                context_str = f"Live Context for Specific Project ({req.projectId}):\n"
                context_str += f"- Name: {p6.get('name')}\n"
                context_str += f"- Status: {p6.get('status')} | SPI: {p6.get('spi')} | CPI: {p6.get('cpi')}\n"
                context_str += f"- Schedule: {p6.get('startDate')} to {p6.get('forecastFinish' if p6.get('forecastFinish') else 'finishDate')}\n"
                context_str += f"- Variance: {p6.get('scheduleVariance', 0)} days\n"
                context_str += f"- Top Vendors: {', '.join([v.get('vendorName', '') for v in sap_vendors[:3]])}\n"
            else:
                context_str = f"Could not fetch details for project {req.projectId}.\n"
        else:
            project_data = calculate_project_360_metrics(db)
            context_str = "Live Portfolio Context (Top 5 Riskiest Projects):\n"
            for p in project_data[:5]:
                context_str += f"- Project {p['projectName']}: Health={p['health']}, SPI={p['spi']}, CPI={p['cpi']}, RiskScore={p['riskScore']}, Issue={p['keyIssue']}\n"
    except Exception as e:
        context_str = f"Context unavailable. Error: {str(e)}"

    system_prompt = f"""You are an Executive Intelligence Analyst for a large-scale infrastructure and renewable energy project.

Your role is to analyze all available project data, KPIs, schedules, engineering records, procurement records, material management data, construction progress, workforce information, quality metrics, safety metrics, financial data, and risk indicators.

Your objective is not only to report the data but also to generate actionable business insights.

For every analysis:
1. Explain what the data indicates.
2. Identify positive trends and achievements.
3. Identify negative trends, bottlenecks, delays, inefficiencies, and risks.
4. Detect anomalies, unusual patterns, and outliers.
5. Identify root causes wherever possible.
6. Compare actual performance against targets.
7. Highlight critical KPIs requiring immediate attention.
8. Predict future risks if current trends continue.
9. Estimate likely impacts on:
   - Schedule
   - Cost
   - Resource utilization
   - Procurement
   - Material availability
   - Productivity
   - Safety
   - Quality

10. Provide recommendations categorized as:
    - Immediate Actions (0-7 days)
    - Short-Term Actions (1-4 weeks)
    - Medium-Term Actions (1-3 months)
    - Strategic Improvements

11. Prioritize recommendations based on:
    - Business Impact
    - Cost Impact
    - Schedule Impact
    - Ease of Implementation

12. Generate an Executive Summary suitable for CEO/Director review.

13. Generate a Project Health Assessment:
    - Overall Health Score (0-100)
    - Schedule Health
    - Cost Health
    - Procurement Health
    - Material Health
    - Engineering Health
    - Construction Health
    - Safety Health
    - Quality Health

14. For every issue found:
    - Problem
    - Evidence from data
    - Impact
    - Recommendation
    - Priority (Low/Medium/High/Critical)

15. Be highly analytical and data-driven.
Never make assumptions without mentioning confidence levels.

CRITICAL INSTRUCTION: You MUST output your response in STRICT JSON format with exactly two keys: "response" and "suggestions". 
"response" must contain your detailed analytical answer in markdown format. 
"suggestions" must be an array of exactly 3 concise, highly relevant follow-up questions the user might ask next based on your answer.

Example Output format:
{{
  "response": "Based on the data...",
  "suggestions": ["Why is Project A delayed?", "Show me the CAPEX impact", "What are the recommended actions?"]
}}

CRITICAL INSTRUCTION: You MUST base your answers STRICTLY and EXCLUSIVELY on the Live Portfolio Context provided below. 
Do NOT use outside knowledge, and do NOT hallucinate or guess information.

Live Portfolio Context:
{context_str}
"""
    messages = [{"role": "system", "content": system_prompt}]
    for h in req.history[-10:]:
        role = "assistant" if h.get("type") == "bot" else "user"
        messages.append({"role": role, "content": h.get("content")})
    messages.append({"role": "user", "content": req.message})

    try:
        if provider == "azure":
            content = call_azure_openai_curl(messages, temperature=0.3, max_tokens=1000, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.3, max_tokens=1000, json_response=True)
            
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        data = json.loads(content)
        return {
            "response": data.get("response", "Could not parse response."),
            "suggestions": data.get("suggestions", [])
        }
    except Exception as e:
        logger.error(f"AKASHA AI API Error: {e}")
        error_msg = str(e).replace("groq", "ai").replace("Groq", "AKASHA AI Provider")
        raise HTTPException(status_code=500, detail=error_msg)

@router.get("/generate-briefing")
def generate_executive_briefing(db: Session = Depends(get_db)):
    provider = get_ai_provider()
    try:
        project_data = calculate_project_360_metrics(db)
        context_str = json.dumps(project_data[:10], indent=2)
    except Exception as e:
        context_str = "[]"

    prompt = f"""You are an Executive Intelligence Analyst for a large-scale infrastructure and renewable energy project.

Your role is to analyze all available project data, KPIs, schedules, engineering records, procurement records, material management data, construction progress, workforce information, quality metrics, safety metrics, financial data, and risk indicators.
Your objective is not only to report the data but also to generate actionable business insights.

You MUST output your response in STRICT JSON format, generating an Executive Briefing consisting of:
1. "toplineSummary": A 2-3 sentence overarching summary of the portfolio health and immediate critical risks.
2. "keyActions": An array of exactly 3 most critical action items. Each item must have:
   - "type": (e.g., "Critical Bottleneck", "Financial Risk", "Schedule Milestone")
   - "title": A short title
   - "description": A detailed explanation of the issue and recommended action
   - "color": Hex color code (e.g., "#EF4444" for red/critical, "#F59E0B" for yellow/financial, "#10B981" for green/milestone)
3. "deepDive": An array of 2 detailed analytical paragraphs uncovering hidden correlations (e.g., how a vendor delay is causing a schedule slip). Each item must have:
   - "title": Topic title
   - "description": The detailed analysis paragraph
4. "confidenceScore": An integer between 0 and 100 representing the accuracy or confidence level of this analysis based on the completeness and quality of the provided data.

Be highly analytical and data-driven. Never make assumptions without mentioning confidence levels.
You MUST base your answers STRICTLY and EXCLUSIVELY on the Live Portfolio Context provided below. 
Do NOT use outside knowledge, and do NOT hallucinate or guess information.

You MUST output ONLY valid json in the exact structure below, with no markdown formatting or extra text:
{{
  "toplineSummary": "...",
  "confidenceScore": 95,
  "keyActions": [
    {{ "type": "...", "title": "...", "description": "...", "color": "..." }}
  ],
  "deepDive": [
    {{ "title": "...", "description": "..." }}
  ]
}}

Live Portfolio Context:
{context_str}
"""
    messages = [{"role": "user", "content": prompt}]
    
    try:
        if provider == "azure":
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=1500, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=1500, json_response=True)
            
        content = content.strip()
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
    provider = get_ai_provider()
    prompt = f"""You are an elite AI Project Manager. Analyze the following live project data.
Provide a concise, highly analytical, 2-3 sentence diagnostic of the project's health. 
Highlight the biggest risk (e.g., schedule delay, low material availability, bad SPI/CPI) and recommend a mitigation step.
Be completely factual and strict. No fluff.

Project Data:
{json.dumps(project, indent=2)}
"""
    messages = [{"role": "user", "content": prompt}]
    
    try:
        if provider == "azure":
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=200)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=200)
        return {"diagnostic": content}
    except Exception as e:
        logger.error(f"AKASHA AI API Error: {e}")
        raise HTTPException(status_code=500, detail="Diagnostic generation failed.")

