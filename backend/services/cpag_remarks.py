"""
Variance remarks for the CPAG Physical Progress table.

Each row's remark is written from P6 facts only: the row's plan-to-date,
actual and variance, and the activities furthest behind their baseline
Labor units (routers.bess._variance_drivers).  Azure OpenAI turns those
facts into one short sentence per row; every number in its answer must
appear in the facts handed to it, or that row falls back to a plain
sentence built from the same facts.  P6 holds no reason for a delay, so
the remark says where the gap is, never why - a cause or mitigation is the
reviewer's to add (a manual remark always wins on the slide).
"""
import hashlib
import json
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Generated remarks by facts hash: the pack is rebuilt on every sync, the
# facts mostly are not.
_CACHE: Dict[str, Dict[str, Any]] = {}

ON_PLAN_PTS = 0.5     # |plan - actual| within this reads "on plan"
AI_TIMEOUT_S = 45


def _d(iso: Optional[str]) -> Optional[str]:
    return date.fromisoformat(iso).strftime("%d-%b-%y") if iso else None


def _n(v: Optional[float]) -> str:
    return f"{v:.1f}" if v is not None else "-"


def _facts(pss: str, buckets: List[Dict[str, Any]], plan: float, actual: float,
           data_date: Optional[str]) -> Dict[str, Any]:
    """The remark inputs, numbers pre-rounded to the one decimal the remark
    may quote and dates pre-formatted, so the answer can be checked."""
    rows = []
    for b in buckets:
        p, a = b.get("planToDatePct"), b.get("earnedPct")
        drv = b.get("drivers") or {}
        rows.append({
            "row": b["label"],
            "weightPct": _n(b.get("weightPct")),
            "planToDatePct": _n(p), "actualPct": _n(a),
            "variancePts": _n(None if p is None or a is None else p - a),
            "scheduledAfterDataDatePts": _n(drv.get("afterDataDatePts")),
            "varianceAtDataDatePts": _n(None if p is None or a is None
                                        else p - a - (drv.get("afterDataDatePts") or 0)),
            "activitiesBehindAtDataDate": drv.get("behindCount", 0),
            "mostBehind": [{
                "activity": t["activity"],
                "wbs": t.get("wbs"),
                "status": t["status"],
                "baselineFinish": _d(t["baselineFinish"]),
                "plannedToDatePct": _n(t["plannedToDatePct"]),
                "actualPct": _n(t["actualPct"]),
                "gapPts": _n(t["gapPts"]),
            } for t in drv.get("top", [])],
        })
    return {"project": pss, "dataDate": _d(data_date), "rows": rows,
            "total": {"planToDatePct": _n(plan), "actualPct": _n(actual),
                      "variancePts": _n(plan - actual)}}


def _fallback_row(r: Dict[str, Any], data_date: Optional[str]) -> str:
    """One short sentence from the facts: the delay left at the data date,
    the part of the gap that is only planned later, and the activity most
    behind."""
    try:
        var, at_dd = float(r["variancePts"]), float(r["varianceAtDataDatePts"])
    except ValueError:
        return ""
    if abs(var) <= ON_PLAN_PTS:
        return "On plan."
    if var < 0:
        return f"Ahead of plan by {_n(-var)} pts."
    if at_dd <= ON_PLAN_PTS:
        return (f"Gap is work planned after the {data_date} data date; "
                f"on plan at the data date.")
    text = f"Behind by {r['varianceAtDataDatePts']} pts at the {data_date} data date"
    if r["scheduledAfterDataDatePts"] not in ("-", "0.0"):
        text += f" (+{r['scheduledAfterDataDatePts']} pts planned later this month)"
    lead = r["mostBehind"][:1]
    if lead:
        t = lead[0]
        text += (f". Most behind: {t['activity']}" + (f" - {t['wbs']}" if t["wbs"] else "")
                 + f", {t['actualPct']}% vs {t['plannedToDatePct']}% planned"
                 + (f", BL finish {t['baselineFinish']}" if t["baselineFinish"] else ""))
    return text + "."


def _fallback_total(f: Dict[str, Any]) -> str:
    t = f["total"]
    if float(t["variancePts"]) <= ON_PLAN_PTS:
        return "Overall on or ahead of plan."
    later = sum(float(r["scheduledAfterDataDatePts"]) for r in f["rows"]
                if r["scheduledAfterDataDatePts"] != "-")
    behind = [r for r in f["rows"] if r["varianceAtDataDatePts"] != "-"
              and float(r["varianceAtDataDatePts"]) > ON_PLAN_PTS]
    text = (f"{t['variancePts']} pts behind, of which {_n(later)} pts is planned after "
            f"the {f['dataDate']} data date")
    if behind:
        worst = max(behind, key=lambda r: float(r["varianceAtDataDatePts"]))
        text += f"; largest real gap in {worst['row']} ({worst['varianceAtDataDatePts']} pts)"
    return text + "."


_NUM = re.compile(r"\d+(?:\.\d+)?")


MAX_WORDS = 35


def _grounded(text: str, scope: Any) -> bool:
    """Every number the remark quotes must be in `scope` - the facts of the
    row it describes, not just anywhere in the payload, so a figure from
    another row cannot be attached to this one (dates are pre-formatted, so
    their day/year digits are in there too) - and it must be short."""
    have = set(_NUM.findall(json.dumps(scope, ensure_ascii=False)))
    return (len(text.split()) <= MAX_WORDS
            and all(n in have for n in _NUM.findall(text)))


SYSTEM = """You write the "Variance Remark" column of a construction progress \
review table for a BESS project. You get JSON facts from the Primavera P6 \
schedule: each row's plan-to-date % (to the end of the data date's month), \
actual % (to the P6 data date), variance in points (plan minus actual, \
positive = behind), how many of those points are work planned after the data \
date (scheduledAfterDataDatePts - not yet due, so not late), the variance \
left at the data date (varianceAtDataDatePts - the real delay), and the \
activities furthest behind plan at the data date, with their WBS.

Rules:
- One remark per row, in the same order, plus one for the Total row.
- At most 25 words each. Plain, factual, management tone. No bullet points.
- Use ONLY the facts given. Copy numbers and dates exactly as written in the \
facts; do not compute new numbers, round differently or add units other than % and pts.
- When a row is behind, name the 1-2 activities driving the gap with their \
WBS and baseline finish, and say how much of the gap is only planned after \
the data date when that is material.
- Never state or guess a cause, reason, constraint or mitigation - the \
schedule does not record why work is late.
- A row within 0.5 pts reads as on plan; a negative variance is ahead of plan.
- Judge delay on varianceAtDataDatePts. If it is 0.5 or less, say the gap is \
work planned after the data date, not a delay.

Reply as JSON: {"rows": ["...", ...], "total": "..."}"""


def _ai(facts: Dict[str, Any], facts_json: str) -> Optional[Dict[str, Any]]:
    """The app's configured LLM (AI_PROVIDER: azure, else Ollama), as every
    other AI route uses."""
    from routers.ai import call_azure_openai_curl, call_ollama, get_ai_provider
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": facts_json}]
    if get_ai_provider() == "azure":
        raw = call_azure_openai_curl(messages, temperature=0, max_tokens=900,
                                     json_response=True, timeout=AI_TIMEOUT_S)
    else:
        raw = call_ollama(messages, temperature=0, max_tokens=900, json_response=True)
    out = json.loads(raw)
    rows = out.get("rows")
    if not isinstance(rows, list) or len(rows) != len(facts["rows"]):
        raise ValueError(f"expected {len(facts['rows'])} rows, got {rows!r:.200}")
    return {"rows": [str(r).strip() for r in rows], "total": str(out.get("total") or "").strip()}


def scurve_remarks(pss: str, buckets: List[Dict[str, Any]], plan: float,
                   actual: float, data_date: Optional[str]) -> Dict[str, Any]:
    """{"rows": [remark per bucket], "total": remark, "source": "ai"|"data"}"""
    facts = _facts(pss, buckets, plan, actual, data_date)
    facts_json = json.dumps(facts, ensure_ascii=False)
    key = hashlib.sha1(facts_json.encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]

    rows = [_fallback_row(r, facts["dataDate"]) for r in facts["rows"]]
    total = _fallback_total(facts)
    source = "data"
    try:
        ai = _ai(facts, facts_json)
        kept = 0
        for i, txt in enumerate(ai["rows"]):
            if txt and _grounded(txt, [facts["rows"][i], facts["dataDate"]]):
                rows[i], kept = txt, kept + 1
            else:
                logger.warning("CPAG remark for %s row %d not grounded, using data text: %s",
                               pss, i, txt)
        if ai["total"] and _grounded(ai["total"], facts):
            total, kept = ai["total"], kept + 1
        source = "ai" if kept else "data"
    except Exception as e:   # no AI configured, timeout, bad JSON
        logger.warning("CPAG remarks AI unavailable for %s, using data text: %s", pss, e)

    result = {"rows": rows, "total": total, "source": source}
    if source == "ai":   # a failed call is retried on the next build
        _CACHE[key] = result
    return result
