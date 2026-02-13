import { useCallback, useRef, useState, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Network } from 'lucide-react';

export default function GraphPane({ graphData, highlightNodeId, onNodeClick, graphRef }) {
  const containerRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 600 });
  const [hoveredNode, setHoveredNode] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const handleNodeHover = useCallback((node, prevNode) => {
    setHoveredNode(node || null);
    document.body.style.cursor = node ? 'pointer' : 'default';
  }, []);

  const handleNodeClick = useCallback((node) => {
    if (node && onNodeClick) {
      onNodeClick(node.id);
    }
  }, [onNodeClick]);

  const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
    const isHighlighted = node.id === highlightNodeId;
    const radius = isHighlighted ? node.size * 1.8 : node.size * 1.2;
    const label = node.name;
    const fontSize = Math.max(10 / globalScale, 2);

    // Glow effect for highlighted node
    if (isHighlighted) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius + 5, 0, 2 * Math.PI);
      ctx.fillStyle = `${node.color}30`;
      ctx.fill();
    }

    // Node circle with solid fill and border
    ctx.beginPath();
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
    ctx.fillStyle = node.color;
    ctx.fill();
    ctx.strokeStyle = isHighlighted ? '#1e293b' : '#475569';
    ctx.lineWidth = isHighlighted ? 2.5 / globalScale : 1 / globalScale;
    ctx.stroke();

    // Label
    if (globalScale > 0.8) {
      ctx.font = `600 ${fontSize}px Inter, system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = '#1e293b';
      ctx.fillText(label, node.x, node.y + radius + 3);
    }
  }, [highlightNodeId]);

  const nodePointerAreaPaint = useCallback((node, color, ctx) => {
    const radius = node.size * 1.5;
    ctx.beginPath();
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
  }, []);

  const isEmpty = graphData.nodes.length === 0;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <Network size={16} className="text-indigo-500" />
          <h2 className="text-sm font-semibold text-slate-700 tracking-wide">CODEBASE MAP</h2>
        </div>
        {!isEmpty && (
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span>{graphData.nodes.length} nodes</span>
            <span>{graphData.links.length} edges</span>
          </div>
        )}
      </div>

      {/* Graph */}
      <div ref={containerRef} className="flex-1 relative bg-white">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-8">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-50 to-purple-50 flex items-center justify-center mb-4 border border-indigo-100">
              <Network size={28} className="text-indigo-500" />
            </div>
            <h3 className="text-sm font-semibold text-slate-600 mb-2">Knowledge Graph</h3>
            <p className="text-xs text-slate-400 max-w-[200px]">
              Ask a question to visualize the code entities and their relationships.
            </p>
          </div>
        ) : (
          <>
            <ForceGraph2D
              ref={graphRef}
              width={dimensions.width}
              height={dimensions.height}
              graphData={graphData}
              nodeCanvasObject={nodeCanvasObject}
              nodePointerAreaPaint={nodePointerAreaPaint}
              onNodeHover={handleNodeHover}
              onNodeClick={handleNodeClick}
              linkColor={() => '#94a3b8'}
              linkWidth={1.5}
              linkDirectionalArrowLength={5}
              linkDirectionalArrowRelPos={1}
              linkDirectionalArrowColor={() => '#64748b'}
              backgroundColor="#ffffff"
              enableNodeDrag={true}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.3}
              cooldownTicks={100}
              minZoom={0.5}
              maxZoom={8}
            />

            {/* Tooltip */}
            {hoveredNode && (
              <div
                className="absolute z-50 pointer-events-none px-3 py-2 rounded-lg bg-white border border-slate-200 shadow-lg"
                style={{
                  left: tooltipPos.x + 15,
                  top: tooltipPos.y - 10,
                }}
                onMouseMove={(e) => setTooltipPos({ x: e.clientX, y: e.clientY })}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: hoveredNode.color }}
                  />
                  <span className="text-sm font-medium text-slate-700">{hoveredNode.name}</span>
                  <span className="text-xs text-slate-400 capitalize">({hoveredNode.type})</span>
                </div>
                {hoveredNode.filepath && (
                  <div className="text-xs text-slate-500 font-mono">
                    {hoveredNode.filepath}
                    {hoveredNode.startLine && `:${hoveredNode.startLine}-${hoveredNode.endLine}`}
                  </div>
                )}
                {hoveredNode.score != null && (
                  <div className="text-xs text-blue-600 mt-0.5">
                    similarity: {hoveredNode.score.toFixed(3)}
                  </div>
                )}
              </div>
            )}

            {/* Legend */}
            <div className="absolute bottom-4 left-4 flex flex-col gap-1.5 px-3 py-2 rounded-lg bg-white/90 border border-slate-200 shadow-sm">
              <LegendItem color="#0ea5e9" label="Function" />
              <LegendItem color="#8b5cf6" label="Class" />
              <LegendItem color="#10b981" label="File" />
              <LegendItem color="#64748b" label="Other" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function LegendItem({ color, label }) {
  return (
    <div className="flex items-center gap-2 text-xs text-slate-600">
      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </div>
  );
}
