import os
import sys
import requests
from dotenv import load_dotenv

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

import models
from database import engine, SessionLocal
from scripts.ingest_sap_data import build_wbs_mapping, match_wbs_to_master
from scripts.ingest_einvoice import parse_date

load_dotenv()

def fetch_live_invoices():
    print("Authenticating with SAP UAT BTP Token endpoint...")
    token_url = os.getenv('EINVOICE_TOKEN_URL')
    client_id = os.getenv('EINVOICE_CLIENT_ID')
    client_secret = os.getenv('EINVOICE_CLIENT_SECRET')

    if not all([token_url, client_id, client_secret]):
        print("E-Invoice credentials missing from environment. "
              "Set EINVOICE_TOKEN_URL, EINVOICE_CLIENT_ID and EINVOICE_CLIENT_SECRET in backend/.env")
        return []

    try:
        r = requests.post(token_url, data={'grant_type': 'client_credentials'}, auth=(client_id, client_secret))
        r.raise_for_status()
        token = r.json().get('access_token')
        print("Successfully obtained access token!")
    except Exception as e:
        print(f"Failed to authenticate: {e}")
        if r: print(r.text)
        return []

    print("Fetching invoices from LIVE SAP API...")
    api_url = 'https://adani-green-energy-limited-asset-tagging-renewables-dev583d013a.cfapps.ap11.hana.ondemand.com/odata/v2/InvoiceChatBotService/getAllInvoices'
    
    try:
        res = requests.get(api_url, headers={'Authorization': f'Bearer {token}'})
        res.raise_for_status()
        data = res.json()
        results = data.get('d', {}).get('results', []) if 'd' in data else data
        print(f"Successfully fetched {len(results)} invoices!")
        return results
    except Exception as e:
        print(f"Failed to fetch invoices: {e}")
        if res: print(res.text)
        return []


def sync_einvoice_live():
    results = fetch_live_invoices()
    if not results:
        print("No invoices returned. Aborting sync.")
        return

    print("Dropping old table if exists to load fresh live data...")
    models.EInvoiceRecord.__table__.drop(bind=engine, checkfirst=True)
    
    print("Creating tables if not exists...")
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    data_dir = os.path.join(os.path.dirname(backend_dir), "Data", "NEW31")
        
    master_path = os.path.join(data_dir, "AKASHA SAP MASTER FILE.xlsx")
    print("Building WBS mapping from SAP Master...")
    wbs_map = build_wbs_mapping(master_path)
    
    print("Pre-loading PO to WBS mappings...")
    po_wbs = {po.purchasing_document: po.wbs_element for po in db.query(models.MTPOAmount.purchasing_document, models.MTPOAmount.wbs_element).all() if po.purchasing_document}

    print(f"Found {len(results)} invoice records. Clearing old records in DB...")
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
            workOrderNo=work_order_no,
            invoiceAmount=inv_amt,
            soAmount=so_amt,
            statusDesc=inv.get('statusDesc'),
            stage=str(inv.get('stage')) if inv.get('stage') is not None else None,
            isPending=inv.get('isPending') == True or str(inv.get('isPending')).lower() == 'true',
            submittedOn=parse_date(inv.get('submissionDate')),
            invoiceDate=parse_date(inv.get('invoiceDate')),
            currentApprover=inv.get('currentApprover'),
            latestAction=inv.get('lastActionDate'),
            p6ProjectName=p6_proj_name
        )
        records.append(record)
        
        # Batch insert to avoid huge memory spike
        if len(records) >= 500:
            db.add_all(records)
            db.commit()
            records = []
            
    if records:
        db.add_all(records)
        db.commit()
        
    print(f"Live Ingestion complete! Total records inserted: {len(results)}")

if __name__ == "__main__":
    sync_einvoice_live()
