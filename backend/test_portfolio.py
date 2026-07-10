from database import SessionLocal
import models

db = SessionLocal()
portfolio = "Solar Khavda"
query = db.query(models.ProjectMapping).filter(
    (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
    (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
)
mappings = query.all()
print(f"Found {len(mappings)} mappings for {portfolio}")

portfolio = "BESS"
query = db.query(models.ProjectMapping).filter(
    (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
    (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
)
print(f"Found {len(query.all())} mappings for {portfolio}")
