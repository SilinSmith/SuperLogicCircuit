# ADR-06 前端框架与布局库选型（P3）

> 状态：已采纳；日期：2026-11-25；适用阶段：P3 起。
> 依据：`slc完整方案.md` 第 2 章与第 15 章。本 ADR 只记录 P3 实际落地的选择与核对结果。

## 决策

| 项 | 决策 |
|---|---|
| 框架 | React 19.3.1 + TypeScript 5.9.3 + Vite 7.3.8 |
| 节点编辑器 | `@xyflow/react` 12.12.1（MIT） |
| 默认布局 | `dagre` 0.8.5（MIT），同步计算，数据流视图方向 LR |
| 布局候选 | `elkjs` 暂不安装；时钟树/精细布局在 P4 评估，届时按需引入并放入 Web Worker |
| 状态 | React Flow 受控模式（`useNodesState` / `useEdgesState`），拖拽只改前端坐标 |
| 数据源 | 只读 `node_graph.json` 契约；P3 用 `/sample/node_graph.json`，`?graph=` 可覆盖；P5 起默认 `/api/graph` |
| 端口 | dev/preview **5174**；`/api` 代理到 `slc serve` 的 **8123** |

## v11 → v12 迁移核对（按 12.12.1 类型与实际编译验证）

1. 包名 `reactflow` → `@xyflow/react`，样式路径 `@xyflow/react/dist/style.css`。
2. `defaultPosition` / `defaultZoom` 等默认视口 prop 统一为 `defaultViewport`；本 ADR 的实现改用 `fitView`，不受影响。
3. `NodeProps` / `EdgeProps` 均为泛型：`NodeProps<Node<Data, Type>>`、`EdgeProps<Edge<Data, Type>>`；自定义组件按此标注，类型检查通过。
4. 自定义边使用 `BaseEdge` + `EdgeLabelRenderer`（标签 portal 到画布容器），边几何用 `getBezierPath`。
5. 受控模式必须同时提供 `nodes` 与 `onNodesChange`，否则拖拽不会生效（P3 e2e 曾复现此问题，已修复）。
6. 节点尺寸由 `width` / `height` 显式给出，避免首帧测量抖动；`onlyRenderVisibleElements` 在容器尺寸可用后开启。
7. `parentNode` 等 v11 字段未使用；本项目未涉及子节点/分组。

## React 19 兼容性

- `npm ls react` 仅一份 React 19.3.1；`@xyflow/react` 12.12.1 在 Playwright Chromium 下完成 load/drag 冒烟。
- 未降级 React 18；若后续 plugin 依赖冲突，按方案要求在本 ADR 追加记录，不允许静默悬空。

## 体积与性能（实测）

| 指标 | 实测值 | 依据 |
|---|---|---|
| `npm run build` JS | 513.59 kB（gzip 167.38 kB，sourcemap 2.41 MB） | Vite 7.3.8 构建输出 |
| CSS | 20.43 kB（gzip 3.83 kB） | 同上 |
| 500 节点拖动帧 p95 | **60.2 FPS**（59 帧样本） | `PERF=1 npx playwright test e2e/perf-500.spec.ts` |

体积不设硬门槛（方案 P3 口径），数值随报告提交。

## P4 追加：三视图与图表库

- **时钟树**：采用确定性 BFS 径向布局（`web/src/lib/radial.ts`），不引入 elkjs。理由：时钟树节点规模小；elkjs 为 EPL-2.0/GPL-3.0 双许可、约 8 MB，且要求异步 Worker 生命周期。数据仍完全来自 `node_graph.json` 的 clock/cdc 边，后续替换布局算法不影响契约。详见 D17。
- **统计**：`echarts` 5.6.0（Apache-2.0），仅经 `echarts/core` 注册 BarChart/Grid/Tooltip/CanvasRenderer；`EChart` 组件在卸载时 `dispose()` 并断开 ResizeObserver（单测覆盖）。
- **插件视图**：`plugins/cpu` 注册流水线时空图与 Cache 视图；仅当图出现 `x-cpu-stage` 或 `p_cpu:*` 节点时显示，通用图（如 UART golden）不出现（e2e 覆盖）。
- **构建体积（P4）**：JS 980.16 kB（gzip 323.94 kB，map 5.03 MB），CSS 21.88 kB（gzip 4.10 kB）。ECharts 使体积翻倍，仍在单页应用可接受范围；若后续视图继续增长，按视图动态 import。

## P5 追加：实时提示与布局持久化

- **事件流**：`EventSource` 订阅 `/api/events`；只累加“有更新（N）”徽标，点击才重新拉图，绝不自动覆写视图。断线由 EventSource 自动重连并携带 `Last-Event-ID`，服务端补发或发 `resync`。
- **布局**：`localStorage["slc:layout:v1"]` 按 node id 合并坐标，重载与浏览器刷新均保留；live 时同步 `POST /api/layout` 写 `layout.json`（不进 git）。`pinned`/`collapsed` 字段已保留，UI 控件待后续（D25）。
- **数据源**：serve 托管或 `?live=1` 用 `/api/graph`、`/api/trace-summary`；其余场景保持静态样例，e2e 不依赖后端。
- **构建体积（P5）**：JS 983.58 kB（gzip 325.31 kB），CSS 22.13 kB（gzip 4.16 kB）。
- **e2e**：新增 `offline.spec.ts`（数据源不可达→错误→恢复后重试）与 `reload-keeps-layout.spec.ts`（应用内重载 / 浏览器刷新后坐标保持）。

## 被否方案

- 自研 Canvas/SVG 看板：重复实现拖拽/缩放/吸附/无障碍，维护成本高（方案 2.3）。
- 前端直接消费 YAML：schema 变更会同时打穿两端，必须有 `node_graph.json` 隔离层。
- Cytoscape.js 作为主编辑器：布局生态强但表单化节点交互弱，保留为布局候选。
