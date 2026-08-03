import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Paperclip, Mic, Plus, Database, Sparkles, Calendar,
  MessageSquare, BarChart3, ShieldAlert, TrendingUp,
  Clock, ArrowRight, Trash2, Search, Activity, History, X,
  Square, Loader2, Pencil, ThumbsUp, ThumbsDown, Download
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion, AnimatePresence } from 'framer-motion';
import ChatVisualizationGrid from './ChatVisualizationGrid';
import type { ChartVisualization } from './visualizationTypes';
import {
  ChatStreamError,
  formatChatError,
  getChatRequestId,
  getChatStreamError,
  readChatStream,
} from './chatStream';
import {
  cancelChatRun,
  createChatSession,
  deleteChatSession,
  getStoredChatMetadata,
  getChatSession,
  hasLegacyBrowserChats,
  listChatSessions,
  migrateLegacyBrowserChats,
  renameChatSession,
  setChartReportInclusion,
  sendChatMessage,
  submitChatFeedback,
  type StoredChatMessage,
  type ChatSessionSummary,
} from './chatApi';
import { mergeChatMetadata, type ChatMessageMetadata } from './chatContract';
import { useAuth } from '../../context/AuthContext';

interface SpeechRecognitionResultLike {
  [index: number]: { transcript: string };
}

interface SpeechRecognitionEventLike {
  results: ArrayLike<SpeechRecognitionResultLike>;
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  start: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

interface Message {
  id: number;
  type: 'user' | 'bot';
  content: string;
  timestamp: Date;
  imageData?: string; // Optional base64 image data attached to the message
  visualizations?: ChartVisualization[]; // Inline charts streamed from grounded backend tools
  metadata?: ChatMessageMetadata;
  suggestions?: string[];
  feedbackStatus?: 'none' | 'liked' | 'disliked';
  status?: 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
}

interface Thread {
  id: string;
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

function mapStoredMessages(messages: StoredChatMessage[]): Message[] {
  return messages.map(message => {
    const metadata = getStoredChatMetadata(message);
    return {
      id: message.id,
      type: message.role === 'assistant' ? 'bot' : 'user',
      content: message.content,
      timestamp: new Date(message.created_at),
      visualizations: message.visualizations as ChartVisualization[],
      metadata,
      suggestions: metadata.suggestions,
      feedbackStatus: message.feedback_status,
      status: message.status,
    };
  });
}

export default function AICopilot({ onMinimize }: AICopilotProps = {}) {
  const { user } = useAuth();
  const userId = user?.id;
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [typingStage, setTypingStage] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [isDeepAnalysis, setIsDeepAnalysis] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');

  const updateChartReportInclusion = async (
    messageId: number,
    visualizationIndex: number,
    value: 'auto' | 'include' | 'exclude',
  ) => {
    if (!activeThreadId || messageId <= 0) return;
    try {
      await setChartReportInclusion(activeThreadId, messageId, visualizationIndex, value);
      setMessages(current => current.map(message => message.id === messageId ? {
        ...message,
        visualizations: message.visualizations?.map((visualization, index) => index === visualizationIndex
          ? { ...visualization, report_inclusion: value }
          : visualization),
      } : message));
    } catch {
      setHistoryError('Unable to update this chart\'s report selection. Please try again.');
    }
  };
  
  // Voice and Image states
  const [isListening, setIsListening] = useState(false);
  const [imageFile, setImageFile] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [backendStatus, setBackendStatus] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeRunIdRef = useRef<string | null>(null);
  const migrationRef = useRef<{ userId: string; promise: Promise<void> } | null>(null);

  const greeting = useMemo(() => getGreeting(), []);

  const startListening = () => {
    const speechWindow = window as Window & {
      SpeechRecognition?: SpeechRecognitionConstructor;
      webkitSpeechRecognition?: SpeechRecognitionConstructor;
    };
    const SpeechRecognitionAPI = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) {
      alert('Your browser does not support Speech Recognition.');
      return;
    }
    const recognition = new SpeechRecognitionAPI();
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    
    recognition.onresult = (event: SpeechRecognitionEventLike) => {
      const transcript = Array.from(event.results)
        .map(result => result[0].transcript)
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

  const mapThread = (thread: ChatSessionSummary): Thread => ({
    id: thread.session_id,
    title: thread.title,
    preview: thread.preview,
    timestamp: new Date(thread.updated_at),
    messageCount: thread.message_count,
  });

  const refreshThreads = async () => {
    setIsHistoryLoading(true);
    setHistoryError('');
    try {
      const sessions = await listChatSessions();
      setThreads(sessions.map(mapThread));
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : 'Unable to load chat history.');
      throw error;
    } finally {
      setIsHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (!userId) {
      setThreads([]);
      return;
    }
    let active = true;
    setIsHistoryLoading(true);
    setHistoryError('');
    const initializeHistory = async () => {
      if (!migrationRef.current || migrationRef.current.userId !== userId) {
        const migrationKey = `akasha_chat_migration_${userId}`;
        const promise = (async () => {
          if (!localStorage.getItem(migrationKey) && hasLegacyBrowserChats()) {
            const shouldImport = window.confirm(
              'Legacy chats are stored in this browser without user isolation. Select OK to import them into your private account, or Cancel to remove them from this browser.'
            );
            await migrateLegacyBrowserChats(shouldImport);
            localStorage.setItem(migrationKey, 'complete');
          }
        })();
        migrationRef.current = { userId, promise };
      }
      await migrationRef.current.promise;
      const sessions = await listChatSessions();
      if (active) {
        setThreads(sessions.map(mapThread));
        setHistoryError('');
        setIsHistoryLoading(false);
      }
    };
    initializeHistory().catch(error => {
      console.error('Unable to initialize chat history:', error);
      if (active) {
        setHistoryError(error instanceof Error ? error.message : 'Unable to load chat history.');
        setIsHistoryLoading(false);
      }
    });
    return () => { active = false; };
  }, [userId]);

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

  const filteredThreads = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter(t => (t.title || '').toLowerCase().includes(q));
  }, [threads, searchQuery]);

  const startNewThread = () => {
    setActiveThreadId(null);
    setMessages([]);
    inputRef.current?.focus();
  };

  const loadThread = async (thread: Thread) => {
    try {
      const detail = await getChatSession(thread.id);
      setActiveThreadId(thread.id);
      setMessages(mapStoredMessages(detail.messages));
    } catch (error) {
      console.error('Unable to load chat:', error);
    }
  };

  const deleteThread = async (threadId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteChatSession(threadId);
      setThreads(prev => prev.filter(t => t.id !== threadId));
      if (activeThreadId === threadId) startNewThread();
    } catch (error) {
      console.error('Unable to delete chat:', error);
    }
  };

  const renameThread = async (thread: Thread, e: React.MouseEvent) => {
    e.stopPropagation();
    const title = window.prompt('Rename conversation', thread.title)?.trim();
    if (!title || title === thread.title) return;
    try {
      const updated = await renameChatSession(thread.id, title);
      setThreads(prev => prev.map(item => item.id === thread.id ? mapThread(updated) : item));
    } catch (error) {
      console.error('Unable to rename chat:', error);
    }
  };

  const submitFeedback = async (
    msgId: number,
    backendMessageId: number,
    type: 'thumbs_up' | 'thumbs_down',
  ) => {
    await submitChatFeedback({ messageId: backendMessageId, feedbackType: type });
    setMessages(prev => prev.map(m =>
      m.id === msgId ? { ...m, feedbackStatus: type === 'thumbs_up' ? 'liked' : 'disliked' } : m
    ));
  };

  const handleSend = async (overrideInput?: string) => {
    const text = overrideInput || input.trim();
    if ((!text && !imageFile) || isStreaming) return;
    let requestId: string | undefined;
    let streamedBotMessageId: number | undefined;
    let requestController: AbortController | undefined;

    let currentThreadId = activeThreadId;
    if (!currentThreadId) {
      try {
        const created = await createChatSession(text.substring(0, 100) || 'Image conversation');
        currentThreadId = created.session_id;
        setActiveThreadId(currentThreadId);
        setThreads(prev => [mapThread(created), ...prev.filter(thread => thread.id !== created.session_id)]);
      } catch (error) {
        setMessages(prev => [...prev, {
          id: Date.now(),
          type: 'bot',
          content: `System Error: ${error instanceof Error ? error.message : 'Unable to create a private chat session.'}`,
          timestamp: new Date(),
          feedbackStatus: 'none',
        }]);
        return;
      }
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

    try {
      const controller = new AbortController();
      requestController = controller;
      abortControllerRef.current = controller;
      setIsStreaming(true);

      const response = await sendChatMessage({
        message: text,
        sessionId: currentThreadId,
        isDeepAnalysis: isDeepAnalysis,
        imageData: currentImageData,
      }, controller.signal);
      requestId = getChatRequestId(response);

      let botContent = '';
      const botMsgId = Date.now() + 1;
      streamedBotMessageId = botMsgId;
      let botMessageAdded = false;
      let streamError: ChatStreamError | undefined;
      let hasVisualization = false;
      const ensureBotMessage = () => {
        if (botMessageAdded) return;
        botMessageAdded = true;
        setMessages(prev => [...prev, {
          id: botMsgId,
          type: 'bot',
          content: '',
          timestamp: new Date(),
          metadata: requestId ? { request_id: requestId } : undefined,
          feedbackStatus: 'none',
          status: 'running',
        }]);
      };
      
      for await (const data of readChatStream(response)) {
        requestId = data.request_id || requestId;
        if (data.type === 'start') {
          activeRunIdRef.current = data.run_id || null;
          setMessages(prev => prev.map(message => message.id === userMsg.id ? { ...message, id: data.user_message_id } : message));
        } else if (data.type === 'status') {
          setBackendStatus(data.status.replaceAll('_', ' '));
        } else if (data.type === 'token') {
          setIsTyping(false);
          ensureBotMessage();
          botContent += data.content;
          setMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, content: botContent } : m));
        } else if (data.type === 'visualization' && data.spec) {
          setIsTyping(false);
          ensureBotMessage();
          hasVisualization = true;
          // Inline chart from the agent — append to this message's chart list.
          setMessages(prev => prev.map(m => m.id === botMsgId ? {
            ...m,
            visualizations: [...(m.visualizations || []), {
              schema_version: data.schema_version,
              chart_type: data.chart_type,
              title: data.title,
              subtitle: data.subtitle,
              summary: data.summary,
              accessibility_description: data.accessibility_description,
              data_as_of: data.data_as_of,
              data_table: data.data_table,
              spec: data.spec,
            }]
          } : m));
        } else if (data.type === 'metadata') {
          setIsTyping(false);
          ensureBotMessage();
          setMessages(prev => prev.map(m => m.id === botMsgId ? {
            ...m,
            metadata: mergeChatMetadata(m.metadata, { ...data.metadata, request_id: requestId }),
            suggestions: data.metadata.suggestions ?? m.suggestions,
          } : m));
        } else if (data.type === 'error') {
          streamError = new ChatStreamError(getChatStreamError(data), data.request_id || requestId);
          ensureBotMessage();
          setMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, status: 'failed' } : m));
        } else if (data.type === 'cancelled') {
          ensureBotMessage();
          setMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, status: 'cancelled' } : m));
        } else if (data.type === 'done') {
          setIsTyping(false);
          ensureBotMessage();
          setMessages(prev => prev.map(m => m.id === botMsgId ? {
            ...m,
            id: data.message_id,
            metadata: mergeChatMetadata(m.metadata, { message_id: data.message_id, request_id: requestId }),
            status: data.status,
          } : m));
        }
      }

      if (streamError) throw streamError;
      if (!botContent.trim() && !hasVisualization) {
        throw new ChatStreamError('The chat stream ended without a response.', requestId);
      }
      await refreshThreads();
      
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        if (streamedBotMessageId !== undefined) {
          setMessages(prev => prev.map(message => message.id === streamedBotMessageId
            ? { ...message, status: 'cancelled' }
            : message));
        }
      } else {
        setIsTyping(false);
        const detail = formatChatError(err, requestId);
        setMessages(prev => [...prev, {
          id: Date.now() + 1,
          type: 'bot',
          content: `System Error: ${detail}`,
          timestamp: new Date(),
          feedbackStatus: 'none'
        }]);
      }
    } finally {
      if (abortControllerRef.current === requestController) {
        setIsStreaming(false);
        abortControllerRef.current = null;
        activeRunIdRef.current = null;
        setBackendStatus('');
      }
      refreshThreads().catch(error => console.error('Unable to refresh chat history:', error));
    }
  };

  const handleStop = async () => {
    const controller = abortControllerRef.current;
    if (!controller) return;
    setBackendStatus('cancelling');
    const runId = activeRunIdRef.current;
    if (runId) {
      await cancelChatRun(runId).catch(() => undefined);
    }
    controller.abort();
    setIsTyping(false);
  };

  const downloadReport = async (url: string, fallbackName: string) => {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`Download failed (${response.status})`);
      const blob = await response.blob();
      const disposition = response.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
      const filename = match ? decodeURIComponent(match[1].replace(/"/g, '')) : fallbackName;
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      console.error('Unable to download report:', error);
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
              onClick={() => {
                const opening = !sidebarOpen;
                setSidebarOpen(opening);
                if (opening) {
                  refreshThreads().catch(error => console.error('Unable to refresh chat history:', error));
                }
              }}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${sidebarOpen ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
              title="Chat history"
            >
              <History className="w-[18px] h-[18px]" />
            </button>

            {/* Floating history panel (dropdown, not a second sidebar) */}
            {sidebarOpen && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setSidebarOpen(false)} />
                <div className="absolute top-11 left-0 w-80 max-h-[calc(100vh-5rem)] bg-card border border-border shadow-xl rounded-2xl z-40 flex flex-col overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
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
                  <div className="flex-1 min-h-0 overflow-y-auto p-1.5">
                    <div className="px-2 py-1.5 text-[11px] font-semibold text-muted-foreground/60 uppercase tracking-wider">All chats ({filteredThreads.length})</div>
                    {historyError && threads.length > 0 && (
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          refreshThreads().catch(error => console.error('Unable to refresh chat history:', error));
                        }}
                        className="w-full px-2 py-1.5 mb-1 text-left text-[11px] text-red-500 hover:bg-muted rounded-lg"
                      >
                        Refresh failed. Showing saved results; select to retry.
                      </button>
                    )}
                    {isHistoryLoading && threads.length === 0 ? (
                      <div className="px-3 py-8 text-center text-[12px] text-muted-foreground/60">
                        Loading conversations...
                      </div>
                    ) : historyError && threads.length === 0 ? (
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          refreshThreads().catch(error => console.error('Unable to refresh chat history:', error));
                        }}
                        className="w-full px-3 py-6 text-center text-[12px] text-red-500 hover:bg-muted rounded-lg"
                      >
                        Unable to load conversations. Select to retry.
                      </button>
                    ) : filteredThreads.length > 0 ? (
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
                             onClick={(e) => renameThread(thread, e)}
                             className="p-1 rounded hover:bg-muted text-muted-foreground/60 hover:text-primary opacity-0 group-hover:opacity-100 transition-all"
                             title="Rename"
                           >
                             <Pencil className="w-3 h-3" />
                           </button>
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
                <div className="max-w-[80%] mx-auto w-full px-4 py-8 space-y-2">
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
                            {msg.status && msg.status !== 'completed' && (
                              <span className="text-[10px] capitalize text-muted-foreground">{msg.status}</span>
                            )}
                          </div>

                          <div className="akasha-response prose max-w-none prose-p:text-[14.5px] prose-p:leading-[1.7] prose-p:text-foreground prose-headings:text-foreground prose-headings:text-[16px] prose-strong:text-foreground prose-strong:font-semibold prose-code:text-primary prose-code:bg-primary/10 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-muted prose-pre:border prose-pre:border-border prose-a:text-primary prose-li:text-[14px] prose-li:text-foreground prose-table:text-[13px]">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                a: ({ href, children }) => {
                                  const isReport = Boolean(href?.match(/^\/akasha\/api\/reports\/artifacts\/[a-f0-9]+\/download$/));
                                  if (!isReport) return <a href={href}>{children}</a>;
                                  return (
                                    <button
                                      type="button"
                                      onClick={() => downloadReport(href!, String(children))}
                                      className="not-prose inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/15"
                                    >
                                      <Download className="h-3.5 w-3.5" />
                                      {children}
                                    </button>
                                  );
                                },
                              }}
                            >
                              {msg.content}
                            </ReactMarkdown>
                          </div>

                          {/* ── Enhanced Chart Cards ── */}
                          {msg.visualizations && msg.visualizations.length > 0 && (
                            <ChatVisualizationGrid
                              visualizations={msg.visualizations}
                              onReportInclusionChange={msg.status === 'completed'
                                ? (index, value) => updateChartReportInclusion(msg.id, index, value)
                                : undefined}
                            />
                          )}

                          {msg.metadata?.message_id && (
                            <div className="mt-2 flex items-center gap-1 text-[10px] text-muted-foreground/50">
                              <button
                                onClick={() => submitFeedback(msg.id, msg.metadata!.message_id!, 'thumbs_up')}
                                disabled={msg.feedbackStatus !== 'none'}
                                className={`p-1 rounded hover:bg-muted ${msg.feedbackStatus === 'liked' ? 'text-success bg-success/10' : ''}`}
                                title="Good response"
                              >
                                <ThumbsUp className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => submitFeedback(msg.id, msg.metadata!.message_id!, 'thumbs_down')}
                                disabled={msg.feedbackStatus !== 'none'}
                                className={`p-1 rounded hover:bg-muted ${msg.feedbackStatus === 'disliked' ? 'text-destructive bg-destructive/10' : ''}`}
                                title="Poor response"
                              >
                                <ThumbsDown className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          )}

                          {/* Suggested Follow-ups */}
                          {msg.id === messages[messages.length - 1].id && msg.suggestions && msg.suggestions.length > 0 && (
                            <div className="flex items-center gap-2 mt-4 flex-wrap">
                              {msg.suggestions.map((followup, i) => (
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
                        <span className="text-[11px] text-muted-foreground/60 font-mono animate-pulse">{backendStatus || currentStage.text}</span>
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
