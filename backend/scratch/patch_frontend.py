import os
import re

frontend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(os.path.dirname(frontend_dir), "frontend", "src", "features", "projects", "ProjectWorkspace.tsx")

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add Receipt to lucide imports
if 'Receipt' not in content:
    content = re.sub(
        r'(import \{[^\}]*?)(, Maximize2)(\s*\}\s*from\s*\'lucide-react\';)', 
        r'\1\2, Receipt\3', 
        content
    )

# 2. Add SLR states
if 'slrData' not in content:
    state_injection = """  const [slrData, setSlrData] = useState<any>(null);
  const [slrLoading, setSlrLoading] = useState(false);
  const [slrFilter, setSlrFilter] = useState<'ALL' | 'SPV' | 'AGEL' | 'AGE6L'>('ALL');

  useEffect(() => {
    if (!project?.mapping_id) return;
    setSlrLoading(true);
    fetch(`/akasha/api/projects/${project.mapping_id}/slr?filter_code=${slrFilter}`)
      .then(res => res.json())
      .then(data => setSlrData(data))
      .catch(err => console.error(err))
      .finally(() => setSlrLoading(false));
  }, [project?.mapping_id, slrFilter]);
"""
    content = re.sub(
        r'(const \[syncingP6, setSyncingP6\] = useState\(false\);\n)', 
        r'\1\n' + state_injection, 
        content
    )

# 3. Add TabBtn
if "label=\"SLR Data\"" not in content:
    content = re.sub(
        r'(<TabBtn active=\{activeTab === \'sap\'\} label=\"SAP Intelligence\" icon=\{Database\} onClick=\{\(\) => setActiveTab\(\'sap\'\)\} />\n)',
        r'\1          <TabBtn active={activeTab === \'slr\'} label="SLR Data" icon={Receipt} onClick={() => setActiveTab(\'slr\')} />\n',
        content
    )

# 4. Add Tab Content
if "SLR DATA TAB" not in content:
    tab_content = """
          {/* ════════ SLR DATA TAB (NEW) ════════ */}
          {activeTab === 'slr' && (
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
                  <div className="flex items-center justify-between mb-2">
                    <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                      <Receipt className="w-5 h-5 text-primary/70" /> SLR Data
                    </h2>
                    <div className="flex items-center bg-muted border border-border rounded-lg p-0.5">
                      {['ALL', 'SPV', 'AGEL', 'AGE6L'].map(opt => (
                        <button
                          key={opt}
                          onClick={() => setSlrFilter(opt as any)}
                          className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all ${
                            slrFilter === opt
                              ? 'bg-primary text-primary-foreground shadow-sm'
                              : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                          }`}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>

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
    content = re.sub(
        r'(          \{\/\* ════════ P6 DEEP DIVE TAB ════════ \*\/})',
        tab_content.replace('\\', '\\\\') + r'\n\1',
        content
    )

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("ProjectWorkspace.tsx patched successfully.")
