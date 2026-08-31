import os

file_path = r'd:\Akasha_Platform\frontend\src\features\projects\ProjectWorkspace.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Search for the start of the Workflow Modal block
start_idx = -1
for i, line in enumerate(lines):
    if '{/* Workflow Modal */}' in line:
        start_idx = i
        break

if start_idx == -1:
    print("Could not find Workflow Modal start")
    exit(1)

# Keep track of brace depth to find the end of the showWorkflowModal && ( block
depth = 0
in_block = False
end_idx = -1

for i in range(start_idx + 1, len(lines)):
    line = lines[i]
    if '{showWorkflowModal && (' in line:
        in_block = True
    
    if in_block:
        for char in line:
            if char == '{' or char == '(':
                depth += 1
            elif char == '}' or char == ')':
                depth -= 1
        
        if depth == 0:
            end_idx = i
            break

if end_idx == -1:
    print("Could not find Workflow Modal end")
    exit(1)

# Extract lines
modal_lines = lines[start_idx:end_idx+1]

# Delete them from original position
del lines[start_idx:end_idx+1]

# Find where to insert (before the final closing div and return)
insert_idx = -1
for i in range(len(lines)-1, -1, -1):
    if '  );' in lines[i]:
        insert_idx = i - 1
        break

if insert_idx == -1:
    print("Could not find insert idx")
    exit(1)

# Insert the modal
lines.insert(insert_idx, '\n')
for line in reversed(modal_lines):
    lines.insert(insert_idx, line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"Successfully moved modal from {start_idx} - {end_idx} to {insert_idx}")
