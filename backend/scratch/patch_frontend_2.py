import os
import re

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(os.path.dirname(backend_dir), "frontend", "src", "features", "projects", "ProjectWorkspace.tsx")

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove the top level SLR Data TabBtn
content = re.sub(
    r'\s*<TabBtn active=\{activeTab === \'slr\'\} label="SLR Data" icon=\{Receipt\} onClick=\{\(\) => setActiveTab\(\'slr\'\)\} />\n',
    '\n',
    content
)

# 2. Add SAP Sub-tab state
if 'sapSubTab' not in content:
    content = re.sub(
        r'(  const \[slrFilter, setSlrFilter\] = useState<\'ALL\' \| \'SPV\' \| \'AGEL\' \| \'AGE6L\'>\(\'ALL\'\);)',
        r'\1\n  const [sapSubTab, setSapSubTab] = useState<\'old\' | \'slr\'>(\'old\');',
        content
    )

# 3. Modify the SAP Intelligence tab to include sub-tabs and render either old SAP data or SLR data.
# First, extract the SLR tab content block and remove it from its current position
slr_tab_match = re.search(r'(\s*\{\/\* ════════ SLR DATA TAB \(NEW\) ════════ \*\/}.*?)(?=\s*\{\/\* ════════ P6 DEEP DIVE TAB)', content, re.DOTALL)
slr_content = ""
if slr_tab_match:
    slr_content = slr_tab_match.group(1)
    content = content.replace(slr_content, '')
    
    # Clean up the slr_content to remove {activeTab === 'slr' && ( ... )} wrapper
    slr_content = re.sub(r'\{\/\* ════════ SLR DATA TAB \(NEW\) ════════ \*\/\}', '', slr_content)
    slr_content = re.sub(r'^\s*\{activeTab === \'slr\' && \(\s*<div className="space-y-6">', '<div className="space-y-6">', slr_content, flags=re.MULTILINE)
    # Remove the closing wrapper
    slr_content = slr_content.rstrip()
    if slr_content.endswith(')}'):
        slr_content = slr_content[:-2]
        
# Now, find the SAP Tab content
sap_tab_pattern = r'(<h2 className="text-lg font-semibold text-foreground flex items-center gap-2">\s*<Database className="w-5 h-5 text-primary/70" /> SAP Intelligence\s*</h2>)'

sub_tab_ui = """\\1
                    <div className="flex bg-muted/50 p-1 rounded-lg">
                      <button 
                        onClick={() => setSapSubTab('old')}
                        className={`px-4 py-1.5 text-sm font-semibold rounded-md transition-colors ${sapSubTab === 'old' ? 'bg-background shadow text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                      >
                        PO (Old)
                      </button>
                      <button 
                        onClick={() => setSapSubTab('slr')}
                        className={`px-4 py-1.5 text-sm font-semibold rounded-md transition-colors ${sapSubTab === 'slr' ? 'bg-background shadow text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                      >
                        SLR Data (New)
                      </button>
                    </div>"""
                    
content = re.sub(sap_tab_pattern, sub_tab_ui, content)

# Find where the old SAP data rendering starts: {/* SAP Summary Header */} -> then there's the header div, then the grids.
# We need to wrap the grids in `{sapSubTab === 'old' && ( ... )}` and add `{sapSubTab === 'slr' && ( ... slr_content ... )}`

old_data_start_pattern = r'(<div className="grid grid-cols-1 md:grid-cols-5 gap-4">)'
if '{sapSubTab === \'old\'' not in content:
    content = re.sub(
        old_data_start_pattern,
        r'{sapSubTab === \'old\' && (\n                    <>\n                      \1',
        content
    )
    
    # Now find the end of the old SAP data, which is just before {/* ════════ P6 DEEP DIVE TAB ════════ */}
    # but we are inside `activeTab === 'sap'` block.
    # The end of the sap tab is:
    #                 </div>
    #               )}
    #             </div>
    #           )}
    # Let's use a replacement to close the old block and insert the new block.
    
    old_data_end_pattern = r'(?=\s*\{\/\* ════════ P6 DEEP DIVE TAB ════════ \*\/})'
    
    # Actually, we wrapped the old data in <>. The old data ends right before the closing of `activeTab === 'sap'` div.
    content = re.sub(
        r'(\s*</div>\s*)\n(\s*\)\}\s*</div>\s*\)\}\s*\{\/\* ════════ P6 DEEP DIVE TAB)',
        r'\n                    </>\n                  )}\n\n                  {sapSubTab === \'slr\' && (\n                    ' + slr_content.replace('\\', '\\\\') + r'\n                  )}\1\n\2',
        content
    )

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("ProjectWorkspace.tsx SAP Sub-tabs patched successfully.")
