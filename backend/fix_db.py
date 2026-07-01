import re
from database import SessionLocal
from models import Notification

db = SessionLocal()
notifs = db.query(Notification).all()

budget_pattern = re.compile(r"Resource '(.*?)' actual units \((.*?)\) exceed budgeted units \((.*?)\)")
budget_cost_pattern = re.compile(r"Resource '(.*?)' actual cost \((.*?)\) exceed budgeted cost \((.*?)\)")
critical_date_pattern = re.compile(r"Activity '(.*?)'.*?\((.*?)\).*?\((.*?)\)")

for n in notifs:
    if n.change_type == 'Budget Exceeded':
        match = budget_pattern.search(n.message)
        if not match:
            match = budget_cost_pattern.search(n.message)
            
        if match:
            n.activity_name = match.group(1)
            n.new_value = match.group(2)
            n.old_value = match.group(3)
    elif n.change_type == 'Critical Date Slip':
        match = critical_date_pattern.search(n.message)
        if match:
            n.activity_name = match.group(1)
            n.old_value = match.group(2)
            n.new_value = match.group(3)

db.commit()
print('Successfully fixed the dummy values!')
