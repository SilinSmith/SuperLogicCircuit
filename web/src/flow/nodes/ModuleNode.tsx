import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { GraphNode, GraphPort } from "../../../contracts/node_graph";
import { visiblePorts, type FlowNode } from "../types";

function dirGlyph(dir: GraphPort["dir"]): string {
  if (dir === "input") return "←";
  if (dir === "output") return "→";
  return "↔";
}

function widthText(port: GraphPort): string {
  if (typeof port.width_bits === "number") return `${port.width_bits}b`;
  if (port.width_expr !== null && port.width_expr !== undefined) return String(port.width_expr);
  return "?";
}

export function typeLabel(node: GraphNode): string {
  if (node.type === "module_node") return "module";
  if (node.type === "clock_node") return "clock";
  if (node.type === "cdc_node") return "cdc";
  if (node.type === "stats_node") return "stats";
  return node.type.replace(/^p_[a-z0-9_]+:/, "plugin:");
}

export const ModuleNode = memo(function ModuleNode({ data, selected }: NodeProps<FlowNode>) {
  const node = data.graph;
  const ports = visiblePorts(node) ?? [];
  const hidden = Math.max(0, (node.ports?.length ?? 0) - ports.length);

  return (
    <div
      className={`module-node${selected ? " module-node--selected" : ""}`}
      data-testid={`module-node-${node.id}`}
    >
      <Handle type="target" position={Position.Left} className="module-node__handle" />
      <header className="module-node__header">
        <span className="module-node__label">{node.label}</span>
        <span className="module-node__badge">{typeLabel(node)}</span>
      </header>
      <div className="module-node__meta">
        <span>{node.domain ?? "domain: -"}</span>
        <span>{node.clock ?? "-"}</span>
      </div>
      <ul className="module-node__ports">
        {ports.map((port) => (
          <li key={port.name} className="module-node__port" title={`${port.dir} ${port.name}`}>
            <span className="module-node__dir">{dirGlyph(port.dir)}</span>
            <span className="module-node__port-name">{port.name}</span>
            <span className="module-node__width">{widthText(port)}</span>
          </li>
        ))}
        {hidden > 0 ? <li className="module-node__port module-node__more">+{hidden} 个端口</li> : null}
      </ul>
      {node.status ? <div className="module-node__status">{node.status}</div> : null}
      <Handle type="source" position={Position.Right} className="module-node__handle" />
    </div>
  );
});
