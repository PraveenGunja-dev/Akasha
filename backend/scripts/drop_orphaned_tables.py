import os
import sys
from sqlalchemy import text

# Ensure backend is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import engine

def drop_tables():
    tables_to_drop = [
        "master_project",
        "p6_capacity_milestone",
        "p6_project_details",
        "sap_inventory_balance",
        "sap_material_dimension",
        "sap_material_transaction",
        "sap_vendor_dimension",
        "transmission_edge",
        "transmission_node"
    ]
    
    with engine.begin() as conn:
        for table in tables_to_drop:
            print(f"Dropping table {table}...")
            # We use CASCADE to drop any dependent objects (like foreign keys) pointing to these tables
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
            
    print("\nSuccessfully dropped all orphaned tables.")

if __name__ == "__main__":
    drop_tables()
