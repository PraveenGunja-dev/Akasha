import sys

with open('d:\\Akasha_Platform\\frontend\\src\\components\\sections\\ProjectWorkspace.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "activeTab === 'p6'" in l:
        print("P6 Tab start:", i)
    if "activeTab === 'overview'" in l:
        print("Overview Tab start:", i)
