// slc:// 按钮：生成 URI、尝试拉起协议，并始终提供剪贴板回退。
// 不做全局 URI Scheme 注册；注册脚本见 scripts/register-rvopen-*。
import type { GraphNode } from "../../contracts/node_graph";

export function buildSlcUri(node: GraphNode): string | null {
  if (!node.loc) return null;
  const params = new URLSearchParams({
    file: node.loc.file,
    line: String(node.loc.line),
  });
  if (node.module) params.set("module", node.module);
  return `slc://open?${params.toString()}`;
}

export type OpenResult = "copied" | "failed";

/** 浏览器无法感知协议处理器是否成功，因此拉起后仍需复制作为兜底。 */
export function openSlcUri(uri: string): void {
  try {
    window.location.href = uri;
  } catch {
    // 协议未注册时部分浏览器会抛错；由调用方提示使用复制回退。
  }
}

export async function copySlcUri(uri: string): Promise<OpenResult> {
  try {
    if (!navigator.clipboard) return "failed";
    await navigator.clipboard.writeText(uri);
    return "copied";
  } catch {
    return "failed";
  }
}
