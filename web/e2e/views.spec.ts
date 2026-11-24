import { expect, test } from "@playwright/test";

test("核心三视图可切换：数据流 / 时钟树 / 统计", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("tab-dataflow")).toHaveClass(/app__tab--active/);

  await page.getByTestId("tab-clock").click();
  await expect(page.locator('[data-id="clk:clk"]')).toBeVisible();
  await expect(page.locator('[data-id="clk:clk_fast"]')).toBeVisible();

  await page.getByTestId("tab-stats").click();
  await expect(page.getByTestId("stats-view")).toBeVisible();
  await expect(page.getByTestId("chart-bandwidth")).toBeVisible();
  await expect(page.getByTestId("stats-view")).toContainText("20000 cycles");

  await page.getByTestId("tab-dataflow").click();
  await expect(page.locator('[data-id="mod:uart"]')).toBeVisible();
});

test("通用图不出现 CPU 插件视图", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("tab-dataflow")).toBeVisible();
  await expect(page.getByTestId("tab-cpu-pipeline")).toHaveCount(0);
  await expect(page.getByTestId("tab-cpu-cache")).toHaveCount(0);
});

test("启用 cpu 插件数据时出现流水线/Cache 视图", async ({ page }) => {
  await page.goto("/?graph=/sample/node_graph_cpu.json&summary=/sample/missing.json");
  await page.getByTestId("tab-cpu-pipeline").click();
  await expect(page.getByTestId("pipeline-view")).toBeVisible();
  await expect(page.getByTestId("pipeline-view")).toContainText("addi");
  await expect(page.getByTestId("pipeline-view")).toContainText("IF");

  await page.getByTestId("tab-cpu-cache").click();
  await expect(page.getByTestId("cache-view")).toContainText("icache");
  await expect(page.getByTestId("cache-view")).toContainText("256");
});
