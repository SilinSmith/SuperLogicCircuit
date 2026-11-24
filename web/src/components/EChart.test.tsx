import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResizeObserverStub } from "../test/setup";
import { EChart } from "./EChart";

const mocks = vi.hoisted(() => {
  const dispose = vi.fn();
  const setOption = vi.fn();
  const resize = vi.fn();
  const init = vi.fn(() => ({ dispose, setOption, resize }));
  return { dispose, setOption, resize, init };
});

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init: mocks.init,
  getInstanceByDom: vi.fn(() => null),
}));
vi.mock("echarts/charts", () => ({ BarChart: {} }));
vi.mock("echarts/components", () => ({ GridComponent: {}, TooltipComponent: {} }));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));

describe("EChart 生命周期", () => {
  it("卸载时 dispose 并断开 ResizeObserver", () => {
    const { unmount } = render(<EChart label="测试图" option={{ series: [] }} />);
    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(mocks.setOption).toHaveBeenCalled();
    unmount();
    expect(mocks.dispose).toHaveBeenCalledTimes(1);
    expect(ResizeObserverStub.instances.every((instance) => instance.disconnected)).toBe(true);
  });
});
