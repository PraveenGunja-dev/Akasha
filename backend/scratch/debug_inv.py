import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import SessionLocal
from services.project_service import calculate_project_360_metrics

db = SessionLocal()
data = calculate_project_360_metrics(db)
print(f"Total projects returned: {len(data)}")
inv_projects = [d for d in data if d.get('invoiceCount', 0) > 0]
print(f"Projects with invoices > 0: {len(inv_projects)}")
for d in inv_projects:
    name = d["projectName"]
    count = d["invoiceCount"]
    print(f"  {name}: invoiceCount={count}")
db.close()
