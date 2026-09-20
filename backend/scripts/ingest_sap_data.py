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
from sqlalchemy import func

# The SAP extracts land here — both the local Data/NEW31 drop and the SharePoint
# sync write into it. Names carry copy suffixes ("ZPSPS0071", "ME2J 2") depending
# on who exported them, so each extract is matched by pattern and the newest
# file wins rather than a single hardcoded name.
import re
import glob
SAP_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "19_09")
SAP_FILE_PATTERNS = {
    "zsps": re.compile(r"^ZPSPS007.*\.xlsx?$", re.I),
    "me2j": re.compile(r"^ME2J.*\.xlsx?$", re.I),
    "mb52": re.compile(r"^MB52_Khavda_Live_Inventry.*\.xlsx?$", re.I),
    "mb51": re.compile(r"^MB51_Khavda_Mat_Consumption.*\.xlsx?$", re.I),
}

# Everything the ingest reads from ME2J. The first line is what mt_poamount
# borrows per PO; the rest feeds mt_me2j_po (ownership and lifecycle).
ME2J_COLUMNS = [
    'Purchasing Document', 'Buyer Name', 'Document Date', 'Storage Location', 'Material', 'Plant', 'Currency', 'Delivery Completed', 'WBS Element',
    'Name of Vendor', 'Buyer Email ID', 'PR Creator Name', 'PR First Release Date', 'PO First Time Full Release Date',
    'PO Latest Full Release Date', 'Release indicator', 'Release status', 'Validity Period End', 'Amendment Number',
    'Amendment Date', 'Purchasing Doc. Type', 'Incoterms', 'Reason Description',
]


def ingest_me2j_po(db, df_me2j):
    """Replace mt_me2j_po from a PO-deduplicated ME2J frame. Same transaction
    pattern as the PO table: delete and insert together, commit once."""
    from auto_migrate import auto_upgrade_schema
    auto_upgrade_schema()
    rows = []
    for _, r in df_me2j.iterrows():
        po = safe_sap_id(r.get('Purchasing Document', ''))
        if not po or po.lower() == 'nan':
            continue
        amend = pd.to_numeric(r.get('Amendment Number'), errors='coerce')
        rows.append(models.MTME2JPO(
            purchasing_document=po,
            vendor_name=safe_str(r.get('Name of Vendor', '')) or None,
            buyer_name=safe_str(r.get('Buyer Name', '')) or None,
            buyer_email=safe_str(r.get('Buyer Email ID', '')) or None,
            pr_creator=safe_str(r.get('PR Creator Name', '')) or None,
            pr_first_release=safe_date(r.get('PR First Release Date')),
            po_first_release=safe_date(r.get('PO First Time Full Release Date')),
            po_latest_release=safe_date(r.get('PO Latest Full Release Date')),
            release_indicator=safe_str(r.get('Release indicator', '')) or None,
            release_status=safe_str(r.get('Release status', '')) or None,
            validity_end=safe_date(r.get('Validity Period End')),
            amendment_no=int(amend) if pd.notna(amend) else None,
            amendment_date=safe_date(r.get('Amendment Date')),
            doc_type=safe_str(r.get('Purchasing Doc. Type', '')) or None,
            incoterms=safe_str(r.get('Incoterms', '')) or None,
            reason=safe_str(r.get('Reason Description', '')) or None,
            document_date=safe_date(r.get('Document Date')),
        ))
    try:
        db.query(models.MTME2JPO).delete()
        for i in range(0, len(rows), 5000):
            db.add_all(rows[i:i + 5000])
        db.commit()
        print(f"  Inserted {len(rows)} ME2J PO ownership rows.")
    except Exception:
        db.rollback()
        raise


def find_sap_file(key: str, data_dir: str = SAP_DATA_DIR):
    """Newest file in data_dir matching the extract's pattern, or None."""
    pat = SAP_FILE_PATTERNS[key]
    hits = [f for f in glob.glob(os.path.join(data_dir, "*")) if pat.match(os.path.basename(f))]
    if not hits:
        return None
    best = max(hits, key=os.path.getmtime)
    if len(hits) > 1:
        print(f"  {key}: {len(hits)} candidates, using newest {os.path.basename(best)}")
    return best

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
        val_str = safe_sap_id(val)
        if val_str.lower() in ('not found', '-', 'none', '', 'nan'):
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


def ingest_data(files=None, max_drop_pct=15.0, allow_drop=False):
    """files: optional {key: path} overriding the newest-file lookup, e.g.
    {'zsps': '.../ZPSPS0071.xlsx'} to load a specific extract.

    max_drop_pct / allow_drop guard the PO table: see services/sync_guard.py.
    A collapsed extract raises before anything is deleted, so the previous
    (good) data stays live and the sync is logged as failed, not silently
    accepted."""
    files = files or {}
    pick = lambda key, d: files.get(key) or find_sap_file(key, d)
    from auto_migrate import auto_upgrade_schema
    auto_upgrade_schema()
    from services.sync_guard import check_snapshot
    db = SessionLocal()
    data_dir = os.path.join(os.path.dirname(backend_dir), "Data", "19_09")
    master_path = os.path.join(data_dir, "AKASHA SAP MASTER FILE (1) 1.xlsx")
    
    # ================================================================
    # Build WBS mapping from SAP Master
    # ================================================================
    print("Building WBS mapping from SAP Master...")
    wbs_map = build_wbs_mapping(master_path)
    print(f"  Loaded {len(wbs_map)} WBS codes from master.")

    # ================================================================def main():
    print("Connecting to database...")
    db = SessionLocal()
    
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "Data", "19_09")
    
    # MTPOAmount / MTEInvoicePOLookup are no longer pre-cleared here: their
    # delete now happens inside the ZSPS block's own transaction, guarded and
    # atomic with the insert. MTInventory / MTMaterialDocument keep the
    # simple clear-then-load pattern for now (see services/sync_guard.py for
    # why a guard was added to the PO table specifically).
    print("Clearing old inventory/consumption data...")
    try:
        db.query(models.MTInventory).delete()
        db.query(models.MTMaterialDocument).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error clearing old data: {e}")
    # ================================================================
    # Process MB52 (Inventory) — unchanged
    # ================================================================
    mb52_path = pick("mb52", data_dir)
    if mb52_path and os.path.exists(mb52_path):
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
    zsps_path = pick("zsps", data_dir)
    me2j_path = pick("me2j", data_dir)
    
    if zsps_path and os.path.exists(zsps_path):
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
            
            # 2. Purchase orders only. mt_poamount is the PO table; a PReq is a
            #    requisition, not an order, and counting it overstated PO value
            #    by Rs 3,769 Cr. Requisitions stay available in mt_slr_data.
            if 'Type' in df.columns:
                df = df[df['Type'].astype(str).str.strip() == 'POrd']
                
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
            if me2j_path and os.path.exists(me2j_path):
                print("  Loading ME2J for supplementary PO data (Buyer Name, Date, etc.)...")
                df_me2j = pd.read_excel(me2j_path, usecols=lambda c: c in ME2J_COLUMNS)
                df_me2j = df_me2j.drop_duplicates(subset=['Purchasing Document'])
                ingest_me2j_po(db, df_me2j)
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
                    doc_type=safe_str(row.get('Type', '')) or None,
                )
                po_amounts.append(po)

            # --- Guard: is this a plausible successor to what is live now? ---
            # The 20 Aug -> 16 Sep incident (BESS cluster silently dropped,
            # Rs 11,850 Cr / 307 POs) is exactly what this catches. Checked
            # before any delete, so a collapsed extract leaves old data intact.
            new_count = len({po.purchasing_document for po in po_amounts})
            new_value_cr = sum(po.net_order_value_inr or 0 for po in po_amounts) / 10000000
            old_row = db.query(
                func.count(func.distinct(models.MTPOAmount.purchasing_document)),
                func.sum(models.MTPOAmount.net_order_value_inr),
            ).filter(models.MTPOAmount.doc_type == 'POrd').first()
            old_count = old_row[0] or 0
            old_value_cr = (old_row[1] or 0) / 10000000
            guard = check_snapshot("ZSPS PO", old_count, new_count, old_value_cr, new_value_cr, max_drop_pct)
            print(f"  Snapshot check: live {old_count} POs / Rs {old_value_cr:,.0f} Cr -> "
                  f"new {new_count} POs / Rs {new_value_cr:,.0f} Cr")
            if not guard.ok and not allow_drop:
                raise RuntimeError(guard.reason)
            if not guard.ok and allow_drop:
                print(f"  WARNING: {guard.reason}")
                print("  Proceeding anyway (allow_drop=True).")

            # Delete + insert in the SAME transaction: if anything below
            # raises, the rollback restores the pre-existing PO data instead
            # of leaving the table cleared.
            db.query(models.MTPOAmount).delete()

            BATCH_SIZE = 5000
            total_inserted = 0
            for i in range(0, len(po_amounts), BATCH_SIZE):
                batch = po_amounts[i:i + BATCH_SIZE]
                db.add_all(batch)
                total_inserted += len(batch)
            db.commit()
            print(f"  Inserted {total_inserted} ZSPS PO records (single transaction).")

            print(f"  ZSPS Summary:")
            print(f"    Inserted: {total_inserted}")
            print(f"    Skipped (no WBS): {skipped_no_wbs}")
            print(f"    Skipped (WBS not in master): {skipped_no_match}")
            
        except Exception as e:
            db.rollback()
            print(f"Error processing ZSPS: {e}")
            import traceback
            traceback.print_exc()
            raise
            
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

            # Same transaction as the delete, same reasoning as the PO table above.
            db.query(models.MTEInvoicePOLookup).delete()
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
    mb51_path = pick("mb51", data_dir)
    if mb51_path and os.path.exists(mb51_path):
        try:
            print(f"Processing {os.path.basename(mb51_path)}...")
            df = pd.read_excel(mb51_path)
            # Standardize column names since the new file uses spaces instead of underscores
            if hasattr(df.columns, 'str'):
                df.columns = df.columns.str.replace(' ', '_')
            
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
    import argparse
    ap = argparse.ArgumentParser(description="Refresh SAP data. Default: pull today's extracts from SharePoint, then ingest.")
    ap.add_argument("--local", action="store_true", help="skip SharePoint; ingest whatever is already in Data/NEW31")
    ap.add_argument("--zsps", metavar="PATH", help="with --local: use this ZPSPS007 file instead of the newest one")
    ap.add_argument("--max-drop-pct", type=float, default=15.0, metavar="PCT",
                     help="refuse the replace if PO count or value falls more than this vs. what is live now (default 15)")
    ap.add_argument("--allow-drop", action="store_true",
                     help="proceed even if the new extract collapses vs. current data (use when the drop is real, e.g. a portfolio closed out)")
    args = ap.parse_args()
    if args.local:
        from database import SessionLocal
        from services.sap_sync import sync_sap_from_local
        r = sync_sap_from_local(SessionLocal(), zsps_path=args.zsps,
                                 max_drop_pct=args.max_drop_pct, allow_drop=args.allow_drop)
        print()
        print(r['message'])
        print(f"Data as on {r['data_as_on']}  |  files: {', '.join(f['name'] for f in r['files'])}")
    else:
        from database import SessionLocal
        from services.sap_sync import sync_sap_from_sharepoint
        r = sync_sap_from_sharepoint(SessionLocal(), max_drop_pct=args.max_drop_pct, allow_drop=args.allow_drop)
        print()
        print(r['message'])
        print(f"Data as on {r['data_as_on']}  |  files: {', '.join(f['name'] for f in r['files'])}")
