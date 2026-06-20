import pandas as pd
from database import engine

query = """
SELECT pm.project_name_from_p6 as "P6 Project Name",
       tc.pss as "PSS",
       tc.project as "TC Project Name"
FROM tc_project_entry tc
LEFT JOIN project_mapping pm ON pm.id = tc.mapping_id
"""

try:
    df = pd.read_sql_query(query, engine)
    with open('p6_pss_tc_mapping.md', 'w') as f:
        f.write(df.to_markdown(index=False))
    print("Mapping created in p6_pss_tc_mapping.md")
except Exception as e:
    print(f"Error: {e}")
