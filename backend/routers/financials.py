from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional
from database import get_db
import models
import time

_FIN_CACHE = {}
_FIN_TTL = 300  # 5 minutes

router = APIRouter(prefix="/api")

@router.get("/financials")
def get_financials(project_name: Optional[str] = None, portfolio: Optional[str] = None, phase: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"fin_{project_name or 'All'}_{portfolio or 'All'}_{phase or 'All'}"
    if not nocache and cache_key in _FIN_CACHE:
        entry = _FIN_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _FIN_TTL:
            return entry["data"]

    from slr_rules import po_lines_only, zsps_po_lines_only
    # ZSPS (mt_poamount) is the book of record for purchase orders, so PO value,
    # PO count and delivered value all come off it. These previously came from
    # SLR (type='POrd' plus the po_lines_only filter), a narrower population
    # reporting 38,583.85 Cr over 5,408 POs where ZSPS holds 66,691.36 Cr over
    # 6,413 - a 28,107 Cr gap between this screen and the executive band.
    po_query = db.query(
        func.count(func.distinct(models.MTPOAmount.vendor_name)).label("vendors"),
        func.count(func.distinct(models.MTPOAmount.material_code)).label("materials"),
        func.sum(models.MTPOAmount.po_quantities).label("volume"),
        func.sum(models.MTPOAmount.net_order_value_inr).label("po_value"),
        func.sum(models.MTPOAmount.delivered_value_inr_cr).label("po_delivered_cr"),
        func.count(func.distinct(models.MTPOAmount.purchasing_document)).label("total_pos")
    ).filter(zsps_po_lines_only())
    
    slr_query = db.query(
        func.sum(func.coalesce(models.MTSLRData.actual_amount, 0) + func.coalesce(models.MTSLRData.commitment_amount, 0)).label("total_val"),
        func.count(func.distinct(models.MTSLRData.po_document)).label("total_pos")
    ).filter(po_lines_only(), models.MTSLRData.type == 'POrd')
    
    # 1. Global Portfolio Filter
    map_query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        map_query = map_query.filter(
            (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
            (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
        )
        
    normalised = (phase or "all").strip().lower()
    if normalised == "ongoing":
        map_query = map_query.filter(models.ProjectMapping.is_commissioned.is_(False))
    elif normalised == "commissioned":
        map_query = map_query.filter(models.ProjectMapping.is_commissioned.is_(True))
    
    # 2. Local Project Filter
    if project_name and project_name != "All":
        map_query = map_query.filter(models.ProjectMapping.project_name_from_p6 == project_name)
        
    mappings = map_query.all()
    
    if (project_name and project_name != "All") or (portfolio and portfolio.lower() != "all portfolios") or (phase and phase.lower() not in ("all", "")):
        wbs_exacts = [
            str(m.module_wbs).strip()
            for m in mappings
            if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', '')
        ]
        if wbs_exacts:
            wbs_conditions = [models.MTPOAmount.wbs_element == p for p in wbs_exacts]
            po_query = po_query.filter(or_(*wbs_conditions))
            
            # SLR data stores plant code without H- prefix. We can use the prefixes for SLR
            from routers.dashboard import _extract_wbs_prefixes
            wbs_prefixes = []
            for m in mappings:
                for val in [m.spv_plant_code, m.agel, m.age6l]:
                    if val:
                        import re
                        matches = [c.upper() for c in re.findall(r'H-?\s*([A-Za-z0-9]+)', str(val).strip())]
                        wbs_prefixes.extend(matches)
            wbs_prefixes = list(set(wbs_prefixes))
            if wbs_prefixes:
                slr_query = slr_query.filter(models.MTSLRData.plant_code.in_(wbs_prefixes))
        else:
            return [{"quarter": "Total", "plannedCapex": 0, "actualCapex": 0, "deliveredCapex": 0, "cashFlowVariancePercent": 0, "totalPos": 0, "vendors": 0, "materials": 0, "volume": 0}]

    res = po_query.first()
    
    total_po_value = (res.po_value or 0) if res else 0
    total_pos = (res.total_pos or 0) if res else 0
    # delivered_value_inr_cr is already stored in crore by the ZSPS ingest.
    delivered_cr = (res.po_delivered_cr or 0) if res else 0
    vendors = (res.vendors or 0) if res else 0
    materials = (res.materials or 0) if res else 0
    volume = (res.volume or 0) if res else 0
    
    # Convert from raw INR to Crores (1 Cr = 10,000,000)
    total_po_value_cr = round(total_po_value / 10000000, 2)
    result = [
        {
            "quarter": "Total",
            "plannedCapex": 0,
            "actualCapex": total_po_value_cr,
            "deliveredCapex": round(delivered_cr, 2),
            "cashFlowVariancePercent": 0,
            "totalPos": total_pos,
            "vendors": vendors,
            "materials": materials,
            "volume": volume
        }
    ]
    _FIN_CACHE[cache_key] = {"data": result, "timestamp": time.time()}
    return result

@router.get("/financials/material-breakdown")
def get_material_breakdown(by: str = "category", limit: int = 6, codes: Optional[str] = None, db: Session = Depends(get_db)):
    """Material flow per group, in VALUE, split into stages that do not overlap.

    Two things this fixes over the quantity-based version:

    1. QUANTITY IS NOT SUMMABLE HERE. mt_poamount mixes units of measure
       across lines, and the columns do not reconcile at all —
       order_quantity 354,213,226 against still_to_deliver 380,898,647 and
       delivered 671,042,584. Adding those is arithmetic on different things.
       The value columns DO reconcile exactly (35,740.7 + 30,950.7 =
       66,691.4 Cr), so value is what the chart can honestly stack.

    2. STAGES MUST PARTITION, NOT NEST. "PO raised" already contains what is
       in transit, so stacking PO + in-transit double counts the same money.
       The stages here are DELIVERED and IN TRANSIT, which sum to ordered.
    """
    CR = 10000000.0
    col = models.MTPOAmount.vendor_name if by == "supplier" else models.MTPOAmount.material_name

    q = db.query(
        col,
        func.sum(models.MTPOAmount.net_order_value_inr),
        func.sum(models.MTPOAmount.delivered_value_inr_cr),
        func.count(func.distinct(models.MTPOAmount.purchasing_document)),
    )

    # Optional company scope: comma-separated plant / WBS codes, matched the
    # way the SAP screen's SPV / AGEL / AGE6L toggle matches them client-side
    # (substring on plant_code or wbs_element, with and without the H- prefix).
    # Filtering here keeps the toggle honest — the screen used to re-aggregate
    # a 1,000-row sample of an 88k-row table when a scope was selected.
    code_list = [c.strip() for c in (codes or "").split(",") if c.strip()]
    if code_list:
        conds = []
        for c in code_list:
            for variant in {c, c[2:] if c.upper().startswith("H-") else c}:
                conds.append(models.MTPOAmount.plant_code.ilike(f"%{variant}%"))
                conds.append(models.MTPOAmount.wbs_element.ilike(f"%{variant}%"))
        q = q.filter(or_(*conds))

    rows = q.group_by(col).all()

    out = []
    for name, ordered, delivered, pos in rows:
        ordered_cr = round((ordered or 0) / CR, 1)
        if ordered_cr <= 0:
            continue
        delivered_cr = round(delivered or 0, 1)
        out.append({
            "name": (name or "").strip() or ("(no vendor recorded)" if by == "supplier" else "Unclassified"),
            "ordered_cr": ordered_cr,
            "delivered_cr": delivered_cr,
            "in_transit_cr": round(max(ordered_cr - delivered_cr, 0), 1),
            "pos": pos or 0,
            "delivered_pct": round(delivered_cr * 100.0 / ordered_cr, 1) if ordered_cr else 0.0,
        })

    out.sort(key=lambda r: -r["ordered_cr"])
    return {"by": by, "groups": out[:limit], "group_count": len(out)}


@router.get("/financials/material-mix")
def get_material_mix(limit: int = 7, db: Session = Depends(get_db)):
    """Where the material money sits, and how far along it is.

    Two readings of the same ZSPS rows:

      categories  ordered value split by material_name. `material_type` is
                  null on all 87,899 rows, so the name is the only category
                  the data actually carries. Long tail folded into "Other".

      status      ordered / delivered / still-to-deliver, in crore. These
                  reconcile exactly — delivered + still = ordered — because
                  ZSPS stores Actual Amount and Commitment Amt separately and
                  the ingest sums them into net_order_value.

    No segment names are invented: there is no generation/transmission/
    distribution column in this data, so the split is by what was bought.
    """
    CR = 10000000.0

    totals = db.query(
        func.sum(models.MTPOAmount.net_order_value_inr),
        func.sum(models.MTPOAmount.delivered_value_inr_cr),
        func.sum(models.MTPOAmount.still_to_deliver_inr),
        func.count(func.distinct(models.MTPOAmount.purchasing_document)),
    ).one()

    ordered_cr = round((totals[0] or 0) / CR, 1)
    delivered_cr = round(totals[1] or 0, 1)
    in_transit_cr = round((totals[2] or 0) / CR, 1)
    po_count = totals[3] or 0

    rows = db.query(
        models.MTPOAmount.material_name,
        func.sum(models.MTPOAmount.net_order_value_inr),
        func.count(models.MTPOAmount.id),
    ).group_by(models.MTPOAmount.material_name).all()

    named = [
        {"name": (r[0] or "Unclassified").strip() or "Unclassified",
         "value_cr": round((r[1] or 0) / CR, 1),
         "lines": r[2]}
        for r in rows if (r[1] or 0) > 0
    ]
    named.sort(key=lambda x: -x["value_cr"])

    top = named[:limit]
    tail = named[limit:]
    if tail:
        top.append({
            "name": "Other",
            "value_cr": round(sum(t["value_cr"] for t in tail), 1),
            "lines": sum(t["lines"] for t in tail),
            "rolled_up": len(tail),
        })

    for t in top:
        t["share"] = round(t["value_cr"] * 100.0 / ordered_cr, 1) if ordered_cr else 0.0

    # ── Signals worth acting on ───────────────────────────────────────────
    # Only what the columns actually support. `delivery_date` is NULL on all
    # 87,899 rows, so there is no overdue or ageing analysis to be had here;
    # vendor_name and the delivered/committed split are fully populated, and
    # those carry the real exposure.

    # Delivery rate per category: the biggest spend is not always the one
    # landing, and that gap is the thing a value ring cannot show.
    rate_rows = db.query(
        models.MTPOAmount.material_name,
        func.sum(models.MTPOAmount.net_order_value_inr),
        func.sum(models.MTPOAmount.delivered_value_inr_cr),
    ).group_by(models.MTPOAmount.material_name).all()

    rates = []
    for name, ordered, delivered in rate_rows:
        o_cr = (ordered or 0) / CR
        if o_cr < 500:                      # ignore the long tail
            continue
        rates.append({
            "name": (name or "Unclassified").strip() or "Unclassified",
            "ordered_cr": round(o_cr, 1),
            "delivered_cr": round(delivered or 0, 1),
            "delivered_pct": round((delivered or 0) * 100.0 / o_cr, 1) if o_cr else 0.0,
        })
    rates.sort(key=lambda r: r["delivered_pct"])
    laggard = rates[0] if rates else None
    leader = rates[-1] if rates else None

    # Counterparty concentration of what is still owed to us.
    vend_rows = db.query(
        models.MTPOAmount.vendor_name,
        func.sum(models.MTPOAmount.still_to_deliver_inr),
        func.count(func.distinct(models.MTPOAmount.purchasing_document)),
    ).filter(models.MTPOAmount.still_to_deliver_inr > 0).group_by(models.MTPOAmount.vendor_name).all()

    named_vendors, unattributed_cr, unattributed_pos = [], 0.0, 0
    for vname, still, pos in vend_rows:
        cr = (still or 0) / CR
        if not (vname or "").strip():
            unattributed_cr += cr
            unattributed_pos += pos or 0
            continue
        named_vendors.append({"name": vname.strip(), "cr": round(cr, 1), "pos": pos or 0})
    named_vendors.sort(key=lambda v: -v["cr"])

    top_vendor = named_vendors[0] if named_vendors else None
    if top_vendor and in_transit_cr:
        top_vendor["share"] = round(top_vendor["cr"] * 100.0 / in_transit_cr, 1)

    return {
        "ordered_cr": ordered_cr,
        "delivered_cr": delivered_cr,
        "in_transit_cr": in_transit_cr,
        "po_count": po_count,
        "delivered_pct": round(delivered_cr * 100.0 / ordered_cr, 1) if ordered_cr else 0.0,
        "in_transit_pct": round(in_transit_cr * 100.0 / ordered_cr, 1) if ordered_cr else 0.0,
        "categories": top,
        "category_count": len(named),
        "laggard": laggard,
        "leader": leader,
        "top_vendor": top_vendor,
        "unattributed_cr": round(unattributed_cr, 1),
        "unattributed_pos": unattributed_pos,
        "unattributed_pct": round(unattributed_cr * 100.0 / in_transit_cr, 1) if in_transit_cr else 0.0,
        # Stated so the UI never implies a schedule signal this data cannot give.
        "has_delivery_dates": False,
    }


@router.get("/financials/details")
def get_financials_details(project_name: Optional[str] = None, portfolio: Optional[str] = None, phase: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"fin_det_{project_name or 'All'}_{portfolio or 'All'}_{phase or 'All'}"
    if not nocache and cache_key in _FIN_CACHE:
        entry = _FIN_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _FIN_TTL:
            return entry["data"]

    query = db.query(models.MTPOAmount)
    
    map_query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        map_query = map_query.filter(
            (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
            (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
        )
        
    normalised = (phase or "all").strip().lower()
    if normalised == "ongoing":
        map_query = map_query.filter(models.ProjectMapping.is_commissioned.is_(False))
    elif normalised == "commissioned":
        map_query = map_query.filter(models.ProjectMapping.is_commissioned.is_(True))
            
    if project_name and project_name != "All":
        map_query = map_query.filter(models.ProjectMapping.project_name_from_p6 == project_name)
        
    mappings = map_query.all()
    
    if (project_name and project_name != "All") or (portfolio and portfolio.lower() != "all portfolios") or (phase and phase.lower() not in ("all", "")):
        wbs_exacts = [
            str(m.module_wbs).strip()
            for m in mappings
            if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', '')
        ]
        if wbs_exacts:
            wbs_conditions = [models.MTPOAmount.wbs_element == p for p in wbs_exacts]
            query = query.filter(or_(*wbs_conditions))
        else:
            return []
            
    results = query.order_by(models.MTPOAmount.net_order_value.desc()).limit(1000).all()
    _FIN_CACHE[cache_key] = {"data": results, "timestamp": time.time()}
    return results


@router.get('/financials/trends')
def get_financials_trends(db: Session = Depends(get_db)):
    cache_key = 'fin_trends_global'
    if cache_key in _FIN_CACHE and time.time() - _FIN_CACHE[cache_key]['timestamp'] < _FIN_TTL:
        return _FIN_CACHE[cache_key]['data']

    # 1. MB51 Consumption
    mat_q = db.query(
        func.date_trunc('month', models.MTMaterialDocument.posting_date).label('month'),
        func.sum(models.MTMaterialDocument.quantity).label('qty'),
        func.sum(models.MTMaterialDocument.amount_in_lc).label('val')
    ).filter(models.MTMaterialDocument.posting_date.isnot(None)).group_by('month').all()

    # 2. ME2J POs
    po_q = db.query(
        func.date_trunc('month', models.MTPOAmount.document_date).label('month'),
        func.sum(models.MTPOAmount.order_quantity).label('qty')
    ).filter(models.MTPOAmount.document_date.isnot(None)).group_by('month').all()

    # 3. MB52 Inventory — total, plus the movement behind it.
    # MB52 carries no dates: every row is a point-in-time stock position, so a
    # history cannot be read from it. MB51 does have dated movements, so the
    # position is reconstructed BACKWARDS from the known MB52 closing figure.
    inv_total = db.query(func.sum(models.MTInventory.quantity_inv)).scalar() or 0

    mov_by_month = {
        row.month.strftime('%Y-%m'): float(row.qty or 0)
        for row in mat_q if row.month is not None
    }

    timeline = {}
    
    for row in mat_q:
        m_str = row.month.strftime('%Y-%m')
        if m_str not in timeline:
            timeline[m_str] = {'month': m_str, 'po_qty': 0, 'consumed_qty': 0, 'reversals': 0, 'value_inr': 0}
        
        qty = float(row.qty or 0)
        val = float(row.val or 0)
        if qty < 0:
            timeline[m_str]['consumed_qty'] += qty
            timeline[m_str]['value_inr'] += val
        else:
            timeline[m_str]['reversals'] += qty

    for row in po_q:
        m_str = row.month.strftime('%Y-%m')
        if m_str not in timeline:
            timeline[m_str] = {'month': m_str, 'po_qty': 0, 'consumed_qty': 0, 'reversals': 0, 'value_inr': 0}
        timeline[m_str]['po_qty'] += float(row.qty or 0)

    sorted_timeline = [timeline[k] for k in sorted(timeline.keys())]
    # Filter out empty months before 2022 if they exist
    sorted_timeline = [x for x in sorted_timeline if x['month'] >= '2022-01']

    # Walk backwards from the MB52 closing position, undoing each month's net
    # movement, so the line ends exactly on the figure shown above the chart.
    running = float(inv_total)
    for row in reversed(sorted_timeline):
        row['inventory_qty'] = round(running, 2)
        running -= mov_by_month.get(row['month'], 0.0)

    result = {
        'trends': sorted_timeline,
        'total_inventory': float(inv_total)
    }

    _FIN_CACHE[cache_key] = {'data': result, 'timestamp': time.time()}
    return result

