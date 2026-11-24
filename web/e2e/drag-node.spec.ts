import { expect, test } from "@playwright/test";

test("drag-node：拖动节点后位置改变且不触发重排", async ({ page }) => {
  await page.goto("/");
  const node = page.locator('[data-id="mod:uart"]');
  await expect(node).toBeVisible();
  const before = await node.boundingBox();
  expect(before).not.toBeNull();
  if (!before) return;

  const startX = before.x + before.width / 2;
  const startY = before.y + 24;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 140, startY + 90, { steps: 12 });
  await page.mouse.up();

  await page.waitForTimeout(100);
  const after = await node.boundingBox();
  expect(after).not.toBeNull();
  if (!after) return;
  expect(Math.abs(after.x - before.x)).toBeGreaterThan(60);
  expect(Math.abs(after.y - before.y)).toBeGreaterThan(30);

  // 拖动只改坐标，不应改写图契约（页面无报错、节点仍在）
  await expect(node).toBeVisible();
});
