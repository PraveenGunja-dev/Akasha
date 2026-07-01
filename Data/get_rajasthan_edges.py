import psycopg2
import json

conn = psycopg2.connect(host="localhost", port=3315, database="postgres", user="postgres", password="Prvn@3315")
cursor = conn.cursor()

print("=" * 80)
print("RAJASTHAN UNMAPPED TRANSMISSION LINES (EDGES)")
print("=" * 80)

cursor.execute("""
    SELECT id, from_label, to_label, projects
    FROM tc_network_edge
    WHERE region = 'Rajasthan'
    ORDER BY id
""")
edges = cursor.fetchall()

json_output = []
for edge in edges:
    edge_id, from_label, to_label, projects_raw = edge
    json_output.append({
        "edge_id": edge_id,
        "from_substation": from_label,
        "to_substation": to_label,
        "current_projects_json": projects_raw
    })

print(json.dumps(json_output, indent=2))

conn.close()
