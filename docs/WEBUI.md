# rvgen Web 看板（P3）

> P3 只交付数据流视图骨架；时钟树、统计视图、SSE 与多视图切换分别在 P4/P5 补齐。

## 运行

```powershell
cd web
npm install          # 首次
npm run dev          # http://127.0.0.1:5174
```

- dev 固定 5174（`strictPort`），避开旧工程 5173。
- `/api/*` 代理到 `http://127.0.0.1:8123`（`rvgen serve`，P5 提供）。
- 数据源默认 `/sample/node_graph.json`（golden 样例的只读拷贝）；用 `?graph=/api/graph` 或任意 JSON URL 覆盖。

```powershell
npm run typecheck
npm run test:unit    # 快照 + 泄漏检查 + 契约守卫
npm run test:e2e     # Playwright load-json / drag-node
$env:PERF='1'; npx playwright test e2e/perf-500.spec.ts   # 500 节点性能校准
npm run build        # 产物在 web/dist
```

## 数据契约

- 只读 `schema/node_graph.json` v1；前端类型镜像在 `web/contracts/node_graph.ts`，禁止 import `py/`。
- 运行期守卫只校验渲染必需字段（`schema_version`、节点 id/type/label、边端点存在性），完整语义仍由 `rvgen check` 负责。
- 带宽口径：`bits/cycle` 为权威值；`GB/s` 按十进制 1e9 换算并在 UI 标注 `(decimal)`。

## 视图与交互（P3）

| 能力 | 行为 |
|---|---|
| 数据流视图 | dagre LR 布局；只显示模块/统计/plugin 节点与 data/handshake/bundle/param 边；时钟树与 CDC 不在本视图 |
| 节点 | `ModuleNode` 展示模块名、类型、时钟域、前 8 个端口与位宽，超出折叠为 `+N` |
| 边 | `BandwidthEdge` 显示 derived/explicit 带宽；critical 边标红；时钟/复位/CDC 用虚线区分（P4 生效） |
| 拖拽 | 只修改前端坐标，不回写 `node_graph.json`；`layout.json` 持久化在 P4/P5 接入 |
| 详情抽屉 | 点击节点展示端口表、`file:line`、状态；无 `loc` 时提示 W10 |
| `rvgen://` | P3 复制 `rvgen://open?file=…&line=……` 到剪贴板；协议注册与真正拉起在 P5 |

## 当前边界（与方案一致的未收口项）

- 未知协议不会被浏览器自动拉起，因此 P3 按钮只做复制 + 提示；P5 提供三平台注册脚本后再切换为直接拉起。
- 静态样例与 `tests/golden/node_graph.json` 内容一致；P5 接入 `/api/graph` 后样例仅用于离线演示。
- 视口/折叠等偏好尚未持久化（P4/P5 写入 `layout.json`，不进 git）。
