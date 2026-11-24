import { memo } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import { edgeLabel } from "../../lib/bandwidth";
import type { FlowEdge } from "../types";

const KIND_CLASS: Record<string, string> = {
  data: "edge--data",
  handshake: "edge--handshake",
  bundle: "edge--bundle",
  param: "edge--param",
  clock: "edge--clock",
  reset: "edge--reset",
  cdc: "edge--cdc",
};

export interface BandwidthLabelProps {
  id: string;
  x: number;
  y: number;
  label: string;
}

/** 标签单独导出，便于在无 React Flow 画布上下文时做快照测试。 */
export function BandwidthLabel({ id, x, y, label }: BandwidthLabelProps) {
  return (
    <span
      className="bandwidth-edge__label"
      data-testid={`edge-label-${id}`}
      style={{ transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }}
    >
      {label}
    </span>
  );
}

export const BandwidthEdge = memo(function BandwidthEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<FlowEdge>) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const graph = data?.graph;
  const label = graph ? edgeLabel(graph) : "";
  const kindClass = graph ? (KIND_CLASS[graph.kind] ?? "edge--data") : "edge--data";
  const critical = graph?.is_critical ? " edge--critical" : "";

  return (
    <>
      <BaseEdge id={id} path={path} className={`bandwidth-edge ${kindClass}${critical}`} />
      {label ? (
        <EdgeLabelRenderer>
          <BandwidthLabel id={id} x={labelX} y={labelY} label={label} />
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
});
