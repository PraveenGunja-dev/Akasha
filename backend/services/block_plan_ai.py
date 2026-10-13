"""Plain-language explanations of the block-level ordering plan.

The plan's numbers come from services/block_ordering.py; this module only
turns a compact set of those figures into short sentences a non-technical
reader can follow. The model is told to use no number that is not in the
facts it is given, and when no model is reachable the same facts are written
out by a fixed template - the page never shows an invented figure.

Provider order matches the module copilot: Groq (AKASHA_AI_API_KEY), then
Azure OpenAI, then the template.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

STYLE = """You explain a module ordering plan for a solar company to managers who are not technical.
Rules:
- Use ONLY the numbers in FACTS. Never estimate, round differently or add a figure that is not there.
- Plain words, short sentences, no jargon. Say "MWp" for module quantity. Explain any term you must use.
- No headings, no markdown tables. Use at most 5 short bullet points starting with "- ".
- Be direct about problems and say what needs to be done and by whom (planning team, procurement, master data).
- Mention a month only if it appears in FACTS.
- Never group suppliers into one date range: state each supplier's full months exactly as listed for it.
Meaning of the terms (use them exactly this way):
- SCOD: the contract date by which the plant must be running (scheduled commercial operation date).
- LTA: the date the grid connection is available to export power.
- Block: one section of a solar plant (about 17 MWp) with its own installation dates.
- MMS: the steel structure the modules are fixed on; modules can only go on once it is up.
- Lead time: days a supplier needs from order to delivery.
- Supplier origin: where modules come from - China, SEA (South-East Asia), ALMM (approved Indian makers),
  DCR (Indian cells and modules), ALCM; "Unknown" means the master does not say.
- Order now: modules needed sooner than the supplier can deliver if ordered later.
"""


def _llm(prompt: str, max_tokens: int = 450) -> Tuple[Optional[str], Optional[str]]:
    """(text, provider) from the first model that answers, else (None, None)."""
    key = os.environ.get("AKASHA_AI_API_KEY")
    if key:
        try:
            from groq import Groq
            res = Groq(api_key=key).chat.completions.create(
                messages=[{"role": "system", "content": STYLE}, {"role": "user", "content": prompt}],
                model=os.environ.get("AKASHA_AI_MODEL", "qwen/qwen3.8-27b"),
                max_tokens=max_tokens, temperature=0.2)
            return res.choices[0].message.content.strip(), "groq"
        except Exception as e:                     # noqa: BLE001 - fall through to the next provider
            logger.warning(f"Block plan AI (Groq) failed: {e}")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    akey = os.environ.get("AZURE_OPENAI_API_KEY")
    dep = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
    if endpoint and akey and dep:
        try:
            ver = os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15")
            r = requests.post(
                f"{endpoint.rstrip('/')}/openai/deployments/{dep}/chat/completions?api-version={ver}",
                headers={"api-key": akey, "Content-Type": "application/json"},
                json={"messages": [{"role": "system", "content": STYLE}, {"role": "user", "content": prompt}],
                      "temperature": 0.2, "max_tokens": max_tokens},
                timeout=60, verify=False, proxies={"http": None, "https": None})
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"].strip(), "azure"
        except Exception as e:                     # noqa: BLE001
            logger.warning(f"Block plan AI (Azure) failed: {e}")
    return None, None


def _fmt(v: Any) -> str:
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def portfolio_facts(plan: Dict[str, Any]) -> Dict[str, Any]:
    """The handful of figures the summary may use, taken from the plan."""
    blk = [p for p in plan.get("projects", []) if p.get("method") == "block"]
    quota = plan.get("quota_by_origin", {})
    full = {o: [m for m, v in q["used_mwac_by_month"].items() if v >= q["cap_mwac"] - 0.5] for o, q in quota.items()}
    delayed = sorted((p for p in blk if (p.get("quota_delayed_mwp") or 0) > 0.5), key=lambda p: -p["quota_delayed_mwp"])
    return {
        "projects_planned": len(blk),
        "projects_without_block_data": sum(1 for p in plan.get("projects", []) if p.get("method") == "none"),
        "blocks_total": sum(p["blocks_total"] for p in blk), "blocks_open": sum(p["blocks_open"] for p in blk),
        "mwp_to_order": round(sum(p.get("new_order_mwp") or 0 for p in blk)),
        "mwp_needed_inside_lead_time_order_now": round(sum(p.get("late_need_mwp") or 0 for p in blk)),
        "mwp_delayed_by_supplier_monthly_limit": round(sum(p.get("quota_delayed_mwp") or 0 for p in blk)),
        "projects_delayed_by_supplier_limit": len(delayed),
        "largest_delays": [{"project": p["project_name"], "mwp": round(p["quota_delayed_mwp"]),
                            "months_late": p.get("max_quota_delay_months")} for p in delayed[:4]],
        "supplier_limits_mwac_per_month": {o: q["cap_mwac"] for o, q in quota.items()},
        "supplier_months_full": {o: ms for o, ms in full.items() if ms},
        "blocks_finishing_after_scod": sum(p.get("blocks_after_scod") or 0 for p in blk),
        "projects_with_unknown_supplier_origin": [p["project_name"] for p in blk if not p.get("origin_known")],
        "projects_where_p6_and_sap_quantities_disagree": [p["project_name"] for p in blk if not p["verify"]["agree"]],
        "projects_with_priority_set": sum(1 for p in blk if (p.get("priority") or "standard") != "standard"),
    }


def _portfolio_template(f: Dict[str, Any]) -> str:
    lines = [
        f"- {_fmt(f['mwp_to_order'])} MWp of modules still need to be ordered across {f['projects_planned']} projects "
        f"({f['blocks_open']} of {f['blocks_total']} blocks are still to be installed).",
        f"- {_fmt(f['mwp_needed_inside_lead_time_order_now'])} MWp is needed sooner than suppliers can deliver, "
        f"so it should be ordered now.",
    ]
    if f["mwp_delayed_by_supplier_monthly_limit"]:
        top = ", ".join(f"{d['project']} ({_fmt(d['mwp'])} MWp)" for d in f["largest_delays"][:3])
        lines.append(f"- Suppliers' monthly limits push {_fmt(f['mwp_delayed_by_supplier_monthly_limit'])} MWp "
                     f"on {f['projects_delayed_by_supplier_limit']} projects past the date it is needed; largest: {top}.")
    if f["projects_with_unknown_supplier_origin"]:
        lines.append(f"- {len(f['projects_with_unknown_supplier_origin'])} projects have no supplier origin in the master, "
                     f"so their limit is assumed; the master data team should fill it in.")
    if f["projects_with_priority_set"] == 0:
        lines.append("- No project is marked P1 or P2 yet, so scarce supply is shared by need date only.")
    return "\n".join(lines)


def explain_portfolio(plan: Dict[str, Any]) -> Dict[str, Any]:
    facts = portfolio_facts(plan)
    text, provider = _llm("Summarise this ordering plan for management in plain language.\n\nFACTS:\n"
                          + json.dumps(facts, indent=1, default=str))
    return {"text": text or _portfolio_template(facts), "ai": bool(text), "provider": provider or "template",
            "facts": facts}


def project_facts(p: Dict[str, Any]) -> Dict[str, Any]:
    blocks = [b for b in p.get("blocks", []) if (b.get("remaining_mwp") or 0) > 0]
    held = [b["block"] for b in blocks if any(str(f).startswith("held by MMS") for f in b.get("flags", []))]
    return {
        "project": p.get("project_name"), "supplier_origin": p.get("type"), "priority": p.get("priority"),
        "supplier_lead_time_days": p.get("lead_days"), "blocks_open": p.get("blocks_open"),
        "blocks_total": p.get("blocks_total"), "block_mwp": p.get("block_mwp"),
        "installed_mwp": p.get("installed_mwp"), "already_ordered_or_on_the_way_mwp": p.get("pipeline_mwp"),
        "mwp_to_order": p.get("new_order_mwp"), "order_now_mwp": p.get("late_need_mwp"),
        "orders_by_month_mwp": p.get("orders_by_month"),
        "delayed_by_supplier_limit_mwp": p.get("quota_delayed_mwp"),
        "months_late_by_supplier_limit": p.get("max_quota_delay_months"),
        "install_pace_mwp_per_day": p.get("pace_mwp_per_day"), "pace_source": p.get("pace_basis"),
        "blocks_waiting_for_structure_mms": held[:12], "count_blocks_waiting_for_structure": len(held),
        "blocks_finishing_after_scod": p.get("blocks_after_scod"), "scod": p.get("scod"),
        "blocks_finishing_after_lta": p.get("blocks_after_lta"), "lta": p.get("lta"),
        "p6_and_sap_quantities_agree": (p.get("verify") or {}).get("agree"),
        "check_to_order_from_p6": (p.get("verify") or {}).get("to_order_by_blocks_mwp"),
        "check_to_order_from_sap": (p.get("verify") or {}).get("to_order_by_sap_mwp"),
    }


def explain_project(p: Dict[str, Any]) -> Dict[str, Any]:
    f = project_facts(p)
    text, provider = _llm("Explain this one project's module ordering plan to a project manager.\n\nFACTS:\n"
                          + json.dumps(f, indent=1, default=str), max_tokens=380)
    if not text:
        months = ", ".join(f"{m}: {_fmt(v)} MWp" for m, v in (f["orders_by_month_mwp"] or {}).items()) or "none"
        text = "\n".join(x for x in [
            f"- {f['blocks_open']} of {f['blocks_total']} blocks still need modules; {_fmt(f['mwp_to_order'])} MWp remains to be ordered.",
            f"- Order plan: {months}.",
            f"- {_fmt(f['order_now_mwp'])} MWp is needed sooner than the {f['supplier_lead_time_days']}-day supplier lead time allows - order now." if f["order_now_mwp"] else "",
            f"- The supplier's monthly limit delays {_fmt(f['delayed_by_supplier_limit_mwp'])} MWp by up to {f['months_late_by_supplier_limit']} month(s)." if f["delayed_by_supplier_limit_mwp"] else "",
            f"- {f['count_blocks_waiting_for_structure']} blocks are waiting for their structure (MMS) before modules can go on." if f["count_blocks_waiting_for_structure"] else "",
            "- P6 and SAP quantities do not agree here - check the records." if f["p6_and_sap_quantities_agree"] is False else "",
        ] if x)
    return {"text": text, "ai": provider is not None, "provider": provider or "template", "facts": f}
