# ADR-08 命名小写与图契约不变

> 状态：已采纳（用户拍板）；日期：2026-11-25；适用阶段：P1 起。
> 依据：用户口径“收紧 YAML”；决策记录 D3。

## 决策

- YAML 标识符必须匹配 `^[a-z][a-z0-9_]*$`：`project.top`、`reset.name`、clock `name`/`domain_id`/`parent`、`cdc.id`/`from`/`to`、interface 与 signal 名、`modules[].name`、`ports[].name`、接口实例名、`top.ports[].name`、`tieoffs[].port`。
- 例外：`params[].name` 允许大写（Verilog 参数惯例，如 `WIDTH`）。
- 非小写在 **loader / `validate_semantic`** 阶段报 `E09`，不再只等到建图。
- `node_graph.json` 的 node id / node_port 契约**不变**（`mod:<name>`、端口名原样）。

## 理由

小写消除大小写不敏感文件系统与跨工具比较的歧义；把校验前移到加载期，错误位置更准确、诊断更早。

## 后果

- 存量 YAML 若含大写模块/端口名会直接失败；迁移需人工改 YAML（不改图契约）。
- 参数名大写保留，避免破坏 `WIDTH`/`DEPTH` 习惯。
- `E09` 同时覆盖重名，消息需区分“非法命名”与“重复”。

## 替代方案

- 只警告不报错：否决，会让图 id 在不同平台产生歧义。
- 连参数名一起收紧：否决，违背 Verilog 惯例且无收益。
