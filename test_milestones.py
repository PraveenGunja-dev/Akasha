import sys, os
sys.path.append(os.path.abspath('backend'))
import dotenv
dotenv.load_dotenv('backend/.env')
from database import SessionLocal
from models import ProjectMapping, P6Project
from services.project_service import get_project_360_detail
db = SessionLocal()
m = db.query(ProjectMapping).filter(ProjectMapping.project_id == 'FY25-P02').first()
res = get_project_360_detail(db, m.project_id)
print(f'Milestones for FY25-P02: {len(res.get("p6", {}).get("milestones", []))}')
