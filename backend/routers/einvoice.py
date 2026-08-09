from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any
import datetime

import models
from database import get_db

router = APIRouter(prefix="/api/einvoice", tags=["E-Invoice"])

@router.get("/global")
def get_global_einvoices(db: Session = Depends(get_db)) -> Dict[str, Any]:
    try:
        records = db.query(models.EInvoiceRecord).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read E-Invoice data from DB: {str(e)}")

    total_invoices = len(records)
    total_amount = 0.0
    completed_amount = 0.0
    pending_amount = 0.0

    project_type_dist = {}
    location_dist = {}
    status_dist = {}
    status_val_dist = {}
    vendor_dist = {}
    month_dist = {}
    package_dist = {}
    stage_dist = {}
    approver_dist = {}

    all_invoices = []

    for inv in records:
        amt = inv.invoiceAmount or 0.0
        so_amt = inv.soAmount or 0.0
        
        # Format for frontend matching the old JSON
        inv_dict = {
            "invoiceNo": inv.invoiceNo,
            "invoiceCode": inv.invoiceCode,
            "invoiceRequestID": inv.invoiceRequestID,
            "vendorName": inv.vendorName,
            "sapVendorCode": inv.sapVendorCode,
            "projectType": inv.projectType,
            "packageName": inv.packageName,
            "workLocation": inv.workLocation,
            "site": inv.site,
            "invoiceAmount": str(amt),
            "SOAmount": str(so_amt),
            "statusDesc": inv.statusDesc,
            "stage": inv.stage,
            "isPending": inv.isPending,
            "currentApprover": inv.currentApprover,
            "invoiceDate": inv.invoiceDate.isoformat() + "Z" if inv.invoiceDate else None,
            "createdAt": inv.createdAt.isoformat() + "Z" if inv.createdAt else None,
            "completionDate": inv.completionDate.isoformat() + "Z" if inv.completionDate else None,
            "workDescription": inv.workDescription,
            "workOrderNo": inv.workOrderNo,
            "p6ProjectName": inv.p6ProjectName
        }
        all_invoices.append(inv_dict)

        # Totals
        total_amount += amt
        status = (inv.statusDesc or 'Pending').strip()
        if status.lower() == 'completed':
            completed_amount += amt
        else:
            pending_amount += amt
            
        # Distribution by Project Type
        ptype = (inv.projectType or 'Unknown').strip()
        
        # Extrapolate BESS projects from packageName or ptype
        pkg_name = (inv.packageName or '').upper()
        if 'BESS' in pkg_name or 'BESS' in ptype.upper() or 'BESS' in (inv.workDescription or '').upper():
            ptype = 'BESS'
            
        if ptype:
            project_type_dist[ptype] = project_type_dist.get(ptype, 0) + amt
        
        # Distribution by Location
        loc = (inv.workLocation or 'Unknown').strip()
        if loc:
            location_dist[loc] = location_dist.get(loc, 0) + amt
            
        # Distribution by Package (Invoice vs SO)
        pkg = (inv.packageName or 'Unknown').strip()
        if pkg:
            if pkg not in package_dist:
                package_dist[pkg] = {'invoice': 0, 'so': 0}
            package_dist[pkg]['invoice'] += amt
            package_dist[pkg]['so'] += so_amt
            
        # Distribution by Vendor (Invoice vs SO)
        vendor = (inv.vendorName or 'Unknown').strip()
        if vendor:
            if vendor not in vendor_dist:
                vendor_dist[vendor] = {'invoice': 0, 'so': 0}
            vendor_dist[vendor]['invoice'] += amt
            vendor_dist[vendor]['so'] += so_amt
            
        # Distribution by Month
        if inv.invoiceDate:
            month_key = inv.invoiceDate.strftime('%Y-%m') # e.g., 2024-05
            month_dist[month_key] = month_dist.get(month_key, 0) + amt
        
        # Distribution by Status (count and value)
        status_dist[status] = status_dist.get(status, 0) + 1
        status_val_dist[status] = status_val_dist.get(status, 0) + amt
        
        # Distribution by Stage
        stage = (inv.stage or 'Unknown').strip()
        if stage:
            stage_dist[stage] = stage_dist.get(stage, 0) + 1
            
        # Distribution by Approver (Bottleneck)
        if inv.isPending and inv.currentApprover:
            app = inv.currentApprover.strip()
            if app not in approver_dist:
                approver_dist[app] = {'count': 0, 'value': 0}
            approver_dist[app]['count'] += 1
            approver_dist[app]['value'] += amt

    return {
        "metrics": {
            "totalInvoices": total_invoices,
            "totalAmount": total_amount,
            "completedAmount": completed_amount,
            "pendingAmount": pending_amount
        },
        "distributions": {
            "byProjectType": [{"name": k, "value": v} for k, v in project_type_dist.items()],
            "byLocation": [{"name": k, "value": v} for k, v in location_dist.items()],
            "byPackage": [{"name": k, "invoice": v['invoice'], "so": v['so']} for k, v in package_dist.items()],
            "byVendor": [{"name": k, "invoice": v['invoice'], "so": v['so']} for k, v in vendor_dist.items()],
            "byMonth": [{"name": k, "value": v} for k, v in sorted(month_dist.items())],
            "byStatus": [{"name": k, "value": v} for k, v in status_dist.items()],
            "byStatusValue": [{"name": k, "value": v} for k, v in status_val_dist.items()],
            "byStage": [{"name": f"Stage {k}" if k != 'Unknown' else k, "value": v} for k, v in sorted(stage_dist.items())],
            "byApprover": [{"name": f"Approver {k}", "count": v['count'], "value": v['value']} for k, v in sorted(approver_dist.items(), key=lambda x: x[1]['count'], reverse=True)]
        },
        "invoices": all_invoices
    }
