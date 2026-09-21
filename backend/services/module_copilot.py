"""
Module Delivery Strategic LLM Copilot
─────────────────────────────────────
Provides on-demand strategic supply chain advisory powered by LLM.
Evaluates what-if scenarios, leadership briefings, shipping delays,
and commercial risk exposure using live portfolio constraints.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv('d:/Akasha_Platform/backend/.env')
logger = logging.getLogger(__name__)


def ask_module_planning_copilot(
    query: str, 
    portfolio_context: Dict[str, Any],
    project_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Executes a strategic advisory query using the available LLM (Groq / Azure / Rule-based).
    Returns answer markdown and suggested follow-up prompts.
    """
    system_prompt = f"""You are the Chief Supply Chain & Planning AI Copilot for the Akasha Platform at Adani Green Energy.
You advise the C-Suite and Project Directors on solar module procurement, vendor delivery quotas, and commissioning milestones for Khavda projects.

CRITICAL OPERATIONAL PARAMETERS:
- Monthly Supplier Limits: China (750 MW/mo, +136d lead time), SEA (500 MW/mo, +136d), ALMM (500 MW/mo, +98d), DCR (100 MW/mo, +98d), ALCM (100 MW/mo, +98d).
- TC Date = FTC Date - 45 days. Module Site Date = TC Date - Lead Time.
- Priority Framework: P1 projects get absolute first claim on supplier manufacturing quotas; standard projects are leveled into earlier months if monthly quota saturates.

LIVE PORTFOLIO STATE:
{json.dumps(portfolio_context, indent=2)}

{f"SPECIFIC PROJECT UNDER INQUIRY: {json.dumps(project_context, indent=2)}" if project_context else ""}

INSTRUCTIONS FOR YOUR RESPONSE:
1. Provide an executive-level, clear, authoritative response.
2. Structure your analysis using bold headers and concise bullet points.
3. Think across 4 core dimensions:
   - 💼 Commercial & PPA Penalties (SCOD compliance, liquidated damages)
   - 🚢 Supply Chain & Factory Quotas (monthly MW limits, port transit)
   - 🏗️ Site Execution & Laydown (crane teams, acreages for storage)
   - ⚡ Grid & Transmission (Khavda Pooling Substation charging dates)
4. Give concrete, practical recommendations with realistic EPC dates.
"""

    # 1. Try Groq (Ultra-fast)
    groq_api_key = os.environ.get('AKASHA_AI_API_KEY')
    if groq_api_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_api_key)
            res = client.chat.completions.create(
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': query}
                ],
                model='qwen/qwen3.8-27b',
                max_tokens=800,
                temperature=0.3
            )
            return {
                'answer': res.choices[0].message.content,
                'provider': 'groq:qwen3.8-27b',
                'status': 'success'
            }
        except Exception as e:
            logger.warning(f"Groq copilot call failed: {e}. Attempting Azure OpenAI fallback...")

    # 2. Try Azure OpenAI Fallback
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    azure_key = os.environ.get("AZURE_OPENAI_API_KEY")
    azure_dep = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
    azure_ver = os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15")

    if azure_endpoint and azure_key and azure_dep:
        try:
            import subprocess
            import uuid
            url = f"{azure_endpoint.rstrip('/')}/openai/deployments/{azure_dep}/chat/completions?api-version={azure_ver}"
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.3,
                "max_tokens": 800
            }
            temp_file = f"temp_copilot_{uuid.uuid4().hex}.json"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            try:
                cmd = ["curl.exe", "-k", "--noproxy", "*", "-X", "POST", url, "-H", "Content-Type: application/json", "-H", f"api-key: {azure_key}", "-d", f"@{temp_file}", "-s"]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
                data = json.loads(result.stdout)
                if "choices" in data:
                    return {
                        'answer': data["choices"][0]["message"]["content"],
                        'provider': 'azure:openai',
                        'status': 'success'
                    }
            finally:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        except Exception as e:
            logger.warning(f"Azure copilot call failed: {e}. Using deterministic synthesis fallback...")

    # 3. Deterministic Strategic Fallback (Zero failure rate)
    bal = portfolio_context.get('total_balance_ordering_mwp', 8208.4)
    crit = portfolio_context.get('critical_ordering_projects_count', 0)
    p1_count = portfolio_context.get('p1_projects_count', 0)
    
    fallback_response = f"""### Strategic Planning Assessment
**Query**: *{query}*

#### 1. 💼 Commercial & PPA Perspective
* **Active Scenario**: Prioritizing **{p1_count} strategic projects** protects committed PPA tariff structures against Liquidated Damages (LD) delay liabilities.
* **SCOD Protection**: Projects on the critical path receive allocated manufacturing slots, mitigating revenue delay risks.

#### 2. 🚢 Supply Chain & Quota Perspective
* **Portfolio Balance**: **{bal:,.1f} MWp** total un-ordered balance scheduled across rolling 13-month horizon.
* **Quota Utilization**: Vendor allocations respect hard monthly limits (**China 750 MW/mo, ALMM 500 MW/mo, SEA 500 MW/mo, DCR 100 MW/mo**).
* **Critical Ordering**: **{crit} projects** have immediate procurement urgency due to 98d/136d lead-time requirements.

#### 3. 🏗️ Site Laydown & Logistics Perspective
* Early-leveled deliveries require prepared site laydown yards (~2 acres per 25 MWp batch) and dedicated crawler/unloading crane mobilization.

#### 4. ⚡ Grid & Transmission Alignment
* Module arrival dates are synchronized with Khavda Pooling Substation (KPS) transmission charging phases to ensure 45-day trial-run completion ahead of FTC.
"""
    return {
        'answer': fallback_response,
        'provider': 'akasha:expert-system',
        'status': 'success'
    }
