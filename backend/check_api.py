import requests
import json

try:
    r = requests.get('http://localhost:3510/api/module-deliveries/summary')
    data = r.json()
    projects = data.get('projects', [])
    with_ftc = [p for p in projects if p.get('ftc_date')]
    
    print(f"Total projects: {len(projects)}")
    print(f"Projects with FTC dates: {len(with_ftc)}")
    
    if with_ftc:
        print("Sample FTC date:", with_ftc[0].get('ftc_date'))
        
except Exception as e:
    print("Error:", e)
