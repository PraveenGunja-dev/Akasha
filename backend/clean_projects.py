import json
from database import SessionLocal
from models import ProjectMapping

user_mapping_str = """[
    {
      "Sr_no": 1,
      "Project": "MLP T1  PPA - J&K",
      "P6_Project_Name": "AGE26AL_A16_FT_50MW_PPA_Commissioned"
    },
    {
      "Sr_no": 2,
      "Project": "MLP T1  PPA - CG",
      "P6_Project_Name": "AGE26AL_A16_FT_200MW_PPA"
    },
    {
      "Sr_no": 5,
      "Project": "MLP T1  PPA - TN",
      "P6_Project_Name": "AGE26AL_A16C_FT_167MW_PPA"
    },
    {
      "Sr_no": 8,
      "Project": "MLP T1  PPA - OR",
      "P6_Project_Name": "AGE26AL_A16_FT_333MW_PPA"
    },
    {
      "Sr_no": 11,
      "Project": "MLP T4 PPA - AP",
      "P6_Project_Name": "AGE26BL_A03_HSAT_250 MW_MLP T4 AP NEW"
    },
    {
      "Sr_no": 13,
      "Project": "MLP T4 PPA - AP",
      "P6_Project_Name": "AGE24L_A03_HSAT_250 MW"
    },
    {
      "Sr_no": 22,
      "Project": "MLP T2 PPA - AP",
      "P6_Project_Name": null
    },
    {
      "Sr_no": 31,
      "Project": "SECI H-3 PPA",
      "P6_Project_Name": "AHEJ5L PSS-05 (39 Loc.)"
    },
    {
      "Sr_no": 35,
      "Project": "AGEL Merchant (Solar)",
      "P6_Project_Name": "AGE24L_A14_HSAT_150MW_MERCHANT_Commissioned"
    },
    {
      "Sr_no": 45,
      "Project": "AESL PPA (C&I) - Solar",
      "P6_Project_Name": "ARE41L_A01- C_HSAT_25 MW_MERCHANT"
    },
    {
      "Sr_no": 46,
      "Project": "Group - Port (Hybrid - Solar)",
      "P6_Project_Name": "APSEZ_A01- D_HSAT_25 MW_GROUP"
    },
    {
      "Sr_no": 53,
      "Project": "Group - Cement (Hybrid - Solar)",
      "P6_Project_Name": "ACL_A01- E_FT_25MW_GROUP NEW"
    },
    {
      "Sr_no": 54,
      "Project": "Group - Cement (Hybrid - Solar)",
      "P6_Project_Name": "ACL_A01_HSAT_50MW_Group_NEW"
    },
    {
      "Sr_no": 55,
      "Project": "MSEDCL PPA Ph-1",
      "P6_Project_Name": "ARE55L_A01_HSAT_150MW_Group_NEW"
    },
    {
      "Sr_no": 57,
      "Project": "TPL-D PPA",
      "P6_Project_Name": "ARE8L_A02_HSAT_150MW_Merc"
    },
    {
      "Sr_no": 58,
      "Project": "MSEDCL PPA Ph-1",
      "P6_Project_Name": "ARE55L_A02_HSAT_125MW"
    },
    {
      "Sr_no": 64,
      "Project": "Group - Port (Hybrid)",
      "P6_Project_Name": "APSEZ_A01- D_HSAT_25 MW_GROUP"
    }
]"""

user_mapping = json.loads(user_mapping_str)
valid_p6_names = {item['P6_Project_Name'].strip() for item in user_mapping if item.get('P6_Project_Name')}

db = SessionLocal()
all_mappings = db.query(ProjectMapping).all()
deleted = 0
kept = 0

for m in all_mappings:
    if m.category == 'Wind':
        kept += 1
        continue
        
    is_valid = False
    if m.project_name_from_p6 and m.project_name_from_p6.strip() in valid_p6_names:
        is_valid = True
    elif m.project and m.project.strip() in valid_p6_names:
        is_valid = True
    elif m.project_id and m.project_id.strip() in valid_p6_names:
        is_valid = True
        
    if is_valid:
        kept += 1
    else:
        db.delete(m)
        deleted += 1

db.commit()
print(f'Kept {kept} required projects (including Wind). Deleted {deleted} unrequired projects.')
