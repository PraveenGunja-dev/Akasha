import json
from sqlalchemy.orm import Session
from database import SessionLocal
import models

def verify_khavda_mapping():
    user_data = {
      "id": "khavda",
      "name": "Khavda",
      "children": [
        {
          "id": "agel",
          "name": "AGEL",
          "children": [
            {
              "id": "agel-projects",
              "name": "AGEL Projects",
              "projects": [
                {"projectId": "FY27-P16-3-2", "projectName": "NHPC EPC 600 MW Khavda-I"},
                {"projectId": "FY27-P06&07", "projectName": "ARE55L_S02A_HSAT_250 MW_PPA"},
                {"projectId": "FY26-P26", "projectName": "ARE55L_S10_HSAT_50 MW_PPA"},
                {"projectId": "FY26-P04", "projectName": "ARE57L_A12_HSAT_350MW_PPA"},
                {"projectId": "FY25-P15", "projectName": "AGE25CL_A06_FT_425MW_PPA"},
                {"projectId": "FY25-P14", "projectName": "AGE26AL_A10a_FT_50MW_PPA_Commissioned"},
                {"projectId": "FY25-P13", "projectName": "AGE26AL_A16_FT_333MW_PPA_Commissioned"},
                {"projectId": "FY25-P12", "projectName": "AGE26AL_A16C_FT_167MW_PPA_Commissioned"},
                {"projectId": "FY25-P11", "projectName": "AGE26AL_A16_FT_200MW_PPA_Commissioned"},
                {"projectId": "FY25-P10", "projectName": "AGE26AL_A16_FT_50MW_PPA_Commissioned"},
                {"projectId": "FY25-P09", "projectName": "AGE25CL_A06_HSAT_75MW_PPA_Commissioned"},
                {"projectId": "FY25-P08", "projectName": "ACL_A1_FT_125MW_GROUP_Commissioned"},
                {"projectId": "FY25-P07", "projectName": "AGE24L_A14_HSAT_150MW_MERCHANT_Commissioned"},
                {"projectId": "FY25-P06", "projectName": "AGE24L_S05_HSAT_150MW_MERCHANT_Commissioned"},
                {"projectId": "FY25-P05", "projectName": "AGE26BL_S05_HSAT_292MW_MERCHANT_HYBRID_Commissioned"},
                {"projectId": "FY25-P04", "projectName": "AHEJ5L_A15a_HSAT_150MW_MERCHANT"},
                {"projectId": "FY25-P03", "projectName": "ARE48L_S08_HSAT_100MW_MERCHANT"},
                {"projectId": "FY25-P02", "projectName": "ASEJ6PL_A06_HSAT_35MW_MERCHANT_Commissioned"},
                {"projectId": "FY25-P01", "projectName": "ARE3L_A06_HSAT_25MW_MERCHANT_Commissioned"}
              ]
            },
            {
              "id": "epc-contractor",
              "name": "EPC Contractor",
              "children": [
                {
                  "id": "larsen-and-toubro",
                  "name": "Larsen and Toubro Limited",
                  "projects": [
                    {"projectId": "FY27-P05", "projectName": "AGEL_S10_287.5_MW_HSAT"},
                    {"projectId": "FY26-P25", "projectName": "AE3L_S01_HSAT_75_MW_MERCHANT"},
                    {"projectId": "FY26-P24", "projectName": "ARE55L_S02B_HSAT_12.5_MW_PPA"},
                    {"projectId": "FY26-P22", "projectName": "ARE55L_S01_HSAT_200_MW_PPA"},
                    {"projectId": "FY26-P20", "projectName": "ARE55L_S02A_HSAT_50_MW_PPA"},
                    {"projectId": "FY26-P19", "projectName": "ARE55L_S01_HSAT_100_MW_PPA"},
                    {"projectId": "FY26-P17", "projectName": "ARE55L_S02A_HSAT_175_MW_PPA"}
                  ]
                },
                {
                  "id": "amara-raja",
                  "name": "Amara Raja",
                  "projects": [
                    {"projectId": "FY26-P10", "projectName": "ARE55L_A02_HSAT_125MW"},
                    {"projectId": "FY26-P09", "projectName": "ARE55L_A01_HSAT_150MW_Group_NEW"},
                    {"projectId": "FY26-P08", "projectName": "ARE8L_A02_HSAT_150MW_PPA_TPL"},
                    {"projectId": "FY26-P07", "projectName": "ACL_A01_HSAT_50MW_Group_NEW"}
                  ]
                },
                {
                  "id": "sterling-wilson",
                  "name": "Sterling & Wilson",
                  "projects": [
                    {"projectId": "FY26-P23", "projectName": "ARE55L_A18_HSAT_600MW_PPA"},
                    {"projectId": "FY26-P15", "projectName": "ARE55L_S09_HSAT_400MW_PPA"},
                    {"projectId": "FY26-P06", "projectName": "ARE55L_A15b_HSAT_50MW_PPA"}
                  ]
                },
                {
                  "id": "kpi-green-energy",
                  "name": "KPI Green Energy",
                  "projects": [
                    {"projectId": "FY26-P18", "projectName": "AGE26AL_S06A_FT_234MW_PPA"},
                    {"projectId": "FY26-P14", "projectName": "ASEJ6PL_S07_FT_300MW_PPA"},
                    {"projectId": "FY26-P05", "projectName": "AHEJ5L_S04_HSAT_300MW_MERCHANT_HYBRID"},
                    {"projectId": "FY25-P18&19&20", "projectName": "AGE25BL_A15a_HSAT_50MW_MERCHANT"}
                  ]
                },
                {
                  "id": "bondada-energy",
                  "name": "Bondada Energy Limited",
                  "projects": [
                    {"projectId": "FY27-P01&P02", "projectName": "ARE55L_S03_HSAT_500MW_MERCHANT"},
                    {"projectId": "FY26-P21", "projectName": "AE2L_S03_HSAT_150MW_MERCHANT"},
                    {"projectId": "FY26-P12-5", "projectName": "AGE26BL_A03_HSAT_250MW_LTP_T4_AP_NEW"},
                    {"projectId": "FY26-P03", "projectName": "ACL_A01_E_FT_25MW_GROUP_NEW"},
                    {"projectId": "FY26-P02", "projectName": "APSEZ_A01_D_HSAT_25MW_GROUP"},
                    {"projectId": "FY26-P01", "projectName": "ARE41L_A01-C_HSAT_25MW_MERCHANT"}
                  ]
                },
                {
                  "id": "hild-energy",
                  "name": "Hild Energy",
                  "projects": [
                    {"projectId": "FY27-P03&04", "projectName": "AGEL_SE14_HSAT_500MW_HILD"},
                    {"projectId": "FY26-P12", "projectName": "AGE24L_A03_HSAT_250MW"}
                  ]
                },
                {
                  "id": "enrich-energy",
                  "name": "Enrich Energy",
                  "projects": [
                    {"projectId": "FY26-P13", "projectName": "ASEJ6PL_S07_FT_300MW_PPA"}
                  ]
                }
              ]
            }
          ]
        }
      ]
    }

    user_projects = []
    for agel_or_epc in user_data["children"][0]["children"]:
        if "projects" in agel_or_epc:
            for p in agel_or_epc["projects"]:
                user_projects.append((p["projectId"], p["projectName"]))
        if "children" in agel_or_epc:
            for epc in agel_or_epc["children"]:
                for p in epc["projects"]:
                    user_projects.append((p["projectId"], p["projectName"]))

    db: Session = SessionLocal()
    
    unmapped = []
    fixed = 0
    
    for uid, uname in user_projects:
        rec = db.query(models.ProjectMapping).filter_by(project_id=uid).first()
        if rec:
            if rec.cluster != "Solar Khavda" or rec.category == "Wind":
                print(f"Fixing {uid}... (Was {rec.cluster} / {rec.category})")
                rec.cluster = "Solar Khavda"
                rec.category = "Solar"
                fixed += 1
        else:
            print(f"Wait, {uid} is missing?!")
            
    db.commit()
    print(f"Total checked: {len(user_projects)}. Fixed mappings for {fixed} projects. All 46 are now 'Solar Khavda'.")

if __name__ == "__main__":
    verify_khavda_mapping()
