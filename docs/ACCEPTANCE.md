# 验收场景清单（30 条）

> 状态：✅ 通过；⚠️ 部分通过/未实测；❌ 未实现。
> 统计：**✅ 14 · ⚠️ 12 · ❌ 4**（基准 2026-11-25，工具 `v1.0.0`，schema `1.1.0`）。
> 未通过项不是“测试没跑”，而是能力缺口；逐条对应 [decisions-log.md](decisions-log.md) D27 与 [HANDOVER.md](HANDOVER.md) 第 7 节。

| # | 状态 | 结论与证据 |
|---|---|---|
| AC01 | ⚠️ | `vendor/wheels/` 有离线 wheel；`vendor/npm/` 为空（只有 `.gitkeep`），`npm ci --offline` 无法从仓库内缓存复原。`scripts/npm-offline.{sh,ps1}` 存在，未做全新 clone 实测。 |
| AC02 | ❌ | `rvgen init` 未接线（`cli.py` 返回 E00）。 |
| AC03 | ✅ | `tests/unit/test_emitter.py::test_emit_preserves_user_logic_across_runs`：USER 块原样保留；生成区更新；W01 只在块外。 |
| AC04 | ✅ | `test_emitter.py::test_merge_reports_duplicate_and_orphan_block`：`orphaned/` 落 `.v.bak`，`I04`，退出 0。 |
| AC05 | ✅ | `test_emitter.py::test_emit_is_idempotent`；`tests/golden` 校验 `graph --write` 两次逐字节相同。 |
| AC06 | ✅ | `check` 逐字段比较期望图与 `node_graph.json`：手改端口位宽 → `E16` + 点号路径 `nodes.mod:uart.ports.cfg.width_bits` + hint，退出 1；`check --fix` 重写图后退出 0。测试：`tests/checker/test_check_lint.py::test_check_semantic_diff_and_fix`。 |
| AC07 | ⚠️ | `examples/uart` 的 `graph --write → sync → check --strict → sync --check` 均退出 0，无 `P*` 码；但 `init` 缺失，链路不完整。 |
| AC08 | ❌ | `examples/rv32i` 未落地，无法验证两项目并存与流水线视图隔离。 |
| AC09 | ⚠️ | `py/rvgen/importer.py` 已实现端口/参数骨架与 `W14` 待办，单测通过；`rvgen import` CLI 未接线。 |
| AC10 | ⚠️ | `test_graph.py::test_E13_duplicate_top_name_and_multi_driver` 覆盖重复名与多驱动；`role: clock` 与数据口同名的“不连线不候选”没有单独断言。 |
| AC11 | ❌ | `gen fuse-soc` 未接线，不产出 `.core`；`doctor` 只探测 fusesoc 是否存在。 |
| AC12 | ⚠️ | `tests/unit/test_core_whitelist.py` 全部通过（四类 kind、无 stage/cache、plugin 必须 `p_` 前缀）；但 `grep -rnE "is_cpu\|rv32i\|JALR\|pipeline_stage" py/rvgen/` 命中 1 处：`cli.py:42 --preset rv32i`（CLI 样例名，非核心逻辑）。 |
| AC13 | ✅ | `tests/unit/test_plugins.py` 覆盖坏 plugin：schema 非法/规则抛异常 → `W11` 跳过，其余命令退出 0；`rvgen plugin list` 可用。 |
| AC14 | ⚠️ | `trace normalize` 的 `core` flavor 与 6 列契约通过；`examples/rv32i` 与 `--flavor cpu` 端到端缺样例。 |
| AC15 | ✅ | `node_graph.json` 无 `metrics`/`viewport`/`position`（`examples/uart` 实测 grep 零命中）；布局与 trace 写旁路文件。 |
| AC16 | ✅ | `test_graph.py` 的 E03 用例断言完整环路径。 |
| AC17 | ✅ | `test_graph.py` 的 E08 用例：跨域直连报错，补 `cdc[]` 后通过。 |
| AC18 | ✅ | `test_graph.py` 的 E01 用例：未声明参数 + hint 列出可用参数。 |
| AC19 | ⚠️ | `module_node`/`clock_node`/`cdc_node` 与 `p_cpu:cache_node`/`p_cpu:pipeline_slot_node` 均有外观（`ModuleNode` 变体 + 样例）；`stats_node` 仅契约保留，核心构图不产出，无法验证其外观。 |
| AC20 | ⚠️ | 边标签显示位宽与 `derived` 的 bits/cycle + 十进制 GB/s，`explicit` 显示原值；无 explicit/derived 图标区分，`trace_summary` 利用率没有第三种标记。 |
| AC21 | ⚠️ | 核心三视图 + cpu 两视图切换有 e2e；切换 20 次内存增长 <20% 未测量。 |
| AC22 | ✅ | `test_server_sse.py` 的 watcher/SSE；`web/e2e/reload-keeps-layout.spec.ts` 验证重载后坐标保持；1.5 s 内徽标（轮询 200 ms + 去抖 400 ms）。 |
| AC23 | ✅ | `git check-ignore layout.json` 通过，`git ls-files layout.json` 为空；`rvgen.yaml` 无 `x:`/`y:`/`position`。 |
| AC24 | ⚠️ | Windows 注册脚本与 `rvgen://` fallback 已验证；macOS 脚本未实机验证；Linux 脚本按 desktop/xdg-mime 编写未实测三平台全覆盖。 |
| AC25 | ✅ | `tests/unit/test_trace_*.py`：core 行含 `loc/state/ids/arc/cdc`；cpu 键进 `p_cpu`。 |
| AC26 | ✅ | `tests/unit/test_trace_E11.py`：换行/列数错误报 E11 带行号，且不写半截 JSONL。 |
| AC27 | ⚠️ | `tests/unit/test_hooks.py` 验证 commit 阻断与 post-checkout 单次检查；CI 配置含 Playwright，但仓库未推送，`ubuntu-22.04` 实跑未执行。 |
| AC28 | ✅ | `test_server_sse.py`：缓冲补发、溢出 `resync`、慢客户端丢弃不阻塞。 |
| AC29 | ⚠️ | 500 节点 p95 **60.2 FPS**、100 万行归一化 **6.50 s**；200 节点 elkjs Worker <1.5 s **未实现**。 |
| AC30 | ⚠️ | `docs/HANDOVER.md` 已交付；未做“未参与者半天独立跑通”的外部试用。 |

## 交付判定

- **可以作为 v1.0.0 交付的能力**：YAML 校验、静态建图、RTL 骨架与用户块保护、`sync --check`、看板三视图 + plugin 视图、本地服务/SSE/布局、trace 归一化与 summary、迁移首例、文档全套。
- **不能宣称完成的能力**：`init/import/gen` CLI、`check --fix`/语义 diff、rv32i 样例、elkjs、离线 npm 缓存、跨平台协议全验证。
- 上述缺口已同步到 [NOT_IN_SCOPE.md](NOT_IN_SCOPE.md) 第 2 节与 [HANDOVER.md](HANDOVER.md) 第 7 节，不藏在测试通过率里。
