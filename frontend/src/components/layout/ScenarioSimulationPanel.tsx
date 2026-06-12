import React, { useState, useRef, useEffect } from 'react';
import { Bot, Send, Sparkles, Loader2, FastForward, Sliders, X, Maximize2, MoreVertical, Search, Lightbulb, Plus, Settings2, PictureInPicture } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Message {
  id?: number;
  type: 'user' | 'bot';
  content: string;
  timestamp?: Date | string;
  sources?: string[];
}

interface ScenarioSimulationPanelProps {
  isOpen: boolean;
  setIsOpen: (val: boolean) => void;
  onMaximize?: () => void;
  projectId?: string;
}

export default function ScenarioSimulationPanel({ isOpen, setIsOpen, onMaximize, projectId }: ScenarioSimulationPanelProps) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      const savedActive = localStorage.getItem('akasha_active_thread');
      if (savedActive) {
        const tid = parseInt(savedActive);
        const savedMsgs = localStorage.getItem(`akasha_msgs_${tid}`);
        if (savedMsgs) {
          setMessages(JSON.parse(savedMsgs));
        }
      }
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [isOpen]);

  // Also auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (overrideText?: string) => {
    const textToSend = overrideText || input.trim();
    if (!textToSend || loading) return;
    
    setInput('');
    
    const userMsg: Message = {
      id: Date.now(),
      type: 'user',
      content: textToSend,
      timestamp: new Date()
    };
    
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    
    let activeThreadId = localStorage.getItem('akasha_active_thread');
    let currentThreadId = activeThreadId ? parseInt(activeThreadId) : null;
    
    if (!currentThreadId) {
      currentThreadId = Date.now();
      localStorage.setItem('akasha_active_thread', String(currentThreadId));
      
      const newThread = {
        id: currentThreadId,
        title: textToSend.substring(0, 50),
        preview: textToSend.substring(0, 80),
        timestamp: new Date(),
        messageCount: 1
      };
      const savedThreadsStr = localStorage.getItem('akasha_threads_v2');
      const savedThreads = savedThreadsStr ? JSON.parse(savedThreadsStr) : [];
      localStorage.setItem('akasha_threads_v2', JSON.stringify([newThread, ...savedThreads].slice(0, 20)));
    } else {
      const savedThreadsStr = localStorage.getItem('akasha_threads_v2');
      if (savedThreadsStr) {
        let savedThreads = JSON.parse(savedThreadsStr);
        savedThreads = savedThreads.map((t: any) => t.id === currentThreadId ? { ...t, messageCount: t.messageCount + 1 } : t);
        localStorage.setItem('akasha_threads_v2', JSON.stringify(savedThreads));
      }
    }
    
    localStorage.setItem(`akasha_msgs_${currentThreadId}`, JSON.stringify(newMessages));
    setLoading(true);

    try {
      const res = await fetch('/akasha/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: textToSend, history: newMessages.slice(-10), projectId })
      });
      const data = await res.json();
      
      const botMsg: Message = {
        id: Date.now() + 1,
        type: 'bot',
        content: res.ok ? data.response : `Error: ${data.detail || 'Connection failed'}`,
        timestamp: new Date(),
        sources: ['Simulation Engine']
      };
      const finalMessages = [...newMessages, botMsg];
      setMessages(finalMessages);
      localStorage.setItem(`akasha_msgs_${currentThreadId}`, JSON.stringify(finalMessages));
    } catch {
      const errorMsg: Message = {
        id: Date.now() + 1,
        type: 'bot',
        content: 'Simulation engine error. Please try again.',
        timestamp: new Date()
      };
      const finalMessages = [...newMessages, errorMsg];
      setMessages(finalMessages);
      localStorage.setItem(`akasha_msgs_${currentThreadId}`, JSON.stringify(finalMessages));
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed top-[88px] right-6 w-[420px] h-[calc(100vh-110px)] flex flex-col bg-card border border-border/50 z-[60] shadow-2xl rounded-2xl animate-in slide-in-from-right-8 duration-300 fade-in overflow-hidden">
      
      {/* Header */}
      <div className="flex items-center justify-end px-3 py-2">
        <div className="flex items-center gap-1 relative">
          <button onClick={() => setShowHistory(!showHistory)} className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="History">
            <MoreVertical className="w-5 h-5" />
          </button>
          
          {showHistory && (
             <div className="absolute top-full right-20 mt-1 w-64 bg-card border border-border rounded-xl shadow-xl py-2 z-50">
               <div className="px-4 py-2 text-xs font-bold text-muted-foreground uppercase tracking-wider border-b border-border/50 mb-1">Recent History</div>
               <div className="max-h-48 overflow-y-auto custom-scrollbar">
                 <button className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors truncate">What if SAP delivery slips?</button>
                 <button className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors truncate">Show critical path risks</button>
                 <button className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors truncate">Analyze budget variance</button>
               </div>
             </div>
          )}

          {onMaximize && (
            <button onClick={onMaximize} className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="Detach / Maximize">
              <PictureInPicture className="w-5 h-5" />
            </button>
          )}
          <button onClick={() => setIsOpen(false)} className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="Close">
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6 custom-scrollbar overscroll-contain" data-lenis-prevent="true">
        {messages.length === 0 && (
          <div className="flex flex-col justify-end h-full px-2 pb-6 animate-fade-up">
            <h2 className="text-[28px] font-medium bg-gradient-to-r from-[#4285f4] via-[#ea4335] to-[#fbbc04] bg-clip-text text-transparent mb-1">Hello, Praveen</h2>
            <h3 className="text-[28px] font-medium text-foreground/70 mb-10">How can I help you today?</h3>
            
            <div className="flex flex-col gap-3 w-full">
              {[
                { icon: <Sparkles className="w-4 h-4 text-[#4285f4]" />, text: 'What can you do?' },
                { icon: <Search className="w-4 h-4 text-[#ea4335]" />, text: 'What kinds of questions can I ask?' },
                { icon: <Lightbulb className="w-4 h-4 text-[#fbbc04]" />, text: 'Help me think through a problem' }
              ].map((q, i) => (
                <button key={i} onClick={() => sendMessage(q.text)}
                  className="text-[13px] text-left px-4 py-3.5 rounded-2xl border border-border/30 bg-muted/40 hover:bg-muted/80 transition-colors text-foreground/90 flex items-center gap-3 w-max max-w-full group">
                  {q.icon}
                  <span className="truncate">{q.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'} animate-fade-up`} style={{animationDelay: '50ms'}}>
            <div className={`max-w-[85%] px-5 py-3 rounded-3xl text-[14px] leading-relaxed ${
              msg.type === 'user'
                ? 'bg-muted/60 text-foreground rounded-br-sm'
                : 'bg-transparent text-foreground'
            }`}>
              {msg.type === 'bot' && (
                <div className="flex items-center gap-3 mb-2">
                  <Sparkles className="w-4 h-4 text-[#4285f4]" />
                  <span className="text-xs font-semibold text-foreground/70">AKASHA AI</span>
                </div>
              )}
              {msg.type === 'bot' ? (
                <div className="akasha-response prose prose-sm max-w-none dark:prose-invert ml-7">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              ) : msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start animate-fade-up">
            <div className="px-5 py-3">
              <div className="flex items-center gap-3 mb-2">
                <Sparkles className="w-4 h-4 text-[#4285f4] animate-pulse" />
                <span className="text-xs font-semibold text-foreground/70">AKASHA AI</span>
              </div>
              <div className="flex items-center gap-2 ml-7">
                <Loader2 className="w-4 h-4 text-primary animate-spin" />
                <span className="text-sm text-muted-foreground">Thinking...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 pt-0">
        <div className="flex flex-col bg-muted/30 rounded-[24px] p-1.5 border border-border/50 focus-within:bg-muted/60 focus-within:border-border transition-all">
          <div className="flex items-center px-3 pt-2 pb-1">
            <input ref={inputRef} type="text" value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
              placeholder="Ask AKASHA..."
              className="flex-1 bg-transparent text-[15px] text-foreground placeholder-muted-foreground py-1 focus:outline-none"
            />
          </div>
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-1">
              <button className="p-2 rounded-full hover:bg-muted text-muted-foreground transition-colors" title="Upload file">
                <Plus className="w-5 h-5" />
              </button>
              <button className="p-2 rounded-full hover:bg-muted text-muted-foreground transition-colors" title="Settings">
                <Settings2 className="w-4 h-4" />
              </button>
            </div>
            <button onClick={() => sendMessage()} disabled={!input.trim() || loading}
              className="p-2.5 rounded-full text-foreground hover:bg-muted transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="text-center mt-3">
          <p className="text-[10px] text-muted-foreground/60">AKASHA AI may display inaccurate info, so double-check its responses.</p>
        </div>
      </div>
    </div>
  );
}
