const fs = require('fs');
const path = 'd:\\Akasha_Platform\\frontend\\src\\components\\sections\\ProjectWorkspace.tsx';
let content = fs.readFileSync(path, 'utf8');

// 1. Schedule Left Column Removal
const leftColStart = content.indexOf('{/* Left Column: Key Indices */}');
const rightColStart = content.indexOf('{/* Right Column: Timeline & Variance */}');
if (leftColStart !== -1 && rightColStart !== -1) {
    const block = content.substring(leftColStart, rightColStart);
    content = content.replace(block, '');
    content = content.replace('<div className="lg:col-span-8 flex flex-col gap-6">', '<div className="lg:col-span-12 flex flex-col gap-6">');
}

// 2. Remove Supply and Risk tabs
const supplyStart = content.indexOf('{/* ════════ SUPPLY CHAIN TAB ════════ */}');
const sapStart = content.indexOf('{/* ════════ SAP INTELLIGENCE TAB (NEW) ════════ */}');
if (supplyStart !== -1 && sapStart !== -1) {
    const block = content.substring(supplyStart, sapStart);
    content = content.replace(block, '');
}

// 3. Add KPI row to P6 Deep Dive
const p6Target = `                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                    {/* Full Project Timeline */}`;
const p6Replacement = `                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                    <HeroMetric label="MW Capacity" value={project?.capacityMW || 0} icon={Zap} color="text-yellow-500" />
                    <div onClick={() => setShowDelayedModal(true)} className="cursor-pointer hover:scale-105 transition-transform">
                      <HeroMetric label="Delayed Activities" value={delayedActivities.length} icon={AlertTriangle} color="text-red-500" />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                    {/* Full Project Timeline */}`;
content = content.replace(p6Target, p6Replacement);

// 4. Add Modal at the end
const endMarker = '    </div>\n  );\n}\n';
const modalStr = `      {/* Delayed Activities Modal */}
      {showDelayedModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-border bg-muted/30">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-red-500/20 text-red-400 rounded-lg">
                  <AlertTriangle className="w-6 h-6" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-foreground">Delayed Activities</h2>
                  <p className="text-sm text-muted-foreground">Activities past planned dates based on Data Date</p>
                </div>
              </div>
              <button 
                onClick={() => setShowDelayedModal(false)}
                className="p-2 hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            {/* Body */}
            <div className="p-6 overflow-y-auto flex-1">
              {delayedActivities.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">No delayed activities found.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-muted-foreground uppercase bg-muted/50">
                      <tr>
                        <th className="px-4 py-3 rounded-tl-lg">Activity ID</th>
                        <th className="px-4 py-3">Name</th>
                        <th className="px-4 py-3">Group / WBS</th>
                        <th className="px-4 py-3">Planned Start</th>
                        <th className="px-4 py-3">Planned Finish</th>
                        <th className="px-4 py-3">Status</th>
                        <th className="px-4 py-3 rounded-tr-lg text-right">Delay (Days)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50">
                      {delayedActivities.map((act) => (
                        <tr key={act.id} className="hover:bg-muted/30 transition-colors">
                          <td className="px-4 py-3 font-medium text-foreground">{act.id}</td>
                          <td className="px-4 py-3">{act.name}</td>
                          <td className="px-4 py-3">
                            <div className="flex flex-col">
                              <span>{act.group}</span>
                              <span className="text-xs text-muted-foreground">{act.wbs}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">{new Date(act.plannedStart).toLocaleDateString()}</td>
                          <td className="px-4 py-3 text-muted-foreground">{new Date(act.plannedFinish).toLocaleDateString()}</td>
                          <td className="px-4 py-3">
                            <span className={\`px-2 py-1 rounded-full text-xs font-medium border \${
                              act.status === 'In Progress' 
                                ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' 
                                : 'bg-orange-500/10 text-orange-400 border-orange-500/20'
                            }\`}>
                              {act.status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right font-bold text-red-400">+{act.delayDays}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
`;

content = content.replace(endMarker, endMarker + modalStr);

fs.writeFileSync(path, content, 'utf8');
console.log('Done');
