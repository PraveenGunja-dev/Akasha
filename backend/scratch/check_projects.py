import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text

# Using the VM UAT DATABASE_URL from .env
DATABASE_URL = "postgresql://postgres:Prvn%403315@localhost:5432/Akasha"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def main():
    try:
        db = SessionLocal()
        # count project_mapping
        db = SessionLocal()
        
        # count project_mapping by category/cluster
        print("--- Project Mappings by Category ---")
        by_category = db.execute(text("SELECT category, count(*) FROM project_mapping GROUP BY category;")).fetchall()
        for cat in by_category:
            print(f"  {cat[0]}: {cat[1]}")
            
        print("\n--- Project Mappings by Cluster ---")
        by_cluster = db.execute(text("SELECT cluster, count(*) FROM project_mapping GROUP BY cluster;")).fetchall()
        for cl in by_cluster:
            print(f"  {cl[0]}: {cl[1]}")
            
        print("\n--- Detailed List of 'Wind' and 'BESS' Projects (to find the missing ones) ---")
        wind_projects = db.execute(text("SELECT project FROM project_mapping WHERE category ILIKE '%wind%' OR cluster ILIKE '%wind%';")).fetchall()
        print(f"Wind projects found ({len(wind_projects)}):")
        for p in wind_projects:
            print(f"  - {p[0]}")
            
        print("\n--- Transmission Data Check ---")
        tc_proj = db.execute(text("SELECT count(*) FROM tc_project_entry;")).scalar()
        tc_nodes = db.execute(text("SELECT count(*) FROM tc_network_node;")).scalar()
        tc_edges = db.execute(text("SELECT count(*) FROM tc_network_edge;")).scalar()
        print(f"TcProjectEntry count: {tc_proj}")
        print(f"TcNetworkNode count: {tc_nodes}")
        print(f"TcNetworkEdge count: {tc_edges}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
