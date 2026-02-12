import { useCallback, useRef, useState, useEffect } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import { Network, Info } from 'lucide-react';
import * as THREE from 'three';

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

  const nodeThreeObject = useCallback((node) => {
    const isHighlighted = node.id === highlightNodeId;
    const geometry = new THREE.SphereGeometry(
      isHighlighted ? node.size * 1.5 : node.size,
      16,
      16
    );
    const material = new THREE.MeshPhongMaterial({
      color: node.color,
      emissive: node.color,
      emissiveIntensity: isHighlighted ? 0.8 : 0.3,
      transparent: true,
      opacity: isHighlighted ? 1 : 0.85,
    });
    return new THREE.Mesh(geometry, material);
  }, [highlightNodeId]);

  const linkColor = useCallback(() => 'rgba(100, 116, 139, 0.3)', []);
  const linkWidth = useCallback(() => 0.5, []);

  const isEmpty = graphData.nodes.length === 0;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Network size={16} className="text-purple-400" />
          <h2 className="text-sm font-semibold text-slate-200 tracking-wide">CODEBASE MAP</h2>
        </div>
        {!isEmpty && (
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span>{graphData.nodes.length} nodes</span>
            <span>{graphData.links.length} edges</span>
          </div>
        )}
      </div>

      {/* Graph */}
      <div ref={containerRef} className="flex-1 relative bg-[#060610]">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-8">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center mb-4 border border-purple-500/10">
              <Network size={28} className="text-purple-400" />
            </div>
            <h3 className="text-sm font-semibold text-slate-300 mb-2">Knowledge Graph</h3>
            <p className="text-xs text-slate-500 max-w-[200px]">
              Ask a question to visualize the code entities and their relationships.
            </p>
          </div>
        ) : (
          <>
            <ForceGraph3D
              ref={graphRef}
              width={dimensions.width}
              height={dimensions.height}
              graphData={graphData}
              nodeThreeObject={nodeThreeObject}
              nodeLabel=""
              onNodeHover={handleNodeHover}
              onNodeClick={handleNodeClick}
              linkColor={linkColor}
              linkWidth={linkWidth}
              linkDirectionalArrowLength={3}
              linkDirectionalArrowRelPos={1}
              linkDirectionalArrowColor={() => 'rgba(148, 163, 184, 0.4)'}
              backgroundColor="#060610"
              showNavInfo={false}
              enableNodeDrag={true}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.3}
            />

            {/* Tooltip */}
            {hoveredNode && (
              <div
                className="absolute z-50 pointer-events-none px-3 py-2 rounded-lg bg-slate-900/95 border border-slate-700 shadow-xl backdrop-blur-sm"
                style={{
                  left: dimensions.width / 2,
                  top: 60,
                  transform: 'translateX(-50%)',
                }}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: hoveredNode.color }}
                  />
                  <span className="text-sm font-medium text-slate-200">{hoveredNode.name}</span>
                  <span className="text-xs text-slate-500 capitalize">({hoveredNode.type})</span>
                </div>
                {hoveredNode.filepath && (
                  <div className="text-xs text-slate-400 font-mono">
                    {hoveredNode.filepath}
                    {hoveredNode.startLine && `:${hoveredNode.startLine}-${hoveredNode.endLine}`}
                  </div>
                )}
                {hoveredNode.score != null && (
                  <div className="text-xs text-cyan-400 mt-0.5">
                    similarity: {hoveredNode.score.toFixed(3)}
                  </div>
                )}
              </div>
            )}

            {/* Legend */}
            <div className="absolute bottom-4 left-4 flex flex-col gap-1.5 px-3 py-2 rounded-lg bg-slate-900/80 border border-slate-800 backdrop-blur-sm">
              <LegendItem color="#38bdf8" label="Function" />
              <LegendItem color="#a78bfa" label="Class" />
              <LegendItem color="#34d399" label="File" />
              <LegendItem color="#94a3b8" label="Other" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function LegendItem({ color, label }) {
  return (
    <div className="flex items-center gap-2 text-xs text-slate-400">
      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </div>
  );
}
