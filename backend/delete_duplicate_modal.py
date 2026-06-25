import sys

filepath = r'd:\Akasha_Platform\frontend\src\components\sections\ProjectWorkspace.tsx'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, l in enumerate(lines):
    if '{/* ── Delayed Activities Modal ── */}' in l:
        start_idx = i
    if '{/* ── Modals ── */}' in l:
        end_idx = i

if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
    del lines[start_idx:end_idx]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'Deleted {end_idx - start_idx} lines from {start_idx} to {end_idx}')
else:
    print(f'Could not find indices: {start_idx}, {end_idx}')
