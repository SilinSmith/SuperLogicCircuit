# ADR-11 版本与迁移

> 状态：已采纳；日期：2026-11-25；适用阶段：P1/P6。
> 依据：`slc完整方案.md` §4.1、§4.5；决策记录 D1/D28。

## 决策

| 版本 | 值 | 说明 |
|---|---|---|
| 工具 | `1.0.1` | 与 tag `v1.0.1` 对齐 |
| `slc.yaml` schema | `1.1.0` | 核心四类 kind；领域字段 `x-*` |
| `node_graph.json` | `1.0.0` | 纯静态图契约 |
| `layout.json` / `trace_summary.json` | `1.0.0` | 旁路文件 |

- 加载时 major 必须为 1；任何非 `1.1.0` 的 1.x 按 1.1.0 校验并报 `I02`，保留原版本。
- 删除/重命名字段、删除枚举值 → major，必须提供迁移 step。
- 新增可选字段/枚举值 → minor；旧文件不受影响，新文件在旧 CLI 上被 schema 拒绝。
- 迁移在 `py/slc/migrate.py`：纯函数 step 链，每步后用目标 schema 校验。
- `migrate_file` 写前快照 `.slc/snapshots/<UTC>/slc.yaml`；`--dry-run` 只输出 JSON Patch。
- 首个迁移：`1.0.0 → 1.1.0`（去 `profiles`、`stage → x-cpu-stage`、`axi → handshake`）。

## 理由

工具版本与 schema 版本独立演进：工具可修 bug 而不动 schema；schema 变更必须可重放、可审计。

## 后果

- 本版 tag 为 `v1.0.1`，schema 为 `1.1.0`，两者不一致是**有意**的，不是笔误。
- 迁移只处理结构字段，不猜测 `kind`/`clock`/`domain`；无法还原的信息保留并提示。
- 迁移快照不自动清理，避免误删恢复点。

## 替代方案

- 工具版本跟 schema 同号：否决，会把 CLI 变更误标为 schema 破坏。
- 就地转换不校验：否决，半迁移文件比失败更危险。
