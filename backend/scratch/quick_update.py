import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import SessionLocal
from models import ProjectMapping

def main():
    db = SessionLocal()
    project_name = "ASEJ6PL_S07_FT_300MW_PPA"
    project = db.query(ProjectMapping).filter(ProjectMapping.project_name == project_name).first()
    
    if project:
        print(f"Found project: {project.project_name}, old OL: {getattr(project, 'ol', None)}, old type: {getattr(project, 'type', None)}")
        
        if hasattr(project, 'ol'):
            project.ol = 1.36
        if hasattr(project, 'type'):
            project.type = "China"
            
        if hasattr(project, 'capacity_mwac') and getattr(project, 'capacity_mwac', None) is not None:
             if hasattr(project, 'capacity_mwdc'):
                 project.capacity_mwdc = project.capacity_mwac * 1.36
                 
        db.commit()
        print("Updated successfully.")
    else:
        print("Project not found by exact name. Searching by contains...")
        projects = db.query(ProjectMapping).filter(ProjectMapping.project_name.like(f"%{project_name}%")).all()
        for p in projects:
            print(p.project_name)

if __name__ == "__main__":
    main()
