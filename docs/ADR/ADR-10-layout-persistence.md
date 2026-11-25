# ADR-10 布局持久化：layout.json + localStorage

> 状态：已采纳；日期：2026-11-25；适用阶段：P5 起。
> 依据：`slc完整方案.md` A5、§7.3；决策记录 D23。

## 决策

- 浏览器键固定 `localStorage["slc:layout:v1"]`，按 **node id** 合并。
- live 模式下拖动同时 `POST /api/layout`，服务端合并写项目根 `layout.json`。
- 重载（应用内或浏览器刷新）只按 id 覆盖坐标，不重建视图偏好。
- `layout.json` 默认不进 git；`_stale` 条目保留 30 天。
- `pinned` / `collapsed` / `control_points` 原样保留，但 P5 UI 不提供控件。
- 图文件与 YAML 永不写坐标。

## 理由

按 `source_digest` 分键会让 YAML 任意改动丢坐标，违背“重载保留坐标”；node id 在端口/连线变化时仍稳定。双写保证 `serve` 与静态演示一致。

## 后果

- 删除模块后其布局条目变 `_stale`，30 天后清理。
- 多标签页同时拖动以最后一次 `POST` 为准，不做冲突合并（单机工具可接受）。
- 布局不影响 `check` 与生成物。

## 替代方案

- 只存 localStorage：否决，`serve` 与静态预览不一致。
- 布局写回 YAML：否决，破坏唯一声明源。
