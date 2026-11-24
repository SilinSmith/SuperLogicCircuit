import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResizeObserverStub } from "../test/setup";
import { useElementSize } from "./useElementSize";

function Probe() {
  const [ref] = useElementSize<HTMLDivElement>();
  return <div ref={ref} data-testid="probe" />;
}

describe("useElementSize 泄漏检查", () => {
  it("挂载/卸载 20 次后所有 ResizeObserver 都已 disconnect", () => {
    for (let index = 0; index < 20; index += 1) {
      const { unmount } = render(<Probe />);
      unmount();
    }
    expect(ResizeObserverStub.instances.length).toBeGreaterThanOrEqual(20);
    expect(ResizeObserverStub.instances.every((instance) => instance.disconnected)).toBe(true);
  });
});
