import sys
sys.path.append('d:/Adani_projects/Akasha/backend')
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()

sap_pos = db.execute(text("SELECT DISTINCT purchasing_document FROM mt_poamount WHERE (material_name ILIKE '%module%' OR short_text ILIKE '%module%') AND doc_type = 'POrd' AND purchasing_document IS NOT NULL AND purchasing_document != ''")).fetchall()
sap_set = set(str(r[0]).strip() for r in sap_pos)

ariba_pos = db.execute(text("SELECT DISTINCT po_number FROM ariba_inbound_delivery WHERE po_number IS NOT NULL AND po_number != ''")).fetchall()
ariba_set = set(str(r[0]).strip() for r in ariba_pos)

matched = sap_set.intersection(ariba_set)

print(f"Total SAP Module POs (POrd): {len(sap_set)}")
print(f"Total Ariba Dispatched POs: {len(ariba_set)}")
print(f"SAP Module POs found in Ariba: {len(matched)}")
print(f"SAP Module POs NOT YET in Ariba: {len(sap_set) - len(matched)}")
