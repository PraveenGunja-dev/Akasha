import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import P6WBSNode

db = SessionLocal()
wbs_nodes = db.query(P6WBSNode).filter(P6WBSNode.wbs_name.ilike('%WTG%')).all()
print(f"Total WTG nodes: {len(wbs_nodes)}")
names = list(set([w.wbs_name for w in wbs_nodes]))
print(names[:20])
db.close()
