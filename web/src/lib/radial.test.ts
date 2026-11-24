import { describe, expect, it } from "vitest";
import { sampleGraph } from "../test/fixtures";
import { radialLayout } from "./radial";

describe("时钟树径向布局", () => {
  it("只保留时钟/cdc/模块节点与时钟边", () => {
    const layout = radialLayout(sampleGraph);
    expect(layout.nodes.map((node) => node.id).sort()).toEqual(["clk:clk", "mod:uart"]);
    expect(layout.edges.map((edge) => edge.id)).toEqual(["clk:clk->mod:uart"]);
  });

  it("根在原点，子节点在外环，且结果确定", () => {
    const first = radialLayout(sampleGraph);
    const second = radialLayout(sampleGraph);
    expect(JSON.stringify(first)).toBe(JSON.stringify(second));
    const root = first.nodes.find((node) => node.id === "clk:clk");
    const child = first.nodes.find((node) => node.id === "mod:uart");
    expect(root?.depth).toBe(0);
    expect(child?.depth).toBe(1);
    expect(Math.hypot(child?.x ?? 0, child?.y ?? 0)).toBeGreaterThan(100);
  });
});
