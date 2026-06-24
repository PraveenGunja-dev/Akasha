from database import engine
from sqlalchemy import text

try:
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE mt_inventory ADD COLUMN base_unit VARCHAR;'))
    print("Column added successfully")
except Exception as e:
    print(f"Error adding column: {e}")
