import { describe, expect, it } from "vitest";
import { GraphLoadError, parseGraph, resolveGraphUrl } from "./graph";
import { sampleGraph } from "../test/fixtures";

describe("node_graph 运行期守卫", () => {
  it("接受合法静态图", () => {
    const graph = parseGraph(JSON.parse(JSON.stringify(sampleGraph)));
    expect(graph.nodes).toHaveLength(3);
    expect(graph.edges).toHaveLength(2);
  });

  it("拒绝不支持的 schema_version", () => {
    expect(() => parseGraph({ ...sampleGraph, schema_version: "2.0.0" })).toThrow(GraphLoadError);
  });

  it("拒绝悬空边", () => {
    const broken = JSON.parse(JSON.stringify(sampleGraph));
    broken.edges[0].target = "mod:missing";
    expect(() => parseGraph(broken)).toThrow(/不存在的节点/);
  });

  it("?graph= 覆盖默认数据源", () => {
    expect(resolveGraphUrl("?graph=/api/graph")).toBe("/api/graph");
    expect(resolveGraphUrl("")).toBe("/sample/node_graph.json");
  });
});
