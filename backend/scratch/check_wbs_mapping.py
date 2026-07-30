import os
import sys
import pandas as pd

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

from database import SessionLocal
import models

def check_wbs_mapping():
    file_path = os.path.join(os.path.dirname(backend_dir), "Data", "ZPSPS007.XLSX")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
        
    print(f"Reading {file_path}...")
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error reading excel: {e}")
        return
        
    print("Columns:", list(df.columns))
    
    # Try to find the WBS column
    wbs_col = None
    for col in df.columns:
        if 'wbs' in str(col).lower():
            wbs_col = col
            break
            
    if not wbs_col:
        print("Could not find a WBS column!")
        # Print a sample to help identify
        print(df.head(3).to_string())
        return
        
    print(f"Using WBS column: {wbs_col}")
    
    db = SessionLocal()
    try:
        # Load mappings
        mappings = db.query(models.ProjectMapping).all()
        spv_codes = {str(m.spv_plant_code).strip() for m in mappings if m.spv_plant_code}
        agel_codes = {str(m.agel).strip() for m in mappings if m.agel}
        age6l_codes = {str(m.age6l).strip() for m in mappings if m.age6l}
        
        # Create mapping from code to list of project names
        from collections import defaultdict
        code_to_projects = defaultdict(list)
        for m in mappings:
            proj_name = m.project or m.project_name_from_p6
            if m.spv_plant_code: code_to_projects[str(m.spv_plant_code).strip()].append(proj_name)
            if m.agel: code_to_projects[str(m.agel).strip()].append(proj_name)
            if m.age6l: code_to_projects[str(m.age6l).strip()].append(proj_name)
            
        match_stats = {
            'total_rows': len(df),
            'valid_wbs_rows': 0,
            'match_spv': 0,
            'match_agel': 0,
            'match_age6l': 0,
            'match_any': 0,
            'no_match': 0
        }
        
        unmatched_prefixes = set()
        matched_projects = set()
        
        for _, row in df.iterrows():
            wbs_val = str(row.get(wbs_col, '')).strip()
            if not wbs_val or wbs_val.lower() == 'nan':
                continue
                
            match_stats['valid_wbs_rows'] += 1
            
            # Take first 6 characters
            prefix = wbs_val[:6]
            
            matched = False
            
            if prefix in spv_codes:
                match_stats['match_spv'] += 1
                matched = True
            
            if prefix in agel_codes:
                match_stats['match_agel'] += 1
                matched = True
                
            if prefix in age6l_codes:
                match_stats['match_age6l'] += 1
                matched = True
                
            if matched:
                match_stats['match_any'] += 1
                matched_projects.update(code_to_projects[prefix])
            else:
                match_stats['no_match'] += 1
                unmatched_prefixes.add(prefix)
                
        print("\n--- MATCHING STATISTICS ---")
        print(f"Total Rows in Excel: {match_stats['total_rows']}")
        print(f"Rows with valid WBS: {match_stats['valid_wbs_rows']}")
        print(f"Matches found for SPV: {match_stats['match_spv']}")
        print(f"Matches found for AGEL: {match_stats['match_agel']}")
        print(f"Matches found for AGE6L: {match_stats['match_age6l']}")
        print(f"Total Rows Matched (Any of the 3): {match_stats['match_any']}")
        print(f"Total Rows UNMATCHED: {match_stats['no_match']}")
        print(f"\nTotal UNIQUE Projects Mapped to this Data: {len(matched_projects)} (out of {len(mappings)} total projects)")
        
        print("\nBreakdown of Match Counts by Prefix:")
        prefix_counts = {}
        for _, row in df.iterrows():
            wbs_val = str(row.get(wbs_col, '')).strip()
            if not wbs_val or wbs_val.lower() == 'nan': continue
            prefix = wbs_val[:6]
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
            
        for prefix, count in prefix_counts.items():
            mapped_projs = code_to_projects.get(prefix, [])
            print(f"Prefix '{prefix}': {count} rows in Excel, Maps to {len(mapped_projs)} projects. Examples: {mapped_projs[:3]}")
            
        print("\nSample of Unmatched WBS Prefixes (first 6 chars):")
        print(list(unmatched_prefixes)[:20])
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_wbs_mapping()
