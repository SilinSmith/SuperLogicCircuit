import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom 不实现 ResizeObserver / DOMMatrixReadOnly；React Flow 初始化需要它们。
class ResizeObserverStub {
  static instances: ResizeObserverStub[] = [];
  disconnected = false;
  observed: Element[] = [];

  constructor(private readonly callback: ResizeObserverCallback) {
    ResizeObserverStub.instances.push(this);
  }

  observe(target: Element): void {
    this.observed.push(target);
    this.callback(
      [{ contentRect: { width: 800, height: 600 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }

  unobserve(): void {}

  disconnect(): void {
    this.disconnected = true;
  }
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

if (typeof globalThis.DOMMatrixReadOnly === "undefined") {
  class DOMMatrixStub {
    m22 = 1;
    constructor(_transform?: string) {}
  }
  globalThis.DOMMatrixReadOnly = DOMMatrixStub as unknown as typeof DOMMatrixReadOnly;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

export { ResizeObserverStub };
