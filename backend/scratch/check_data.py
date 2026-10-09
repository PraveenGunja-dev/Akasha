import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'), override=True)
from sqlalchemy import create_engine, text, inspect

engine = create_engine(os.getenv('DATABASE_URL'))
insp = inspect(engine)
tables = sorted(insp.get_table_names())

conn = engine.connect()
for t in tables:
    res = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"'))
    count = res.scalar()
    status = 'HAS DATA' if count > 0 else 'EMPTY'
    print(f'  {t:40s} {count:>8} rows  {status}')
conn.close()
