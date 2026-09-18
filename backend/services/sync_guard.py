"""Guards a full-snapshot table replace against an extract that has silently
lost scope — see the 16 Sep 2026 ZPSPS007 dropping the entire BESS cluster
(307 POs, Rs 11,850 Cr) with nothing catching it before the numbers went live.

Why not incremental upsert instead: SAP/SLR extracts are a full daily
snapshot with no per-row change signal (no last-modified flag, no delete
tombstone). "Only add what's new, leave the rest" cannot tell "still valid,
unchanged" from "SAP genuinely cancelled this PO" — it would let stale data
accumulate forever, which is worse than what we have. What IS checkable is
whether today's snapshot is a plausible successor to yesterday's, before it
is trusted enough to replace it.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class GuardResult:
    ok: bool
    label: str
    old_count: int
    new_count: int
    old_value_cr: float
    new_value_cr: float
    reason: Optional[str] = None


def check_snapshot(label: str, old_count: int, new_count: int,
                    old_value_cr: float, new_value_cr: float,
                    max_drop_pct: float = 15.0) -> GuardResult:
    """Refuse a replace where count or value has collapsed by more than
    max_drop_pct against what is currently live. Growth, or a normal day's
    churn (POs closing out), passes; only an implausible drop is blocked.
    An empty current table never blocks a first load."""
    if old_count == 0:
        return GuardResult(True, label, old_count, new_count, old_value_cr, new_value_cr)

    count_drop = (old_count - new_count) / old_count * 100
    value_drop = (old_value_cr - new_value_cr) / old_value_cr * 100 if old_value_cr else 0.0

    if count_drop > max_drop_pct or value_drop > max_drop_pct:
        reason = (
            f"{label}: refusing replace — new extract has {new_count} records / "
            f"Rs {new_value_cr:,.0f} Cr vs {old_count} / Rs {old_value_cr:,.0f} Cr "
            f"currently live ({count_drop:.1f}% fewer records, {value_drop:.1f}% less value; "
            f"threshold {max_drop_pct:.0f}%). If this drop is real (a portfolio genuinely "
            f"closed out), rerun with allow_drop=True / --allow-drop."
        )
        return GuardResult(False, label, old_count, new_count, old_value_cr, new_value_cr, reason)

    return GuardResult(True, label, old_count, new_count, old_value_cr, new_value_cr)
