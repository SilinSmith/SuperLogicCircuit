# 明确不做（NOT_IN_SCOPE）

> 本文件是范围护栏。以下事项**不是缺陷**，提交者不得以“补全”为名顺手实现；需要时先改方案与本文件。

## 1. 产品边界

| # | 不做 | 原因 / 替代 |
|---|---|---|
| 1 | 核心层任何 ISA / 应用域知识（RV32I、AXI、UART、Cache 一致性） | 一律 plugin；`plugins/cpu` 只是示例 |
| 2 | 综合/布局布线脚本、时序约束、FPGA 板级 IO 约束 | 文件列表与 target 交给 FuseSoC `.core`；不自研构建系统 |
| 3 | VSCode 插件、浏览器扩展 | 只提供 `slc://` 与注册脚本 |
| 4 | 全局 URI Scheme 自动注册 | 注册脚本需用户自行执行，不改系统关联 |
| 5 | GUI → YAML 自动写回 | GUI 只写 `layout.json`；结构变更必须改 YAML |
| 6 | diff 可视化、波形查看器 | 只出统计与时空图 |
| 7 | 多用户协作、服务端数据库、鉴权 | 单机本地服务 |
| 8 | formal verification 断言生成 | `check` 只留扩展点 |
| 9 | SystemVerilog `interface` / `class` / `covergroup` 生成 | 可读 SV 模块头，生成恒为 Verilog-2005 |
| 10 | verilator 之外的覆盖率合并 | 不做 |
| 11 | IP-XACT 读写 | 仅作数据模型参照；将来走 plugin |
| 12 | 安装/管理 verilator、fusesoc、verible、yosys、Node 版本 | `doctor` 只探测并提示 |
| 13 | 静默更新受控资产 | `node_graph.json` 只能显式写；`serve`/hook 永不写 |
| 14 | 自动生成 `slc.yaml`（除 `import` 的骨架能力外） | 声明是人工输入 |
| 15 | 跨项目模板市场、远程 registry | 不在 v1 范围 |

## 2. 本版未交付但属于方案范围的项

这些**是欠账**，不是“不做”；已记录在 [ACCEPTANCE.md](ACCEPTANCE.md) 与 [decisions-log.md](decisions-log.md)。

| 项 | 状态 |
|---|---|
| elkjs / Web Worker 精细布局 | 不实现；dagre 已达成 500 节点 p95 60 FPS 的同等目标 |
| 视图切换内存相对基线实测 | 不做绝对值断言；改为相对基线（同机同浏览器切 20 次，记录 JSHeapUsedSize p95 与基线倍数），尚未测量（AC21） |
| 仓库内置离线 npm tgz | 不内置；改为有网时用 `scripts/npm-prefetch.*` 预取到本机 cache；Python 依赖的 `vendor/wheels` 离线安装已由 CI 验证（AC01 ✅） |
| macOS `slc://` 实机验证 | 非验收范围（待环境）；协议验收限定 Windows 本机 + CI `ubuntu-22.04`（AC24） |
| 未参与者半天五步人工试用 | 非阻塞；需未参与项目的工程师按清单执行（AC30） |
| Windows 变异测试 | 依赖 fork，不可用 |

## 3. 判定方法

出现以下任一情况，先停下来记录，不要自行扩张：

- 需要新增核心 `kind`、核心规则码或修改退出码语义；
- 需要引入付费服务、外部 API、云端存储；
- 需要删除/改写既有 git 历史；
- 需要推翻已拍板口径（core 分层、退出码 0/1/2/3、trace 静态列、显式更新图、命名小写）。
