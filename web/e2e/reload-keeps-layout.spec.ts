import { expect, test, type Page } from "@playwright/test";

const NODE = '[data-id="mod:uart"]';

async function nodeTransform(page: Page): Promise<string> {
  return page.locator(NODE).evaluate((element) => (element as HTMLElement).style.transform);
}

async function dragNode(page: Page): Promise<void> {
  const node = page.locator(NODE);
  await expect(node).toBeVisible();
  const box = await node.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;
  const startX = box.x + box.width / 2;
  const startY = box.y + 24;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 160, startY + 100, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(100);
}

test("reload-keeps-layout：应用内重载后坐标保留", async ({ page }) => {
  await page.goto("/");
  await dragNode(page);
  const moved = await nodeTransform(page);

  await page.getByTestId("reload-button").click();
  await expect(page.getByTestId("graph-meta")).toContainText("节点");
  await expect(page.locator(NODE)).toBeVisible();
  expect(await nodeTransform(page)).toBe(moved);
});

test("reload-keeps-layout：浏览器刷新后坐标从 localStorage 恢复", async ({ page }) => {
  await page.goto("/");
  await dragNode(page);
  const moved = await nodeTransform(page);

  await page.reload();
  await expect(page.getByTestId("graph-meta")).toContainText("节点");
  await expect(page.locator(NODE)).toBeVisible();
  expect(await nodeTransform(page)).toBe(moved);
});
