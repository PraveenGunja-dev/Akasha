import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
import models
import pandas as pd

db = SessionLocal()
print("Total POs:", db.query(models.MTPOAmount).count())
print("Total Inventory:", db.query(models.MTInventory).count())
print("Total Consumption:", db.query(models.MTConsumption).count())

wbs = db.query(models.MTPOAmount.wbs_element).distinct().limit(10).all()
print("Some WBS in PO:", [w[0] for w in wbs])

proj_wbs = db.query(models.ProjectMapping.project_id, models.ProjectMapping.module_wbs).filter(models.ProjectMapping.module_wbs.isnot(None)).limit(10).all()
print("Some mapped WBS:", proj_wbs)
