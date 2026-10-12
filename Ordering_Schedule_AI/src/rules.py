"""The current Akasha planning engine's deterministic logic — the benchmark.

    TC date      = FTC - 45 days
    Module date  = TC - vendor lead time (China/SEA 136 d, ALMM/ALCM/DCR 98 d)
    Priority     = PPA first; LTA after the deadline means the modules can wait

The datasets, the training baselines and the API all call these functions, so
"rule engine" means one thing everywhere.
"""
from __future__ import annotations

from datetime import date, timedelta

from features import RULE_LEAD_DAYS, TC_BUFFER_DAYS

# A PPA phase that lands within this many days of SCOD (or past it) is P1.
P1_SLACK_DAYS = 60


def rule_tc(ftc: date) -> date:
    return ftc - timedelta(days=TC_BUFFER_DAYS)


def rule_order(ftc: date, vendor_type: str) -> date | None:
    lead = RULE_LEAD_DAYS.get(vendor_type)
    return None if lead is None else rule_tc(ftc) - timedelta(days=lead)


def priority_class(contract_type: str, slack_days: float | None, lta_after_deadline_days: float | None) -> str:
    """P1 / P2 / STANDARD.

    slack_days = deadline - FTC (negative: FTC after the deadline). The rule
    engine passes the P6 FTC; the training label passes the realistic FTC.
    Category order (business): PPA (penalty) > MERCHANT (open market) > GROUP
    (captive). LTA after the deadline: transmission binds, the phase can wait.
    """
    deferred = lta_after_deadline_days is not None and lta_after_deadline_days == lta_after_deadline_days \
        and lta_after_deadline_days > 0
    has_slack = slack_days is not None and slack_days == slack_days  # not NaN
    if contract_type == "PPA":
        return "P1" if (not deferred and has_slack and slack_days < P1_SLACK_DAYS) else "P2"
    if contract_type == "MERCHANT" and has_slack and slack_days < 0 and not deferred:
        return "P2"
    return "STANDARD"
