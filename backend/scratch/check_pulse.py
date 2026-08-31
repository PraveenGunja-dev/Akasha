import sys
import os
sys.path.append('d:/Akasha_Platform/backend')
from dotenv import load_dotenv
load_dotenv('d:/Akasha_Platform/backend/.env')

from database import SessionLocal
from models import PulseNC, ProjectMaster

db = SessionLocal()
pulse_names = set([nc.project_name for nc in db.query(PulseNC.project_name).all() if nc.project_name])
print("PULSE NAMES:", pulse_names)
