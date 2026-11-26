import { expect, test } from "@playwright/test";
import type { NodeGraph } from "../contracts/node_graph";

// 500 节点门槛（P3 验收）：默认不跑，PERF=1 时运行并输出 p95 帧率。
test.skip(!process.env.PERF, "PERF=1 才跑 500 节点性能校准");

function makeGraph(count: number): NodeGraph {
  const nodes = Array.from({ length: count }, (_, index) => ({
    id: `mod:m${index}`,
    type: "module_node" as const,
    label: `m${index}`,
    module: `m${index}`,
    clock: "clk",
    domain: "sys",
    ports: [
      { name: "clk", dir: "input" as const, width_bits: 1, kind: "clock" as const },
      { name: "din", dir: "input" as const, width_bits: 32, kind: "data" as const },
      { name: "dout", dir: "output" as const, width_bits: 32, kind: "data" as const },
    ],
    loc: { file: "slc.yaml", line: index + 1 },
  }));
  const edges = Array.from({ length: count - 1 }, (_, index) => ({
    id: `mod:m${index}.dout->mod:m${index + 1}.din`,
    source: `mod:m${index}`,
    target: `mod:m${index + 1}`,
    source_port: "dout",
    target_port: "din",
    kind: "data" as const,
    width_bits: 32,
    bandwidth: { source: "derived" as const, width_bits: 32, clock: "clk", freq_hz: 50_000_000 },
  }));
  return {
    schema_version: "1.0.0",
    generated_by: "slc 1.0.2",
    source_digest: "sha256:ffffffffffffffff",
    nodes,
    edges,
  };
}

test("perf-500：拖动帧 p95 ≥ 30 FPS", async ({ page }) => {
  const graph = makeGraph(500);
  await page.route("**/sample/node_graph.json", (route) =>
    route.fulfill({ json: graph, contentType: "application/json" }),
  );
  await page.goto("/");
  // 500 节点链在 minZoom 下无法整屏可见，取链条中段作为拖拽对象。
  const node = page.locator('[data-id="mod:m250"]');
  await expect(node).toBeVisible();

  const box = await node.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;

  const samples = await page.evaluate(async ({ x, y }) => {
    const frames: number[] = [];
    let last = performance.now();
    let running = true;
    const tick = (now: number) => {
      frames.push(now - last);
      last = now;
      if (running) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);

    const target = document.elementFromPoint(x, y) as HTMLElement | null;
    const init = { bubbles: true, clientX: x, clientY: y, buttons: 1 } as MouseEventInit;
    target?.dispatchEvent(new MouseEvent("mousedown", init));
    for (let index = 0; index < 60; index += 1) {
      window.dispatchEvent(
        new MouseEvent("mousemove", { ...init, clientX: x + index * 2, clientY: y + index }),
      );
      await new Promise((resolve) => requestAnimationFrame(resolve));
    }
    window.dispatchEvent(new MouseEvent("mouseup", { ...init, buttons: 0 }));
    running = false;
    return frames.slice(1);
  }, { x: box.x + box.width / 2, y: box.y + 20 });

  const fps = samples.map((ms) => 1000 / ms).sort((a, b) => a - b);
  const p95 = fps[Math.floor(fps.length * 0.95)] ?? 0;
  console.log(`[perf-500] frames=${fps.length} p95=${p95.toFixed(1)} FPS`);
  expect(p95).toBeGreaterThanOrEqual(30);
});
