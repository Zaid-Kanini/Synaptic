import { useCallback } from 'react';
import ChatPane from './components/ChatPane';
import GraphPane from './components/GraphPane';
import { useSynaptic } from './hooks/useSynaptic';
import { findNodeByFilepath } from './lib/graphUtils';

export default function App() {
  const {
    messages,
    loading,
    graphData,
    highlightNodeId,
    repoPath,
    setRepoPath,
    sendQuestion,
    focusNode,
    graphRef,
  } = useSynaptic();

  const handleFileClick = useCallback(
    (filepath, line) => {
      const node = findNodeByFilepath(graphData.nodes, filepath, line);
      if (node) focusNode(node.id);
    },
    [graphData.nodes, focusNode]
  );

  return (
    <div className="h-screen w-screen flex bg-[#0a0a0f]">
      {/* Left: Chat */}
      <div className="w-1/2 min-w-[400px] border-r border-slate-800 flex flex-col">
        <ChatPane
          messages={messages}
          loading={loading}
          repoPath={repoPath}
          setRepoPath={setRepoPath}
          onSend={sendQuestion}
          onFileClick={handleFileClick}
        />
      </div>

      {/* Right: 3D Graph */}
      <div className="flex-1 flex flex-col">
        <GraphPane
          graphData={graphData}
          highlightNodeId={highlightNodeId}
          onNodeClick={focusNode}
          graphRef={graphRef}
        />
      </div>
    </div>
  );
}
