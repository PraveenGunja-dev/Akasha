import os
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal
from models import ProjectMapping, P6Project

db = SessionLocal()

try:
    db.execute(text("ALTER TABLE project_mapping ADD COLUMN IF NOT EXISTS is_commissioned BOOLEAN DEFAULT FALSE;"))
    db.commit()
except Exception as e:
    print("Column might already exist:", e)
    db.rollback()

mappings = db.query(ProjectMapping).all()
updated = 0
for mapping in mappings:
    # Find matching P6 project for progress
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
print(f"Updated {updated} project mappings.")
db.close()
