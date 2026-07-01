import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
from models import P6Activity, ProjectMapping
from sqlalchemy import func

db = SessionLocal()

# Find project IDs that have COD activities
projects_with_cod = db.query(P6Activity.project_object_id).filter(P6Activity.name.ilike('%COD%')).distinct().all()

for proj_id_tuple in projects_with_cod:
    pid = proj_id_tuple[0]
    # count CODs
    cod_count = db.query(P6Activity).filter(P6Activity.project_object_id == pid, P6Activity.name.ilike('%COD%')).count()
    
    # get capacity
    # To get capacity, we need the p6 project id (e.g. FY25-P15) to query ProjectMapping
    # Wait, project_object_id is an int.
    # We can get project id from P6Project or ProjectMapping?
    
    # Just print the COD count
    print(f"Project Object ID: {pid}, COD count: {cod_count}")
