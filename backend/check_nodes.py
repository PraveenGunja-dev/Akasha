import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
import models
db = SessionLocal()

nodes = db.query(models.TcNetworkNode).filter(models.TcNetworkNode.id.in_(['n1', 'n2', 'n4', 'n5', 'n15'])).all()
for n in nodes:
    print(f"Node ID: {n.id}, Label: {n.label}")
