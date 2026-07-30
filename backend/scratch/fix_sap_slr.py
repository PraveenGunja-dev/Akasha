import os
import re

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(os.path.dirname(backend_dir), "frontend", "src", "features", "projects", "ProjectWorkspace.tsx")

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# The missing SLR Content
slr_content = """
                  {sapSubTab === 'slr' && (
                    <div className="space-y-6">
                      {slrLoading ? (
                        <div className="flex items-center justify-center h-[300px]">
                          <div className="flex items-center gap-3">
                            <Loader2 className="w-5 h-5 text-primary animate-spin" />
                            <span className="text-sm text-muted-foreground/60">Loading SLR data...</span>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-6">
                          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            <div className="intelligence-card p-4">
                              <div className="text-sm text-muted-foreground font-semibold mb-1">TOTAL POs</div>
                              <div className="text-2xl font-bold text-foreground">{slrData?.total_pos || 0}</div>
                            </div>
                            <div className="intelligence-card p-4">
                              <div className="text-sm text-muted-foreground font-semibold mb-1">OPEN POs</div>
                              <div className="text-2xl font-bold text-primary">{slrData?.open_pos || 0}</div>
                            </div>
                            <div className="intelligence-card p-4">
                              <div className="text-sm text-muted-foreground font-semibold mb-1">CLOSED POs</div>
                              <div className="text-2xl font-bold text-muted-foreground">{slrData?.closed_pos || 0}</div>
                            </div>
                            <div className="intelligence-card p-4">
                              <div className="text-sm text-muted-foreground font-semibold mb-1">TOTAL AMOUNT</div>
                              <div className="text-2xl font-bold text-foreground">₹{slrData?.total_amount ? (slrData.total_amount / 10000000).toFixed(2) : 0} Cr</div>
                            </div>
                          </div>

                          {slrData?.data && slrData.data.length > 0 && (
                            <div className="intelligence-card overflow-hidden">
                              <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left">
                                  <thead className="bg-muted/50 border-b border-border">
                                    <tr>
                                      <th className="px-4 py-3 font-semibold text-muted-foreground">PO Number</th>
                                      <th className="px-4 py-3 font-semibold text-muted-foreground">Description</th>
                                      <th className="px-4 py-3 font-semibold text-muted-foreground text-right">Total Amount</th>
                                      <th className="px-4 py-3 font-semibold text-muted-foreground text-right">Actual</th>
                                      <th className="px-4 py-3 font-semibold text-muted-foreground text-right">Commitment</th>
                                      <th className="px-4 py-3 font-semibold text-muted-foreground text-center">Status</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-border">
                                    {slrData.data.map((row: any, i: number) => (
                                      <tr key={i} className="hover:bg-muted/30 transition-colors">
                                        <td className="px-4 py-3 font-medium text-foreground">{row.po_document}</td>
                                        <td className="px-4 py-3 text-muted-foreground truncate max-w-[200px]" title={row.description}>{row.description}</td>
                                        <td className="px-4 py-3 text-right">₹{row.total.toLocaleString(undefined, {maximumFractionDigits:2})}</td>
                                        <td className="px-4 py-3 text-right">₹{row.actual.toLocaleString(undefined, {maximumFractionDigits:2})}</td>
                                        <td className="px-4 py-3 text-right">₹{row.commitment.toLocaleString(undefined, {maximumFractionDigits:2})}</td>
                                        <td className="px-4 py-3 text-center">
                                          <span className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest ${
                                            row.status === 'Open' ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
                                          }`}>
                                            {row.status}
                                          </span>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
"""

# Find where to inject `{sapSubTab === 'old' && (<>`
if "{sapSubTab === 'old' && (" not in content:
    content = content.replace(
        "                  {!sap || sap.summary.totalPOs === 0 ? (",
        "                  {sapSubTab === 'old' && (\n                    <>\n                      {!sap || sap.summary.totalPOs === 0 ? ("
    )
    
    # Close the block and append SLR content right before the end of the sap tab content
    # The end of sap tab content looks like:
    #                   )}
    #                 </div>
    #               )}
    #             </div>
    #           )}
    #           {/* ════════ P6 DEEP DIVE TAB (NEW) ════════ */}
    
    pattern = r'(                  \)\}\n                </div>\n              \)\}\n            </div>\n          \)\}\n\n          \{\/\* ════════ P6 DEEP DIVE TAB)'
    replacement = r'                  </>\n                  )}\n\n' + slr_content.replace('\\', '\\\\') + r'\n\1'
    content = re.sub(pattern, replacement, content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("SLR content successfully injected!")
