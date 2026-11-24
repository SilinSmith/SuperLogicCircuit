import { describe, expect, it } from "vitest";
import { edgeLabel, formatBandwidth, formatGbps } from "./bandwidth";

describe("bandwidth 单位口径", () => {
  it("derived：32 bit × 50 MHz = 0.2 GB/s (decimal)", () => {
    expect(formatGbps(32, 50_000_000)).toBe("0.200 GB/s (decimal)");
    expect(
      formatBandwidth({ source: "derived", width_bits: 32, clock: "clk", freq_hz: 50_000_000 }),
    ).toBe("32 bit/cyc · 0.200 GB/s (decimal)");
  });

  it("explicit 原样采用", () => {
    expect(
      formatBandwidth({ source: "explicit", value: "12.8 GB/s", reason: "手册标称峰值" }),
    ).toBe("12.8 GB/s");
  });

  it("null 带宽回退到位宽/类别文案", () => {
    expect(formatBandwidth(null)).toBeNull();
    expect(
      edgeLabel({
        id: "e1",
        source: "a",
        target: "b",
        kind: "data",
        width_bits: 8,
      }),
    ).toBe("8 bit");
    expect(
      edgeLabel({ id: "e2", source: "a", target: "b", kind: "clock", width_bits: null }),
    ).toBe("clock");
  });
});
