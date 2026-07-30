import os
import re

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def patch_file(filepath):
    if not os.path.exists(filepath):
        print(f"Not found: {filepath}")
        return
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update dict gets
    content = content.replace("req_by_plant.get(agel_code_str, 0)", "req_by_plant.get(agel_code_str, 0) or req_by_plant.get(age6l_code_str, 0)")
    content = content.replace("inv_by_plant.get(agel_code_str, 0)", "inv_by_plant.get(agel_code_str, 0) or inv_by_plant.get(age6l_code_str, 0)")
    content = content.replace("it_by_plant.get(agel_code_str, 0)", "it_by_plant.get(agel_code_str, 0) or it_by_plant.get(age6l_code_str, 0)")
    content = content.replace("po_qty_by_plant.get(agel_code_str, 0)", "po_qty_by_plant.get(agel_code_str, 0) or po_qty_by_plant.get(age6l_code_str, 0)")
    content = content.replace("po_val_by_plant.get(agel_code_str, 0)", "po_val_by_plant.get(agel_code_str, 0) or po_val_by_plant.get(age6l_code_str, 0)")
    content = content.replace("po_delivered_val_by_plant.get(agel_code_str, 0)", "po_delivered_val_by_plant.get(agel_code_str, 0) or po_delivered_val_by_plant.get(age6l_code_str, 0)")

    # 2. Add age6l_code_str definitions if agel_code_str is present
    if "agel_code_str = str(m.agel).strip() if m.agel else \"\"" in content and "age6l_code_str =" not in content:
        content = content.replace("agel_code_str = str(m.agel).strip() if m.agel else \"\"", 
                                  "agel_code_str = str(m.agel).strip() if m.agel else \"\"\n        age6l_code_str = str(m.age6l).strip() if m.age6l else \"\"")
                                  
    if "agel_code = str(m.agel or \"\").strip()" in content and "age6l_code =" not in content:
        content = content.replace("agel_code = str(m.agel or \"\").strip()", 
                                  "agel_code = str(m.agel or \"\").strip()\n        age6l_code = str(m.age6l or \"\").strip()")
        
    if "if plant_code or agel_code:" in content:
        content = content.replace("if plant_code or agel_code:", "if plant_code or agel_code or age6l_code:")

    # 3. Update SQLAlchemy OR queries
    # models.MTPOAmount.plant_code == agel_code)
    # models.MTPOAmount.plant_code == str(m.agel).strip())
    
    # regex for exact match
    content = re.sub(
        r'\(models\.([A-Za-z]+)\.([a-z_]+)\s*==\s*str\(m\.agel\)\.strip\(\)\)',
        r'(models.\1.\2 == str(m.agel).strip()) | (models.\1.\2 == str(m.age6l).strip())',
        content
    )
    
    content = re.sub(
        r'\(models\.([A-Za-z]+)\.([a-z_]+)\s*==\s*agel_code\)',
        r'(models.\1.\2 == agel_code) | (models.\1.\2 == age6l_code)',
        content
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print(f"Successfully patched {filepath}")


if __name__ == "__main__":
    files_to_patch = [
        os.path.join(backend_dir, "routers", "dashboard.py"),
        os.path.join(backend_dir, "services", "project_service.py"),
        os.path.join(backend_dir, "services", "project_service_profile.py"),
        os.path.join(backend_dir, "services", "project_service_profile2.py"),
    ]
    
    for f in files_to_patch:
        patch_file(f)
