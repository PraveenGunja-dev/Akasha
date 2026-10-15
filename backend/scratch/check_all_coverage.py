import sys
sys.path.append('d:/Adani_projects/Akasha/backend')
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()

# All SAP POs (POrd)
all_sap_pos = db.execute(text("SELECT DISTINCT purchasing_document FROM mt_poamount WHERE doc_type = 'POrd' AND purchasing_document IS NOT NULL AND purchasing_document != ''")).fetchall()
all_sap_set = set(str(r[0]).strip() for r in all_sap_pos)

# Module SAP POs
mod_sap_pos = db.execute(text("SELECT DISTINCT purchasing_document FROM mt_poamount WHERE (material_name ILIKE '%module%' OR short_text ILIKE '%module%') AND doc_type = 'POrd' AND purchasing_document IS NOT NULL AND purchasing_document != ''")).fetchall()
mod_sap_set = set(str(r[0]).strip() for r in mod_sap_pos)

# Non-Module SAP POs
non_mod_sap_set = all_sap_set - mod_sap_set

# Ariba POs
ariba_pos = db.execute(text("SELECT DISTINCT po_number FROM ariba_inbound_delivery WHERE po_number IS NOT NULL AND po_number != ''")).fetchall()
ariba_set = set(str(r[0]).strip() for r in ariba_pos)

# Matches
matched_all = all_sap_set.intersection(ariba_set)
matched_mod = mod_sap_set.intersection(ariba_set)
matched_non_mod = non_mod_sap_set.intersection(ariba_set)

print(f"Total SAP POs (POrd): {len(all_sap_set)}")
print(f"Total Ariba Dispatched POs: {len(ariba_set)}\n")

print(f"--- NON-MODULE POs ---")
print(f"Total Non-Module SAP POs: {len(non_mod_sap_set)}")
print(f"Non-Module POs found in Ariba: {len(matched_non_mod)}")
print(f"Non-Module POs NOT YET in Ariba: {len(non_mod_sap_set) - len(matched_non_mod)}\n")

print(f"--- OVERALL ---")
print(f"Total SAP POs found in Ariba: {len(matched_all)}")
print(f"Total SAP POs NOT YET in Ariba: {len(all_sap_set) - len(matched_all)}")
