import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import { User, Brain, AlertCircle, Clock, Zap, FileCode } from 'lucide-react';

function FileRefLink({ children, onFileClick }) {
  if (typeof children !== 'string') return children;

  const fileRefRegex = /(`?)([a-zA-Z0-9_/\\.-]+\.[a-zA-Z]+):(\d+)(?:-(\d+))?\1/g;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = fileRefRegex.exec(children)) !== null) {
    if (match.index > lastIndex) {
      parts.push(children.slice(lastIndex, match.index));
    }
    const filepath = match[2];
    const line = parseInt(match[3], 10);
    parts.push(
      <button
        key={match.index}
        onClick={() => onFileClick(filepath, line)}
        className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 cursor-pointer transition-colors"
        title={`Focus on ${filepath}:${line}`}
      >
        {match[0].replace(/`/g, '')}
      </button>
    );
    lastIndex = match.index + match[0].length;
  }

  if (parts.length === 0) return children;
  if (lastIndex < children.length) parts.push(children.slice(lastIndex));
  return <>{parts}</>;
}

export default function ChatMessage({ message, onFileClick }) {
  const isUser = message.role === 'user';
  const isError = message.role === 'error';

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
          isUser
            ? 'bg-blue-500/20 text-blue-400'
            : isError
            ? 'bg-red-500/20 text-red-400'
            : 'bg-cyan-500/20 text-cyan-400'
        }`}
      >
        {isUser ? <User size={16} /> : isError ? <AlertCircle size={16} /> : <Brain size={16} />}
      </div>

      <div
        className={`flex-1 min-w-0 ${
          isUser ? 'text-right' : ''
        }`}
      >
        {isUser ? (
          <div className="inline-block px-4 py-2.5 rounded-2xl rounded-tr-sm bg-blue-600/20 border border-blue-500/20 text-sm text-slate-200">
            {message.content}
          </div>
        ) : isError ? (
          <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-300">
            {message.content}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="markdown-body text-sm text-slate-300 leading-relaxed">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight, rehypeRaw]}
                components={{
                  p: ({ children }) => (
                    <p className="mb-3">
                      {Array.isArray(children)
                        ? children.map((child, i) => (
                            <FileRefLink key={i} onFileClick={onFileClick}>
                              {child}
                            </FileRefLink>
                          ))
                        : <FileRefLink onFileClick={onFileClick}>{children}</FileRefLink>
                      }
                    </p>
                  ),
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>

            {message.metadata && (
              <div className="flex flex-wrap gap-3 pt-2 border-t border-slate-800">
                <MetaBadge icon={Clock} label="Retrieval" value={`${message.metadata.retrieval_time_ms}ms`} />
                <MetaBadge icon={Zap} label="Synthesis" value={`${message.metadata.synthesis_time_ms}ms`} />
                <MetaBadge icon={FileCode} label="Sources" value={`${message.metadata.entry_points + message.metadata.neighbours} nodes`} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MetaBadge({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-slate-500">
      <Icon size={12} />
      <span>{label}:</span>
      <span className="text-slate-400 font-medium">{value}</span>
    </div>
  );
}
