// 时钟树径向布局：不引入 elkjs（EPL/GPL 双许可且需 Worker），用确定性 BFS 分层。
// 根为没有入边的时钟节点；半径按层递增，叶子在同一环上均分角度。
import type { GraphEdge, GraphNode, NodeGraph } from "../../contracts/node_graph";

export const RING_RADIUS = 260;
const ROOT_RADIUS = 40;

export interface RadialNode {
  id: string;
  depth: number;
  x: number;
  y: number;
}

export interface RadialLayout {
  nodes: RadialNode[];
  edges: GraphEdge[];
  roots: string[];
}

const CLOCK_KINDS = new Set(["clock", "cdc"]);

export function clockTreeSubset(graph: NodeGraph): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const edges = graph.edges.filter((edge) => CLOCK_KINDS.has(edge.kind));
  const involved = new Set<string>();
  for (const edge of edges) {
    involved.add(edge.source);
    involved.add(edge.target);
  }
  const nodes = graph.nodes.filter(
    (node) =>
      involved.has(node.id) &&
      (node.type === "clock_node" || node.type === "cdc_node" || node.type === "module_node"),
  );
  return { nodes, edges };
}

export function radialLayout(graph: NodeGraph): RadialLayout {
  const { nodes, edges } = clockTreeSubset(graph);
  const ids = new Set(nodes.map((node) => node.id));
  const adjacency = new Map<string, string[]>();
  const incoming = new Set<string>();
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
    adjacency.set(edge.source, [...(adjacency.get(edge.source) ?? []), edge.target]);
    incoming.add(edge.target);
  }

  const clockIds = nodes.filter((node) => node.type === "clock_node").map((node) => node.id);
  const roots = clockIds.filter((id) => !incoming.has(id));
  const rootList = roots.length > 0 ? roots : clockIds.slice(0, 1);
  const depth = new Map<string, number>();
  const queue: string[] = [];
  for (const root of rootList) {
    depth.set(root, 0);
    queue.push(root);
  }
  while (queue.length > 0) {
    const current = queue.shift() as string;
    const level = depth.get(current) ?? 0;
    for (const next of adjacency.get(current) ?? []) {
      if (!depth.has(next)) {
        depth.set(next, level + 1);
        queue.push(next);
      }
    }
  }
  // 环上的 CDC/模块如果未被任何时钟走到，挂到最后一层，避免节点消失。
  const maxDepth = Math.max(0, ...depth.values());
  for (const node of nodes) {
    if (!depth.has(node.id)) depth.set(node.id, maxDepth + 1);
  }

  const byDepth = new Map<number, string[]>();
  for (const [id, level] of depth) {
    byDepth.set(level, [...(byDepth.get(level) ?? []), id]);
  }
  const positions: RadialNode[] = [];
  for (const [level, members] of [...byDepth.entries()].sort((a, b) => a[0] - b[0])) {
    const radius = level === 0 ? ROOT_RADIUS : ROOT_RADIUS + level * RING_RADIUS;
    members.sort();
    const count = Math.max(1, members.length);
    members.forEach((id, index) => {
      const angle = level === 0 && count === 1 ? -Math.PI / 2 : (2 * Math.PI * index) / count;
      positions.push({
        id,
        depth: level,
        x: radius * Math.cos(angle),
        y: radius * Math.sin(angle),
      });
    });
  }
  return { nodes: positions, edges, roots: rootList };
}
