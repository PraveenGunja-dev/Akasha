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
def get_financials(project_name: Optional[str] = None, portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"fin_{project_name or 'All'}_{portfolio or 'All'}"
    if not nocache and cache_key in _FIN_CACHE:
        entry = _FIN_CACHE[cache_key]
        if time.time() - entry["timestamp"] < _FIN_TTL:
            return entry["data"]

    po_query = db.query(
        func.sum(models.MTPOAmount.net_order_value).label("total_val"),
        func.count(models.MTPOAmount.id).label("total_pos"),
        func.count(func.distinct(models.MTPOAmount.vendor_name)).label("vendors"),
        func.count(func.distinct(models.MTPOAmount.material_code)).label("materials"),
        func.sum(models.MTPOAmount.po_quantities).label("volume")
    )
    
    # 1. Global Portfolio Filter
    map_query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        map_query = map_query.filter(
            (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
            (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
        )
    
    # 2. Local Project Filter
    if project_name and project_name != "All":
        map_query = map_query.filter(models.ProjectMapping.project_name_from_p6 == project_name)
        
    mappings = map_query.all()
    
    if (project_name and project_name != "All") or (portfolio and portfolio.lower() != "all portfolios"):
        wbs_exacts = [
            str(m.module_wbs).strip()
            for m in mappings
            if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', 'null', '')
        ]
        if wbs_exacts:
            wbs_conditions = [models.MTPOAmount.wbs_element == p for p in wbs_exacts]
            po_query = po_query.filter(or_(*wbs_conditions))
        else:
            return [{"quarter": "Total", "plannedCapex": 0, "actualCapex": 0, "cashFlowVariancePercent": 0, "totalPos": 0, "vendors": 0, "materials": 0, "volume": 0}]

    res = po_query.first()
    total_po_value = res.total_val or 0
    total_pos = res.total_pos or 0
    vendors = res.vendors or 0
    materials = res.materials or 0
    volume = res.volume or 0
    
    # Convert from raw INR to Crores (1 Cr = 10,000,000)
    total_po_value_cr = round(total_po_value / 10000000, 2)
    result = [
        {
            "quarter": "Total",
            "plannedCapex": 0,
            "actualCapex": total_po_value_cr,
            "cashFlowVariancePercent": 0,
            "totalPos": total_pos,
            "vendors": vendors,
            "materials": materials,
            "volume": volume
        }
    ]
    _FIN_CACHE[cache_key] = {"data": result, "timestamp": time.time()}
    return result

@router.get("/financials/details")
def get_financials_details(project_name: Optional[str] = None, portfolio: Optional[str] = None, nocache: bool = False, db: Session = Depends(get_db)):
    cache_key = f"fin_det_{project_name or 'All'}_{portfolio or 'All'}"
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
            
    if project_name and project_name != "All":
        map_query = map_query.filter(models.ProjectMapping.project_name_from_p6 == project_name)
        
    mappings = map_query.all()
    
    if (project_name and project_name != "All") or (portfolio and portfolio.lower() != "all portfolios"):
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

    # 3. MB52 Inventory Total
    inv_total = db.query(func.sum(models.MTInventory.quantity_inv)).scalar() or 0

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

    result = {
        'trends': sorted_timeline,
        'total_inventory': float(inv_total)
    }

    _FIN_CACHE[cache_key] = {'data': result, 'timestamp': time.time()}
    return result

