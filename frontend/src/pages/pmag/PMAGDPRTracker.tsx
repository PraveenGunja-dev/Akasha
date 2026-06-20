import React from 'react';
import { Layers, CheckCircle2, Clock, XCircle } from 'lucide-react';

export default function PMAGDPRTracker({ dpr_tracker }: any) {
  return (
    <div className="bento-card p-8 min-h-[700px] flex flex-col">
      <div className="flex items-center justify-between mb-6 border-b border-gray-100 dark:border-gray-800 pb-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Layers className="w-6 h-6 text-violet-500" />
            DPR Submission Tracker
          </h2>
          <p className="text-sm text-gray-500 mt-1">Detailed daily progress report submissions across all projects.</p>
        </div>
        <span className="px-3 py-1 rounded-full bg-violet-50 dark:bg-violet-500/10 text-violet-600 dark:text-violet-400 text-sm font-bold border border-violet-100 dark:border-violet-500/20">Last 7 Days</span>
      </div>
      <div className="flex-1 overflow-x-auto overflow-y-auto custom-scrollbar">
        <table className="intel-table w-full">
          <thead>
            <tr>
              <th className="py-4 text-sm">Site / Project</th>
              {dpr_tracker[0]?.days.map((d: any, i: number) => (
                <th key={i} className="text-center py-4 text-sm">{d.day}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dpr_tracker.map((site: any, i: number) => (
              <tr key={i} className="hover:bg-gray-50 dark:hover:bg-slate-800/50 transition-colors">
                <td className="font-bold py-4 px-4 border-b border-gray-100 dark:border-gray-800">{site.project}</td>
                {site.days.map((d: any, j: number) => (
                  <td key={j} className="text-center py-4 border-b border-gray-100 dark:border-gray-800">
                    <div className="flex flex-col items-center justify-center gap-1.5">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${d.status === 'submitted' ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600' : d.status === 'pending' ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-600' : 'bg-red-100 dark:bg-red-500/20 text-red-600'}`} title={`${d.date}: ${d.status}`}>
                        {d.status === 'submitted' ? <CheckCircle2 className="w-4 h-4" /> : d.status === 'pending' ? <Clock className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                      </div>
                      <span className="text-[10px] font-medium text-gray-500 capitalize">{d.status}</span>
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
