import sys; sys.path.append("backend")
from dotenv import load_dotenv; load_dotenv("backend/.env")
from database import SessionLocal
from models import ProjectMapping
from services.project_service import get_project_einvoices
db = SessionLocal()

mappings = db.query(ProjectMapping).all()
total_mapped_invoices = 0
projects_with_data = []

for mapping in mappings:
    res = get_project_einvoices(db, mapping)
    inv_count = len(res.get('invoices', []))
    if inv_count > 0:
        projects_with_data.append((mapping.project_name_from_p6 or "Unknown Project", inv_count))
        total_mapped_invoices += inv_count

print(f"\nTotal Projects with E-Invoice Data: {len(projects_with_data)}")
print("-" * 50)
for p_name, count in sorted(projects_with_data, key=lambda x: x[1], reverse=True):
    print(f"{p_name}: {count} invoices")

print("-" * 50)
print(f"Total E-Invoices successfully mapped across all projects: {total_mapped_invoices}")
