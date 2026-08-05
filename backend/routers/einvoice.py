from fastapi import APIRouter, HTTPException
import json
import os
from typing import Dict, Any

router = APIRouter(prefix="/api/einvoice", tags=["E-Invoice"])

# Path to the static JSON file
E_INVOICE_FILE_PATH = r"d:\Akasha_Platform\Data\NEW31\Get All Invoices Production(E-invoice) json response.txt"

@router.get("/global")
def get_global_einvoices() -> Dict[str, Any]:
    if not os.path.exists(E_INVOICE_FILE_PATH):
        raise HTTPException(status_code=404, detail="E-Invoice data file not found.")

    try:
        with open(E_INVOICE_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read E-Invoice data: {str(e)}")

    all_invoices = data.get('d', {}).get('results', [])

    # We will compute some high-level metrics right here to save frontend processing, 
    # but also return the raw list so the frontend master table can use it.
    
    total_invoices = len(all_invoices)
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

    for inv in all_invoices:
        # Amount parsing
        inv_amt_str = inv.get('invoiceAmount')
        try:
            amt = float(inv_amt_str) if inv_amt_str else 0.0
        except ValueError:
            amt = 0.0
        
        # Totals
        total_amount += amt
        status = (inv.get('statusDesc') or 'Pending').strip()
        if status.lower() == 'completed':
            completed_amount += amt
        else:
            pending_amount += amt
            
        # Distribution by Project Type
        ptype = (inv.get('projectType') or 'Unknown').strip()
        if ptype:
            project_type_dist[ptype] = project_type_dist.get(ptype, 0) + amt
        
        # Distribution by Location
        loc = (inv.get('workLocation') or 'Unknown').strip()
        if loc:
            location_dist[loc] = location_dist.get(loc, 0) + amt
            
        # Distribution by Package
        pkg = (inv.get('packageName') or 'Unknown').strip()
        if pkg:
            package_dist[pkg] = package_dist.get(pkg, 0) + amt
            
        # Distribution by Vendor
        vendor = (inv.get('vendorName') or 'Unknown').strip()
        if vendor:
            vendor_dist[vendor] = vendor_dist.get(vendor, 0) + amt
            
        # Distribution by Month
        inv_date_str = inv.get('invoiceDate')
        if inv_date_str and '/Date(' in inv_date_str:
            try:
                import datetime
                import re
                match = re.search(r'/Date\((\d+)', inv_date_str)
                if match:
                    ms = int(match.group(1))
                    dt = datetime.datetime.fromtimestamp(ms / 1000.0)
                    month_key = dt.strftime('%Y-%m') # e.g., 2024-05
                    month_dist[month_key] = month_dist.get(month_key, 0) + amt
            except:
                pass
        
        # Distribution by Status (count and value)
        status_dist[status] = status_dist.get(status, 0) + 1
        status_val_dist[status] = status_val_dist.get(status, 0) + amt

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
            "byPackage": [{"name": k, "value": v} for k, v in package_dist.items()],
            "byVendor": [{"name": k, "value": v} for k, v in vendor_dist.items()],
            "byMonth": [{"name": k, "value": v} for k, v in sorted(month_dist.items())],
            "byStatus": [{"name": k, "value": v} for k, v in status_dist.items()],
            "byStatusValue": [{"name": k, "value": v} for k, v in status_val_dist.items()]
        },
        "invoices": all_invoices
    }
