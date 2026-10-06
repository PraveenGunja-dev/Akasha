from sqlalchemy import text
from database import engine

queries = [
    "ALTER TABLE mt_intransit ADD COLUMN IF NOT EXISTS grn_quantity FLOAT;",
    "ALTER TABLE mt_intransit ADD COLUMN IF NOT EXISTS ibd_creation_date TIMESTAMP;",
    "ALTER TABLE mt_intransit ADD COLUMN IF NOT EXISTS po_quantity FLOAT;",
    "ALTER TABLE mt_intransit ADD COLUMN IF NOT EXISTS rejected_quantity FLOAT;",
    
    "ALTER TABLE mt_inventory ADD COLUMN IF NOT EXISTS special_stock VARCHAR;",
    "ALTER TABLE mt_inventory ADD COLUMN IF NOT EXISTS material_type VARCHAR;",
    "ALTER TABLE mt_inventory ADD COLUMN IF NOT EXISTS material_group VARCHAR;",
    "ALTER TABLE mt_inventory ADD COLUMN IF NOT EXISTS material_description VARCHAR;",
    "ALTER TABLE mt_inventory ADD COLUMN IF NOT EXISTS value_unrestricted FLOAT;",
    "ALTER TABLE mt_inventory ADD COLUMN IF NOT EXISTS plant_name VARCHAR;",
    
    "ALTER TABLE mt_poamount ADD COLUMN IF NOT EXISTS quantity_received FLOAT;",
    "ALTER TABLE mt_poamount ADD COLUMN IF NOT EXISTS still_to_be_delivered_qty FLOAT;",
    "ALTER TABLE mt_poamount ADD COLUMN IF NOT EXISTS delivery_date TIMESTAMP;",
    "ALTER TABLE mt_poamount ADD COLUMN IF NOT EXISTS delivery_completed_flag VARCHAR;",
    "ALTER TABLE mt_poamount ADD COLUMN IF NOT EXISTS deletion_indicator VARCHAR;",
    "ALTER TABLE mt_poamount ADD COLUMN IF NOT EXISTS document_date TIMESTAMP;",
    "ALTER TABLE mt_poamount ADD COLUMN IF NOT EXISTS short_text VARCHAR;"
]

def fix_db():
    print("Fixing db columns...")
    with engine.begin() as conn:
        for q in queries:
            try:
                conn.execute(text(q))
                print(f"Executed: {q}")
            except Exception as e:
                print(f"Error on {q}: {e}")

if __name__ == '__main__':
    fix_db()
