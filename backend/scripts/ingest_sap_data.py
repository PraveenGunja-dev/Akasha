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

def safe_str(val):
    """Return trimmed string or empty string for NaN/None."""
    if pd.isna(val):
        return ''
    return str(val).strip()

def safe_sap_id(val):
    """Return trimmed string without trailing .0 from pandas float parsing."""
    s = safe_str(val)
    if s.endswith('.0'):
        return s[:-2]
    return s

def safe_date(val):
    """Parse a date value, return None on failure."""
    try:
        dt = pd.to_datetime(val, errors='coerce')
        if pd.notna(dt):
            return dt.to_pydatetime()
    except Exception:
        pass
    return None

def build_wbs_mapping(master_path):
    """
    Read the AKASHA SAP MASTER FILE and build a lookup dict:
      wbs_code -> { project_name, spv, type, wbs_type }
    
    Extracts codes from columns:
      Col 4 (SPV WBS like H-6061), Col 5 (AGEL WBS), Col 6 (AGE6L WBS)
      Col 8 (SPV numeric), Col 9 (AGEL numeric), Col 10 (AGE6L numeric)
    """
    df = pd.read_excel(master_path)
    wbs_map = {}
    
    def extract_codes(val):
        codes = []
        if pd.isna(val):
            return codes
        val_str = str(val).strip()
        if val_str in ('Not Found', '-', 'None', ''):
            return codes
        parts = val_str.replace('\n', ' ').split()
        for part in parts:
            part = part.strip()
            if part.startswith('H-'):
                codes.append(part[2:].upper())
            elif part and part not in ('H-', '', 'H'):
                codes.append(part.upper())
        return codes
    
    for _, row in df.iterrows():
        info_base = {
            'project_name': safe_str(row.iloc[1]),
            'spv': safe_str(row.iloc[2]),
            'type': safe_str(row.iloc[3]),
        }
        
        # SPV WBS codes (col 4 & col 8)
        for code in extract_codes(row.iloc[4]) + extract_codes(row.iloc[8]):
            wbs_map[code] = {**info_base, 'wbs_type': 'SPV'}
        # AGEL WBS codes (col 5 & col 9)
        for code in extract_codes(row.iloc[5]) + extract_codes(row.iloc[9]):
            wbs_map[code] = {**info_base, 'wbs_type': 'AGEL'}
        # AGE6L WBS codes (col 6 & col 10)
        for code in extract_codes(row.iloc[6]) + extract_codes(row.iloc[10]):
            wbs_map[code] = {**info_base, 'wbs_type': 'AGE6L'}
    
    # Remove junk codes that are too short or obviously wrong
    junk_keys = [k for k in wbs_map if len(k) < 3 or k in ('-', 'ACL', '50', '175')]
    for k in junk_keys:
        del wbs_map[k]
    
    return wbs_map

def match_wbs_to_master(wbs_val, wbs_map):
    """
    Given a WBS element like 'H621R0503' or 'H-621R-05-03',
    normalise it to '621R0503' then check if it starts with
    any code in wbs_map (e.g., '621R').
    Returns the matched master info dict or None.
    """
    if not wbs_val:
        return None
    wbs_str = str(wbs_val).strip().upper()
    # Remove all dashes (handles H-621R-05-03 format)
    wbs_str = wbs_str.replace('-', '')
    if wbs_str.startswith('H'):
        code_part = wbs_str[1:]
    else:
        code_part = wbs_str
    
    # Try longest match first (some codes are 4 chars, some 5+)
    for length in range(min(len(code_part), 10), 2, -1):
        prefix = code_part[:length]
        if prefix in wbs_map:
            return wbs_map[prefix]
    return None


def ingest_data():
    db = SessionLocal()
    data_dir = os.path.join(os.path.dirname(backend_dir), "Data", "NEW31")
    master_path = os.path.join(data_dir, "AKASHA SAP MASTER FILE (2).xlsx")
    
    # ================================================================
    # Build WBS mapping from SAP Master
    # ================================================================
    print("Building WBS mapping from SAP Master...")
    wbs_map = build_wbs_mapping(master_path)
    print(f"  Loaded {len(wbs_map)} WBS codes from master.")

    # ================================================================def main():
    print("Connecting to database...")
    db = SessionLocal()
    
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "Data", "NEW31")
    
    # Pre-clear existing data
    print("Clearing old SAP data...")
    try:
        db.query(models.MTInventory).delete()
        db.query(models.MTPOAmount).delete()
        db.query(models.MTMaterialDocument).delete()
        db.query(models.MTEInvoicePOLookup).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error clearing old data: {e}")
    # ================================================================
    # Process MB52 (Inventory) — unchanged
    # ================================================================
    mb52_path = os.path.join(data_dir, "MB52_Khavda_Live_Inventry 2.xlsx")
    if os.path.exists(mb52_path):
        try:
            print(f"Processing {os.path.basename(mb52_path)}...")
            df = pd.read_excel(mb52_path)
            inventories = []
            for _, row in df.iterrows():
                mat_code = safe_sap_id(row.get('Material', ''))
                # Skip Total rows and empty rows
                if not mat_code or mat_code.lower() == 'nan' or 'total' in mat_code.lower():
                    continue
                    
                wbs = str(row.get('WBS_Element', '')).strip()
                if not wbs or wbs.lower() in ('nan', 'none'):
                    continue
                    
                # --- Match WBS to SAP Master ---
                master_info = match_wbs_to_master(wbs, wbs_map)
                if not master_info:
                    continue

                    
                unrestricted = safe_float(row.get('Unrestricted', 0))
                if unrestricted > 0:
                    inv = models.MTInventory(
                        material_code=mat_code,
                        material_name=str(row.get('Materail_Name', '')),
                        plant_code=str(row.get('Plant', '')),
                        unrestricted_qty=unrestricted,
                        value_unrestricted=safe_float(row.get('Value_Unrestricted', 0)),
                        quantity_inv=unrestricted,
                        storage_location_mapping=str(row.get('Storage_Location', '')),
                        wbs_element=wbs,
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

    # ================================================================
    # Process ZSPS (PO Amount) — Replacing ME2J, merging with ME2J metadata
    # ================================================================
    zsps_path = os.path.join(data_dir, "ZPSPS007_merged.xlsx")
    me2j_path = os.path.join(data_dir, "ME2J 2.xlsx")
    
    if os.path.exists(zsps_path):
        try:
            print(f"Processing {os.path.basename(zsps_path)}...")
            df = pd.read_excel(zsps_path)
            print(f"  Total rows read: {len(df)}")
            
            # Filter where C.Document is not null (has PO)
            df = df[df['C.Document'].notna()]
            
            # --- APPLY BUSINESS LOGIC FILTERS ---
            # 1. Summary should be blank (i.e. not 'X')
            if 'Summary' in df.columns:
                df = df[df['Summary'].isna() | (df['Summary'].astype(str).str.strip() == '') | (df['Summary'].astype(str).str.lower() == 'nan')]
            
            # 2. Type column should not be blank
            if 'Type' in df.columns:
                df = df[df['Type'].notna() & (df['Type'].astype(str).str.strip() != '') & (df['Type'].astype(str).str.lower() != 'nan')]
                
            # 3. Skip if both Commitment Amt and Actual Amount are 0
            comm_amt = pd.to_numeric(df['Commitment Amt'], errors='coerce').fillna(0.0)
            act_amt = pd.to_numeric(df['Actual Amount'], errors='coerce').fillna(0.0)
            df = df[(comm_amt != 0) | (act_amt != 0)]
            
            # 4. Exclude entire POs if Description contains SPGS, PMC, or ISA
            if 'Description' in df.columns:
                excluded_pos = df[df['Description'].astype(str).str.contains('SPGS|PMC|ISA', case=False, na=False)]['C.Document'].unique()
                df = df[~df['C.Document'].isin(excluded_pos)]
                
            print(f"  After applying all filters: {len(df)}")

            # --- Load ME2J for lookup mapping ---
            po_lookup = {}
            df_me2j = None
            if os.path.exists(me2j_path):
                print("  Loading ME2J for supplementary PO data (Buyer Name, Date, etc.)...")
                df_me2j = pd.read_excel(me2j_path, usecols=lambda c: c in [
                    'Purchasing Document', 'Buyer Name', 'Document Date', 
                    'Storage Location', 'Material', 'Plant', 'Currency', 'Delivery Completed',
                    'WBS Element'
                ])
                df_me2j = df_me2j.drop_duplicates(subset=['Purchasing Document'])
                # Convert to dict for fast lookup
                po_lookup = df_me2j.set_index('Purchasing Document').to_dict('index')
                print(f"  Loaded {len(po_lookup)} unique POs from ME2J.")
            else:
                print("  WARNING: Me2J 1.xlsx not found, supplementary data will be missing.")

            po_amounts = []
            skipped_no_wbs = 0
            skipped_no_match = 0
            
            for _, row in df.iterrows():
                po_doc = safe_sap_id(row.get('C.Document', ''))
                if not po_doc or po_doc.lower() == 'nan':
                    continue
                
                # ZSPS has 'WBS Element'
                wbs_el = safe_str(row.get('WBS Element', ''))
                    
                if not wbs_el or wbs_el.lower() in ('nan', 'none'):
                    skipped_no_wbs += 1
                    continue

                # --- Match WBS to SAP Master ---
                master_info = match_wbs_to_master(wbs_el, wbs_map)
                if not master_info:
                    skipped_no_match += 1
                    continue
                
                # --- Lookup supplementary ME2J Data ---
                # po_doc might be string, but the dict index might be float or int if parsed as numeric
                # We try both exact string and numeric cast
                po_doc_key = po_doc
                if po_doc_key not in po_lookup:
                    try:
                        po_doc_key = float(po_doc)
                    except ValueError:
                        pass
                
                me2j_data = po_lookup.get(po_doc_key, {})

                # --- Extract only required columns based on ZSPS ---
                qty = safe_float(row.get('C.Quantity', 0))
                del_qty = safe_float(row.get('A.Quantity', 0))
                still_qty = qty - del_qty if qty >= del_qty else 0
                
                # ZSPS provides Commitment Amt (Pending) and Actual Amount (Delivered)
                still_inr = safe_float(row.get('Commitment Amt', 0))
                del_val_inr = safe_float(row.get('Actual Amount', 0))
                net_value_inr = still_inr + del_val_inr
                
                del_val_cr = del_val_inr / 10000000

                po = models.MTPOAmount(
                    purchasing_document=po_doc,
                    wbs_element=wbs_el,
                    plant_code=safe_str(me2j_data.get('Plant', '')), 
                    material_code=safe_sap_id(me2j_data.get('Material', '')), 
                    material_name=safe_str(row.get('Description', '')),
                    vendor_name=safe_str(row.get('Vendor Name', '')),
                    short_text=safe_str(row.get('Short text', '')),
                    order_quantity=qty,
                    po_quantities=qty,
                    net_order_value=net_value_inr,
                    net_order_value_inr=net_value_inr,
                    still_to_deliver_qty=still_qty,
                    still_to_deliver_inr=still_inr,
                    delivered_qty=del_qty,
                    delivered_value_inr_cr=del_val_cr,
                    storage_location=safe_str(me2j_data.get('Storage Location', '')),
                    currency=safe_str(me2j_data.get('Currency', 'INR')),
                    buyer_name=safe_str(me2j_data.get('Buyer Name', '')),
                    delivery_completed_flag=safe_str(me2j_data.get('Delivery Completed', '')),
                    document_date=safe_date(me2j_data.get('Document Date')),
                )
                po_amounts.append(po)
            
            # Batch insert
            BATCH_SIZE = 5000
            total_inserted = 0
            for i in range(0, len(po_amounts), BATCH_SIZE):
                batch = po_amounts[i:i + BATCH_SIZE]
                db.add_all(batch)
                db.commit()
                total_inserted += len(batch)
                print(f"  Inserted batch {i // BATCH_SIZE + 1}: {len(batch)} records (total: {total_inserted})")
            
            print(f"  ZSPS Summary:")
            print(f"    Inserted: {total_inserted}")
            print(f"    Skipped (no WBS): {skipped_no_wbs}")
            print(f"    Skipped (WBS not in master): {skipped_no_match}")
            
        except Exception as e:
            db.rollback()
            print(f"Error processing ZSPS: {e}")
            import traceback
            traceback.print_exc()
            
        # ================================================================
        # Populate MTEInvoicePOLookup from BOTH ZSPS and ME2J
        # ================================================================
        print("Populating E-Invoice PO Lookup Table from ZSPS and ME2J...")
        try:
            lookup_records = {}
            
            # Extract from ME2J
            if df_me2j is not None:
                for _, row in df_me2j.iterrows():
                    po_doc = safe_sap_id(row.get('Purchasing Document', ''))
                    wbs_el = safe_str(row.get('WBS Element', ''))
                    if po_doc and wbs_el and wbs_el.lower() not in ('nan', 'none'):
                        lookup_records[po_doc] = wbs_el
            
            # Extract from ZSPS (overrides ME2J if conflict)
            for _, row in df.iterrows():
                po_doc = safe_sap_id(row.get('C.Document', ''))
                wbs_el = safe_str(row.get('WBS Element', ''))
                if po_doc and wbs_el and wbs_el.lower() not in ('nan', 'none'):
                    lookup_records[po_doc] = wbs_el
                    
            lookup_inserts = [
                models.MTEInvoicePOLookup(purchasing_document=po, wbs_element=wbs)
                for po, wbs in lookup_records.items()
            ]
            
            # Batch insert
            for i in range(0, len(lookup_inserts), BATCH_SIZE):
                batch = lookup_inserts[i:i + BATCH_SIZE]
                db.add_all(batch)
                db.commit()
                
            print(f"  Inserted {len(lookup_records)} unique PO -> WBS lookups for E-Invoice Mapping.")
        except Exception as e:
            db.rollback()
            print(f"Error populating E-Invoice PO Lookup: {e}")
            
    else:
        print(f"File not found: {zsps_path}")

    # ================================================================
    # Process MB51 (Material Documents/Consumption) — unchanged
    # ================================================================
    mb51_path = os.path.join(data_dir, "MB51_Khavda_Mat_Consumption_221_222 2.XLSX")
    if os.path.exists(mb51_path):
        try:
            print(f"Processing {os.path.basename(mb51_path)}...")
            df = pd.read_excel(mb51_path)
            material_docs = []
            for _, row in df.iterrows():
                doc = str(row.get('Material_Document', ''))
                mat_code = safe_sap_id(row.get('Material', ''))
                
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
                
                wbs_element = str(row.get('WBS_Element', '')).strip()
                if not wbs_element or wbs_element.lower() in ('nan', 'none'):
                    continue
                    
                # --- Match WBS to SAP Master ---
                master_info = match_wbs_to_master(wbs_element, wbs_map)
                if not master_info:
                    continue
                
                m_doc = models.MTMaterialDocument(
                    material_code=mat_code,
                    material_name=str(row.get('Material_Name', '')),
                    material_description=str(row.get('Material_Description', '')),
                    plant_code=str(row.get('Plant', '')),
                    movement_type=movement_type,
                    posting_date=posting_date_val,
                    quantity=qty,
                    material_document=doc,
                    wbs_element=wbs_element,
                    amount_in_lc=amt_lc,
                    amount_in_lc_cr=amt_lc / 10000000 if amt_lc != 0 else 0,
                    storage_location=str(row.get('Storage_Location', '')),
                    block_plot_name=str(row.get('Block_Plot_Name', '')),
                    purchase_order=safe_sap_id(row.get('Purchase_Order', '')),
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
