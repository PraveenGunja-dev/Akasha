import sys
from database import SessionLocal
from routers.dashboard import get_knowledge_graph

db = SessionLocal()
try:
    res = get_knowledge_graph(db=db)
    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
