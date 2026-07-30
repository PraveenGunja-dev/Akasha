import os
import re

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(os.path.dirname(backend_dir), "frontend", "src", "features", "projects", "ProjectWorkspace.tsx")

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the specific escaped quotes injected by previous script
content = content.replace("useState<\\'old\\' | \\'slr\\'>(\\'old\\');", "useState<'old' | 'slr'>('old');")
content = content.replace("{sapSubTab === \\'old\\' && (", "{sapSubTab === 'old' && (")
content = content.replace("{sapSubTab === \\'slr\\' && (", "{sapSubTab === 'slr' && (")

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Quotes fixed.")
