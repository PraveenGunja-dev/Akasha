import json
import os
import sys
import re

os.environ['DATABASE_URL'] = 'postgresql://postgres:Prvn%403315@localhost:5432/Akasha'
sys.path.append('d:/Akasha_Platform/backend')

from database import SessionLocal
from models import MTPOAmount, ProjectMapping

def main():
    file_path = r'd:\Akasha_Platform\Data\NEW31\Get All Invoices Production(E-invoice) json response.txt'
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    invoices = data.get('d', {}).get('results', [])
    work_orders = set(inv.get('workOrderNo') for inv in invoices if inv.get('workOrderNo'))

    db = SessionLocal()
    pos = db.query(MTPOAmount.purchasing_document, MTPOAmount.wbs_element).filter(
        MTPOAmount.purchasing_document.in_(list(work_orders))
    ).all()

    db_po_wbs_map = {po[0]: po[1] for po in pos}
    db_pos_set = set(po[0] for po in pos)
    missing_from_db = work_orders - db_pos_set

    print(f'Total Work Orders from JSON: {len(work_orders)}')
    print(f'Work Orders NOT found in mt_poamount table at all: {len(missing_from_db)}')
    if missing_from_db:
        print(f'List of POs completely missing from DB: {list(missing_from_db)}')

    mappings = db.query(ProjectMapping).all()
    mapped_pos = set()
    unmapped_in_db = []

    for po_num, wbs in db_po_wbs_map.items():
        matched_proj = None
        if wbs:
            for m in mappings:
                prefixes = []
                for val in [m.spv_plant_code, m.agel, m.age6l]:
                    if val:
                        matches = [c.strip()[:6] for c in re.findall(r'H-\S+', str(val).strip()) if len(c.strip()) >= 6]
                        prefixes.extend(matches)
                        prefixes.extend([mx.replace('-', '') for mx in matches])
                if any(wbs.startswith(p) for p in prefixes):
                    matched_proj = m.project_id
                    break
        
        if matched_proj:
            mapped_pos.add(po_num)
        else:
            unmapped_in_db.append({'po': po_num, 'wbs': wbs})

    print(f'\nWork Orders FOUND in DB, but could not be mapped to any project: {len(unmapped_in_db)}')
    for item in unmapped_in_db:
        print(f"PO: {item['po']} - WBS: {item['wbs']}")

if __name__ == '__main__':
    main()
