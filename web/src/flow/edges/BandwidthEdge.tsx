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
  source?: "explicit" | "derived" | "trace";
  utilization?: number | null;
}

const SOURCE_MARK: Record<string, string> = {
  explicit: "E",
  derived: "D",
  trace: "T",
};

const SOURCE_TITLE: Record<string, string> = {
  explicit: "带宽来源：explicit（人工标注）",
  derived: "带宽来源：derived（宽度 × 时钟）",
  trace: "带宽来源：trace_summary（实测）",
};

/** 标签单独导出，便于在无 React Flow 画布上下文时做快照测试。 */
export function BandwidthLabel({ id, x, y, label, source, utilization }: BandwidthLabelProps) {
  const mark = source ? SOURCE_MARK[source] : null;
  return (
    <span
      className="bandwidth-edge__label"
      data-testid={`edge-label-${id}`}
      style={{ transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }}
    >
      {source && mark ? (
        <span className="bandwidth-edge__source" data-source={source} title={SOURCE_TITLE[source]}>
          {mark}
        </span>
      ) : null}
      {label}
      {typeof utilization === "number" ? (
        <span className="bandwidth-edge__util" title="trace_summary 实测利用率">
          {Math.round(utilization * 100)}%
        </span>
      ) : null}
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
  const utilization = data?.utilization;
  const source =
    typeof utilization === "number"
      ? "trace"
      : graph?.bandwidth?.source === "explicit" || graph?.bandwidth?.source === "derived"
        ? graph.bandwidth.source
        : undefined;

  return (
    <>
      <BaseEdge id={id} path={path} className={`bandwidth-edge ${kindClass}${critical}`} />
      {label ? (
        <EdgeLabelRenderer>
          <BandwidthLabel
            id={id}
            x={labelX}
            y={labelY}
            label={label}
            source={source}
            utilization={utilization}
          />
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
});
