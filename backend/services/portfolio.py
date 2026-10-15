"""One definition of "which portfolio does this row belong to", used by every
endpoint that takes ?portfolio= and by access control.

A portfolio is a project_mapping.cluster value ("Solar Khavda", "Solar
Rajasthan", "Wind", "BESS"). Everything shown in Akasha belongs to a project,
and the project's cluster decides who may see it.

?portfolio= accepts one cluster, several separated by commas ("Solar Khavda,
Wind" - what a user with two portfolios gets), or "All Portfolios"/nothing.
Matching is exact (case-insensitive). The previous per-endpoint filters used
substring matches on cluster OR category OR project name, which is too loose
to enforce access with.

Two data gaps are bridged here, documented so they can be fixed at source:
- 2 live Wind projects (AHEJ5L, ASEJ2L PH-4) have no cluster, only category
  'Wind'. Their portfolio is taken from the category.
- Pulse NC/RFI rows carry a region ("Gujarat"/"Rajasthan"), not a cluster.
  Their portfolio is inferred from project_type + region (PULSE_RULE). A
  `transmission_line` row belongs to no portfolio, so only all-portfolio users
  see it. Comparing cluster_name with "Solar Khavda" matched nothing, which
  is why the Quality screens went empty under a portfolio filter.
"""
from typing import Optional

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

ALL = "all portfolios"


def parse(portfolio: Optional[str]) -> Optional[list[str]]:
    """Clusters asked for, or None for no filter."""
    if not portfolio:
        return None
    values = [v.strip() for v in portfolio.replace("+", " ").split(",") if v.strip()]
    if not values or any(v.lower() == ALL for v in values):
        return None
    return values


def is_filtered(portfolio: Optional[str]) -> bool:
    return parse(portfolio) is not None


# ── project_mapping ─────────────────────────────────────────────────────────

def mapping_cluster_expr():
    from models import ProjectMapping
    return func.coalesce(
        func.nullif(func.trim(ProjectMapping.cluster), ""),
        case((func.lower(ProjectMapping.category) == "wind", "Wind"), else_=None),
    )


def mapping_cluster(m) -> Optional[str]:
    """Python twin of mapping_cluster_expr for an already-loaded row."""
    c = (m.cluster or "").strip()
    if c:
        return c
    return "Wind" if (m.category or "").strip().lower() == "wind" else None


def filter_mappings(query, portfolio: Optional[str]):
    clusters = parse(portfolio)
    if clusters is None:
        return query
    return query.filter(func.lower(mapping_cluster_expr()).in_([c.lower() for c in clusters]))


def all_clusters(db: Session) -> list[str]:
    from models import ProjectMapping
    return sorted({c for (c,) in db.query(mapping_cluster_expr()).distinct() if c})


# ── Pulse (NC / RFI) ────────────────────────────────────────────────────────

def pulse_cluster_expr(model):
    t, region = func.lower(model.project_type), func.lower(model.cluster_name)
    return case(
        (t == "bess", "BESS"),
        (t.in_(["wind", "pss"]), "Wind"),          # PSS rows are the wind pooling substations
        (and_(t == "solar", region == "rajasthan"), "Solar Rajasthan"),
        (t == "solar", "Solar Khavda"),
        else_=None,
    )


def filter_pulse(query, model, portfolio: Optional[str]):
    clusters = parse(portfolio)
    if clusters is None:
        return query
    return query.filter(func.lower(pulse_cluster_expr(model)).in_([c.lower() for c in clusters]))


def cluster_in(cluster: Optional[str], clusters: Optional[list[str]]) -> bool:
    if clusters is None:
        return True
    return bool(cluster) and cluster.strip().lower() in {c.lower() for c in clusters}
