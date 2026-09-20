import sys
import os
import re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from database import SessionLocal
import models

def ingest_mapping():
    db = SessionLocal()
    mapping_file_old = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "Project_Name_Master.xlsx")
    mapping_file_new = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "NEW31", "AKASHA SAP MASTER FILE (2).xlsx")
    
    try:
        # Create table if not exists
        models.Base.metadata.create_all(bind=db.get_bind())

        print(f"Reading new mapping {mapping_file_new}...")
        df_new = pd.read_excel(mapping_file_new)

        print(f"Reading old mapping {mapping_file_old}...")
        df_old = pd.read_excel(mapping_file_old)

        print("Merging mapping data...")
        # Normalize the join keys first - the old master file has leading/trailing
        # whitespace on ~half its 'Project ID' values, which makes an exact-string
        # merge silently miss those rows (capacity, WBS, category, etc. all come
        # from this file and were showing up blank/0 for every affected project).
        df_new['P6 ID'] = df_new['P6 ID'].astype(str).str.strip()
        df_old['Project ID'] = df_old['Project ID'].astype(str).str.strip()
        df = pd.merge(df_new, df_old, left_on='P6 ID', right_on='Project ID', how='left').fillna("")

        def parse_float(val):
            try:
                return float(str(val).strip())
            except ValueError:
                return 0.0

        def parse_date(val):
            if pd.isna(val) or str(val).strip() == '':
                return None
            try:
                return pd.to_datetime(val)
            except Exception:
                return None

        def parse_p6_name(name):
            if not name:
                return {}
            # e.g. ARE55L_A15b_HSAT_50MW_PPA or ARE55L_S01_HSAT_100_MW_PPA
            mms_match = re.search(r'_(HSAT|FT)_', name, re.IGNORECASE)
            cap_match = re.search(r'_(\d+(?:\.\d+)?)\s*_?MW', name, re.IGNORECASE)
            
            parsed = {}
            if mms_match:
                parsed['mms_type'] = mms_match.group(1).upper()
                parts = name[:mms_match.start()].split('_', 1)
                if len(parts) > 1:
                    parsed['plot_no'] = parts[1]
                    
            if cap_match:
                parsed['capacity_mwac'] = float(cap_match.group(1))
                trailer = name[cap_match.end():].strip('_')
                if trailer:
                    if 'PPA' in trailer.upper(): parsed['category'] = 'PPA'
                    elif 'MERCHANT' in trailer.upper(): parsed['category'] = 'Merchant'
                    elif 'GROUP' in trailer.upper(): parsed['category'] = 'Group'
                    
                    trailer_parts = trailer.split('_')
                    # Guess EPC if the last part is not a common keyword
                    if trailer_parts[-1].upper() not in ('PPA', 'MERCHANT', 'GROUP', 'NEW', 'COMMISSIONED', 'HYBRID', 'T4', 'AP', 'LTP'):
                        parsed['subcluster'] = trailer_parts[-1]
            return parsed

        # Upsert keyed on the stable P6 project id, instead of delete-all +
        # re-insert. project_mapping.id is a FK target for transmission data
        # (tc_network_edge.mapping_id, tc_project_entry.mapping_id) — recreating
        # rows with fresh ids on every re-ingest silently orphans that data.
        existing_by_pid = {m.project_id: m for m in db.query(models.ProjectMapping).all()}
        seen_pids = set()
        mappings = []

        for _, row in df.iterrows():
            project_id = str(row.get('P6 ID', '')).strip()
            if not project_id:  # Removed plant_code check since some projects don't have it
                continue
            seen_pids.add(project_id)

            project = str(row.get('Project', '')).strip()
            project_name_from_p6 = str(row.get('Project Name', '')).strip()
            if not project:
                project = project_name_from_p6

            parsed_p6 = parse_p6_name(project_name_from_p6)

            cap_ac = parse_float(row.get('Capacity\n(MWac)', ''))
            if not cap_ac:
                cap_ac = parsed_p6.get('capacity_mwac', 0.0)
                
            plot_no = str(row.get('Plot No', '')).strip()
            if not plot_no: plot_no = parsed_p6.get('plot_no', '')
            
            mms_type = str(row.get('MMS Type', '')).strip()
            if not mms_type: mms_type = parsed_p6.get('mms_type', '')
            
            cat = str(row.get('Category', '')).strip()
            if not cat: cat = parsed_p6.get('category', '')
            
            epc = str(row.get('Type (Cluster)', '')).strip()
            if not epc: epc = parsed_p6.get('subcluster', '')

            raw_lta_date = row.get('ECOD')
            lta_date = parse_date(raw_lta_date)

            fields = dict(
                project=project,
                spv_name=str(row.get('SPV', '')).strip(),
                project_id=project_id,
                project_name_from_p6=project_name_from_p6,
                plot_no=plot_no,
                category=cat,
                mms_type=mms_type,
                capacity_mwac=cap_ac,
                ol=str(row.get('OL', '')).strip(),
                capacity_mwdc=parse_float(row.get('Capacity (MWdc)', '')),
                spv_plant_code=str(row.get('SPV.1', '')).strip(),
                agel=str(row.get('AGEL', '')).strip(),
                module_wbs=str(row.get('Module WBS', '')).strip(),
                age6l=str(row.get('AGE6L', '')).strip(),
                cluster=epc,  # Used as subcluster previously, storing as cluster? Wait...
                # Actually, the DB column is 'subcluster'. Let's ensure we map it to subcluster.
                subcluster=epc,
                not_allocated=str(row.get('Not Allocated', '')).strip(),
                priority=str(row.get('Priority', '')).strip(),
                source_of_origin=str(row.get('SourceOfOrigin', '')).strip(),
                lta_date=lta_date,
            )

            if project_id in existing_by_pid:
                mapping = existing_by_pid[project_id]
                for k, v in fields.items():
                    setattr(mapping, k, v)
            else:
                mapping = models.ProjectMapping(**fields)
                db.add(mapping)

            mappings.append(mapping)

        # Projects that dropped out of the source file: unlink any transmission
        # data pointing at them before removing the now-stale mapping row.
        stale = [m for pid, m in existing_by_pid.items() if pid not in seen_pids]
        for m in stale:
            db.query(models.TcProjectEntry).filter(models.TcProjectEntry.mapping_id == m.id).update({"mapping_id": None})
            db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id == m.id).update({"mapping_id": None})
            db.delete(m)

        db.commit()

        if stale:
            print(f"Removed {len(stale)} stale mapping(s) no longer present in source file.")

        # Now automatically calculate the commissioned flag
        from models import P6Project
        updated = 0
        for mapping in mappings:
            p6 = db.query(P6Project).filter(P6Project.project_id == mapping.project_id).first()
            prog_val = 0
            if p6 and p6.duration_percent_complete is not None:
                progress = p6.duration_percent_complete
                if isinstance(progress, str) and '%' in progress:
                    try:
                        prog_val = float(progress.replace('%', ''))
                    except: pass
                else:
                    try:
                        prog_val = float(progress)
                    except: pass
            proj_str = str(mapping.project).lower() if mapping.project else ''
            p6_proj_str = str(mapping.project_name_from_p6).lower() if mapping.project_name_from_p6 else ''
            is_comm = ('commission' in proj_str or 'commension' in proj_str or 
                       'commission' in p6_proj_str or 'commension' in p6_proj_str or 
                       prog_val >= 99 or (0.99 <= prog_val <= 1.0))
            mapping.is_commissioned = is_comm
            updated += 1
            
        db.commit()
        print(f"Successfully ingested {len(mappings)} project mappings (set {updated} commission flags)!")
        
    except Exception as e:
        db.rollback()
        print(f"Error ingesting mapping: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    ingest_mapping()
