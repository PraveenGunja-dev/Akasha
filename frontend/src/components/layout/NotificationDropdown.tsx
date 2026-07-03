import React, { useState } from 'react';
import { CheckCircle2, AlertCircle, Clock, CalendarDays, TrendingUp, Filter, Play, Sparkles } from 'lucide-react';

export default function NotificationDropdown({ notifications, onClose, onMarkAllRead, onSimulate }: any) {
  const [activeTab, setActiveTab] = useState('All');
  const [aiSuggestions, setAiSuggestions] = useState<{[key: number]: string}>({});
  const [loadingSuggestion, setLoadingSuggestion] = useState<number | null>(null);

  const fetchAISuggestion = async (e: React.MouseEvent, n: any) => {
    e.stopPropagation();
    if (aiSuggestions[n.id]) return;
    setLoadingSuggestion(n.id);
    try {
      const res = await fetch('/akasha/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: `Provide a very short, one sentence concrete suggestion to resolve this project issue: "${n.message}". Focus on actionable operational recovery (like fast-tracking, resources, etc). Be direct and extremely brief (max 15 words).` })
      });
      if (res.ok) {
        const data = await res.json();
        setAiSuggestions(prev => ({ ...prev, [n.id]: data.response || "Fast-track parallel works or assign an extra crew to recover the delay." }));
      } else {
        setAiSuggestions(prev => ({ ...prev, [n.id]: "Fast-track parallel works or assign an extra crew to recover the delay." }));
      }
    } catch {
      setAiSuggestions(prev => ({ ...prev, [n.id]: "Fast-track parallel works or assign an extra crew to recover the delay." }));
    }
    setLoadingSuggestion(null);
  };

  const tabs = ['All', 'Scope', 'COD', 'Trials', 'Dates'];

  const filteredNotifs = activeTab === 'All' 
    ? notifications 
    : notifications.filter((n: any) => n.category === activeTab);

  const getIcon = (type: string) => {
    if (!type) return <Clock className="w-4 h-4 text-sky-500" />;
    if (type.includes('Scope') || type.includes('Budget')) return <TrendingUp className="w-4 h-4 text-red-500" />;
    if (type.includes('COD') || type.includes('Trial') || type.includes('Critical')) return <AlertCircle className="w-4 h-4 text-orange-500" />;
    return <CalendarDays className="w-4 h-4 text-sky-500" />;
  };

  return (
    <div className="absolute right-0 top-full mt-3 w-[450px] bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-[0_10px_40px_rgba(0,0,0,0.15)] z-50 flex flex-col overflow-hidden max-h-[600px] transform origin-top-right transition-all">
      <div className="p-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between bg-sky-50/50 dark:bg-sky-900/10">
        <div className="flex items-center gap-2">
          <span className="font-bold text-[15px] tracking-tight text-gray-900 dark:text-white">Notifications</span>
          <span className="px-2 py-0.5 bg-sky-100 dark:bg-sky-500/20 text-sky-600 dark:text-sky-400 rounded-full text-[10px] font-bold">
            {notifications.length}
          </span>
        </div>
        <button onClick={onMarkAllRead} className="text-[12px] text-sky-500 hover:text-sky-600 font-semibold transition-colors px-2 py-1 hover:bg-sky-50 dark:hover:bg-sky-900/20 rounded-lg">Mark all read</button>
      </div>

      {/* Tabs */}
      <div className="p-3 bg-gray-50/50 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-800">
        <div className="flex items-center gap-1 overflow-x-auto hide-scrollbar pb-1" data-lenis-prevent="true">
          <Filter className="w-3.5 h-3.5 text-gray-400 mr-1 shrink-0" />
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3.5 py-1.5 text-[12px] font-semibold rounded-full transition-all shrink-0 ${
                activeTab === tab 
                  ? 'bg-sky-500 text-white shadow-md' 
                  : 'bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-y-auto flex-1 bg-white dark:bg-gray-900" data-lenis-prevent="true">
        {filteredNotifs.length === 0 ? (
          <div className="p-12 flex flex-col items-center justify-center text-gray-400">
            <CheckCircle2 className="w-12 h-12 mb-3 opacity-20" />
            <p className="text-[13px] font-medium text-gray-500">All caught up!</p>
            <p className="text-[11px] opacity-60">No notifications in this category.</p>
          </div>
        ) : (
          filteredNotifs.map((n: any) => (
            <div 
              key={n.id} 
              className={`p-4 border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-all group relative bg-white dark:bg-gray-900 ${n.is_read ? 'opacity-70' : ''}`}
            >
              {!n.is_read && (
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-sky-500 rounded-r-full" />
              )}
              
              <div className="flex gap-4 relative z-10">
                <div className="mt-0.5 p-2 bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-xl shadow-sm group-hover:scale-110 transition-transform h-fit">
                  {getIcon(n.change_type)}
                </div>
                
                <div className="flex-1 min-w-0 flex flex-col gap-2.5 mt-0.5">
                  <div className="flex justify-between items-start">
                    <span className="font-bold text-[14px] text-gray-900 dark:text-white truncate pr-2 group-hover:text-sky-600 transition-colors tracking-tight">{n.project_name}</span>
                    <span className="text-[10px] font-semibold text-gray-500 whitespace-nowrap bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 px-2 py-0.5 rounded-full shrink-0 shadow-sm mt-0.5">
                      {new Date(n.created_at).toLocaleDateString()}
                    </span>
                  </div>

                  <div className="flex items-center flex-wrap gap-2">
                    {n.block && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-100 dark:border-sky-500/20 shadow-sm">
                        {n.block}
                      </span>
                    )}
                    {n.activity_name && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 truncate max-w-full shadow-sm">
                        {n.activity_name}
                      </span>
                    )}
                  </div>

                  <div className="p-3 rounded-xl bg-gray-50 dark:bg-gray-800/80 border border-gray-100 dark:border-gray-700/50 mt-1 shadow-sm">
                    <p className="text-[13px] text-gray-700 dark:text-gray-200 leading-relaxed font-medium">
                      {n.message}
                    </p>
                  </div>
                  
                  {/* Actions & AI Suggestions */}
                  {(n.change_type?.includes('Delay') || n.message?.toLowerCase().includes('delay') || n.change_type?.includes('Critical')) && (
                    <div className="mt-3 flex flex-col gap-2">
                      <div className="flex gap-2">
                        {onSimulate && (
                          <button 
                            onClick={(e) => {
                              e.stopPropagation();
                              onSimulate(n.project_name, n);
                            }}
                            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400 font-bold text-[11px] uppercase tracking-widest border border-sky-200 dark:border-sky-500/20 hover:bg-sky-100 dark:hover:bg-sky-500/20 transition-colors shadow-sm"
                          >
                            <Play className="w-3.5 h-3.5" /> Simulate
                          </button>
                        )}
                        <button 
                          onClick={(e) => fetchAISuggestion(e, n)}
                          disabled={loadingSuggestion === n.id}
                          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 font-bold text-[11px] uppercase tracking-widest border border-purple-200 dark:border-purple-500/20 hover:bg-purple-100 dark:hover:bg-purple-500/20 transition-colors shadow-sm disabled:opacity-50"
                        >
                          <Sparkles className="w-3.5 h-3.5" /> 
                          {loadingSuggestion === n.id ? 'Thinking...' : 'AI Suggestion'}
                        </button>
                      </div>

                      {aiSuggestions[n.id] && (
                        <div className="p-3 mt-1 rounded-xl bg-purple-50/50 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-800/50 relative overflow-hidden">
                          <div className="absolute top-0 left-0 w-1 h-full bg-purple-400"></div>
                          <div className="flex gap-2 items-start">
                            <Sparkles className="w-4 h-4 text-purple-500 mt-0.5 shrink-0" />
                            <p className="text-[12px] text-purple-900 dark:text-purple-100 font-medium leading-relaxed">
                              {aiSuggestions[n.id]}
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
