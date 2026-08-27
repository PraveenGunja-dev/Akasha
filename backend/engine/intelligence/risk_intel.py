"""
Akasha Intelligence Engine — Cross-Domain Risk Intelligence

Synthesizes results from all domain analyzers to produce:
- Unified risk matrix (schedule × material × transmission × financial × quality)
- Primary bottleneck identification
- Overall project status determination
- Cross-domain risk correlations
- Risk-specific insights

Read-only: never modifies existing data.
"""

import logging

logger = logging.getLogger(__name__)


def analyze_risk(schedule: dict, materials: dict, transmission: dict,
                 financials: dict, quality: dict, ctx: dict) -> dict:
    """
    Cross-domain risk intelligence. Reads the outputs of all 5 domain analyzers
    and produces a unified risk assessment.
    """
    project_name = ctx["project_name"]

    # ═══════════════════════════════════════════════════════
    # 1. COLLECT HEALTH SCORES
    # ═══════════════════════════════════════════════════════
    scores = {}
    weights = {}

    if schedule.get("health_score") is not None:
        scores["schedule"] = schedule["health_score"]
        weights["schedule"] = 0.35  # Schedule is most important

    if materials.get("health_score") is not None:
        scores["material"] = materials["health_score"]
        weights["material"] = 0.25

    if transmission.get("health_score") is not None:
        scores["transmission"] = transmission["health_score"]
        weights["transmission"] = 0.20

    if financials.get("health_score") is not None:
        scores["financial"] = financials["health_score"]
        weights["financial"] = 0.10

    if quality.get("health_score") is not None:
        scores["quality"] = quality["health_score"]
        weights["quality"] = 0.10

    # Renormalize weights to sum to 1.0 (if some domains have no data)
    total_weight = sum(weights.values())
    if total_weight > 0:
        weights = {k: v / total_weight for k, v in weights.items()}

    # Compute overall health
    overall_health = 0
    if scores:
        overall_health = round(sum(scores[k] * weights[k] for k in scores), 1)

    # ═══════════════════════════════════════════════════════
    # 2. DETERMINE OVERALL STATUS
    # ═══════════════════════════════════════════════════════
    if overall_health >= 75:
        overall_status = "ON_TRACK"
    elif overall_health >= 50:
        overall_status = "AT_RISK"
    elif overall_health >= 25:
        overall_status = "CRITICAL"
    else:
        overall_status = "SEVERE"

    # Override: if any single domain is critical, escalate
    any_critical = any(s < 30 for s in scores.values())
    if any_critical and overall_status == "ON_TRACK":
        overall_status = "AT_RISK"

    # ═══════════════════════════════════════════════════════
    # 3. IDENTIFY PRIMARY BOTTLENECK
    # ═══════════════════════════════════════════════════════
    domain_labels = {
        "schedule": "Construction Schedule",
        "material": "Material/Procurement",
        "transmission": "Transmission/Connectivity",
        "financial": "Financial/Budget",
        "quality": "Quality/NC",
    }

    primary_bottleneck = None
    bottleneck_detail = None
    lowest_score = 100
    lowest_domain = None

    for domain, score in scores.items():
        if score < lowest_score:
            lowest_score = score
            lowest_domain = domain

    if lowest_domain:
        primary_bottleneck = domain_labels.get(lowest_domain, lowest_domain)

        # Get specific detail from the domain
        if lowest_domain == "schedule":
            delay = schedule.get("total_delay_days", 0)
            waterfall = schedule.get("delay_waterfall", [])
            worst_phase = waterfall[0]["phase"] if waterfall else "Unknown"
            bottleneck_detail = f"Project {delay} days behind schedule. Worst phase: {worst_phase}"

        elif lowest_domain == "material":
            overdue = len(materials.get("overdue_pos", []))
            fulfillment = materials.get("summary", {}).get("fulfillment_pct", 0)
            bottleneck_detail = f"{overdue} overdue POs, {fulfillment}% fulfillment"

        elif lowest_domain == "transmission":
            tc_summary = transmission.get("summary", {})
            binding = tc_summary.get("is_tc_binding_constraint", False)
            delayed = tc_summary.get("delayed", 0)
            if binding:
                bottleneck_detail = f"TC is binding constraint — extends COD by {tc_summary.get('tc_extends_cod_by_days', 0)} days"
            else:
                bottleneck_detail = f"{delayed} transmission lines delayed"

        elif lowest_domain == "financial":
            cpi = financials.get("summary", {}).get("cpi", 1)
            variance = financials.get("summary", {}).get("variance_cr", 0)
            bottleneck_detail = f"CPI: {cpi}, Budget variance: ₹{abs(variance)} Cr"

        elif lowest_domain == "quality":
            critical = quality.get("summary", {}).get("critical_open", 0)
            closure = quality.get("summary", {}).get("closure_rate", 0)
            bottleneck_detail = f"{critical} critical NCs open, closure rate: {closure}%"

    # ═══════════════════════════════════════════════════════
    # 4. RISK MATRIX
    # ═══════════════════════════════════════════════════════
    def _risk_level(score):
        if score is None:
            return "UNKNOWN"
        if score >= 75:
            return "LOW"
        if score >= 50:
            return "MEDIUM"
        if score >= 25:
            return "HIGH"
        return "CRITICAL"

    risk_matrix = {
        domain: {
            "score": scores.get(domain),
            "risk_level": _risk_level(scores.get(domain)),
            "weight": round(weights.get(domain, 0), 2),
        }
        for domain in ["schedule", "material", "transmission", "financial", "quality"]
    }

    # ═══════════════════════════════════════════════════════
    # 5. CROSS-DOMAIN CORRELATIONS
    # ═══════════════════════════════════════════════════════
    correlations = []

    # Material delay → Schedule delay correlation
    if (materials.get("has_data") and schedule.get("has_data") and
        len(materials.get("overdue_pos", [])) > 0 and schedule.get("total_delay_days", 0) > 15):
        correlations.append({
            "from_domain": "material",
            "to_domain": "schedule",
            "correlation": "Material delivery delays are likely contributing to schedule slippage",
            "evidence": f"{len(materials.get('overdue_pos', []))} overdue POs + "
                       f"{schedule.get('total_delay_days', 0)} days project delay",
        })

    # Transmission → COD correlation
    tc_summary = transmission.get("summary", {})
    if tc_summary.get("is_tc_binding_constraint"):
        correlations.append({
            "from_domain": "transmission",
            "to_domain": "schedule",
            "correlation": "Transmission delay is the binding constraint — overrides all schedule recovery",
            "evidence": f"TC extends COD by {tc_summary.get('tc_extends_cod_by_days', 0)} days "
                       f"even if construction finishes on time",
        })

    # Quality → Schedule correlation
    critical_ncs = quality.get("summary", {}).get("critical_open", 0)
    if critical_ncs > 3 and schedule.get("total_delay_days", 0) > 0:
        correlations.append({
            "from_domain": "quality",
            "to_domain": "schedule",
            "correlation": "Critical quality NCs may be causing work stoppages",
            "evidence": f"{critical_ncs} critical NCs open, project {schedule.get('total_delay_days', 0)} days delayed",
        })

    # ═══════════════════════════════════════════════════════
    # 6. INSIGHTS
    # ═══════════════════════════════════════════════════════
    insights = []

    if overall_status in ("CRITICAL", "SEVERE"):
        insights.append({
            "severity": "critical",
            "domain": "risk",
            "title": f"Project '{project_name}' is in {overall_status} status (health: {overall_health}/100)",
            "description": f"Primary bottleneck: {primary_bottleneck}. {bottleneck_detail}",
            "impact": "Requires immediate executive attention and intervention plan",
        })

    if correlations:
        for corr in correlations:
            insights.append({
                "severity": "high",
                "domain": "risk",
                "title": f"Cross-domain impact: {corr['from_domain']} → {corr['to_domain']}",
                "description": corr["correlation"],
                "impact": corr["evidence"],
            })

    # Domains at risk
    high_risk_domains = [d for d, info in risk_matrix.items() if info["risk_level"] in ("HIGH", "CRITICAL")]
    if len(high_risk_domains) >= 3:
        insights.append({
            "severity": "critical",
            "domain": "risk",
            "title": f"{len(high_risk_domains)} domains at HIGH/CRITICAL risk",
            "description": f"Domains: {', '.join(domain_labels.get(d, d) for d in high_risk_domains)}",
            "impact": "Multi-domain risk indicates systemic project issues, not isolated problems",
        })

    return {
        "overall_health": overall_health,
        "overall_status": overall_status,
        "primary_bottleneck": primary_bottleneck,
        "bottleneck_detail": bottleneck_detail,
        "risk_matrix": risk_matrix,
        "correlations": correlations,
        "insights": insights,
    }
