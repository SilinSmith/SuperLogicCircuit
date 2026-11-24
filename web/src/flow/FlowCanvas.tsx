import { useCallback, useEffect } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type EdgeTypes,
  type NodeMouseHandler,
  type NodeTypes,
} from "@xyflow/react";
import type { GraphNode } from "../../contracts/node_graph";
import { BandwidthEdge } from "./edges/BandwidthEdge";
import { ModuleNode } from "./nodes/ModuleNode";
import { useElementSize } from "./useElementSize";
import type { FlowEdge, FlowNode } from "./types";

const nodeTypes = { module: ModuleNode } satisfies NodeTypes;
const edgeTypes = { bandwidth: BandwidthEdge } satisfies EdgeTypes;

export interface FlowCanvasProps {
  nodes: FlowNode[];
  edges: FlowEdge[];
  onSelectNode?: (node: GraphNode) => void;
}

export function FlowCanvas({ nodes, edges, onSelectNode }: FlowCanvasProps) {
  const [containerRef, size] = useElementSize<HTMLDivElement>();
  // 受控画布：拖拽只改本地坐标，不回写 node_graph.json（方案决策二）。
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState(nodes);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(edges);

  useEffect(() => {
    setFlowNodes(nodes);
    setFlowEdges(edges);
  }, [nodes, edges, setFlowNodes, setFlowEdges]);

  const handleNodeClick = useCallback<NodeMouseHandler<FlowNode>>(
    (_event, node) => {
      onSelectNode?.(node.data.graph);
    },
    [onSelectNode],
  );

  return (
    <div className="flow-canvas" ref={containerRef} data-testid="flow-canvas">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={handleNodeClick}
        fitView
        minZoom={0.15}
        maxZoom={2}
        onlyRenderVisibleElements={size.width > 0}
        proOptions={{ hideAttribution: false }}
      >
        <Background gap={24} size={1} />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable nodeStrokeWidth={2} />
      </ReactFlow>
    </div>
  );
}
