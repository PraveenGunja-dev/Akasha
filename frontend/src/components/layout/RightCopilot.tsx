import React, { useState } from 'react';
import { Bot, Send, Mic, Sparkles, X, ChevronRight, AlertCircle, TrendingUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function RightCopilot() {
  const [isOpen, setIsOpen] = useState(true);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: 1,
      type: 'bot',
      content: "Good morning. I've analyzed the overnight sync from P6 and SAP. How can I assist?"
    }
  ]);

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const userMsg = { id: Date.now(), type: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    try {
      const response = await fetch('/akasha/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input, history: messages })
      });
      
      const data = await response.json();
      
      setIsTyping(false);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'bot',
        content: response.ok ? data.response : `Error: ${data.detail || 'Failed'}`
      }]);
    } catch (error) {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'bot',
        content: 'System Error: Could not reach the AKASHA AI backend.'
      }]);
    }
  };

  if (!isOpen) {
    return (
      <button 
        onClick={() => setIsOpen(true)}
        className="absolute right-0 top-1/2 -translate-y-1/2 bg-[#1F2937] border-l border-t border-b border-[#3B82F6]/30 p-2 rounded-l-xl text-[#3B82F6] hover:bg-[#3B82F6]/10 transition-colors shadow-[-4px_0_15px_rgba(0,0,0,0.5)] z-50"
      >
        <Bot className="w-6 h-6" />
      </button>
    );
  }

  return (
    <aside className="w-[320px] h-full flex flex-col bg-[#0B1020] border-l border-[#1F2937] flex-shrink-0 z-20 shadow-[-4px_0_24px_rgba(0,0,0,0.5)]">
      {/* Header */}
      <div className="p-4 border-b border-[#1F2937] flex items-center justify-between bg-[#111827]">
        <div className="flex items-center gap-2">
           <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#3B82F6] to-[#75479C] p-[1px]">
              <div className="w-full h-full bg-[#0B1020] rounded-lg flex items-center justify-center">
                 <Bot className="w-4 h-4 text-white" />
              </div>
           </div>
           <div>
             <h2 className="text-sm font-semibold text-white flex items-center gap-1">
               Akasha Copilot <Sparkles className="w-3 h-3 text-[#F59E0B]" />
             </h2>
             <p className="text-[10px] text-gray-400">Enterprise AI Assistant</p>
           </div>
        </div>
        <button onClick={() => setIsOpen(false)} className="p-1 hover:bg-[#1F2937] rounded text-gray-400 hover:text-white transition-colors">
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar flex flex-col">
         <div className="text-center my-2">
            <span className="text-[10px] text-gray-500 uppercase tracking-widest font-semibold border border-gray-800 rounded-full px-3 py-1">Today</span>
         </div>

         {messages.map((msg) => (
           <div key={msg.id} className={`flex gap-3 ${msg.type === 'user' ? 'flex-row-reverse' : ''}`}>
             <div className={`w-6 h-6 rounded flex items-center justify-center shrink-0 mt-1 ${msg.type === 'user' ? 'bg-[#374151]' : 'bg-[#3B82F6]/20'}`}>
                {msg.type === 'user' ? <span className="text-[10px] font-bold text-white">CEO</span> : <Bot className="w-3 h-3 text-[#3B82F6]" />}
             </div>
             <div className={`flex-1 space-y-2 ${msg.type === 'user' ? 'text-right' : ''}`}>
                <div className={`text-xs p-3 rounded-2xl border shadow-sm leading-relaxed prose prose-invert max-w-full ${
                  msg.type === 'user' 
                    ? 'bg-[#3B82F6] text-white rounded-tr-none border-[#3B82F6]' 
                    : 'bg-[#1F2937] text-gray-200 rounded-tl-none border-gray-800'
                }`}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
             </div>
           </div>
         ))}
         
         {isTyping && (
           <div className="flex gap-3">
             <div className="w-6 h-6 rounded bg-[#3B82F6]/20 flex items-center justify-center shrink-0 mt-1">
                <Bot className="w-3 h-3 text-[#3B82F6]" />
             </div>
             <div className="flex-1">
                <p className="text-xs p-3 rounded-2xl rounded-tl-none bg-[#1F2937] text-gray-400 border border-gray-800 flex items-center gap-2 w-fit">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3B82F6] animate-bounce"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3B82F6] animate-bounce delay-100"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3B82F6] animate-bounce delay-200"></span>
                </p>
             </div>
           </div>
         )}
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-[#1F2937] bg-[#111827]">
        <div className="relative flex items-center">
           <textarea 
             rows={1}
             value={input}
             onChange={(e) => setInput(e.target.value)}
             onKeyDown={(e) => {
               if (e.key === 'Enter' && !e.shiftKey) {
                 e.preventDefault();
                 handleSend();
               }
             }}
             placeholder="Ask Copilot..."
             className="w-full bg-[#1F2937] border border-gray-700 focus:border-[#3B82F6] rounded-xl py-3 pl-4 pr-20 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-[#3B82F6] transition-all resize-none overflow-hidden"
             style={{ minHeight: '44px' }}
           />
           <div className="absolute right-2 flex items-center gap-1">
              <button className="p-1.5 text-gray-400 hover:text-[#3B82F6] transition-colors rounded-lg">
                <Mic className="w-4 h-4" />
              </button>
              <button onClick={handleSend} disabled={!input.trim()} className="p-1.5 bg-[#3B82F6] text-white rounded-lg shadow-[0_0_10px_rgba(59,130,246,0.3)] hover:bg-blue-600 transition-colors disabled:opacity-50">
                <Send className="w-4 h-4" />
              </button>
           </div>
        </div>
        <div className="flex gap-2 mt-2 px-1 overflow-x-auto custom-scrollbar whitespace-nowrap hide-scrollbar">
           <span onClick={() => setInput("Why is Project A delayed?")} className="text-[10px] text-gray-500 cursor-pointer hover:text-gray-300">"Why is Project A delayed?"</span>
           <span onClick={() => setInput("Show procurement bottlenecks")} className="text-[10px] text-gray-500 cursor-pointer hover:text-gray-300">"Show procurement bottlenecks"</span>
        </div>
      </div>
    </aside>
  );
}
