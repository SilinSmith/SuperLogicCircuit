# ADR-05 trace 静态列与 flavor 扩展

> 状态：已采纳；日期：2026-11-25；适用阶段：P4 起。
> 依据：`slc完整方案.md` §4.3、§0.1 表第 4 条；决策记录 D19/D20。

## 背景

CPU 的 `icache`/`dcache`/`pipe` 字段若进核心列，UART 项目会被迫造假字段；RTL 里拼 JSON 既难写又易产生半截输出。

## 决策

- RTL 只写 6 列 TSV：`Time`、`Cycle`、`Loc`、`State`、`Ids`、`Ext`。
- 扩展键放 `Ext`：核心 `arc`/`cdc`；plugin 已声明键进 `p_<flavor>`；未声明键原样进顶层 `ext`（`W15`）。
- `Loc`/`State` 是通用语义：CPU 是 PC/指令，非 CPU 是状态编码/事务 ID，缺省 `-`。
- JSONL 只在 Python 侧构建；`normalize` 严格校验列数、数字、`Cycle` 单调。
- 指标写 `trace_summary.json`：`bits_per_cycle`/`gbps`/`utilization`/`toggles`，不进图、不进 git。
- `arc` 的 `>` 规范化为 `->`，与 `node_graph` 边 id 对齐。

## 理由

6 列是跨领域最小公分母；flavor 只影响键的命名空间，不改变列结构，前端可以吃同一份 JSONL。

## 后果

- 新增领域 trace 字段不需要改列，只需声明 flavor 键。
- 归一化是唯一结构化入口；错误在 Python 侧报 `E11` 并附行号，不产出半截文件。
- `trace_summary` 的 plugin 专属聚合尚未实现，CPU 字段原样保留。

## 替代方案

- 每领域一套列：否决，前端与工具链分叉。
- RTL 直接 `$fwrite` JSON：否决，转义与半截行不可控。
