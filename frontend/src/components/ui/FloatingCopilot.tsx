import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Send, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { streamChat } from '../../features/chatbot/chatSseClient';
import { useAuth } from '../../context/AuthContext';

interface Message {
  id?: number;
  type: 'user' | 'bot';
  content: string;
}

export default function FloatingCopilot() {
  const { token } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>(['Which projects need attention?', 'Show me critical risks', 'Generate executive summary']);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  const sendMessage = async (overrideText?: string) => {
    const textToSend = overrideText || input;
    if (!textToSend.trim() || loading) return;
    
    const userMsg = textToSend.trim();
    setInput('');
    setSuggestions([]);
    setMessages(prev => [...prev, { type: 'user', content: userMsg }]);
    setLoading(true);

    try {
      let botContent = '';
      const botId = Date.now() + 1;
      setMessages(prev => [...prev, { id: botId, type: 'bot', content: '' }]);

      await streamChat(
        { message: userMsg, history: messages.slice(-10), client_version: 'akasha-floating-copilot-1' },
        {
          token,
          onEvent: (event) => {
            if (event.type === 'answer_delta' || event.type === 'token') {
              botContent += event.content || '';
            } else if (event.type === 'clarification_required') {
              botContent = event.question || 'I need one clarification before I can answer.';
            } else if (event.type === 'run_completed' || event.type === 'metadata') {
              setSuggestions(event.suggestions || []);
            } else if (event.type === 'error') {
              botContent = event.message || 'The chatbot run failed before completion.';
            }

            setMessages(prev => prev.map(msg => msg.id === botId ? { ...msg, content: botContent } : msg));
          },
        }
      );
    } catch (error: any) {
      setMessages(prev => [...prev, { type: 'bot', content: `Connection error. ${error?.message || 'Please try again.'}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Top Nav Button */}
      {!isOpen && (
        <button 
          onClick={() => setIsOpen(true)} 
          className="p-2 rounded-full hover:bg-accent text-muted-foreground hover:text-accent-foreground transition-colors"
          title="Ask Akasha"
        >
          <MessageSquare className="w-5 h-5" />
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
                <MessageSquare className="w-4 h-4 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-foreground">Ask Akasha</h3>
                <p className="text-[9px] text-muted-foreground/50 uppercase tracking-widest">Data Query Assistant</p>
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
                  <MessageSquare className="w-7 h-7 text-primary/50" />
                </div>
                <p className="text-sm text-muted-foreground/50 mb-4">Ask me about your projects, risks, or portfolio health.</p>
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

          {/* Suggestions */}
          {suggestions.length > 0 && (
            <div className="px-4 py-2 border-t border-white/[0.06] flex gap-2 overflow-x-auto hide-scrollbar">
              {suggestions.map((q, idx) => (
                <button key={idx} onClick={() => sendMessage(q)}
                  className="whitespace-nowrap text-[10px] text-primary/60 bg-primary/[0.06] border border-primary/10 px-3 py-1.5 rounded-lg hover:bg-primary/10 hover:text-primary transition-colors">
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="px-4 py-3 border-t border-white/[0.06]">
            <div className="flex items-center gap-2 bg-white/[0.03] border border-white/[0.06] rounded-xl px-3 py-1 focus-within:border-primary/30 transition-colors">
              <input ref={inputRef} type="text" value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendMessage()}
                placeholder="Ask AKASHA..."
                className="flex-1 bg-transparent text-sm text-foreground/90 placeholder-muted-foreground/30 py-2 focus:outline-none"
              />
              <button onClick={() => sendMessage()} disabled={!input.trim() || loading}
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
