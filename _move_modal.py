with open("frontend/src/features/projects/ProjectWorkspace.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

# The modal starts at line 3255 (index 3254) and ends at line 3345 (index 3344)
start_idx = 3254
end_idx = 3344

modal_lines = lines[start_idx:end_idx+1]
del lines[start_idx:end_idx+1]

# Insert after line 3066 (index 3065)
# Wait, if we delete lines from the bottom, the top indices are unaffected!
insert_idx = 3066
lines = lines[:insert_idx] + modal_lines + lines[insert_idx:]

with open("frontend/src/features/projects/ProjectWorkspace.tsx", "w", encoding="utf-8") as f:
    f.writelines(lines)
