import os
import re

file_path = r'd:\Akasha_Platform\frontend\src\features\projects\ProjectWorkspace.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the start of the modal
start_str = "              {/* Workflow Modal */}\n              {showWorkflowModal && ("
start_idx = content.find(start_str)

if start_idx != -1:
    # We need to find the matching closing brace for `{showWorkflowModal && (`
    # The block is roughly 84 lines long
    # Let's just find "              )}\n\n            </div>\n          </div>\n        </div>\n      )}\n    </div>"
    
    # Or just use regex to match the block
    pattern = r'( +\{/\* Workflow Modal \*/\}\n +\{showWorkflowModal && \(\n(?:.*?)\n +\)\}\n)'
    match = re.search(pattern, content[start_idx:], re.DOTALL)
    if match:
        modal_content = match.group(1)
        # Remove it
        new_content = content[:start_idx] + content[start_idx + len(modal_content):]
        
        # Now insert it before the last </div>
        end_idx = new_content.rfind('    </div>\n  );\n}')
        if end_idx != -1:
            new_content = new_content[:end_idx] + modal_content + new_content[end_idx:]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print("Successfully moved the modal!")
        else:
            print("Could not find end tag.")
    else:
        print("Could not match the block.")
else:
    print("Could not find start string.")
