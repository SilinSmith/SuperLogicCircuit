# Changelog

格式参考 Keep a Changelog；版本号遵循 SemVer。工具版本与 schema 版本独立演进。

## [1.0.0] - 2026-11-25

首个可交付版本：YAML → 校验/建图 → RTL 骨架 → 看板 → 本地服务 → trace → 迁移首例。

### Added

- **loader/model**：schema 1.1.0 校验、YAML 行号锚点、位宽表达式、参数展开、plugin kind/interface 注册、语义规则 E01–E14/W01–W15。
- **digest**：契约规范化与 `sha256:` 指纹；生成物指纹写入注释。
- **graph**：静态 `node_graph.json`（module/clock/cdc 节点，data/handshake/clock/cdc 边）、`graph --write` 原子写、带宽 derived/explicit、确定性排序。
- **emitter**：模块/top/CDC 模板、USER 块合并、`orphaned/` 落盘（I04）、frozen 保护（E10）、契约提示（W01）、`sync --check` 生成物比对（E15）。
- **trace**：6 列 TSV 解析（E11）、`normalize` JSONL、`summary`（W05/W15）、`stats`。
- **serve**：`GET /api/graph|trace-summary|layout|health|events`，`POST /api/layout|reload`，SSE 环形缓冲/重放/`resync`，200 ms 轮询 + 400 ms 去抖，git 状态事件。
- **web**：React Flow 12 + dagre 数据流、时钟树、统计、plugin 视图（流水线/Cache）、详情抽屉、`rvgen://` 跳转、布局 localStorage + 服务端合并、失效徽标与手动重载。
- **rvopen/gitw**：`rvgen://open` URI、三平台注册脚本、`post-commit`/`post-checkout` hook。
- **migrate**：`1.0.0 → 1.1.0`（去 `profiles`、`stage → x-cpu-stage`、`axi → handshake`），写前快照、`--dry-run` JSON Patch。
- **CI**：Python 覆盖率门禁、lint-imports、前端 typecheck/unit/build/e2e、pre-commit；nightly 变异测试（门槛 80%）。
- **examples/uart**：uart + fifo + baud_gen，零 CPU，iverilog 编译通过。
- **docs**：README、ARCHITECTURE、YAML/NODE_GRAPH/TRACE 参考、EXTENDING、TESTING、HANDOVER、NOT_IN_SCOPE、PERF、ACCEPTANCE、12 篇 ADR、决策与偏差记录。

### Changed

- **命名收紧（破坏性）**：YAML 中模块名、端口名、实例名、时钟名、`domain_id` 一律 `^[a-z][a-z0-9_]*$`；非小写在**加载/校验阶段**报 `E09`，不再等到建图。
- `node_graph.json` 的 node id / node_port 契约**不变**。
- `sync` 不写 `node_graph.json`；`sync --update-graph` 才写。
- `serve` 的 `rvgen_protocol` doctor 检查改为 `manual`（注册脚本需用户执行）。

### Fixed

- Windows 上 `allow_reuse_address=False`，端口冲突正确退出 3。
- `sync` 后 `sync --check` 把 W01 一次性提示误判为生成物落后；现比较时忽略 `// [W01]` 行。
- `merge_layout` 改为两层深合并，节点坐标不再丢失。
- `post-checkout` 依据 `$3=0` 跳过文件 checkout，避免误触发。
- `plugins/cpu` 节点类型统一为 `p_cpu:cache_node`，与前端/样例一致。

### Known limitations

见 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) 与 [docs/HANDOVER.md](docs/HANDOVER.md) 第 7 节：`init/import/gen` CLI、`check --fix`/语义 diff、rv32i 样例、elkjs、离线 npm 缓存、macOS 协议实测。

## [0.x] - 2026-11-24 及之前

- P0–P5 分阶段实现，提交见 `git log`（`fb4ad88` 起）。

## Schema

| schema | 变更 |
|---|---|
| `rvgen.yaml` 1.1.0 | 核心 kind 四类；`stage` 移入 `x-cpu-stage`；新增 `interfaces[]`、`cdc[]` 枚举、`top.tieoffs[]` |
| `node_graph.json` 1.0.0 | 首版；核心四类节点，plugin 必须 `p_` 前缀 |
| `layout.json` 1.0.0 | 节点/边/视图/偏好；默认不进 git |
| `trace_summary.json` 1.0.0 | 静态列 + 派生指标；不进 git |

## Migration

| from → to | 内容 |
|---|---|
| 1.0.0 → 1.1.0 | 删除 `profiles`；`stage/stage_index → x-cpu-stage/x-cpu-stage_index`；`axi → handshake`；`schema_version` 升 1.1.0 |
