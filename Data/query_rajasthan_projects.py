import psycopg2
import json

conn = psycopg2.connect(host="localhost", port=3315, database="postgres", user="postgres", password="Prvn@3315")
cursor = conn.cursor()

def search_project(search_str):
    cursor.execute("""
        SELECT id, project_id, project_name_from_p6, project 
        FROM project_mapping 
        WHERE project_id ILIKE %s OR project_name_from_p6 ILIKE %s OR project ILIKE %s
    """, (f'%{search_str}%', f'%{search_str}%', f'%{search_str}%'))
    return cursor.fetchall()

print("Search results for BAIYA:")
for row in search_project("BAIYA"):
    print(row)

print("\nSearch results for BANDHA:")
for row in search_project("BANDHA"):
    print(row)

conn.close()
