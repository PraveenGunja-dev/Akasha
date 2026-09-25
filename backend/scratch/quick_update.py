import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import SessionLocal
from models import ProjectMapping

def main():
    db = SessionLocal()
    project_name = "ASEJ6PL_S07_FT_300MW_PPA"
    
    # Try searching by project, project_name_from_p6, project_id
    project = db.query(ProjectMapping).filter(ProjectMapping.project == project_name).first()
    if not project:
        project = db.query(ProjectMapping).filter(ProjectMapping.project_name_from_p6 == project_name).first()
    
    if project:
        print(f"Found project: {project.project} (P6: {project.project_name_from_p6}), old OL: {project.ol}, old type (source_of_origin): {project.source_of_origin}")
        
        project.ol = "1.36"
        project.source_of_origin = "China"
            
        if project.capacity_mwac is not None:
             project.capacity_mwdc = project.capacity_mwac * 1.36
                 
        db.commit()
        print("Updated successfully.")
    else:
        print("Project not found by exact name. Searching by contains...")
        projects = db.query(ProjectMapping).filter(ProjectMapping.project.like(f"%{project_name}%")).all()
        for p in projects:
            print(p.project)
        
        print("Searching P6 name by contains...")
        projects_p6 = db.query(ProjectMapping).filter(ProjectMapping.project_name_from_p6.like(f"%{project_name}%")).all()
        for p in projects_p6:
            print(p.project_name_from_p6)

if __name__ == "__main__":
    main()
