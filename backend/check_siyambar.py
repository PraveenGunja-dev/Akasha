import sys
sys.path.append('d:\\Akasha_Platform\\backend')

from database import SessionLocal
import models

db = SessionLocal()

print('--- TC Edges with Siyambar ---')
edges = db.query(models.TcNetworkEdge).filter(
    (models.TcNetworkEdge.from_node.ilike('%Siyambar%')) | 
    (models.TcNetworkEdge.to_node.ilike('%Siyambar%')) |
    (models.TcNetworkEdge.projects.ilike('%Siyambar%'))
).all()
for e in edges:
    print(f'Edge ID: {e.id}, From: {e.from_node}, To: {e.to_node}, Projects: {e.projects}')

print('--- TC Edges with Bandha ---')
edges2 = db.query(models.TcNetworkEdge).filter(
    (models.TcNetworkEdge.from_node.ilike('%Bandha%')) | 
    (models.TcNetworkEdge.to_node.ilike('%Bandha%')) |
    (models.TcNetworkEdge.projects.ilike('%Bandha%'))
).all()
for e in edges2:
    print(f'Edge ID: {e.id}, From: {e.from_node}, To: {e.to_node}, Projects: {e.projects}')

print('--- Mappings with Siyambar ---')
maps = db.query(models.ProjectMapping).filter(models.ProjectMapping.project.ilike('%Siyambar%')).all()
for m in maps:
    print(f'Map ID: {m.id}, Project: {m.project}, P6 Name: {m.project_name_from_p6}')
    
print('--- Mappings with Bandha ---')
maps2 = db.query(models.ProjectMapping).filter(models.ProjectMapping.project.ilike('%Bandha%')).all()
for m in maps2:
    print(f'Map ID: {m.id}, Project: {m.project}, P6 Name: {m.project_name_from_p6}')

