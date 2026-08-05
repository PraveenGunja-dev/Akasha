import os

filepath = 'd:/Akasha_Platform/frontend/src/features/projects/ProjectWorkspace.tsx'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 1. Extract the SLR block from the bottom
# Look for the exact line: <div className="space-y-6 mt-12 pt-8 border-t border-border">
try:
    slr_div_idx = next(i for i, l in enumerate(lines) if 'className="space-y-6 mt-12 pt-8 border-t border-border"' in l)
except StopIteration:
    print("Could not find SLR block at the bottom.")
    exit(1)

# The block starts at slr_div_idx - 1 (which is `<>`) and ends before P6 DEEP DIVE TAB
slr_start = slr_div_idx - 1
p6_idx = next(i for i, l in enumerate(lines) if 'P6 DEEP DIVE TAB (NEW)' in l)

# the end of SLR block is 4 lines before p6_idx:
# 1874:                   </>
# 1875:                   </div>
# 1876:               )}
slr_end = p6_idx - 4

# Extract and delete the block
slr_block_lines = lines[slr_start:slr_end]
del lines[slr_start:slr_end]

print(f"Extracted {len(slr_block_lines)} lines of SLR block from {slr_start} to {slr_end}")

# 2. Extract ONLY the charts and tables from slr_block_lines.
# We don't need the KPI cards because we're moving them to HeroMetrics.
# We don't need the slrLoading check because we handle that at the HeroMetrics level.
# The charts and tables start at `{slrData?.data && slrData.data.length > 0 && (`
try:
    chart_start_idx = next(i for i, l in enumerate(slr_block_lines) if '{slrData?.data && slrData.data.length > 0 && (' in l)
    # The end is 5 lines before the end of slr_block_lines
    chart_end_idx = len(slr_block_lines) - 5
    slr_charts_lines = slr_block_lines[chart_start_idx:chart_end_idx]
except StopIteration:
    print("Could not find charts in SLR block")
    exit(1)

# Convert slr_charts_lines to a proper react conditional
slr_charts_str = "".join(slr_charts_lines)
# Replace `{slrData?.data && slrData.data.length > 0 && (` with `{expandedMetric === 'slr' && slrData?.data && slrData.data.length > 0 && (`
slr_charts_str = slr_charts_str.replace("{slrData?.data && slrData.data.length > 0 && (", "{expandedMetric === 'slr' && slrData?.data && slrData.data.length > 0 && (")

# 3. Add 'slr' to breakdown titles
try:
    transit_title_idx = next(i for i, l in enumerate(lines) if "expandedMetric === 'transit' && 'In-Transit Breakdown'" in l)
    lines.insert(transit_title_idx + 1, "                              {expandedMetric === 'slr' && 'SLR Purchase Orders Breakdown'}\n")
except StopIteration:
    print("Could not find transit breakdown title")
    exit(1)

# 4. Insert slr_charts_str at the end of the breakdown panel
try:
    # Find the end of transit breakdown
    transit_panel_idx = next(i for i, l in enumerate(lines) if "expandedMetric === 'transit' && (" in l)
    # The transit panel is 12 lines long, we'll just look for the `</div>` that closes the Interactive Breakdown Panel
    # Wait, it's easier to find:
    #                     {/* Allocation Context */}
    allocation_idx = next(i for i, l in enumerate(lines) if "{/* Allocation Context */}" in l)
    
    # insert before allocation context
    lines.insert(allocation_idx, slr_charts_str + "\n                          \n")
except StopIteration:
    print("Could not find Allocation Context")
    exit(1)

# 5. Insert HeroMetrics
try:
    interactive_panel_idx = next(i for i, l in enumerate(lines) if "{/* ── Interactive Breakdown Panel ── */}" in l)
    
    hero_metrics = """                      {/* SLR KPIs */}
                      {slrLoading ? (
                        <div className="flex items-center justify-center gap-3 mt-4 pt-4 border-t border-border">
                          <Loader2 className="w-5 h-5 text-primary animate-spin" />
                          <span className="text-sm text-muted-foreground/60">Loading SLR data...</span>
                        </div>
                      ) : slrData && slrData.data?.length > 0 && (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-4 border-t border-border">
                          <HeroMetric label="Total SLR POs" value={slrData.total_pos || 0} icon={FileText} color="text-primary dark:text-primary" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'slr' ? null : 'slr')} active={expandedMetric === 'slr'} />
                          <HeroMetric label="Open POs" value={slrData.open_pos || 0} icon={Activity} color="text-primary dark:text-primary" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'slr' ? null : 'slr')} active={expandedMetric === 'slr'} />
                          <HeroMetric label="Closed POs" value={slrData.closed_pos || 0} icon={Check} color="text-muted-foreground dark:text-muted-foreground" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'slr' ? null : 'slr')} active={expandedMetric === 'slr'} />
                          <HeroMetric label="Total Amount" value={`₹${slrData.total_amount ? (slrData.total_amount / 10000000).toFixed(2) : 0}`} unit="Cr" icon={DollarSign} color="text-pink-500 dark:text-pink-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'slr' ? null : 'slr')} active={expandedMetric === 'slr'} />
                        </div>
                      )}

"""
    lines.insert(interactive_panel_idx, hero_metrics)
except StopIteration:
    print("Could not find Interactive Breakdown Panel")
    exit(1)

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Successfully refactored SLR section")
