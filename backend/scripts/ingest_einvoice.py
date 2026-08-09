import os
import sys
import json
import datetime

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

import models
from database import engine, SessionLocal
from scripts.ingest_sap_data import build_wbs_mapping, match_wbs_to_master

def parse_date(date_str):
    if not date_str:
        return None
    if isinstance(date_str, str) and '/Date(' in date_str:
        import re
        match = re.search(r'\/Date\((\d+)', date_str)
        if match:
            ms = int(match.group(1))
            return datetime.datetime.fromtimestamp(ms / 1000.0)
    # Handle ISO strings if any
    try:
        from dateutil import parser
        return parser.parse(date_str)
    except:
        return None

def ingest_einvoice():
    print("Dropping old table if exists...")
    models.EInvoiceRecord.__table__.drop(bind=engine, checkfirst=True)
    
    print("Creating tables if not exists...")
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    data_dir = os.path.join(os.path.dirname(backend_dir), "Data", "NEW31")
    einvoice_path = os.path.join(data_dir, "Get All Invoices Production(E-invoice) json response.txt")
    
    if not os.path.exists(einvoice_path):
        print(f"Error: Could not find E-Invoice data at {einvoice_path}")
        return
        
    master_path = os.path.join(data_dir, "AKASHA SAP MASTER FILE.xlsx")
    print("Building WBS mapping from SAP Master...")
    wbs_map = build_wbs_mapping(master_path)
    
    print("Pre-loading PO to WBS mappings...")
    po_wbs = {po.purchasing_document: po.wbs_element for po in db.query(models.MTPOAmount.purchasing_document, models.MTPOAmount.wbs_element).all() if po.purchasing_document}

    print("Reading E-Invoice JSON data...")
    with open(einvoice_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    results = data.get('d', {}).get('results', [])
    if not results:
        print("No results found in JSON.")
        return

    print(f"Found {len(results)} invoice records. Clearing old records...")
    # Clear old records (truncate essentially)
    db.query(models.EInvoiceRecord).delete()
    db.commit()

    print("Inserting new records...")
    records = []
    for inv in results:
        # Safe float conversion
        try:
            inv_amt = float(inv.get('invoiceAmount') or 0)
        except ValueError:
            inv_amt = 0.0
            
        try:
            so_amt = float(inv.get('SOAmount') or 0)
        except ValueError:
            so_amt = 0.0

        work_order_no = inv.get('workOrderNo')
        
        # Try to resolve p6ProjectName
        p6_proj_name = None
        if work_order_no:
            wbs = po_wbs.get(work_order_no)
            if wbs:
                match = match_wbs_to_master(wbs, wbs_map)
                if match:
                    p6_proj_name = match.get('project_name')

        record = models.EInvoiceRecord(
            invoiceNo=inv.get('invoiceNo'),
            invoiceCode=inv.get('invoiceCode'),
            invoiceRequestID=inv.get('invoiceRequestID'),
            vendorName=inv.get('vendorName'),
            sapVendorCode=inv.get('sapVendorCode'),
            projectType=inv.get('projectType'),
            packageName=inv.get('packageName'),
            workLocation=inv.get('workLocation'),
            site=inv.get('site'),
            invoiceAmount=inv_amt,
            soAmount=so_amt,
            statusDesc=(inv.get('statusDesc') or 'Pending').strip(),
            invoiceDate=parse_date(inv.get('invoiceDate')),
            createdAt=parse_date(inv.get('createdAt')),
            completionDate=parse_date(inv.get('completionDate')),
            workDescription=inv.get('workDescription'),
            workOrderNo=work_order_no,
            p6ProjectName=p6_proj_name
        )
        records.append(record)

    # Batch insert
    BATCH_SIZE = 1000
    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        db.add_all(batch)
        db.commit()
        total += len(batch)
        print(f"Inserted batch {i // BATCH_SIZE + 1}: {len(batch)} records (Total: {total})")

    db.close()
    print("Ingestion complete!")

if __name__ == "__main__":
    ingest_einvoice()
