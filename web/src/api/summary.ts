import { parseTraceSummary, type TraceSummary } from "../lib/stats";

export const DEFAULT_SUMMARY_URL = "/sample/trace_summary.json";

export function resolveSummaryUrl(search = window.location.search): string {
  const params = new URLSearchParams(search);
  const value = params.get("summary");
  return value && value.trim() !== "" ? value : DEFAULT_SUMMARY_URL;
}

/** trace_summary 是可选旁路数据：404 视为未提供，不阻塞主图。 */
export async function loadSummary(url: string, signal?: AbortSignal): Promise<TraceSummary | null> {
  const response = await fetch(url, { signal, headers: { Accept: "application/json" } });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`读取 ${url} 失败：HTTP ${response.status}`);
  return parseTraceSummary(await response.json());
}
