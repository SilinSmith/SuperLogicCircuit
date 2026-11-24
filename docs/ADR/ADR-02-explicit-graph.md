# ADR-02 声明源与显式图更新

> 状态：已采纳；日期：2026-11-25；适用阶段：P1 起。
> 依据：`rvgen完整方案.md` 决策二、§5；决策记录 D4。

## 背景

看板需要稳定的图形契约；若前端直接读 YAML，schema 一改两端同时炸。若文件一变就自动写图，受控资产会被静默改写。

## 决策

- `rvgen.yaml` 是唯一声明源。
- `node_graph.json` 是受控生成物，**只有** `rvgen graph --write` 或 `rvgen sync --update-graph` 能写。
- `rvgen sync` 默认只生成 RTL 骨架/top/CDC，不碰图。
- `serve`、watcher、pre-commit/post-checkout hook 只读；最多提示“图落后”。
- `layout.json`、`trace_summary.json` 是旁路文件，默认不进 git，`check` 不读。
- 图文件不含时间戳，排序确定，保证两次 `graph --write` 逐字节相同。

## 理由

单向同步（YAML → 图 → 视图）让 `check` 只面对静态结构，不被布局/trace 噪声干扰；显式动作让“受控资产被改写”可审计。

## 后果

- 改端口/连线后必须手动 `graph --write`，否则看板显示旧图；这是有意的摩擦。
- `sync --update-graph` 是唯一把“生成 + 更新图”合并的便利开关，仍属显式。
- `source_digest` 让读者能判断图对应哪版 YAML，但工具不据此自动重写。

## 替代方案

- 文件变更自动重写图：否决，违背“不静默更新受控资产”。
- 看板直接读 YAML：否决，契约层缺失。
