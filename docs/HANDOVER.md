# 交接说明（HANDOVER）

> 面向接手者：先读本文件，再按 [ARCHITECTURE.md](ARCHITECTURE.md) 找代码，按 [ACCEPTANCE.md](ACCEPTANCE.md) 判断“能不能交付”，按 [decisions-log.md](decisions-log.md) 判断“为什么是这样”。

## 1. 一句话现状

`rvgen` v1.0.0 已实现 **YAML 声明 → 校验/建图 → RTL 骨架生成 → 静态看板 → 本地服务 + 失效提示 → trace 指标 → 迁移首例** 的主链路；核心零领域知识，CPU 只是 `plugins/cpu` 示例。
**未实现**：`rvgen init`、`rvgen import` 的 CLI、`rvgen gen cdc/fuse-soc` 的 CLI、`check --fix`、逐字段语义 diff、`examples/rv32i`、elkjs Worker。详见第 7 节与 AC 表。

## 2. 上手五分钟

```powershell
cd y:\workspace\SuperLogicCircuit2
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\lint-imports.exe

cd examples\uart
..\..\.venv\Scripts\rvgen.exe graph --write
..\..\.venv\Scripts\rvgen.exe sync
..\..\.venv\Scripts\rvgen.exe check --strict
..\..\.venv\Scripts\rvgen.exe sync --check

cd ..\..
.venv\Scripts\rvgen.exe serve --project examples\uart
```

浏览器打开 `http://127.0.0.1:8123`（或 `?live=1`）。改动 `examples/uart/rvgen.yaml` 后看板应出现“源已变更”，点“重新加载”才更新。

前端开发：

```powershell
cd web
npm ci
npm run dev          # 5174，代理到 8123
npm run test:unit
npm run test:e2e
```

## 3. 代码地图

| 关注点 | 入口 |
|---|---|
| CLI 与退出码 | `py/rvgen/cli.py`、`py/rvgen/diag.py` |
| 加载/schema/行号/命名 | `py/rvgen/loader.py`、`py/rvgen/model.py` |
| 静态建图 | `py/rvgen/graph.py` |
| 指纹与差异 | `py/rvgen/digest.py`、`py/rvgen/checker.py` |
| 生成物保护 | `py/rvgen/emitter.py`、`templates/` |
| trace | `py/rvgen/trace.py`、`templates/trace_*.v.j2` |
| 迁移 | `py/rvgen/migrate.py` |
| 本地服务 | `py/rvgen/server.py`、`py/rvgen/gitw.py`、`py/rvgen/rvopen.py` |
| 前端 | `web/src/`（App、views、flow、panels、api、lib、plugins） |
| hook / 注册脚本 | `scripts/hooks/`、`scripts/register-rvopen-*` |
| CI | `.github/workflows/ci.yml`、`nightly.yml` |
| 契约样例 | `schema/`、`tests/golden/`、`tests/fixtures/` |

## 4. 不可协商的不变量

1. **核心零领域知识**：`CORE_KINDS` 只有四类；领域字段一律 `x-<plugin>-*`。
2. **退出码**：0 成功；1 有 E 或 CLI 用法错误；2 仅 W 且 `--strict`；3 环境/IO。
3. **trace 静态列**：6 列 TSV，扩展走 `Ext`，Python 侧归一化。
4. **显式更新图**：只有 `graph --write` / `sync --update-graph` 能写 `node_graph.json`。
5. **命名小写**：YAML 的模块/端口/实例/时钟/域标识符一律 `^[a-z][a-z0-9_]*$`；加载阶段报 `E09`。`node_graph.json` 的 id/port 契约不变。
6. **用户代码保护**：USER 块原样保留；删除块进 `orphaned/` 并报 `I04`；frozen 生成物被改报 `E10`。

## 5. 交付物与提交

| 阶段 | 提交 |
|---|---|
| P0 CI 骨架 | `fb4ad88` |
| P1 model/loader/digest/importer/graph | `027dcce`…`a17ed9d` |
| P1 命名收紧 | `cc37a75` |
| P2 emitter / sync | `640f7ed`、`c71500d`、`51a07df`、`bd640f0` |
| P3 看板 | `7ca2186`、`28637d5` |
| P4 trace 与插件视图 | `f3729a0`、`0f3ec72` |
| P5 serve/SSE/布局 | `b72eae3` |
| P6 硬化与交付 | 本阶段提交 + tag `v1.0.0` |

分支 `master`，未推送远端；tag 为本地轻量/附注 tag，具体以 `git tag -n` 为准。

## 6. 常见故障

| 现象 | 处理 |
|---|---|
| `rvgen` 命令找不到 | 用 `.venv\Scripts\rvgen.exe`，或 `pip install -e .` |
| `serve` 退出 3 | 端口被占；换 `--port`，Windows 上不会复用端口 |
| `sync --check` 报 E15 | 先 `rvgen sync`，确认 diff 后提交生成物 |
| frozen 模块报 E10 | 人工改回生成物，或显式 `--force-unfreeze`（会有 W 提示） |
| pre-commit 失败 | 先跑 `rvgen check` 与 `rvgen sync --check`；hook 在无 `rvgen.yaml` 时自动跳过 |
| e2e 起不来 | `npx playwright install chromium` |
| 前端快照 | `CI=true` 不自动写，用 `npx vitest run -u` 人工确认 |

## 7. 已知缺口（接手第一优先级）

1. `check` 没有逐字段语义 diff，也没有 `--fix`；手改 `node_graph.json` 目前不会被 `check` 直接判 1（见 AC06）。
2. `rvgen init` / `rvgen import` / `rvgen gen cdc` / `rvgen gen fuse-soc` 的 CLI 未接线；`importer.py` 与 `render_cdc` 能力已存在。
3. `examples/rv32i` 参考设计未落地；当前验收样例是 `examples/uart`。
4. elkjs 精细布局与 Web Worker 未实现；当前只有 dagre 与径向。
5. macOS `rvgen://` 注册脚本未实机验证；Windows 脚本已验证。
6. mutmut 在 Windows 不可用，变异分数只在 nightly Linux 产出。
7. `trace_summary` 无 plugin 专属聚合；CPU 字段原样保留。
8. `stats_node` 仅为契约保留，核心构图不产出。

## 8. 修改前自检

- 这条代码一个 UART 项目需要吗？不需要 → plugin。
- 这个文件是受控资产吗？是 → 只能由显式命令写。
- 这个行为改变退出码或契约吗？是 → 更新 AC、CHANGELOG、decisions-log，并补测试。
- 这个改动需要迁移吗？schema 删除/重命名 → 必须加 `migrate` step。
