import os
import re

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(os.path.dirname(backend_dir), "frontend", "src", "features", "projects", "ProjectWorkspace.tsx")

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update filter logic
filter_section_pattern = r"(\{\[\s*\{\s*key:\s*'all'\s*as\s*const.*?\)\}\s*</div>)"

new_filter_section = """{sapSubTab === 'old' ? (
                        [
                          { key: 'all' as const, label: 'All', disabled: false },
                          {
                            key: 'spv' as const,
                            label: `SPV (${project?.sapPlantCode || '—'})`,
                            disabled: project?.sapPlantCode ? ![(sapRaw?.purchaseOrders || []), (sapRaw?.inventory || []), (sapRaw?.consumption || [])].some(arr => arr.some((x: any) => x.plantCode === project.sapPlantCode)) : true
                          },
                          {
                            key: 'agel' as const,
                            label: `AGEL (${project?.agelCode || '—'})`,
                            disabled: project?.agelCode ? ![(sapRaw?.purchaseOrders || []), (sapRaw?.inventory || []), (sapRaw?.consumption || [])].some(arr => arr.some((x: any) => x.plantCode === project.agelCode)) : true
                          },
                        ].map(opt => (
                          <button
                            key={opt.key}
                            onClick={() => !opt.disabled && setSapFilter(opt.key)}
                            disabled={opt.disabled}
                            title={opt.disabled ? 'No procurement data found for this plant code' : ''}
                            className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all ${opt.disabled
                              ? 'opacity-40 cursor-not-allowed border border-dashed border-muted-foreground/30 text-muted-foreground'
                              : sapFilter === opt.key
                                ? 'bg-primary text-primary-foreground shadow-sm'
                                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                              }`}
                          >
                            {opt.label}
                          </button>
                        ))
                      ) : (
                        [
                          { key: 'ALL' as const, label: 'All', disabled: false },
                          { key: 'SPV' as const, label: `SPV (${project?.sapPlantCode || '—'})`, disabled: !project?.sapPlantCode },
                          { key: 'AGEL' as const, label: `AGEL (${project?.agelCode || '—'})`, disabled: !project?.agelCode },
                          { key: 'AGE6L' as const, label: `AGE6L (${project?.age6lCode || '—'})`, disabled: false },
                        ].map(opt => (
                          <button
                            key={opt.key}
                            onClick={() => !opt.disabled && setSlrFilter(opt.key)}
                            disabled={opt.disabled}
                            className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all ${opt.disabled
                              ? 'opacity-40 cursor-not-allowed border border-dashed border-muted-foreground/30 text-muted-foreground'
                              : slrFilter === opt.key
                                ? 'bg-primary text-primary-foreground shadow-sm'
                                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                              }`}
                          >
                            {opt.label}
                          </button>
                        ))
                      )}
                      </div>"""

content = re.sub(filter_section_pattern, new_filter_section.replace('\\', '\\\\'), content, flags=re.DOTALL)

# 2. Add Charts and Fix Table
table_pattern = r"(\{\s*slrData\?\.data\s*&&\s*slrData\.data\.length\s*>\s*0\s*&&\s*\()(.*?)(\)\s*\})"

new_table_and_charts = """{slrData?.data && slrData.data.length > 0 && (
                            <>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="intelligence-card p-4 h-[300px] flex flex-col">
                                  <h3 className="text-sm font-semibold mb-4 text-muted-foreground">PO Status Distribution</h3>
                                  <div className="flex-1">
                                    <ResponsiveContainer width="100%" height="100%">
                                      <PieChart>
                                        <Pie
                                          data={[
                                            { name: 'Open', value: slrData.open_pos },
                                            { name: 'Closed', value: slrData.closed_pos }
                                          ]}
                                          cx="50%" cy="50%"
                                          innerRadius={60} outerRadius={80}
                                          paddingAngle={5}
                                          dataKey="value"
                                        >
                                          <Cell fill="#3b82f6" />
                                          <Cell fill="#94a3b8" />
                                        </Pie>
                                        <RechartsTooltip formatter={(val: number) => [val, 'Count']} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                                        <Legend />
                                      </PieChart>
                                    </ResponsiveContainer>
                                  </div>
                                </div>
                                
                                <div className="intelligence-card p-4 h-[300px] flex flex-col">
                                  <h3 className="text-sm font-semibold mb-4 text-muted-foreground">Top 5 POs by Amount (₹)</h3>
                                  <div className="flex-1">
                                    <ResponsiveContainer width="100%" height="100%">
                                      <BarChart data={[...slrData.data].sort((a,b) => b.total - a.total).slice(0, 5)} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(255,255,255,0.1)" />
                                        <XAxis type="number" tickFormatter={(val) => `₹${(val/10000000).toFixed(1)}Cr`} tick={{fontSize: 10}} />
                                        <YAxis dataKey="po_document" type="category" width={80} tick={{fontSize: 10}} />
                                        <RechartsTooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} formatter={(val: number) => [`₹${val.toLocaleString()}`, 'Amount']} />
                                        <Bar dataKey="total" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                                      </BarChart>
                                    </ResponsiveContainer>
                                  </div>
                                </div>
                              </div>

                              <div className="intelligence-card overflow-hidden flex flex-col">
                                <div className="p-4 border-b border-border bg-muted/30">
                                  <h3 className="text-sm font-semibold text-foreground">SLR Line Items ({slrData.data.length})</h3>
                                </div>
                                <div className="overflow-x-auto overflow-y-auto max-h-[500px]">
                                  <table className="w-full text-sm text-left relative">
                                    <thead className="bg-muted border-b border-border sticky top-0 z-10">
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
                                          <td className="px-4 py-3 font-medium text-foreground">{row.po_document || '—'}</td>
                                          <td className="px-4 py-3 text-muted-foreground truncate max-w-[250px]" title={row.description}>{row.description || '—'}</td>
                                          <td className="px-4 py-3 text-right">₹{row.total.toLocaleString(undefined, {maximumFractionDigits:2})}</td>
                                          <td className="px-4 py-3 text-right text-emerald-500/80">₹{row.actual.toLocaleString(undefined, {maximumFractionDigits:2})}</td>
                                          <td className="px-4 py-3 text-right text-amber-500/80">₹{row.commitment.toLocaleString(undefined, {maximumFractionDigits:2})}</td>
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
                            </>
                          )}"""

content = re.sub(table_pattern, new_table_and_charts.replace('\\', '\\\\'), content, flags=re.DOTALL)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("UI patched!")
