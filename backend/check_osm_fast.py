import requests
import json
import re

substations = [
    'Vadodara', 'Navsari', 'Lakadia', 'Halvad', 'Nagpur',
    'South Olpad', 'Pune', 'Babhaleswar', 'Padghe', 'Ahmedabad',
    'Velgaon', 'Ghandhar', 'Hazira', 'Vataman', 'Hinjewadi',
    'Koyna', 'Narendra', 'Pirana', 'Banaskantha', 'Wardha',
    'Raipur', 'Bhuj', 'Kps-I', 'Kps-II', 'Kps-III'
]

names_regex = '|'.join(substations)

query = f"""
[out:json][timeout:25];
area["name"="India"]->.searchArea;
(
  node["power"="substation"]["name"~"({names_regex})",i](area.searchArea);
  way["power"="substation"]["name"~"({names_regex})",i](area.searchArea);
);
out tags;
"""

print('Sending query...')
try:
    res = requests.post('https://overpass-api.de/api/interpreter', data={'data': query})
    data = res.json()
    elements = data.get('elements', [])

    found_names = set()
    for el in elements:
        osm_name = el.get('tags', {}).get('name', '').lower()
        for sub in substations:
            if sub.lower() in osm_name:
                found_names.add(sub)

    print(f'Found {len(found_names)} out of {len(substations)} major substations in OSM!')
    print('Matches:', found_names)
    missing = set(substations) - found_names
    print('Missing:', missing)
except Exception as e:
    print('Error:', e)
