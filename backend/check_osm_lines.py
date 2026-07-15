"""
Check how many transmission lines (power=line) exist in OSM
in the Khavda and Rajasthan corridors using the Overpass API.
Uses curl.exe to bypass PowerShell escaping issues.
"""
import subprocess
import json
import re
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
import models

db = SessionLocal()
edges = db.query(models.TcNetworkEdge).all()

khavda_lines = {}
raj_lines = {}
for e in edges:
    if e.from_label and e.to_label:
        from_clean = re.sub(r'\s*\(.*?\)', '', e.from_label).strip()
        to_clean = re.sub(r'\s*\(.*?\)', '', e.to_label).strip()
        route = f"{from_clean} -> {to_clean}"
        khavda_lines[route] = e.voltage or "" if e.region == "Khavda" else raj_lines.update({route: e.voltage or ""}) or ""

# Remove None entries from raj_lines
raj_lines = {k: v for k, v in raj_lines.items() if v is not None}

print(f"DB Khavda Lines: {len(khavda_lines)}")
print(f"DB Rajasthan Lines: {len(raj_lines)}")
print()

# --- Overpass query for power lines using curl.exe ---
def overpass_query(query_str):
    """Run an Overpass query using curl.exe to avoid PowerShell issues."""
    try:
        result = subprocess.run(
            ["curl.exe", "-s", "-X", "POST",
             "-d", f"data={query_str}",
             "https://overpass-api.de/api/interpreter"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"Query error: {e}")
    return None

# Query 1: Khavda area (Kutch/Gujarat) - 765kV and 400kV lines
print("Fetching Khavda area power lines from OSM...")
khavda_query = '[out:json][timeout:30];way["power"="line"]["voltage"~"765000|400000"](22.0,69.0,24.5,73.0);out tags;'
khavda_data = overpass_query(khavda_query)

if khavda_data:
    khavda_osm_lines = khavda_data.get("elements", [])
    print(f"  Found {len(khavda_osm_lines)} power lines (765kV/400kV) in Khavda bounding box")
    for line in khavda_osm_lines[:10]:
        tags = line.get("tags", {})
        name = tags.get("name", "unnamed")
        voltage = tags.get("voltage", "?")
        print(f"    - {name} ({voltage}V)")
else:
    print("  Failed to query Khavda area")

# Query 2: Full Gujarat-Maharashtra-Rajasthan corridor
print()
print("Fetching wider corridor power lines from OSM...")
wide_query = '[out:json][timeout:30];way["power"="line"]["voltage"~"765000|400000"](18.0,68.0,28.0,78.0);out tags;'
wide_data = overpass_query(wide_query)

if wide_data:
    wide_osm_lines = wide_data.get("elements", [])
    print(f"  Found {len(wide_osm_lines)} power lines (765kV/400kV) in Gujarat-Rajasthan-Maharashtra corridor")
    
    # Count named vs unnamed
    named = [l for l in wide_osm_lines if l.get("tags", {}).get("name")]
    print(f"  Named lines: {len(named)}")
    print(f"  Unnamed lines: {len(wide_osm_lines) - len(named)}")
    
    # Show named ones
    for line in named[:20]:
        tags = line.get("tags", {})
        name = tags.get("name", "")
        voltage = tags.get("voltage", "?")
        print(f"    - {name} ({voltage}V)")
else:
    print("  Failed to query wide corridor")

# Query 3: Rajasthan area - Bhadla/Bikaner/Ramgarh
print()
print("Fetching Rajasthan area power lines from OSM...")
raj_query = '[out:json][timeout:30];way["power"="line"]["voltage"~"765000|400000"](25.0,69.0,29.0,75.0);out tags;'
raj_data = overpass_query(raj_query)

if raj_data:
    raj_osm_lines = raj_data.get("elements", [])
    print(f"  Found {len(raj_osm_lines)} power lines (765kV/400kV) in Rajasthan bounding box")
    named = [l for l in raj_osm_lines if l.get("tags", {}).get("name")]
    print(f"  Named lines: {len(named)}")
    for line in named[:20]:
        tags = line.get("tags", {})
        name = tags.get("name", "")
        voltage = tags.get("voltage", "?")
        print(f"    - {name} ({voltage}V)")
else:
    print("  Failed to query Rajasthan area")

# --- Now try matching our lines against named OSM lines ---
print()
print("=" * 60)
print("MATCHING YOUR LINES AGAINST OSM NAMED LINES")
print("=" * 60)

all_osm_names = set()
if wide_data:
    for l in wide_data.get("elements", []):
        name = l.get("tags", {}).get("name", "").lower()
        if name:
            all_osm_names.add(name)
if raj_data:
    for l in raj_data.get("elements", []):
        name = l.get("tags", {}).get("name", "").lower()
        if name:
            all_osm_names.add(name)

all_lines = {**khavda_lines, **raj_lines}
found = []
missing = []

for route, voltage in sorted(all_lines.items()):
    parts = route.split(" -> ")
    from_name = parts[0].lower()
    to_name = parts[1].lower()
    
    matched = False
    match_name = ""
    for osm_name in all_osm_names:
        if (from_name in osm_name and to_name in osm_name) or \
           (to_name in osm_name and from_name in osm_name):
            matched = True
            match_name = osm_name
            break
    
    if matched:
        found.append(route)
        print(f"  FOUND: {route} ({voltage}) -> {match_name}")
    else:
        missing.append(route)
        print(f"  MISSING: {route} ({voltage})")

print()
print("=" * 60)
print(f"LINES FOUND IN OSM: {len(found)} / {len(all_lines)}")
print(f"LINES MISSING: {len(missing)} / {len(all_lines)}")
print("=" * 60)

db.close()
