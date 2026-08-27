"""
Akasha Intelligence Engine — Financial Intelligence

Analyzes SAP SLR, PO value, MB51 expenditure, and E-Invoice data to produce:
- Budget burn rate analysis
- Cost-to-complete forecasting (EAC)
- Invoice aging and payment pipeline
- Financial health scoring
- Finance-specific insights and next steps

Read-only: never modifies existing data.
"""

import logging
from datetime import datetime
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

import models

logger = logging.getLogger(__name__)


def analyze_financials(db: Session, ctx: dict) -> dict:
    """Full financial intelligence analysis."""
    project_name = ctx["project_name"]
    p6_proj = ctx.get("p6_project")
    wbs = ctx.get("wbs")
    plant_code = ctx.get("plant_code")
    mapping = ctx.get("mapping")

    if not wbs and not plant_code:
        return {
            "has_data": False, "health_score": None,
            "insights": [], "next_steps": [],
        }

    # ═══════════════════════════════════════════════════════
    # 1. BUDGET & EXPENDITURE (from SAP POs + MB51)
    # ═══════════════════════════════════════════════════════
    # Total PO value = budget committed
    po_query = db.query(
        func.sum(models.MTPOAmount.net_order_value_inr).label("budget"),
        func.count(models.MTPOAmount.id).label("po_lines"),
    )
    if wbs:
        po_query = po_query.filter(models.MTPOAmount.wbs_element.ilike(f"{wbs}%"))
    elif plant_code:
        po_query = po_query.filter(models.MTPOAmount.plant_code == plant_code)

    po_result = po_query.first()
    budget_inr = float(po_result.budget or 0) if po_result else 0
    total_po_lines = int(po_result.po_lines or 0) if po_result else 0

    # Total expenditure from MB51
    mb51_query = db.query(
        func.sum(models.MTMaterialDocument.amount_in_lc).label("expenditure"),
        func.count(models.MTMaterialDocument.id).label("doc_count"),
    )
    if wbs:
        mb51_query = mb51_query.filter(models.MTMaterialDocument.wbs_element.ilike(f"{wbs}%"))
    elif plant_code:
        mb51_query = mb51_query.filter(models.MTMaterialDocument.plant_code == plant_code)

    mb51_result = mb51_query.first()
    # MB51 amounts are typically negative (goods receipt), so negate
    expenditure_inr = abs(float(mb51_result.expenditure or 0)) if mb51_result else 0
    doc_count = int(mb51_result.doc_count or 0) if mb51_result else 0

    budget_cr = round(budget_inr / 10000000, 2) if budget_inr else 0
    expenditure_cr = round(expenditure_inr / 10000000, 2) if expenditure_inr else 0

    # ═══════════════════════════════════════════════════════
    # 2. BURN RATE & COST-TO-COMPLETE
    # ═══════════════════════════════════════════════════════
    progress_pct = 0
    if p6_proj:
        progress_pct = p6_proj.duration_percent_complete or 0
        if progress_pct > 1:
            progress_pct = progress_pct / 100  # normalize to 0-1

    burn_pct = round(expenditure_inr / max(budget_inr, 1) * 100, 1) if budget_inr > 0 else 0

    # CPI calculation
    cpi = 1.0
    if expenditure_inr > 0 and progress_pct > 0 and budget_inr > 0:
        earned_value = progress_pct * budget_inr
        cpi = round(earned_value / expenditure_inr, 2)

    # EAC (Estimate at Completion)
    eac_inr = budget_inr / cpi if cpi > 0 else budget_inr
    eac_cr = round(eac_inr / 10000000, 2)
    variance_cr = round((eac_cr - budget_cr), 2)
    variance_pct = round(variance_cr / max(budget_cr, 0.01) * 100, 1)

    # ═══════════════════════════════════════════════════════
    # 3. E-INVOICE ANALYSIS (if data exists)
    # ═══════════════════════════════════════════════════════
    invoice_summary = {"total": 0, "pending": 0, "pending_value": 0}

    # Try to find invoices via PO lookup
    if wbs:
        wbs_prefix = wbs[:6] if len(wbs) >= 6 else wbs
        po_lookups = db.query(models.MTEInvoicePOLookup.purchasing_document).filter(
            models.MTEInvoicePOLookup.wbs_element.ilike(f"{wbs_prefix}%")
        ).all()
        po_numbers = [p[0] for p in po_lookups if p[0]]

        if po_numbers:
            invoices = db.query(models.EInvoiceRecord).filter(
                models.EInvoiceRecord.workOrderNo.in_(po_numbers)
            ).all()

            total_invoices = len(invoices)
            pending_invoices = [inv for inv in invoices if inv.isPending]
            pending_value = sum(float(inv.invoiceAmount or 0) for inv in pending_invoices)

            invoice_summary = {
                "total": total_invoices,
                "pending": len(pending_invoices),
                "pending_value_cr": round(pending_value / 10000000, 2),
                "stages": defaultdict(int),
            }
            for inv in pending_invoices:
                stage = inv.stage or "Unknown"
                invoice_summary["stages"][stage] += 1
            invoice_summary["stages"] = dict(invoice_summary["stages"])

    # ═══════════════════════════════════════════════════════
    # 4. HEALTH SCORE
    # ═══════════════════════════════════════════════════════
    # Financial health based on CPI, burn alignment, and invoice flow
    if budget_inr == 0:
        health_score = None
    else:
        cpi_score = min(cpi * 50, 50)  # CPI of 1.0 = 50 points
        burn_alignment = 50 - abs(burn_pct - (progress_pct * 100)) * 0.5  # Penalty for misalignment
        burn_alignment = max(0, min(50, burn_alignment))
        health_score = round(max(0, min(100, cpi_score + burn_alignment)), 1)

    # ═══════════════════════════════════════════════════════
    # 5. INSIGHTS
    # ═══════════════════════════════════════════════════════
    insights = []

    if cpi < 0.85 and budget_inr > 0:
        insights.append({
            "severity": "critical" if cpi < 0.7 else "high",
            "domain": "financial",
            "title": f"Cost overrun detected — CPI is {cpi}",
            "description": f"Budget: ₹{budget_cr} Cr, Spent: ₹{expenditure_cr} Cr, Progress: {round(progress_pct*100, 1)}%. "
                          f"EAC: ₹{eac_cr} Cr (₹{abs(variance_cr)} Cr {'overrun' if variance_cr > 0 else 'underrun'})",
            "impact": f"At current spending rate, project will overrun budget by ₹{abs(variance_cr)} Cr ({abs(variance_pct)}%)",
        })

    if burn_pct > 80 and progress_pct < 0.6 and budget_inr > 0:
        insights.append({
            "severity": "high",
            "domain": "financial",
            "title": f"Budget burn rate is {burn_pct}% but progress is only {round(progress_pct*100, 1)}%",
            "description": f"Spending is outpacing progress — ₹{expenditure_cr} Cr spent of ₹{budget_cr} Cr budget",
            "impact": "Likely to exhaust budget before project completion",
        })

    if invoice_summary.get("pending", 0) > 5:
        insights.append({
            "severity": "medium",
            "domain": "financial",
            "title": f"{invoice_summary['pending']} invoices pending approval",
            "description": f"Total pending value: ₹{invoice_summary.get('pending_value_cr', 0)} Cr. "
                          f"Stages: {invoice_summary.get('stages', {})}",
            "impact": "Delayed payments may cause vendors to slow down or stop work",
        })

    # ═══════════════════════════════════════════════════════
    # 6. NEXT STEPS
    # ═══════════════════════════════════════════════════════
    next_steps = []

    if cpi < 0.85 and budget_inr > 0:
        next_steps.append({
            "priority": "P1",
            "category": "finance",
            "action": f"Conduct cost review — CPI {cpi} indicates ₹{abs(variance_cr)} Cr overrun risk",
            "reason": f"Estimate at Completion: ₹{eac_cr} Cr vs Budget ₹{budget_cr} Cr",
            "assigned_role": "finance",
        })

    if invoice_summary.get("pending", 0) > 3:
        next_steps.append({
            "priority": "P2",
            "category": "finance",
            "action": f"Clear {invoice_summary['pending']} pending invoices "
                      f"(₹{invoice_summary.get('pending_value_cr', 0)} Cr)",
            "reason": "Vendor payment delays create supply chain risk",
            "assigned_role": "finance",
        })

    return {
        "has_data": budget_inr > 0 or expenditure_inr > 0,
        "health_score": health_score,

        "summary": {
            "budget_cr": budget_cr,
            "expenditure_cr": expenditure_cr,
            "burn_pct": burn_pct,
            "cpi": cpi,
            "eac_cr": eac_cr,
            "variance_cr": variance_cr,
            "variance_pct": variance_pct,
            "total_po_lines": total_po_lines,
            "total_documents": doc_count,
        },

        "invoices": invoice_summary,

        "insights": insights,
        "next_steps": next_steps,
    }
