from database import SessionLocal
import models

def patch_wind_projects():
    db = SessionLocal()
    
    print("Checking existing wind projects...")
    
    # 1. Projects to Add / Ensure they exist as Wind
    projects_to_add = [
        {
            "project": "Wind - AGE25CL PSS-18 (49 Loc.) - Phase-4",
            "project_name_from_p6": "AGE25CL (PH-4)",
            "project_id": "AGE25CL (PH-4)",
            "category": "Wind",
            "module_wbs": "Wind",
            "mms_type": "Wind",
            "spv_name": "AGE25CL Phase-4"
        },
        {
            "project": "Wind - MUNDRA NORTH-NEW",
            "project_name_from_p6": "MNW - B3",
            "project_id": "MNW - B3",
            "category": "Wind",
            "module_wbs": "Wind",
            "mms_type": "Wind",
            "spv_name": "MUNDRA NORTH-NEW"
        }
    ]
    
    for p_data in projects_to_add:
        existing = db.query(models.ProjectMapping).filter_by(project_name_from_p6=p_data["project_name_from_p6"]).first()
        if not existing:
            new_mapping = models.ProjectMapping(**p_data)
            db.add(new_mapping)
            print(f"[+] Added new Wind project mapping: {p_data['project_name_from_p6']}")
        else:
            # Update existing to ensure it is marked as Wind
            existing.category = "Wind"
            existing.module_wbs = "Wind"
            existing.mms_type = "Wind"
            print(f"[~] Updated existing mapping to Wind: {p_data['project_name_from_p6']}")

    # 2. Project to Remove (MUNDRA NORTH-OLD / MNW)
    old_mnw = db.query(models.ProjectMapping).filter_by(project_name_from_p6="MNW").first()
    if old_mnw:
        db.delete(old_mnw)
        print("[-] Removed old project mapping: MNW (MUNDRA NORTH-OLD)")
    else:
        print("[ ] MNW (MUNDRA NORTH-OLD) was not mapped, nothing to remove.")

    db.commit()
    print("\nDatabase patching complete!")

if __name__ == "__main__":
    patch_wind_projects()
