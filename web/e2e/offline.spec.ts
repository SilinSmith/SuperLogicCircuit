import { expect, test } from "@playwright/test";

test("offline：数据源不可达时给出错误，恢复后重试成功", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("graph-meta")).toContainText("节点");

  await page.route("**/sample/node_graph.json*", (route) => route.abort());
  await page.getByTestId("reload-button").click();
  const alert = page.getByRole("alert");
  await expect(alert).toBeVisible();
  await expect(alert).toContainText("无法读取");

  await page.unroute("**/sample/node_graph.json*");
  await alert.getByRole("button", { name: "重试" }).click();
  await expect(page.getByTestId("graph-meta")).toContainText("节点");
  await expect(page.locator('[data-id="mod:uart"]')).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});
