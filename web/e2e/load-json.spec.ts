import { expect, test } from "@playwright/test";

test("load-json：加载 node_graph.json 并打开详情抽屉", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("graph-meta")).toContainText("节点");
  await expect(page.locator('[data-id="mod:uart"]')).toBeVisible();
  await expect(page.locator('[data-id="mod:fifo"]')).toBeVisible();

  await page.locator('[data-id="mod:uart"]').click();
  const drawer = page.getByTestId("detail-drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer).toContainText("uart");
  await expect(drawer).toContainText("rvgen.yaml:23");
  await expect(page.getByTestId("rvgen-button")).toBeEnabled();
});

test("load-json：非法数据源给出可读错误", async ({ page }) => {
  await page.goto("/?graph=/sample/missing.json");
  await expect(page.getByRole("alert")).toContainText("读取");
});
