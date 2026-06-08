import os
import sys
import pandas as pd
import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

import models
from database import SessionLocal
from services.sharepoint_service import SharePointService

def safe_float(val):
    if pd.isna(val):
        return 0.0
    try:
        return float(str(val).replace(',', '').strip())
    except ValueError:
        return 0.0

def ingest_data():
    db = SessionLocal()
    
    print("Clearing old data...")
    db.query(models.MTInventory).delete()
    db.query(models.MTPOAmount).delete()
    db.query(models.MTInTransit).delete()
    db.commit()
    
    sp = SharePointService()
    files = sp.list_files_in_target_folder()
    
    download_dir = os.path.join(backend_dir, "downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    downloaded_files = {}
    for f in files:
        name = f['name']
        if name in ['MB52_Raw_Data.csv', 'ME2M_Raw_Data.csv', 'ZIBDSESREP.csv']:
            save_path = os.path.join(download_dir, name)
            if not os.path.exists(save_path):
                print(f"Downloading {name} from SharePoint...")
                sp.download_file(f['download_url'], save_path)
            else:
                print(f"Using local file {name}...")
            downloaded_files[name] = save_path
            
    # Process MB52 (Inventory)
    if 'MB52_Raw_Data.csv' in downloaded_files:
        try:
            print("Processing MB52_Raw_Data.csv...")
            df = pd.read_csv(downloaded_files['MB52_Raw_Data.csv'], low_memory=False).fillna(0)
            inventories = []
            for _, row in df.iterrows():
                unrestricted = safe_float(row.get('Unrestricted', 0))
                if unrestricted > 0:
                    inv = models.MTInventory(
                        material_code=str(row.get('Material', '')),
                        plant_code=str(row.get('Plant', '')),
                        quantity_inv=unrestricted,
                        storage_location_mapping=str(row.get('Storage Location', '')),
                        mw_multiplication_factor=1.0,
                        quantity_mw=unrestricted * 1.0,
                        company_code=str(row.get('Company Code', 'ADANI')),
                        wbs_element=str(row.get('WBS Element', '')).strip()
                    )
                    inventories.append(inv)
            db.add_all(inventories)
            db.commit()
            print(f"Inserted {len(inventories)} inventory records.")
        except Exception as e:
            db.rollback()
            print(f"Error processing MB52: {e}")
            
    # Process ME2M (PO Amount)
    if 'ME2M_Raw_Data.csv' in downloaded_files:
        try:
            print("Processing ME2M_Raw_Data.csv...")
            df = pd.read_csv(downloaded_files['ME2M_Raw_Data.csv'], low_memory=False).fillna(0)
            po_amounts = []
            seen_pos = set()
            for _, row in df.iterrows():
                po_doc = str(row.get('Purchasing Document', ''))
                qty = safe_float(row.get('Order Quantity', 0))
                if qty > 0 and po_doc and po_doc not in seen_pos:
                    seen_pos.add(po_doc)
                    po = models.MTPOAmount(
                        purchasing_document=po_doc,
                        plant_code=str(row.get('Plant', '')),
                        material_code=str(row.get('Material', '')),
                        vendor_name=str(row.get('Vendor/supplying plant', '')),
                        po_quantities=qty,
                        mw_multiplication_factor=1.0,
                        po_quantities_mw=qty * 1.0,
                        net_order_value=safe_float(row.get('Net Order Value', 0)),
                        company_code=str(row.get('Company Code', 'ADANI'))
                    )
                    po_amounts.append(po)
            db.add_all(po_amounts)
            db.commit()
            print(f"Inserted {len(po_amounts)} PO Amount records.")
        except Exception as e:
            db.rollback()
            print(f"Error processing ME2M: {e}")
            
    # Process ZIBDSESREP (In-Transit)
    if 'ZIBDSESREP.csv' in downloaded_files:
        try:
            print("Processing ZIBDSESREP.csv...")
            df = pd.read_csv(downloaded_files['ZIBDSESREP.csv'], low_memory=False).fillna(0)
            in_transits = []
            for _, row in df.iterrows():
                pending = safe_float(row.get('Inbound Delivery Quantity', 0))
                po_doc = str(row.get('PO Number', ''))
                if pending > 0:
                    transit = models.MTInTransit(
                        material_code=str(row.get('Material Number', '')),
                        plant_code=str(row.get('Plant', '')),
                        inbound_delivery_quantity=pending,
                        vendor_name=str(row.get('Vendor Name', '')),
                        po_number=po_doc,
                        mw_multiplication_factor=1.0,
                        quantity_mw=pending * 1.0,
                        wbs_element=str(row.get('WBS Element', '')).strip()
                    )
                    in_transits.append(transit)
            db.add_all(in_transits)
            db.commit()
            print(f"Inserted {len(in_transits)} In-Transit records.")
        except Exception as e:
            db.rollback()
            print(f"Error processing ZIBDSESREP: {e}")
            
    db.close()
    print("Ingestion complete!")

if __name__ == "__main__":
    ingest_data()
