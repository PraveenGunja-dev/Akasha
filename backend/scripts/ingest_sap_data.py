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
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', ''):
        return 0.0
    s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return 0.0

def ingest_data():
    db = SessionLocal()
    
    print("Clearing old data...")
    db.query(models.MTInventory).delete()
    db.query(models.MTPOAmount).delete()
    db.query(models.MTInTransit).delete()
    db.query(models.MTMaterialDocument).delete()
    db.commit()
    
    data_dir = os.path.join(os.path.dirname(backend_dir), "Data")
    
    # Process MB52 (Inventory) from Local
    mb52_path = os.path.join(data_dir, "MB52_Khavda_Live_Inventry - Copy (1).xlsx")
    if os.path.exists(mb52_path):
        try:
            print(f"Processing {os.path.basename(mb52_path)}...")
            df = pd.read_excel(mb52_path)
            inventories = []
            for _, row in df.iterrows():
                unrestricted = safe_float(row.get('Unrestricted', 0))
                if unrestricted > 0:
                    inv = models.MTInventory(
                        material_code=str(row.get('Material', '')),
                        material_name=str(row.get('Materail_Name', '')),
                        plant_code=str(row.get('Plant', '')),
                        unrestricted_qty=unrestricted,
                        value_unrestricted=safe_float(row.get('Value_Unrestricted', 0)),
                        quantity_inv=unrestricted,
                        storage_location_mapping=str(row.get('Storage_Location', '')),
                        wbs_element=str(row.get('WBS_Element', '')).strip(),
                        material_description=str(row.get('Material_Description', ''))
                    )
                    inventories.append(inv)
            db.add_all(inventories)
            db.commit()
            print(f"Inserted {len(inventories)} MB52 inventory records.")
        except Exception as e:
            db.rollback()
            print(f"Error processing MB52: {e}")
    else:
        print(f"File not found: {mb52_path}")

    # Process ME2M (PO Amount) from Local
    me2m_path = os.path.join(data_dir, "ME2M_Khavda_Po_List 3.XLSX")
    if os.path.exists(me2m_path):
        try:
            print(f"Processing {os.path.basename(me2m_path)}...")
            df = pd.read_excel(me2m_path)
            po_amounts = []
            for _, row in df.iterrows():
                po_doc = str(row.get('Purchasing_Document', ''))
                qty = safe_float(row.get('Order_Quantity', 0))
                if po_doc and po_doc.lower() != 'nan':
                    po = models.MTPOAmount(
                        purchasing_document=po_doc,
                        plant_code=str(row.get('Plant', '')),
                        material_code=str(row.get('Material', '')),
                        material_name=str(row.get('Materail_Name', '')),
                        vendor_name=str(row.get('Vendor_Name', '')),
                        short_text=str(row.get('Short_Text', '')),
                        order_quantity=qty,
                        po_quantities=qty,  # Legacy field
                        net_order_value=safe_float(row.get('Net_Order_Value_IN_INR_Cr', 0)) * 10000000,
                        net_order_value_inr=safe_float(row.get('Net_Order_Value_IN_INR_Cr', 0)) * 10000000,
                        still_to_deliver_qty=safe_float(row.get('Still_to_be_delivered_qty_', 0)),
                        still_to_deliver_inr=safe_float(row.get('Still_to_be_delivered_IN_INR_Cr', 0)) * 10000000,
                        delivered_qty=safe_float(row.get('Delivered_QTY', 0)),
                        delivered_value_inr_cr=safe_float(row.get('Delivered_Value_IN_Cr', 0)),
                        storage_location=str(row.get('Storage_Location', '')),
                        block_plot_name=str(row.get('Block_Plot_Name', '')),
                        currency=str(row.get('Currency', ''))
                    )
                    po_amounts.append(po)
            db.add_all(po_amounts)
            db.commit()
            print(f"Inserted {len(po_amounts)} ME2M PO Amount records.")
        except Exception as e:
            db.rollback()
            print(f"Error processing ME2M: {e}")
    else:
        print(f"File not found: {me2m_path}")

    # Process MB51 (Material Documents/Consumption) from Local
    mb51_path = os.path.join(data_dir, "MB51_Khavda_Mat_Consumption_221_222 2 (2).XLSX")
    if os.path.exists(mb51_path):
        try:
            print(f"Processing {os.path.basename(mb51_path)}...")
            df = pd.read_excel(mb51_path)
            material_docs = []
            for _, row in df.iterrows():
                doc = str(row.get('Material_Document', ''))
                if doc and doc.lower() != 'nan':
                    p_date = pd.to_datetime(row.get('Posting_Date'), errors='coerce')
                    posting_date_val = p_date.to_pydatetime() if pd.notna(p_date) else None
                    
                    m_doc = models.MTMaterialDocument(
                        material_code=str(row.get('Material', '')),
                        material_name=str(row.get('Material_Name', '')),
                        material_description=str(row.get('Material_Description', '')),
                        plant_code=str(row.get('Plant', '')),
                        movement_type=str(row.get('Movement_Type', '')),
                        posting_date=posting_date_val,
                        quantity=safe_float(row.get('Quantity', 0)),
                        material_document=doc,
                        wbs_element=str(row.get('WBS_Element', '')).strip(),
                        amount_in_lc=safe_float(row.get('Amount_in_LC', 0)),
                        amount_in_lc_cr=safe_float(row.get('Amount_in_LC_in_CR', 0)),
                        storage_location=str(row.get('Storage_Location', '')),
                        block_plot_name=str(row.get('Block_Plot_Name', '')),
                        purchase_order=str(row.get('Purchase_Order', '')),
                        base_unit=str(row.get('Base_Unit_of_Measure', ''))
                    )
                    material_docs.append(m_doc)
            db.add_all(material_docs)
            db.commit()
            print(f"Inserted {len(material_docs)} MB51 Material Document records.")
        except Exception as e:
            db.rollback()
            print(f"Error processing MB51: {e}")
    else:
        print(f"File not found: {mb51_path}")

    # Process ZIBDSESREP (In-Transit) from SharePoint
    try:
        sp = SharePointService()
        files = sp.list_files_in_target_folder()
        download_dir = os.path.join(backend_dir, "downloads")
        os.makedirs(download_dir, exist_ok=True)
        
        zib_file = next((f for f in files if f['name'] == 'ZIBDSESREP.csv'), None)
        if zib_file:
            save_path = os.path.join(download_dir, 'ZIBDSESREP.csv')
            if not os.path.exists(save_path):
                print("Downloading ZIBDSESREP.csv from SharePoint...")
                sp.download_file(zib_file['download_url'], save_path)
            
            print("Processing ZIBDSESREP.csv...")
            df = pd.read_csv(save_path, low_memory=False).fillna(0)
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
                        wbs_element=str(row.get('WBS Element', '')).strip()
                    )
                    in_transits.append(transit)
            db.add_all(in_transits)
            db.commit()
            print(f"Inserted {len(in_transits)} ZIBDSESREP In-Transit records.")
    except Exception as e:
        print(f"Error processing SharePoint ZIBDSESREP: {e}")

    db.close()
    print("Ingestion complete!")

if __name__ == "__main__":
    ingest_data()
