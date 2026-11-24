import type { GraphNode } from "../../../contracts/node_graph";
import type { PluginViewProps } from "../registry";

interface Slot {
  id: string;
  label: string;
  cycle: number;
  stage: number;
}

function stageColumns(graph: PluginViewProps["graph"]): string[] {
  const stages: { name: string; index: number }[] = [];
  for (const node of graph.nodes) {
    const name = node["x-cpu-stage"];
    const index = node["x-cpu-stage_index"];
    if (typeof name === "string" && typeof index === "number") {
      stages.push({ name, index });
    }
  }
  const unique = new Map<number, string>();
  for (const stage of stages) unique.set(stage.index, stage.name);
  return [...unique.entries()].sort((a, b) => a[0] - b[0]).map(([, name]) => name);
}

function slots(graph: PluginViewProps["graph"]): Slot[] {
  return graph.nodes.flatMap((node: GraphNode) => {
    if (node.type !== "p_cpu:pipeline_slot_node") return [];
    const cycle = node["x-cpu-cycle"];
    const stage = node["x-cpu-stage_index"];
    if (typeof cycle !== "number" || typeof stage !== "number") return [];
    return [{ id: node.id, label: node.label, cycle, stage }];
  });
}

/** plugins/cpu 注册的流水线时空图：横轴阶段、纵轴周期，只读 x-cpu-* 字段。 */
export function PipelineView({ graph }: PluginViewProps) {
  const stages = stageColumns(graph);
  const items = slots(graph).sort((a, b) => a.cycle - b.cycle || a.stage - b.stage);
  if (stages.length === 0) {
    return <div className="plugin-empty">该图没有 x-cpu-stage / x-cpu-stage_index 字段，无法绘制流水线。</div>;
  }
  const maxCycle = items.reduce((max, item) => Math.max(max, item.cycle), 0);
  return (
    <div className="pipeline-view" data-testid="pipeline-view">
      <div
        className="pipeline-view__grid"
        style={{
          gridTemplateColumns: `64px repeat(${stages.length}, minmax(96px, 1fr))`,
          gridTemplateRows: `repeat(${Math.max(1, maxCycle + 1)}, 34px)`,
        }}
      >
        {stages.map((stage, index) => (
          <div key={stage} className="pipeline-view__stage" style={{ gridColumn: index + 2, gridRow: 1 }}>
            {stage}
          </div>
        ))}
        {Array.from({ length: maxCycle + 1 }, (_, cycle) => (
          <div key={`c${cycle}`} className="pipeline-view__cycle" style={{ gridColumn: 1, gridRow: cycle + 1 }}>
            c{cycle}
          </div>
        ))}
        {items.map((slot) => (
          <div
            key={slot.id}
            className="pipeline-view__slot"
            style={{ gridColumn: slot.stage + 2, gridRow: slot.cycle + 1 }}
            title={`${slot.label} @ cycle ${slot.cycle}`}
          >
            {slot.label}
          </div>
        ))}
      </div>
      {items.length === 0 ? <p className="plugin-empty">没有 p_cpu:pipeline_slot_node 槽位数据。</p> : null}
    </div>
  );
}
