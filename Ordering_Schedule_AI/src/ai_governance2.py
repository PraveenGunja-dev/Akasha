"""AI governance pass over the Ordering Schedule export.

Sends each project to an LLM (Claude Sonnet via OpenRouter by default; Anthropic
direct, Azure OpenAI or Groq on request) with the Akasha governance
system prompt; the LLM may correct `ai_priority` and `ai_monthly_order_tc_forecast`
and returns a review status + reason. Nothing else on the project is touched.

Credentials come from Ordering_Schedule_AI/.env (git-ignored):
    OPENROUTER_API_KEY, OPENROUTER_MODEL (default anthropic/claude-sonnet-5.5)
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL (default claude-sonnet-5-5),
    ANTHROPIC_EFFORT (default medium; also used for OpenRouter)
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT_NAME,
    AZURE_OPENAI_API_VERSION
    AKASHA_AI_API_KEY, GROQ_MODEL (default openai/gpt-oss-120b)

Usage:
    python src/ai_governance2.py                     # all projects, Sonnet via OpenRouter
    python src/ai_governance2.py --limit 3           # smoke test
    python src/ai_governance2.py --provider anthropic   # or azure / groq
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend" / ".env")  # fallback: the backend's AI keys

INPUT_JSON = ROOT / "data" / "output" / "AIAkashaOrderingSchedule_final.json"
OUTPUT_JSON = ROOT / "data" / "output" / "AIAkashaOrderingSchedule_governed.json"
SYSTEM_PROMPT_FILE = ROOT / "src" / "akasha_system_prompt.txt"

MAX_TOKENS = 8000      # the LLM echoes two full nested objects back
# Groq counts prompt + max_tokens against a per-request cap (8k on gpt-oss-120b on-demand).
GROQ_REQUEST_TOKENS = int(os.getenv("GROQ_REQUEST_TOKENS", "8000"))
TIMEOUT_S = 120

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
# Thinking can't be turned off on Sonnet 5.5; effort sets how much it reasons per project.
ANTHROPIC_EFFORT = os.getenv("ANTHROPIC_EFFORT", "medium")
ANTHROPIC_MAX_TOKENS = 32000   # thinking + the two echoed objects; streamed, so no HTTP timeout
_anthropic_client: anthropic.Anthropic | None = None

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5")

SYSTEM_PROMPT = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")


# =========================================================
# LLM CLIENT
# =========================================================

def _parse_json(content: str) -> dict:
    m = re.search(r"\{.*\}", content, re.S)
    return json.loads(m.group(0) if m else content)


def call_anthropic(system: str, user: str) -> dict:
    global _anthropic_client
    if _anthropic_client is None:
        # Reads ANTHROPIC_API_KEY; the SDK retries 429/5xx/connection errors itself.
        _anthropic_client = anthropic.Anthropic(max_retries=4)

    with _anthropic_client.beta.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=ANTHROPIC_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": ANTHROPIC_EFFORT},
        # If a safety classifier declines, the API re-runs the request on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        raise RuntimeError(f"model declined the request ({getattr(msg.stop_details, 'category', None)})")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError(f"reply cut off at max_tokens={ANTHROPIC_MAX_TOKENS}")

    text = "".join(b.text for b in msg.content if b.type == "text")
    return _parse_json(text)


def call_llm(provider: str, system: str, user: str) -> dict:
    if provider == "anthropic":
        return call_anthropic(system, user)

    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    if provider == "azure":
        url = (f"{os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/')}/openai/deployments/"
               f"{os.environ['AZURE_OPENAI_DEPLOYMENT_NAME']}/chat/completions"
               f"?api-version={os.getenv('AZURE_OPENAI_API_VERSION', '2023-05-15')}")
        headers = {"api-key": os.environ["AZURE_OPENAI_API_KEY"]}
        # api-version 2023-05-15 has no response_format; the JSON is extracted below.
        payload = {"messages": msgs, "temperature": 0, "max_tokens": MAX_TOKENS}
    elif provider == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                   "X-Title": "Akasha AI Governance"}
        # Sonnet 5.5 rejects temperature; reasoning_effort sets how much it thinks per project.
        payload = {"model": OPENROUTER_MODEL, "messages": msgs,
                   "max_tokens": ANTHROPIC_MAX_TOKENS,
                   "reasoning_effort": ANTHROPIC_EFFORT,
                   "response_format": {"type": "json_object"}}
    elif provider == "groq":
        model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {os.environ['AKASHA_AI_API_KEY']}"}
        est_input = (len(system) + len(user)) // 3          # conservative chars->tokens
        budget = min(MAX_TOKENS, GROQ_REQUEST_TOKENS - est_input - 200)
        if budget < 1500:
            raise ValueError(f"prompt ~{est_input} tokens leaves no room for the reply under Groq's "
                             f"{GROQ_REQUEST_TOKENS}-token request cap; run with --provider azure")
        payload = {"model": model, "messages": msgs, "temperature": 0,
                   "max_tokens": budget, "response_format": {"type": "json_object"}}
        if "gpt-oss" in model:
            payload["reasoning_effort"] = "low"
    else:
        raise ValueError(f"Unknown provider '{provider}' (use openrouter, anthropic, azure or groq)")

    # Rate limits / transient upstream errors: wait, a few times, then fail this project.
    timeout = 600 if provider == "openrouter" else TIMEOUT_S   # thinking replies take minutes
    for attempt in range(4):
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code not in (429, 502, 503) or attempt == 3:
            break
        time.sleep(min(float(r.headers.get("retry-after") or 2 ** attempt), 60))
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")

    body = r.json()
    if "error" in body:   # OpenRouter can return 200 with an upstream error
        raise RuntimeError(f"provider error: {body['error']}")
    choice = body["choices"][0]
    if choice.get("finish_reason") in ("length", "max_tokens"):
        raise RuntimeError(f"reply cut off at max_tokens={payload.get('max_tokens')}")
    return _parse_json(choice["message"]["content"])


# =========================================================
# BUILD PROJECT CONTEXT
# =========================================================

def _j(obj) -> str:
    """Compact JSON - indentation alone adds ~30% tokens to the prompt."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def build_project_prompt(project: dict) -> str:

    return f"""
PROJECT REVIEW REQUEST

====================================================
PROJECT INFORMATION
====================================================

Project:
{project.get('project_name')}

P6 Name:
{project.get('p6_name')}

Category:
{project.get('category')}

Vendor Type:
{project.get('type')}

MMS Type:
{project.get('mms_type')}

EPC:
{project.get('epc')}

Priority:
{project.get('priority')}

Status:
{project.get('status')}

Capacity MWac:
{project.get('capacity_mwac')}

Capacity MWp:
{project.get('capacity_mwp')}

Ordered MWp:
{project.get('ordered_mwp')}

Balance Ordering MWp:
{project.get('balance_ordering_mwp')}

Receipt MWp:
{project.get('total_receipt_mwp')}

Inventory MWp:
{project.get('module_inventory_mwp')}

Inventory Negative:
{project.get('module_inventory_negative')}

Transit MWp:
{project.get('under_transit_mwp')}

Erection Done MWp:
{project.get('erection_done_mwp')}

Completed FTC MWp:
{project.get('completed_ftc_mwp')}

Commissioned:
{project.get('is_commissioned')}

====================================================
SCHEDULE INFORMATION
====================================================

LTA:
{project.get('lta')}

LTA Risk:
{_j(project.get('lta_risk'))}

SCOD:
{project.get('scod')}

SCOD LTA Difference Days:
{project.get('scod_lta_diff_days')}

AOP:
{project.get('aop_plan')}

FTC:
{project.get('ftc_date')}

TC:
{project.get('tc_date')}

Module Date:
{project.get('module_date')}

====================================================
PLANNING
====================================================

Planning Flags:
{_j(project.get('planning_flags', []))}

Remarks:
{project.get('remarks')}

Perspectives:
{_j(project.get('perspectives', {}))}

Month Allocation:
{_j(project.get('month_mwp', {}))}

Overdue Allocation:
{_j(project.get('month_overdue_mwp', {}))}

Phase Allocation:
{_j(project.get('month_phases', {}))}

====================================================
FTC RISK SECTION
====================================================

FTC At Risk MWp:
{project.get('ftc_at_risk_mwp', 0)}

FTC Max Short Days:
{project.get('ftc_max_short_days', 0)}

FTC Past LTA MWp:
{project.get('ftc_past_lta_mwp', 0)}

====================================================
CURRENT ML OUTPUTS
====================================================

Current AI Priority Object:

{_j(project.get("ai_priority", {}))}

Current AI Monthly Order Forecast Object:

{_j(project.get("ai_monthly_order_tc_forecast", {}))}

====================================================
CLIENT REVIEW RULES
====================================================

1. Inventory + Transit + Open Orders should be consumed first.

2. Fully ordered projects with adequate inventory generally
should not be urgent.

3. PPA > LTA Risk > P1 > P2 > Standard > Earliest FTC

4. FTC risk should strongly affect priority.

5. capacity_delayed, ftc_unreachable, ftc_past_lta
indicate elevated priority.

6. TC date is generally FTC - 45 days.

7. Module Order Date is generally
TC Date - Lead Time.

Lead Times:

China = 136 days

SEA = 136 days

ALMM = 98 days

ALCM = 98 days

DCR = 98 days

8. Monthly quota:

China = 750 MWac

SEA = 500 MWac

ALMM = 500 MWac

ALCM = 100 MWac

DCR = 100 MWac

9. If quota is full:

Move earlier up to 2 months.

Only then move later.

10. If FTC exceeds LTA because of quota limits:

Capacity Delayed.

11. If project is fully ordered, inventory exists,
and there are no planning flags,
do not artificially increase priority.

====================================================
TASK
====================================================

Review the current AI outputs:

1. ai_priority
2. ai_monthly_order_tc_forecast

Correct them if required. Return each object in full, keeping
its existing structure and keys; change only the values you correct.
If an object has status "not_scored", return it unchanged.

Return ONLY JSON:

{{
  "ai_priority": {{...}},
  "ai_monthly_order_tc_forecast": {{...}},
  "ai_review_status": "VALIDATED or CORRECTED",
  "ai_review_reason": "One or two sentences: what was checked, and what was changed and why."
}}

No markdown.
No explanation outside JSON.
"""


# =========================================================
# PROCESS PROJECTS
# =========================================================

def diff_paths(before, after, path: str) -> list[dict]:
    """Leaf-level differences between the original and the reviewed object."""
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for k in sorted(set(before) | set(after), key=str):
            out += diff_paths(before.get(k), after.get(k), f"{path}.{k}")
        return out
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        out = []
        for i, (b, a) in enumerate(zip(before, after)):
            out += diff_paths(b, a, f"{path}[{i}]")
        return out
    return [] if before == after else [{"field": path, "before": before, "after": after}]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="openrouter",
                    choices=["openrouter", "anthropic", "azure", "groq"])
    ap.add_argument("--input", type=Path, default=INPUT_JSON)
    ap.add_argument("--output", type=Path, default=OUTPUT_JSON)
    ap.add_argument("--limit", type=int, default=None, help="review only the first N projects (testing)")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between calls")
    args = ap.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    projects = data["ordering_schedule"]["projects"]
    todo = projects[: args.limit] if args.limit else projects

    model = {"anthropic": ANTHROPIC_MODEL, "openrouter": OPENROUTER_MODEL}.get(args.provider, "")
    print(f"\nProvider        : {args.provider} {model}")
    print(f"Projects Loaded : {len(projects)} (reviewing {len(todo)})\n")

    for idx, project in enumerate(todo):

        print(f"[{idx + 1}/{len(todo)}] {project.get('project_name')}")

        try:
            result = call_llm(args.provider, SYSTEM_PROMPT, build_project_prompt(project))

            changes = []
            for key in ("ai_priority", "ai_monthly_order_tc_forecast"):
                if isinstance(result.get(key), dict):
                    changes += diff_paths(project.get(key), result[key], key)
                    project[key] = result[key]

            # The model's own status is not trusted: it can change a value and still say VALIDATED.
            status = "CORRECTED" if changes else "VALIDATED"
            reason = (result.get("ai_review_reason") or "").strip()
            if status != result.get("ai_review_status"):
                note = f"Model reported {result.get('ai_review_status') or 'no status'}; status set from the field diff."
                reason = f"{reason} {note}".strip()

            project["ai_review_status"] = status
            project["ai_review_reason"] = reason or "Model gave no reason."
            project["ai_review_changes"] = changes  # audit trail: every value the model changed

        except Exception as ex:
            print(f"  ERROR : {ex}")
            project["ai_review_status"] = "ERROR"
            project["ai_review_reason"] = f"Validation failed - manual review required: {ex}"

        time.sleep(args.sleep)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nSaved Final JSON : {args.output}")


if __name__ == "__main__":
    main()
