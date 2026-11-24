// rvgen:// 按钮：P3 生成 URI 并复制到剪贴板；协议注册与拉起在 P5（rvopen + register 脚本）。
// 不做全局 URI Scheme 注册，也不在未注册时静默失败。
import type { GraphNode } from "../../contracts/node_graph";

export function buildRvgenUri(node: GraphNode): string | null {
  if (!node.loc) return null;
  const params = new URLSearchParams({
    file: node.loc.file,
    line: String(node.loc.line),
  });
  if (node.module) params.set("module", node.module);
  return `rvgen://open?${params.toString()}`;
}

export type OpenResult = "copied" | "failed";

export async function copyRvgenUri(uri: string): Promise<OpenResult> {
  try {
    if (!navigator.clipboard) return "failed";
    await navigator.clipboard.writeText(uri);
    return "copied";
  } catch {
    return "failed";
  }
}
