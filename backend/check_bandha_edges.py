import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
import models
from routers.dashboard import get_dashboard_summary

db = SessionLocal()
data = get_dashboard_summary(nocache=True, db=db)
projects = data.get('projects', [])

for p in projects:
    if 'bandha' in str(p.get('p6_project_name')).lower() or 'bandha' in str(p.get('project_name')).lower():
        print(f"Mapping ID: {p.get('mapping_id')}")
        # Fetch edges manually using mapping logic to print from/to nodes
        m = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == p.get('mapping_id')).first()
        edges = db.query(models.TcNetworkEdge).all()
        for edge in edges:
            matched = False
            proj_str = str(edge.projects)
            if m.project:
                tc_names = [t.strip() for t in m.project.split(',')]
                matched = any(f'"{t_name}"' in proj_str for t_name in tc_names if t_name)
            if matched or (m.project_name_from_p6 and f'"{m.project_name_from_p6}"' in proj_str):
                print(f"Edge ID: {edge.id}, From: {edge.from_node}, To: {edge.to_node}, Projects: {edge.projects}")
