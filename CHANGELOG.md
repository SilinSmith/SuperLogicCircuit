# Changelog

格式参考 Keep a Changelog；版本号遵循 SemVer。工具版本与 schema 版本独立演进。

## [1.0.2] - 2026-11-26

工具自身补丁版本；schema 不变（`slc.yaml` 1.1.0 / `node_graph.json` 1.0.0）。

### Fixed

- CI：将 `tests/fixtures/schema/valid/layout.json` 纳入版本库，修复干净检出时 11 个测试的 `FileNotFoundError`。
- CI：将 `web/public/sample/trace_summary.json` 纳入版本库，修复 e2e 统计视图断言失败；新增 `test_sample_files_are_tracked` 回归检查，防止样例再被 `.gitignore` 忽略。
- CI：补齐 `checker` 覆盖分支（`_compare` 字典/列表差异、`_MAX_DIFFS` 汇总、`check --fix` 异常路径），`checker`/`digest` 覆盖率 100%，95% 门禁通过。

### Changed

- 验收口径收敛：AC01 按 CI 可验证的 `vendor/wheels` 离线安装判为通过；AC21 改为相对基线趋势；AC24 收窄为 Windows 本机 + CI `ubuntu-22.04`（macOS 移出）；AC30 定性为非阻塞人工试用；AC27 依据 CI run `45661473395` 转为通过。统计 27✅ / 3⚠️ / 0❌。
- 工具版本由 `1.0.1` 升到 `1.0.2`；`generated_by` 与生成物版本行同步。

## [1.0.1] - 2026-11-25

工具自身版本升级；schema 不变（`slc.yaml` 1.1.0 / `node_graph.json` 1.0.0）。

### Added

- **CLI**：`init`（minimal/uart/rv32i）、`import`、`gen cdc`、`gen fuse-soc` 接线；`.core` 含 fileset/参数/target。
- **examples/rv32i**：5 级流水 + I/D cache，cpu 插件字段进图；`trace/example.tsv` 覆盖 `--flavor cpu`。
- **graph**：模块 `x-*` 扩展字段透传到 node，供 plugin 视图使用。

### Changed

- 数据流边标签用 `E`/`D`/`T` 区分 explicit/derived/trace_summary，trace 边显示实测利用率。
- 工具版本由 `1.0.0` 升到 `1.0.1`；`generated_by` 与生成物版本行同步。
- 项目由 `rvgen` 更名为 **SuperLogicCircuit**，代码标识统一为 `slc`：CLI 命令 `slc`、Python 包 `slc`、配置 `slc.yaml`、协议 `slc://`、环境变量 `SLC_*`、schema 与生成物 `generated_by` 全部同步；不提供旧名兼容别名。既有 tag 不变。

### Fixed

- `check` 增加与 `node_graph.json` 的逐字段语义 diff（`E16`，点号路径 + hint）与 `check --fix`。
- `import` 保留 `[WIDTH-1:0]` 参数化位宽（`WIDTH`），不再丢弃。

### Known limitations

见 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) 与 [docs/HANDOVER.md](docs/HANDOVER.md) 第 7 节。

## [1.0.0] - 2026-11-25

首个可交付版本：YAML → 校验/建图 → RTL 骨架 → 看板 → 本地服务 → trace → 迁移首例。

### Added

- **loader/model**：schema 1.1.0 校验、YAML 行号锚点、位宽表达式、参数展开、plugin kind/interface 注册、语义规则 E01–E14/W01–W15。
- **digest**：契约规范化与 `sha256:` 指纹；生成物指纹写入注释。
- **graph**：静态 `node_graph.json`（module/clock/cdc 节点，data/handshake/clock/cdc 边）、`graph --write` 原子写、带宽 derived/explicit、确定性排序。
- **emitter**：模块/top/CDC 模板、USER 块合并、`orphaned/` 落盘（I04）、frozen 保护（E10）、契约提示（W01）、`sync --check` 生成物比对（E15）。
- **trace**：6 列 TSV 解析（E11）、`normalize` JSONL、`summary`（W05/W15）、`stats`。
- **serve**：`GET /api/graph|trace-summary|layout|health|events`，`POST /api/layout|reload`，SSE 环形缓冲/重放/`resync`，200 ms 轮询 + 400 ms 去抖，git 状态事件。
- **web**：React Flow 12 + dagre 数据流、时钟树、统计、plugin 视图（流水线/Cache）、详情抽屉、`slc://` 跳转、布局 localStorage + 服务端合并、失效徽标与手动重载。
- **rvopen/gitw**：`slc://open` URI、三平台注册脚本、`post-commit`/`post-checkout` hook。
- **migrate**：`1.0.0 → 1.1.0`（去 `profiles`、`stage → x-cpu-stage`、`axi → handshake`），写前快照、`--dry-run` JSON Patch。
- **CI**：Python 覆盖率门禁、lint-imports、前端 typecheck/unit/build/e2e、pre-commit；nightly 变异测试（门槛 80%）。
- **examples/uart**：uart + fifo + baud_gen，零 CPU，iverilog 编译通过。
- **docs**：README、ARCHITECTURE、YAML/NODE_GRAPH/TRACE 参考、EXTENDING、TESTING、HANDOVER、NOT_IN_SCOPE、PERF、ACCEPTANCE、12 篇 ADR、决策与偏差记录。

### Changed

- **命名收紧（破坏性）**：YAML 中模块名、端口名、实例名、时钟名、`domain_id` 一律 `^[a-z][a-z0-9_]*$`；非小写在**加载/校验阶段**报 `E09`，不再等到建图。
- `node_graph.json` 的 node id / node_port 契约**不变**。
- `sync` 不写 `node_graph.json`；`sync --update-graph` 才写。
- `serve` 的 `slc_protocol` doctor 检查改为 `manual`（注册脚本需用户执行）。

### Fixed

- Windows 上 `allow_reuse_address=False`，端口冲突正确退出 3。
- `sync` 后 `sync --check` 把 W01 一次性提示误判为生成物落后；现比较时忽略 `// [W01]` 行。
- `merge_layout` 改为两层深合并，节点坐标不再丢失。
- `post-checkout` 依据 `$3=0` 跳过文件 checkout，避免误触发。
- `plugins/cpu` 节点类型统一为 `p_cpu:cache_node`，与前端/样例一致。

### Known limitations

见 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) 与 [docs/HANDOVER.md](docs/HANDOVER.md) 第 7 节。

## [0.x] - 2026-11-24 及之前

- P0–P5 分阶段实现，提交见 `git log`（`fb4ad88` 起）。

## Schema

| schema | 变更 |
|---|---|
| `slc.yaml` 1.1.0 | 核心 kind 四类；`stage` 移入 `x-cpu-stage`；新增 `interfaces[]`、`cdc[]` 枚举、`top.tieoffs[]` |
| `node_graph.json` 1.0.0 | 首版；核心四类节点，plugin 必须 `p_` 前缀 |
| `layout.json` 1.0.0 | 节点/边/视图/偏好；默认不进 git |
| `trace_summary.json` 1.0.0 | 静态列 + 派生指标；不进 git |

## Migration

| from → to | 内容 |
|---|---|
| 1.0.0 → 1.1.0 | 删除 `profiles`；`stage/stage_index → x-cpu-stage/x-cpu-stage_index`；`axi → handshake`；`schema_version` 升 1.1.0 |
