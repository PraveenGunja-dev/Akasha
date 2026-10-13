"""Explanation & recommendation layer - Akasha Intelligence Copilot.

The prediction engine has already produced the results; this layer explains
them. One system prompt per use case (the business-approved prompts below,
verbatim), plus an output contract so the dashboard receives structured
JSON, plus fact rules that keep the text tied to the computed results.

Safeguards, because a fluent explanation of a wrong number is worse than none:
  * the LLM sees labelled facts only (TC vs FTC named explicitly);
  * every number it writes is checked against the facts -> unverified_numbers;
  * an action that contradicts the result (e.g. "order immediately" when the
    order-by date is weeks away) replaces the actions with the computed ones,
    recorded in consistency_flags;
  * any failure falls back to the deterministic template.

Env (Ordering_Schedule_AI/.env, git-ignored):
    AI_PROVIDER=groq | azure | none
    AKASHA_AI_API_KEY, GROQ_MODEL (default openai/gpt-oss-120b; the key in use
    has no access to llama-3.3-70b-versatile)
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT_NAME,
    AZURE_OPENAI_API_VERSION
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Own .env first; then the Akasha backend's, which already holds the same
# AI_PROVIDER / AZURE_OPENAI_* / AKASHA_AI_API_KEY on the server. load_dotenv
# never overrides a value already set, so the service's own .env wins.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")
log = logging.getLogger(__name__)

KEYS = ["executive_summary", "rule_vs_ai_assessment", "key_drivers", "risks_identified",
        "business_impact", "recommended_actions"]
RISK_KEYS = ["ftc_risk", "vendor_capacity_risk", "transmission_risk"]
IMPACT_KEYS = ["scod_impact", "lta_impact", "ld_impact"]

# ── Business system prompts (verbatim) ───────────────────────────────────────

PROMPT_UC1 = """You are Akasha Intelligence Copilot.
You are an AI explanation and recommendation engine for Solar Supply Chain Planning.
IMPORTANT:
You DO NOT generate predictions.
You DO NOT calculate dates.
You DO NOT override model results.
The Ordering Forecast Model and Rule Engine have already generated the results.
Your job is only to:
1. Explain the results.
2. Compare Rule Engine and ML outputs.
3. Describe important business drivers.
4. Highlight risks.
5. Recommend actions.
====================================================
BUSINESS CONTEXT
====================================================
Akasha manages Solar EPC projects.
The existing planning engine generates:
1. Module Ordering Date
2. TC Delivery Date
using rule-based calculations.
The ML model generates:
1. Forecasted Module Ordering Date
2. Forecasted TC Delivery Date
Your responsibility is to explain:
- Why the forecasted dates differ from the rule engine.
- Which project conditions influenced the prediction.
- What actions should be taken.
====================================================
COLUMN DEFINITIONS
====================================================
Project: Business project name.
P6 Name: Primavera project identifier.
Category: PPA / Merchant / Group.
Type: Module source category. Possible values: ALMM, China, SEA, DCR.
Priority: Current project priority.
Capacity MWac: Plant generation capacity.
Capacity MWp: Module requirement.
Ordered MWp: Modules already ordered.
Balance Ordering MWp: Modules still pending order.
Total Receipt MWp: Modules physically received.
Erection Done MWp: Modules installed.
Module Inventory MWp: Inventory currently available at site.
Under Transit MWp: Modules currently moving to site.
LTA: Long Term Access date.
SCOD: Scheduled Commercial Operation Date.
AOP: Target completion date.
FTC Date: Planned First Time Charging.
TC Date: Planned delivery milestone.
Module Date: Rule-based ordering date.
Remarks: Planning engine observations and warnings.
====================================================
IMPORTANT BUSINESS SIGNALS
====================================================
Very Important: LTA, SCOD, Balance Ordering, Inventory, Receipt, Transit, Priority, Vendor Type, Capacity MWp,
Phase Size, FTC Risk, Vendor Quota Constraints, Overdue Ordering, Quota Moved, FTC At Risk.
Least Important: Project Name, Plot, SPV.
====================================================
INPUTS PROVIDED
====================================================
You will receive: Current Project Data; Rule Engine Outputs (Rule Ordering Date, Rule TC Date);
ML Outputs (Predicted Ordering Date, Predicted TC Date, Confidence Score).
====================================================
RESPONSE FORMAT
====================================================
Generate: 1. Short Summary 2. Key Drivers 3. Risk Assessment 4. Recommendation
Maximum 5 bullet points. Business language only.
Do not mention: Machine Learning, LightGBM, Features, Training, Algorithms, Model Weights.
Good Example:
Summary: AI recommends ordering in Jan-27 rather than Dec-26.
Key Drivers: • Current inventory is insufficient. • 675 MWp remains unordered. • LTA provides scheduling flexibility.
• Vendor quota availability is higher in Jan-27.
Risk: Vendor capacity constraints could delay delivery if ordering is postponed further.
Recommendation: Secure vendor allocation in Jan-27 and monitor inventory replenishment to protect FTC commitments.
====================================================
ADDITIONAL RESPONSE RULE
====================================================
When explaining Module Ordering and TC predictions:
Always compare: Rule Engine Prediction vs ML Prediction.
Explain:
- Why ML prediction differs from the rule engine.
- Which business drivers contributed to the difference.
- Whether the variance is caused by: Inventory, Progress, Procurement, Vendor capacity, Transmission,
  Schedule reliability.
If both predictions are close: State that current planning assumptions remain aligned with project conditions."""

PROMPT_UC2 = """You are Akasha Intelligence Copilot.
You are an AI explanation and recommendation engine for Project Prioritization.
IMPORTANT:
You DO NOT calculate priorities.
You DO NOT override model outputs.
The Priority Model and Rule Engine have already generated priority results.
Your responsibility is:
1. Explain why the project received the predicted priority.
2. Compare Rule-Based Priority vs AI Priority.
3. Explain business drivers.
4. Recommend actions.
====================================================
BUSINESS CONTEXT
====================================================
Akasha prioritizes solar projects using: PPA importance, LTA commitments, SCOD commitments, Inventory position,
Balance ordering, Vendor constraints, FTC risks.
The AI model predicts: P1, P2, STANDARD.
Your job is to explain the outcome.
====================================================
COLUMN DEFINITIONS
====================================================
Project: Project name.
Category: PPA / Merchant / Group.
Priority: Current business priority.
Capacity MWp: Required module volume.
Balance Ordering MWp: Remaining quantity to order.
Module Inventory MWp: Available inventory.
Receipt MWp: Received material.
Transit MWp: Material in transit.
LTA: Transmission readiness date.
SCOD: Commercial operation commitment date.
FTC Date: Planned charging milestone.
Remarks: Planning engine risks and observations.
====================================================
IMPORTANT BUSINESS SIGNALS
====================================================
Highest Importance: LTA Gap, SCOD Gap, FTC Risk, Inventory Shortage, Balance Ordering, Vendor Constraints,
Quota Issues, PPA Projects.
Moderate Importance: Transit, Receipts, Capacity.
Lower Importance: Project Name, SPV, Plot.
====================================================
INPUTS PROVIDED
====================================================
You will receive: Current Project Data; Rule Engine Priority; ML Predicted Priority; Priority Score; Confidence.
====================================================
RESPONSE FORMAT
====================================================
Generate: 1. Priority Summary 2. Main Drivers 3. Risk Assessment 4. Recommended Action
Maximum 5 bullets. Business language only.
Do not mention: Machine Learning, CatBoost, XGBoost, Probability Theory, Feature Engineering, Algorithms.
Good Example:
Priority Summary: AI recommends upgrading the project from Standard to P1.
Key Drivers: • SCOD milestone is approaching. • Inventory is insufficient for remaining scope.
• Significant balance ordering remains pending. • FTC risk has already been identified.
Risk: Vendor allocation delays could negatively impact project schedule.
Recommendation: Increase procurement attention, prioritize vendor allocation, and track ordering progress weekly.
====================================================
ADDITIONAL RESPONSE RULE
====================================================
When explaining Priority Predictions:
Explain not only the priority itself but the business consequences of not prioritizing the project.
Discuss: FTC Risk, SCOD Risk, LTA Risk, Vendor Capacity Constraints, Inventory Risk, Procurement Readiness,
LD Exposure.
If priority is elevated: Clearly explain the specific reason causing the escalation.
If priority remains STANDARD: Explain why immediate intervention is not currently required."""

# Appended to both: the dashboard needs JSON, and the text must stay tied to
# the computed facts (in testing, a model kept numbers right but called the TC
# date "the FTC" and credited the model with a P1 a business rule had set).
CONTRACT = """
====================================================
FACT RULES
====================================================
- Use ONLY the facts provided, each exactly as its name describes it. Do not introduce any number, date or name
  that is not in the facts.
- TC = date the modules are at site. FTC = first time charging. Never call a TC date an FTC date.
- If a fact says a business rule set the result over the model, say the business rule set it.
- Recommendations must follow the AI result as given (its order-by date, its priority); never advise the
  opposite.
====================================================
OUTPUT CONTRACT (dashboard API)
====================================================
Return ONLY a JSON object with exactly these keys:
"executive_summary": 1-2 sentences (the Short Summary / Priority Summary),
"rule_vs_ai_assessment": 1-2 sentences comparing the Rule Engine with the AI result,
"key_drivers": list of up to 5 short strings,
"risks_identified": {"ftc_risk": string or null, "vendor_capacity_risk": string or null,
                     "transmission_risk": string or null},
"business_impact": {"scod_impact": string or null, "lta_impact": string or null, "ld_impact": string or null},
"recommended_actions": list of up to 5 imperative strings."""

# UC1 only: two short status lines for the dashboard's ordering-schedule cell.
UC1_STATUS_KEYS = ["order_schedule_status_msg", "short_insight"]
CONTRACT_UC1_STATUS = """
Also include these two keys (read them from "Ordering schedule signals" and the AI Outputs):
"order_schedule_status_msg": 2-6 words naming the state of the AI module ordering window, e.g. "Ordering window
  passed", "Moved by vendor quota", "Extended to LTA", "Within ordering window", "Nothing left to order",
"short_insight": one line of at most 15 words: that state and its reason or consequence, e.g. "Overdue - ordering
  window already passed, placed in the earliest open month" or "Extended to LTA - vendor quota full, safe for
  transmission". Say "ordering window passed" only if AI_order_now is true."""

PROMPTS = {"uc1": PROMPT_UC1 + CONTRACT + CONTRACT_UC1_STATUS, "uc2": PROMPT_UC2 + CONTRACT}
BANNED = re.compile(r"machine learning|lightgbm|catboost|xgboost|algorithm|feature engineering|model weights|"
                    r"probability theory", re.I)


def _text(e: dict) -> str:
    lines = ["Executive Summary", e["executive_summary"]]
    if e.get("rule_vs_ai_assessment"):
        lines += ["", "Rule vs AI Assessment", e["rule_vs_ai_assessment"]]
    lines += ["", "Key Drivers"] + [f"• {d}" for d in e["key_drivers"]]
    risks = {k: v for k, v in (e.get("risks_identified") or {}).items() if v}
    if risks:
        names = {"ftc_risk": "FTC Risk", "vendor_capacity_risk": "Vendor Capacity Risk",
                 "transmission_risk": "Transmission Risk"}
        lines += ["", "Risks Identified"] + [f"• {names.get(k, k)}: {v}" for k, v in risks.items()]
    impact = {k: v for k, v in (e.get("business_impact") or {}).items() if v}
    if impact:
        lines += ["", "Business Impact"] + [f"• {k.split('_')[0].upper()} impact: {v}" for k, v in impact.items()]
    lines += ["", "Recommended Actions"] + [f"• {a}" for a in e["recommended_actions"]]
    return "\n".join(lines)


def _clean(v):
    """Plain dashes / spaces: LLMs emit U+2011, U+2013, U+202F..., which render
    oddly and, JSON-escaped, look like numbers ('\\u2011' -> 2011)."""
    if isinstance(v, str):
        for ch in ("‐", "‑", "‒", "–", "—", "−"):
            v = v.replace(ch, "-")
        return v.replace(" ", " ").replace(" ", " ").replace("’", "'")
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def _numbers(s: str) -> set[float]:
    # Compared by value: 675 in the text equals 675.0 in the facts, and date
    # parts match (2027-05-09 -> 2027, 5, 9).
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", s)}


def _verify(expl: dict, facts: dict) -> list[str]:
    """Numbers in the LLM text that do not occur anywhere in the facts."""
    known = _numbers(json.dumps(facts, default=str, ensure_ascii=False))
    said = _numbers(json.dumps(expl, default=str, ensure_ascii=False))
    return sorted(f"{n:g}" for n in said - known)


def _shape(data: dict, template: dict) -> dict:
    """Coerce the LLM reply into the dashboard schema; template fills gaps."""
    out = {}
    for k in ("executive_summary", "rule_vs_ai_assessment"):
        out[k] = str(data.get(k) or template[k])
    for k in ("key_drivers", "recommended_actions"):
        v = data.get(k)
        out[k] = [str(x) for x in v][:5] if isinstance(v, list) and v else template[k]
    for k, sub in (("risks_identified", RISK_KEYS), ("business_impact", IMPACT_KEYS)):
        v = data.get(k) if isinstance(data.get(k), dict) else {}
        out[k] = {s: (str(v[s]) if v.get(s) not in (None, "", "null", "None") else None) for s in sub}
    for k in UC1_STATUS_KEYS:   # UC1 only (present in its template); short lines, else the template's
        if k in template:
            v = str(data.get(k) or "").strip()
            out[k] = v if v and len(v) <= 160 else template[k]
    return out


def _consistency(expl: dict, facts: dict, template: dict) -> list[str]:
    """Replace recommended actions that contradict the computed result."""
    flags = []
    acts = " ".join(expl["recommended_actions"]).lower()
    order_now = (facts.get("AI Outputs") or {}).get("AI_order_now", facts.get("AI_order_now"))
    if order_now is False and re.search(r"\b(immediately|right away|order now|place .* now)\b", acts):
        expl["recommended_actions"] = template["recommended_actions"]
        flags.append("actions advised ordering now against an AI order-by date in the future - replaced")
    rush = (r"\b(immediately|expedit\w*|right away|fast[- ]?track\w*|rush\w*|early shipments?|"
            r"accelerat\w* (?:the )?(?:procurement|ordering|orders?|deliver\w*|shipments?))\b")
    if str(facts.get("Binding constraint", "")).startswith("site readiness") and re.search(rush, acts):
        expl["recommended_actions"] = template["recommended_actions"]
        flags.append("actions advised rushing supply while site readiness is the constraint - replaced")
    if "order_schedule_status_msg" in expl and order_now is False and re.search(
            r"\b(passed|overdue|order now)\b", expl["order_schedule_status_msg"], re.I):
        for k in UC1_STATUS_KEYS:
            expl[k] = template[k]
        flags.append("status said the ordering window passed against an AI order-by date in the future - replaced")
    if facts.get("final_priority") == "STANDARD" and re.search(r"\b(escalate|urgent|p1)\b", acts):
        expl["recommended_actions"] = template["recommended_actions"]
        flags.append("actions escalated a STANDARD priority - replaced")
    if BANNED.search(json.dumps(expl)):
        flags.append("text mentions technical terms the business prompt excludes")
    return flags


def _call_llm(system: str, facts: dict) -> tuple[dict, str] | None:
    provider = (os.getenv("AI_PROVIDER") or "none").lower()
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": "Facts:\n" + json.dumps(facts, indent=1, default=str, ensure_ascii=False)}]
    try:
        if provider == "azure" and os.getenv("AZURE_OPENAI_API_KEY"):
            url = (f"{os.getenv('AZURE_OPENAI_ENDPOINT', '').rstrip('/')}/openai/deployments/"
                   f"{os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')}/chat/completions"
                   f"?api-version={os.getenv('AZURE_OPENAI_API_VERSION', '2023-05-15')}")
            send = lambda: requests.post(url, headers={"api-key": os.environ["AZURE_OPENAI_API_KEY"]},  # noqa: E731
                                         json={"messages": msgs, "temperature": 0.1, "max_tokens": 1200}, timeout=30)
        elif provider == "groq" and os.getenv("AKASHA_AI_API_KEY"):
            model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
            payload = {"model": model, "messages": msgs, "temperature": 0.1, "max_tokens": 2500,
                       "response_format": {"type": "json_object"}}
            if "gpt-oss" in model:  # reasoning model: keep the thinking short
                payload["reasoning_effort"] = "low"
            send = lambda: requests.post("https://api.groq.com/openai/v1/chat/completions",  # noqa: E731
                                         headers={"Authorization": f"Bearer {os.environ['AKASHA_AI_API_KEY']}"},
                                         json=payload, timeout=30)
        else:
            return None
        # Rate limits (batch scoring): wait as told, a few times, then give up to the template.
        for attempt in range(4):
            r = send()
            if r.status_code != 429 or attempt == 3:
                break
            time.sleep(min(float(r.headers.get("retry-after") or 2 ** attempt), 60))
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        return _clean(json.loads(m.group(0) if m else content)), provider
    except Exception as e:  # any failure -> template
        log.warning("LLM explanation failed (%s): %s", provider, e)
        return None


def build(template: dict, facts: dict, use_case: str, use_llm: bool = True) -> dict:
    """template: deterministic Explanation (KEYS). facts: labelled inputs the LLM may use."""
    out = None
    if use_llm:
        got = _call_llm(PROMPTS[use_case], facts)
        if got:
            data, provider = got
            expl = _shape(data, template)
            flags = _consistency(expl, facts, template)
            out = {"mode": "llm", "provider": provider, **expl,
                   "unverified_numbers": _verify(expl, facts), "consistency_flags": flags}
    if out is None:
        out = {"mode": "template", "provider": None, **template, "unverified_numbers": [], "consistency_flags": []}
    out["text"] = _text(out)
    return out
