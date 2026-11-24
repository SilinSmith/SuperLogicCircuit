export const DEFAULT_EVENTS_URL = "/api/events";

export interface ServerEvent {
  kind: string;
  path?: string;
  sha256?: string;
  at?: string;
  [key: string]: unknown;
}

export interface EventHandlers {
  onStale?: (event: ServerEvent) => void;
  onResync?: () => void;
  onGitState?: (state: Record<string, unknown>) => void;
  onStatus?: (status: "open" | "reconnecting") => void;
}

interface EventSourceLike {
  addEventListener(type: string, listener: (event: MessageEvent) => void): void;
  close(): void;
  onopen: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
}

type EventSourceFactory = (url: string) => EventSourceLike;

export function eventsUrl(search = window.location.search): string {
  const params = new URLSearchParams(search);
  const value = params.get("events");
  return value && value.trim() !== "" ? value : DEFAULT_EVENTS_URL;
}

function parsePayload(data: string): Record<string, unknown> {
  try {
    const value = JSON.parse(data);
    return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

/**
 * 订阅服务端事件。收到 `yaml_changed` 等只记“有更新”，绝不自动拉图；
 * resync 也交由调用方决定是否重载（方案 §7.2）。
 */
export function connectEvents(
  url: string,
  handlers: EventHandlers,
  factory: EventSourceFactory = (target) => new EventSource(target) as unknown as EventSourceLike,
): () => void {
  const source = factory(url);
  for (const kind of ["yaml_changed", "graph_changed", "summary_changed"]) {
    source.addEventListener(kind, (event) => {
      handlers.onStale?.({ kind, ...parsePayload(event.data) });
    });
  }
  source.addEventListener("resync", () => handlers.onResync?.());
  source.addEventListener("git_state", (event) => handlers.onGitState?.(parsePayload(event.data)));
  source.onopen = () => handlers.onStatus?.("open");
  source.onerror = () => handlers.onStatus?.("reconnecting");
  return () => source.close();
}
