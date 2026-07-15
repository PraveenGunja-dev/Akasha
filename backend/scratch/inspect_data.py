from database import SessionLocal
from models import ProjectMapping, P6Activity, MTTrialRun, P6WBSNode

db = SessionLocal()

projects = db.query(ProjectMapping).all()
print(f"Total projects in mapping: {len(projects)}")

print("\nSample projects:")
for p in projects[:3]:
    print(f"- {p.project_id} | {p.project_name_from_p6} | WBS: {p.module_wbs}")

# Check MTTrialRun
trial_runs = db.query(MTTrialRun).all()
print(f"\nTotal Trial Run records: {len(trial_runs)}")
if trial_runs:
    for tr in trial_runs[:3]:
        print(f"- {tr.project_name} | {tr.activity_name} | Block: {tr.project_name_block}")

# Check activities for COD
cod_activities = db.query(P6Activity).filter(P6Activity.name.ilike('%COD%')).all()
print(f"\nTotal COD activities in P6: {len(cod_activities)}")
if cod_activities:
    for a in cod_activities[:3]:
        print(f"- {a.project_object_id} | {a.name} | Status: {a.status} | % Complete: {a.percent_complete}")

# Check WBS Nodes for blocks
blocks = db.query(P6WBSNode).filter(P6WBSNode.is_block == True).all()
print(f"\nTotal Block WBS Nodes: {len(blocks)}")
if blocks:
    for b in blocks[:3]:
        print(f"- Project: {b.project_object_id} | Name: {b.wbs_name} | Block #: {b.block_number}")

db.close()
