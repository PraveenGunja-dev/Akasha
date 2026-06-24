import sys
import os
import json
import requests
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from services.p6_service import P6Service

def test_fetch_wind_structure():
    p6 = P6Service()
    p6_object_id = 3105 # MANDVI 300MW
    
    print(f"Fetching WBS and Activities for ProjectObjectId={p6_object_id}")
    
    # Fetch WBS
    wbs_endpoint = f"{p6.base_url}/wbs"
    wbs_params = {
        "Fields": "ObjectId,Code,Name,ParentObjectId",
        "Filter": f"ProjectObjectId={p6_object_id}"
    }
    
    try:
        res = requests.get(wbs_endpoint, headers=p6.headers, params=wbs_params, verify=False)
        res.raise_for_status()
        wbs_data = res.json()
        print(f"Total WBS fetched: {len(wbs_data)}")
        
        # Build WBS tree locally
        wbs_map = {w['ObjectId']: w for w in wbs_data}
        for w in wbs_data:
            w['Children'] = []
            w['Activities'] = []
            
        root_wbs = []
        for w in wbs_data:
            parent_id = w.get('ParentObjectId')
            if parent_id and parent_id in wbs_map:
                wbs_map[parent_id]['Children'].append(w)
            else:
                root_wbs.append(w)
                
        # Fetch Activities
        act_endpoint = f"{p6.base_url}/activity"
        act_params = {
            "Fields": "ObjectId,Id,Name,WBSObjectId,ActualStartDate,ActualFinishDate",
            "Filter": f"ProjectObjectId={p6_object_id}"
        }
        res = requests.get(act_endpoint, headers=p6.headers, params=act_params, verify=False)
        res.raise_for_status()
        act_data = res.json()
        print(f"Total Activities fetched: {len(act_data)}")
        
        for act in act_data:
            wbs_id = act.get('WBSObjectId')
            if wbs_id in wbs_map:
                wbs_map[wbs_id]['Activities'].append(act)
                
        def print_wbs(node, indent=""):
            # Only print if it or its children have "Block", "Test", "Comm", "Trial", "COD"
            name = node.get('Name', '').lower()
            code = node.get('Code', '')
            print(f"{indent}- WBS: {name} (Code: {code}, ID: {node.get('ObjectId')})")
            
            for act in node['Activities']:
                act_name = act.get('Name', '').lower()
                if "cod" in act_name or "trial" in act_name or "comm" in act_name:
                    print(f"{indent}  * Activity: {act_name} (ID: {act.get('Id')})")
                    
            for child in node['Children']:
                print_wbs(child, indent + "  ")
                
        for root in root_wbs:
            print_wbs(root)

    except Exception as e:
        print(f"Error fetching: {e}")

if __name__ == "__main__":
    test_fetch_wind_structure()
