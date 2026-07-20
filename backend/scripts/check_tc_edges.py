import sys
sys.path.append('backend')
from dotenv import load_dotenv
load_dotenv('backend/.env')
from database import SessionLocal
from models import TcNetworkEdge
import json
from collections import Counter

db = SessionLocal()
edges = db.query(TcNetworkEdge).all()
print(f'Total TC Network Edges in DB: {len(edges)}')

counts = Counter()
for e in edges:
    phase = 'Unknown Phase'
    if e.projects:
        try:
            arr = json.loads(e.projects) if isinstance(e.projects, str) else e.projects
            if isinstance(arr, list) and len(arr) > 0:
                phase = str(arr[0]).strip()
            else:
                phase = str(e.projects).strip()
        except:
            phase = str(e.projects).strip()
            
    phase = phase.replace('Phase-', 'Phase ')
    voltage = str(e.voltage).strip() if e.voltage else 'Unknown Voltage'
    counts[f'{phase} - {voltage}'] += 1

print('--- DB Raw Edge Counts ---')
for k, v in counts.most_common(10):
    print(f'{k}: {v}')
