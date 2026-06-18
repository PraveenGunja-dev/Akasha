import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, engine
from sqlalchemy import text
import models

def run_migration():
    print("Starting database migration for SAP material tracking...")
    db = SessionLocal()
    
    statements = [
        "ALTER TABLE project_mapping ADD COLUMN source_of_origin VARCHAR",
        "ALTER TABLE project_mapping ADD COLUMN priority VARCHAR",
        "ALTER TABLE mt_poamount ADD COLUMN material_name VARCHAR",
        "ALTER TABLE mt_poamount ADD COLUMN order_quantity FLOAT",
        "ALTER TABLE mt_poamount ADD COLUMN net_order_value_inr FLOAT",
        "ALTER TABLE mt_poamount ADD COLUMN still_to_deliver_qty FLOAT",
        "ALTER TABLE mt_poamount ADD COLUMN still_to_deliver_inr FLOAT",
        "ALTER TABLE mt_poamount ADD COLUMN delivered_qty FLOAT",
        "ALTER TABLE mt_poamount ADD COLUMN delivered_value_inr_cr FLOAT",
        "ALTER TABLE mt_poamount ADD COLUMN storage_location VARCHAR",
        "ALTER TABLE mt_poamount ADD COLUMN block_plot_name VARCHAR",
        "ALTER TABLE mt_poamount ADD COLUMN currency VARCHAR",
        "ALTER TABLE mt_materialdocument ADD COLUMN material_name VARCHAR",
        "ALTER TABLE mt_materialdocument ADD COLUMN material_description VARCHAR",
        "ALTER TABLE mt_materialdocument ADD COLUMN amount_in_lc FLOAT",
        "ALTER TABLE mt_materialdocument ADD COLUMN amount_in_lc_cr FLOAT",
        "ALTER TABLE mt_materialdocument ADD COLUMN storage_location VARCHAR",
        "ALTER TABLE mt_materialdocument ADD COLUMN block_plot_name VARCHAR",
        "ALTER TABLE mt_materialdocument ADD COLUMN purchase_order VARCHAR",
        "ALTER TABLE mt_materialdocument ADD COLUMN base_unit VARCHAR",
        "ALTER TABLE mt_inventory ADD COLUMN material_name VARCHAR",
        "ALTER TABLE mt_inventory ADD COLUMN unrestricted_qty FLOAT"
    ]
    
    for stmt in statements:
        try:
            db.execute(text(stmt))
            db.commit()
            print(f"SUCCESS: {stmt}")
        except Exception as e:
            db.rollback()
            print(f"SKIPPED (Already exists or error): {stmt}")

    db.close()
    print("Migration finished.")

if __name__ == "__main__":
    run_migration()
