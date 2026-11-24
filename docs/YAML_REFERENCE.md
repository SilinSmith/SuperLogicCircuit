# `rvgen.yaml` 参考（schema 1.1.0）

> `schema/rvgen.schema.json` 是结构契约；本文补充 schema 无法表达或由 loader 语义校验的规则。
> 标识符（模块名、端口名、实例名、时钟/域/CDC id、顶层端口名）一律小写 `^[a-z][a-z0-9_]*$`，
> 否则在加载阶段报 **E09**；`params[].name` 例外，允许 Verilog 惯例的大写。

## 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema_version` | 是 | 固定 `"1.1.0"`；其他 1.x 按 1.1.0 校验并报 I02 |
| `project` | 是 | 名称、顶层模块、默认时钟、复位策略 |
| `clocks` | 是 | ≥1 个时钟；每项含 `name/freq_hz/domain_id/source` |
| `cdc` | 否 | 跨域声明；`id/from/to/kind`，`async_fifo` 需 `width+depth` |
| `interfaces` | 否 | 接口库：`name/type/params/signals/dir_flip` |
| `modules` | 是 | ≥1 个模块 |
| `top` | 是 | `ports`（显式连线唯一依据）与 `tieoffs` |
| `plugins` | 否 | 局部 plugin 注册（键为小写 plugin 名） |
| `x-*` | 否 | plugin 扩展字段，核心透传不解释 |

## project

```yaml
project:
  name: uart_example          # ^[a-z][a-z0-9_]{2,31}$
  top: top                    # 小写标识符
  default_clock: clk
  reset: {name: rst_n, polarity: active_low, sync: true, levels: 2}
```

## clocks / cdc

```yaml
clocks:
  - {name: clk,      freq_hz: 50000000, domain_id: sys,  source: pad}
  - {name: clk_fast, freq_hz: 100000000, domain_id: fast, source: generated, parent: clk}
cdc:
  - {id: sys_fast, from: sys, to: fast, kind: 2ff}
  - {id: fifo_cross, from: sys, to: fast, kind: async_fifo, width: 8, depth: 16}
```

- `source: generated` 必须给 `parent`；`pll/pad` 不允许 `parent`。
- 两个不同 `domain_id` 的模块直连 → **E08**；补 `cdc[]` 后通过。
- `async_fifo.depth` 必须为 2 的幂，`almost_full < depth`（语义校验）。

## modules

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 小写；同时是 RTL 文件名与实例名 |
| `kind` | 是 | 核心：`module/bridge/memory/clock_gen`；其他值须 plugin 注册（E05） |
| `clock` | 是 | 引用 `clocks[].name` |
| `status` | 否 | `draft/wip/stable/frozen`；`frozen` 禁止 `sync` 覆写（I03/E10） |
| `todo` | 否 | 未完成说明 |
| `params` | 否 | `name`（可大写）+ `width` 或 `expr`（互斥）+ `default` |
| `ports` | 是 | ≥1；`name/dir` 必填，`width/kind/domain/default/connect/doc` 可选 |
| `interfaces` | 否 | 命名接口实例；`name/type/params/signals/dir_flip` |
| `x-*` | 否 | plugin 字段（如 `x-cpu-stage`） |

端口 `kind`：`data / valid / ready / handshake / clock / reset / param`。
`inout` 只允许 `kind: memory` 的模块。

```yaml
modules:
  - name: uart
    kind: module
    clock: clk
    params:
      - {name: WIDTH, default: 8}
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: cfg, dir: input, width: WIDTH}
      - {name: tx,  dir: output, width: 1}
```

## top

```yaml
top:
  ports:
    - {name: clk, dir: input, role: clock}
    - {name: cfg, dir: input, to: [uart.cfg]}
    - {name: tx,  dir: output, from: uart.tx}
  tieoffs:
    - {port: cfg, value: "8'h00"}
```

- `output` 必须且只能有 `from`；`input` 必须有 `to` 或 `role: clock/reset`（后者不参与推断）。
- 两个 output 指向同一 `module.port` → **E13**；不存在同名自动连线，时钟/复位永不参与同名推断。

## 三个完整示例

### 1) 单核 5 级流水线（plugin 字段以 `x-` 存在）

```yaml
schema_version: '1.1.0'
project:
  name: mini_core
  top: top
  default_clock: clk
  reset: {name: rst_n, polarity: active_low, sync: true, levels: 2}
clocks:
  - {name: clk, freq_hz: 100000000, domain_id: sys, source: pad}
modules:
  - name: core
    kind: module
    clock: clk
    x-cpu-stage: EX
    x-cpu-stage_index: 2
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: instr, dir: input, width: 32}
      - {name: pc, dir: output, width: 32}
top:
  ports:
    - {name: clk, dir: input, role: clock}
    - {name: instr, dir: input, to: [core.instr]}
    - {name: pc, dir: output, from: core.pc}
```

### 2) 带 CDC

```yaml
schema_version: '1.1.0'
project:
  name: cdc_demo
  top: top
  default_clock: clk
  reset: {name: rst_n, polarity: active_low, sync: true, levels: 2}
clocks:
  - {name: clk, freq_hz: 50000000, domain_id: sys, source: pad}
  - {name: clk_fast, freq_hz: 100000000, domain_id: fast, source: generated, parent: clk}
cdc:
  - {id: sys_fast, from: sys, to: fast, kind: 2ff}
modules:
  - name: slow_src
    kind: module
    clock: clk
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: d, dir: output, width: 1}
  - name: fast_sink
    kind: module
    clock: clk_fast
    ports:
      - {name: clk_fast, dir: input, kind: clock}
      - {name: d, dir: input, width: 1}
top:
  ports:
    - {name: clk, dir: input, role: clock}
    - {name: d, dir: output, from: slow_src.d}
```

### 3) 带 Cache 元数据（仅 plugin 解释）

```yaml
schema_version: '1.1.0'
project:
  name: cache_demo
  top: top
  default_clock: clk
  reset: {name: rst_n, polarity: active_low, sync: true, levels: 2}
clocks:
  - {name: clk, freq_hz: 50000000, domain_id: sys, source: pad}
modules:
  - name: dcache
    kind: memory
    clock: clk
    x-cpu-ways: 2
    x-cpu-sets: 256
    x-cpu-policy: write_back
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: addr, dir: input, width: 32}
      - {name: data, dir: inout, width: 32, kind: data}
top:
  ports:
    - {name: clk, dir: input, role: clock}
    - {name: addr, dir: input, to: [dcache.addr]}
    - {name: data, dir: output, from: dcache.data}
```

## 常见诊断

| 码 | 触发 |
|---|---|
| E01 | 端口位宽引用未声明参数（hint 列出可用参数） |
| E03 | 模块组合环（打印完整环路径） |
| E05 | 未注册的 kind |
| E08 | 不同 `domain_id` 直连且无 CDC |
| E09 | 标识符非小写 / 不匹配 `^[a-z][a-z0-9_]*$` |
| E13 | 两个 output 指向同一模块端口 |
| E15 | `sync --check`：生成物落后（`sync` 可修复） |
| E16 | `check`：`node_graph.json` 与 YAML 期望图语义不一致（`check --fix` 可修复） |
| W01 | USER 块契约（fingerprint）变更 |
| W14 | `import` 生成的待办字段（kind/clock/domain/top.ports） |
| I05 | `` `ifdef `` 包裹的端口被跳过 |
