import { useMemo } from "react";
import type { GraphEdge, GraphNode, NodeGraph } from "../../contracts/node_graph";
import { FlowCanvas } from "../flow/FlowCanvas";
import { layoutNodes } from "../flow/layout";
import { NODE_WIDTH, nodeHeight, type FlowEdge, type FlowNode } from "../flow/types";
import { applyLayout, type LayoutFile } from "../lib/layout";
import type { TraceSummary } from "../lib/stats";

const DATAFLOW_EDGE_KINDS: GraphEdge["kind"][] = ["data", "handshake", "bundle", "param"];

/** 数据流视图：只保留承载数据的模块节点与数据边；时钟树/跨域桥在 P4 的独立视图中呈现。 */
export function dataflowSubset(graph: NodeGraph): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes = graph.nodes.filter(
    (node) => node.type === "module_node" || node.type === "stats_node" || node.type.startsWith("p_"),
  );
  const visible = new Set(nodes.map((node) => node.id));
  const edges = graph.edges.filter(
    (edge) =>
      visible.has(edge.source) &&
      visible.has(edge.target) &&
      DATAFLOW_EDGE_KINDS.includes(edge.kind),
  );
  return { nodes, edges };
}

export function buildFlowElements(
  graph: NodeGraph,
  layout?: LayoutFile,
  summary?: TraceSummary | null,
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const { nodes, edges } = dataflowSubset(graph);
  const metrics = new Map((summary?.edges ?? []).map((edge) => [edge.id, edge]));
  const positions = layoutNodes(nodes, edges, "LR");
  const flowNodes: FlowNode[] = nodes.map((node) => {
    const point = positions.get(node.id) ?? { x: 0, y: 0 };
    return {
      id: node.id,
      type: "module",
      position: point,
      data: { graph: node },
      width: NODE_WIDTH,
      height: nodeHeight(node),
      selected: false,
    };
  });
  const positioned = layout ? applyLayout(flowNodes, layout) : flowNodes;
  const flowEdges: FlowEdge[] = edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: "bandwidth",
    data: { graph: edge, utilization: metrics.get(edge.id)?.utilization ?? null },
    animated: false,
  }));
  return { nodes: positioned, edges: flowEdges };
}

export interface DataflowViewProps {
  graph: NodeGraph;
  onSelectNode?: (node: GraphNode) => void;
  layout?: LayoutFile;
  summary?: TraceSummary | null;
  onNodeDragStop?: (id: string, position: { x: number; y: number }) => void;
}

export function DataflowView({ graph, onSelectNode, layout, summary, onNodeDragStop }: DataflowViewProps) {
  const elements = useMemo(() => buildFlowElements(graph, layout, summary), [graph, layout, summary]);
  return (
    <FlowCanvas
      nodes={elements.nodes}
      edges={elements.edges}
      onSelectNode={onSelectNode}
      onNodeDragStop={onNodeDragStop}
    />
  );
}
