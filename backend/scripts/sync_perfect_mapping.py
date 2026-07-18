import sys
import os
import json

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine, SessionLocal
import models
from sqlalchemy import text

def run_perfect_sync():
    print("🚀 Running Perfect Mapping Sync...")
    
    db = SessionLocal()
    try:
        # Load perfect mapping JSON
        json_path = os.path.join(os.path.dirname(__file__), 'perfect_mapping.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            perfect_projects = json.load(f)
            
        print(f"📦 Loaded {len(perfect_projects)} perfect projects from JSON.")
        
        # Wipe TC tables first to avoid Foreign Key violations
        print("🧹 Wiping Transmission tables to clear foreign key constraints...")
        db.query(models.TcNetworkEdge).delete(synchronize_session=False)
        db.query(models.TcProjectEntry).delete(synchronize_session=False)
        db.query(models.TcNetworkNode).delete(synchronize_session=False)
        
        # Completely wipe the existing messed up mappings
        print("🧹 Wiping existing ProjectMapping table...")
        deleted = db.query(models.ProjectMapping).delete(synchronize_session=False)
        print(f"✅ Deleted {deleted} old mapped projects.")
        
        # Insert all perfect projects
        print("⚡ Inserting perfect projects...")
        for p_data in perfect_projects:
            new_mapping = models.ProjectMapping(**p_data)
            db.add(new_mapping)
            
        db.commit()
        print(f"🎉 Successfully inserted {len(perfect_projects)} perfect mapped projects!")
        
        # Verify the count
        final_count = db.query(models.ProjectMapping).count()
        print(f"📊 Final ProjectMapping count in DB: {final_count}")
        
    except Exception as e:
        print(f"❌ Error during perfect sync: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_perfect_sync()
