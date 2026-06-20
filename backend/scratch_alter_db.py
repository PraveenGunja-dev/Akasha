import os
import sys
sys.path.append(os.getcwd())
from database import engine
from sqlalchemy import text

def alter_db():
    with engine.connect() as conn:
        conn.execute(text('ALTER TABLE mt_poamount ADD COLUMN wbs_element VARCHAR;'))
        conn.execute(text('CREATE INDEX ix_mt_poamount_wbs_element ON mt_poamount(wbs_element);'))
        conn.commit()
    print('Table altered.')

if __name__ == "__main__":
    alter_db()
