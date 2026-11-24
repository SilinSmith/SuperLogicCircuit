// 带宽单位口径（方案 4.2）：权威单位 bits/cycle；GB/s 按十进制 1e9，UI 标注 decimal。
import type { Bandwidth, GraphEdge } from "../../contracts/node_graph";

export function formatGbps(widthBits: number, freqHz: number): string {
  const gbps = (widthBits * freqHz) / 8 / 1e9;
  if (gbps === 0) return "0 GB/s";
  const fixed = gbps >= 100 ? gbps.toFixed(0) : gbps >= 1 ? gbps.toFixed(2) : gbps.toFixed(3);
  return `${fixed} GB/s (decimal)`;
}

export function formatBandwidth(bandwidth: Bandwidth | null | undefined): string | null {
  if (!bandwidth) return null;
  if (bandwidth.source === "explicit") return bandwidth.value;
  return `${bandwidth.width_bits} bit/cyc · ${formatGbps(bandwidth.width_bits, bandwidth.freq_hz)}`;
}

export function edgeLabel(edge: GraphEdge): string {
  const bandwidth = formatBandwidth(edge.bandwidth);
  if (bandwidth) return bandwidth;
  if (edge.kind === "clock") return "clock";
  if (edge.kind === "reset") return "reset";
  if (edge.kind === "cdc") return "cdc";
  if (typeof edge.width_bits === "number") return `${edge.width_bits} bit`;
  return "";
}
