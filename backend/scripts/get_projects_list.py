import sys
import os

# Add the parent directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import ProjectMapping

def main():
    db = SessionLocal()
    try:
        mappings = db.query(ProjectMapping).all()
        print(f"Total projects found: {len(mappings)}")
        print("P6 ID | Project Name | SPV | Type")
        print("-" * 60)
        for m in mappings:
            print(f"{m.project_id} | {m.project_name_from_p6} | {m.spv_name} | {m.cluster}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
