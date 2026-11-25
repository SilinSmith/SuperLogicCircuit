from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest

from slc.server import EventBus, Watcher, _Server, make_handler, merge_layout


@pytest.fixture
def live_server(tmp_path: Path):
    (tmp_path / "node_graph.json").write_text('{"schema_version": "1.0.0"}', encoding="utf-8")
    bus = EventBus()
    server = _Server(("127.0.0.1", 0), make_handler(tmp_path, bus))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], bus, tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(port: int, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes, dict[str, str]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
    response = connection.getresponse()
    payload = response.read()
    headers = dict(response.getheaders())
    connection.close()
    return response.status, payload, headers


def _read_sse(response) -> tuple[str | None, dict[str, str]]:
    event: str | None = None
    data: dict[str, str] = {}
    while True:
        line = response.fp.readline()
        if not line:
            return event, data
        text = line.decode("utf-8").rstrip("\r\n")
        if text == "":
            # `retry:` 前后的空行是流前言，不应作为事件结束。
            if event is not None or data:
                return event, data
            continue
        if text.startswith("event: "):
            event = text[len("event: ") :]
        elif text.startswith("data: "):
            data["body"] = text[len("data: ") :]
        elif text.startswith("id: "):
            data["id"] = text[len("id: ") :]


def test_event_bus_replay_returns_events_after_last_id():
    bus = EventBus()
    first = bus.publish("yaml_changed", {"path": "slc.yaml"})
    second = bus.publish("graph_changed", {"path": "node_graph.json"})
    assert first.id == 1 and second.id == 2
    replayed, resync = bus.replay(1)
    assert resync is False
    assert [event.id for event in replayed] == [2]
    assert bus.replay(None) == ([], False)


def test_event_bus_resync_when_last_id_evicted():
    bus = EventBus(capacity=2)
    for index in range(3):
        bus.publish("yaml_changed", {"n": index})
    assert bus.replay(0) == ([], True)
    replayed, resync = bus.replay(1)
    assert resync is False
    assert [event.id for event in replayed] == [2, 3]
    assert bus.replay(2)[1] is False


def test_event_bus_slow_subscriber_is_dropped_and_flagged():
    bus = EventBus()
    subscriber = bus.subscribe(maxsize=1)
    bus.publish("yaml_changed", {"n": 1})
    bus.publish("yaml_changed", {"n": 2})
    assert bus.subscriber_count() == 0
    assert subscriber.get_nowait() is None


def _manual_clock(start: float = 0.0):
    now = {"value": start}
    return now, lambda: now["value"]


def _touch(path: Path, when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("changed", encoding="utf-8")
    ns = int(when * 1_000_000_000)
    import os

    os.utime(path, ns=(ns, ns))


def test_watcher_debounce_publishes_once(tmp_path: Path):
    bus = EventBus()
    now, clock = _manual_clock()
    watcher = Watcher(root=tmp_path, bus=bus, debounce=0.4, clock=clock)
    _touch(tmp_path / "slc.yaml", 1.0)
    assert watcher.poll_once() == []

    _touch(tmp_path / "slc.yaml", 2.0)
    now["value"] = 2.0
    assert watcher.poll_once() == []

    now["value"] = 2.2
    assert watcher.poll_once() == []

    now["value"] = 2.45
    events = watcher.poll_once()
    assert [event.kind for event in events] == ["yaml_changed"]
    assert events[0].payload["path"] == "slc.yaml"
    assert events[0].payload["sha256"]

    now["value"] = 3.0
    assert watcher.poll_once() == []


def test_watcher_git_event_publishes_git_state(tmp_path: Path):
    bus = EventBus()
    now, clock = _manual_clock()
    watcher = Watcher(root=tmp_path, bus=bus, debounce=0.4, clock=clock)
    _touch(tmp_path / ".slc" / ".git-event", 1.0)
    watcher.poll_once()

    _touch(tmp_path / ".slc" / ".git-event", 2.0)
    now["value"] = 2.0
    watcher.poll_once()
    now["value"] = 2.5
    events = watcher.poll_once()
    assert [event.kind for event in events] == ["git_state"]
    assert "at" in events[0].payload


def test_merge_layout_merges_nested_entries():
    base = {"nodes": {"mod:a": {"x": 1, "y": 2, "pinned": True}}, "version": 1}
    incoming = {"nodes": {"mod:a": {"y": 9}, "mod:b": {"x": 3, "y": 4}}}
    merged = merge_layout(base, incoming)
    assert merged["nodes"]["mod:a"] == {"x": 1, "y": 9, "pinned": True}
    assert merged["nodes"]["mod:b"] == {"x": 3, "y": 4}
    assert merged["version"] == 1


def test_health_and_graph_endpoints(live_server):
    port, _bus, _root = live_server
    status, body, _headers = _request(port, "GET", "/api/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["service"] == "slc"

    status, body, _headers = _request(port, "GET", "/api/graph")
    assert status == 200
    assert json.loads(body)["schema_version"] == "1.0.0"

    status, _body, _headers = _request(port, "GET", "/api/trace-summary")
    assert status == 404


def test_layout_post_merges_and_persists(live_server):
    port, _bus, root = live_server
    status, body, _headers = _request(
        port, "POST", "/api/layout", json.dumps({"nodes": {"mod:a": {"x": 1, "y": 2}}}).encode()
    )
    assert status == 200
    status, body, _headers = _request(
        port, "POST", "/api/layout", json.dumps({"nodes": {"mod:a": {"y": 8}}}).encode()
    )
    assert status == 200
    assert json.loads(body)["nodes"]["mod:a"] == {"x": 1, "y": 8}
    stored = json.loads((root / "layout.json").read_text(encoding="utf-8"))
    assert stored["nodes"]["mod:a"] == {"x": 1, "y": 8}

    status, body, _headers = _request(port, "GET", "/api/layout")
    assert status == 200
    assert json.loads(body)["nodes"]["mod:a"]["x"] == 1


def test_sse_replays_after_last_event_id(live_server):
    port, bus, _root = live_server
    bus.publish("yaml_changed", {"path": "slc.yaml"})
    bus.publish("graph_changed", {"path": "node_graph.json"})

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", "/api/events?last_id=1")
    response = connection.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/event-stream"
    try:
        event, data = _read_sse(response)
        assert event == "graph_changed"
        assert data["id"] == "2"
        assert json.loads(data["body"])["path"] == "node_graph.json"
    finally:
        connection.close()


def test_sse_sends_resync_when_last_id_evicted(live_server):
    port, bus, _root = live_server
    for index in range(65):
        bus.publish("yaml_changed", {"n": index})

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", "/api/events?last_id=0")
    response = connection.getresponse()
    try:
        event, data = _read_sse(response)
        assert event == "resync"
        assert data["body"] == "{}"
    finally:
        connection.close()


def test_reload_endpoint_reads_graph_without_side_effects(live_server):
    port, bus, _root = live_server
    status, body, _headers = _request(port, "POST", "/api/reload")
    assert status == 200
    assert json.loads(body)["schema_version"] == "1.0.0"
    assert bus.replay(None) == ([], False)
