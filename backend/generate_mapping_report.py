import pandas as pd
from database import engine

query = """
SELECT 
    pm.project_id as "P6 Project ID",
    pm.project_name_from_p6 as "P6 Project Name",
    pm.spv_plant_code as "SAP Machinery Code",
    pm.agel as "SAP Supply Code (AGEL)",
    pm.module_wbs as "SAP Module WBS",
    STRING_AGG(DISTINCT tc.phase, ', ') as "TC Phase Mapped",
    STRING_AGG(DISTINCT tc.project, ', ') as "TC Project Mapped"
FROM project_mapping pm
LEFT JOIN tc_project_entry tc ON tc.mapping_id = pm.id
GROUP BY 
    pm.project_id, pm.project_name_from_p6, pm.spv_plant_code, pm.agel, pm.module_wbs
ORDER BY pm.project_name_from_p6
"""

df = pd.read_sql(query, engine)
df.fillna('N/A', inplace=True)
md = df.to_markdown(index=False)

with open('mapping_report.md', 'w') as f:
    f.write(md)
print("Done")
