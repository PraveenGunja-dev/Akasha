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

def safe_float(val):
    if pd.isna(val):
        return 0.0
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', ''):
        return 0.0
    s = s.replace(',', '')
    # Handle SAP negative sign trailing like '100.00-'
    if s.endswith('-'):
        s = '-' + s[:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0

def ingest_data():
    db = SessionLocal()
    
    print("Clearing old data...")
    db.query(models.MTInventory).delete()
    db.query(models.MTPOAmount).delete()
    db.query(models.MTMaterialDocument).delete()
    db.commit()
    
    data_dir = os.path.join(os.path.dirname(backend_dir), "Data")
    
    # Process MB52 (Inventory) from Local
    mb52_path = os.path.join(data_dir, "MB52_Khavda_Live_Inventry 1.xlsx")
    if not os.path.exists(mb52_path):
        mb52_path = os.path.join(data_dir, "MB52_Khavda_Live_Inventry - Copy (1).xlsx")
    
    if os.path.exists(mb52_path):
        try:
            print(f"Processing {os.path.basename(mb52_path)}...")
            df = pd.read_excel(mb52_path)
            inventories = []
            for _, row in df.iterrows():
                mat_code = str(row.get('Material', '')).strip()
                # Skip Total rows and empty rows
                if not mat_code or mat_code.lower() == 'nan' or 'total' in mat_code.lower():
                    continue
                    
                unrestricted = safe_float(row.get('Unrestricted', 0))
                val_unrestricted = safe_float(row.get('Value_Unrestricted', 0))
                if unrestricted > 0 or val_unrestricted > 0:
                    inv = models.MTInventory(
                        material_code=mat_code,
                        material_name=str(row.get('Materail_Name', row.get('Material_Name', ''))),
                        plant_code=str(row.get('Plant', '')),
                        unrestricted_qty=unrestricted,
                        value_unrestricted=val_unrestricted,
                        quantity_inv=unrestricted,
                        storage_location_mapping=str(row.get('Storage_Location', '')),
                        wbs_element=str(row.get('WBS_Element', '')).strip(),
                        material_description=str(row.get('Material_Description', '')),
                        base_unit=str(row.get('Base_Unit_of_Measure', ''))
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

    # Process ME2J (PO Amount)
    me2j_path = os.path.join(data_dir, "Me2J 1.xlsx")
    if not os.path.exists(me2j_path):
        me2j_path = os.path.join(data_dir, "ME2J.XLSX")
        
    if os.path.exists(me2j_path):
        try:
            print(f"Processing {os.path.basename(me2j_path)}...")
            df = pd.read_excel(me2j_path)
            
            # Filter: we need to use blank ones only in 'Statistical' column
            if 'Statistical' in df.columns:
                df = df[df['Statistical'].isna() | (df['Statistical'].astype(str).str.strip() == '') | (df['Statistical'].astype(str).str.lower() == 'nan')]

            po_amounts = []
            for _, row in df.iterrows():
                po_doc = str(row.get('Purchasing Document', ''))
                qty = safe_float(row.get('Order Quantity', 0))
                
                if po_doc and po_doc.lower() != 'nan':
                    wbs_el = str(row.get('WBS Element', '')).strip()
                    if not wbs_el or wbs_el.lower() == 'nan':
                        # Fallback to 'WBS element' if column capitalization differs
                        wbs_el = str(row.get('WBS element', '')).strip()

                    still_qty = safe_float(row.get('Still to be delivered (qty)', 0))
                    
                    # Use "PO Pending Value in Local Currency" for pending amount, or fallback to 'Still to be delivered (value)'
                    still_inr = safe_float(row.get('PO Pending Value in Local Currency', 0))
                    if still_inr == 0:
                        still_inr = safe_float(row.get('Still to be delivered (value)', 0))
                    
                    # Target value / overall value in INR using "PO Value in Local Currency"
                    net_value_inr = safe_float(row.get('PO Value in Local Currency', 0))
                    if net_value_inr == 0:
                        net_value_inr = safe_float(row.get('Net Order Value', 0))

                    del_qty = qty - still_qty if qty >= still_qty else 0
                    del_val_inr = net_value_inr - still_inr if net_value_inr >= still_inr else 0
                    del_val_cr = del_val_inr / 10000000

                    po = models.MTPOAmount(
                        purchasing_document=po_doc,
                        wbs_element=wbs_el,
                        plant_code=str(row.get('Plant', '')),
                        material_code=str(row.get('Material', '')),
                        material_name=str(row.get('Short Text', '')), # Material name/description
                        vendor_name=str(row.get('Name of Vendor', row.get('Vendor/supplying plant', ''))),
                        short_text=str(row.get('Short Text', '')),
                        order_quantity=qty,
                        po_quantities=qty,
                        net_order_value=net_value_inr,
                        net_order_value_inr=net_value_inr,
                        still_to_deliver_qty=still_qty,
                        still_to_deliver_inr=still_inr,
                        delivered_qty=del_qty,
                        delivered_value_inr_cr=del_val_cr,
                        storage_location=str(row.get('Storage Location', '')),
                        currency=str(row.get('Currency', '')),
                        buyer_name=str(row.get('Buyer Name', '')),
                        delivery_completed_flag=str(row.get('Delivery Completed', '')),
                        document_date=pd.to_datetime(row.get('Document Date'), errors='coerce').to_pydatetime() if pd.notna(pd.to_datetime(row.get('Document Date'), errors='coerce')) else None
                    )
                    po_amounts.append(po)
            db.add_all(po_amounts)
            db.commit()
            print(f"Inserted {len(po_amounts)} ME2J PO Amount records.")
        except Exception as e:
            db.rollback()
            print(f"Error processing ME2J: {e}")
    else:
        print(f"File not found: {me2j_path}")

    # Process MB51 (Material Documents/Consumption) from Local
    mb51_path = os.path.join(data_dir, "MB51_Khavda_Mat_Consumption_221_222 1.XLSX")
    if not os.path.exists(mb51_path):
        mb51_path = os.path.join(data_dir, "MB51_Khavda_Mat_Consumption_221_222 2 (2).XLSX")
    if os.path.exists(mb51_path):
        try:
            print(f"Processing {os.path.basename(mb51_path)}...")
            df = pd.read_excel(mb51_path)
            material_docs = []
            for _, row in df.iterrows():
                doc = str(row.get('Material_Document', ''))
                mat_code = str(row.get('Material', '')).strip()
                
                # Skip Total rows and invalid entries
                if not doc or doc.lower() == 'nan' or 'total' in mat_code.lower():
                    continue
                    
                p_date = pd.to_datetime(row.get('Posting_Date'), errors='coerce')
                posting_date_val = p_date.to_pydatetime() if pd.notna(p_date) else None
                
                movement_type = str(row.get('Movement_Type', '')).strip()
                
                # STRICT LOGIC: Only allow consumption (221) and reversals (222)
                if movement_type not in ['221', '222', '261', '262']:
                    continue
                
                qty = safe_float(row.get('Quantity', 0))
                amt_lc = safe_float(row.get('Amount_in_LC', 0))
                
                m_doc = models.MTMaterialDocument(
                    material_code=mat_code,
                    material_name=str(row.get('Material_Name', '')),
                    material_description=str(row.get('Material_Description', '')),
                    plant_code=str(row.get('Plant', '')),
                    movement_type=movement_type,
                    posting_date=posting_date_val,
                    quantity=qty,
                    material_document=doc,
                    wbs_element=str(row.get('WBS_Element', '')).strip(),
                    amount_in_lc=amt_lc,
                    amount_in_lc_cr=amt_lc / 10000000 if amt_lc != 0 else 0,
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

    db.close()
    print("Ingestion complete!")

if __name__ == "__main__":
    ingest_data()
