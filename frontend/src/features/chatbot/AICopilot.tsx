import React, { useState, useEffect, useRef } from 'react';
import {
  Bot, Send, Paperclip, Mic, Image as ImageIcon, Zap, Plus,
  FileText, Database, Sparkles, Calendar, Settings, PanelLeftClose,
  PanelLeft, MessageSquare, BarChart3, ShieldAlert, TrendingUp,
  Clock, ArrowRight, Trash2, Search, Globe, Cpu, BrainCircuit,
  Activity, ChevronDown, ThumbsUp, ThumbsDown, CheckCircle2, History, X,
  Square, Loader2
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { useAuth } from '../../context/AuthContext';
import { metadataFromEvent, streamChat } from './chatSseClient';

interface Message {
  id: number;
  type: 'user' | 'bot';
  content: string;
  timestamp: Date;
  sources?: string[];
  imageData?: string; // Optional base64 image data attached to the message
  metadata?: {
    message_id?: number;
    data_as_of?: string | null;
    latency_ms?: number;
    intent?: string;
  };
  feedbackStatus?: 'none' | 'liked' | 'disliked';
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
  { text: 'Interpreting query...', icon: Search },
  { text: 'Scanning P6 schedules...', icon: Calendar },
  { text: 'Cross-referencing SAP data...', icon: Database },
  { text: 'Aggregating results...', icon: Activity },
];

interface AICopilotProps {
  onMinimize?: () => void;
  projectId?: string | null;
}

export default function AICopilot({ onMinimize, projectId }: AICopilotProps = {}) {
  const { token } = useAuth();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [typingStage, setTypingStage] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeThreadId, setActiveThreadId] = useState<number | null>(null);
  const [suggestedFollowups, setSuggestedFollowups] = useState<string[]>([]);
  const [isDeepAnalysis, setIsDeepAnalysis] = useState(false);
  
  // Voice and Image states
  const [isListening, setIsListening] = useState(false);
  const [imageFile, setImageFile] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const startListening = () => {
    const SpeechRecognitionAPI = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) {
      alert('Your browser does not support Speech Recognition.');
      return;
    }
    const recognition = new SpeechRecognitionAPI();
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    
    recognition.onresult = (event: any) => {
      const transcript = Array.from(event.results)
        .map((result: any) => result[0].transcript)
        .join('');
      setInput(transcript);
    };

    recognition.start();
  };

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setImageFile(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  // Load threads from localStorage on mount
  useEffect(() => {
    const savedThreads = localStorage.getItem('akasha_threads_v2');
    if (savedThreads) {
      setThreads(JSON.parse(savedThreads));
    }
    // We intentionally do not auto-load the last active thread
    // so the user starts with the landing view every time.
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

  const submitFeedback = async (msgId: number, backendMessageId: number, type: 'thumbs_up' | 'thumbs_down') => {
    try {
      await fetch('/akasha/api/chat/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messageId: backendMessageId,
          feedbackType: type,
        })
      });
      setMessages(prev => prev.map(m => 
        m.id === msgId ? { ...m, feedbackStatus: type === 'thumbs_up' ? 'liked' : 'disliked' } : m
      ));
    } catch (e) {
      console.error("Failed to submit feedback", e);
    }
  };

  const handleSend = async (overrideInput?: string) => {
    const text = overrideInput || input.trim();
    if (!text && !imageFile) return;

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
      timestamp: new Date(),
      imageData: imageFile || undefined
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    const currentImageData = imageFile;
    setImageFile(null);
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
      const controller = new AbortController();
      abortControllerRef.current = controller;
      setIsStreaming(true);

      let botContent = '';
      const botMsgId = Date.now() + 1;
      
      // Add empty bot message that we will append to
      setMessages(prev => [...prev, {
        id: botMsgId,
        type: 'bot',
        content: '',
        timestamp: new Date(),
        feedbackStatus: 'none'
      }]);
      
      setIsTyping(false);

      await streamChat({
        message: text,
        history: messages,
        projectId: projectId && projectId !== 'All' ? projectId : undefined,
        sessionId: currentThreadId.toString(),
        isDeepAnalysis,
        imageData: currentImageData,
        mode: isDeepAnalysis ? 'analysis' : 'auto',
        client_version: 'akasha-web-1',
      }, {
        token,
        signal: controller.signal,
        onEvent: (data) => {
          if (data.type === 'answer_delta' || data.type === 'token') {
            botContent += data.content || '';
            setMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, content: botContent } : m));
          } else if (data.type === 'clarification_required') {
            botContent = data.question || 'I need one clarification before I can answer.';
            setMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, content: botContent } : m));
          } else if (data.type === 'run_completed' || data.type === 'metadata') {
            setSuggestedFollowups(data.suggestions || []);
            const metadata = metadataFromEvent(data);
            setMessages(prev => prev.map(m => m.id === botMsgId ? {
              ...m,
              metadata,
              sources: metadata?.sources?.tables || data.sources || []
            } : m));
          } else if (data.type === 'error') {
            botContent = data.message || 'The chatbot run failed before completion.';
            setMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, content: botContent } : m));
          }
        },
      });
      
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        // User stopped the generation — keep partial content
      } else {
        setIsTyping(false);
        setMessages(prev => [...prev, {
          id: Date.now() + 1,
          type: 'bot',
          content: '⚠️ System Error: Could not reach the AKASHA AI backend. Please verify the server is running.',
          timestamp: new Date(),
          feedbackStatus: 'none'
        }]);
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsTyping(false);
      setIsStreaming(false);
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

  const currentStage = TYPING_STAGES[typingStage];
  const StageIcon = currentStage.icon;

  return (
    <div className="flex h-full w-full overflow-hidden bg-background border-t border-border relative">
      {/* ── Main Content Area ── */}
      <div className="flex-1 flex flex-col relative min-w-0">

        {/* Ambient Background */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="absolute top-[20%] left-[30%] w-[600px] h-[600px] bg-primary/[0.03] rounded-full blur-[150px]"></div>
          <div className="absolute bottom-[10%] right-[20%] w-[400px] h-[400px] bg-violet-500/[0.02] rounded-full blur-[120px]"></div>
        </div>

        {/* Top Bar */}
        <div className="h-14 flex items-center justify-between px-5 border-b border-border bg-background/80 backdrop-blur-xl z-20 shrink-0">
          <div className="flex items-center gap-3 relative">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${sidebarOpen ? 'bg-primary/10 text-primary' : 'hover:bg-muted text-muted-foreground hover:text-foreground'}`}
              title="View History"
            >
              <History className="w-4 h-4" />
            </button>
            
            {/* History Modal */}
            {sidebarOpen && (
              <div className="absolute top-12 left-0 w-80 bg-card border border-border shadow-2xl rounded-xl z-50 flex flex-col overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                <div className="p-3 flex items-center justify-between border-b border-border/50 bg-muted">
                  <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Chat History</span>
                  <button
                    onClick={startNewThread}
                    className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium text-primary hover:bg-primary/100/10 transition-colors"
                  >
                    <Plus className="w-3 h-3" /> New
                  </button>
                </div>
                <div className="p-2 border-b border-border/50">
                  <div className="flex items-center gap-2 bg-background rounded-md px-2 py-1.5 border border-border">
                    <Search className="w-3.5 h-3.5 text-muted-foreground/70 shrink-0" />
                    <input
                      type="text"
                      placeholder="Search conversations..."
                      className="bg-transparent text-[11px] text-foreground placeholder-muted-foreground outline-none flex-1 min-w-0"
                    />
                  </div>
                </div>
                <div className="max-h-64 overflow-y-auto scrollbar-hide p-1.5">
                  {threads.length > 0 ? (
                    <div className="space-y-0.5">
                      {threads.map(thread => (
                        <button
                          key={thread.id}
                          onClick={() => { loadThread(thread); setSidebarOpen(false); }}
                          className={`w-full text-left px-2.5 py-2 rounded-md transition-all duration-150 group/item relative flex items-center gap-2.5 ${
                            activeThreadId === thread.id
                              ? 'bg-primary/5 text-primary'
                              : 'text-muted-foreground hover:bg-muted hover:text-foreground/90'
                          }`}
                        >
                          <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-70" />
                          <span className="text-[12px] font-medium truncate flex-1">
                            {thread.title}
                          </span>
                          <button
                            onClick={(e) => { e.stopPropagation(); deleteThread(thread.id, e); }}
                            className="p-1 rounded hover:bg-destructive/100/10 text-muted-foreground/50 hover:text-destructive opacity-0 group-hover/item:opacity-100 transition-all duration-200"
                          >
                            <Trash2 className="w-3 h-3 shrink-0" />
                          </button>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="py-6 text-center">
                      <p className="text-[11px] text-muted-foreground/60">No conversations yet</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="h-5 w-px bg-border/50 mx-1"></div>

            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center shadow-md">
                <MessageSquare className="w-3.5 h-3.5 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-[13px] font-semibold text-foreground tracking-wide">Ask Akasha</h1>
              </div>
            </div>

            <div className="flex items-center gap-1.5 ml-3 px-2 py-1 rounded-md bg-success/100/10 border border-success/20">
              <div className="w-1.5 h-1.5 rounded-full bg-success/100 animate-pulse"></div>
              <span className="text-[10px] text-success font-semibold tracking-wider uppercase">Online</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
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
                <MessageSquare className="w-8 h-8 text-primary-foreground" />
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
                  className="group text-left p-5 rounded-2xl bg-white/40 backdrop-blur-md border border-border/60 hover:bg-card hover:border-primary/40 hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] dark:hover:shadow-[0_8px_30px_rgba(59,130,246,0.1)] transition-all duration-300 hover:-translate-y-1 relative overflow-hidden"
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
          <div className="flex-1 overflow-y-auto scrollbar-hide z-10" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
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
                          <MessageSquare className="w-3 h-3 text-primary-foreground" />
                        </div>
                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">AKASHA</span>
                      </div>

                      <div className="akasha-response prose dark:prose-invert max-w-[60%] prose-p:text-[13.5px] prose-p:leading-relaxed prose-p:text-foreground/90 prose-headings:text-foreground prose-headings:text-[15px] prose-strong:text-primary prose-strong:font-semibold prose-code:text-primary prose-code:bg-primary/100/10 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-card prose-pre:border prose-pre:border-border prose-a:text-primary prose-li:text-[13px] prose-li:text-foreground/85">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>

                      {/* Source Badges & Metadata */}
                      <div className="flex flex-col gap-2 mt-4">
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider font-medium">Sources:</span>
                            {msg.sources.map((src, i) => (
                              <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted border border-border text-[10px] text-muted-foreground/70">
                                <Globe className="w-2.5 h-2.5" />
                                {src}
                              </span>
                            ))}
                          </div>
                        )}
                        
                        {msg.metadata && (
                          <div className="flex items-center gap-4 text-[10px] text-muted-foreground/50">
                            {msg.metadata.data_as_of && (
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                Data as of: {new Date(msg.metadata.data_as_of).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                              </span>
                            )}
                            {msg.metadata.latency_ms && (
                              <span className="flex items-center gap-1">
                                <Zap className="w-3 h-3" />
                                Generated in {(msg.metadata.latency_ms / 1000).toFixed(1)}s
                              </span>
                            )}
                            
                            {/* Feedback System */}
                            {msg.metadata.message_id && (
                              <div className="flex items-center gap-1 ml-auto">
                                <button 
                                  onClick={() => submitFeedback(msg.id, msg.metadata!.message_id!, 'thumbs_up')}
                                  disabled={msg.feedbackStatus !== 'none'}
                                  className={`p-1 rounded hover:bg-muted transition-colors ${msg.feedbackStatus === 'liked' ? 'text-success bg-success/100/10' : ''}`}
                                  title="Good response"
                                >
                                  <ThumbsUp className="w-3.5 h-3.5" />
                                </button>
                                <button 
                                  onClick={() => submitFeedback(msg.id, msg.metadata!.message_id!, 'thumbs_down')}
                                  disabled={msg.feedbackStatus !== 'none'}
                                  className={`p-1 rounded hover:bg-muted transition-colors ${msg.feedbackStatus === 'disliked' ? 'text-destructive bg-destructive/100/10' : ''}`}
                                  title="Poor response"
                                >
                                  <ThumbsDown className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Suggested Follow-ups */}
                      {msg.id === messages[messages.length - 1].id && suggestedFollowups.length > 0 && (
                        <div className="flex items-center gap-2 mt-4 flex-wrap">
                          {suggestedFollowups.map((followup, i) => (
                            <button
                              key={i}
                              onClick={() => handleSend(followup)}
                              className="px-3 py-1.5 rounded-lg bg-card border border-border text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted hover:border-border/80 transition-all"
                            >
                              {followup}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {/* Typing Indicator — Inline Subtle */}
              {isTyping && (
                <div className="py-3 animate-in fade-in duration-300">
                  <div className="flex items-center gap-2.5">
                    <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center">
                      <Loader2 className="w-3 h-3 text-primary-foreground animate-spin" />
                    </div>
                    <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">AKASHA</span>
                    <span className="text-[11px] text-muted-foreground/60 font-mono animate-pulse">{currentStage.text}</span>
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
              {/* Image Preview */}
              {imageFile && (
                <div className="px-4 pt-3 pb-1">
                  <div className="relative inline-block">
                    <img src={imageFile} alt="Attached" className="h-16 w-16 object-cover rounded-md border border-border" />
                    <button 
                      onClick={() => setImageFile(null)}
                      className="absolute -top-2 -right-2 w-5 h-5 bg-background border border-border rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              )}
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
                {isStreaming ? (
                  <button
                    onClick={handleStop}
                    className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 transition-all duration-200 mb-0.5 bg-destructive/100 text-white shadow-md hover:bg-red-600 animate-pulse"
                    title="Stop generating"
                  >
                    <Square className="w-3.5 h-3.5 fill-current" />
                  </button>
                ) : (
                  <button
                    onClick={() => handleSend()}
                    disabled={(!input.trim() && !imageFile) || isTyping}
                    className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 transition-all duration-200 mb-0.5 ${
                      (input.trim() || imageFile) && !isTyping
                        ? 'bg-primary text-primary-foreground shadow-md hover:bg-primary/90'
                        : 'bg-muted text-muted-foreground/50 cursor-not-allowed'
                    }`}
                  >
                    <Send className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {/* Bottom Tools Row */}
              <div className="flex items-center justify-between px-4 pb-2.5 pt-0.5">
                <div className="flex items-center gap-1">
                  <button className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground/90 transition-colors" title="Attach file">
                    <Paperclip className="w-4 h-4" />
                  </button>
                  <input type="file" ref={fileInputRef} hidden accept="image/*" onChange={handleImageChange} />
                  <button 
                    onClick={() => fileInputRef.current?.click()}
                    className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground/90 transition-colors" 
                    title="Image"
                  >
                    <ImageIcon className="w-4 h-4" />
                  </button>
                  <button 
                    onClick={startListening}
                    className={`p-1.5 rounded-lg transition-colors ${isListening ? 'bg-destructive/100/10 text-destructive hover:bg-destructive/100/20' : 'hover:bg-muted text-muted-foreground hover:text-foreground/90'}`}
                    title="Voice input"
                  >
                    <Mic className="w-4 h-4" />
                  </button>
                  <div className="h-4 w-px bg-border/50 mx-1"></div>
                  <button 
                    onClick={() => setIsDeepAnalysis(!isDeepAnalysis)}
                    className={`p-1.5 rounded-lg transition-colors flex items-center gap-1 ${
                      isDeepAnalysis 
                        ? 'bg-primary/20 text-primary border border-primary/30 shadow-[0_0_10px_rgba(59,130,246,0.3)]' 
                        : 'hover:bg-muted text-muted-foreground hover:text-foreground/90'
                    }`} 
                    title="Deep Analysis Agent Mode"
                  >
                    <Activity className={`w-4 h-4 ${isDeepAnalysis ? 'animate-pulse' : ''}`} />
                    <span className="text-[10px] hidden sm:inline">{isDeepAnalysis ? 'Deep Analysis: ON' : 'Deep Analysis'}</span>
                  </button>
                </div>
                <span className="text-[10px] text-muted-foreground/30 hidden sm:inline">Akasha Platform · Enterprise Data</span>
              </div>
            </div>

            {/* Disclaimer */}
            {!isLanding && (
              <div className="text-center mt-2">
                <span className="text-[10px] text-muted-foreground/30">Automated analysis. Verify critical executive decisions independently.</span>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
