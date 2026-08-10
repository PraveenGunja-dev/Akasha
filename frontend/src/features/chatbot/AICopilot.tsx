import React, { useState, useEffect, useRef, useMemo } from 'react';
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
import ReactECharts from 'echarts-for-react';
import { motion, AnimatePresence } from 'framer-motion';

interface ChartViz {
  chart_type?: string;
  title?: string;
  spec: any; // ECharts `option` object, built server-side from real DB data
}

interface Message {
  id: number;
  type: 'user' | 'bot';
  content: string;
  timestamp: Date;
  sources?: string[];
  imageData?: string; // Optional base64 image data attached to the message
  visualizations?: ChartViz[]; // Inline charts streamed from the agent's render_chart tool
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
}

/** Returns a time-of-day greeting string. */
function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good Morning';
  if (hour < 17) return 'Good Afternoon';
  return 'Good Evening';
}

export default function AICopilot({ onMinimize }: AICopilotProps = {}) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [typingStage, setTypingStage] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeThreadId, setActiveThreadId] = useState<number | null>(null);
  const [suggestedFollowups, setSuggestedFollowups] = useState<string[]>([]);
  const [isDeepAnalysis, setIsDeepAnalysis] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [exportMenuOpenId, setExportMenuOpenId] = useState<number | null>(null);
  
  // Voice and Image states
  const [isListening, setIsListening] = useState(false);
  const [imageFile, setImageFile] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const greeting = useMemo(() => getGreeting(), []);

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

  const handleExportReport = async (content: string, format: 'docx' | 'pdf', metadata?: any, visualizations?: ChartViz[]) => {
    try {
      const images: string[] = [];

      // 1. Check pre-cached Base64 PNG screenshots from onChartReady
      if (visualizations && visualizations.length > 0) {
        visualizations.forEach((v: any) => {
          if (v && v._b64Image && v._b64Image.length > 500) {
            images.push(v._b64Image);
          }
        });
      }

      // 2. Secondary fallback: Query live canvas elements in the DOM at export time
      if (images.length === 0) {
        const canvasElements = document.querySelectorAll('.copilot-chart-card canvas');
        canvasElements.forEach((canvas) => {
          try {
            const dataUrl = (canvas as HTMLCanvasElement).toDataURL('image/png');
            if (dataUrl && dataUrl.startsWith('data:image') && dataUrl.length > 500) {
              images.push(dataUrl);
            }
          } catch (e) {
            console.warn('Chart canvas image capture warning:', e);
          }
        });
      }

      const response = await fetch(`/akasha/api/export/${format}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Adani Renewables Executive Intelligence Report',
          content: content,
          metadata: metadata,
          images: images,
          visualizations: visualizations
        })
      });

      if (!response.ok) throw new Error('Export failed');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Akasha_Report_${new Date().toISOString().slice(0, 10)}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error(`Error downloading ${format}:`, err);
      alert(`Could not generate ${format.toUpperCase()} report.`);
    }
  };

  const isLanding = messages.length === 0;

  const filteredThreads = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter(t => (t.title || '').toLowerCase().includes(q));
  }, [threads, searchQuery]);

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

      const response = await fetch('/akasha/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: text, 
          history: messages,
          sessionId: currentThreadId.toString(),
          isDeepAnalysis: isDeepAnalysis,
          imageData: currentImageData,
          stream: true
        }),
        signal: controller.signal
      });

      if (!response.ok) {
        throw new Error('Connection failed');
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
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

      if (reader) {
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          // Append to a buffer and only process COMPLETE lines — a streamed SSE frame
          // can be split across two reads, so keep the trailing partial line for next time.
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            const trimmed = line.trimStart();
            if (!trimmed.startsWith('data: ')) continue;
            try {
              const data = JSON.parse(trimmed.slice(6));
              if (data.type === 'token') {
                botContent += data.content;
                setMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, content: botContent } : m));
              } else if (data.type === 'visualization' && data.spec) {
                // Inline chart from the agent — append to this message's chart list.
                setMessages(prev => prev.map(m => m.id === botMsgId ? {
                  ...m,
                  visualizations: [...(m.visualizations || []), { chart_type: data.chart_type, title: data.title, spec: data.spec }]
                } : m));
              } else if (data.type === 'metadata') {
                setSuggestedFollowups(data.suggestions || []);
                setMessages(prev => prev.map(m => m.id === botMsgId ? {
                  ...m,
                  metadata: data.metadata,
                  sources: data.metadata?.sources?.tables || []
                } : m));
              }
            } catch (e) {
              // Incomplete/non-JSON frame — skip
            }
          }
        }
      }
      
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

  // ──────────────────────────────────────────────
  // Shared Input Bar (used in both landing & conversation states)
  // ──────────────────────────────────────────────
  const renderInputBar = (inLanding: boolean) => (
    <div className="w-full">
      <div className="rounded-[1.5rem] border border-border bg-card shadow-[0_2px_12px_rgba(15,23,42,0.06)] focus-within:border-border focus-within:shadow-[0_4px_20px_rgba(15,23,42,0.10)] transition-all duration-200">
        {/* Image Preview */}
        {imageFile && (
          <div className="px-4 pt-3">
            <div className="relative inline-block">
              <img src={imageFile} alt="Attached" className="h-16 w-16 object-cover rounded-lg border border-border" />
              <button
                onClick={() => setImageFile(null)}
                className="absolute -top-2 -right-2 w-5 h-5 bg-card border border-border rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground shadow-sm"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          </div>
        )}
        {/* Textarea */}
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
          placeholder={inLanding ? 'Ask anything about your portfolio…' : 'Reply to Akasha…'}
          className="w-full bg-transparent text-[15px] text-foreground placeholder-muted-foreground/60 outline-none resize-none min-h-[26px] max-h-[200px] leading-relaxed px-4 pt-3.5"
          rows={1}
        />

        {/* Toolbar Row */}
        <div className="flex items-center justify-between px-3 pb-2.5 pt-1.5">
          <div className="flex items-center gap-0.5">
            <input type="file" ref={fileInputRef} hidden accept="image/*" onChange={handleImageChange} />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              title="Attach image"
            >
              <Paperclip className="w-[18px] h-[18px]" />
            </button>
            <button
              onClick={startListening}
              className={`p-2 rounded-lg transition-colors ${isListening ? 'bg-red-50 text-red-500' : 'hover:bg-muted text-muted-foreground hover:text-foreground'}`}
              title="Voice input"
            >
              <Mic className="w-[18px] h-[18px]" />
            </button>
            <button
              onClick={() => setIsDeepAnalysis(!isDeepAnalysis)}
              className={`ml-1 pl-2 pr-2.5 py-1.5 rounded-full transition-colors flex items-center gap-1.5 text-[12px] font-medium border ${
                isDeepAnalysis
                  ? 'bg-primary/10 text-primary border-primary/25'
                  : 'bg-card text-muted-foreground border-border hover:bg-muted'
              }`}
              title="Deep Analysis Agent Mode — grounds answers in live P6/SAP/TC tools"
            >
              <Activity className="w-3.5 h-3.5" />
              <span>{isDeepAnalysis ? 'Deep Analysis' : 'Deep Analysis'}</span>
            </button>
          </div>

          {isStreaming ? (
            <button
              onClick={handleStop}
              className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 bg-foreground text-background hover:opacity-90 transition-all"
              title="Stop generating"
            >
              <Square className="w-3 h-3 fill-current" />
            </button>
          ) : (
            <button
              onClick={() => handleSend()}
              disabled={(!input.trim() && !imageFile) || isTyping}
              className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-all duration-200 ${
                (input.trim() || imageFile) && !isTyping
                  ? 'bg-primary text-primary-foreground hover:opacity-90'
                  : 'bg-muted text-muted-foreground/40 cursor-not-allowed'
              }`}
              title="Send"
            >
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
      {inLanding && (
        <p className="text-center text-[11px] text-muted-foreground/60 mt-3">
          Akasha can make mistakes. Verify critical executive decisions independently.
        </p>
      )}
    </div>
  );

  return (
    <div className="flex h-full w-full overflow-hidden bg-background text-foreground">

      {/* ── Chat pane fills the full area (the app already provides the nav sidebar) ── */}
      <div className="flex-1 flex flex-col relative min-w-0 bg-background">

        {/* Header */}
        <div className="h-14 flex items-center justify-between px-4 border-b border-border bg-background/90 backdrop-blur-sm z-30 shrink-0">
          <div className="flex items-center gap-2 relative">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${sidebarOpen ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
              title="Chat history"
            >
              <History className="w-[18px] h-[18px]" />
            </button>

            {/* Floating history panel (dropdown, not a second sidebar) */}
            {sidebarOpen && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setSidebarOpen(false)} />
                <div className="absolute top-11 left-0 w-80 bg-card border border-border shadow-xl rounded-2xl z-40 flex flex-col overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
                  <div className="p-2.5 border-b border-border">
                    <button
                      onClick={() => { startNewThread(); setSidebarOpen(false); }}
                      className="flex items-center gap-2 w-full px-3 py-2 rounded-xl bg-primary/5 border border-primary/15 text-[13px] font-medium text-primary hover:bg-primary/10 transition-colors"
                    >
                      <Plus className="w-4 h-4" /> New chat
                    </button>
                    <div className="flex items-center gap-2 px-2.5 py-1.5 mt-2 rounded-lg bg-muted border border-border">
                      <Search className="w-3.5 h-3.5 text-muted-foreground/60 shrink-0" />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search chats…"
                        className="bg-transparent text-[12.5px] text-foreground placeholder-muted-foreground/60 outline-none flex-1 min-w-0"
                      />
                    </div>
                  </div>
                  <div className="max-h-80 overflow-y-auto scrollbar-hide p-1.5">
                    <div className="px-2 py-1.5 text-[11px] font-semibold text-muted-foreground/60 uppercase tracking-wider">Recents</div>
                    {filteredThreads.length > 0 ? (
                      filteredThreads.map(thread => (
                        <div
                          key={thread.id}
                          onClick={() => { loadThread(thread); setSidebarOpen(false); }}
                          className={`group flex items-center gap-2.5 px-2.5 py-2 rounded-lg cursor-pointer transition-colors ${
                            activeThreadId === thread.id ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted'
                          }`}
                        >
                          <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-50" />
                          <span className="text-[13px] truncate flex-1">{thread.title}</span>
                          <button
                            onClick={(e) => deleteThread(thread.id, e)}
                            className="p-1 rounded hover:bg-muted text-muted-foreground/60 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all"
                            title="Delete"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      ))
                    ) : (
                      <div className="px-3 py-8 text-center text-[12px] text-muted-foreground/60">
                        {searchQuery ? 'No matches' : 'No conversations yet'}
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
            <span className="text-[13.5px] font-semibold text-foreground">Ask Akasha</span>
            <span className="flex items-center gap-1.5 ml-1 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold tracking-wide uppercase">Online</span>
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={startNewThread}
              className="px-3 py-1.5 rounded-lg text-[12.5px] font-medium text-muted-foreground hover:bg-muted transition-colors flex items-center gap-1.5"
              title="New chat"
            >
              <Plus className="w-3.5 h-3.5" /> New
            </button>
            {onMinimize && (
              <button
                onClick={onMinimize}
                className="w-8 h-8 rounded-lg hover:bg-muted flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
                title="Minimize"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* ══════════════════════════════════════════ */}
        {/* ── Landing View (No Messages) ──          */}
        {/* ══════════════════════════════════════════ */}
        <AnimatePresence mode="wait">
          {isLanding ? (
            <motion.div
              key="landing"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, y: -30, scale: 0.98 }}
              transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
              className="flex-1 flex flex-col items-center justify-center px-6 z-10"
            >
              {/* Greeting */}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15, duration: 0.5 }}
                className="text-center mb-8"
              >
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center shadow-md mx-auto mb-5">
                  <Sparkles className="w-6 h-6 text-white" />
                </div>
                <h2 className="text-[2rem] font-semibold text-foreground tracking-tight">
                  {greeting}
                </h2>
                <p className="text-[1.05rem] text-muted-foreground mt-1">
                  How can I help with your portfolio today?
                </p>
              </motion.div>

              {/* Centered Input */}
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.28, duration: 0.5 }}
                className="w-full max-w-[720px]"
              >
                {renderInputBar(true)}
              </motion.div>

              {/* Quick-action suggestion chips */}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4, duration: 0.5 }}
                className="flex flex-wrap justify-center gap-2 max-w-[720px] mt-5"
              >
                {insightCards.map((card, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(card.prompt)}
                    className="group flex items-center gap-2 px-3.5 py-2 rounded-full bg-card border border-border text-[12.5px] font-medium text-muted-foreground hover:border-border hover:bg-muted transition-all shadow-sm"
                  >
                    <card.icon className="w-3.5 h-3.5" style={{ color: card.color }} />
                    <span>{card.title}</span>
                  </button>
                ))}
              </motion.div>
            </motion.div>

          ) : (
            /* ══════════════════════════════════════════ */
            /* ── Conversation View ──                    */
            /* ══════════════════════════════════════════ */
            <motion.div
              key="conversation"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.35 }}
              className="flex-1 flex flex-col min-h-0"
            >
              {/* Messages area */}
              <div className="flex-1 overflow-y-auto scrollbar-hide z-10" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
                <div className="max-w-[95%] lg:max-w-[90%] mx-auto w-full px-4 py-8 space-y-2">
                  {messages.map((msg, idx) => (
                    <motion.div
                      key={msg.id}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, delay: idx === messages.length - 1 ? 0.05 : 0 }}
                    >
                      {msg.type === 'user' ? (
                        /* User Message */
                        <div className="flex justify-end py-2">
                          <div className="max-w-[85%] bg-muted text-foreground px-4 py-2.5 rounded-2xl rounded-br-md">
                            {msg.imageData && (
                              <img src={msg.imageData} alt="Attached" className="h-32 w-auto rounded-lg mb-2 border border-border" />
                            )}
                            <p className="text-[14.5px] leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                          </div>
                        </div>
                      ) : (
                        /* Bot Response */
                        <div className="py-4">
                          <div className="flex items-center gap-2 mb-2.5">
                            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center">
                              <Sparkles className="w-3 h-3 text-white" />
                            </div>
                            <span className="text-[12px] font-semibold text-muted-foreground">Akasha</span>
                          </div>

                          <div className="akasha-response prose max-w-none prose-p:text-[14.5px] prose-p:leading-[1.7] prose-p:text-foreground prose-headings:text-foreground prose-headings:text-[16px] prose-strong:text-foreground prose-strong:font-semibold prose-code:text-primary prose-code:bg-primary/10 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-a:text-primary prose-li:text-[14px] prose-li:text-foreground prose-table:text-[13px]">
                            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                              {typeof msg.content === 'string' ? msg.content : (msg.content ? String(msg.content) : '')}
                            </ReactMarkdown>
                          </div>

                          {/* ── Enhanced Chart Cards (2 per row side-by-side) ── */}
                          {msg.visualizations && msg.visualizations.length > 0 && (
                            <div className={`grid gap-4 mt-4 w-full ${msg.visualizations.length > 1 ? 'grid-cols-1 md:grid-cols-2 max-w-[1100px]' : 'grid-cols-1 max-w-[650px]'}`}>
                              {msg.visualizations.map((viz, i) => {
                                const isDonut = viz.chart_type === 'activity_status' || viz.chart_type === 'transmission_status' || viz.spec?.series?.[0]?.type === 'pie';
                                return (
                                  <motion.div
                                    key={i}
                                    initial={{ opacity: 0, y: 16 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ duration: 0.45, delay: i * 0.1 }}
                                    className="copilot-chart-card w-full"
                                  >
                                    {/* Chart Header with title + type badge */}
                                    <div className="chart-header">
                                      <BarChart3 className="w-4 h-4 text-primary/60 shrink-0" />
                                      <span className="chart-title truncate">
                                        {viz.title || 'Visualization'}
                                      </span>
                                      {viz.chart_type && (
                                        <span className="chart-type-badge ml-auto shrink-0">
                                          {viz.chart_type}
                                        </span>
                                      )}
                                    </div>
                                    {/* Chart Body */}
                                    <div className="chart-body">
                                      <ReactECharts
                                        option={viz.spec}
                                        style={{ height: isDonut ? 280 : 310, width: '100%' }}
                                        notMerge={true}
                                        opts={{ renderer: 'canvas' }}
                                        onChartReady={(echartsInstance) => {
                                          const captureFinishedChart = () => {
                                            try {
                                              const b64 = echartsInstance.getDataURL({
                                                type: 'png',
                                                pixelRatio: 3,
                                                backgroundColor: '#ffffff'
                                              });
                                              if (b64 && b64.length > 500) {
                                                (viz as any)._b64Image = b64;
                                              }
                                            } catch (e) {
                                              console.warn('onChartReady getDataURL failed:', e);
                                            }
                                          };

                                          // Listen for ECharts 'finished' event (fires when rendering & expansion animations complete 100%)
                                          try {
                                            echartsInstance.off('finished');
                                            echartsInstance.on('finished', captureFinishedChart);
                                          } catch (e) {
                                            // fallback if off/on not supported
                                          }

                                          // Safety fallback: capture after 1600ms to guarantee animation finish
                                          setTimeout(captureFinishedChart, 1600);
                                        }}
                                      />
                                    </div>
                                  </motion.div>
                                );
                              })}
                            </div>
                          )}

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
                                      className={`p-1 rounded hover:bg-muted transition-colors ${msg.feedbackStatus === 'liked' ? 'text-success bg-success/10' : ''}`}
                                      title="Good response"
                                    >
                                      <ThumbsUp className="w-3.5 h-3.5" />
                                    </button>
                                    <button 
                                      onClick={() => submitFeedback(msg.id, msg.metadata!.message_id!, 'thumbs_down')}
                                      disabled={msg.feedbackStatus !== 'none'}
                                      className={`p-1 rounded hover:bg-muted transition-colors ${msg.feedbackStatus === 'disliked' ? 'text-destructive bg-destructive/10' : ''}`}
                                      title="Poor response"
                                    >
                                      <ThumbsDown className="w-3.5 h-3.5" />
                                    </button>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Export Report Dropdown Button */}
                            <div className="relative mt-2.5 pt-2 border-t border-border/30 text-[11px] inline-block">
                              <button
                                onClick={() => setExportMenuOpenId(exportMenuOpenId === msg.id ? null : msg.id)}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-muted/70 hover:bg-muted text-foreground text-[11px] font-medium transition-all border border-border/70 shadow-2xs hover:border-primary/40 group"
                                title="Export report into Microsoft Word or PDF document"
                              >
                                <FileText className="w-3.5 h-3.5 text-primary group-hover:scale-105 transition-transform" />
                                <span>Export Report</span>
                                <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform duration-200 ${exportMenuOpenId === msg.id ? 'rotate-180' : ''}`} />
                              </button>

                              {/* Upward Popover Menu (Guaranteed fully visible above input box) */}
                              <AnimatePresence>
                                {exportMenuOpenId === msg.id && (
                                  <>
                                    <div className="fixed inset-0 z-40" onClick={() => setExportMenuOpenId(null)} />
                                    <motion.div
                                      initial={{ opacity: 0, y: 8, scale: 0.96 }}
                                      animate={{ opacity: 1, y: 0, scale: 1 }}
                                      exit={{ opacity: 0, y: 6, scale: 0.96 }}
                                      transition={{ duration: 0.16, ease: "easeOut" }}
                                      className="absolute left-0 bottom-full mb-2 w-52 bg-card border border-border shadow-2xl rounded-xl z-50 p-1.5 backdrop-blur-2xl"
                                    >
                                      <div className="px-2.5 py-1 text-[10px] font-semibold text-muted-foreground/70 uppercase tracking-wider border-b border-border/40 mb-1">
                                        Select Export Format
                                      </div>
                                      <button
                                        onClick={() => {
                                          handleExportReport(msg.content, 'docx', msg.metadata, msg.visualizations);
                                          setExportMenuOpenId(null);
                                        }}
                                        className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-lg hover:bg-primary/10 text-foreground text-[12px] font-medium transition-colors group/item text-left"
                                      >
                                        <div className="w-6 h-6 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold text-[10px] shrink-0">W</div>
                                        <span>Microsoft Word (.docx)</span>
                                      </button>
                                      <button
                                        onClick={() => {
                                          handleExportReport(msg.content, 'pdf', msg.metadata, msg.visualizations);
                                          setExportMenuOpenId(null);
                                        }}
                                        className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-lg hover:bg-red-500/10 text-foreground text-[12px] font-medium transition-colors group/item text-left"
                                      >
                                        <div className="w-6 h-6 rounded bg-red-500/10 text-red-600 dark:text-red-400 flex items-center justify-center font-bold text-[10px] shrink-0">PDF</div>
                                        <span>Adobe PDF (.pdf)</span>
                                      </button>
                                    </motion.div>
                                  </>
                                )}
                              </AnimatePresence>
                            </div>
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
                    </motion.div>
                  ))}

                  {/* Typing Indicator — Inline Subtle */}
                  {isTyping && (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="py-3"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-primary to-violet-500 flex items-center justify-center">
                          <Loader2 className="w-3 h-3 text-primary-foreground animate-spin" />
                        </div>
                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">AKASHA</span>
                        <span className="text-[11px] text-muted-foreground/60 font-mono animate-pulse">{currentStage.text}</span>
                      </div>
                    </motion.div>
                  )}

                  <div ref={messagesEndRef} />
                </div>
              </div>

              {/* ── Bottom Input Bar (conversation mode) ── */}
              <div className="px-4 pb-4 pt-2 z-20 relative bg-gradient-to-t from-background via-background to-transparent">
                <div className="max-w-[80%] mx-auto w-full">
                  {renderInputBar(false)}
                  <p className="text-center text-[11px] text-muted-foreground/60 mt-2">
                    Akasha can make mistakes. Verify critical executive decisions independently.
                  </p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </div>
  );
}
