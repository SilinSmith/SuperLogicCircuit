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
