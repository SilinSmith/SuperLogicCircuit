// 手写的 node_graph.json v1 契约镜像，字段顺序与 schema/node_graph.schema.json 一致。
// 前端只允许依赖本目录与 /api；不得 import py/。P6 可改为由 schema 自动生成。
// 纯静态契约：不包含 layout / trace 指标 / 时间戳。

export type CoreNodeType = "module_node" | "clock_node" | "cdc_node" | "stats_node";
export type NodeType = CoreNodeType | `p_${string}:${string}`;

export type PortDir = "input" | "output" | "inout";
export type PortKind =
  | "data"
  | "valid"
  | "ready"
  | "handshake"
  | "clock"
  | "reset"
  | "param";

export type EdgeKind = "data" | "handshake" | "clock" | "reset" | "cdc" | "param" | "bundle";

export interface GraphLocation {
  file: string;
  line: number;
  end_line?: number | null;
}

export interface GraphPort {
  name: string;
  dir: PortDir;
  width_expr?: string | number | null;
  width_bits?: number | null;
  kind?: PortKind;
  domain?: string | null;
  unresolved?: string | null;
}

interface Extensible {
  [key: `x-${string}`]: unknown;
}

export interface GraphNode extends Extensible {
  id: string;
  type: NodeType;
  label: string;
  module?: string | null;
  clock?: string | null;
  loc?: GraphLocation | null;
  domain?: string | null;
  ports?: GraphPort[];
  status?: string | null;
  todo?: string | null;
}

export interface BandwidthExplicit extends Extensible {
  source: "explicit";
  value: string;
  reason: string;
}

export interface BandwidthDerived extends Extensible {
  source: "derived";
  width_bits: number;
  clock: string;
  freq_hz: number;
}

export type Bandwidth = BandwidthExplicit | BandwidthDerived;

export interface GraphEdge extends Extensible {
  id: string;
  source: string;
  target: string;
  source_port?: string | null;
  target_port?: string | null;
  kind: EdgeKind;
  width_bits?: number | null;
  bandwidth?: Bandwidth | null;
  is_critical?: boolean;
}

export interface NodeGraph extends Extensible {
  schema_version: "1.0.0";
  generated_by: string;
  source_digest: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export function isCoreNodeType(type: string): type is CoreNodeType {
  return (
    type === "module_node" ||
    type === "clock_node" ||
    type === "cdc_node" ||
    type === "stats_node"
  );
}
