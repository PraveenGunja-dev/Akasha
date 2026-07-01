import psycopg2
import json

conn = psycopg2.connect(host="localhost", port=3315, database="postgres", user="postgres", password="Prvn@3315")
cursor = conn.cursor()

# Project Mappings Based on User Image
baiya_project_name = "ASEB1PL_BAIYA_FT_600MW_PPA"
bandha_project_name = "AGE25BL_BANDHA_FT_500MW_PPA"
baiya_mapping_id = 317
bandha_mapping_id = 316

print("Updating Rajasthan Mappings based on Substations...")

# 1. Update Fatehgarh-III edges -> BAIYA
cursor.execute("""
    UPDATE tc_network_edge
    SET mapping_id = %s, projects = %s
    WHERE region = 'Rajasthan' AND (from_label ILIKE 'Fatehgarh%%' OR to_label ILIKE 'Fatehgarh%%')
    RETURNING id, from_label, to_label
""", (baiya_mapping_id, json.dumps({"projects": [baiya_project_name], "phases": []})))

fatehgarh_edges = cursor.fetchall()
print(f"Updated {len(fatehgarh_edges)} edges for Fatehgarh-III -> BAIYA project:")
for e in fatehgarh_edges:
    print(f"  - Edge ID {e[0]}: {e[1]} -> {e[2]}")


# 2. Update Ramgarh edges -> BANDHA
cursor.execute("""
    UPDATE tc_network_edge
    SET mapping_id = %s, projects = %s
    WHERE region = 'Rajasthan' AND (from_label ILIKE 'Ramgarh%%' OR to_label ILIKE 'Ramgarh%%')
    RETURNING id, from_label, to_label
""", (bandha_mapping_id, json.dumps({"projects": [bandha_project_name], "phases": []})))

ramgarh_edges = cursor.fetchall()
print(f"\nUpdated {len(ramgarh_edges)} edges for Ramgarh -> BANDHA project:")
for e in ramgarh_edges:
    print(f"  - Edge ID {e[0]}: {e[1]} -> {e[2]}")

conn.commit()
conn.close()
