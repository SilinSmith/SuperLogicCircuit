# rvgen Web 看板（P3–P5）

> P5 起由 `rvgen serve` 托管：静态产物 + `/api/graph` + SSE 事件流 + 布局持久化。
> 前端始终只读受控资产；源文件变化只提示“有更新”，由用户手动重载（方案 §7.2）。

## 运行

```powershell
rvgen serve                      # 默认 127.0.0.1:8123，自动打开浏览器
rvgen serve --no-open            # CI/脚本用；不启动浏览器
rvgen serve --project examples/rv32i --port 8124
```

- 先把前端产物放到 `web/dist`（`cd web && npm run build`）；`serve` 直接托管它。
- `serve` 读取项目根的 `node_graph.json` / `trace_summary.json` / `layout.json`，**永不写** `node_graph.json` 或 `rvgen.yaml`。
- 端口被占用时退出码 **3**（E00，IO/环境类）。

开发模式：

```powershell
cd web
npm install
npm run dev          # http://127.0.0.1:5174，/api 代理到 8123
```

- dev 固定 5174（`strictPort`），避开旧工程 5173；`/api/*` → `http://127.0.0.1:8123`。
- 数据源选择：`serve` 托管（端口 8123）或 `?live=1` → `/api/graph`；否则读 `/sample/node_graph.json`。
  `?graph=<url>` 始终优先，`?live=0` 可强制回退样例。
- 动态指标：live 时 `/api/trace-summary`，否则 `/sample/trace_summary.json`；`?summary=` 可覆盖；404 只降级为静态统计。

```powershell
npm run typecheck
npm run test:unit
npm run test:e2e     # load-json / drag-node / offline / reload-keeps-layout / views
$env:PERF='1'; npx playwright test e2e/perf-500.spec.ts
npm run build
```

## HTTP API（§7.2）

| 方法与路径 | 行为 |
|---|---|
| `GET /api/graph` | 返回项目根 `node_graph.json`；不存在 → 404（不合成默认图） |
| `GET /api/trace-summary` | 返回 `trace_summary.json`；不存在 → 404（前端降级） |
| `GET /api/layout` | 返回 `layout.json`；不存在 → `{}` |
| `POST /api/layout` | 按节点 id 深度合并后原子写回 `layout.json`，返回合并结果 |
| `GET /api/health` | `{ok, service, version, project, subscribers}` |
| `POST /api/reload` | 回读当前 `node_graph.json`；无副作用、不发事件 |
| `GET /api/events` | SSE 事件流；支持 `Last-Event-ID` 头与 `?last_id=` |

静态资源：`GET /` 与其余路径从 `web/dist` 读取；无 dist 时返回 JSON 提示。

## SSE 事件

| event | data | 触发 |
|---|---|---|
| `yaml_changed` | `{path, sha256, at, mtime}` | `rvgen.yaml` 内容变化 |
| `graph_changed` | 同上 | `node_graph.json` 被显式改写（`graph --write`） |
| `summary_changed` | 同上 | `trace_summary.json` 变化 |
| `git_state` | `{branch, head, dirty, counts, at}` | `.rvgen/.git-event` 被 hook 触碰 |
| `resync` | `{}` | `Last-Event-ID` 已滑出 64 条环形缓冲，或客户端队列积压被丢弃 |

- watcher 轮询 200 ms，内容稳定 400 ms 后才发一条；同一内容不重复发。
- 每客户端队列 128 条；写满即断开并让客户端重连，靠 `Last-Event-ID` 补发或 `resync` 全量重拉。
- 服务端不改写、不重排；前端收到任一变化只累加“有更新（N）”，点击后才 `GET /api/graph`，视口与坐标不重置。

## 布局与坐标

- 拖动节点写入 `localStorage["rvgen:layout:v1"]`，按 **node id** 合并；浏览器刷新后坐标恢复。
- live 模式下同时 `POST /api/layout` 持久化到项目根 `layout.json`（不进 git）。
- 图中消失的节点移入 `_stale` 保留 30 天；`pinned` / `collapsed` / `control_points` 字段随条目原样保留（UI 暂未提供折叠/钉住控件，见 decisions-log D25）。

## `rvgen://` 与 git hooks

```powershell
# Windows（当前用户，无需管理员）
powershell -ExecutionPolicy Bypass -File scripts/register-rvopen-windows.ps1
# macOS / Linux
sh scripts/register-rvopen-macos.sh
sh scripts/register-rvopen-linux.sh

sh scripts/install-hooks.sh        # 安装 post-commit / post-checkout
```

- 处理器 `scripts/rvopen-handler.{ps1,sh}` 优先 `code --goto file:line`，其余用系统默认程序；失败时打印手动命令。
- hook 在 commit / 分支 checkout 后跑 `rvgen check --quiet` 并触碰 `.rvgen/.git-event`，`serve` 随即推送 `git_state`；**绝不自动改写工作区**。
- `pre-commit` 门禁示例见仓库根 `.pre-commit-config.yaml`（`rvgen check` + `rvgen sync --check`）。

## 视图与交互

| 能力 | 行为 |
|---|---|
| 数据流视图 | dagre LR 布局；只显示模块/统计/plugin 节点与 data/handshake/bundle/param 边；时钟树与 CDC 不在本视图 |
| 时钟树视图 | 确定性 BFS 径向布局（不引入 elkjs）；根为无入边时钟节点 |
| 统计视图 | ECharts 柱状图：边带宽 bit/cycle、节点利用率（有 summary 时）或类型分布 |
| plugin 视图 | `plugins/cpu` 注册流水线时空图与 Cache；仅当图含 `x-cpu-stage` 或 `p_cpu:*` 节点时出现 |
| 节点/边 | 端口表 + 带宽徽标；critical 边标红，时钟/复位/CDC 虚线 |
| 详情抽屉 | 端口表、`file:line`；`rvgen://` 尝试拉起编辑器并始终复制 URI 兜底 |
| live 徽标 | 连接成功显示“实时”；断线显示“连接中”，EventSource 自动重连 |

## 当前边界（与方案一致的未收口项）

- 折叠 / pinned 字段已持久化但 UI 未提供控件（D25）。
- 三平台注册脚本中，仅 Windows 在本机实测；macOS/Linux 未实机验证。
- `check_result` / `rtl_changed` 事件未由服务端主动发出（无内置 check 运行器，D24）。
- 静态样例与 `tests/golden/node_graph.json` 内容一致，仅用于离线演示与 e2e。
