import { useState, useCallback, useRef } from 'react';
import { queryRAG } from '../lib/api';
import { buildGraphData } from '../lib/graphUtils';

export function useSynaptic() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [highlightNodeId, setHighlightNodeId] = useState(null);
  const [repoPath, setRepoPath] = useState('D:\\Practice\\python\\Synapse\\test_repo');
  const graphRef = useRef(null);

  const sendQuestion = useCallback(async (question) => {
    const userMsg = { role: 'user', content: question, timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const data = await queryRAG({ question, repoPath });

      const assistantMsg = {
        role: 'assistant',
        content: data.answer,
        sourceNodes: data.source_nodes,
        relationships: data.relationships,
        metadata: data.metadata,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, assistantMsg]);

      const gd = buildGraphData(data.source_nodes, data.relationships);
      setGraphData(gd);
    } catch (err) {
      const errorMsg = {
        role: 'error',
        content: `Error: ${err.message}`,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  }, [repoPath]);

  const focusNode = useCallback((nodeId) => {
    setHighlightNodeId(nodeId);
    if (graphRef.current && nodeId) {
      const node = graphData.nodes.find((n) => n.id === nodeId);
      if (node) {
        graphRef.current.cameraPosition(
          { x: node.x + 80, y: node.y + 80, z: node.z + 80 },
          { x: node.x, y: node.y, z: node.z },
          1000
        );
      }
    }
  }, [graphData.nodes]);

  return {
    messages,
    loading,
    graphData,
    highlightNodeId,
    repoPath,
    setRepoPath,
    sendQuestion,
    focusNode,
    graphRef,
  };
}
