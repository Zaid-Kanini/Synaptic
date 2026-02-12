import { Brain, GitBranch, Search, Cpu } from 'lucide-react';

const steps = [
  { icon: Search, text: 'Vectorizing question...' },
  { icon: GitBranch, text: 'Traversing knowledge graph...' },
  { icon: Cpu, text: 'Loading source code...' },
  { icon: Brain, text: 'Synthesizing answer...' },
];

export default function ScanLoader() {
  return (
    <div className="flex flex-col gap-4 p-6 rounded-xl border border-cyan-500/20 bg-cyan-500/5">
      <div className="flex items-center gap-2 text-cyan-400 text-sm font-semibold tracking-wide uppercase">
        <div className="relative h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75 animate-ping" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
        </div>
        Scanning Repository...
      </div>

      <div className="space-y-3">
        {steps.map((step, i) => (
          <div
            key={i}
            className="flex items-center gap-3 animate-pulse-glow"
            style={{ animationDelay: `${i * 0.5}s` }}
          >
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-slate-800 border border-slate-700">
              <step.icon size={14} className="text-cyan-400" />
            </div>
            <div className="flex-1">
              <div className="h-2 rounded-full bg-slate-700 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 animate-pulse"
                  style={{
                    width: '60%',
                    animationDelay: `${i * 0.3}s`,
                  }}
                />
              </div>
              <span className="text-xs text-slate-500 mt-1">{step.text}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="relative h-1 w-full rounded-full bg-slate-800 overflow-hidden mt-2">
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent animate-scan" />
      </div>
    </div>
  );
}
