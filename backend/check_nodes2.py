import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
import models
db = SessionLocal()

nodes = db.query(models.TcNetworkNode).filter(models.TcNetworkNode.node_id.in_(['n1', 'n2', 'n4', 'n5', 'n15'])).all()
for n in nodes:
    print(f"Node ID: {n.node_id}, Label: {n.label}")
