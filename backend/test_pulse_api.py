"""
Deep exploration of Pulse data to understand the full landscape.
Pulls NCs and RFIs to analyze: statuses, categories, projects, clusters, packages, timelines.
"""
import requests
import json
from collections import Counter, defaultdict
from datetime import datetime

BASE_URL = "https://pulse.cfapps.ap11.hana.ondemand.com"

def fetch_all(entity, select_fields, top=500):
    """Fetch records with pagination."""
    all_records = []
    skip = 0
    while True:
        url = f"{BASE_URL}/pulse-api/{entity}?$top={top}&$skip={skip}&$select={select_fields}"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"  Error at skip={skip}: {resp.status_code}")
            break
        data = resp.json()
        records = data.get("value", [])
        if not records:
            break
        all_records.extend(records)
        skip += top
        if len(records) < top:
            break
    return all_records

def fetch_with_expand(entity, expand, top=50):
    """Fetch with $expand for nested data."""
    url = f"{BASE_URL}/pulse-api/{entity}?$top={top}&$expand={expand}"
    resp = requests.get(url, timeout=30)
    if resp.status_code == 200:
        return resp.json().get("value", [])
    print(f"  Error: {resp.status_code} - {resp.text[:200]}")
    return []

print("=" * 70)
print("  PULSE DATA DEEP EXPLORATION")
print("=" * 70)

# ============================================
# 1. NC Data Analysis
# ============================================
print("\n--- 1. Fetching ALL NCs ---")
nc_fields = "ID,NC_LABEL,STATUS,STATUS_LABEL,CATEGORY,CLUSTER_NAME,CREATED_AT,UPDATED_AT,APPROVED_AT,CURRENT_HANDLER,AD_HOC,ARCHIVED,DEFECT_TYPE,QUANTITY,DESCRIPTION,DEBIT,DEBIT_REASON,VERSION"
all_ncs = fetch_all("Ncs", nc_fields)
print(f"  Total NCs: {len(all_ncs)}")

# Status breakdown
print("\n  -- NC Statuses --")
statuses = Counter(nc.get("STATUS") for nc in all_ncs)
for s, c in statuses.most_common():
    label = next((nc.get("STATUS_LABEL") for nc in all_ncs if nc.get("STATUS") == s), s)
    print(f"    {s:25s} ({label:25s}): {c}")

# Category breakdown
print("\n  -- NC Categories --")
categories = Counter(nc.get("CATEGORY") for nc in all_ncs)
for cat, c in categories.most_common():
    print(f"    {str(cat):20s}: {c}")

# Cluster breakdown
print("\n  -- NC by Cluster --")
clusters = Counter(nc.get("CLUSTER_NAME") for nc in all_ncs)
for cl, c in clusters.most_common():
    print(f"    {str(cl):20s}: {c}")

# Current handler breakdown
print("\n  -- NC Current Handler --")
handlers = Counter(nc.get("CURRENT_HANDLER") for nc in all_ncs)
for h, c in handlers.most_common():
    print(f"    {str(h):25s}: {c}")

# Ad-hoc vs RFI-based
print("\n  -- Ad-hoc vs RFI-linked --")
adhoc = sum(1 for nc in all_ncs if nc.get("AD_HOC"))
print(f"    Ad-hoc: {adhoc}, RFI-linked: {len(all_ncs) - adhoc}")

# Defect types
print("\n  -- Top 15 Defect Types --")
defects = Counter(nc.get("DEFECT_TYPE") for nc in all_ncs)
for d, c in defects.most_common(15):
    print(f"    {str(d)[:60]:60s}: {c}")

# Debit analysis
print("\n  -- Debit (Financial Penalty) --")
debits = [nc for nc in all_ncs if nc.get("DEBIT") is not None]
print(f"    NCs with debit: {len(debits)} / {len(all_ncs)}")
if debits:
    total_debit = sum(nc.get("DEBIT", 0) for nc in debits)
    print(f"    Total debit amount: {total_debit}")

# NC Aging
print("\n  -- NC Aging (days since created) --")
now = datetime.utcnow()
open_ncs = [nc for nc in all_ncs if nc.get("STATUS") not in ('closed', 'accepted')]
aging_buckets = {"0-3 days": 0, "3-7 days": 0, "7-14 days": 0, "14-30 days": 0, "30+ days": 0}
for nc in open_ncs:
    try:
        created = datetime.fromisoformat(nc["CREATED_AT"].replace("Z", "+00:00")).replace(tzinfo=None)
        days = (now - created).days
        if days <= 3: aging_buckets["0-3 days"] += 1
        elif days <= 7: aging_buckets["3-7 days"] += 1
        elif days <= 14: aging_buckets["7-14 days"] += 1
        elif days <= 30: aging_buckets["14-30 days"] += 1
        else: aging_buckets["30+ days"] += 1
    except:
        pass
for bucket, count in aging_buckets.items():
    print(f"    {bucket:15s}: {count}")

# ============================================
# 2. NC with expanded data (sample)
# ============================================
print("\n--- 2. Fetching NCs with full expand (sample 20) ---")
nc_expand = "WORKAREA($expand=PROJECT($expand=SPV)),WORKLOCATION,CONTRACTOR($expand=VENDOR),ENGINEER,QUALITY,SUBACTIVITY($expand=ACTIVITY($expand=SUBPACKAGE($expand=PACKAGE))),PACKAGE,SCOPES($expand=DESIGNELEMENTLOOKUP)"
expanded_ncs = fetch_with_expand("Ncs", nc_expand, top=20)
print(f"  Got {len(expanded_ncs)} expanded NCs")

# Project breakdown from expanded data
print("\n  -- Projects in NCs --")
projects = defaultdict(lambda: {"count": 0, "spv": "", "type": ""})
for nc in expanded_ncs:
    wa = nc.get("WORKAREA") or {}
    proj = wa.get("PROJECT") or {}
    pname = proj.get("NAME", "Unknown")
    projects[pname]["count"] += 1
    projects[pname]["spv"] = (proj.get("SPV") or {}).get("NAME", "")
    projects[pname]["type"] = proj.get("TYPE", "")
for pname, info in sorted(projects.items(), key=lambda x: -x[1]["count"]):
    print(f"    {pname:40s}: {info['count']} NCs | SPV: {info['spv']} | Type: {info['type']}")

# Package breakdown
print("\n  -- Packages in NCs --")
packages = Counter((nc.get("PACKAGE") or {}).get("NAME", "Unknown") for nc in expanded_ncs)
for p, c in packages.most_common():
    print(f"    {p:20s}: {c}")

# Contractor/Vendor breakdown
print("\n  -- Contractors raising NCs --")
contractors = Counter()
for nc in expanded_ncs:
    contractor = nc.get("CONTRACTOR") or {}
    vendor = contractor.get("VENDOR") or {}
    contractors[vendor.get("NAME", "Unknown")] += 1
for v, c in contractors.most_common():
    print(f"    {str(v)[:50]:50s}: {c}")

# Work locations
print("\n  -- Work Locations --")
locations = Counter((nc.get("WORKLOCATION") or {}).get("NAME", "Unknown") for nc in expanded_ncs)
for l, c in locations.most_common(10):
    print(f"    {l:30s}: {c}")

# Work areas (blocks)
print("\n  -- Work Areas (Blocks) --")
areas = Counter((nc.get("WORKAREA") or {}).get("NAME", "Unknown") for nc in expanded_ncs)
for a, c in areas.most_common(10):
    print(f"    {a:20s}: {c}")

# ============================================
# 3. RFI Data Analysis
# ============================================
print("\n--- 3. Fetching ALL RFIs ---")
rfi_fields = "ID,STATUS,STATUS_LABEL,CLUSTER_NAME,CREATED_AT,UPDATED_AT,CURRENT_HANDLER,RFI_LABEL"
all_rfis = fetch_all("Rfis", rfi_fields)
print(f"  Total RFIs: {len(all_rfis)}")

# RFI Status breakdown
print("\n  -- RFI Statuses --")
rfi_statuses = Counter(rfi.get("STATUS") for rfi in all_rfis)
for s, c in rfi_statuses.most_common():
    label = next((rfi.get("STATUS_LABEL") for rfi in all_rfis if rfi.get("STATUS") == s), s)
    print(f"    {s:25s} ({label:25s}): {c}")

# RFI by cluster
print("\n  -- RFI by Cluster --")
rfi_clusters = Counter(rfi.get("CLUSTER_NAME") for rfi in all_rfis)
for cl, c in rfi_clusters.most_common():
    print(f"    {str(cl):20s}: {c}")

# RFI Current handler
print("\n  -- RFI Current Handler --")
rfi_handlers = Counter(rfi.get("CURRENT_HANDLER") for rfi in all_rfis)
for h, c in rfi_handlers.most_common():
    print(f"    {str(h):25s}: {c}")

# ============================================
# 4. Timeline Analysis
# ============================================
print("\n--- 4. Timeline (NC creation over time) ---")
monthly = defaultdict(int)
for nc in all_ncs:
    try:
        dt = datetime.fromisoformat(nc["CREATED_AT"].replace("Z", "+00:00"))
        monthly[dt.strftime("%Y-%m")] += 1
    except:
        pass
for month in sorted(monthly.keys()):
    bar = "#" * (monthly[month] // 2)
    print(f"    {month}: {monthly[month]:4d} {bar}")

# ============================================
# 5. NC Label pattern analysis
# ============================================
print("\n--- 5. NC Label patterns (first 10) ---")
for nc in all_ncs[:10]:
    print(f"    {nc.get('NC_LABEL', 'N/A')}")

print("\n--- 6. RFI Label patterns (first 10) ---")
for rfi in all_rfis[:10]:
    print(f"    {rfi.get('RFI_LABEL', 'N/A')}")

print("\n" + "=" * 70)
print("  EXPLORATION COMPLETE")
print("=" * 70)
