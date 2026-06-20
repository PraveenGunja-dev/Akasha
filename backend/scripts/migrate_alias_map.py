import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import ProjectMapping

ALIAS_MAP = {
    "MLP T1  PPA - J&K": "MLP T1 J&K",
    "MLP T1  PPA - CG": "MLP T1 CG",
    "MLP T1  PPA - TN": "MLP T1 TN",
    "MLP T1  PPA - OR": "MLP T1 OR",
    "MLP T3 PPA - AP": "MLP T3 AP",
    "MLP  PPA - AP New": "MLP AP New",
    "Group - Cement (Hybrid - Solar)": "ACL",
    "AGEL Hybrid Merchant (Wind)": "AGEL Hybrid Merchant",
    "AESL PPA (C&I) - Asahi, Wilmar, Airport": "AESL PPA (C&I) - Solar",
    "AESL PPA (C&I) - Asahi, Wilmar, Airport, Shantigram": "AESL PPA (C&I) - Solar",
    "AESL PPA (C&I) - Asahi, Wilmar, Nestle": "AESL PPA (C&I) - Solar",
    "AESL PPA (C&I) - Asahi, Wilmar,Nestle": "AESL PPA (C&I) - Solar",
    "AESL PPA (C&I) - Wind - RSWM": "AESL PPA (C&I) - Solar"
}

def migrate_aliases():
    db = SessionLocal()
    try:
        added_count = 0
        for transmission_name, global_project_name in ALIAS_MAP.items():
            # Check if mapping already exists
            existing = db.query(ProjectMapping).filter(ProjectMapping.project == transmission_name).first()
            if not existing:
                # We map the transmission_name to the 'project' field (which acts as the TC/Transmission name)
                # We'll map the global_project_name to 'project_name_from_p6' or as another mapping key
                # Actually, in the old logic: target = ALIAS_MAP[name]; q = db.query(ProjectMapping).filter(ProjectMapping.project == target)
                # This means ALIAS_MAP maps a new name -> existing mapping's name.
                # Let's find the target mapping
                
                target_mapping = db.query(ProjectMapping).filter(ProjectMapping.project == global_project_name).first()
                if target_mapping:
                    # Create a duplicate mapping for the alias
                    new_mapping = ProjectMapping(
                        project=transmission_name,
                        spv_name=target_mapping.spv_name,
                        project_id=target_mapping.project_id,
                        project_name_from_p6=target_mapping.project_name_from_p6,
                        plot_no=target_mapping.plot_no,
                        category=target_mapping.category,
                        mms_type=target_mapping.mms_type,
                        capacity_mwac=target_mapping.capacity_mwac,
                        ol=target_mapping.ol,
                        capacity_mwdc=target_mapping.capacity_mwdc,
                        spv_plant_code=target_mapping.spv_plant_code,
                        agel=target_mapping.agel,
                        module_wbs=target_mapping.module_wbs,
                        age6l=target_mapping.age6l,
                        cluster=target_mapping.cluster,
                        not_allocated=target_mapping.not_allocated,
                        source_of_origin=target_mapping.source_of_origin,
                        priority=target_mapping.priority
                    )
                    db.add(new_mapping)
                    added_count += 1
                    print(f"Migrated alias: {transmission_name} -> {global_project_name}")
                else:
                    # Target doesn't exist, just create a new empty one mapping the names
                    new_mapping = ProjectMapping(
                        project=transmission_name,
                        project_name_from_p6=global_project_name
                    )
                    db.add(new_mapping)
                    added_count += 1
                    print(f"Created bare alias: {transmission_name} -> {global_project_name}")
            else:
                print(f"Alias already exists in DB: {transmission_name}")
                
        db.commit()
        print(f"Successfully added {added_count} new mappings from ALIAS_MAP.")
    except Exception as e:
        print(f"Error during migration: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_aliases()
