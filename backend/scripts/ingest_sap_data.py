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

    # Process ME2K (PO Amount) from Local
    me2k_path = os.path.join(data_dir, "ME2K (1).xlsx")
    if os.path.exists(me2k_path):
        try:
            print(f"Processing {os.path.basename(me2k_path)}...")
            df = pd.read_excel(me2k_path)
            po_amounts = []
            for _, row in df.iterrows():
                po_doc = str(row.get('Purchasing Document', ''))
                qty = safe_float(row.get('Order Quantity', 0))
                if po_doc and po_doc.lower() != 'nan':
                    # Support user adding Net_Order_Value_IN_INR_Cr column
                    net_order_value_cr = safe_float(row.get('Net_Order_Value_IN_INR_Cr', 0))
                    
                    still_qty = safe_float(row.get('Still to be delivered (qty)', 0))
                    still_inr = safe_float(row.get('Still to be delivered in INR', 0))
                    
                    # Robust calculation of Net Order Value
                    if net_order_value_cr > 0:
                        net_value_inr = net_order_value_cr * 10000000
                    else:
                        # Compute using unit price
                        if still_qty > 0 and still_inr > 0:
                            unit_price = still_inr / still_qty
                        else:
                            # Fallback if no pending items: use Net price
                            unit_price = safe_float(row.get('Net Price in INR', safe_float(row.get('Net price', 0))))
                        net_value_inr = qty * unit_price

                    del_qty = qty - still_qty if qty >= still_qty else 0
                    del_val_inr = net_value_inr - still_inr if net_value_inr >= still_inr else 0
                    del_val_cr = del_val_inr / 10000000

                    po = models.MTPOAmount(
                        purchasing_document=po_doc,
                        wbs_element=str(row.get('WBS Element', '')).strip(),
                        plant_code=str(row.get('Plant', '')),
                        material_code=str(row.get('Material', '')),
                        material_name=str(row.get('Short Text', '')),
                        vendor_name=str(row.get('Name of Vendor', '')),
                        short_text=str(row.get('Short Text', '')),
                        order_quantity=qty,
                        po_quantities=qty,  # Legacy field
                        net_order_value=net_value_inr,
                        net_order_value_inr=net_value_inr,
                        still_to_deliver_qty=still_qty,
                        still_to_deliver_inr=still_inr,
                        delivered_qty=del_qty,
                        delivered_value_inr_cr=del_val_cr,
                        storage_location=str(row.get('Storage Location', '')),
                        block_plot_name=str(row.get('Block_Plot_Name', '')),
                        currency=str(row.get('Currency', ''))
                    )
                    po_amounts.append(po)
            db.add_all(po_amounts)
            db.commit()
            print(f"Inserted {len(po_amounts)} ME2K PO Amount records.")
        except Exception as e:
            db.rollback()
            print(f"Error processing ME2K: {e}")
    else:
        print(f"File not found: {me2k_path}")

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

    # ZIBDSESREP ingestion removed as requested.

    db.close()
    print("Ingestion complete!")

if __name__ == "__main__":
    ingest_data()
