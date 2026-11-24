import type { Edge, Node } from "@xyflow/react";
import type { GraphEdge, GraphNode } from "../../contracts/node_graph";

export interface ModuleNodeData extends Record<string, unknown> {
  graph: GraphNode;
}

export interface BandwidthEdgeData extends Record<string, unknown> {
  graph: GraphEdge;
  utilization?: number | null;
}

export type FlowNode = Node<ModuleNodeData, "module">;
export type FlowEdge = Edge<BandwidthEdgeData, "bandwidth">;

export const NODE_WIDTH = 248;
export const PORT_ROW_HEIGHT = 20;
export const MAX_VISIBLE_PORTS = 8;

export function visiblePorts(node: GraphNode): GraphNode["ports"] {
  const ports = node.ports ?? [];
  return ports.slice(0, MAX_VISIBLE_PORTS);
}

export function nodeHeight(node: GraphNode): number {
  const ports = visiblePorts(node)?.length ?? 0;
  const hidden = Math.max(0, (node.ports?.length ?? 0) - ports);
  return 64 + ports * PORT_ROW_HEIGHT + (hidden > 0 ? PORT_ROW_HEIGHT : 0);
}
