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
        "model": "llama-3.3-70b-versatile",
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

Your objective is to provide short, crisp, and highly accurate insights based ONLY on the provided project data.

Important Rules:
1. Be extremely concise. Use short sentences and bullet points.
2. Do not generate long, repetitive reports unless explicitly asked by the user.
3. Answer the user's question directly based on the data provided.
4. If asked for a summary, highlight only the most critical KPI deviations, top risks, and immediate actions.
5. The supply chain quantities in the data are in absolute Units, NOT Megawatts (MW). Use "Units" instead of "MW".
6. Never invent project data or hallucinate. Use only the supplied project information.

CRITICAL INSTRUCTION: You MUST output your response in STRICT JSON format with exactly two keys: "response" and "suggestions". 
"response" must contain your detailed but concise analytical answer in markdown format. 
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
            content = call_azure_openai_curl(messages, temperature=0.3, max_tokens=4000, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.3, max_tokens=4000, json_response=True)
            
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        try:
            data = json.loads(content)
        except Exception:
            data = {
                "response": content,
                "suggestions": []
            }
            
        return {
            "response": data.get("response", content),
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
IMPORTANT: The supply chain quantities in the data are in absolute Units, NOT Megawatts (MW). Do not use "MW" or "Megawatts". Use "Units" instead.

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
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=4000, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=4000, json_response=True)
            
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        try:
            return json.loads(content)
        except Exception:
            return {
                "toplineSummary": "Failed to parse AI response.",
                "confidenceScore": 0,
                "keyActions": [],
                "deepDive": [{"title": "Raw Output", "description": content}]
            }
    except Exception as e:
        logger.error(f"AKASHA AI API Error: {e}")
        error_msg = str(e).replace("groq", "ai").replace("Groq", "AKASHA AI Provider")
        raise HTTPException(status_code=500, detail=error_msg)

from fastapi import APIRouter, Depends, HTTPException, Body

USE_VARIANCE_ENGINE = os.environ.get("USE_VARIANCE_ENGINE", "true").lower() == "true"

from typing import Optional, List, Dict, Any

class SimulationLabRequest(BaseModel):
    project: dict
    notification_context: Optional[dict] = None
    all_notifications: Optional[list] = []

@router.post("/simulation-lab")
def run_simulation_lab(req: SimulationLabRequest, db: Session = Depends(get_db)):
    from services.project_service import get_project_360_detail
    provider = get_ai_provider()
    
    project = req.project
    project_name = project.get("project_name", "")
    notif_ctx = req.notification_context
    all_notifs = req.all_notifications

    # Build notification context string for the LLM
    notif_context_str = ""
    if notif_ctx:
        notif_context_str += f"""\n\n═══ TRIGGERED BY THIS SPECIFIC NOTIFICATION ═══
Change Type: {notif_ctx.get('change_type', 'Unknown')}
Activity: {notif_ctx.get('activity_name', 'N/A')}
Block: {notif_ctx.get('block', 'N/A')}
Old Value: {notif_ctx.get('old_value', 'N/A')} → New Value: {notif_ctx.get('new_value', 'N/A')}
Message: {notif_ctx.get('message', '')}

Focus your analysis on: How does this specific change cascade through dependent downstream activities?
What activities are blocked or delayed because of this? What is the best recovery path?"""
    if all_notifs:
        notif_summary = json.dumps(all_notifs[:15], indent=2, default=str)[:3000]
        notif_context_str += f"""\n\n═══ ALL RECENT NOTIFICATIONS FOR THIS PROJECT ═══
{notif_summary}

Use these notifications to understand the full picture of delays and changes happening on this project."""

    # ═══════════════════════════════════════════════════════════
    # HYBRID ARCHITECTURE: Deterministic Engine + LLM Narrative
    # ═══════════════════════════════════════════════════════════
    if USE_VARIANCE_ENGINE:
        from engine.variance import compute_full_variance, compute_portfolio_variance

        # 1. DETERMINISTIC: compute variance table from live DB data
        if project_name and project_name != 'Entire Portfolio':
            variance = compute_full_variance(db, project_name)
        else:
            variance = compute_portfolio_variance(db, top_n=10)

        # 2. LLM: explain and rank only — NEVER invent numbers
        # Truncate variance data to fit in context window
        variance_str = json.dumps(variance, indent=2, default=str)[:6000]

        prompt = f"""You are the AKASHA AI Diagnostic Engine.
The deterministic variance engine has already computed the data below from live P6, SAP, and TC databases.

CRITICAL RULES:
- Do NOT calculate or estimate any new numbers.
- Use ONLY the days, percentages, and quantities given in the Computed Variance Data below.
- Every number you mention must appear verbatim in the input data.
- The supply chain quantities are in absolute Units, NOT Megawatts (MW).
- Explicitly review the "tc" (Transmission) section. If there are at-risk transmission lines, factor them into your root cause and suggestions.
{notif_context_str}

Computed Variance Data:
{variance_str}

Project Summary:
{json.dumps(project, indent=2)}

Based ONLY on the computed data above, provide:
1. "issues": An array of exactly 4 root-cause explanations. At least 2 must be "Critical", rest "Warning". 
   Each must reference actual drift_days, gap_qty, or float_hours from the data above.
   If a notification trigger was provided, the FIRST issue MUST directly address that specific change and its cascading impact.
   Format: {{"title": "specific issue referencing real numbers from data", "severity": "Critical"|"Warning"}}
2. "suggestions": An array of exactly 2 actionable strategies referencing the specific bottleneck activities or materials from the data.
   Format: {{"title": "strategy name", "description": "detailed strategy referencing specific data points"}}

You MUST output ONLY valid JSON with no markdown or extra text:
{{
  "issues": [
    {{"title": "...", "severity": "Critical"}}
  ],
  "suggestions": [
    {{"title": "...", "description": "..."}}
  ]
}}"""
        messages = [{"role": "user", "content": prompt}]

        try:
            if provider == "azure":
                content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=4000, json_response=True)
            else:
                content = call_ollama(messages, temperature=0.2, max_tokens=4000, json_response=True)
                
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()

            try:
                llm_result = json.loads(content)
            except Exception:
                llm_result = {
                    "issues": [{"title": "AI analysis unavailable. Variance data computed successfully.", "severity": "Warning"}],
                    "suggestions": [],
                }

            # 3. MERGE: engine numbers (always) + LLM narrative (explanation only)
            return {
                "issues": llm_result.get("issues", []),
                "suggestions": llm_result.get("suggestions", []),
                "scheduleImpact": variance["schedule_impact"],  # ALWAYS from engine
                "variance": variance,  # full variance data for frontend drill-down
                "engine_version": "2.0",
            }

        except Exception as e:
            logger.error(f"LLM call failed, returning engine-only results: {e}")
            # Even if LLM fails, we still return deterministic data
            return {
                "issues": [{"title": "AI narrative unavailable. Review variance data below.", "severity": "Warning"}],
                "suggestions": [],
                "scheduleImpact": variance["schedule_impact"],
                "variance": variance,
                "engine_version": "2.0",
            }

    # ═══════════════════════════════════════════════════════════
    # LEGACY PATH (feature flag off — old LLM-only behavior)
    # ═══════════════════════════════════════════════════════════
    deep_data = {}
    if project_name and project_name != 'Entire Portfolio':
        detail = get_project_360_detail(db, project_name)
        if detail and "error" not in detail:
            deep_data = detail

    prompt = f"""You are the AKASHA AI Simulation Engine. You are running a deep diagnostic on the following live project data to detect critical risks and provide strategic recommendations.
You must analyze the deep data (including P6 schedules, SAP procurement records, and TC engineering data) to identify exact bottlenecks.
Do not make up generic issues. Identify actual materials that are late, specific labor issues, or specific variance details found in the data.
IMPORTANT: The supply chain quantities in the data are in absolute Units, NOT Megawatts (MW). Do not use "MW" or "Megawatts" in your analysis. Use "Units" instead.

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
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=4000, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=4000, json_response=True)
            
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        try:
            result = json.loads(content)
            result["engine_version"] = "1.0"  # legacy
            return result
        except Exception:
            return {
                "issues": [{"title": "Raw Output: " + content[:200], "severity": "Warning"}],
                "suggestions": [],
                "scheduleImpact": [0,0,0],
                "engine_version": "1.0",
            }
    except Exception as e:
        logger.error(f"AKASHA AI API Error: {e}")
        error_msg = str(e).replace("groq", "ai").replace("Groq", "AKASHA AI Provider")
        raise HTTPException(status_code=500, detail=error_msg)

class FinalReportRequest(BaseModel):
    project: dict
    strategy: dict
    tasks: list
    simulation_results: dict
    notification_context: Optional[dict] = None
    all_notifications: Optional[list] = []

class StrategiesRequest(BaseModel):
    project: dict
    constraints: dict
    notification_context: Optional[dict] = None
    all_notifications: Optional[list] = []

@router.post("/simulation-lab/strategies")
def generate_strategies(req: StrategiesRequest, db: Session = Depends(get_db)):
    from services.project_service import get_project_360_detail
    from engine.monte_carlo import run_monte_carlo_simulation
    from datetime import datetime
    
    provider = get_ai_provider()
    project_name = req.project.get("project_name", "")
    p6_id = req.project.get("p6", {}).get("id") or req.project.get("project_id", "") or project_name
    
    # 1. Run baseline deterministic simulation (no modifiers)
    # Using 500 iterations for speed during interactive session
    baseline_sim = run_monte_carlo_simulation(db, p6_id, iterations=500, seed=42)
    if "error" in baseline_sim:
        baseline_p50_date = datetime.today()
    else:
        baseline_p50_date = datetime.strptime(baseline_sim["completion_dates"]["p50"], "%Y-%m-%d")

    # Build notification context for strategies
    notif_str = ""
    if req.notification_context:
        nc = req.notification_context
        notif_str = f"""\n\nIMPORTANT CONTEXT - This simulation was triggered by a specific notification alert:
Change: {nc.get('change_type', 'Unknown')} | Activity: {nc.get('activity_name', 'N/A')} | Block: {nc.get('block', 'N/A')}
Old: {nc.get('old_value', 'N/A')} → New: {nc.get('new_value', 'N/A')}
Message: {nc.get('message', '')}

Your strategies MUST directly address recovering from this specific issue."""
    if req.all_notifications:
        notif_str += f"\n\nAll recent project notifications:\n{json.dumps(req.all_notifications[:10], indent=2, default=str)[:2000]}"

    # Deep Context extraction for LLM
    import models
    historical_str = "\n\nDEEP PROJECT CONTEXT & HISTORY:\n"
    past_delays = db.query(models.Notification).filter(
        models.Notification.project_name == project_name,
        models.Notification.change_type.in_(["Date Delay", "Critical Slip", "Delay"])
    ).order_by(models.Notification.created_at.desc()).limit(5).all()
    
    if past_delays:
        historical_str += "Past Delays & COD shifts:\n"
        for pd in past_delays:
            historical_str += f"- {pd.created_at.strftime('%Y-%m-%d')}: {pd.change_type} on {pd.activity_name or 'Project'} - {pd.message}\n"
    else:
        historical_str += "No significant historical delays found.\n"
        
    proj_map = db.query(models.ProjectMapping).filter(
        (models.ProjectMapping.project == project_name) | 
        (models.ProjectMapping.project_name_from_p6 == project_name) |
        (models.ProjectMapping.project_id == project_name)
    ).first()
    if proj_map:
        historical_str += f"Project Specs: Category={proj_map.category}, Capacity={proj_map.capacity_mwac} MW, SPV={proj_map.spv_name}\n"

    # 2. Get LLM to propose 3 strategy permutations based on user constraints
    prompt = f"""You are the AKASHA AI Strategy Engine. The user wants to run a "What-If" simulation with the following parameters:
{json.dumps(req.constraints, indent=2)}
{notif_str}
{historical_str}

Analyze the historical trends and the specific alert to generate 3 highly targeted strategy options based on these constraints. 
For example:
- Strategy 1: Strictly follow the user's requested parameters.
- Strategy 2: More aggressive (e.g., add more crews if weather is bad).
- Strategy 3: More conservative/cost-saving.

You MUST output strictly in valid JSON format matching this schema:
{{
  "strategies": [
    {{
      "id": "strategy_1",
      "title": "Strict Adherence",
      "description": "Applies exactly 2 crews under heavy monsoon conditions.",
      "modifiers": {{
         "weather_monsoon": "Heavy",
         "weather_wind": "Normal",
         "added_crews": 2
      }},
      "ai_confidence_pct": 87,
      "recommended": true,
      "radar_data": [80, 60, 90, 85, 87] 
    }}
  ]
}}
IMPORTANT: You do NOT provide cost or time impact. The deterministic Monte Carlo engine will calculate that based on your `modifiers` payload. Just provide the 3 strategies and their modifiers.
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        if provider == "azure":
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=2000, json_response=True)
        else:
            content = call_groq(messages, temperature=0.2, max_tokens=2000, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        
        try:
            llm_result = json.loads(content)
        except Exception:
            llm_result = {"strategies": []}
            
        # 3. DETERMINISTIC MATH: Feed LLM parameters into Monte Carlo engine
        final_strategies = []
        for strat in llm_result.get("strategies", []):
            mods = strat.get("modifiers", {})
            strat_sim = run_monte_carlo_simulation(db, p6_id, iterations=500, modifiers=mods, seed=42)
            
            if "error" not in strat_sim:
                strat_p50_date = datetime.strptime(strat_sim["completion_dates"]["p50"], "%Y-%m-%d")
                
                # Time Saved = Baseline P50 - Strat P50 (positive means finished earlier)
                time_saved_days = (baseline_p50_date - strat_p50_date).days
                
                # Cost Impact = deterministic calculation (e.g. 0.5 Cr per added crew)
                crews = int(mods.get("added_crews", 0))
                cost_cr = round(crews * 0.5, 2)
                
                # Risk Reduction = how much P90 - P10 spread was reduced
                baseline_spread = baseline_sim.get("spread_days", 1)
                strat_spread = strat_sim.get("spread_days", 1)
                risk_reduction_pct = round(((baseline_spread - strat_spread) / baseline_spread) * 100)
                
                strat["time_saved_days"] = time_saved_days
                strat["cost_impact_cr"] = cost_cr
                strat["risk_reduction_pct"] = risk_reduction_pct
                
            final_strategies.append(strat)
            
        return {"strategies": final_strategies}

    except Exception as e:
        logger.error(f"Strategy generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class SimulationExecuteRequest(BaseModel):
    project: dict
    strategy: dict
    notification_context: Optional[dict] = None

@router.post("/simulation-lab/simulate")
def generate_simulation(req: SimulationExecuteRequest, db: Session = Depends(get_db)):
    from engine.monte_carlo import run_monte_carlo_simulation
    project_name = req.project.get("project_name", "")
    p6_id = req.project.get("p6", {}).get("id") or req.project.get("project_id", "") or project_name
    
    # 1. Get Baseline Simulation
    baseline = run_monte_carlo_simulation(db, p6_id, iterations=1000, seed=42)
    
    # 2. Get Strategy Simulation
    mods = req.strategy.get("modifiers", {})
    simulated = run_monte_carlo_simulation(db, p6_id, iterations=1000, seed=42, modifiers=mods)
    
    timeline = []
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for i, m in enumerate(months):
        timeline.append({
            "month": m,
            "baseline": min(100, i * 8.5),
            "simulated": min(100, i * 9.5 + 5)
        })

    return {
        "baseline": baseline,
        "simulated": simulated,
        "timeline": timeline,
        "engine_version": "2.0"
    }

@router.post("/simulation-lab/execute")
def execute_strategy(req: SimulationExecuteRequest, db: Session = Depends(get_db)):
    provider = get_ai_provider()
    
    # Fetch Transmission (TC) Variance to include in context
    p6_id = req.project.get("p6", {}).get("id") or req.project.get("project_id", "") or req.project.get("project_name", "")
    from engine.variance import compute_tc_variance, _resolve_project_id
    resolved_id = _resolve_project_id(db, p6_id) or p6_id
    tc_variance = compute_tc_variance(db, resolved_id)
    
    prompt = f"""You are the AKASHA AI Execution Engine. Generate the automated task directives that will be pushed to integrated systems (SAP, PMAG, Contractor Portal) based on the chosen strategy.
    
Project Context:
{json.dumps(req.project, indent=2)}

Transmission (TC) Context:
{json.dumps(tc_variance, indent=2)}

Strategy Applied:
{json.dumps(req.strategy, indent=2)}

If the Transmission Context shows at-risk lines, make sure to generate at least one transmission-related task (e.g. expediting stringing, Contractor mobilization).

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
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=4000, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=4000, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        try:
            return json.loads(content)
        except Exception:
            return {"tasks": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/simulation-lab/report")
def generate_report(req: SimulationExecuteRequest, db: Session = Depends(get_db)):
    # Generate an executive report based on the executed strategy
    provider = get_ai_provider()
    
    # Fetch Transmission (TC) Variance to include in context
    p6_id = req.project.get("p6", {}).get("id") or req.project.get("project_id", "") or req.project.get("project_name", "")
    from engine.variance import compute_tc_variance, _resolve_project_id
    resolved_id = _resolve_project_id(db, p6_id) or p6_id
    tc_variance = compute_tc_variance(db, resolved_id)
    
    # Extract Human-Readable Project Name (not ID)
    project_name = req.project.get("raw_project_name") or req.project.get("project_name") or req.project.get("name") or "Unknown Project"

    # Include notification trigger in report if available
    notif_report_str = ""
    if req.notification_context:
        nc = req.notification_context
        notif_report_str = f"""\n\n## Original Trigger
This simulation was triggered by a notification alert:
- Change: {nc.get('change_type', 'Unknown')}
- Activity: {nc.get('activity_name', 'N/A')}
- Block: {nc.get('block', 'N/A')}
- Details: {nc.get('old_value', '')} → {nc.get('new_value', '')}
- Message: {nc.get('message', '')}

The report MUST reference this original trigger and explain how the chosen strategy addresses it."""

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
8. If the Transmission Context shows at-risk lines or delays, explicitly mention Transmission in the Root Cause Analysis and Key Findings.

CRITICAL INSTRUCTION: Keep all answers highly concise, short, and crisp. Use a maximum of 2 sentences per paragraph or point. Do not provide long explanations.
{notif_report_str}

## What You Must Do
Analyze the following project summary and the selected strategy:
Project Name: '{project_name}'
Project Context: {json.dumps(req.project, indent=2)}
Transmission Context: {json.dumps(tc_variance, indent=2)}
Strategy Applied: {json.dumps(req.strategy, indent=2)}

Provide:
1. Executive Summary (Must start with mentioning the Project Name)
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
            content = call_azure_openai_curl(messages, temperature=0.1, max_tokens=4000, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.1, max_tokens=4000, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        try:
            return json.loads(content)
        except Exception:
            return {"title": "Error", "executiveSummary": content, "keyFindings": [], "riskAssessment": "", "rootCauseAnalysis": "", "recommendedActions": [], "expectedOutcome": ""}
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
IMPORTANT: The supply chain quantities in the data are in absolute Units, NOT Megawatts (MW). Do not use "MW" or "Megawatts". Use "Units" instead.

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
            content = call_azure_openai_curl(messages, temperature=0.2, max_tokens=4000, json_response=True)
        else:
            content = call_ollama(messages, temperature=0.2, max_tokens=4000, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        try:
            return json.loads(content)
        except Exception:
            return {"executiveSummary": content, "keyFindings": [], "riskAssessment": "", "rootCauseAnalysis": "", "recommendedActions": [], "expectedOutcome": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




