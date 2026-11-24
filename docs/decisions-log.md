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
  P5 实测构建 **JS 983.58 kB（gzip 325.31 kB）**、CSS 22.13 kB（gzip 4.16 kB），增量来自 SSE/布局模块。
  P6 收尾实测 **JS 983.87 kB（gzip 325.43 kB）**、CSS 22.13 kB（gzip 4.16 kB），与 P5 基本持平；未做 code-split，理由见 [PERF.md](PERF.md)。

## P5

### D22 服务端实现：stdlib HTTP + 轮询 watcher

- 决策：`server.py` 使用标准库 `ThreadingHTTPServer` + SSE 手写流，watcher 用 200 ms 轮询 mtime/sha256 + 400 ms 去抖；不引入 ASGI/FastAPI 运行时，也不使用 `watchdog` 事件线程。
- 理由：P5 契约（端点、事件、补发/resync）与实现无关；stdlib 方案无线程生命周期泄漏、Windows 文件通知差异与额外测试依赖，单测可直接起本地端口验证。`fastapi/uvicorn/watchdog` 仍在 P0 依赖清单中，后续若要换实现不影响对外契约。
- 影响：`py/rvgen/server.py`、`tests/unit/test_server_sse.py`。
- 状态：已收口（如需 ASGI 化，另开阶段）。

### D23 布局持久化键与合并口径

- 决策：前端固定使用 `localStorage["rvgen:layout:v1"]`，按 node id 合并；live 模式下拖动同时 `POST /api/layout` 写入项目根 `layout.json`。重载（应用内或浏览器刷新）只按 id 覆盖坐标，不重建视图偏好。
- 理由：若按 `source_digest` 分键，YAML 任何改动都会丢坐标，违背“重载保留坐标”的验收；`layout.json` 与 localStorage 双写保证 `serve` 与静态演示一致。
- 影响：`web/src/lib/layout.ts`、`web/src/App.tsx`、`web/src/views/DataflowView.tsx`。
- 状态：已收口。

### D24 事件与端点的最小集合

- 决策：只发 `yaml_changed` / `graph_changed` / `summary_changed` / `git_state` / `resync`；不实现 `check_result`、`rtl_changed`（服务端不跑 check、不监听 RTL）；`POST /api/reload` 仅回读当前图，无副作用、不发事件。
- 理由：`check_result` 需要服务端常驻 check 运行器，`rtl_changed` 在无 check 模式下会制造噪声；手动重载按 §7.2 由前端 `GET /api/graph` 完成，端点保留只用于显式回读。`node_graph.json` 的变化用 `graph_changed` 表达，避免与 YAML 语义混淆。
- 影响：`py/rvgen/server.py`、`docs/WEBUI.md`。
- 状态：待 P6/后续若加入服务端 check 时补 `check_result`/`rtl_changed`。

### D25 collapsed / pinned 只持久化、不提供控件

- 决策：布局条目保留 `pinned`、`collapsed`、`control_points` 字段并在合并时原样保留，但 P5 UI 不新增折叠/钉住按钮。
- 理由：P5 验收只要求“重载保留折叠/坐标/pinned”，字段与合并语义已满足；新增交互控件超出本轮范围，且会牵动节点渲染与边重算。
- 影响：`web/src/lib/layout.ts`。
- 状态：待后续 UI 迭代收口。

### D26 rvgen:// 拉起与兜底

- 决策：详情抽屉新增“在编辑器中打开”，点击即尝试 `window.location.href = rvgen://…`，同时把 URI 复制到剪贴板并提示“若未响应，已复制”；保存原复制按钮。三平台注册脚本只给脚本，不自动执行。
- 理由：浏览器无法可靠检测自定义协议是否被处理，静默失败不可接受；Windows 脚本本机可验证，macOS/Linux 脚本按平台标准做法编写但**未实机验证**。
- 影响：`web/src/lib/rvopen.ts`、`web/src/panels/DetailDrawer.tsx`、`scripts/*`、`docs/WEBUI.md`。
- 状态：Windows 已收口；macOS/Linux 脚本待实机验证。

## P6

### D27 `check` 语义 diff 与 `--fix` 未实现

- 决策：P6 不补 `check --fix`，也不补“手改图逐字段 diff → 退出 1”。`check` 维持 schema lint + 语义规则重算 + `generated_by` 的 `W10`；`sync --check` 负责生成物落后（E15）。
- 理由：逐字段 diff 与 `--fix` 的修图语义（哪些字段可由 YAML 覆盖、哪些是人工意图）文档没有定论；P2 已记为 D10 待收口。P6 范围是硬化与交付，补实现会越过“范围之外不写”的约束。
- 影响：AC06 ❌、AC12 的 grep 口径、HANDOVER 第 7 节。
- 状态：**已收口**（D36 补齐）。

### D36 AC06 收口：语义 diff + `check --fix`

- 决策：`check` 对期望图与 `node_graph.json` 做逐字段 diff，差异报 `E16`，路径按 `nodes.<id>.ports.<port>.<field>` 生成，最多 20 条；忽略 `generated_by`（仍走 `W10`）与 `source_digest`（注释/格式变化不产生语义噪声）。
- `--fix`：先按 loader + graph 顺序校验，全部通过后才原子重写 `node_graph.json`，再跑一次 check；schema/规则错误时**不写**。
- 理由：AC06 要求退出 1、点号路径、hint 与 `--fix`；用户本轮明确把 AC06 纳入范围。
- 影响：`py/rvgen/checker.py`、`tests/checker/test_check_lint.py`、`tests/fixtures/schema/valid/node_graph.json`（改为真实生成的期望图）。
- 状态：已收口；验收 AC06 = ✅。

### D37 AC02/AC09/AC11 收口：四个 CLI 接线

- 决策：`init` 用内置 preset（minimal/uart/rv32i）写 YAML 后直接 `load → graph → emit → write`；`import` 调 `importer.import_verilog` 并输出 YAML；`gen cdc` 生成 `CDC_MODULES` 五个模块（WIDTH=1）；`gen fuse-soc` 生成 CAPI=2 `.core`（fileset/参数/default target）。
- 理由：用户本轮明确要求“接线到库内已有能力”；`.core` 只做文件列表与参数，不自研构建系统。
- 影响：`py/rvgen/cli.py`、`py/rvgen/init_presets.py`、`py/rvgen/fusesoc.py`、`tests/unit/test_cli_init_import_gen.py`。
- 状态：已收口；AC02/AC09/AC11 = ✅。

### D38 `import` 保留参数化位宽

- 决策：`_width_of` 对 `[WIDTH-1:0]` 返回 `"WIDTH"`，对纯数字仍返回整数；`[A-1:0]` 之外的非常量范围原样返回 `"msb:lsb"`。
- 理由：AC09 明确要求“参数化位宽也正确”；原实现直接丢弃 → `rvgen.yaml` 缺 `width`，与声明不符。
- 影响：`py/rvgen/importer.py`、`tests/unit/test_importer.py`。
- 状态：已收口；已知边界：复杂表达式（如 `2*W-1:0`）原样输出，是否可被 loader 解析由 schema 决定，不在 import 阶段展开。

### D39 AC08/AC14 收口：rv32i 样例与 CPU flavor

- 决策：`examples/rv32i` 由 `init --preset rv32i` 生成并提交生成物；trace 样例用 `schema=cpu`，已声明键进 `p_cpu`。
- 同时把模块的 `x-*` 扩展字段透传到图节点：否则前端流水线视图拿不到 `x-cpu-stage`，AC08 的“流水线视图只在 rv32i 出现”不成立。
- 理由：plugin 字段是图契约的一部分；只透传 `x-` 前缀，核心仍不解释。
- 影响：`py/rvgen/graph.py`、`tests/unit/test_graph.py`、`examples/rv32i/*`。
- 状态：已收口；AC08/AC14 = ✅。未做：真实 RTL 仿真 trace（样例为手工 TSV），`trace summary` 的 `flavor` 仍写 `core`。

### D28 迁移首例：`axi → handshake`

- 决策：`1.0.0 → 1.1.0` 迁移中，模块 `x-cpu-*` 外的 `axi` 接口/端口统一映射为 `handshake`，同时删除 `profiles`、`stage/stage_index → x-cpu-stage/x-cpu-stage_index`。
- 理由：`axi` 在 1.0.0 样例中只表示“握手通道”，不是完整 AXI 协议；映射到内置 `handshake` 是语义最小改动。完整 AXI 仍走接口库 `axi4lite`。
- 影响：`py/rvgen/migrate.py`、`tests/migration/fixtures/v1.0.0.yaml`、AC 表未涉及。
- 状态：已收口；如后续出现真实 AXI 字段，另加 step 而不是改本步。

### D29 变异测试只在 Linux nightly 跑

- 决策：`mutmut` 依赖 `fork`，Windows 不可用；本机只验证 `scripts/mutation_score.py` 的解析/门槛（3 个单测），真实变异交给 `.github/workflows/nightly.yml`。
- 理由：不为 Windows 改测试架构；变异是夜间质量信号，不阻塞本地提交。
- 影响：`pyproject.toml [tool.mutmut]`、nightly、TESTING。
- 状态：已收口（Linux 首跑数据待 CI 产出）。

### D30 离线 npm 缓存为空

- 决策：仓库只保留 `vendor/npm/.gitkeep`，不提交 tgz；AC01 的“全新 clone 离线 npm ci”降级为 ⚠️。
- 理由：把 node_modules 依赖打进 git 体积不可接受；`scripts/npm-offline.*` 的用途是从已装环境回填缓存，首次仍需联网。
- 影响：AC01、README 安装说明。
- 状态：**未收口**；若需真正离线，另开 vendor tgz 提交策略。

### D31 plugin 节点类型统一为 `p_cpu:cache_node`

- 决策：`plugins/cpu/plugin.py` 的 `node_types` 从 `p_cpu:cache_state_node` 改为 `p_cpu:cache_node`，与 `schema/node_graph.schema.json`、前端样例、`test_plugins` 一致。
- 理由：P5 前端按 `p_cpu:cache_node` 渲染；注册名不一致会让 `plugin list` 与图契约脱节，且 AC19 无法成立。
- 影响：`plugins/cpu/plugin.py`。
- 状态：已收口。

### D32 AC12 的 grep 命中 CLI 预设名

- 决策：保留 `rvgen init --preset rv32i`（方案 §7.1 明确列出），接受 AC12 的 `grep -rnE "is_cpu|rv32i|..." py/rvgen/` 命中 1 处；AC12 记为 ⚠️。
- 理由：该字符串是 CLI 样例域名称，不是核心逻辑分支；删掉会与方案 §7.1 冲突。schema 白名单测试（`test_core_whitelist.py`）全绿，核心边界仍成立。
- 影响：AC12、NOT_IN_SCOPE。
- 状态：**口径已记录**；若用户要求 grep 零命中，需把 preset 改名并同步方案。

### D33 工具版本升到 1.0.0

- 决策：`py/rvgen/__init__.py` 从 `0.1.0` 升到 `1.0.0`，同步 golden/fixtures/示例生成物与 `test_cli_skeleton`；tag 打 `v1.0.0`。
- 理由：P6 退出标准要求工具版本 `v1.0.0`；tag 与 `--version` 不一致会让 `generated_by` 与 `W10` 失真。
- 影响：`__init__.py`、`tests/golden/node_graph.json`、`tests/fixtures/schema/valid/node_graph.json`、`web/public/sample/*.json`、`web/src/test/fixtures.ts`、`web/e2e/perf-500.spec.ts`、`examples/uart/*`。
- 状态：已收口（重新生成后 `graph --write`、`sync`、`sync --check`、`check --strict` 均 0，iverilog 0）。

### D34 文档与 AC 的诚实标注

- 决策：30 条验收逐条标注 ✅/⚠️/❌，不为“全绿”改测试或删条目；未实现的能力同时写入 HANDOVER 第 7 节与 NOT_IN_SCOPE 第 2 节。
- 理由：交付物必须让接手者一眼看到真实边界；把缺口藏在通过率里是更坏的交付。
- 影响：`docs/ACCEPTANCE.md`、`docs/HANDOVER.md`、`docs/NOT_IN_SCOPE.md`。
- 状态：已收口。

### D35 性能数字与复现口径

- 决策：PERF 只记录本机可复现命令与同机数字：1M 行归一化 6.50 s、500 节点 p95 60.2 FPS、构建 983.87 kB / gzip 325.43 kB；不把数字写成 SLA。
- 理由：换机器即变；门槛（25 s / 30 FPS / 80% 变异）才是契约。
- 影响：`docs/PERF.md`、ADR-06、D21。
- 状态：已收口。
