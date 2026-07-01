import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
import models
db = SessionLocal()

print('--- All Mappings ---')
maps = db.query(models.ProjectMapping).all()
for m in maps:
    if 'siyamb' in str(m.project).lower() or 'siyamb' in str(m.project_name_from_p6).lower():
        print(f'Siyambar Map ID: {m.id}, Project: {m.project}, P6: {m.project_name_from_p6}')
    if 'bandha' in str(m.project).lower() or 'bandha' in str(m.project_name_from_p6).lower():
        print(f'Bandha Map ID: {m.id}, Project: {m.project}, P6: {m.project_name_from_p6}')
