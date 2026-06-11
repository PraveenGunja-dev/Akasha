import React, { useState, useRef, useEffect } from 'react';
import { Bot, Send, Sparkles, Loader2, FastForward, Sliders, X, Maximize2 } from 'lucide-react';
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
    return (
      <button 
        onClick={() => setIsOpen(true)} 
        className="fixed bottom-6 right-6 px-4 h-14 bg-primary text-primary-foreground rounded-xl flex items-center justify-center gap-2 hover:bg-primary/90 transition-all hover:-translate-y-1 z-50 animate-in fade-in zoom-in group border border-border shadow-lg"
      >
        <Sparkles className="w-5 h-5 group-hover:hidden" />
        <Bot className="w-5 h-5 hidden group-hover:block" />
        <span className="font-semibold tracking-wide">Ask Akasha</span>
        <span className="absolute -top-1.5 -right-1.5 w-3 h-3 bg-destructive rounded-full animate-pulse border-2 border-background"></span>
      </button>
    );
  }

  return (
    <div className="w-[400px] h-full flex flex-col border-l border-border bg-card shrink-0 z-[40] animate-in slide-in-from-right-8 duration-300 fade-in">
      
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/20">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
            <Sliders className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-foreground tracking-wide">Scenario Simulation</h3>
            <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-semibold mt-0.5">AI Copilot</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onMaximize && (
            <button onClick={onMaximize} className="p-1.5 rounded-md hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors" title="Maximize">
              <Maximize2 className="w-4 h-4" />
            </button>
          )}
          <button onClick={() => setIsOpen(false)} className="p-1.5 rounded-md hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5 custom-scrollbar">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center px-2 animate-fade-up">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-6 border border-primary/20">
              <Sparkles className="w-8 h-8 text-primary" />
            </div>
            <h4 className="text-base font-semibold text-foreground mb-2">Run Portfolio Simulations</h4>
            <p className="text-xs text-muted-foreground leading-relaxed mb-6">
              Test 'What If' scenarios across P6 schedules, SAP procurement, and Transmission grid linkages.
            </p>
            <div className="flex flex-col gap-2 w-full">
              {[
                'What if SAP delivery for Khavda slips 2 weeks?', 
                'Simulate cost impact if Rajasthan P6 delays by 10%', 
                'Identify single points of failure in supply chain'
              ].map(q => (
                <button key={q} onClick={() => sendMessage(q)}
                  className="text-xs text-left px-4 py-3 rounded-xl border border-border bg-card hover:border-primary/40 transition-colors text-foreground/80 flex items-center gap-2 group">
                  <FastForward className="w-3.5 h-3.5 text-primary/50 group-hover:text-primary" />
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'} animate-fade-up`} style={{animationDelay: '50ms'}}>
            <div className={`max-w-[85%] px-4 py-3 rounded-2xl text-[13px] leading-relaxed border ${
              msg.type === 'user'
                ? 'bg-primary text-primary-foreground border-primary rounded-br-sm'
                : 'bg-card border-border text-foreground rounded-bl-sm'
            }`}>
              {msg.type === 'bot' ? (
                <div className="akasha-response prose prose-sm max-w-none dark:prose-invert">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              ) : msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start animate-fade-up">
            <div className="bg-card border border-border px-4 py-3 rounded-2xl rounded-bl-sm">
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 text-primary animate-spin" />
                <span className="text-xs font-medium text-muted-foreground">Running scenario...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-border bg-card">
        <div className="flex items-center gap-2 bg-background border border-border rounded-xl px-3 py-2 focus-within:border-primary/50 transition-colors">
          <input ref={inputRef} type="text" value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && sendMessage()}
            placeholder="Simulate a scenario..."
            className="flex-1 bg-transparent text-sm text-foreground placeholder-muted-foreground/50 py-1.5 focus:outline-none"
          />
          <button onClick={() => sendMessage()} disabled={!input.trim() || loading}
            className="p-2 rounded-lg text-white bg-primary hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm">
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
