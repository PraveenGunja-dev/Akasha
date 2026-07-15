"""
Cross-reference Akasha transmission substations against OpenStreetMap.
Uses Nominatim search API for name lookups (reliable, no rate-limit issues).
"""
import requests
import re
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
import models

# --- 1. Get all unique node labels from DB ---
db = SessionLocal()
nodes = db.query(models.TcNetworkNode).all()

khavda_nodes = []
rajasthan_nodes = []
for n in nodes:
    if n.label:
        clean = re.sub(r'\s*\(.*?\)', '', n.label).strip()
        if len(clean) > 2:
            if n.region == "Khavda":
                khavda_nodes.append(clean)
            elif n.region == "Rajasthan":
                rajasthan_nodes.append(clean)

khavda_unique = sorted(set(khavda_nodes))
rajasthan_unique = sorted(set(rajasthan_nodes))
all_unique = sorted(set(khavda_unique + rajasthan_unique))

print(f"Khavda substations in DB: {len(khavda_unique)}")
print(f"Rajasthan substations in DB: {len(rajasthan_unique)}")
print(f"Total unique substations: {len(all_unique)}")
print()

# --- 2. Use Nominatim search API ---
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

session = requests.Session()
session.headers.update({
    "User-Agent": "AkashaPlatform/1.0 (praveen@akasha.com)",
    "Accept": "application/json",
})

def search_osm(name):
    """Search Nominatim for a substation/location by name in India."""
    search_terms = [
        f"{name} power India",
        f"{name} India",
    ]
    
    for term in search_terms:
        try:
            resp = session.get(NOMINATIM_URL, params={
                "q": term,
                "format": "json",
                "countrycodes": "in",
                "limit": 5,
            }, timeout=15)
            if resp.status_code == 200:
                results = resp.json()
                for r in results:
                    display = r.get("display_name", "").lower()
                    if name.lower() in display:
                        return True, r.get("display_name", "")
        except Exception as e:
            print(f"    Error for {name}: {e}")
        time.sleep(1.1)  # Rate limit: 1 req/sec
    
    return False, ""

found = []
missing = []

for i, name in enumerate(all_unique):
    matched, display = search_osm(name)
    status = "FOUND" if matched else "MISSING"
    extra = f" -> {display[:80]}" if matched else ""
    print(f"  [{i+1}/{len(all_unique)}] {name}: {status}{extra}")
    sys.stdout.flush()
    if matched:
        found.append(name)
    else:
        missing.append(name)

# --- 3. Print results ---
khavda_found = [n for n in found if n in khavda_unique]
khavda_missing = [n for n in missing if n in khavda_unique]
raj_found = [n for n in found if n in rajasthan_unique]
raj_missing = [n for n in missing if n in rajasthan_unique]

print()
print("=" * 60)
print("KHAVDA SUBSTATIONS")
print(f"  Total: {len(khavda_unique)}")
print(f"  Mapped in OSM: {len(khavda_found)}")
print(f"  Missing in OSM: {len(khavda_missing)}")
if khavda_found:
    print(f"  Found: {', '.join(khavda_found)}")
if khavda_missing:
    print(f"  Missing: {', '.join(khavda_missing)}")
print()
print("RAJASTHAN SUBSTATIONS")
print(f"  Total: {len(rajasthan_unique)}")
print(f"  Mapped in OSM: {len(raj_found)}")
print(f"  Missing in OSM: {len(raj_missing)}")
if raj_found:
    print(f"  Found: {', '.join(raj_found)}")
if raj_missing:
    print(f"  Missing: {', '.join(raj_missing)}")
print()
print("OVERALL")
print(f"  Total: {len(all_unique)}")
print(f"  Mapped in OSM: {len(found)}")
print(f"  Missing in OSM: {len(missing)}")
print("=" * 60)

db.close()
