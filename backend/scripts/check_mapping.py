import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from database import SessionLocal
from models import TcProjectEntry, TcNetworkEdge, ProjectMapping

db = SessionLocal()

# Check Khavda
khavda_entries = db.query(TcProjectEntry).all()
khavda_mapped = sum(1 for e in khavda_entries if e.mapping_id is not None)
print(f"Khavda Projects: {khavda_mapped}/{len(khavda_entries)} successfully mapped.")

# Check Rajasthan
raj_edges = db.query(TcNetworkEdge).all()
raj_mapped = sum(1 for e in raj_edges if e.mapping_id is not None)
print(f"Rajasthan Edges: {raj_mapped}/{len(raj_edges)} successfully mapped.")

# Print some ProjectMapping examples to see what we're working with
mappings = db.query(ProjectMapping).limit(5).all()
print("\nSample ProjectMappings in DB:")
for m in mappings:
    print(f"ID: {m.id}, TC: {m.tc_project_name}, P6 Name: {m.p6_project_name}, SAP Plant: {m.sap_plant_code}, WBS: {m.module_wbs}")

# Print some unmapped Tc projects
print("\nSample unmapped Tc projects:")
for e in khavda_entries[:5]:
    if e.mapping_id is None:
        print(f"Khavda unmapped: {e.project}")

for e in raj_edges[:5]:
    if e.mapping_id is None:
        print(f"Rajasthan unmapped: {e.projects}")

db.close()
