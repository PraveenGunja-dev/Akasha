from database import SessionLocal
import models

db = SessionLocal()
mappings = db.query(models.ProjectMapping).all()
p6_projs = db.query(models.P6Project).all()
p6_by_pid = {p.project_id: p for p in p6_projs}

print(f"Total ProjectMapping rows: {len(mappings)}")
print(f"Total P6Project rows: {len(p6_projs)}")

demo_list = []
no_p6_list = []
active_list = []

for m in mappings:
    name = m.project_name_from_p6 or m.project or m.project_id or ""
    is_demo = "demo" in name.lower()
    has_p6 = m.project_id in p6_by_pid
    
    if is_demo:
        demo_list.append((m.project_id, name))
    elif not has_p6:
        no_p6_list.append((m.project_id, name))
    else:
        active_list.append((m.project_id, name))

print(f"\nDemo Test Projects Filtered Out ({len(demo_list)}):")
for pid, name in demo_list:
    print(f"  - {pid}: {name}")

print(f"\nMapped Projects Without P6 Schedule Data ({len(no_p6_list)}):")
for pid, name in no_p6_list:
    print(f"  - {pid}: {name}")

print(f"\nActive Portfolio Projects with P6 Schedule Data ({len(active_list)}):")
print(f"Total Active Projects: {len(active_list)}")
