import os
import re

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(os.path.dirname(backend_dir), "frontend", "src", "features", "projects", "ProjectWorkspace.tsx")

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the Recharts block with ECharts block
pattern = r"(\{\s*slrData\?\.data\s*&&\s*slrData\.data\.length\s*>\s*0\s*&&\s*\(\s*<>\s*<div className=\"grid grid-cols-1 md:grid-cols-3 gap-4\">).*?(<div className=\"intelligence-card overflow-hidden flex flex-col\">)"

replacement = """{slrData?.data && slrData.data.length > 0 && (
                            <>
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="intelligence-card p-4 h-[300px] flex flex-col">
                                  <h3 className="text-sm font-semibold mb-2 text-muted-foreground">PO Status Distribution</h3>
                                  <div className="flex-1 min-h-0">
                                    <ReactECharts
                                      option={{
                                        tooltip: { trigger: 'item' },
                                        color: ['#3b82f6', '#94a3b8'],
                                        legend: { bottom: 0, textStyle: { color: '#888' } },
                                        series: [{
                                          type: 'pie',
                                          radius: ['50%', '70%'],
                                          center: ['50%', '45%'],
                                          data: [
                                            { value: slrData.open_pos, name: 'Open' },
                                            { value: slrData.closed_pos, name: 'Closed' }
                                          ]
                                        }]
                                      }}
                                      style={{ height: '100%', width: '100%' }}
                                    />
                                  </div>
                                </div>
                                
                                <div className="intelligence-card p-4 h-[300px] flex flex-col">
                                  <h3 className="text-sm font-semibold mb-2 text-muted-foreground">Amount by Category</h3>
                                  <div className="flex-1 min-h-0">
                                    <ReactECharts
                                      option={{
                                        tooltip: { trigger: 'axis', formatter: (params: any) => `₹${params[0].value.toLocaleString()}` },
                                        grid: { top: 10, right: 10, bottom: 60, left: 50 },
                                        xAxis: {
                                          type: 'category',
                                          data: Object.entries(slrData.data.reduce((acc: any, row: any) => { acc[row.description || 'Unknown'] = (acc[row.description || 'Unknown'] || 0) + row.total; return acc; }, {})).map(([k, v]) => ({ name: k, amount: v })).sort((a: any, b: any) => b.amount - a.amount).slice(0, 5).map(d => d.name),
                                          axisLabel: { interval: 0, rotate: 30, fontSize: 9, color: '#888' }
                                        },
                                        yAxis: {
                                          type: 'value',
                                          axisLabel: { formatter: (val: number) => `₹${(val/10000000).toFixed(0)}Cr`, fontSize: 9, color: '#888' },
                                          splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
                                        },
                                        series: [{
                                          data: Object.entries(slrData.data.reduce((acc: any, row: any) => { acc[row.description || 'Unknown'] = (acc[row.description || 'Unknown'] || 0) + row.total; return acc; }, {})).map(([k, v]) => ({ name: k, amount: v })).sort((a: any, b: any) => b.amount - a.amount).slice(0, 5).map(d => d.amount),
                                          type: 'bar',
                                          itemStyle: { color: '#8b5cf6', borderRadius: [4, 4, 0, 0] }
                                        }]
                                      }}
                                      style={{ height: '100%', width: '100%' }}
                                    />
                                  </div>
                                </div>

                                <div className="intelligence-card p-4 h-[300px] flex flex-col">
                                  <h3 className="text-sm font-semibold mb-2 text-muted-foreground">Top POs by Amount</h3>
                                  <div className="flex-1 min-h-0">
                                    <ReactECharts
                                      option={{
                                        tooltip: { trigger: 'axis', formatter: (params: any) => `₹${params[0].value.toLocaleString()}` },
                                        grid: { top: 10, right: 20, bottom: 20, left: 70 },
                                        xAxis: {
                                          type: 'value',
                                          axisLabel: { formatter: (val: number) => `₹${(val/10000000).toFixed(0)}Cr`, fontSize: 9, color: '#888' },
                                          splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
                                        },
                                        yAxis: {
                                          type: 'category',
                                          data: [...slrData.data].sort((a: any,b: any) => b.total - a.total).slice(0, 5).reverse().map((d: any) => d.po_document || 'Unk'),
                                          axisLabel: { fontSize: 9, color: '#888' }
                                        },
                                        series: [{
                                          data: [...slrData.data].sort((a: any,b: any) => b.total - a.total).slice(0, 5).reverse().map((d: any) => d.total),
                                          type: 'bar',
                                          itemStyle: { color: '#06b6d4', borderRadius: [0, 4, 4, 0] }
                                        }]
                                      }}
                                      style={{ height: '100%', width: '100%' }}
                                    />
                                  </div>
                                </div>
                              </div>

                              <div className="intelligence-card overflow-hidden flex flex-col">"""

content = re.sub(pattern, replacement.replace('\\', '\\\\'), content, flags=re.DOTALL)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Charts fixed!")
