import React, { useState, useEffect, useRef } from 'react';
import {
  Bot, Send, Paperclip, Mic, Image as ImageIcon, Zap, Plus,
  FileText, Database, Sparkles, Calendar, Settings, PanelLeftClose,
  PanelLeft, MessageSquare, BarChart3, ShieldAlert, TrendingUp,
  Clock, ArrowRight, Trash2, Search, Globe, Cpu, BrainCircuit,
  Activity, ChevronDown
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

interface Message {
  id: number;
  type: 'user' | 'bot';
  content: string;
  timestamp: Date;
  sources?: string[];
}

interface Thread {
  id: number;
  title: string;
  preview: string;
  timestamp: Date;
  messageCount: number;
}

// Typing status stages for the animated indicator
const TYPING_STAGES = [
  { text: 'Interpreting query...', icon: BrainCircuit },
  { text: 'Scanning P6 schedules...', icon: Calendar },
  { text: 'Cross-referencing SAP data...', icon: Database },
  { text: 'Synthesizing intelligence...', icon: Sparkles },
];

interface AICopilotProps {
  onMinimize?: () => void;
}

export default function AICopilot({ onMinimize }: AICopilotProps = {}) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [typingStage, setTypingStage] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeThreadId, setActiveThreadId] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load threads from localStorage on mount
  useEffect(() => {
    const savedThreads = localStorage.getItem('akasha_threads_v2');
    if (savedThreads) {
      setThreads(JSON.parse(savedThreads));
    }
    const savedActive = localStorage.getItem('akasha_active_thread');
    if (savedActive) {
      const tid = parseInt(savedActive);
      setActiveThreadId(tid);
      const savedMsgs = localStorage.getItem(`akasha_msgs_${tid}`);
      if (savedMsgs) setMessages(JSON.parse(savedMsgs));
    }
  }, []);

  // Persist messages when they change
  useEffect(() => {
    if (activeThreadId && messages.length > 0) {
      localStorage.setItem(`akasha_msgs_${activeThreadId}`, JSON.stringify(messages));
    }
  }, [messages, activeThreadId]);

  // Persist threads
  useEffect(() => {
    if (threads.length > 0) {
      localStorage.setItem('akasha_threads_v2', JSON.stringify(threads));
    }
  }, [threads]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // Cycle typing stages
  useEffect(() => {
    if (!isTyping) { setTypingStage(0); return; }
    const interval = setInterval(() => {
      setTypingStage(prev => (prev + 1) % TYPING_STAGES.length);
    }, 1800);
    return () => clearInterval(interval);
  }, [isTyping]);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 160) + 'px';
    }
  }, [input]);

  const isLanding = messages.length === 0;

  const startNewThread = () => {
    const newId = Date.now();
    setActiveThreadId(newId);
    setMessages([]);
    localStorage.setItem('akasha_active_thread', String(newId));
    inputRef.current?.focus();
  };

  const loadThread = (thread: Thread) => {
    setActiveThreadId(thread.id);
    localStorage.setItem('akasha_active_thread', String(thread.id));
    const saved = localStorage.getItem(`akasha_msgs_${thread.id}`);
    if (saved) setMessages(JSON.parse(saved));
    else setMessages([]);
  };

  const deleteThread = (threadId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setThreads(prev => prev.filter(t => t.id !== threadId));
    localStorage.removeItem(`akasha_msgs_${threadId}`);
    if (activeThreadId === threadId) {
      setActiveThreadId(null);
      setMessages([]);
    }
  };

  const handleSend = async (overrideInput?: string) => {
    const text = overrideInput || input.trim();
    if (!text) return;

    // Create thread if needed
    let currentThreadId = activeThreadId;
    if (!currentThreadId) {
      currentThreadId = Date.now();
      setActiveThreadId(currentThreadId);
      localStorage.setItem('akasha_active_thread', String(currentThreadId));
    }

    const userMsg: Message = {
      id: Date.now(),
      type: 'user',
      content: text,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    // Update thread list
    if (messages.length === 0) {
      const newThread: Thread = {
        id: currentThreadId,
        title: text.substring(0, 50),
        preview: text.substring(0, 80),
        timestamp: new Date(),
        messageCount: 1
      };
      setThreads(prev => [newThread, ...prev.filter(t => t.id !== currentThreadId)].slice(0, 20));
    } else {
      setThreads(prev => prev.map(t =>
        t.id === currentThreadId ? { ...t, messageCount: t.messageCount + 1 } : t
      ));
    }

    try {
      const response = await fetch('/akasha/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: messages })
      });

      const data = await response.json();
      setIsTyping(false);

      const botMsg: Message = {
        id: Date.now() + 1,
        type: 'bot',
        content: response.ok ? data.response : `Error: ${data.detail || 'Connection failed'}`,
        timestamp: new Date(),
        sources: ['Primavera P6', 'SAP R/3', 'Project 360']
      };
      setMessages(prev => [...prev, botMsg]);
    } catch {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'bot',
        content: '⚠️ System Error: Could not reach the AKASHA AI backend. Please verify the server is running.',
        timestamp: new Date(),
      }]);
    }
  };

  const insightCards = [
    {
      icon: ShieldAlert,
      color: '#EF4444',
      title: 'Risk Analysis',
      description: 'Identify high-risk projects and material bottlenecks',
      prompt: 'Analyze all critical-risk projects and identify root causes'
    },
    {
      icon: BarChart3,
      color: '#3B82F6',
      title: 'Portfolio Performance',
      description: 'SPI/CPI breakdown across all active projects',
      prompt: 'Give me a complete SPI and CPI performance breakdown for all projects'
    },
    {
      icon: TrendingUp,
      color: '#10B981',
      title: 'Schedule Intelligence',
      description: 'Critical path delays and forecast analysis',
      prompt: 'Analyze critical path delays in the Solar Portfolio and suggest mitigations'
    },
    {
      icon: Clock,
      color: '#F59E0B',
      title: 'Board Report',
      description: 'Generate an executive summary for leadership',
      prompt: 'Draft a concise board-level status update covering schedule, cost, and procurement risks'
    },
  ];

  const suggestedFollowups = [
    'Break this down by project',
    'What are the recommended actions?',
    'Show me the financial impact',
    'Compare with last quarter',
  ];

  const currentStage = TYPING_STAGES[typingStage];
  const StageIcon = currentStage.icon;

  return (
    <div className="flex h-full w-full overflow-hidden bg-background border-t border-border/50">

      {/* ── Collapsible History Panel ── */}
      <div
        className={`${sidebarOpen ? 'w-72' : 'w-0'} transition-all duration-300 ease-in-out overflow-hidden flex-shrink-0`}
      >
        <div className="w-72 h-full flex flex-col bg-card border-r border-border/50">
          {/* Panel Header */}
          <div className="p-4 flex items-center justify-between">
            <span className="text-[11px] font-semibold text-muted-foreground/70 uppercase tracking-[0.15em]">History</span>
            <button
              onClick={startNewThread}
              className="w-7 h-7 rounded-lg bg-primary/10 hover:bg-primary/20 flex items-center justify-center text-blue-400 transition-colors"
              title="New Conversation"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Search */}
          <div className="px-4 pb-3">
            <div className="flex items-center gap-2 bg-muted rounded-lg px-3 py-2 border border-border/50">
              <Search className="w-3.5 h-3.5 text-muted-foreground/70" />
              <input
                type="text"
                placeholder="Search conversations..."
                className="bg-transparent text-xs text-foreground/90 placeholder-muted-foreground/50 outline-none flex-1"
              />
            </div>
          </div>

          {/* Threads */}
          <div className="flex-1 overflow-y-auto scrollbar-hide px-2">
            {threads.length > 0 ? (
              <div className="space-y-0.5">
                {threads.map(thread => (
                  <button
                    key={thread.id}
                    onClick={() => loadThread(thread)}
                    className={`w-full text-left px-3 py-2.5 rounded-lg transition-all duration-150 group relative ${
                      activeThreadId === thread.id
                        ? 'bg-accent text-foreground'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground/90'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-50" />
                      <span className="text-[13px] truncate flex-1">{thread.title}</span>
                    </div>
                    <button
                      onClick={(e) => deleteThread(thread.id, e)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-accent text-muted-foreground/70 hover:text-red-500 transition-all"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </button>
                ))}
              </div>
            ) : (
              <div className="px-4 py-8 text-center">
                <MessageSquare className="w-8 h-8 text-muted-foreground/30 mx-auto mb-3" />
                <p className="text-xs text-muted-foreground/50">No conversations yet</p>
                <p className="text-[10px] text-muted-foreground/30 mt-1">Start a new analysis above</p>
              </div>
            )}
          </div>

          {/* Data Sources */}
          <div className="p-4 border-t border-border/50">
            <div className="text-[10px] font-bold text-muted-foreground/50 uppercase tracking-[0.15em] mb-3">Connected Sources</div>
            <div className="space-y-2">
              <div className="flex items-center gap-2.5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.5)]"></div>
                <span className="text-[11px] text-muted-foreground">Primavera P6</span>
                <span className="text-[9px] text-emerald-500 ml-auto font-mono">LIVE</span>
              </div>
              <div className="flex items-center gap-2.5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.5)]"></div>
                <span className="text-[11px] text-muted-foreground">SAP R/3</span>
                <span className="text-[9px] text-emerald-500 ml-auto font-mono">LIVE</span>
              </div>
              <div className="flex items-center gap-2.5">
                <div className="w-1.5 h-1.5 rounded-full bg-primary shadow-[0_0_6px_rgba(59,130,246,0.5)]"></div>
                <span className="text-[11px] text-muted-foreground">Document Index</span>
                <span className="text-[9px] text-primary ml-auto font-mono">14 FILES</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Main Content Area ── */}
      <div className="flex-1 flex flex-col relative min-w-0">

        {/* Ambient Background */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="absolute top-[20%] left-[30%] w-[600px] h-[600px] bg-primary/[0.03] rounded-full blur-[150px]"></div>
          <div className="absolute bottom-[10%] right-[20%] w-[400px] h-[400px] bg-violet-500/[0.02] rounded-full blur-[120px]"></div>
        </div>

        {/* Top Bar */}
        <div className="h-14 flex items-center justify-between px-5 border-b border-border/50 bg-background/80 backdrop-blur-xl z-20 shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="w-8 h-8 rounded-lg hover:bg-muted flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
            >
              {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
            </button>

            <div className="h-5 w-px bg-border/50"></div>

            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center shadow-md">
                <BrainCircuit className="w-3.5 h-3.5 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-[13px] font-semibold text-foreground tracking-wide">AKASHA Intelligence</h1>
              </div>
            </div>

            <div className="flex items-center gap-1.5 ml-3 px-2 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
              <span className="text-[10px] text-emerald-500 font-semibold tracking-wider uppercase">Online</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-muted border border-border/50">
              <Cpu className="w-3 h-3 text-muted-foreground/70" />
              <span className="text-[10px] text-muted-foreground/70 font-mono">GPT-OSS-120B</span>
            </div>
            {onMinimize && (
              <button 
                onClick={onMinimize}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-muted text-primary hover:text-primary/80 transition-colors border border-border bg-card"
              >
                Minimize
              </button>
            )}
            <button className="w-8 h-8 rounded-lg hover:bg-muted flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors">
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* ── Landing View (No Messages) ── */}
        {isLanding ? (
          <div className="flex-1 flex flex-col items-center justify-center px-6 z-10">
            {/* Hero */}
            <div className="text-center mb-12">
              <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center shadow-md">
                <BrainCircuit className="w-8 h-8 text-primary-foreground" />
              </div>
              <h2 className="text-3xl font-light text-foreground tracking-tight mb-3">
                What can I analyze for you<span className="text-primary">?</span>
              </h2>
              <p className="text-sm text-muted-foreground/70 max-w-md mx-auto leading-relaxed">
                I have real-time access to your Primavera P6 schedules, SAP financials, and logistics data.
                Ask me anything about your portfolio.
              </p>
            </div>

            {/* Insight Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl w-full mb-10">
              {insightCards.map((card, i) => (
                <button
                  key={i}
                  onClick={() => handleSend(card.prompt)}
                  className="group text-left p-5 rounded-2xl bg-card/40 backdrop-blur-md border border-border/60 hover:bg-card hover:border-primary/40 hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] dark:hover:shadow-[0_8px_30px_rgba(59,130,246,0.1)] transition-all duration-300 hover:-translate-y-1 relative overflow-hidden"
                >
                  {/* Subtle Colored Glow Overlay on Hover */}
                  <div 
                    className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
                    style={{ background: `radial-gradient(circle at top right, ${card.color}15, transparent 70%)` }}
                  />
                  
                  <div className="relative z-10 flex items-start gap-4">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3 shadow-sm"
                      style={{ backgroundColor: `${card.color}15`, border: `1px solid ${card.color}30` }}
                    >
                      <card.icon className="w-5 h-5 transition-colors duration-300" style={{ color: card.color }} />
                    </div>
                    <div className="flex-1 min-w-0 pt-0.5">
                      <h3 className="text-[14px] font-semibold text-foreground mb-1 transition-colors duration-300">{card.title}</h3>
                      <p className="text-[12px] text-muted-foreground/80 leading-relaxed transition-colors duration-300 group-hover:text-foreground/70">{card.description}</p>
                    </div>
                    <ArrowRight 
                      className="w-4 h-4 opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300 shrink-0 mt-1" 
                      style={{ color: card.color }}
                    />
                  </div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* ── Conversation View ── */
          <div className="flex-1 overflow-y-auto scrollbar-hide z-10">
            <div className="w-full px-8 py-6 space-y-1">
              {messages.map((msg) => (
                <div key={msg.id} className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                  {msg.type === 'user' ? (
                    /* User Message */
                    <div className="flex justify-end py-3">
                      <div className="max-w-[85%] bg-primary text-primary-foreground px-4 py-3 rounded-2xl rounded-br-md shadow-md">
                        <p className="text-[13.5px] leading-relaxed">{msg.content}</p>
                      </div>
                    </div>
                  ) : (
                    /* Bot Response */
                    <div className="py-5">
                      <div className="flex items-center gap-2.5 mb-3">
                        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center">
                          <Sparkles className="w-3 h-3 text-primary-foreground" />
                        </div>
                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">AKASHA</span>
                      </div>

                      <div className="akasha-response prose dark:prose-invert max-w-none prose-p:text-[13.5px] prose-p:leading-relaxed prose-p:text-foreground/90 prose-headings:text-foreground prose-strong:text-foreground prose-code:text-blue-400 prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-card prose-pre:border prose-pre:border-border/50 prose-a:text-blue-400">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>

                      {/* Source Badges */}
                      {msg.sources && (
                        <div className="flex items-center gap-2 mt-4 flex-wrap">
                          <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider font-medium">Sources:</span>
                          {msg.sources.map((src, i) => (
                            <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted border border-border/50 text-[10px] text-muted-foreground/70">
                              <Globe className="w-2.5 h-2.5" />
                              {src}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Suggested Follow-ups */}
                      <div className="flex items-center gap-2 mt-4 flex-wrap">
                        {suggestedFollowups.map((followup, i) => (
                          <button
                            key={i}
                            onClick={() => handleSend(followup)}
                            className="px-3 py-1.5 rounded-lg bg-card border border-border/50 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted hover:border-border/80 transition-all"
                          >
                            {followup}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Typing Indicator */}
              {isTyping && (
                <div className="py-5 animate-in fade-in duration-300">
                  <div className="flex items-center gap-2.5 mb-3">
                    <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center">
                      <Sparkles className="w-3 h-3 text-primary-foreground animate-pulse" />
                    </div>
                    <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">AKASHA</span>
                  </div>

                  <div className="flex items-center gap-3 p-4 rounded-xl bg-muted/50 border border-border/50">
                    {/* Animated Bars */}
                    <div className="flex items-end gap-[3px] h-5">
                      <div className="w-[3px] bg-primary rounded-full animate-pulse" style={{ height: '60%', animationDelay: '0ms' }}></div>
                      <div className="w-[3px] bg-primary rounded-full animate-pulse" style={{ height: '100%', animationDelay: '150ms' }}></div>
                      <div className="w-[3px] bg-violet-500 rounded-full animate-pulse" style={{ height: '40%', animationDelay: '300ms' }}></div>
                      <div className="w-[3px] bg-violet-500 rounded-full animate-pulse" style={{ height: '80%', animationDelay: '450ms' }}></div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StageIcon className="w-3.5 h-3.5 text-primary" />
                      <span className="text-[12px] text-muted-foreground font-mono">{currentStage.text}</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        {/* ── Floating Command Bar ── */}
        <div className={`px-5 ${isLanding ? '' : 'pb-5'} z-20 relative`}>
          <div className="w-full">
            <div className="bg-card border border-border rounded-2xl shadow-lg overflow-hidden focus-within:border-primary/40 focus-within:shadow-[0_0_0_1px_rgba(59,130,246,0.15)] transition-all duration-200">
              {/* Input */}
              <div className="flex items-end px-4 pt-3 pb-2 gap-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder="Ask anything about your portfolio..."
                  className="flex-1 bg-transparent text-[14px] text-foreground placeholder-muted-foreground/50 outline-none resize-none min-h-[28px] max-h-[160px] leading-relaxed"
                  rows={1}
                />
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isTyping}
                  className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-all duration-200 mb-0.5 ${
                    input.trim() && !isTyping
                      ? 'bg-primary text-primary-foreground shadow-md hover:bg-primary/90'
                      : 'bg-muted text-muted-foreground/50 cursor-not-allowed'
                  }`}
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Bottom Tools Row */}
              <div className="flex items-center justify-between px-4 pb-2.5 pt-0.5">
                <div className="flex items-center gap-1">
                  <button className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground/90 transition-colors" title="Attach file">
                    <Paperclip className="w-4 h-4" />
                  </button>
                  <button className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground/90 transition-colors" title="Image">
                    <ImageIcon className="w-4 h-4" />
                  </button>
                  <button className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground/90 transition-colors" title="Voice input">
                    <Mic className="w-4 h-4" />
                  </button>
                  <div className="h-4 w-px bg-border/50 mx-1"></div>
                  <button className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground/90 transition-colors flex items-center gap-1" title="Deep analysis mode">
                    <Activity className="w-4 h-4" />
                    <span className="text-[10px] hidden sm:inline">Deep Analysis</span>
                  </button>
                </div>
                <span className="text-[10px] text-muted-foreground/30 hidden sm:inline">AKASHA AI · Enterprise Intelligence</span>
              </div>
            </div>

            {/* Disclaimer */}
            {!isLanding && (
              <div className="text-center mt-2">
                <span className="text-[10px] text-muted-foreground/30">AI-generated analysis. Verify critical executive decisions independently.</span>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
