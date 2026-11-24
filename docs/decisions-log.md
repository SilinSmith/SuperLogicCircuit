# rvgen 决策与偏差记录

按阶段追加。每条记录：决策、理由、影响范围、是否需要后续收口。
遵守既定口径：core 分层、退出码 0/1/2/3、trace 静态列、显式更新图、命名小写。

## P1

### D1 `schema_version` minor 加载

- 决策：major 必须为 1；任何非 `1.1.0` 的 1.x 版本按 `1.1.0` 校验并报 I02，同时保留原版本到 `model.schema_version`。
- 理由：同时满足 §4.1 的 `const` 与 §4.5 的 minor 前向加载。
- 状态：已收口。

### D2 AC12 与 kind 开放

- 决策：`modules[].kind` 保持自由字符串；core 只校验 `module/bridge/memory/clock_gen` 四类，plugin kind 由已启用 plugin 的 `kinds` 注册表校验。
- 理由：schema 需要允许 plugin 领域 kind，同时 core 不能认识领域概念。
- 状态：已收口。

### D3 命名收紧（v1.2）

- 决策：`project.top`、`project.reset.name`、clocks/`domain_id`/`parent`、`cdc.id`、interfaces 及 signals、`modules[].name`、`ports[].name`、模块接口实例名、`top.ports[].name` 必须匹配 `^[a-z][a-z0-9_]*$`，在 loader/`validate_semantic` 阶段报 E09；`params[].name` 允许大写（Verilog 惯例）。
- 理由：用户拍板“收紧 YAML”，node_graph 契约不变；参数名大写是既有样例与 Verilog 习惯，不纳入收紧。
- 状态：已收口（参数名例外保留）。

### D4 `graph --check` / `--accept-wiring` / `--list-cdc`

- 决策：P1 只实现 `graph --write`，其余返回 E00 且消息含“尚未实现”。
- 理由：文档未定义这三个子模式在 P1 的诊断码与 `stats_node` 语义。
- 状态：待后续阶段收口。

### D5 E10/E11 未在 P1 实现

- 决策：E10（frozen 覆写保护）留到 P2；E11（trace 列/Ext 校验）留到 P4。
- 理由：§9 的 P1 规则码列表与阶段定义冲突；提前实现会引入 P2/P4 代码。
- 状态：E10 已在 P2 实现；E11 待 P4。

## P2

### D6 frozen 的写与查语义

- 决策：`sync` 写模式遇到 `status: frozen` 且文件已存在时跳过并报 I03；`sync --check` 对同一文件比对生成物，落后则报 E10；`--force-unfreeze` 两侧都放行。
- 理由：既保留“绝不静默覆写 frozen”的硬约束，又让 E10 在只读检查中可用。
- 状态：已收口。

### D7 新增 E15（生成物落后）

- 决策：非 frozen 生成物在 `sync --check` 中落后时报 E15，提示运行 `rvgen sync`。
- 理由：文档没有为“生成物落后”分配核心规则码；复用 E09/E00 会误导。新增码不改变 0/1/2/3 退出码。
- 状态：已收口；如后续文档统一编号，可改名。

### D8 `sync --check` 不比较 `node_graph.json`

- 决策：`sync --check` 只比较 `rtl/` 生成物；`node_graph.json` 的新鲜度仍由 `check` 负责。
- 理由：遵循 §7.4 的职责划分。
- 状态：已收口。

### D9 CDC 基础模块的最小实现

- 决策：`sync` 在 `cdc[]` 非空时生成 `rtl/gen/cdc/<module>.v`，五种 kind 共用同一个跨域桥模板（时钟/复位 + d/q），实例名 `u_cdc_<id>`。
- 理由：P2 用户范围只点名 emitter 与生成物保护；`gen cdc` 的独立 CLI 与各 kind 的精细实现留到后续。当前模板保证顶层可例化、不引用未定义模块。
- 状态：待后续阶段替换为 kind 专属实现。

### D10 `check --fix` / `gen cdc` / `fusesoc .core` / `wiring_suggestions`

- 决策：P2 本轮不实现；`gen` 子命令仍返回 E00。
- 理由：用户本轮 P2 范围明确为 emitter、生成物保护、`sync --check` 比对、E10。
- 状态：待后续阶段（P3/P5/按需）收口。

## P3

### D11 P3 数据源与样例

- 决策：前端默认读 `/sample/node_graph.json`（`tests/golden/node_graph.json` 的只读拷贝），`?graph=<url>` 可覆盖；P5 接入 `rvgen serve` 后默认改为 `/api/graph`。
- 理由：P3 尚无服务端，但 e2e 必须能加载真实契约；静态样例与 golden 同源，避免前端自造 JSON。
- 状态：P5 收口为默认 `/api/graph`，样例保留用于离线演示。

### D12 `rvgen://` 按钮在 P3 的行为

- 决策：P3 只生成 URI 并复制到剪贴板，附“协议注册后可直接打开”提示；不尝试 `window.location` 跳转，不做全局 URI Scheme 注册。
- 理由：未注册的协议浏览器会静默失败；方案把协议注册放在 P5，P3 提前拉起会产生误导。
- 状态：待 P5 收口为直接拉起。

### D13 拖拽与布局持久化

- 决策：P3 拖拽只更新 React Flow 本地状态，不写 `node_graph.json`、不写 `layout.json`/localStorage。
- 理由：方案 A5 要求布局旁路持久化，但 `layout.json` 的合并与折叠语义属于 P4/P5；P3 只验证画布交互。
- 状态：P4/P5 接入 `layout.json`（不进 git）。

### D14 `vendor/npm` 未生成 tgz

- 决策：P3 不把前端传递依赖的 tgz 提交进 `vendor/npm`；本机以预热缓存验证 `npm ci --offline`，CI 在 vendor 为空时回退 `npm ci`。
- 理由：完整前端依赖树约数百个包（数十 MB），提交二进制 tgz 会显著膨胀仓库；功能门禁不依赖离线安装。
- 状态：待 P6 或发布前按需补齐；CI 已按“有 tgz 用离线、否则联网”自适应。

### D15 前端依赖版本对齐

- 决策：按实际可安装版本锁定 Vitest 3.2.7、Playwright 1.65.1、`dagre` 0.8.5（配 `@types/dagre`），替换文档表格中的 Vitest 2 / Playwright 1.49 / `@dagrejs/dagre`；React 19.3.1、Vite 7.3.8、`@xyflow/react` 12.12.1 与方案一致。
- 理由：主版本口径不变（React 19 / Vite 7 / xyflow 12 / TS 5）；React Flow 官方示例即用 `dagre`，避免再引入维护分支。
- 状态：已收口，`docs/DEPENDENCIES.md` 已同步实测版本与体积。

### D16 500 节点性能门禁的执行方式

- 决策：`e2e/perf-500.spec.ts` 默认跳过，`PERF=1` 时运行并断言拖拽帧 p95 ≥ 30 FPS；CI 只跑 `load-json`/`drag-node` 功能 e2e。
- 理由：无头环境帧率受宿主影响，作为常驻门禁会抖动；性能门槛按方案要求实测并记录数值。
- 状态：本机实测 **60.2 FPS**（59 帧样本），已写入 `docs/ADR/ADR-06-frontend.md`。

## P4

### D17 时钟树径向布局不引入 elkjs

- 决策：用确定性 BFS 分层 + 同心环均分角度实现径向布局（`web/src/lib/radial.ts`），不安装 elkjs。
- 理由：时钟树规模小（时钟 + CDC + 模块，通常 <50 节点），elkjs 带来 EPL-2.0/GPL 双许可、~8 MB 安装体积与异步 Worker 生命周期；自研布局可同步、可单测、无泄漏面。视图契约仍从 `node_graph.json` 的 clock/cdc 边推导，未来换 elkjs 不影响数据契约。
- 状态：已收口；ADR-06 追加记录。

### D18 plugin 视图按 x-cpu-* / p_cpu 节点激活

- 决策：核心只维护视图注册表；`plugins/cpu` 的视图在图中出现 `p_cpu:*` 节点或模块带 `x-cpu-stage` 时出现。流水线格子读取 `x-cpu-cycle` + `x-cpu-stage_index`，Cache 表读取 `p_cpu:cache_node` 与 `x-cpu-ways/x-cpu-sets`。
- 理由：核心不得认识 CPU 概念；视图显隐必须由图数据（plugin 扩展字段）驱动，而不是全局开关。
- 状态：已收口；`x-cpu-cycle` 等只是视图读取约定，校验归 plugin（P1 起 core 不解析 x-*）。

### D19 trace_summary 为可选旁路

- 决策：统计视图默认请求 `/sample/trace_summary.json`，`?summary=` 可覆盖；404/读取失败只降级为静态统计并显示提示，不影响图加载。
- 理由：方案要求 trace 指标与静态图分离且不进 git；缺失 summary 是常态而非错误。
- 状态：已收口；P5 由 serve 提供 `/api/summary` 时沿用。

### D20 trace 归一化细节（Python 侧）

- 决策：`arc` 值同时接受 `src.port>dst.port:t` 与 `src.port->dst.port:t`，统一规范化为 node_graph 的 `->` 边 id；`arc`/`cdc` 值允许 `:`、`>` 字符，其它 Ext 值仍限制 `[A-Za-z0-9_.+-]`；未声明键进 JSONL 顶层 `ext`，cpu/bus 已声明键进 `p_<flavor>`；`summary` 无 `--graph` 时只报 I08 并把 utilization 留空。
- 理由：边 id 本身含 `:`，若严格按文档字符集无法表达；未声明键必须保留（W15）而不是丢弃。
- 状态：已收口；如文档后续给出更严格文法再收紧。

### D21 ECharts 引入与打包体积

- 决策：统计视图使用 `echarts/core` 按需注册（BarChart/Grid/Tooltip/CanvasRenderer），不引入全量 `echarts`。P4 构建 JS 体积增至 980.16 kB（gzip 323.94 kB）。
- 理由：统计图表是方案明确的核心视图；按需注册已把体积压到可接受范围，暂不做路由级 code-split（单页应用，切换视图不重复下载）。
- 状态：已收口；若 P5/P6 加入更多视图导致体积失控，再按视图动态 import。
