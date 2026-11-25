// 只读图加载：P5 起由 slc serve 提供 /api/graph；静态样例仅用于离线演示。
import type { GraphEdge, GraphNode, NodeGraph } from "../../contracts/node_graph";

export const SAMPLE_GRAPH_URL = "/sample/node_graph.json";
export const LIVE_GRAPH_URL = "/api/graph";
export const DEFAULT_GRAPH_URL = SAMPLE_GRAPH_URL;

export class GraphLoadError extends Error {
  constructor(
    message: string,
    readonly detail?: string,
  ) {
    super(message);
    this.name = "GraphLoadError";
  }
}

/** serve 默认端口 8123；`?live=1` 可强制，`?live=0` 可回到样例。 */
export function isLiveSource(
  search = window.location.search,
  port = window.location.port,
): boolean {
  const params = new URLSearchParams(search);
  const flag = params.get("live");
  if (flag === "0") return false;
  if (flag === "1") return true;
  return params.get("graph") === null && port === "8123";
}

/** ?graph= 优先；否则由 serve 托管时走 /api/graph，其余场景读样例。 */
export function resolveGraphUrl(search = window.location.search, port = window.location.port): string {
  const params = new URLSearchParams(search);
  const value = params.get("graph");
  if (value && value.trim() !== "") return value;
  return isLiveSource(search, port) ? LIVE_GRAPH_URL : SAMPLE_GRAPH_URL;
}

function asArray(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new GraphLoadError(`node_graph.json 字段 ${field} 必须是数组`);
  }
  return value;
}

function assertNode(value: unknown): GraphNode {
  if (typeof value !== "object" || value === null) {
    throw new GraphLoadError("node_graph.json 的节点必须是对象");
  }
  const node = value as Partial<GraphNode>;
  if (!node.id || typeof node.id !== "string") {
    throw new GraphLoadError("节点缺少 id");
  }
  if (!node.type || typeof node.type !== "string") {
    throw new GraphLoadError(`节点 ${node.id} 缺少 type`);
  }
  if (!node.label || typeof node.label !== "string") {
    throw new GraphLoadError(`节点 ${node.id} 缺少 label`);
  }
  return node as GraphNode;
}

function assertEdge(value: unknown): GraphEdge {
  if (typeof value !== "object" || value === null) {
    throw new GraphLoadError("node_graph.json 的边必须是对象");
  }
  const edge = value as Partial<GraphEdge>;
  for (const field of ["id", "source", "target", "kind"] as const) {
    if (!edge[field] || typeof edge[field] !== "string") {
      throw new GraphLoadError(`边缺少 ${field}`);
    }
  }
  return edge as GraphEdge;
}

/** 运行期守卫：只校验前端渲染真正用到的字段，完整校验仍由 schema/check 负责。 */
export function parseGraph(raw: unknown): NodeGraph {
  if (typeof raw !== "object" || raw === null) {
    throw new GraphLoadError("node_graph.json 根必须是对象");
  }
  const graph = raw as Partial<NodeGraph>;
  if (graph.schema_version !== "1.0.0") {
    throw new GraphLoadError(`不支持的 schema_version: ${String(graph.schema_version)}`);
  }
  if (typeof graph.source_digest !== "string") {
    throw new GraphLoadError("缺少 source_digest");
  }
  const nodes = asArray(graph.nodes, "nodes").map(assertNode);
  const edges = asArray(graph.edges, "edges").map(assertEdge);
  const ids = new Set(nodes.map((node) => node.id));
  if (ids.size !== nodes.length) {
    throw new GraphLoadError("节点 id 重复");
  }
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) {
      throw new GraphLoadError(
        `边 ${edge.id} 引用了不存在的节点`,
        `${edge.source} -> ${edge.target}`,
      );
    }
  }
  return { ...(graph as NodeGraph), nodes, edges };
}

export async function loadGraph(url: string, signal?: AbortSignal): Promise<NodeGraph> {
  let response: Response;
  try {
    response = await fetch(url, { signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new GraphLoadError(`无法读取 ${url}`, error instanceof Error ? error.message : String(error));
  }
  if (!response.ok) {
    throw new GraphLoadError(`读取 ${url} 失败：HTTP ${response.status}`);
  }
  let raw: unknown;
  try {
    raw = await response.json();
  } catch (error) {
    throw new GraphLoadError(`${url} 不是合法 JSON`, error instanceof Error ? error.message : String(error));
  }
  return parseGraph(raw);
}
