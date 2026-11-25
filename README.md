# SuperLogicCircuit

SuperLogicCircuit 是声明式 Verilog 工程脚手架，命令行与 Python 包名为 `slc`：`slc.yaml` 是唯一声明源，`node_graph.json` 是受控生成物，
`layout.json` / `trace_summary.json` 是旁路数据；看板只读这些契约，结构变更必须显式重算。

- 通用工具，不绑定 ISA；核心只认识 `module / bridge / memory / clock_gen` 四类结构件。
- 纯 Verilog-2005 可综合子集；用户逻辑写在 `// slc:user-begin` 区块内，`sync` 永不覆盖。
- 退出码固定：`0` 成功 / `1` 有 E 或用法错误 / `2` 仅 W 且 `--strict` / `3` 环境或 IO。

## 30 秒上手

本机要求 Python 3.11.6、Node 24.x（前端构建）、git。仓库作者环境已就绪，全新克隆：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\slc.exe doctor

cd examples\uart
..\..\..\.venv\Scripts\slc.exe graph --write   # 只读计算后显式写图
..\..\..\.venv\Scripts\slc.exe sync            # 生成 rtl/*.v，保留 USER 块
..\..\..\.venv\Scripts\slc.exe check --strict  # 0 error / 0 warning
```

前端与看板：

```powershell
cd web
npm ci
npm run build            # 产物进 web/dist
cd ..
.venv\Scripts\slc.exe serve --project examples\uart
# 浏览器打开 http://127.0.0.1:8123/
```

> 尚未实现 `slc init`，因此上手使用 `examples/uart`，而不是从空目录生成。
> 迁移旧版声明：`slc migrate --dry-run` 先看 JSON Patch，再 `slc migrate`（自动写 `.slc/snapshots/`）。

## 常用命令

| 命令 | 作用 |
|---|---|
| `slc doctor [--json]` | 探测 iverilog / node / git / verilator / yosys / fusesoc |
| `slc graph --write` | 从 YAML 重算 `node_graph.json`（唯一写图入口之一） |
| `slc sync [--dry-run\|--check]` | 生成模块骨架、`top.v`、CDC 模块；`--check` 比对生成物 |
| `slc check [--strict] [--format json\|github]` | YAML ↔ 图语义 diff，接 pre-commit / CI |
| `slc trace normalize <tsv> -o <jsonl>` | TSV → JSONL（Python 侧构建结构） |
| `slc trace summary <run> [--graph ...]` | 生成 `trace_summary.json`（旁路，不进 git） |
| `slc serve [--project DIR] [--port 8123] [--no-open]` | 本地看板 + `/api` + SSE |
| `slc plugin list` | 列出发现的 plugin（坏 plugin 报 W11 并跳过） |
| `slc migrate [--dry-run]` | schema 迁移（首例 1.0.0 → 1.1.0） |

## 故障速查（前 5 条）

| 现象 | 原因 | 处理 |
|---|---|---|
| `E09` 标识符非法 | 模块/端口/实例名不是小写 | 改为 `^[a-z][a-z0-9_]*$`；`params[].name` 例外允许大写 |
| `E10` + `sync --check` | frozen 模块生成物被手改 | 还原文件或 `--force-unfreeze` 后 `slc sync` |
| `E15` + `sync --check` | 非 frozen 生成物落后 | 跑 `slc sync`（会保留 USER 块） |
| `check` 退出 1，提示图落后 | 改了 YAML 但没更新图 | `slc graph --write`，再 `slc check` |
| `serve` 端口占用退出 3 | 另一个 slc 在跑 | `--port` 换端口；Windows 也不允许重复绑定 |

更多见 [docs/WEBUI.md](docs/WEBUI.md)、[docs/HANDOVER.md](docs/HANDOVER.md)、
[docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)（30 条验收的当前状态）。

## 仓库地图

```
py/slc/          核心实现（零领域知识）
plugins/cpu/       示例 plugin（不随核心默认启用）
schema/            slc.yaml JSON Schema 1.1.0
tests/             unit / checker / property / golden / migration / perf
web/               React 19 + Vite 7 + React Flow 12 看板
examples/uart/     通用样例（uart + fifo + baud_gen，无 CPU 概念）
docs/              架构、ADR、契约、测试、交接、验收
scripts/           slc:// 注册、git hooks、变异分数
```

## 文档

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 分层、依赖方向、数据闭环
- [docs/YAML_REFERENCE.md](docs/YAML_REFERENCE.md) — `slc.yaml` 全字段
- [docs/NODE_GRAPH_REFERENCE.md](docs/NODE_GRAPH_REFERENCE.md) — `node_graph.json` 契约
- [docs/TRACE_SCHEMA.md](docs/TRACE_SCHEMA.md) — TSV 6 列与 JSONL
- [docs/EXTENDING.md](docs/EXTENDING.md) — kind / 节点 / 视图 / CDC / plugin 规则码
- [docs/TESTING.md](docs/TESTING.md) — 门槛、单测、golden、变异测试
- [docs/HANDOVER.md](docs/HANDOVER.md) — 新人半天 checklist
- [docs/NOT_IN_SCOPE.md](docs/NOT_IN_SCOPE.md) — 明确不做与重新评估条件
- [docs/PERF.md](docs/PERF.md) — 实测性能与复现命令
- [CHANGELOG.md](CHANGELOG.md) — 版本与规则码变更

## 许可

内部工程工具；第三方依赖许可证见 [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)。
