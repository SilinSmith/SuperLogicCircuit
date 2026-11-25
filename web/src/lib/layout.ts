import type { NodeGraph } from "../../contracts/node_graph";
import type { FlowNode } from "../flow/types";

export interface NodeLayout {
  x: number;
  y: number;
  pinned?: boolean;
  collapsed?: boolean;
  control_points?: unknown;
}

export interface LayoutFile {
  version: 1;
  nodes: Record<string, NodeLayout>;
  _stale?: Record<string, NodeLayout & { at: string }>;
}

export const LAYOUT_STORAGE_KEY = "slc:layout:v1";
const STALE_TTL_MS = 30 * 24 * 60 * 60 * 1000;

export function emptyLayout(): LayoutFile {
  return { version: 1, nodes: {} };
}

function isNodeLayout(value: unknown): value is NodeLayout {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Partial<NodeLayout>;
  return typeof entry.x === "number" && typeof entry.y === "number";
}

export function parseLayout(raw: unknown): LayoutFile {
  if (typeof raw !== "object" || raw === null) return emptyLayout();
  const value = raw as Partial<LayoutFile>;
  const nodes: Record<string, NodeLayout> = {};
  if (value.nodes && typeof value.nodes === "object") {
    for (const [id, entry] of Object.entries(value.nodes)) {
      if (isNodeLayout(entry)) nodes[id] = { ...entry };
    }
  }
  const stale: Record<string, NodeLayout & { at: string }> = {};
  if (value._stale && typeof value._stale === "object") {
    for (const [id, entry] of Object.entries(value._stale)) {
      if (isNodeLayout(entry)) {
        stale[id] = { ...entry, at: typeof entry.at === "string" ? entry.at : new Date().toISOString() };
      }
    }
  }
  return { version: 1, nodes, ...(Object.keys(stale).length > 0 ? { _stale: stale } : {}) };
}

function safeStorage(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

export function readLayout(storage: Storage | undefined = safeStorage()): LayoutFile {
  if (!storage) return emptyLayout();
  try {
    const raw = storage.getItem(LAYOUT_STORAGE_KEY);
    return raw ? parseLayout(JSON.parse(raw)) : emptyLayout();
  } catch {
    return emptyLayout();
  }
}

export function writeLayout(layout: LayoutFile, storage: Storage | undefined = safeStorage()): void {
  if (!storage) return;
  try {
    storage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout));
  } catch {
    // 隐私模式/配额不足时静默放弃；布局是旁路数据。
  }
}

/** 按 node id 覆盖坐标；未保存过的节点沿用布局算法初值。 */
export function applyLayout(nodes: FlowNode[], layout: LayoutFile): FlowNode[] {
  return nodes.map((node) => {
    const saved = layout.nodes[node.id];
    return saved ? { ...node, position: { x: saved.x, y: saved.y } } : node;
  });
}

/** 重载后按 node id 合并：消失节点移入 _stale，pinned/collapsed 原样保留。 */
export function mergeLayoutFile(
  graph: Pick<NodeGraph, "nodes">,
  previous: LayoutFile,
  now: number = Date.now(),
): LayoutFile {
  const ids = new Set(graph.nodes.map((node) => node.id));
  const nodes: Record<string, NodeLayout> = {};
  const stale: Record<string, NodeLayout & { at: string }> = { ...(previous._stale ?? {}) };
  for (const [id, entry] of Object.entries(previous.nodes)) {
    if (ids.has(id)) {
      nodes[id] = entry;
    } else {
      stale[id] = { ...entry, at: new Date(now).toISOString() };
    }
  }
  for (const [id, entry] of Object.entries(stale)) {
    if (now - Date.parse(entry.at) > STALE_TTL_MS) delete stale[id];
  }
  return { version: 1, nodes, ...(Object.keys(stale).length > 0 ? { _stale: stale } : {}) };
}

export function recordPosition(
  layout: LayoutFile,
  id: string,
  position: { x: number; y: number },
): LayoutFile {
  return {
    ...layout,
    nodes: {
      ...layout.nodes,
      [id]: { ...layout.nodes[id], x: position.x, y: position.y },
    },
  };
}
