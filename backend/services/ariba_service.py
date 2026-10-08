import pandas as pd
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from models import AribaInboundDelivery

logger = logging.getLogger(__name__)

def parse_date(date_val):
    if pd.isna(date_val):
        return None
    if isinstance(date_val, datetime):
        return date_val
    try:
        return pd.to_datetime(date_val).to_pydatetime()
    except Exception:
        return None

def sync_ariba_inbound_deliveries(db: Session, excel_path: str):
    """
    Reads the ZIBDSESREP.xlsx file and synchronizes Ariba Inbound Deliveries to the database.
    This provides visibility into material transit state (Dispatched vs Received) and 
    finance handover (Checklist Status).
    """
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        logger.error(f"Failed to read ARIBA Excel file {excel_path}: {e}")
        return False
        
    # Standardize columns to handle slight naming variations
    col_map = {
        'PO Number': 'po_number',
        'Item': 'item',
        'Material Number': 'material_number',
        'Material Description': 'material_description',
        'PO Quantity': 'po_quantity',
        'UoM': 'uom',
        'Company Code': 'company_code',
        'Vendor Code': 'vendor_code',
        'Vendor Name': 'vendor_name',
        'Inbound Delivery Quantity': 'inbound_delivery_quantity',
        'Rejected Quantity': 'rejected_quantity',
        'IBD Creation Date': 'ibd_creation_date',
        'Plant': 'plant',
        'GR posting date': 'gr_posting_date',
        'GRN Quantity': 'grn_quantity',
        'Currency': 'currency',
        'ARIBA Invoice date': 'ariba_invoice_date',
        'Checklist Number': 'checklist_number',
        'Checklist Status': 'checklist_status',
        'Checklist_Date': 'checklist_date'
    }
    
    # Rename columns that exist
    actual_cols = {}
    for c in df.columns:
        for k, v in col_map.items():
            if k.lower() in str(c).lower().strip():
                actual_cols[c] = v
                break
    
    df = df.rename(columns=actual_cols)
    
    records_added = 0
    
    # We clear the existing data or merge. Since this is an inbound delivery report, 
    # the best approach is usually to wipe and replace if the file contains the full snapshot.
    db.query(AribaInboundDelivery).delete()
    db.flush()
    
    for _, row in df.iterrows():
        po_num = str(row.get('po_number', '')).strip()
        if not po_num or po_num == 'nan':
            continue
            
        mat_desc = str(row.get('material_description', '')).strip()
        # Note: We explicitly do NOT filter out Solar Modules here. We want them tracked.
        
        def safe_float(val):
            try:
                return float(val) if pd.notna(val) else 0.0
            except Exception:
                return 0.0

        delivery = AribaInboundDelivery(
            po_number=po_num,
            item=str(row.get('item', '')).strip(),
            material_number=str(row.get('material_number', '')).strip(),
            material_description=mat_desc,
            po_quantity=safe_float(row.get('po_quantity')),
            uom=str(row.get('uom', '')).strip(),
            company_code=str(row.get('company_code', '')).strip(),
            vendor_code=str(row.get('vendor_code', '')).strip(),
            vendor_name=str(row.get('vendor_name', '')).strip(),
            inbound_delivery_quantity=safe_float(row.get('inbound_delivery_quantity')),
            rejected_quantity=safe_float(row.get('rejected_quantity')),
            ibd_creation_date=parse_date(row.get('ibd_creation_date')),
            plant=str(row.get('plant', '')).strip(),
            gr_posting_date=parse_date(row.get('gr_posting_date')),
            grn_quantity=safe_float(row.get('grn_quantity')),
            currency=str(row.get('currency', '')).strip(),
            ariba_invoice_date=parse_date(row.get('ariba_invoice_date')),
            checklist_number=str(row.get('checklist_number', '')).strip(),
            checklist_status=str(row.get('checklist_status', '')).strip(),
            checklist_date=parse_date(row.get('checklist_date'))
        )
        db.add(delivery)
        records_added += 1
        
    try:
        db.commit()
        logger.info(f"Successfully synced ARIBA Inbound Deliveries. Total records: {records_added}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing ARIBA data: {e}")
        return False
