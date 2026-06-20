import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import ProjectMapping
from sqlalchemy import func

def deduplicate():
    db = SessionLocal()
    try:
        # Get all mappings
        mappings = db.query(ProjectMapping).all()
        
        # Group by project_name_from_p6
        grouped = {}
        for m in mappings:
            key = m.project_name_from_p6
            if not key:
                continue
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(m)
            
        for p6_name, group in grouped.items():
            if len(group) > 1:
                print(f"Found {len(group)} duplicates for P6 Project: {p6_name}")
                
                # Keep the first one, merge the others
                master = group[0]
                tc_projects = set()
                if master.project:
                    tc_projects.update([p.strip() for p in master.project.split(',') if p.strip()])
                    
                for duplicate in group[1:]:
                    if duplicate.project:
                        tc_projects.update([p.strip() for p in duplicate.project.split(',') if p.strip()])
                    # delete duplicate
                    db.delete(duplicate)
                    
                master.project = ", ".join(tc_projects)
                print(f"Merged TC projects into: {master.project}")
                
        db.commit()
        print("Deduplication complete.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    deduplicate()
