import os, json
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from models import TcProjectEntry, TcNetworkNode, TcNetworkEdge

def load_tc_data():
    data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "Data", "tc_dump.json")
    if not os.path.exists(data_path):
        print(f"File not found: {data_path}")
        return

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    db = SessionLocal()
    try:
        # Clear existing data
        print("Clearing old Transmission Data...")
        db.query(TcProjectEntry).delete()
        db.query(TcNetworkNode).delete()
        db.query(TcNetworkEdge).delete()
        db.commit()

        print("Loading Projects...")
        for p in data["projects"]:
            db.add(TcProjectEntry(**p))
            
        print("Loading Nodes...")
        for n in data["nodes"]:
            db.add(TcNetworkNode(**n))
            
        print("Loading Edges...")
        for e in data["edges"]:
            db.add(TcNetworkEdge(**e))

        db.commit()
        print(f"Successfully loaded {len(data['projects'])} projects, {len(data['nodes'])} nodes, and {len(data['edges'])} edges!")
    except Exception as e:
        db.rollback()
        print(f"Error loading data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    load_tc_data()
