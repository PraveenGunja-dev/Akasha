import sys, os, time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dotenv
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv.load_dotenv(os.path.join(base_dir, '.env'))
from database import SessionLocal
from models import P6Project
from services.p6_service import P6Service
db = SessionLocal()
p6 = P6Service()
projs = db.query(P6Project).all()
print(f'Starting sync for {len(projs)} projects...')
for p in projs:
  if len(p.activities) == 0:
    print(f'Syncing activities for {p.name}...')
    try:
      p6.sync_activities_to_db(db, project_object_id=p.p6_object_id)
    except Exception as e:
      print(f'Failed for {p.name}: {e}')
print('Finished syncing all activities!')
