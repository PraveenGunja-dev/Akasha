import sys
sys.path.append('d:/Adani_projects/Akasha/backend')
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("UPDATE ariba_inbound_delivery SET po_number = REPLACE(po_number, '.0', '') WHERE po_number LIKE '%.0'"))
db.commit()
print('DB PO numbers updated.')
