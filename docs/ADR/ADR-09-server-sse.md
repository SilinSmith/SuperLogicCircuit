# ADR-09 本地服务：stdlib HTTP + SSE + 轮询 watcher

> 状态：已采纳；日期：2026-11-25；适用阶段：P5 起。
> 依据：`slc完整方案.md` §7.2；决策记录 D22/D24。

## 决策

| 项 | 决策 |
|---|---|
| HTTP | `http.server.ThreadingHTTPServer`，无 ASGI 运行时依赖 |
| 推送 | SSE：`GET /api/events`；事件 `yaml_changed` / `graph_changed` / `summary_changed` / `git_state` / `resync` |
| 缓冲 | 环形 64 条；每订阅者队列 128；慢客户端丢弃并收到 `resync` |
| 重放 | `Last-Event-ID` 在缓冲内按序补发；过旧则 `resync` |
| 监听 | 200 ms 轮询 + 400 ms 去抖 + sha256 去重 |
| 端点 | `GET /api/graph|trace-summary|layout|health|events`；`POST /api/layout|reload` |
| 只读性 | `POST /api/reload` 只回读，无副作用、不发事件；服务永不写 `node_graph.json` |
| Windows | `allow_reuse_address=False`，否则重复绑定不会报端口冲突 |

## 理由

契约（端点/事件/补发）与实现无关；stdlib 方案无线程生命周期泄漏，单测可直接起本地端口。SSE 比 WebSocket 简单，断线由浏览器自动重连。

## 后果

- 前端只在收到 `yaml_changed` 时显示“源已变更”，**不自动重载**，用户点按钮才 `GET /api/graph`。
- 服务端不跑 `check`，因此没有 `check_result`/`rtl_changed` 事件。
- 端口占用时 `serve` 返回 3；macOS/Linux 的地址复用行为需在实机再确认。

## 替代方案

- FastAPI/uvicorn：否决，P5 不需要异步框架，且增加运行时依赖。
- `watchdog` 事件线程：否决，Windows 文件通知差异大，轮询更可测。
