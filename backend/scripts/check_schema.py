import sqlite3
import os

def check_db():
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'akasha.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get column names
    cursor.execute("PRAGMA table_info(project_mapping)")
    columns = cursor.fetchall()
    print("ProjectMapping Columns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
        
    # Get a sample row
    cursor.execute("SELECT * FROM project_mapping LIMIT 1")
    row = cursor.fetchone()
    if row:
        print("\nSample Row:")
        for i, val in enumerate(row):
            print(f"  {columns[i][1]}: {val}")
    else:
        print("\nTable is empty.")
        
    conn.close()

if __name__ == "__main__":
    check_db()
