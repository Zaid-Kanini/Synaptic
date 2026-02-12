import { useState, useRef, useEffect } from 'react';
import { Send, Settings, FolderOpen } from 'lucide-react';
import ChatMessage from './ChatMessage';
import ScanLoader from './ScanLoader';

export default function ChatPane({ messages, loading, repoPath, setRepoPath, onSend, onFileClick }) {
  const [input, setInput] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    onSend(q);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-cyan-500 shadow-[0_0_8px_rgba(34,211,238,0.5)]" />
          <h2 className="text-sm font-semibold text-slate-200 tracking-wide">SYNAPTIC CHAT</h2>
        </div>
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
        >
          <Settings size={16} />
        </button>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="px-5 py-3 border-b border-slate-800 bg-slate-900/50">
          <label className="flex items-center gap-2 text-xs text-slate-400">
            <FolderOpen size={14} />
            Repository Path
          </label>
          <input
            type="text"
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            className="mt-1.5 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-slate-200 focus:outline-none focus:border-cyan-500/50 transition-colors"
          />
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 flex items-center justify-center mb-4 border border-cyan-500/10">
              <span className="text-3xl">🧠</span>
            </div>
            <h3 className="text-lg font-semibold text-slate-200 mb-2">Synaptic</h3>
            <p className="text-sm text-slate-500 max-w-xs">
              Ask any question about your codebase. I'll search the knowledge graph and explain the architecture.
            </p>
            <div className="flex flex-wrap gap-2 mt-6 justify-center">
              {[
                'What does utils.py do?',
                'How is user data validated?',
                'Explain the analytics tracking flow',
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => { setInput(q); }}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-400 hover:text-cyan-400 hover:border-cyan-500/30 transition-colors cursor-pointer"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} onFileClick={onFileClick} />
        ))}

        {loading && <ScanLoader />}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="px-5 py-4 border-t border-slate-800">
        <div className="flex items-center gap-2 bg-slate-800/50 border border-slate-700 rounded-xl px-4 py-2 focus-within:border-cyan-500/40 transition-colors">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your codebase..."
            disabled={loading}
            className="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-500 focus:outline-none disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="p-2 rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            <Send size={16} />
          </button>
        </div>
      </form>
    </div>
  );
}
