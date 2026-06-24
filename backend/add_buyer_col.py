import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE mt_poamount ADD COLUMN buyer_name VARCHAR;"))
        print("Successfully added buyer_name to mt_poamount")
    except Exception as e:
        print(f"Error adding column (it might already exist): {e}")
