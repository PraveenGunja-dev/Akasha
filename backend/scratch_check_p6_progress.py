import sys; sys.path.insert(0, '.')
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()

print('=== Checking p6_project for progress columns ===')
try:
    cols = list(db.execute(text('SELECT * FROM p6_project LIMIT 0')).keys())
    print('Columns:', cols)
    row = db.execute(text("SELECT * FROM p6_project WHERE name ILIKE '%MUNDRA%'")).fetchone()
    if row:
        print(dict(zip(cols, row)))
except Exception as e:
    print('Error:', e)

db.close()
