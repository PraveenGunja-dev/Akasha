import requests
import json
import time

substations = [
    'Vadodara', 'Navsari', 'Lakadia', 'Halvad', 'Nagpur',
    'Pune', 'Babhaleswar', 'Padghe', 'Ahmedabad',
    'Velgaon', 'Ghandhar', 'Hazira', 'Vataman', 'Hinjewadi',
    'Koyna', 'Pirana', 'Banaskantha', 'Wardha',
    'Raipur', 'Bhuj'
]

found_names = set()

for sub in substations:
    query = f"""
    [out:json][timeout:25];
    area["name"="India"]->.searchArea;
    node["power"="substation"]["name"~"{sub}",i](area.searchArea);
    out tags;
    """
    try:
        res = requests.post('https://overpass-api.de/api/interpreter', data={'data': query})
        if res.status_code == 200:
            data = res.json()
            if len(data.get('elements', [])) > 0:
                found_names.add(sub)
        else:
            print(f"Error {res.status_code} on {sub}")
    except Exception as e:
        print('Error:', e)
    time.sleep(1.5)

print(f'\nFound {len(found_names)} out of {len(substations)} major substations in OSM!')
print('Matches:', found_names)
missing = set(substations) - found_names
print('Missing:', missing)
