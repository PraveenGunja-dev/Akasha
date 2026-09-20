import os
from dotenv import load_dotenv
load_dotenv(override=True)
from database import SessionLocal
from routers.module_deliveries import get_module_deliveries_summary

db = SessionLocal()
try:
    res = get_module_deliveries_summary(db)
    projects = res.get('projects', [])
    if projects:
        print("Keys returned by the function:", list(projects[0].keys()))
        print("Has ftc_date?", 'ftc_date' in projects[0])
        print("ftc_date value:", projects[0].get('ftc_date'))
    else:
        print("No projects returned.")
finally:
    db.close()
