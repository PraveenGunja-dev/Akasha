import React, { useState, useEffect } from 'react';
import { CheckCircle2, AlertCircle, Clock, CalendarDays, TrendingUp, Filter, Play, Sparkles, Loader2 } from 'lucide-react';

export default function NotificationDropdown({ notifications, onClose, onMarkAllRead, onSimulate }: any) {
  const [activeTab, setActiveTab] = useState('All');
  const [aiSuggestions, setAiSuggestions] = useState<{[key: number]: string}>({});
  const [expandedProjects, setExpandedProjects] = useState<{[key: string]: boolean}>({});
  const [loadingSuggestion, setLoadingSuggestion] = useState<number | null>(null);

  const [tabNotifications, setTabNotifications] = useState<any[]>([]);
  const [tabHasMore, setTabHasMore] = useState(true);
  const [isLoadingTab, setIsLoadingTab] = useState(false);

  useEffect(() => {
    fetchTabNotifications(activeTab, 0, true);
  }, [activeTab]);

  const fetchTabNotifications = async (tab: string, skip = 0, reset = false) => {
    if (reset) setIsLoadingTab(true);
    try {
      const res = await fetch(`/akasha/api/notifications/?skip=${skip}&limit=50&tab=${encodeURIComponent(tab)}`);
      if (res.ok) {
        const data = await res.json();
        if (reset) {
          setTabNotifications(data);
        } else {
          setTabNotifications(prev => [...prev, ...data]);
        }
        setTabHasMore(data.length === 50);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoadingTab(false);
    }
  };

  const handleLoadMore = () => {
    fetchTabNotifications(activeTab, tabNotifications.length, false);
  };

  const fetchAISuggestion = async (e: React.MouseEvent, n: any) => {
    e.stopPropagation();
    
    // If it's already shown, toggle it off
    if (aiSuggestions[n.id]) {
      const newSuggestions = { ...aiSuggestions };
      delete newSuggestions[n.id];
      setAiSuggestions(newSuggestions);
      return;
    }
    
    setLoadingSuggestion(n.id);
    
    try {
      const res = await fetch(`/akasha/api/notifications/${n.id}/ai-suggestion`);
      if (res.ok) {
        const data = await res.json();
        setAiSuggestions(prev => ({ 
          ...prev, 
          [n.id]: data.suggestion 
        }));
      } else {
        setAiSuggestions(prev => ({ 
          ...prev, 
          [n.id]: "Fast-track parallel works or assign an extra crew to recover the delay." 
        }));
      }
    } catch (e) {
      setAiSuggestions(prev => ({ 
        ...prev, 
        [n.id]: "Fast-track parallel works or assign an extra crew to recover the delay." 
      }));
    } finally {
      setLoadingSuggestion(null);
    }
  };

  const tabs = ['All', 'Transmission', 'Critical Path', 'Risk', 'COD', 'Scope', 'Trials', 'Dates'];

  const getIcon = (type: string) => {
    if (!type) return <Clock className="w-4 h-4 text-sky-500" />;
    if (type.includes('Scope') || type.includes('Budget')) return <TrendingUp className="w-4 h-4 text-destructive" />;
    if (type.includes('COD') || type.includes('Trial') || type.includes('Critical')) return <AlertCircle className="w-4 h-4 text-warning" />;
    return <CalendarDays className="w-4 h-4 text-sky-500" />;
  };

  return (
    <div className="absolute right-0 top-full mt-3 w-[450px] bg-card border border-border dark:border-border rounded-2xl shadow-[0_10px_40px_rgba(0,0,0,0.15)] z-50 flex flex-col overflow-hidden max-h-[600px] transform origin-top-right transition-all">
      <div className="p-4 border-b border-muted dark:border-border flex items-center justify-between bg-sky-50/50 dark:bg-sky-900/10">
        <div className="flex items-center gap-2">
          <span className="font-bold text-[15px] tracking-tight text-foreground dark:text-white">Notifications</span>
          <span className="px-2 py-0.5 bg-sky-100 dark:bg-sky-500/20 text-sky-600 dark:text-sky-400 rounded-full text-[10px] font-bold">
            {tabNotifications.length} {tabHasMore ? '+' : ''}
          </span>
        </div>
        <button onClick={onMarkAllRead} className="text-[12px] text-sky-500 hover:text-sky-600 font-semibold transition-colors px-2 py-1 hover:bg-sky-50 dark:hover:bg-sky-900/20 rounded-lg">Mark all read</button>
      </div>

      {/* Tabs */}
      <div className="p-3 bg-muted dark:bg-gray-900/50 border-b border-muted dark:border-border">
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-hide pb-1">
          <Filter className="w-3.5 h-3.5 text-muted-foreground mr-1 shrink-0" />
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3.5 py-1.5 text-[12px] font-semibold rounded-full transition-all shrink-0 ${
                activeTab === tab 
                  ? 'bg-sky-500 text-white shadow-md' 
                  : 'bg-card border border-border dark:border-gray-700 text-muted-foreground dark:text-muted-foreground hover:text-foreground dark:hover:text-white hover:bg-muted dark:hover:bg-card'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-y-auto flex-1 bg-card">
        {isLoadingTab ? (
          <div className="p-12 flex flex-col items-center justify-center text-muted-foreground">
            <Loader2 className="w-8 h-8 mb-3 animate-spin text-sky-500 opacity-50" />
            <p className="text-[13px] font-medium text-muted-foreground">Loading {activeTab} notifications...</p>
          </div>
        ) : tabNotifications.length === 0 ? (
          <div className="p-12 flex flex-col items-center justify-center text-muted-foreground">
            <CheckCircle2 className="w-12 h-12 mb-3 opacity-20" />
            <p className="text-[13px] font-medium text-muted-foreground">All caught up!</p>
            <p className="text-[11px] opacity-60">No notifications in this category.</p>
          </div>
        ) : (
          <>
            {Object.entries(tabNotifications.reduce((acc: any, n: any) => {
              const dispName = n.p6_project_name || n.project_name || 'Global';
              if (!acc[dispName]) acc[dispName] = [];
              acc[dispName].push(n);
              return acc;
            }, {})).map(([projectName, group]: [string, any]) => (
              <div 
                key={projectName} 
                className={`p-3 border-b border-muted dark:border-border hover:bg-muted dark:hover:bg-white/5 transition-all group relative bg-card ${group.every((n: any) => n.is_read) ? 'opacity-70' : ''}`}
              >
                {!group.every((n: any) => n.is_read) && (
                  <div className="absolute left-0 top-0 bottom-0 w-1 bg-sky-500 rounded-r-full" />
                )}
                
                <div className="flex gap-3 relative z-10">
                  <div className="mt-0.5 p-1.5 bg-card border border-muted dark:border-gray-700 rounded-lg shadow-sm h-fit">
                    {getIcon(group[0].change_type)}
                  </div>
                  
                  <div className="flex-1 min-w-0 flex flex-col gap-1.5 mt-0.5">
                    <div className="flex justify-between items-start">
                      <span className="font-bold text-[13px] text-foreground dark:text-white truncate pr-2 group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors tracking-tight">{projectName}</span>
                      <span className="text-[9px] font-semibold text-muted-foreground whitespace-nowrap bg-muted dark:bg-card border border-border dark:border-gray-700 px-1.5 py-0.5 rounded shrink-0 shadow-sm mt-0.5">
                        {group.length} {group.length === 1 ? 'Message' : 'Messages'}
                      </span>
                    </div>

                    <div className="p-2 rounded-lg bg-muted dark:bg-gray-900/80 border border-muted dark:border-gray-700/50 mt-0.5 shadow-sm space-y-2">
                      {(expandedProjects[projectName] ? group : group.slice(0, 2)).map((n: any) => (
                        <div key={n.id} className="border-b border-border/50 dark:border-gray-700/50 pb-2 last:border-0 last:pb-0">
                          <div className="flex items-center flex-wrap gap-1.5 mb-1">
                            {n.block && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-muted-foreground border border-sky-100 dark:border-sky-500/20 shadow-sm">
                                {n.block}
                              </span>
                            )}
                            {n.activity_name && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold bg-muted dark:bg-card text-foreground dark:text-muted-foreground border border-border dark:border-gray-700 truncate max-w-full shadow-sm">
                                {n.block ? n.activity_name.replace(new RegExp(`^${n.block}\\s*-?\\s*`, 'i'), '').trim() || n.activity_name : n.activity_name}
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-foreground dark:text-muted-foreground leading-snug font-medium line-clamp-2">
                            {n.message?.replace(/^🚨\s*DELAY WARNING\s*(\(.*?\))?:\s*/i, '').replace(new RegExp(`'${n.block}'\\s*`, 'i'), '').replace(new RegExp(`${n.block}\\s*`, 'i'), '').trim()}
                          </p>
                          
                          {/* Expanded Actions for Individual Notifications */}
                          {expandedProjects[projectName] && (n.change_type?.includes('Delay') || n.message?.toLowerCase().includes('delay') || n.change_type?.includes('Critical')) && (
                            <div className="mt-2 flex flex-col gap-1.5">
                              <div className="flex gap-1.5">
                                {onSimulate && (
                                  <button 
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      onSimulate(projectName, n);
                                    }}
                                    className="flex-1 flex items-center justify-center gap-1 py-1 rounded bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400 font-bold text-[10px] uppercase tracking-wider border border-sky-200 dark:border-sky-500/20 hover:bg-sky-100 dark:hover:bg-sky-500/20 transition-colors shadow-sm"
                                  >
                                    <Play className="w-3 h-3" /> Simulate
                                  </button>
                                )}
                                <button 
                                  onClick={(e) => fetchAISuggestion(e, n)}
                                  disabled={loadingSuggestion === n.id}
                                  className="flex-1 flex items-center justify-center gap-1 py-1 rounded bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 font-bold text-[10px] uppercase tracking-wider border border-purple-200 dark:border-purple-500/20 hover:bg-purple-100 dark:hover:bg-purple-500/20 transition-colors shadow-sm disabled:opacity-50"
                                >
                                  <Sparkles className="w-3 h-3" /> 
                                  {loadingSuggestion === n.id ? 'Thinking...' : 'AI Suggestion'}
                                </button>
                              </div>

                              {aiSuggestions[n.id] && (
                                <div className="p-2 mt-0.5 rounded-lg bg-purple-50/50 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-800/50 relative overflow-hidden">
                                  <div className="absolute top-0 left-0 w-1 h-full bg-purple-400"></div>
                                  <div className="flex gap-1.5 items-start">
                                    <Sparkles className="w-3.5 h-3.5 text-purple-500 mt-0.5 shrink-0" />
                                    <p className="text-[11px] text-purple-900 dark:text-purple-100 font-medium leading-snug">
                                      {aiSuggestions[n.id]}
                                    </p>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                      {!expandedProjects[projectName] && group.length > 2 && (
                        <button 
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedProjects(prev => ({ ...prev, [projectName]: true }));
                          }}
                          className="text-[10px] text-sky-500 hover:text-sky-600 font-semibold pt-1 text-left w-full transition-colors"
                        >
                          + {group.length - 2} more notifications
                        </button>
                      )}
                      {expandedProjects[projectName] && group.length > 2 && (
                        <button 
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedProjects(prev => ({ ...prev, [projectName]: false }));
                          }}
                          className="text-[10px] text-muted-foreground hover:text-destructive font-semibold pt-1 flex justify-between w-full transition-colors"
                        >
                          <span>Show less</span>
                          <span>Close</span>
                        </button>
                      )}
                    </div>
                    
                    {/* Actions & AI Suggestions (Grouped, only when collapsed) */}
                    {!expandedProjects[projectName] && group.some((n: any) => n.change_type?.includes('Delay') || n.message?.toLowerCase().includes('delay') || n.change_type?.includes('Critical')) && (
                      <div className="mt-1 flex flex-col gap-1.5">
                        <div className="flex gap-1.5">
                          {onSimulate && (
                            <button 
                              onClick={(e) => {
                                e.stopPropagation();
                                onSimulate(projectName, group[0]);
                              }}
                              className="flex-1 flex items-center justify-center gap-1 py-1 rounded bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400 font-bold text-[10px] uppercase tracking-wider border border-sky-200 dark:border-sky-500/20 hover:bg-sky-100 dark:hover:bg-sky-500/20 transition-colors shadow-sm"
                            >
                              <Play className="w-3 h-3" /> Simulate Project
                            </button>
                          )}
                          <button 
                            onClick={(e) => fetchAISuggestion(e, group[0])}
                            disabled={loadingSuggestion === group[0].id}
                            className="flex-1 flex items-center justify-center gap-1 py-1 rounded bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 font-bold text-[10px] uppercase tracking-wider border border-purple-200 dark:border-purple-500/20 hover:bg-purple-100 dark:hover:bg-purple-500/20 transition-colors shadow-sm disabled:opacity-50"
                          >
                            <Sparkles className="w-3 h-3" /> 
                            {loadingSuggestion === group[0].id ? 'Thinking...' : 'AI Suggestion'}
                          </button>
                        </div>

                        {aiSuggestions[group[0].id] && (
                          <div className="p-2 mt-0.5 rounded-lg bg-purple-50/50 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-800/50 relative overflow-hidden">
                            <div className="absolute top-0 left-0 w-1 h-full bg-purple-400"></div>
                            <div className="flex gap-1.5 items-start">
                              <Sparkles className="w-3.5 h-3.5 text-purple-500 mt-0.5 shrink-0" />
                              <p className="text-[11px] text-purple-900 dark:text-purple-100 font-medium leading-snug">
                                {aiSuggestions[group[0].id]}
                              </p>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
            
            {tabHasMore && (
              <div className="p-4 flex justify-center border-t border-muted dark:border-border">
                <button 
                  onClick={handleLoadMore}
                  disabled={isLoadingTab}
                  className="px-4 py-1.5 bg-muted dark:bg-card hover:bg-gray-200 dark:hover:bg-gray-700 text-foreground dark:text-muted-foreground rounded-full text-[12px] font-semibold transition-colors disabled:opacity-50"
                >
                  {isLoadingTab ? 'Loading...' : 'Load More'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
