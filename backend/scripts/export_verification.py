import sys
import os
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from models import MTTrialRun, ProjectMapping, P6Project

# Wind MW per WTG multipliers
WIND_MW_PER_WTG = {
    "3074": 5.2, "4707": 5.0, "3075": 5.2, "3076": 5.2,
    "3072": 5.2, "3073": 5.2, "6733": 5.2, "3105": 3.3,
}
DEFAULT_WIND_MW = 3.3

def export_verification():
    db = SessionLocal()

    # Fetch ProjectMapping for total capacity (solar)
    mappings = db.query(ProjectMapping).all()
    proj_info = {}
    for pm in mappings:
        name = pm.project_name_from_p6 or pm.project
        if name:
            proj_info[name] = {
                'project_id': pm.project_id or '-',
                'capacity': float(pm.capacity_mwac or 0)
            }

    # P6Project for wind object IDs
    p6_projs = db.query(P6Project).all()
    p6_obj_id_map = {p.name: str(p.p6_object_id) for p in p6_projs if p.name and p.p6_object_id}

    # All milestones from P6
    milestones = db.query(MTTrialRun).all()

    # Group into blocks
    block_map = {}
    for m in milestones:
        p_name = m.project_name or m.project_name_p6 or "Unknown"
        b_name = m.project_name_block or "Unknown"
        b_key = f"{p_name}::{b_name}"

        cap = float(m.tr_quantity_mw or 0)
        activity = (m.activity_name or "").lower()
        is_cod = "cod" in activity
        is_tr = "trial" in activity
        is_solar = m.unit_of_measure == "Solar"
        p_type = 'Solar' if is_solar else 'Wind'

        if b_key not in block_map:
            block_map[b_key] = {
                "project": p_name,
                "block": b_name,
                "type": p_type,
                "mw": cap,
                "tr_start": None,
                "tr_finish": None,
                "cod_start": None,
                "cod_finish": None,
            }

        b = block_map[b_key]
        if cap > b["mw"]:
            b["mw"] = cap

        if is_tr:
            b["tr_start"] = m.trial_run_start
            b["tr_finish"] = m.trial_run_finish
        if is_cod:
            b["cod_start"] = m.trial_run_start
            b["cod_finish"] = m.trial_run_finish

    db.close()

    # Build rows grouped by project
    rows = []
    projects = {}
    for b_key, b in block_map.items():
        p_name = b["project"]
        if p_name not in projects:
            projects[p_name] = []
        projects[p_name].append(b)

    # Sort projects by name
    for p_name in sorted(projects.keys()):
        blocks = projects[p_name]
        p_type = blocks[0]["type"]

        # Sort blocks by name to ensure consistent order
        blocks.sort(key=lambda x: x["block"])

        # Get total capacity
        import re
        if p_type == 'Solar':
            total_cap = proj_info.get(p_name, {}).get('capacity', 0)
            if total_cap == 0:
                match = re.search(r'(\d+(?:\.\d+)?)\s*MW', p_name, re.IGNORECASE)
                if match:
                    total_cap = float(match.group(1))
            
            # Apply 12.5 MW logic for Solar:
            # Each block takes 12.5 MW, last block takes the remainder.
            remaining_cap = total_cap
            for i, b in enumerate(blocks):
                if remaining_cap <= 0:
                    b["mw"] = 0
                elif i == len(blocks) - 1:
                    b["mw"] = round(remaining_cap, 2)
                    remaining_cap = 0
                else:
                    assigned = min(12.5, remaining_cap)
                    b["mw"] = assigned
                    remaining_cap -= assigned
                    remaining_cap = round(remaining_cap, 2)
        else:
            obj_id = p6_obj_id_map.get(p_name)
            wtg_mw = WIND_MW_PER_WTG.get(obj_id, DEFAULT_WIND_MW)
            total_cap = len(blocks) * wtg_mw
            # For Wind, capacity per block is the MW of one WTG
            for b in blocks:
                b["mw"] = wtg_mw

        p_id = proj_info.get(p_name, {}).get('project_id', '-')

        cod_blocks = 0
        cod_mw = 0
        tr_blocks = 0
        tr_mw = 0

        for b in blocks:
            has_cod = b["cod_start"] is not None or b["cod_finish"] is not None
            has_tr = b["tr_start"] is not None or b["tr_finish"] is not None

            # Determine status using strict logic
            if has_cod:
                status = "COD"
                cod_blocks += 1
                cod_mw += b["mw"]
            elif has_tr:
                status = "Trial Run"
                tr_blocks += 1
                tr_mw += b["mw"]
            else:
                status = "Pending"

            rows.append({
                'Project ID': p_id,
                'Project Name': p_name,
                'Type': p_type,
                'Block/WTG': b["block"],
                'MW': b["mw"],
                'Status': status,
                'Trial Run Start': b["tr_start"].strftime("%Y-%m-%d") if b["tr_start"] else '-',
                'Trial Run Finish': b["tr_finish"].strftime("%Y-%m-%d") if b["tr_finish"] else '-',
                'COD Start': b["cod_start"].strftime("%Y-%m-%d") if b["cod_start"] else '-',
                'COD Finish': b["cod_finish"].strftime("%Y-%m-%d") if b["cod_finish"] else '-',
            })

        remaining = max(0, total_cap - cod_mw - tr_mw)

        # Add project total row
        rows.append({
            'Project ID': '',
            'Project Name': f'>>> TOTAL: {p_name}',
            'Type': p_type,
            'Block/WTG': f'{len(blocks)} blocks/WTGs',
            'MW': total_cap,
            'Status': f'COD: {cod_blocks} ({cod_mw:.1f} MW) | TR: {tr_blocks} ({tr_mw:.1f} MW) | Remaining: {remaining:.1f} MW',
            'Trial Run Start': '',
            'Trial Run Finish': '',
            'COD Start': '',
            'COD Finish': '',
        })

        # Add empty separator row
        rows.append({k: '' for k in rows[0].keys()})

    df = pd.DataFrame(rows)
    output_path = os.path.join(os.path.dirname(__file__), 'Verification_Report.xlsx')

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Block-Level Verification', index=False)

        # Auto-adjust column widths
        ws = writer.sheets['Block-Level Verification']
        for col_idx, col in enumerate(df.columns, 1):
            max_len = max(len(str(col)), df[col].astype(str).str.len().max())
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 50)

    print(f"Verification report generated: {output_path}")

if __name__ == "__main__":
    export_verification()
