import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Send, Sparkles, Loader2, X, MoreVertical, Search, Lightbulb, Plus, Settings2, PictureInPicture, Square } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  ChatStreamError,
  formatChatError,
  getChatRequestId,
  getChatStreamError,
  readChatStream,
  type ChatStreamMetadata,
} from '../../features/chatbot/chatStream';
import {
  cancelChatRun,
  createChatSession,
  getStoredChatMetadata,
  getChatSession,
  listChatSessions,
  sendChatMessage,
  type ChatSessionSummary,
} from '../../features/chatbot/chatApi';
import { mergeChatMetadata } from '../../features/chatbot/chatContract';

interface Message {
  id?: number;
  type: 'user' | 'bot';
  content: string;
  timestamp?: Date | string;
  metadata?: ChatStreamMetadata;
  suggestions?: string[];
  status?: 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
}

interface ScenarioSimulationPanelProps {
  isOpen: boolean;
  setIsOpen: (val: boolean) => void;
  onMaximize?: () => void;
  projectId?: string;
}

export default function ScenarioSimulationPanel({ isOpen, setIsOpen, onMaximize, projectId }: ScenarioSimulationPanelProps) {
  const { user } = useAuth();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [threads, setThreads] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const sendingRef = useRef(false);
  const nextLocalIdRef = useRef(-1);
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (showHistory) listChatSessions().then(setThreads).catch(error => console.error('Unable to list chats:', error));
  }, [showHistory]);

  const loadThread = async (sessionId: string) => {
    if (sendingRef.current) return;
    try {
      const session = await getChatSession(sessionId);
      setActiveSessionId(sessionId);
      setMessages(session.messages.map(message => {
        const metadata = getStoredChatMetadata(message);
        return {
          id: message.id,
          type: message.role === 'assistant' ? 'bot' : 'user',
          content: message.content,
          timestamp: message.created_at,
          metadata,
          suggestions: metadata.suggestions,
          status: message.status,
        };
      }));
      setShowHistory(false);
    } catch (error) {
      console.error('Unable to load chat:', error);
    }
  };

  const startNewChat = () => {
    if (sendingRef.current) return;
    setActiveSessionId(null);
    setMessages([]);
    setInput('');
  };

  useEffect(() => {
    if (isOpen) {
      listChatSessions().then(setThreads).catch(error => console.error('Unable to list chats:', error));
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [isOpen]);

  // Also auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (overrideText?: string) => {
    const textToSend = overrideText || input.trim();
    if (!textToSend || sendingRef.current) return;
    sendingRef.current = true;

    setInput('');
    
    const userMsg: Message = {
      id: nextLocalIdRef.current--,
      type: 'user',
      content: textToSend,
      timestamp: new Date()
    };
    
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    
    let currentSessionId = activeSessionId;
    if (!currentSessionId) {
      try {
        const created = await createChatSession(textToSend.substring(0, 100));
        currentSessionId = created.session_id;
        setActiveSessionId(currentSessionId);
        setThreads(prev => [created, ...prev.filter(thread => thread.session_id !== created.session_id)]);
      } catch (error) {
        setMessages([...newMessages, { type: 'bot', content: error instanceof Error ? error.message : 'Unable to create chat.' }]);
        sendingRef.current = false;
        return;
      }
    }

    setLoading(true);

    try {
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const res = await sendChatMessage({
        message: textToSend,
        projectId,
        sessionId: currentSessionId,
      }, controller.signal);
      let requestId = getChatRequestId(res);

      const botMsgId = (userMsg.id ?? 0) + 1;
      let botContent = '';
      let botMetadata: ChatStreamMetadata | undefined;
      let botSuggestions: string[] | undefined;
      let hasVisualization = false;
      let streamError: ChatStreamError | undefined;
      let botStatus: Message['status'] = 'running';

      const updateBotMessage = () => {
        const botMsg: Message = {
          id: botMsgId,
          type: 'bot',
          content: botContent,
          timestamp: new Date(),
          metadata: botMetadata,
          suggestions: botSuggestions,
          status: botStatus,
        };
        const updatedMessages = [...newMessages, botMsg];
        setMessages(updatedMessages);
        return updatedMessages;
      };

      try {
        for await (const event of readChatStream(res)) {
          requestId = event.request_id || requestId;
          if (requestId) {
            botMetadata = { ...botMetadata, request_id: requestId };
          }
          if (event.type === 'start') {
            activeRunIdRef.current = event.run_id || null;
          } else if (event.type === 'status') {
            setBackendStatus(event.status.replaceAll('_', ' '));
          } else if (event.type === 'token') {
            botContent += event.content;
            updateBotMessage();
          } else if (event.type === 'metadata') {
            botMetadata = mergeChatMetadata(botMetadata, { ...event.metadata, request_id: requestId });
            botSuggestions = event.metadata.suggestions ?? botSuggestions;
            updateBotMessage();
          } else if (event.type === 'visualization') {
            // The compact panel intentionally omits charts; the full copilot renders the same event.
            hasVisualization = true;
          } else if (event.type === 'error') {
            streamError = new ChatStreamError(getChatStreamError(event), event.request_id || requestId);
            botStatus = 'failed';
            updateBotMessage();
          } else if (event.type === 'cancelled') {
            botStatus = 'cancelled';
            updateBotMessage();
          } else if (event.type === 'done') {
            botMetadata = mergeChatMetadata(botMetadata, { message_id: event.message_id, request_id: requestId });
            botStatus = event.status;
            updateBotMessage();
          }
        }

        if (streamError) throw streamError;
        if (!botContent.trim() && hasVisualization) {
          botContent = 'A visualization was generated. Open the full chat to view it.';
        } else if (!botContent.trim()) {
          throw new ChatStreamError('The chat stream ended without a response.', requestId);
        }

        const finalMessages = updateBotMessage();
        setMessages(finalMessages);
        setThreads(await listChatSessions());
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          botStatus = 'cancelled';
        } else {
          const detail = formatChatError(error, requestId, 'Unknown chat stream error.');
          botContent = botContent ? `${botContent}\n\nError: ${detail}` : `Error: ${detail}`;
          botSuggestions = undefined;
          botStatus = 'failed';
        }
        const finalMessages = updateBotMessage();
        setMessages(finalMessages);
      }
    } catch (error) {
      const detail = formatChatError(error, undefined, 'Unknown connection error.');
      const errorMsg: Message = {
        id: nextLocalIdRef.current--,
        type: 'bot',
        content: `Error: ${detail}`,
        timestamp: new Date()
      };
      const finalMessages = [...newMessages, errorMsg];
      setMessages(finalMessages);
    } finally {
      setLoading(false);
      sendingRef.current = false;
      abortControllerRef.current = null;
      activeRunIdRef.current = null;
      setBackendStatus('');
      listChatSessions().then(setThreads).catch(error => console.error('Unable to refresh chats:', error));
    }
  };

  const cancelActiveRun = async () => {
    const controller = abortControllerRef.current;
    if (!controller) return;
    setBackendStatus('cancelling');
    const runId = activeRunIdRef.current;
    if (runId) {
      await cancelChatRun(runId).catch(() => undefined);
    }
    controller.abort();
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed top-[88px] right-6 w-[420px] h-[calc(100vh-110px)] flex flex-col bg-card border border-border z-[60] shadow-2xl rounded-2xl animate-in slide-in-from-right-8 duration-300 fade-in overflow-hidden">
      
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/20 bg-muted">
        <button onClick={startNewChat} className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-muted text-sm font-medium transition-colors text-foreground">
          <Plus className="w-4 h-4" /> New Chat
        </button>
        <div className="flex items-center gap-1 relative">
          <button onClick={() => setShowHistory(!showHistory)} className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="History">
            <MoreVertical className="w-5 h-5" />
          </button>
          
          {showHistory && (
             <div className="absolute top-full right-16 mt-1 w-64 bg-card border border-border rounded-xl shadow-xl py-2 z-50">
               <div className="px-4 py-2 text-xs font-bold text-muted-foreground uppercase tracking-wider border-b border-border mb-1">Recent History</div>
               <div className="max-h-48 overflow-y-auto custom-scrollbar">
                 {threads.length === 0 ? (
                   <div className="px-4 py-3 text-sm text-muted-foreground italic">No recent chats</div>
                 ) : (
                    threads.map(t => (
                      <button key={t.session_id} onClick={() => loadThread(t.session_id)} className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors truncate">
                       {t.title}
                     </button>
                   ))
                 )}
               </div>
             </div>
          )}

          {onMaximize && (
            <button onClick={onMaximize} className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="Detach / Maximize">
              <PictureInPicture className="w-5 h-5" />
            </button>
          )}
          <button onClick={() => { if (loading) void cancelActiveRun(); setIsOpen(false); }} className="p-2 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="Close">
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6 custom-scrollbar overscroll-contain" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
        {messages.length === 0 && (
          <div className="flex flex-col justify-end h-full px-2 pb-6 animate-fade-up">
            <h2 className="text-[28px] font-medium bg-gradient-to-r from-[#4285f4] via-[#ea4335] to-[#fbbc04] bg-clip-text text-transparent mb-1">Hello, {user?.display_name?.split(' ')[0] || 'there'}</h2>
            <h3 className="text-[28px] font-medium text-foreground/70 mb-10">How can I help you today?</h3>
            
            <div className="flex flex-col gap-3 w-full">
              {[
                { icon: <Sparkles className="w-4 h-4 text-[#4285f4]" />, text: 'What can you do?' },
                { icon: <Search className="w-4 h-4 text-[#ea4335]" />, text: 'What kinds of questions can I ask?' },
                { icon: <Lightbulb className="w-4 h-4 text-[#fbbc04]" />, text: 'Help me think through a problem' }
              ].map((q, i) => (
                <button key={i} onClick={() => sendMessage(q.text)}
                  className="text-[13px] text-left px-4 py-3.5 rounded-2xl border border-border/30 bg-muted hover:bg-muted transition-colors text-foreground/90 flex items-center gap-3 w-max max-w-full group">
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
                ? 'bg-muted text-foreground rounded-br-sm'
                : 'bg-transparent text-foreground'
            }`}>
              {msg.type === 'bot' && (
                <div className="flex items-center gap-3 mb-2">
                  <Sparkles className="w-4 h-4 text-[#4285f4]" />
                  <span className="text-xs font-semibold text-foreground/70">AKASHA AI</span>
                  {msg.status && msg.status !== 'completed' && (
                    <span className="text-[10px] capitalize text-muted-foreground">{msg.status}</span>
                  )}
                </div>
              )}
              {msg.type === 'bot' ? (
                <>
                  <div className="akasha-response prose prose-sm max-w-none dark:prose-invert ml-7">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                  {idx === messages.length - 1 && msg.suggestions && msg.suggestions.length > 0 && (
                    <div className="ml-7 mt-3 flex flex-wrap gap-2">
                      {msg.suggestions.map(suggestion => (
                        <button
                          key={suggestion}
                          onClick={() => sendMessage(suggestion)}
                          disabled={loading}
                          className="px-3 py-1.5 rounded-xl border border-border/30 bg-muted text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}
                </>
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
                <span className="text-sm capitalize text-muted-foreground">{backendStatus || 'Thinking...'}</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 pt-0">
        <div className="flex flex-col bg-muted rounded-[24px] p-1.5 border border-border focus-within:bg-muted focus-within:border-border transition-all">
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
            <button onClick={() => loading ? void cancelActiveRun() : void sendMessage()} disabled={!input.trim() && !loading}
              className="p-2.5 rounded-full text-foreground hover:bg-muted transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
              {loading ? <Square className="w-4 h-4" /> : <Send className="w-4 h-4" />}
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
