import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import dotenv
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

from database import SessionLocal
from models import ProjectMapping, P6Project, TcNetworkEdge, TcProjectEntry
from datetime import datetime

db = SessionLocal()

# 1. ProjectMapping count
mappings = db.query(ProjectMapping).all()
print(f"ProjectMapping total: {len(mappings)}")

# 2. Check P6 health data
print("\n=== P6 Health Check ===")
delayed_count = 0
on_track_count = 0
no_p6_count = 0

for m in mappings:
    p6 = db.query(P6Project).filter(P6Project.project_id == m.project_id).first()
    if not p6:
        no_p6_count += 1
        continue
    
    fdv = p6.finish_date_variance
    sched_finish = p6.scheduled_finish_date
    actual_finish = p6.finish_date
    dpc = p6.duration_percent_complete or 0
    
    # Current logic: only uses finish_date_variance
    health_current = "delayed" if (fdv and fdv < 0) else "on_track"
    
    # Better logic: also check if scheduled finish is past and not complete
    now = datetime.now()
    is_overdue = False
    if sched_finish and sched_finish < now and dpc < 1.0:
        is_overdue = True
    
    if health_current == "delayed":
        delayed_count += 1
    else:
        on_track_count += 1
    
    if is_overdue:
        print(f"  OVERDUE: {m.project_name_from_p6 or m.project} | sched_finish={sched_finish} | dpc={dpc:.2f} | fdv={fdv}")

print(f"\nCurrent logic: delayed={delayed_count}, on_track={on_track_count}, no_p6={no_p6_count}")

# 3. Check activities for delays
from models import P6Activity
print("\n=== Activity-based delay check ===")
for m in mappings[:5]:
    p6 = db.query(P6Project).filter(P6Project.project_id == m.project_id).first()
    if not p6:
        continue
    delayed_acts = db.query(P6Activity).filter(
        P6Activity.project_object_id == p6.p6_object_id,
        P6Activity.status == 'In Progress',
        P6Activity.planned_finish_date < datetime.now()
    ).count()
    total_acts = db.query(P6Activity).filter(P6Activity.project_object_id == p6.p6_object_id).count()
    print(f"  {(m.project_name_from_p6 or m.project)[:40]} | total_acts={total_acts} | delayed_acts={delayed_acts}")

# 4. Transmission data check
print("\n=== Transmission Data ===")
tc_edges = db.query(TcNetworkEdge).count()
tc_entries = db.query(TcProjectEntry).count()
print(f"TcNetworkEdge count: {tc_edges}")
print(f"TcProjectEntry count: {tc_entries}")

# Check which mappings have TC data
mappings_with_tc = 0
for m in mappings:
    entries = db.query(TcProjectEntry).filter(TcProjectEntry.mapping_id == m.id).count()
    if entries > 0:
        mappings_with_tc += 1
        edges_for_project = db.query(TcNetworkEdge).filter(TcNetworkEdge.mapping_id == m.id).count()
        print(f"  TC for {(m.project_name_from_p6 or m.project)[:35]}: {entries} entries, {edges_for_project} direct edges")

print(f"\nMappings with TC data: {mappings_with_tc} / {len(mappings)}")

db.close()
