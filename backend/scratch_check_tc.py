import sys; sys.path.insert(0, '.')
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()

print('=== Checking tc_project_entry ===')
try:
    cols = list(db.execute(text('SELECT * FROM tc_project_entry LIMIT 0')).keys())
    print('Columns:', cols)
    rows = db.execute(text("SELECT * FROM tc_project_entry WHERE project_name ILIKE '%MUNDRA%'")).fetchall()
    for r in rows:
        print(dict(zip(cols, r)))
except Exception as e:
    print('Error:', e)

db.close()
