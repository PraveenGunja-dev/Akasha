import os

filepath = 'd:/Akasha_Platform/frontend/src/features/projects/ProjectWorkspace.tsx'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines[1840:1870], start=1841):
    print(f"{i}: {l.rstrip()}")
