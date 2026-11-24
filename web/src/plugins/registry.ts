import type { ComponentType } from "react";
import type { NodeGraph } from "../../contracts/node_graph";
import { PipelineView } from "./cpu/PipelineView";
import { CacheView } from "./cpu/CacheView";

export interface PluginViewProps {
  graph: NodeGraph;
}

export interface PluginViewDefinition {
  id: string;
  title: string;
  plugin: string;
  applies: (graph: NodeGraph) => boolean;
  Component: ComponentType<PluginViewProps>;
}

const hasCpuNodes = (graph: NodeGraph): boolean =>
  graph.nodes.some((node) => node.type.startsWith("p_cpu:")) ||
  graph.nodes.some((node) => node["x-cpu-stage"] !== undefined);

export const PLUGIN_VIEWS: PluginViewDefinition[] = [
  {
    id: "cpu-pipeline",
    title: "流水线时空",
    plugin: "cpu",
    applies: hasCpuNodes,
    Component: PipelineView,
  },
  {
    id: "cpu-cache",
    title: "Cache",
    plugin: "cpu",
    applies: (graph) =>
      graph.nodes.some((node) => node.type === "p_cpu:cache_node") ||
      graph.nodes.some((node) => node["x-cpu-cache"] !== undefined),
    Component: CacheView,
  },
];

export function availablePluginViews(graph: NodeGraph): PluginViewDefinition[] {
  return PLUGIN_VIEWS.filter((view) => view.applies(graph));
}
