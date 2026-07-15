import requests
import time
import re
from database import SessionLocal
import models

db = SessionLocal()
nodes = db.query(models.TcNetworkNode).all()

clean_names = set()
for n in nodes:
    if n.label:
        clean_name = re.sub(r'\s*\(.*?\)', '', n.label).strip()
        if len(clean_name) > 2:
            clean_names.add(clean_name)

clean_names = list(clean_names)

found_names = set()
missing_names = set()
url = "https://overpass-api.de/api/interpreter"

print(f'Checking {len(clean_names)} substations...')

for i, name in enumerate(clean_names):
    # simple query
    query = f"""
    [out:json][timeout:25];
    (
      node["power"="substation"]["name"~"{name}", i];
      way["power"="substation"]["name"~"{name}", i];
      relation["power"="substation"]["name"~"{name}", i];
    );
    out tags;
    """
    
    try:
        res = requests.post(url, data={'data': query})
        if res.status_code == 200:
            data = res.json()
            if len(data.get('elements', [])) > 0:
                found_names.add(name)
            else:
                missing_names.add(name)
        else:
            missing_names.add(name)
    except Exception as e:
        missing_names.add(name)
        
    time.sleep(1)

print(f'\n--- RESULTS ---')
print(f'Total Unique Clean Node Names: {len(clean_names)}')
print(f'Found in OSM: {len(found_names)}')
print(f'Missing in OSM: {len(clean_names) - len(found_names)}')

print('\nMatched Substations:')
print(', '.join(sorted(found_names)))

print('\nMissing Substations:')
print(', '.join(sorted(missing_names)))
