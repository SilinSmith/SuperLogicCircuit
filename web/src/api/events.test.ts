import { describe, expect, it, vi } from "vitest";
import { DEFAULT_EVENTS_URL, connectEvents, eventsUrl } from "./events";

class FakeEventSource {
  listeners = new Map<string, Array<(event: MessageEvent) => void>>();
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    const existing = this.listeners.get(type) ?? [];
    this.listeners.set(type, [...existing, listener]);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data: JSON.stringify(data) } as MessageEvent);
    }
  }
}

describe("SSE 事件订阅", () => {
  it("?events= 覆盖默认地址", () => {
    expect(eventsUrl("")).toBe(DEFAULT_EVENTS_URL);
    expect(eventsUrl("?events=/custom/events")).toBe("/custom/events");
  });

  it("分发 yaml_changed / resync / git_state，且可关闭", () => {
    const source = new FakeEventSource();
    const onStale = vi.fn();
    const onResync = vi.fn();
    const onGitState = vi.fn();
    const close = connectEvents(
      "/api/events",
      { onStale, onResync, onGitState },
      () => source,
    );

    source.emit("yaml_changed", { path: "rvgen.yaml", sha256: "abc" });
    expect(onStale).toHaveBeenCalledWith({ kind: "yaml_changed", path: "rvgen.yaml", sha256: "abc" });

    source.emit("resync", {});
    expect(onResync).toHaveBeenCalledTimes(1);

    source.emit("git_state", { branch: "master", dirty: false });
    expect(onGitState).toHaveBeenCalledWith({ branch: "master", dirty: false });

    close();
    expect(source.closed).toBe(true);
  });
});
