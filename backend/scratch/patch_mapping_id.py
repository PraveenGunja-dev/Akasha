import os
import re

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(backend_dir, "services", "project_service_profile.py")

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Add mapping_id
if '"mapping_id": m.id' not in content:
    content = re.sub(
        r'("projectId": p6_proj\.project_id if p6_proj else \(m\.project_id or ""\),)',
        r'\1\n            "mapping_id": m.id,',
        content
    )

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("project_service_profile.py patched successfully.")
