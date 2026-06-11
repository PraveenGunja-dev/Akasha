import React, { useState, useRef, useEffect } from 'react';
import { Maximize2, Minimize2, Bot, ChevronRight, Activity, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface AkashaChatProps {
  isOpen: boolean;
  onClose: () => void;
  isFullScreen: boolean;
  onToggleFullScreen: () => void;
}

interface Message {
  id: number;
  type: 'user' | 'bot';
  content: string;
}

export default function AkashaChat({ isOpen, onClose, isFullScreen, onToggleFullScreen }: AkashaChatProps) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      type: 'bot',
      content: "Greetings. I am Akasha, your cross-platform project intelligence. I am continuously analyzing the latest SAP CAPEX drops, P6 baseline variances, and Site DPRs.\n\nWould you like to simulate the risk impact on the **Mundra** project timeline based on today's delay reports?"
    }
  ]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (textOverride?: string) => {
    const textToSend = textOverride || input;
    if (!textToSend.trim() || loading) return;
    
    const userMsg: Message = { id: Date.now(), type: 'user', content: textToSend.trim() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setSuggestions([]);
    setLoading(true);

    try {
      const response = await fetch('/akasha/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg.content, history: messages })
      });
      
      const data = await response.json();
      
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'bot',
        content: response.ok ? data.response : `Error: ${data.detail || 'Connection failed'}`
      }]);
      
      if (response.ok && data.suggestions) {
        setSuggestions(data.suggestions);
      }
    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'bot',
        content: 'System Error: Could not reach the AKASHA AI backend.'
      }]);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div 
      className={`absolute top-0 right-0 h-full bg-background/95 backdrop-blur-2xl border-l border-border transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] flex flex-col z-30 shadow-[-20px_0_50px_rgba(11,116,176,0.1)] ${
        !isOpen ? 'translate-x-full w-[30%]' : 
        isFullScreen ? 'w-full translate-x-0 border-l-0' : 'w-[30%] translate-x-0'
      }`}
    >
      {/* Futuristic Chat Header */}
      <div className="flex items-center justify-between p-5 border-b border-border bg-gradient-to-r from-transparent via-[#0B74B0]/5 to-transparent shrink-0 relative overflow-hidden">
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] opacity-10 mix-blend-overlay pointer-events-none"></div>
        <div className="flex items-center gap-4 relative z-10">
          <div className="relative">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#0B74B0] via-[#75479C] to-[#BD3861] flex items-center justify-center shadow-[0_0_20px_rgba(11,116,176,0.6)] animate-pulse">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div className="absolute -bottom-1 -right-1 w-3 h-3 bg-green-500 rounded-full border-2 border-black"></div>
          </div>
          <div>
            <h2 className="font-bold text-lg tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-foreground to-foreground/70" style={{ fontFamily: "Adani, sans-serif" }}>Akasha Intelligence</h2>
            <p className="text-xs text-[#0B74B0] font-mono tracking-widest uppercase">System Online • Ready</p>
          </div>
        </div>
        <div className="flex items-center gap-1 relative z-10">
          <button 
            onClick={onToggleFullScreen}
            className="p-2.5 hover:bg-white/10 rounded-xl transition-all text-foreground/50 hover:text-foreground hover:shadow-[0_0_15px_rgba(255,255,255,0.2)]"
          >
            {isFullScreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          <button 
            onClick={onClose}
            className="p-2.5 hover:bg-[#BD3861]/20 hover:text-[#BD3861] rounded-xl transition-all text-foreground/50"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Chat Body */}
      <div className="flex-1 p-6 overflow-y-auto flex flex-col gap-8 custom-scrollbar relative">
         <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/stardust.png')] opacity-[0.03] pointer-events-none"></div>
         
         {messages.map((msg) => (
           <div key={msg.id} className={`flex gap-4 relative z-10 max-w-[90%] ${msg.type === 'user' ? 'self-end flex-row-reverse' : ''}`}>
             <div className={`w-8 h-8 shrink-0 rounded-lg flex items-center justify-center mt-1 ${
               msg.type === 'bot' 
                ? 'bg-gradient-to-br from-[#0B74B0] to-[#75479C] shadow-[0_0_10px_rgba(11,116,176,0.3)]' 
                : 'bg-foreground/10 rounded-full border border-border'
             }`}>
               {msg.type === 'bot' ? <Bot className="w-4 h-4 text-white" /> : <span className="text-xs font-bold text-foreground">CEO</span>}
             </div>
             <div className={`rounded-2xl p-4 text-sm font-light leading-relaxed border text-foreground ${
               msg.type === 'bot'
                ? 'bg-gradient-to-b from-foreground/[0.04] to-transparent rounded-tl-sm border-border shadow-lg backdrop-blur-md'
                : 'bg-[#0B74B0]/20 rounded-tr-sm border-[#0B74B0]/30 shadow-[0_0_15px_rgba(11,116,176,0.1)]'
             }`}>
               {msg.type === 'bot' ? (
                 <div className="akasha-response prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed">
                   <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                 </div>
               ) : msg.content}
             </div>
           </div>
         ))}
         
         {loading && (
           <div className="flex gap-4 relative z-10 max-w-[90%]">
             <div className="w-8 h-8 shrink-0 rounded-lg bg-gradient-to-br from-[#0B74B0] to-[#75479C] flex items-center justify-center shadow-[0_0_10px_rgba(11,116,176,0.3)] mt-1">
               <Bot className="w-4 h-4 text-white" />
             </div>
             <div className="bg-gradient-to-b from-foreground/[0.04] to-transparent rounded-2xl rounded-tl-sm p-4 text-sm font-light leading-relaxed border border-border shadow-lg backdrop-blur-md flex items-center gap-2">
               <Loader2 className="w-4 h-4 text-[#0B74B0] animate-spin" />
               <span className="text-muted-foreground animate-pulse">Akasha is thinking...</span>
             </div>
           </div>
         )}
         <div ref={messagesEndRef} />
      </div>

      {/* Futuristic Chat Input */}
      <div className="p-5 border-t border-border bg-background/95 shrink-0 relative z-10">
        <div className="relative group">
          <div className="absolute -inset-0.5 bg-gradient-to-r from-[#0B74B0] via-[#75479C] to-[#BD3861] rounded-2xl blur opacity-30 group-hover:opacity-60 transition duration-500 pointer-events-none"></div>
          <div className="relative flex items-center bg-background border border-border rounded-2xl">
            <input 
              type="text" 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSend();
              }}
              placeholder="Initiate scenario analysis or query..." 
              className="w-full bg-transparent py-4 px-6 text-sm text-foreground placeholder-foreground/40 focus:outline-none font-mono"
            />
            <button 
              onClick={() => handleSend()}
              disabled={!input.trim() || loading}
              className="mr-2 p-2.5 bg-gradient-to-r from-[#0B74B0] to-[#75479C] hover:from-[#0c85c9] hover:to-[#8956b3] text-white rounded-xl transition-all shadow-[0_0_15px_rgba(11,116,176,0.4)] hover:shadow-[0_0_25px_rgba(11,116,176,0.6)] disabled:opacity-50"
            >
              <Activity className="w-5 h-5" />
            </button>
          </div>
        </div>
        
        {suggestions.length > 0 && (
          <div className="flex gap-2 mt-3 overflow-x-auto pb-1 custom-scrollbar hide-scrollbar">
            {suggestions.map((suggestion, idx) => (
              <button 
                key={idx} 
                onClick={() => handleSend(suggestion)}
                className="whitespace-nowrap px-3 py-1.5 rounded-lg border border-[#0B74B0]/30 bg-[#0B74B0]/10 hover:bg-[#0B74B0]/20 text-[11px] text-[#0B74B0] transition-colors font-medium shadow-sm"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
        
        <div className="flex gap-2 mt-3 justify-center">
           <span className="text-[10px] text-foreground/40 uppercase tracking-widest flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-green-500"></span> Live Data Synced</span>
        </div>
      </div>
    </div>
  );
}
