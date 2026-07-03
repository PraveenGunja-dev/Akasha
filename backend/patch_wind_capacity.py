from database import SessionLocal
import models
import re

def update_wind_capacity():
    db = SessionLocal()
    mappings = db.query(models.ProjectMapping).filter(models.ProjectMapping.category == 'Wind').all()
    
    for m in mappings:
        if not m.project_id:
            continue
            
        p6 = db.query(models.P6Project).filter(models.P6Project.project_id == m.project_id).first()
        if p6:
            wtgs = db.query(models.P6Activity).filter(
                models.P6Activity.project_object_id == p6.p6_object_id,
                models.P6Activity.name.ilike('%wtg%')
            ).all()
            
            unique_wtgs = set()
            for w in wtgs:
                match = re.search(r'WTG\s*(\d+)', w.name, re.IGNORECASE)
                if match:
                    unique_wtgs.add(int(match.group(1)))
            
            wtg_count = len(unique_wtgs)
            if wtg_count > 0:
                # Calculate capacity (5.2 MW per WTG)
                calculated_capacity = wtg_count * 5.2
                
                print(f"Project {m.project_name_from_p6}: Found {wtg_count} WTGs. Old Capacity: {m.capacity_mwac} MW -> New Capacity: {calculated_capacity} MW")
                
                # Update the mapping
                m.capacity_mwac = calculated_capacity
                
                # Update progress based on WTG completion if needed? Or overall activity?
                # Actually, let's just update capacity first.
                
    db.commit()
    print("Wind Capacities Updated Successfully!")

if __name__ == "__main__":
    update_wind_capacity()
