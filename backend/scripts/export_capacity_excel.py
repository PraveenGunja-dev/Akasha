import sys
import os
import pandas as pd
import re
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from models import MTTrialRun, ProjectMapping, P6Project

# Wind WTG MW multipliers keyed by p6_object_id
WIND_MW_PER_WTG = {
    "3074": 5.2,   # AGE25CL PSS-11 & PSS-14
    "4707": 5.0,   # AGE25CL PSS-18 Phase-4
    "3075": 5.2,   # AGE26AL PSS-12 & PSS-14
    "3076": 5.2,   # AHEJ5L PSS-05
    "3072": 5.2,   # ARE3L PSS-08
    "3073": 5.2,   # ASEJ6PL PSS-08
    "6733": 5.2,   # Demo DPR Wind
    "3105": 3.3,   # MANDVI
}
DEFAULT_WIND_MW = 3.3  # MUNDRA NORTH NEW etc.

def get_financial_year(date_obj):
    if not date_obj:
        return None
    year = date_obj.year
    month = date_obj.month
    if month >= 4:
        return f"FY{str(year)[-2:]}"
    else:
        return f"FY{str(year - 1)[-2:]}"


def export_excel():
    db = SessionLocal()
    
    # ---- SOURCE 1: ProjectMapping (ONLY for total project capacity) ----
    mappings = db.query(ProjectMapping).all()
    proj_info = {}
    for pm in mappings:
        name = pm.project_name_from_p6 or pm.project
        if name:
            proj_info[name] = {
                'project_id': pm.project_id or '-',
                'capacity': float(pm.capacity_mwac or 0)
            }
    
    # ---- SOURCE 2: P6Project (for wind p6_object_id lookup) ----
    p6_projs = db.query(P6Project).all()
    p6_obj_id_map = {p.name: str(p.p6_object_id) for p in p6_projs if p.name and p.p6_object_id}
    
    # ---- SOURCE 3: P6 (MTTrialRun) - ALL block/WTG level data ----
    milestones = db.query(MTTrialRun).all()
    
    # Step 1: Group every milestone row into unique blocks per project
    # Each unique project::block combination = 1 block or 1 WTG
    block_map = {}
    for m in milestones:
        p_name = m.project_name or m.project_name_p6 or "Unknown Project"
        b_name = m.project_name_block or "Unknown Block"
        b_key = f"{p_name}::{b_name}"
        
        cap = float(m.tr_quantity_mw or 0)  # MW for this block/WTG comes directly from P6
        activity = (m.activity_name or "").lower()
        is_cod = "cod" in activity  # catches both "COD" and "SCOD"
        is_tr = "trial" in activity
        is_solar = m.unit_of_measure == "Solar"
        p_type = 'Solar' if is_solar else 'Wind'
        actual_dt = m.trial_run_finish or m.trial_run_start
        
        if b_key not in block_map:
            block_map[b_key] = {
                "project": p_name,
                "block": b_name,
                "type": p_type,
                "capacity": cap,
                "has_tr": False,
                "has_cod": False,
                "tr_date": None,
                "cod_date": None
            }
            
        b = block_map[b_key]
        if cap > b["capacity"]:
            b["capacity"] = cap
            
        if is_cod and actual_dt:
            b["has_cod"] = True
            b["cod_date"] = actual_dt
        if is_tr and actual_dt:
            b["has_tr"] = True
            b["tr_date"] = actual_dt

    # Step 2: Aggregate blocks into project-level summary
    project_map = {}
    yearly_map = {}
    
    # Group blocks by project
    projects_blocks = {}
    for b_key, b in block_map.items():
        p_name = b["project"]
        if p_name not in projects_blocks:
            projects_blocks[p_name] = []
        projects_blocks[p_name].append(b)

    for p_name, blocks in projects_blocks.items():
        p_type = blocks[0]["type"]
        p_id = proj_info.get(p_name, {}).get('project_id', '-')
        
        # Sort blocks by name
        blocks.sort(key=lambda x: x["block"])
        
        # Calculate total capacity and block-level capacity
        if p_type == 'Solar':
            total_cap = proj_info.get(p_name, {}).get('capacity', 0)
            if total_cap == 0:
                match = re.search(r'(\d+(?:\.\d+)?)\s*MW', p_name, re.IGNORECASE)
                if match:
                    total_cap = float(match.group(1))
                    
            # Apply 12.5 MW logic for Solar blocks
            remaining_cap = total_cap
            for i, b in enumerate(blocks):
                if remaining_cap <= 0:
                    b["capacity"] = 0
                elif i == len(blocks) - 1:
                    b["capacity"] = round(remaining_cap, 2)
                    remaining_cap = 0
                else:
                    assigned = min(12.5, remaining_cap)
                    b["capacity"] = assigned
                    remaining_cap -= assigned
                    remaining_cap = round(remaining_cap, 2)
        else:
            obj_id = p6_obj_id_map.get(p_name)
            wtg_mw = WIND_MW_PER_WTG.get(obj_id, DEFAULT_WIND_MW)
            total_cap = len(blocks) * wtg_mw
            for b in blocks:
                b["capacity"] = wtg_mw
                
        project_map[p_name] = {
            'Project ID': p_id,
            'Project Name': p_name,
            'Type': p_type,
            'Total Capacity (MW)': total_cap,
            'Total Blocks/WTGs': 0,
            'Trial Run Only - Blocks/WTGs': 0,
            'Trial Run Only - MW': 0,
            'COD Done - Blocks/WTGs': 0,
            'COD Done - MW': 0,
            'Remaining Blocks/WTGs': 0,
            'Remaining Capacity (MW)': total_cap,
        }
        
        pm = project_map[p_name]
        
        for b in blocks:
            cap = b["capacity"]
            pm['Total Blocks/WTGs'] += 1
            
            # Categorize - COD takes priority over Trial Run
            if b["has_cod"]:
                pm['COD Done - Blocks/WTGs'] += 1
                pm['COD Done - MW'] += cap
                pm['Remaining Capacity (MW)'] -= cap
                
                if b["cod_date"]:
                    fy = get_financial_year(b["cod_date"])
                    if fy:
                        if fy not in yearly_map:
                            yearly_map[fy] = {'Financial Year': fy, 'Solar TR (MW)': 0, 'Wind TR (MW)': 0, 'Solar COD (MW)': 0, 'Wind COD (MW)': 0}
                        if p_type == 'Solar':
                            yearly_map[fy]['Solar COD (MW)'] += cap
                        else:
                            yearly_map[fy]['Wind COD (MW)'] += cap
                            
            elif b["has_tr"]:
                # Only count as Trial Run if NO COD exists for this block
                pm['Trial Run Only - Blocks/WTGs'] += 1
                pm['Trial Run Only - MW'] += cap
                pm['Remaining Capacity (MW)'] -= cap
                
                if b["tr_date"]:
                    fy = get_financial_year(b["tr_date"])
                    if fy:
                        if fy not in yearly_map:
                            yearly_map[fy] = {'Financial Year': fy, 'Solar TR (MW)': 0, 'Wind TR (MW)': 0, 'Solar COD (MW)': 0, 'Wind COD (MW)': 0}
                        if p_type == 'Solar':
                            yearly_map[fy]['Solar TR (MW)'] += cap
                        else:
                            yearly_map[fy]['Wind TR (MW)'] += cap

    # Post-processing: calculate remaining
    for p in project_map.values():
        p['Remaining Capacity (MW)'] = max(0, round(p['Remaining Capacity (MW)'], 2))
        p['Remaining Blocks/WTGs'] = p['Total Blocks/WTGs'] - p['COD Done - Blocks/WTGs'] - p['Trial Run Only - Blocks/WTGs']

    db.close()
    
    # Build Excel
    project_data = list(project_map.values())
    if project_data:
        totals_row = {
            'Project ID': 'TOTAL',
            'Project Name': '-',
            'Type': '-',
            'Total Capacity (MW)': sum(p['Total Capacity (MW)'] for p in project_data),
            'Total Blocks/WTGs': sum(p['Total Blocks/WTGs'] for p in project_data),
            'Trial Run Only - Blocks/WTGs': sum(p['Trial Run Only - Blocks/WTGs'] for p in project_data),
            'Trial Run Only - MW': sum(p['Trial Run Only - MW'] for p in project_data),
            'COD Done - Blocks/WTGs': sum(p['COD Done - Blocks/WTGs'] for p in project_data),
            'COD Done - MW': sum(p['COD Done - MW'] for p in project_data),
            'Remaining Blocks/WTGs': sum(p['Remaining Blocks/WTGs'] for p in project_data),
            'Remaining Capacity (MW)': sum(p['Remaining Capacity (MW)'] for p in project_data)
        }
        project_data.append(totals_row)

    df_projects = pd.DataFrame(project_data)
    
    yearly_data = list(yearly_map.values())
    yearly_data.sort(key=lambda x: x['Financial Year'])
    
    if yearly_data:
        totals_row_fy = {
            'Financial Year': 'TOTAL',
            'Solar TR (MW)': sum(y['Solar TR (MW)'] for y in yearly_data),
            'Wind TR (MW)': sum(y['Wind TR (MW)'] for y in yearly_data),
            'Solar COD (MW)': sum(y['Solar COD (MW)'] for y in yearly_data),
            'Wind COD (MW)': sum(y['Wind COD (MW)'] for y in yearly_data)
        }
        yearly_data.append(totals_row_fy)
        
    df_yearly = pd.DataFrame(yearly_data)

    output_path = os.path.join(os.path.dirname(__file__), 'Capacity_Report_v8.xlsx')
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df_projects.to_excel(writer, sheet_name='Project Breakdown', index=False)
        df_yearly.to_excel(writer, sheet_name='Yearly Totals', index=False)
        
    print(f"Excel report generated: {output_path}")

if __name__ == "__main__":
    export_excel()
