import os

file_path = r'd:\Akasha_Platform\frontend\src\features\projects\ProjectWorkspace.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# The Workflow Modal block is from line 3229 (index 3228) to line 3313 (index 3312)
# We need to extract it, and place it at the root level, which means inserting it before the last `    </div>` (around line 3319).

# First, let's find the exact indices by looking for the comment and the closing brace.
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if '              {/* Workflow Modal */}' in line:
        start_idx = i
        break

if start_idx != -1:
    # Find the end of this block. It ends with '              )}' around line 3313
    for i in range(start_idx, len(lines)):
        if '              )}' in line and i > start_idx + 10:
            end_idx = i
            break

if start_idx != -1 and end_idx != -1:
    # Extract the lines
    modal_lines = lines[start_idx:end_idx+1]
    
    # Remove them from the original location
    del lines[start_idx:end_idx+1]
    
    # Find the closing tag of the showDelayedModal block
    # After deleting, the showDelayedModal block ends with
    #             </div>
    #           </div>
    #         </div>
    #       )}
    insert_idx = -1
    for i in range(len(lines)-1, -1, -1):
        if '      )}' in lines[i]:
            insert_idx = i + 1
            break
            
    if insert_idx != -1:
        # Insert the modal lines there
        lines = lines[:insert_idx] + ['\n'] + modal_lines + lines[insert_idx:]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"Successfully moved Workflow Modal block from {start_idx+1}-{end_idx+1} to after line {insert_idx+1}")
    else:
        print("Could not find insert index.")
else:
    print("Could not find the start/end of the Workflow Modal block.")
