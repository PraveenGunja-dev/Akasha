import React, { useState, useEffect, useRef } from 'react';
import { X, Send, Save, AlertTriangle, MessageSquarePlus, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

export default function PMAGThreadPanel({ notification, onClose, onResolved }: any) {
  const [messages, setMessages] = useState<any[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [pushing, setPushing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Editable state
  const [editValue, setEditValue] = useState(notification?.new_value || '');

  useEffect(() => {
    if (notification) {
      setEditValue(notification.new_value || '');
      fetchThread();
      
      if (notification.action_status === 'Pending') {
        fetch(`/akasha/api/notifications/${notification.id}/action?status=Acknowledged`, { method: 'POST' });
      }
    }
  }, [notification]);

  const fetchThread = async () => {
    try {
      const res = await fetch(`/akasha/api/notifications/${notification.id}/thread`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data);
        setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMessage.trim()) return;
    
    setLoading(true);
    try {
      const res = await fetch(`/akasha/api/notifications/${notification.id}/thread`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: newMessage, sender: 'User' })
      });
      if (res.ok) {
        setNewMessage('');
        fetchThread();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handlePushToP6 = async () => {
    const confirmDelete = window.confirm("Would you like to delete this conversation history and save?");
    
    setPushing(true);
    try {
      let updates: any = {};
      
      if (notification.category === 'Scope') {
         if (notification.p6_type === 'ResourceAssignment' && notification.activity_name) {
             updates = { resources: { [notification.activity_name]: { p6ObjectId: notification.p6_object_id, actualUnits: editValue } } };
         } else {
             updates = { actual_total_cost: editValue };
         }
      } else {
         updates = { finish_date: editValue }; 
      }

      const res = await fetch(`/akasha/api/notifications/${notification.id}/push`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          updates,
          delete_thread: confirmDelete
        })
      });
      
      const data = await res.json();
      if (res.ok && data.success) {
        toast.success("Changes successfully pushed to Oracle P6!");
        onResolved();
        onClose();
      } else {
        toast.error(data.message || "Failed to push to P6");
      }
    } catch (e) {
      console.error(e);
      toast.error("Network error while pushing to P6");
    } finally {
      setPushing(false);
    }
  };

  if (!notification) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 transition-opacity" onClick={onClose} />
      <div className="fixed top-0 right-0 h-full w-[450px] bg-card shadow-2xl z-50 flex flex-col border-l border-border dark:border-border transform transition-transform duration-300 overflow-hidden">
        
        {/* Header - Glassmorphism */}
        <div className="h-[73px] shrink-0 border-b border-border dark:border-border flex items-center justify-between px-6 bg-gradient-to-r from-sky-500/10 to-transparent">
          <div>
            <h2 className="font-bold text-foreground dark:text-white text-lg tracking-tight">PMAG Action Center</h2>
            <p className="text-xs text-muted-foreground truncate max-w-[300px]">{notification.project_name}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-muted dark:hover:bg-card rounded-full transition-colors">
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Issue Details Card */}
        <div className="p-6 border-b border-border dark:border-border bg-card shrink-0 shadow-sm relative z-10">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-1.5 bg-warning/10 dark:bg-orange-900/20 rounded-lg">
              <AlertTriangle className="w-4 h-4 text-warning" />
            </div>
            <span className="font-semibold text-[15px] text-foreground dark:text-white">{notification.change_type}</span>
          </div>
          
          <div className="space-y-3 mb-5">
            {notification.block && (
              <div className="flex justify-between items-center text-[13px]">
                <span className="text-muted-foreground font-medium">Block:</span>
                <span className="font-semibold text-foreground dark:text-white">{notification.block}</span>
              </div>
            )}
            {notification.activity_name && (
              <div className="flex justify-between items-center text-[13px]">
                <span className="text-muted-foreground font-medium">Activity:</span>
                <span className="font-semibold text-foreground dark:text-white text-right max-w-[240px] truncate">{notification.activity_name}</span>
              </div>
            )}
          </div>

          {notification.category !== 'Scope' ? (
            <>
              <div className="bg-sky-50 dark:bg-sky-900/10 rounded-xl p-4 border border-sky-100 dark:border-sky-800/50 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-24 h-24 bg-sky-500/5 rounded-full blur-2xl transform translate-x-1/2 -translate-y-1/2" />
                <div className="text-[11px] font-semibold tracking-wider uppercase text-sky-600 dark:text-sky-400 mb-2">Value Change</div>
                <div className="flex items-center gap-3 relative z-10">
                  {notification.old_value && (
                    <>
                      <span className="text-destructive line-through font-semibold text-sm opacity-90">{notification.old_value}</span>
                      <span className="text-muted-foreground">➔</span>
                    </>
                  )}
                  <input 
                    type="text" 
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    placeholder="Enter new value..."
                    className="bg-card border border-emerald-500/40 text-success dark:text-success font-bold px-3 py-1.5 rounded-lg text-[15px] w-full focus:outline-none focus:ring-2 focus:ring-emerald-500/30 transition-all shadow-sm"
                  />
                </div>
                {notification.reason && (
                  <p className="text-[12px] text-foreground dark:text-muted-foreground mt-3 italic leading-relaxed relative z-10">{notification.reason}</p>
                )}
              </div>

              <button 
                onClick={handlePushToP6}
                disabled={pushing || !editValue}
                className="w-full mt-5 flex items-center justify-center gap-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-bold py-3 rounded-xl text-[13px] transition-all shadow-[0_4px_15px_rgba(16,185,129,0.3)] hover:shadow-[0_6px_20px_rgba(16,185,129,0.4)] disabled:opacity-70 disabled:pointer-events-none"
              >
                {pushing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                Resolve & Push to P6
              </button>
            </>
          ) : (
            <div className="bg-sky-50 dark:bg-sky-900/10 rounded-xl p-4 border border-sky-100 dark:border-sky-800/50 relative overflow-hidden">
              <div className="text-[11px] font-semibold tracking-wider uppercase text-sky-600 dark:text-sky-400 mb-2">Value</div>
              <div className="flex items-center gap-3 relative z-10">
                {notification.old_value && (
                  <>
                    <span className="text-destructive line-through font-semibold text-sm opacity-90">{notification.old_value}</span>
                    <span className="text-muted-foreground">➔</span>
                  </>
                )}
                <span className="text-success dark:text-success font-bold text-[15px]">{notification.new_value}</span>
              </div>
              {notification.reason && (
                <p className="text-[12px] text-foreground dark:text-muted-foreground mt-3 italic leading-relaxed relative z-10">{notification.reason}</p>
              )}
            </div>
          )}
        </div>

        {/* PMAG Thread - Chat Area */}
        <div className="flex-1 overflow-y-auto p-6 bg-muted dark:bg-gray-900/30 flex flex-col gap-4 relative">
          
          {messages.length === 0 ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground opacity-80">
              <MessageSquarePlus className="w-12 h-12 mb-3 stroke-1" />
              <p className="text-[13px] font-medium">No messages yet.</p>
              <p className="text-[11px] mt-1">Start a conversation with the PMAG Team below.</p>
            </div>
          ) : (
            <div className="text-center text-[10px] uppercase font-bold tracking-wider text-muted-foreground mb-2">
              Conversation Started
            </div>
          )}
          
          {messages.map((msg, i) => (
            <div key={i} className={`flex flex-col max-w-[85%] ${msg.sender === 'User' ? 'self-end items-end' : 'self-start items-start'}`} z-10>
              <span className="text-[10px] text-muted-foreground mb-1 px-1 font-medium">{msg.sender}</span>
              <div className={`px-4 py-2.5 rounded-2xl text-[13px] leading-relaxed shadow-sm ${msg.sender === 'User' ? 'bg-sky-500 text-white rounded-br-sm' : 'bg-card border border-border dark:border-gray-700 text-foreground dark:text-white rounded-bl-sm'}`}>
                {msg.message}
              </div>
              <span className="text-[9px] text-muted-foreground mt-1 px-1">
                {new Date(msg.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
              </span>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Message Input - Bottom Pinned */}
        <div className="p-4 bg-card border-t border-border dark:border-border shadow-[0_-10px_30px_rgba(0,0,0,0.03)] z-10 relative">
          <form onSubmit={handleSendMessage} className="flex gap-2">
            <input 
              type="text"
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder="Type your message to PMAG..."
              className="flex-1 bg-muted dark:bg-card border border-border dark:border-gray-700 focus:border-sky-500 focus:bg-white dark:focus:bg-card focus:ring-2 focus:ring-sky-500/20 rounded-xl text-[13px] px-4 py-3 transition-all"
            />
            <button 
              type="submit"
              disabled={loading || !newMessage.trim()}
              className="bg-sky-500 hover:bg-sky-600 disabled:bg-gray-200 dark:disabled:bg-card disabled:text-muted-foreground text-white rounded-xl px-4 flex items-center justify-center transition-all shadow-[0_4px_10px_rgba(14,165,233,0.2)] disabled:shadow-none"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
