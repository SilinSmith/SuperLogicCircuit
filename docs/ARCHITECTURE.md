# rvgen 架构

## 分层与依赖方向

```
CLI (py/rvgen/cli.py)
  ├── loader → model → graph → emitter → checker    核心链（零领域知识）
  ├── digest / importer / trace / migrate           核心工具
  ├── server / gitw / rvopen                        基础设施（可被 CLI 调用，不反向依赖核心）
  └── plugins (entry_points / rvgen.yaml plugins)   领域扩展
```

规则：

1. **单向依赖**：`loader` 不得 import `graph`/`emitter`；核心模块不得 import `server`/`gitw`/`rvopen`（`lint-imports` 强制）。
2. **核心零领域知识**：schema 的 `modules[].kind` 只有 `module/bridge/memory/clock_gen`；`x-<plugin>-*` 字段只透传不解释。
3. **受控资产只读**：命令之外（`serve`/watch/hook）永不写 `rvgen.yaml` 或 `node_graph.json`。
4. **一次显式动作只改一类资产**：`graph --write` 写图，`sync` 写 RTL，`migrate` 写 YAML（先快照）。

## 数据流闭环

```
rvgen.yaml ──graph.build──> node_graph.json ──前端只读──> 数据流/时钟树/统计
     │                           ▲
     │ sync                      │ check（重算并比对，不写）
     ▼                           │
rtl/*.v（含 USER 块）+ top.v ────┘
     │ 仿真 $fwrite 6 列 TSV
     ▼
trace TSV ──trace normalize──> JSONL ──trace summary──> trace_summary.json（旁路）
```

- `layout.json` 只存坐标/折叠/pinned；`trace_summary.json` 只存指标；两者都不进 git、不参与 `check`。
- 前端事件流（SSE）只提示“源已变更”，重载由用户点击触发；重载按 node id 合并布局。

## 模块职责

| 模块 | 职责 | 关键约束 |
|---|---|---|
| `loader.py` | YAML 读取、schema + 语义校验、标识符小写 E09 | 不 import graph/emitter |
| `model.py` | 只读模型、端口/参数/接口解析 | 无 IO |
| `graph.py` | 静态图构建、带宽推导、E03/E08/E13 等 | 不写盘 |
| `emitter.py` | 骨架/top/CDC 渲染、marker 合并、frozen、fingerprint、E10/E15/W01 | 只写 rtl/ 与 .rvgen/orphaned |
| `checker.py` | YAML ↔ 图语义 diff、规则码汇总 | 只读 |
| `digest.py` | 稳定摘要（sha256 短码） | 与格式解耦 |
| `importer.py` | Verilog 模块头 → YAML 骨架（W14 待办） | 不解析逻辑 |
| `trace.py` | TSV → JSONL、summary、stats | 流式、原子输出 |
| `migrate.py` | schema 迁移链 + 快照 + JSON Patch | 每步后 schema 校验 |
| `server.py` | HTTP API、SSE、轮询 watcher、layout 合并 | 只写 `layout.json` |
| `gitw.py` | git 只读状态 | 只跑 `rev-parse`/`status` |
| `rvopen.py` | `rvgen://` 构造与拉起 | 失败回退手动命令 |

## monorepo 地图

```
schema/        契约（JSON Schema 1.1.0）
py/rvgen/      核心 Python 包；入口 rvgen / python -m rvgen
plugins/       示例 plugin（cpu）；通过 entry_points("rvgen.plugins") 或 rvgen.yaml 注册
web/           看板；contracts/ 为手写 TS 契约；src/api 只读数据源
tests/         unit/checker/property/golden/migration/perf
examples/      可运行样例（uart；rv32i 未交付）
docs/          ARCHITECTURE / ADR / 契约 / 测试 / 交接 / 验收
scripts/       rvgen:// 注册、hooks、mutation score
```

## 错误与退出码

所有诊断走 `DiagnosticSink`，禁止直接 `print` 面向用户。退出码：

| 码 | 含义 |
|---|---|
| 0 | 成功（E 级为 0；W 只提示） |
| 1 | 存在 E，或 CLI 用法错误 |
| 2 | 只有 W 且 `--strict` |
| 3 | 环境/IO（缺文件、端口占用、写失败） |

`--quiet` 只抑制非 E 输出，不改变退出码。

## 扩展点

- 新 kind：plugin 注册表 + schema 允许自由字符串（core 只校验四类）。
- 新视图：`web/src/plugins/registry.ts`；按图数据（`x-*` / `p_*` 节点）激活。
- 新规则码：core 用 `E/W` 序号；plugin 用 `P<PLUGIN>-<n>`。
- 新迁移：`migrate.STEPS` 追加纯函数，必须配 fixture 与 dry-run 测试。
