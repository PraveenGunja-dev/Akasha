import os
import sys
import pandas as pd
import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

from database import SessionLocal, engine
import models

def build_wbs_mapping(master_path):
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
            'project_name': str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else '',
            'spv': str(row.iloc[2]).strip() if not pd.isna(row.iloc[2]) else '',
            'type': str(row.iloc[3]).strip() if not pd.isna(row.iloc[3]) else '',
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
    
    junk_keys = [k for k in wbs_map if len(k) < 3 or k in ('-', 'ACL', '50', '175')]
    for k in junk_keys:
        del wbs_map[k]
    
    return wbs_map

def match_wbs_to_master(wbs_val, wbs_map):
    if not wbs_val:
        return None
    wbs_str = str(wbs_val).strip().upper()
    wbs_str = wbs_str.replace('-', '')
    if wbs_str.startswith('H'):
        code_part = wbs_str[1:]
    else:
        code_part = wbs_str
    
    for length in range(min(len(code_part), 10), 2, -1):
        prefix = code_part[:length]
        if prefix in wbs_map:
            return wbs_map[prefix]
    return None

def ingest_slr():
    data_dir = os.path.join(os.path.dirname(backend_dir), "Data", "NEW31")
    file_path = os.path.join(data_dir, "ZPSPS007_merged.xlsx")
    master_path = os.path.join(data_dir, "AKASHA SAP MASTER FILE (2).xlsx")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
        
    print("Building WBS mapping from SAP Master...")
    wbs_map = build_wbs_mapping(master_path)
    print(f"  Loaded {len(wbs_map)} WBS codes from master.")
        
    print(f"Reading {file_path}...")
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error reading excel: {e}")
        return
        
    # Ensure table exists
    models.MTSLRData.__table__.create(bind=engine, checkfirst=True)
    
    db = SessionLocal()
    
    # Wipe old data
    print("Deleting old SLR data...")
    db.query(models.MTSLRData).delete()
    db.commit()
    
    print("Applying business logic filters & aggregations...")
    # 1. Filter out 'Summary' == 'X'
    if 'Summary' in df.columns:
        df = df[df['Summary'].isna() | (df['Summary'].astype(str).str.strip() == '') | (df['Summary'].astype(str).str.lower() == 'nan')]
    
    # 2. Extract types and ensure numeric amounts
    df['Commitment Amt'] = pd.to_numeric(df['Commitment Amt'], errors='coerce').fillna(0.0)
    df['Actual Amount'] = pd.to_numeric(df['Actual Amount'], errors='coerce').fillna(0.0)
    
    # 3. Filter out both zero
    df = df[(df['Commitment Amt'] != 0) | (df['Actual Amount'] != 0)]
    
    # Fix .0 issue in C.Document
    def clean_po(val):
        if pd.isna(val): return ''
        val_str = str(val).strip()
        if val_str.endswith('.0'):
            return val_str[:-2]
        return val_str
        
    df['C.Document'] = df['C.Document'].apply(clean_po)
    df['WBS Element'] = df['WBS Element'].fillna('').astype(str).str.strip()
    df['Type'] = df['Type'].fillna('').astype(str).str.strip()
    df['Description'] = df['Description'].fillna('').astype(str).str.strip()
    
    # 4. Filter out entire POs if ANY of their lines contain SPGS, PMC, ISA
    excluded_pos = df[df['Description'].str.contains('SPGS|PMC|ISA', case=False, na=False)]['C.Document'].unique()
    df = df[~df['C.Document'].isin(excluded_pos)]
    
    
    # Don't fillna('') yet for Vendor Name so that .agg('first') skips NaNs
    df['Vendor Name'] = df['Vendor Name'].replace(r'^\s*$', pd.NA, regex=True)
    
    print("Mapping WBS to SAP Master before aggregating...")
    def get_master_prefix(wbs_val):
        if not wbs_val or wbs_val.lower() == 'nan':
            return None
        wbs_str = str(wbs_val).strip().upper()
        wbs_str = wbs_str.replace('-', '')
        if wbs_str.startswith('H'):
            code_part = wbs_str[1:]
        else:
            code_part = wbs_str
        
        for length in range(min(len(code_part), 10), 2, -1):
            prefix = code_part[:length]
            if prefix in wbs_map:
                return prefix
        return None

    df['Matched_Prefix'] = df['WBS Element'].apply(get_master_prefix)
    
    # Drop rows that didn't match the master
    skipped_count = df['Matched_Prefix'].isna().sum()
    df = df.dropna(subset=['Matched_Prefix'])
    
    # 4. Group by C.Document, Matched_Prefix, Type to sum amounts
    agg_df = df.groupby(['C.Document', 'Matched_Prefix', 'Type'], as_index=False).agg({
        'Description': 'first',
        'Vendor Name': 'first',
        'WBS Element': 'first',
        'Commitment Amt': 'sum',
        'Actual Amount': 'sum'
    })
    
    slr_records = []
    
    print(f"Parsing {len(agg_df)} distinct aggregated records... (Skipped {skipped_count} raw rows due to no WBS match)")
    for _, row in agg_df.iterrows():
        po_doc = row['C.Document']
        if po_doc.lower() == 'nan': po_doc = ""
            
        desc = row['Description']
        if desc.lower() == 'nan': desc = ""
            
        vendor = row['Vendor Name']
        if pd.isna(vendor) or str(vendor).lower() == 'nan': vendor = ""
            
        type_val = row['Type']
        if type_val.lower() == 'nan': type_val = ""
        
        actual = row['Actual Amount']
        comm = row['Commitment Amt']
            
        record = models.MTSLRData(
            po_document=po_doc,
            description=desc,
            vendor_name=vendor,
            actual_amount=actual,
            commitment_amount=comm,
            wbs_element=row['WBS Element'],
            type=type_val,
            plant_code=row['Matched_Prefix']
        )
        slr_records.append(record)
        
    print(f"Bulk inserting {len(slr_records)} records...")
    
    BATCH_SIZE = 5000
    for i in range(0, len(slr_records), BATCH_SIZE):
        batch = slr_records[i:i + BATCH_SIZE]
        db.bulk_save_objects(batch)
        db.commit()
        
    db.close()
    
    print("Done!")

if __name__ == "__main__":
    ingest_slr()
