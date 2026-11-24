import { beforeEach, describe, expect, it } from "vitest";
import {
  LAYOUT_STORAGE_KEY,
  applyLayout,
  emptyLayout,
  mergeLayoutFile,
  parseLayout,
  readLayout,
  recordPosition,
  writeLayout,
} from "./layout";
import type { FlowNode } from "../flow/types";
import { sampleGraph } from "../test/fixtures";

function flowNode(id: string, x: number, y: number): FlowNode {
  return {
    id,
    type: "module",
    position: { x, y },
    data: { graph: sampleGraph.nodes[0] },
  } as FlowNode;
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("layout 持久化", () => {
  it("applyLayout 只覆盖已保存的节点", () => {
    const nodes = [flowNode("mod:a", 0, 0), flowNode("mod:b", 10, 10)];
    const nodesLayout = applyLayout(nodes, {
      version: 1,
      nodes: { "mod:a": { x: 100, y: 200 } },
    });
    expect(nodesLayout[0].position).toEqual({ x: 100, y: 200 });
    expect(nodesLayout[1].position).toEqual({ x: 10, y: 10 });
  });

  it("mergeLayoutFile 保留 pinned/collapsed，消失节点进 _stale", () => {
    const previous = {
      version: 1 as const,
      nodes: {
        "mod:uart": { x: 1, y: 2, pinned: true, collapsed: true },
        "mod:gone": { x: 3, y: 4 },
      },
    };
    const merged = mergeLayoutFile(sampleGraph, previous, Date.parse("2026-11-25T00:00:00Z"));
    expect(merged.nodes["mod:uart"]).toEqual({ x: 1, y: 2, pinned: true, collapsed: true });
    expect(merged.nodes["mod:gone"]).toBeUndefined();
    expect(merged._stale?.["mod:gone"]).toMatchObject({ x: 3, y: 4 });
    expect(merged._stale?.["mod:gone"].at).toBe("2026-11-25T00:00:00.000Z");
  });

  it("mergeLayoutFile 清理超过 30 天的 _stale 条目", () => {
    const previous = parseLayout({
      version: 1,
      nodes: {},
      _stale: { "mod:old": { x: 1, y: 2, at: "2026-01-01T00:00:00.000Z" } },
    });
    const merged = mergeLayoutFile(sampleGraph, previous, Date.parse("2026-11-25T00:00:00Z"));
    expect(merged._stale).toBeUndefined();
  });

  it("recordPosition 合并坐标且不清除 pinned", () => {
    const layout = { version: 1 as const, nodes: { "mod:a": { x: 1, y: 2, pinned: true } } };
    const next = recordPosition(layout, "mod:a", { x: 9, y: 8 });
    expect(next.nodes["mod:a"]).toEqual({ x: 9, y: 8, pinned: true });
  });

  it("read/write 走 localStorage 并可容错坏数据", () => {
    expect(readLayout()).toEqual(emptyLayout());
    const layout = recordPosition(emptyLayout(), "mod:a", { x: 5, y: 6 });
    writeLayout(layout);
    expect(readLayout()).toEqual(layout);
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, "{not json");
    expect(readLayout()).toEqual(emptyLayout());
  });

  it("parseLayout 丢弃坐标非法的条目", () => {
    const layout = parseLayout({ nodes: { ok: { x: 1, y: 2 }, bad: { x: "1", y: 2 } } });
    expect(layout.nodes).toEqual({ ok: { x: 1, y: 2 } });
  });
});
