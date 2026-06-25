from database import SessionLocal
from models import TcProjectEntry, TcNetworkEdge, ProjectMapping
db = SessionLocal()
m = db.query(ProjectMapping).filter(ProjectMapping.project_id=='FY25-BANDHA_500MW').first()
if m:
    entries = db.query(TcProjectEntry).filter(TcProjectEntry.mapping_id==m.id).all()
    print('Phases mapped:', [e.phase for e in entries])
    edges = db.query(TcNetworkEdge).filter(TcNetworkEdge.mapping_id==m.id).all()
    print('Direct edges:', [e.edge_id for e in edges])
else:
    print('Mapping not found')
