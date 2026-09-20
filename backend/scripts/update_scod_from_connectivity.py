import sys
import os
import pandas as pd
from datetime import datetime
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
import models

def normalize(name):
    if pd.isna(name) or name is None:
        return ""
    # Remove non-alphanumeric, convert to lower
    return re.sub(r'[^a-z0-9]', '', str(name).lower())

def fuzzy_match(db_mappings, project_val, spv_val, solar_cap, wind_cap):
    # Try to find best match
    norm_proj = normalize(project_val)
    norm_spv = normalize(spv_val)
    
    candidates = []
    for m in db_mappings:
        db_proj = normalize(m.project)
        db_p6 = normalize(m.project_name_from_p6)
        db_spv = normalize(m.spv_name)
        
        score = 0
        
        # Name match
        if norm_proj and (norm_proj in db_proj or norm_proj in db_p6 or db_proj in norm_proj or db_p6 in norm_proj):
            score += 10
        elif norm_proj == db_proj or norm_proj == db_p6:
            score += 20
            
        # SPV match
        if norm_spv and (norm_spv in db_spv or db_spv in norm_spv):
            score += 5
            
        # Capacity match (Solar)
        if pd.notna(solar_cap):
            try:
                cap_float = float(solar_cap)
                db_cap_ac = float(m.capacity_mwac or 0)
                db_cap_dc = float(m.capacity_mwdc or 0)
                
                if cap_float > 0:
                    if abs(cap_float - db_cap_ac) < 1 or abs(cap_float - db_cap_dc) < 1:
                        score += 8
            except ValueError:
                pass
                
        if score >= 10:
            candidates.append((score, m))
            
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None

def main():
    db = SessionLocal()
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "20260904_Connectivity_r1Share.xlsx")
    
    print(f"Reading {file_path}")
    try:
        # Use header=2 because the actual column names are on row 3 of the excel sheet
        df = pd.read_excel(file_path, header=2)
    except Exception as e:
        print(f"Failed to read excel: {e}")
        return
        
    print(f"Columns: {df.columns.tolist()}")
    mappings = db.query(models.ProjectMapping).all()
    updated_count = 0
    missing = []
    
    for idx, row in df.iterrows():
        project = row.get('Project')
        spv = row.get('SPV')
        solar_cap = row.get('Solar')
        wind_cap = row.get('Wind')
        scod_val = row.get('SCOD')
        
        if idx < 5:
            print(f"Row {idx}: Project={project}, SCOD={scod_val}")
            
        if pd.isna(project) or str(project).strip() == '':
            continue
            
        if pd.isna(scod_val) or str(scod_val).strip() == '' or str(scod_val) == 'nan' or str(scod_val) == 'NaT':
            continue
            
        match = fuzzy_match(mappings, project, spv, solar_cap, wind_cap)
        if not match:
            missing.append(f"Project: {project} | SPV: {spv} | Solar: {solar_cap}")
            continue
            
        scod_date = None
        
        is_lta = False
        # 1. Try parsing as a standard date
        try:
            scod_date = pd.to_datetime(scod_val)
        except Exception:
            # 2. If it's a string like "LTA + 30D" or "LTA", parse it relative to lta_date
            scod_str = str(scod_val).upper().strip()
            if 'LTA' in scod_str and match.lta_date:
                is_lta = True
                import re
                from datetime import timedelta
                m = re.search(r'LTA\s*([+-])\s*(\d+)', scod_str)
                if m:
                    sign = 1 if m.group(1) == '+' else -1
                    days = int(m.group(2))
                    scod_date = match.lta_date + timedelta(days=sign * days)
                else:
                    # Just 'LTA' with no offset
                    scod_date = match.lta_date

        if scod_date:
            match.manual_scod = scod_date
            match.manual_scod_is_lta = is_lta
            updated_count += 1
            
    db.commit()
    print(f"Updated {updated_count} records with SCOD dates.")
    if missing:
        print(f"Could not find matching projects for {len(missing)} rows:")
        for m in missing[:10]:
            print(f" - {m}")
        if len(missing) > 10:
            print(" ... and more.")

if __name__ == "__main__":
    main()
