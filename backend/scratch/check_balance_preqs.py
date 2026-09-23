import os
import sys
import pandas as pd

backend_dir = r"d:\adani\Akasha\backend"
sys.path.insert(0, backend_dir)

from database import SessionLocal
import models
from routers.module_deliveries import get_module_deliveries_summary
from services.module_wattage import module_watts

db = SessionLocal()

print("=" * 80)
print("1. CURRENT BALANCE ORDERING (MWp) BY PROJECT")
print("=" * 80)
summary = get_module_deliveries_summary(db=db)
items = summary.get('projects', [])
print(f"Total projects tracked: {len(items)}")
print(f"Portfolio totals: {summary.get('totals')}")

balance_projects = []
for it in items:
    bal_order = it.get('balance_ordering_mwp', 0.0)
    cap = it.get('capacity_mwp', 0.0)
    ordered = it.get('ordered_mwp', 0.0)
    wbs = it.get('wbs_element', '')
    pname = it.get('project_name', '')
    pid = it.get('project_id', '')
    if bal_order > 0:
        balance_projects.append({
            'project_id': pid,
            'name': pname,
            'wbs': wbs,
            'cap_mwp': cap,
            'ordered_mwp': ordered,
            'balance_mwp': bal_order
        })

df_bal = pd.DataFrame(balance_projects).sort_values('balance_mwp', ascending=False)
print(f"Projects with Balance Ordering: {len(df_bal)}")
print(f"Total Portfolio Balance Ordering: {df_bal['balance_mwp'].sum():,.2f} MWp")
print("\nTop projects with Balance Ordering:")
print(df_bal.head(15).to_string())

print("\n" + "=" * 80)
print("2. CHECKING PREQ (REQUISITIONS) IN DATABASE (mt_slr_data) FOR THESE WBS")
print("=" * 80)
wbs_prefixes = [p['wbs'][:6] for p in balance_projects if p['wbs']]
clean_prefixes = set([p.replace('H-', '').replace('-', '') for p in wbs_prefixes if p])
print("Prefixes to check:", clean_prefixes)

# Query mt_slr_data for PReq
preqs = db.query(models.MTSLRData).filter(
    models.MTSLRData.type == 'PReq'
).all()
print(f"Total PReqs in mt_slr_data: {len(preqs)}")

mod_preqs = []
for p in preqs:
    desc = str(p.description or '')
    comm = p.commitment_amount or 0
    act = p.actual_amount or 0
    tot = comm + act
    p_code = p.plant_code or ''
    # Check if matching any balance project
    is_bal = any(cp in p_code for cp in clean_prefixes) or any(cp in str(p.wbs_element) for cp in clean_prefixes)
    is_mod = any(k in desc.lower() for k in ['module', 'panel', 'solar', 'pv', 'cell'])
    if is_mod or (is_bal and tot > 0):
        mod_preqs.append({
            'doc': p.po_document,
            'plant': p_code,
            'wbs': p.wbs_element,
            'desc': desc,
            'comm_cr': comm / 1e7,
            'act_cr': act / 1e7,
            'tot_cr': tot / 1e7,
            'is_module': is_mod,
            'matches_balance_project': is_bal
        })

df_mp = pd.DataFrame(mod_preqs)
print(f"\nFound {len(df_mp)} relevant PReq lines in SLR:")
if not df_mp.empty:
    print(df_mp[df_mp['is_module']].to_string())
    print("\nNon-module PReqs on balance projects (e.g. EPC / Turnkey / Balance of Plant):")
    print(df_mp[~df_mp['is_module']].head(20).to_string())

print("\n" + "=" * 80)
print("3. CHECKING PREQs IN NEW FILE (ZPSPS007 4.XLSX)")
print("=" * 80)
df_new = pd.read_excel(r"d:\adani\Akasha\Data\19_09\ZPSPS007 4.XLSX")
preq_in_new = df_new[df_new['Type'].astype(str).str.strip() == 'PReq']
print(f"PReq rows in new file: {len(preq_in_new)}")
if not preq_in_new.empty:
    print(preq_in_new[['C.Document', 'WBS Element', 'Short text', 'C.Quantity', 'Commitment Amt']])

db.close()
