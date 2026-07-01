import React, { useState } from 'react';
import { CheckCircle2, AlertCircle, Clock, CalendarDays, TrendingUp, X, Filter } from 'lucide-react';

export default function NotificationDropdown({ notifications, onClose, onMarkAllRead, onSelectNotification }: any) {
  const [activeTab, setActiveTab] = useState('All');
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
              className={`p-4 border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-all cursor-pointer group relative bg-white dark:bg-gray-900 ${n.is_read ? 'opacity-70' : ''}`}
              onClick={() => onSelectNotification(n)}
            >
              {!n.is_read && (
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-sky-500 rounded-r-full" />
              )}
              
              <div className="flex gap-4 relative z-10">
                <div className="mt-0.5 p-2 bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-xl shadow-sm group-hover:scale-110 transition-transform h-fit">
                  {getIcon(n.change_type)}
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-start mb-1">
                    <span className="font-bold text-[13px] text-gray-900 dark:text-white truncate pr-2 group-hover:text-sky-500 transition-colors">{n.project_name}</span>
                    <span className="text-[10px] font-medium text-gray-500 whitespace-nowrap bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-full">
                      {new Date(n.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  
                  {n.block && <div className="text-[11px] font-bold text-sky-500/80 mb-1 tracking-wider uppercase">{n.block}</div>}
                  {n.activity_name && <div className="text-[12px] font-medium mb-2 truncate text-gray-900 dark:text-white">{n.activity_name}</div>}
                  
                  {/* Values Highlight */}
                  {n.old_value && n.new_value && (
                    <div className="flex items-center gap-2 mb-2 text-[12px] bg-gray-50 dark:bg-gray-800 p-2 rounded-lg border border-gray-100 dark:border-gray-700 shadow-sm inline-flex">
                      <span className="text-red-500 line-through font-semibold">{n.old_value}</span>
                      <span className="text-gray-400">➔</span>
                      <span className="text-emerald-500 font-bold">{n.new_value}</span>
                    </div>
                  )}
                  
                  <p className="text-[12px] text-gray-500 dark:text-gray-400 leading-relaxed line-clamp-2">{n.message}</p>
                  {n.reason && n.reason !== n.message && n.reason !== 'Activity date updated in Primavera P6.' && (
                    <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-1 italic">{n.reason}</p>
                  )}
                  
                  {n.action_status === 'Pending' && (
                    <div className="mt-3 flex gap-2">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider bg-orange-50 dark:bg-orange-500/10 text-orange-600 border border-orange-200 dark:border-orange-500/20 shadow-sm">
                        Action Required
                      </span>
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
