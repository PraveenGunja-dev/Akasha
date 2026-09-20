import os
from dotenv import load_dotenv
load_dotenv(override=True)
from database import SessionLocal
from sqlalchemy import text
db=SessionLocal()
res=db.execute(text("SELECT name, type, planned_finish_date FROM p6_activity WHERE (name ILIKE '%FTC%' OR name ILIKE '%First Time Charging%') AND type = 'Finish Milestone' LIMIT 20")).fetchall()
for r in res:
    print(r)
