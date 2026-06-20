import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import dotenv
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

from database import SessionLocal
from models import ProjectMapping

db = SessionLocal()
mappings = db.query(ProjectMapping).all()

# Categories
cats = {}
for m in mappings:
    c = m.category or 'None'
    cats[c] = cats.get(c, 0) + 1
print(f"Total: {len(mappings)}")
print(f"Categories: {cats}")

# Check source_of_origin
origins = {}
for m in mappings:
    o = m.source_of_origin or 'None'
    origins[o] = origins.get(o, 0) + 1
print(f"Origins: {origins}")

# Check how data is loaded - look for the Excel file
import glob
excel_files = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '**', 'Project*Master*'), recursive=True)
print(f"\nExcel Master files: {excel_files}")

excel_files2 = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '**', '*mapping*'), recursive=True)
print(f"Mapping files: {excel_files2}")

db.close()
