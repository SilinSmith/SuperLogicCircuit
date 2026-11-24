# 验收场景清单（30 条）

> 状态：✅ 通过；⚠️ 部分通过/未实测；❌ 未实现。
> 统计：**✅ 22 · ⚠️ 8 · ❌ 0**（基准 2026-11-25，工具 `v1.0.0`，schema `1.1.0`）。
> 计数说明：此前 `⚠️7 · ❌2` 是分块提交时未同步减项的残留；表内 30 条实际为 ✅21 / ⚠️9 / ❌0，本次只修正计数，未改动任何条目状态。
> 未通过项不是“测试没跑”，而是能力缺口；逐条对应 [decisions-log.md](decisions-log.md) D27 与 [HANDOVER.md](HANDOVER.md) 第 7 节。

| # | 状态 | 结论与证据 |
|---|---|---|
| AC01 | ⚠️ | `vendor/wheels/` 有离线 wheel；`vendor/npm/` 为空（只有 `.gitkeep`），`npm ci --offline` 无法从仓库内缓存复原。`scripts/npm-offline.{sh,ps1}` 存在，未做全新 clone 实测。**本轮跳过**：回填 npm 缓存必须联网执行 `npm ci` 并打包，按“需联网就先跳过”处理。影响：全新 clone 的离线 `npm ci --offline` 仍不可用，需联网一次。 |
| AC02 | ✅ | `rvgen init demo` 生成 `rvgen.yaml` + `rtl/` + `node_graph.json`；`check --strict`、`sync --check` 退出 0；有 iverilog 时编译通过。minimal/uart/rv32i 三个 preset 均可生成。测试：`test_cli_init_import_gen.py::test_init_minimal_generates_compilable_project`。 |
| AC03 | ✅ | `tests/unit/test_emitter.py::test_emit_preserves_user_logic_across_runs`：USER 块原样保留；生成区更新；W01 只在块外。 |
| AC04 | ✅ | `test_emitter.py::test_merge_reports_duplicate_and_orphan_block`：`orphaned/` 落 `.v.bak`，`I04`，退出 0。 |
| AC05 | ✅ | `test_emitter.py::test_emit_is_idempotent`；`tests/golden` 校验 `graph --write` 两次逐字节相同。 |
| AC06 | ✅ | `check` 逐字段比较期望图与 `node_graph.json`：手改端口位宽 → `E16` + 点号路径 `nodes.mod:uart.ports.cfg.width_bits` + hint，退出 1；`check --fix` 重写图后退出 0。测试：`tests/checker/test_check_lint.py::test_check_semantic_diff_and_fix`。 |
| AC07 | ✅ | `rvgen init → graph --write → sync → check --strict → sync --check` 全链路已闭环：`test_cli_init_import_gen.py::test_init_minimal_generates_compilable_project` 在临时目录逐条执行并断言退出码；`examples/uart` 同链路均退出 0，无 `P*` 码。 |
| AC08 | ✅ | `examples/rv32i` 已落地（5 级流水 + I/D cache）；`check --strict`、`sync --check` 退出 0，iverilog 编译退出 0。`serve --project examples/uart` 与 `examples/rv32i` 各自加载自己的图；流水线视图只在含 `x-cpu-stage` 的 rv32i 出现。 |
| AC09 | ✅ | `rvgen import <file.v> -o rvgen.yaml` 已接线；端口/参数骨架 + `W14`，`[WIDTH-1:0]` 归一为 `width: WIDTH`。测试：`test_import_writes_skeleton`、`test_importer.py`。 |
| AC10 | ✅ | `test_E13_duplicate_top_name_and_multi_driver` 覆盖重复名与多驱动；`test_AC10_clock_role_top_port_never_infers_data_connection` 断言 `role: clock` 顶层端口即使与数据口同名，也不产生数据边/候选，对应输入仍报 `E14`。 |
| AC11 | ✅ | `rvgen gen fuse-soc` 生成 `<project>.core`：CAPI=2、VLNV、fileset 文件列表、参数默认值、default target；`gen cdc` 生成五个基础模块。测试：`test_gen_fuse_soc_writes_core`、`test_gen_cdc_writes_five_modules`。 |
| AC12 | ⚠️ | `tests/unit/test_core_whitelist.py` 全部通过（四类 kind、无 stage/cache、plugin 必须 `p_` 前缀）；但 `grep -rnE "is_cpu\|rv32i\|JALR\|pipeline_stage" py/rvgen/` 命中 1 处：`cli.py:42 --preset rv32i`（CLI 样例名，非核心逻辑）。 |
| AC13 | ✅ | `tests/unit/test_plugins.py` 覆盖坏 plugin：schema 非法/规则抛异常 → `W11` 跳过，其余命令退出 0；`rvgen plugin list` 可用。 |
| AC14 | ✅ | `examples/rv32i/trace/example.tsv` 用 `--flavor cpu` 归一化退出 0，`pipe/dec/ctrl/regw/dcache` 进入 `p_cpu`；核心 6 列不变，`trace summary` 退出 0。 |
| AC15 | ✅ | `node_graph.json` 无 `metrics`/`viewport`/`position`（`examples/uart` 实测 grep 零命中）；布局与 trace 写旁路文件。 |
| AC16 | ✅ | `test_graph.py` 的 E03 用例断言完整环路径。 |
| AC17 | ✅ | `test_graph.py` 的 E08 用例：跨域直连报错，补 `cdc[]` 后通过。 |
| AC18 | ✅ | `test_graph.py` 的 E01 用例：未声明参数 + hint 列出可用参数。 |
| AC19 | ⚠️ | `module_node`/`clock_node`/`cdc_node` 与 `p_cpu:cache_node`/`p_cpu:pipeline_slot_node` 均有外观（`ModuleNode` 变体 + 样例）；`stats_node` 仅契约保留，核心构图不产出，无法验证其外观。 |
| AC20 | ✅ | 边标签按来源显示徽标 `E`（explicit）/`D`（derived）/`T`（trace_summary）：derived 显示 bits/cycle + 十进制 GB/s，explicit 显示原值，trace 边附实测利用率（如 `83%`）。测试：`BandwidthEdge.test.tsx::带宽来源与 trace 利用率使用不同标记`、`DataflowView.test.ts::trace_summary 的利用率按边 id 挂到边数据上`；web 单测 39 passed、e2e 9 passed。 |
| AC21 | ⚠️ | 核心三视图 + cpu 两视图切换有 e2e（`views.spec.ts` 两条）；“切换 20 次内存增长 <20%”**未测量**：浏览器无稳定跨浏览器 heap API，视图切换 remount 属设计。影响：无法用数据证明无泄漏，仅能确认反复切换不崩溃、e2e 通过。 |
| AC22 | ✅ | `test_server_sse.py` 的 watcher/SSE；`web/e2e/reload-keeps-layout.spec.ts` 验证重载后坐标保持；1.5 s 内徽标（轮询 200 ms + 去抖 400 ms）。 |
| AC23 | ✅ | `git check-ignore layout.json` 通过，`git ls-files layout.json` 为空；`rvgen.yaml` 无 `x:`/`y:`/`position`。 |
| AC24 | ⚠️ | Windows 注册脚本与 `rvgen://` fallback 已验证；macOS 脚本未实机验证；Linux 脚本按 desktop/xdg-mime 编写未实测三平台全覆盖。 |
| AC25 | ✅ | `tests/unit/test_trace_*.py`：core 行含 `loc/state/ids/arc/cdc`；cpu 键进 `p_cpu`。 |
| AC26 | ✅ | `tests/unit/test_trace_E11.py`：换行/列数错误报 E11 带行号，且不写半截 JSONL。 |
| AC27 | ⚠️ | `tests/unit/test_hooks.py` 验证 commit 阻断与 post-checkout 单次检查；CI 配置含 Playwright，但仓库未推送，`ubuntu-22.04` 实跑未执行。 |
| AC28 | ✅ | `test_server_sse.py`：缓冲补发、溢出 `resync`、慢客户端丢弃不阻塞。 |
| AC29 | ⚠️ | 500 节点 p95 **60.2 FPS**（门槛 30）、100 万行归一化 **6.50 s**；200 节点 elkjs Worker <1.5 s **未实现**：新增 elkjs 依赖与异步布局改造成本高，dagre 已满足 500 节点性能门槛。影响：缺少精细分层布局，既有性能指标不受影响。 |
| AC30 | ⚠️ | `docs/HANDOVER.md` 已交付；未做“未参与者半天独立跑通”的外部试用。 |

### ⚠️ 8 条未通过项：缺什么、卡在哪、补齐成本

- **AC01**：缺 `vendor/npm` 的 tgz 回填与全新 clone 的 `npm ci --offline` 实测；卡在回填必须先联网安装并打包；补齐约半天（一次联网 + 脚本回填 + 复测）。
- **AC12**：缺 `grep` 零命中；卡在 `rvgen init --preset rv32i` 是方案 §7.1 明确列出的 CLI 名称，删改会与方案冲突；补齐约半天，但需先拍板“改名 preset”还是“接受该命中”。
- **AC19**：缺 `stats_node` 的实际外观验证；卡在核心构图按设计不产出该节点、只保留契约；补齐约 1 天（造一个产出该节点的 plugin 并补前端 e2e，或把契约降级）。
- **AC21**：缺“视图切换 20 次内存增长 <20%”的实测；卡在浏览器没有稳定的跨浏览器 heap API，只能人工 DevTools 采样或依赖实验性接口；补齐约 1 天，且结果受浏览器与运行环境影响。
- **AC24**：缺 macOS/Linux 的 `rvgen://` 实机验证；卡在需要对应桌面环境与真人执行注册脚本；补齐约每平台半天，无法在当前 Windows 机器完成。
- **AC27**：缺 `ubuntu-22.04` 的 CI 实跑；卡在仓库未推送、没有远程 runner；补齐约半天（推送并触发一次 CI），但涉及外部平台与推送授权。
- **AC29**：缺 200 节点 elkjs/Worker 布局 <1.5 s；卡在需新增 elkjs 依赖、异步布局与 Worker 生命周期改造，而 dagre 已满足 500 节点 30 FPS 门槛；补齐约 3–5 天（含依赖审计与回归）。
- **AC30**：缺“未参与者半天独立跑通”的外部试用；卡在需要真实第三方接手者与半天档期；补齐约半天组织与记录，但依赖他人。

## 交付判定

- **可以作为 v1.0.0 交付的能力**：YAML 校验、静态建图、RTL 骨架与用户块保护、`sync --check`、看板三视图 + plugin 视图、本地服务/SSE/布局、trace 归一化与 summary、迁移首例、文档全套。
- **不能宣称完成的能力**：elkjs 精细布局、离线 npm 缓存、跨平台协议全验证、视图切换内存增长实测。
- 上述缺口已同步到 [NOT_IN_SCOPE.md](NOT_IN_SCOPE.md) 第 2 节与 [HANDOVER.md](HANDOVER.md) 第 7 节，不藏在测试通过率里。
