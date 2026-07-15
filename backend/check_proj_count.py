import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import ProjectMapping, P6Project
import json

db = SessionLocal()
mappings = db.query(ProjectMapping).all()
p6 = db.query(P6Project).all()
print("Mappings:", len(mappings))
print("P6 Projects:", len(p6))
