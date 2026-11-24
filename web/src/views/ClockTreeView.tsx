import { useMemo } from "react";
import type { GraphNode, NodeGraph } from "../../contracts/node_graph";
import { FlowCanvas } from "../flow/FlowCanvas";
import { NODE_WIDTH, nodeHeight, type FlowEdge, type FlowNode } from "../flow/types";
import { radialLayout } from "../lib/radial";

export interface ClockTreeViewProps {
  graph: NodeGraph;
  onSelectNode?: (node: GraphNode) => void;
}

export function ClockTreeView({ graph, onSelectNode }: ClockTreeViewProps) {
  const elements = useMemo(() => {
    const layout = radialLayout(graph);
    const byId = new Map(graph.nodes.map((node) => [node.id, node]));
    const nodes: FlowNode[] = layout.nodes.flatMap((positioned) => {
      const node = byId.get(positioned.id);
      if (!node) return [];
      return [
        {
          id: node.id,
          type: "module" as const,
          position: { x: positioned.x - NODE_WIDTH / 2, y: positioned.y - nodeHeight(node) / 2 },
          data: { graph: node },
          width: NODE_WIDTH,
          height: nodeHeight(node),
        },
      ];
    });
    const edges: FlowEdge[] = layout.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: "bandwidth" as const,
      data: { graph: edge },
    }));
    return { nodes, edges };
  }, [graph]);

  return <FlowCanvas nodes={elements.nodes} edges={elements.edges} onSelectNode={onSelectNode} />;
}
