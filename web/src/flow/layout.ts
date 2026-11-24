// 数据流视图默认 dagre：分层有向图，同步计算，≤80 节点场景足够（方案 5.6）。
import dagre from "dagre";
import type { GraphEdge, GraphNode } from "../../contracts/node_graph";
import { NODE_WIDTH, nodeHeight } from "./types";

export type LayoutDirection = "LR" | "TB";

export interface Point {
  x: number;
  y: number;
}

export function layoutNodes(
  nodes: GraphNode[],
  edges: GraphEdge[],
  direction: LayoutDirection = "LR",
): Map<string, Point> {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: direction,
    nodesep: 48,
    ranksep: 96,
    marginx: 24,
    marginy: 24,
  });
  graph.setDefaultEdgeLabel(() => ({}));
  for (const node of nodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: nodeHeight(node) });
  }
  for (const edge of edges) {
    if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
      graph.setEdge(edge.source, edge.target);
    }
  }
  dagre.layout(graph);

  const positions = new Map<string, Point>();
  for (const node of nodes) {
    const laid = graph.node(node.id);
    if (!laid) continue;
    positions.set(node.id, {
      x: laid.x - NODE_WIDTH / 2,
      y: laid.y - nodeHeight(node) / 2,
    });
  }
  return positions;
}
