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

def call_groq(messages, temperature, max_tokens, json_response=False):
    import os
    from groq import Groq
    api_key = os.environ.get("AKASHA_AI_API_KEY")
    if not api_key:
        raise Exception("Groq API key missing in environment")
    client = Groq(api_key=api_key)
    
    kwargs = {
        "messages": messages,
        "model": "llama3-70b-8192",
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if json_response:
        kwargs["response_format"] = {"type": "json_object"}
        
    chat_completion = client.chat.completions.create(**kwargs)
    return chat_completion.choices[0].message.content

def call_ollama(messages, temperature, max_tokens, json_response=False):
    import openai
    import httpx
    import os
    
    endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://192.168.0.56:11434/v1")
    model_name = os.environ.get("OLLAMA_MODEL", "llama3")
    
    client = openai.OpenAI(
        base_url=endpoint,
        api_key="ollama",
        timeout=httpx.Timeout(120.0, connect=30.0)
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

from fastapi import APIRouter, Depends, HTTPException, Body

@router.post("/simulation-lab")
def run_simulation_lab(project: dict = Body(...), db: Session = Depends(get_db)):
    from services.project_service import get_project_360_detail
    provider = get_ai_provider()
    
    project_name = project.get("project_name", "")
    deep_data = {}
    if project_name and project_name != 'Entire Portfolio':
        detail = get_project_360_detail(db, project_name)
        if detail and "error" not in detail:
            deep_data = detail

    prompt = f"""You are the AKASHA AI Simulation Engine. You are running a deep diagnostic on the following live project data to detect critical risks and provide strategic recommendations.
You must analyze the deep data (including P6 schedules, SAP procurement records, and TC engineering data) to identify exact bottlenecks.
Do not make up generic issues. Identify actual materials that are late, specific labor issues, or specific variance details found in the data.

Project Summary:
{json.dumps(project, indent=2)}

Deep System Data (P6, SAP, TC):
{json.dumps(deep_data, indent=2)[:8000]}

You MUST output your response in STRICT JSON format, consisting of:
1. "issues": An array of exactly 4 AI-Detected issues (at least 2 critical, 2 warning). Each must have:
   - "title": A detailed description of the issue and its cascading impact referencing REAL data points (e.g. "Transformer delivery delayed by 15 days in SAP").
   - "severity": Either "Critical" or "Warning"
2. "suggestions": An array of exactly 2 actionable AI Strategy Recommendations. Each must have:
   - "title": Strategy title
   - "description": Detailed strategy and estimated impact.
3. "scheduleImpact": An array of 3 numbers representing estimated "Days Delayed" for [Foundation, Module Installation, Grid Connection].

You MUST output ONLY valid json in the exact structure below, with no markdown formatting or extra text:
{{
  "issues": [
    {{ "title": "...", "severity": "Critical" }}
  ],
  "suggestions": [
    {{ "title": "...", "description": "..." }}
  ],
  "scheduleImpact": [12, 5, 20]
}}
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

class StrategiesRequest(BaseModel):
    project: dict
    constraints: dict

@router.post("/simulation-lab/strategies")
def generate_strategies(req: StrategiesRequest, db: Session = Depends(get_db)):
    from services.project_service import get_project_360_detail
    provider = get_ai_provider()
    
    project_name = req.project.get("project_name", "")
    deep_data = {}
    if project_name and project_name != 'Entire Portfolio':
        detail = get_project_360_detail(db, project_name)
        if detail and "error" not in detail:
            deep_data = detail

    prompt = f"""You are the AKASHA AI Strategy Engine. Generate 3 distinct recovery strategies based on the following real project data and user constraints.
You must ground your strategies in the actual SAP, P6, and TC data below.
    
Project Summary:
{json.dumps(req.project, indent=2)}

Deep System Data (P6, SAP, TC):
{json.dumps(deep_data, indent=2)[:8000]}

User Constraints:
{json.dumps(req.constraints, indent=2)}

You MUST output strictly in valid JSON format:
{{
  "strategies": [
    {{
      "id": "strategy_1",
      "title": "...",
      "description": "...",
      "type": "Selective Acceleration",
      "cost_impact_cr": 12.0,
      "time_saved_days": 14,
      "risk_reduction_pct": 78,
      "ai_confidence_pct": 87,
      "recommended": true,
      "radar_data": [80, 60, 90, 85, 87] 
    }}
  ]
}}
Note: "radar_data" is an array of 5 integers (0-100) representing [Feasibility, Cost Efficiency, Speed, Risk Reduction, Confidence]. Exactly 3 strategies. Only one should have "recommended": true.
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        if provider == "azure":
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=1500, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=1500, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SimulationExecuteRequest(BaseModel):
    project: dict
    strategy: dict

@router.post("/simulation-lab/simulate")
def generate_simulation(req: SimulationExecuteRequest):
    provider = get_ai_provider()
    prompt = f"""You are the AKASHA AI Simulation Engine. Simulate the trajectory of project completion over the next 5 months.
    
Project Context:
{json.dumps(req.project, indent=2)}

Strategy Applied:
{json.dumps(req.strategy, indent=2)}

Generate a 5-month completion timeline comparing the "baseline" (if no strategy applied) vs "simulated" (with the strategy applied).
The project's current completion is {req.project.get('progress', 0)}%.
Output valid JSON only:
{{
  "timeline": [
    {{"month": "M1", "baseline": 45, "simulated": 50}},
    {{"month": "M2", "baseline": 50, "simulated": 65}},
    {{"month": "M3", "baseline": 55, "simulated": 80}},
    {{"month": "M4", "baseline": 60, "simulated": 95}},
    {{"month": "M5", "baseline": 65, "simulated": 100}}
  ]
}}
Ensure the simulated values generally outpace baseline values, ending at or near 100 based on the strategy.
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        if provider == "azure":
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=1500, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=1500, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/simulation-lab/execute")
def execute_strategy(req: SimulationExecuteRequest):
    provider = get_ai_provider()
    prompt = f"""You are the AKASHA AI Execution Engine. Generate the automated task directives that will be pushed to integrated systems (SAP, PMAG, Contractor Portal) based on the chosen strategy.
    
Project Context:
{json.dumps(req.project, indent=2)}

Strategy Applied:
{json.dumps(req.strategy, indent=2)}

Output valid JSON only consisting of 3 to 5 execution tasks:
{{
  "tasks": [
    {{
      "system": "SAP", 
      "action": "Generate PR", 
      "description": "Expedite module procurement...", 
      "status": "Pending"
    }}
  ]
}}
Systems can be SAP, PMAG, Contractor Portal, HRMS, etc.
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        if provider == "azure":
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=1500, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=1500, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/simulation-lab/report")
def generate_report(req: SimulationExecuteRequest):
    # Generate an executive report based on the executed strategy
    provider = get_ai_provider()
    prompt = f"""You are Akasha, an Enterprise Project Intelligence Assistant.
Your role is to analyze project data and provide insights, not perform core project calculations.

## Important Rules
1. Never invent project data.
2. Never assume values that are not provided.
3. Use only the supplied project information.
4. If required data is missing, explicitly state it.
5. Explain risks, delays, trends, and impacts based on the data.
6. Provide actionable recommendations.
7. Always justify recommendations using the provided metrics.

CRITICAL INSTRUCTION: Keep all answers highly concise, short, and crisp. Use a maximum of 2 sentences per paragraph or point. Do not provide long explanations.

## What You Must Do
Analyze the following project summary and the selected strategy:
Project: '{req.project.get('project_name')}'
Strategy Applied: {json.dumps(req.strategy, indent=2)}

Provide:
1. Executive Summary
2. Key Findings
3. Risk Assessment
4. Root Cause Analysis
5. Recommended Actions
6. Expected Outcome

## What You Must NOT Do
Do not calculate: SPI, CPI, Delay Percentage, Project Health Score, Forecast Completion Dates. These values are provided by the platform's business logic engine. Use them only for analysis and recommendations.

Output valid JSON only matching this exact structure:
{{
   "title": "Executive Execution Report",
   "executiveSummary": "...",
   "keyFindings": ["...", "..."],
   "riskAssessment": "...",
   "rootCauseAnalysis": "...",
   "recommendedActions": ["...", "..."],
   "expectedOutcome": "..."
}}
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        if provider == "azure":
            content = call_azure_openai_curl(messages, temperature=0.1, max_tokens=1000, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.1, max_tokens=1000, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/project-diagnostic")
def project_diagnostic(project: dict = Body(...), db: Session = Depends(get_db)):
    provider = get_ai_provider()
    prompt = f"""You are Akasha, an Enterprise Project Intelligence Assistant.
Your role is to analyze project data and provide insights, not perform core project calculations.

## Important Rules
1. Never invent project data.
2. Never assume values that are not provided.
3. Use only the supplied project information.
4. Explain risks, delays, trends, and impacts based on the data.
5. Provide actionable recommendations.
6. Always justify recommendations using the provided metrics.

CRITICAL INSTRUCTION: Keep all answers highly concise, short, and crisp. Use a maximum of 2 sentences per paragraph or point. Do not provide long explanations.

## What You Must Do
Analyze the following project summary:
{json.dumps(project, indent=2)}

Provide:
1. Executive Summary
2. Key Findings
3. Risk Assessment
4. Root Cause Analysis
5. Recommended Actions
6. Expected Outcome

## What You Must NOT Do
Do not calculate: SPI, CPI, Delay Percentage, Project Health Score, Forecast Completion Dates. Use the provided metrics only for analysis.

Output valid JSON only matching this exact structure:
{{
   "executiveSummary": "...",
   "keyFindings": ["...", "..."],
   "riskAssessment": "...",
   "rootCauseAnalysis": "...",
   "recommendedActions": ["...", "..."],
   "expectedOutcome": "..."
}}
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        if provider == "azure":
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=1500, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=1500, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




