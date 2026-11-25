# ADR-01 核心零领域知识与 plugin 边界

> 状态：已采纳；日期：2026-11-25；适用阶段：P1 起。
> 依据：`slc完整方案.md` §1.1、§0.1、§4.1；决策记录 D2/D3。

## 背景

slc 是通用 Verilog 工程脚手架，不是 RV32I 专用工具。若核心认识 `stage`、Cache 状态或流水线槽位，UART/FIFO 项目会被迫携带并解释无意义字段。

## 决策

| 层 | 允许内容 |
|---|---|
| 核心 `kind` | 仅 `module` / `bridge` / `memory` / `clock_gen` |
| 核心 schema | 无 `stage` / `stage_index` / `cache`；领域字段必须 `x-<plugin>-*` |
| 核心规则码 | `E01–E15`、`W01–W15`、`I01–I08`；领域规则用 `P<PLUGIN>-nn` |
| plugin 注册 | `entry_points(group="slc.plugins")` + `abc`；`Plugin(kinds, node_types, views, interfaces, rules, trace_flavors)` |
| 图节点类型 | 核心四种；plugin 必须以 `p_<plugin>:` 前缀 |
| 前端视图 | `web/src/plugins/registry.ts`；`applies` 只依赖图数据 |

## 理由

判定问句：*“一个 UART 或 AXI 交叉开关项目需要它吗？”* 不需要就进 plugin。`plugins/cpu` 只是示例，与第三方 plugin 使用同一契约。

## 后果

- 正面：核心 schema 与校验器稳定；换领域不触发核心迁移。
- 负面：plugin 需要自带规则、视图与测试；`plugins/cpu` 的 `x-cpu-*` 字段对核心不可见。
- 约束：`tests/unit/test_core_whitelist.py` 守护 schema 边界；新增核心 kind 属破坏性变更。

## 替代方案

- 在核心加 `domain` 开关：否决，会让核心代码出现领域分支。
- 所有 kind 都开放、不校验：否决，拼写错误无法在加载期发现。
