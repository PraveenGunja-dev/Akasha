import os

filepath = r"d:\Akasha_Platform\backend\routers\dashboard.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("    mapping_id: int, ", "    mapping_id: str, \n")
content = content.replace(
    "m = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == mapping_id).first()",
    "m = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == mapping_id).first()"
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Replaced!")
