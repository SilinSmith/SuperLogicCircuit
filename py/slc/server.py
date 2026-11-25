"""P5 本地看板服务：只读图/摘要、SSE 事件流、轮询去抖 watcher。

纪律：serve 永不改写 node_graph.json / slc.yaml；只有 POST /api/layout 允许写 layout.json。
事件只表达“受控资产变了”，由前端显示徽标并等待用户手动重载。
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import __version__
from .atomic import atomic_write
from .gitw import read_git_state

EVENT_CAPACITY = 64
SLOW_QUEUE = 128
DEBOUNCE_SECONDS = 0.4
POLL_SECONDS = 0.2
KEEPALIVE_SECONDS = 15

# 受控资产 → SSE 事件名；layout.json 由本服务写入，不监听（避免自触发）。
WATCHED: dict[str, str] = {
    "slc.yaml": "yaml_changed",
    "node_graph.json": "graph_changed",
    "trace_summary.json": "summary_changed",
}
GIT_EVENT = ".slc/.git-event"


@dataclass
class Event:
    id: int
    kind: str
    payload: dict[str, Any]


class EventBus:
    """环形缓冲 + 每客户端队列；慢客户端丢弃该订阅者并提示重连 resync。"""

    def __init__(self, capacity: int = EVENT_CAPACITY):
        self._events: deque[Event] = deque(maxlen=capacity)
        self._subscribers: list[queue.Queue[Event | None]] = []
        self._lock = threading.Lock()
        self._next_id = 1

    def publish(self, kind: str, payload: dict[str, Any]) -> Event:
        with self._lock:
            event = Event(self._next_id, kind, payload)
            self._next_id += 1
            self._events.append(event)
            slow: list[queue.Queue[Event | None]] = []
            for subscriber in self._subscribers:
                try:
                    subscriber.put_nowait(event)
                except queue.Full:
                    slow.append(subscriber)
            for subscriber in slow:
                self._subscribers.remove(subscriber)
                try:
                    subscriber.get_nowait()
                    subscriber.put_nowait(None)  # None = resync 指令
                except (queue.Empty, queue.Full):
                    pass
            return event

    def replay(self, last_id: int | None) -> tuple[list[Event], bool]:
        """返回 (待补发事件, 是否需要 resync)。last_id 滑出缓冲区即要求全量重拉。"""
        with self._lock:
            if last_id is None or not self._events:
                return [], False
            oldest = self._events[0].id
            if last_id < oldest - 1:
                return [], True
            return [event for event in self._events if event.id > last_id], False

    def subscribe(self, maxsize: int = SLOW_QUEUE) -> queue.Queue[Event | None]:
        subscriber: queue.Queue[Event | None] = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[Event | None]) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


@dataclass(eq=False)
class Watcher(threading.Thread):
    """轮询文件 mtime + sha256；内容稳定超过 debounce 后才发一条事件。"""

    root: Path
    bus: EventBus
    interval: float = POLL_SECONDS
    debounce: float = DEBOUNCE_SECONDS
    clock: Callable[[], float] = time.monotonic
    _states: dict[str, tuple[float | None, str | None]] = field(default_factory=dict)
    _pending: dict[str, float] = field(default_factory=dict)
    _stop: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        super().__init__(daemon=True, name="slc-watcher")

    def _state(self, key: str) -> tuple[float | None, str | None]:
        path = self.root / key
        try:
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None, None
        return stat.st_mtime, digest

    def poll_once(self) -> list[Event]:
        """单次轮询：首轮建立基线，变化后等 debounce 窗口再发一次。"""
        now = self.clock()
        published: list[Event] = []
        for key in [*WATCHED, GIT_EVENT]:
            state = self._state(key)
            previous = self._states.get(key)
            self._states[key] = state
            if previous is None:
                continue
            if state != previous:
                self._pending[key] = now
                continue
            changed_at = self._pending.get(key)
            if changed_at is not None and now - changed_at >= self.debounce:
                published.append(self._publish_change(key, state))
                self._pending.pop(key, None)
        return published

    def _publish_change(self, key: str, state: tuple[float | None, str | None]) -> Event:
        if key == GIT_EVENT:
            payload: dict[str, Any] = {"at": _now()}
            git_state = read_git_state(self.root)
            payload.update(git_state.as_dict() if git_state is not None else {"available": False})
            return self.bus.publish("git_state", payload)
        kind = WATCHED[key]
        mtime, digest = state
        return self.bus.publish(
            kind,
            {
                "path": key,
                "sha256": digest,
                "at": _now(),
                "mtime": mtime,
            },
        )

    def run(self) -> None:  # pragma: no cover - 线程循环
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def merge_layout(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """按节点 id 合并；incoming 的坐标/折叠/pinned 覆盖 base，不丢未知 id。

    结构固定为 `{nodes: {id: {...}}, _stale: {id: {...}}}`，只需两层合并。
    """
    merged = {**base}
    for key, value in incoming.items():
        existing = merged.get(key)
        if not isinstance(value, dict) or not isinstance(existing, dict):
            merged[key] = value
            continue
        section = {**existing}
        for sub_key, sub_value in value.items():
            previous = section.get(sub_key)
            if isinstance(sub_value, dict) and isinstance(previous, dict):
                section[sub_key] = {**previous, **sub_value}
            else:
                section[sub_key] = sub_value
        merged[key] = section
    return merged


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows 的 SO_REUSEADDR 允许两个进程同时绑定同一端口，必须关掉才能报占用。
    allow_reuse_address = os.name != "nt"


def make_handler(root: Path, bus: EventBus) -> type[BaseHTTPRequestHandler]:
    web_dist = root / "web" / "dist"

    class Handler(BaseHTTPRequestHandler):
        server_version = "slc/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            pass

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path: Path, content_type: str) -> None:
            if not path.exists():
                self._json(HTTPStatus.NOT_FOUND, {"error": f"{path.name} 不存在"})
                return
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/graph":
                self._file(root / "node_graph.json", "application/json; charset=utf-8")
                return
            if path == "/api/trace-summary":
                self._file(root / "trace_summary.json", "application/json; charset=utf-8")
                return
            if path == "/api/layout":
                layout_path = root / "layout.json"
                if layout_path.exists():
                    self._file(layout_path, "application/json; charset=utf-8")
                else:
                    self._json(HTTPStatus.OK, {})
                return
            if path == "/api/health":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "slc",
                        "version": __version__,
                        "project": str(root),
                        "subscribers": bus.subscriber_count(),
                    },
                )
                return
            if path == "/api/events":
                self._stream(parsed.query)
                return
            if path in ("/", "/index.html"):
                self._file(web_dist / "index.html", "text/html; charset=utf-8")
                return
            asset = (web_dist / path.lstrip("/")).resolve()
            if str(asset).startswith(str(web_dist.resolve())) and asset.is_file():
                types = {
                    ".js": "text/javascript",
                    ".css": "text/css",
                    ".json": "application/json",
                    ".svg": "image/svg+xml",
                    ".map": "application/json",
                }
                self._file(asset, types.get(asset.suffix.lower(), "application/octet-stream"))
                return
            if not (web_dist / "index.html").exists():
                self._json(
                    HTTPStatus.OK,
                    {
                        "service": "slc serve",
                        "hint": "web/dist 不存在：先 cd web && npm run build，或使用 vite dev 5174",
                    },
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/reload":
                # 手动重载由前端发起；此端点只回读当前图，不产生任何事件或覆写。
                self._file(root / "node_graph.json", "application/json; charset=utf-8")
                return
            if path != "/api/layout":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                incoming = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": f"invalid json: {exc}"})
                return
            if not isinstance(incoming, dict):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "layout 必须是对象"})
                return
            layout_path = root / "layout.json"
            base: dict[str, Any] = {}
            if layout_path.exists():
                try:
                    base = json.loads(layout_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    base = {}
            merged = merge_layout(base, incoming)
            atomic_write(layout_path, json.dumps(merged, ensure_ascii=False, indent=2) + "\n")
            self._json(HTTPStatus.OK, merged)

        def _stream(self, query: str) -> None:
            params = parse_qs(query)
            raw_last = self.headers.get("Last-Event-ID") or (params.get("last_id") or [None])[0]
            try:
                last_id = int(raw_last) if raw_last not in (None, "") else None
            except ValueError:
                last_id = None
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self.wfile.write(b"retry: 1000\n\n")
                self.wfile.flush()
                subscriber = bus.subscribe()
                try:
                    pending, needs_resync = bus.replay(last_id)
                    if needs_resync:
                        self._resync()
                    for event in pending:
                        self._send_event(event)
                    while True:
                        try:
                            event = subscriber.get(timeout=KEEPALIVE_SECONDS)
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            continue
                        if event is None:
                            self._resync()
                            return
                        self._send_event(event)
                finally:
                    bus.unsubscribe(subscriber)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        def _resync(self) -> None:
            self.wfile.write(b"event: resync\ndata: {}\n\n")
            self.wfile.flush()

        def _send_event(self, event: Event) -> None:
            body = json.dumps(event.payload, ensure_ascii=False)
            self.wfile.write(f"id: {event.id}\nevent: {event.kind}\ndata: {body}\n\n".encode("utf-8"))
            self.wfile.flush()

    return Handler


def serve(root: Path, host: str = "127.0.0.1", port: int = 8123, *, open_browser: bool = True) -> int:
    root = Path(root).resolve()
    bus = EventBus()
    server = _Server((host, port), make_handler(root, bus))
    watcher = Watcher(root=root, bus=bus)
    watcher.start()
    url = f"http://{host}:{port}/"
    print(f"slc serve: {url}（项目根 {root}）", flush=True)
    if open_browser:
        import webbrowser

        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        server.server_close()
    return 0
