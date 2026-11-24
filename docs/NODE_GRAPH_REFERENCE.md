# `node_graph.json` 契约（schema 1.0.0）

> `node_graph.json` 是 YAML 与看板之间的唯一图形契约，**纯静态**：不写布局、不写实测指标、不写时间戳。
> 只有操作者显式运行 `rvgen graph --write`（或 `sync --update-graph`）才会改写它。
> JSON Schema 见 [schema/node_graph.schema.json](../schema/node_graph.schema.json)。

## 1. 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | string | 是 | 固定 `"1.0.0"` |
| `generated_by` | string | 是 | `rvgen x.y.z`；不写 `generated_at`，保证逐字节幂等 |
| `source_digest` | string | 是 | `rvgen.yaml` 文本的 `sha256:` 前 16 位 |
| `nodes[]` | array | 是 | 按 `id` 升序排序 |
| `edges[]` | array | 是 | 按 `id` 升序排序 |

对象额外允许 `x-` 前缀字段（plugin 透传），其余未知字段会被 schema 拒绝。

## 2. 节点

### 2.1 通用字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 核心：`mod:<name>` / `clk:<name>` / `cdc:<id>` / `stats:<name>`；plugin：`p_<plugin>:<type>:<name>` |
| `type` | string | 核心：`module_node` / `clock_node` / `cdc_node` / `stats_node`；plugin：`p_<plugin>:<type>` |
| `label` | string | 展示名 |
| `module` | string\|null | 回指 `modules[].name`，用于 `rvgen://` 跳转 |
| `clock` | string\|null | 该模块使用的时钟名 |
| `domain` | string\|null | 时钟域；未知为 `null` |
| `loc` | object\|null | `{file, line, end_line}`，相对项目根；`null` 表示不可跳转 |
| `ports[]` | array | 仅 `module_node` 有意义 |
| `status` / `todo` | string\|null | 透传 YAML 的 `status` / `todo` |

`id` 与 `type` 的大小写契约不变（本文件不受“YAML 标识符小写”收紧影响，但核心格式本身只接受小写名）。

### 2.2 端口对象

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | `^[a-z][a-z0-9_]*$` |
| `dir` | enum | `input` / `output` / `inout` |
| `width_expr` | string\|integer\|null | YAML 中的原始写法（如 `"WIDTH"`、`8`、`null`） |
| `width_bits` | integer\|null | 解析结果；失败为 `null` |
| `kind` | enum | `data` / `valid` / `ready` / `handshake` / `clock` / `reset` / `param` |
| `domain` | string\|null | 端口级覆盖域 |
| `unresolved` | string\|null | 解析失败时为 `"E01"`，并可能带 `x-unresolved-reason` |

### 2.3 四种核心节点

| `type` | 产生者 | 额外字段 |
|---|---|---|
| `module_node` | 每个 `modules[]` | `module`、`clock`、`domain`、`ports[]`、`status`、`todo` |
| `clock_node` | 每个 `clocks[]` | `clock`、`domain` |
| `cdc_node` | 每个 `cdc[]` | `domain` = `cdc.from` 所在域 |
| `stats_node` | 契约保留；核心构图当前不产出 | 由 plugin 或后续统计节点使用；前端已提供 `stats` 外观 |

> 当前版本核心只产出 `module_node` / `clock_node` / `cdc_node`。统计视图由前端从边与 `trace_summary.json` 计算，不依赖 `stats_node`。

## 3. 边

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 数据/握手边：`mod:<src>.<port>->mod:<dst>.<port>`；时钟边：`clk:<name>->mod:<name>`；CDC 边：`clk:<from>->cdc:<id>`、`cdc:<id>->clk:<to>` |
| `source` / `target` | string | 节点 id |
| `source_port` / `target_port` | string\|null | 端口名；时钟/CDC 边为 `null` |
| `kind` | enum | `data` / `handshake` / `clock` / `reset` / `cdc` / `param` / `bundle` |
| `width_bits` | integer\|null | 静态位宽 |
| `bandwidth` | object\|null | 仅静态，见下 |
| `is_critical` | boolean | 人工标注的静态意图；参与后续语义 diff |

数据边由端口的 `connect` 推导，方向按 `output/inout → input` 归一；宽度不一致报 `W03`。握手边由 `valid` / `ready` / `handshake` 端口参与判定。

## 4. 带宽与单位

权威单位是 **bits/cycle**，与频率解耦；GB/s 一律十进制 `1e9`。

### 4.1 静态来源：derived（当前默认）

```json
{
  "source": "derived",
  "width_bits": 32,
  "clock": "clk_core",
  "freq_hz": 50000000
}
```

算例：32 bit × 50 MHz = 1 600 000 000 bit/s = 200 Mb/s = **0.2 GB/s**（十进制），同时 **32 bits/cycle**。

### 4.2 静态来源：explicit（人工覆盖）

```json
{
  "source": "explicit",
  "value": "12.8 GB/s",
  "reason": "手册标称峰值"
}
```

`explicit` 优先于 `derived`；`reason` 必填。两种来源互斥。

### 4.3 实测值与图文件无关

`toggles`、`bits_per_cycle`（实测）、`utilization`、`gbps`（实测）只存在于 `trace_summary.json`，见 [TRACE_SCHEMA.md](TRACE_SCHEMA.md)。图文件里搜索不到 `metrics` / `viewport`。

## 5. 实例片段（`examples/uart`）

```json
{
  "id": "mod:uart",
  "type": "module_node",
  "label": "uart",
  "module": "uart",
  "clock": "clk",
  "domain": "sys",
  "ports": [
    {"name": "clk", "dir": "input", "width_expr": null, "width_bits": 1, "kind": "clock", "domain": null, "unresolved": null},
    {"name": "cfg", "dir": "input", "width_expr": "WIDTH", "width_bits": 8, "kind": "data", "domain": null, "unresolved": null},
    {"name": "tx", "dir": "output", "width_expr": 1, "width_bits": 1, "kind": "data", "domain": null, "unresolved": null}
  ],
  "loc": {"file": "rvgen.yaml", "line": 10, "end_line": 20}
}
```

```json
{
  "id": "clk:clk->mod:uart",
  "source": "clk:clk",
  "target": "mod:uart",
  "source_port": null,
  "target_port": null,
  "kind": "clock",
  "width_bits": null,
  "bandwidth": null
}
```

## 6. 何时重算、如何校验

| 动作 | 行为 |
|---|---|
| `rvgen graph --write` | 重算并原子写入；第二次运行逐字节相同（AC05） |
| `rvgen sync` | **不改** `node_graph.json` |
| `rvgen sync --update-graph` | 生成 RTL 后额外写图，等价显式 `graph --write` |
| `rvgen check` | 重算图；对 `node_graph.json` 做 schema lint，并在 `generated_by` 与当前 CLI 不一致时报 `W10` |
| `rvgen serve` / watch / hook | 只读，最多提示“图落后” |

> **当前实现边界**：逐字段语义 diff（手改图后退出 1 并给点号路径）与 `check --fix` 尚未实现，`check` 目前覆盖 schema lint + 语义规则重算 + `W10`。该偏差记录在 [ACCEPTANCE.md](ACCEPTANCE.md) AC06 与 [decisions-log.md](decisions-log.md) D27。

## 7. 禁止事项

- 不写 `layout` / `position` / `viewport` / `metrics` / 时间戳；
- 不由 `serve`、watcher、pre-commit hook 写入；
- 不把 plugin 领域字段放核心字段，必须用 `x-<plugin>-*`；
- 不手工编辑后再期望 `check` 自动修复（当前会先被 schema/生成器重算覆盖判断捕获）。
