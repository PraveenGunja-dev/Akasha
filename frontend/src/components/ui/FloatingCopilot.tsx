import React, { useState, useRef, useEffect } from 'react';
import { Bot, X, Send, Sparkles, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Message {
  type: 'user' | 'bot';
  content: string;
}

export default function FloatingCopilot() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { type: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const res = await fetch('/akasha/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg, history: messages.slice(-10) })
      });
      const data = await res.json();
      setMessages(prev => [...prev, { type: 'bot', content: data.response }]);
    } catch {
      setMessages(prev => [...prev, { type: 'bot', content: 'Connection error. Please try again.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Floating Button */}
      {!isOpen && (
        <button onClick={() => setIsOpen(true)} className="floating-copilot-btn" title="Ask AKASHA AI">
          <Bot className="w-6 h-6 text-white" />
        </button>
      )}

      {/* Chat Panel */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-50 w-[420px] h-[560px] rounded-2xl overflow-hidden flex flex-col"
          style={{
            background: 'linear-gradient(180deg, rgba(13,19,33,0.98) 0%, rgba(6,10,20,0.99) 100%)',
            border: '1px solid rgba(59,130,246,0.15)',
            boxShadow: '0 24px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(59,130,246,0.08), 0 0 60px rgba(59,130,246,0.05)',
          }}>
          
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.06]"
            style={{ background: 'linear-gradient(90deg, rgba(59,130,246,0.06), rgba(139,92,246,0.04))' }}>
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary/30 to-purple-600/30 flex items-center justify-center border border-primary/20">
                <Sparkles className="w-4 h-4 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-foreground">AKASHA Copilot</h3>
                <p className="text-[9px] text-muted-foreground/50 uppercase tracking-widest">AI Intelligence Assistant</p>
              </div>
            </div>
            <button onClick={() => setIsOpen(false)}
              className="p-1.5 rounded-lg hover:bg-white/[0.06] text-muted-foreground/50 hover:text-foreground transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 custom-scrollbar">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary/10 to-purple-600/10 flex items-center justify-center mb-4 border border-primary/10">
                  <Bot className="w-7 h-7 text-primary/50" />
                </div>
                <p className="text-sm text-muted-foreground/50 mb-4">Ask me about your projects, risks, or portfolio health.</p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {['Which projects need attention?', 'Show me critical risks', 'Generate executive summary'].map(q => (
                    <button key={q} onClick={() => { setInput(q); }}
                      className="text-[10px] text-primary/60 bg-primary/[0.06] border border-primary/10 px-3 py-1.5 rounded-lg hover:bg-primary/10 transition-colors">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                  msg.type === 'user'
                    ? 'bg-primary/15 text-foreground/90 rounded-br-md border border-primary/10'
                    : 'bg-white/[0.03] text-foreground/80 rounded-bl-md border border-white/[0.04]'
                }`}>
                  {msg.type === 'bot' ? (
                    <div className="akasha-response prose prose-invert prose-sm max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  ) : msg.content}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-white/[0.03] border border-white/[0.04] px-4 py-3 rounded-2xl rounded-bl-md">
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />
                    <span className="text-xs text-muted-foreground/50 animate-pulse">Analyzing...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="px-4 py-3 border-t border-white/[0.06]">
            <div className="flex items-center gap-2 bg-white/[0.03] border border-white/[0.06] rounded-xl px-3 py-1 focus-within:border-primary/30 transition-colors">
              <input ref={inputRef} type="text" value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendMessage()}
                placeholder="Ask AKASHA..."
                className="flex-1 bg-transparent text-sm text-foreground/90 placeholder-muted-foreground/30 py-2 focus:outline-none"
              />
              <button onClick={sendMessage} disabled={!input.trim() || loading}
                className="p-2 rounded-lg text-primary/60 hover:text-primary hover:bg-primary/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
