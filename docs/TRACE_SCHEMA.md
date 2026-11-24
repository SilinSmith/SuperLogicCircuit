# trace 契约：6 列 TSV、JSONL 与 `trace_summary.json`

> RTL 只写**定宽、扁平、可 grep** 的文本；结构化只在 Python 侧做。RTL 里禁止拼 JSON。
> JSON Schema 见 [schema/trace.schema.json](../schema/trace.schema.json)（只约束归一化后的单行 JSONL）。

## 1. TSV 文件

第一行必须是元数据，数据行固定 6 列，制表符分隔，无换行/引号/花括号：

```text
#rvgen-meta	schema=core	timescale=ns
10	0	0x00000000	IDLE	fifo_cnt=0	-
20	1	0x00000004	RX	fifo_cnt=1	arc=uart.tx>fifo.push:1
```

- `schema=<flavor>`：`core`（默认）、`cpu`、`bus`，或 plugin 声明的 flavor。
- `timescale=<n><ps|ns|us|ms|s>`；`normalize` 用它把 `Time` 换算成 `time_ns`，不读 Verilog 的 `` `timescale ``。
- 缺失/非法元数据、列数不为 6、`Time` 非数字、`Cycle` 非数字或回退、`Loc`/`State` 含非法字符 → `E11`，**不产出半截 JSONL**。

### 1.1 六列语义

| 列 | 格式 | 说明 |
|---|---|---|
| `Time` | `%0t` | 仿真时间；建议 tb 先 `$timeformat(-9, 3, " ns", 0)` |
| `Cycle` | `%0d` | 周期计数；必须从 0 起单调不减 |
| `Loc` | `%s` | 通用位置：CPU 是 PC，FSM 是状态编码，流处理是计数器；缺省 `-` |
| `State` | `%s` | 通用进度：CPU 是指令字，其他设计可填事务 ID / 通道号；缺省 `-` |
| `Ids` | `k=v` 列表 | 被写的存储单元，`x1=0000002a,fifo_cnt=3`；无更新写 `-` |
| `Ext` | `k=v` 列表 | 扩展键值，`;` 分隔；无扩展写 `-` |

`Loc`/`State` 不得包含引号、单引号、制表符、花括号或为空字符串（`-` 除外）。

### 1.2 RTL 写法

```verilog
$fwrite(f, "%0t\t%0d\t%s\t%s\t%s\t%s\n", $realtime, cyc, loc, state, ids, ext);
```

## 2. `Ext` 键

| 键 | 归属 | 格式 | 含义 |
|---|---|---|---|
| `arc` | 核心 | `src.port>dst.port:t` 或 `src.port->dst.port:t` | 本周期该边是否翻转（`t=0/1`）；零翻转边在前端标红 |
| `cdc` | 核心 | `id:afull:cnt` | 跨域桥水位 |
| `pipe` `ctrl` `regw` `icache` `dcache` `dec` | `plugins/cpu` | 自由值 | 流水线槽位、气泡原因、写回、Cache 状态、解码文本 |
| `txn` `stall` | `plugins/bus` | 自由值 | 事务节拍与阻塞原因 |
| 其他 | 用户/plugin | `[A-Za-z0-9_.+-]` | 未声明键 → `W15`，保留不丢 |

- `arc` 的 `>` 会被规范化为 `->`，与 `node_graph.json` 的边 id 对齐。
- 已声明键格式非法 → `E11`；未声明键 → `W15` 并原样进入 JSONL 顶层 `ext`。
- flavor 已声明键进入 `p_<flavor>` 命名空间（如 `p_cpu`），核心不解释。

## 3. 归一化输出（JSONL）

```jsonl
{"cycle":0,"time_ns":0,"loc":"-","state":"IDLE","ids":{"fifo_cnt":0},"arc":[],"cdc":[]}
{"cycle":1,"time_ns":20,"loc":"-","state":"RX","ids":{"fifo_cnt":1},"arc":[{"edge":"uart.tx->fifo.push","toggle":1}],"cdc":[]}
{"cycle":2,"time_ns":40,"loc":"0x8","state":"TX","ids":{},"arc":[],"cdc":[],"p_cpu":{"pipe":"EX"},"ext":{"fsm":"tx:1:2:go"}}
```

| 字段 | 说明 |
|---|---|
| `cycle` | 整数，从 0 起 |
| `time_ns` | `Time × timescale 换算到 ns`，保留 6 位小数 |
| `loc` / `state` | 原样字符串 |
| `ids` | 对象；`-` 变 `{}` |
| `arc[]` | `{edge, toggle}`；`toggle` 只能 0/1 |
| `cdc[]` | `{id, afull?, cnt?}` |
| `p_<flavor>` | 已声明 plugin 键 |
| `ext` | 未声明键（W15 保留） |

## 4. `trace_summary.json`（旁路指标）

由 `rvgen trace summary <run.jsonl> --graph node_graph.json` 生成；**不进 git，`check` 不读**。

```json
{
  "schema_version": "1.0.0",
  "trace": "trace/uart_smoke.jsonl",
  "flavor": "core",
  "cycles": 20000,
  "timescale_ns": 1.0,
  "nodes": [{"id": "mod:uart", "active_cycles": 18342, "util": 0.917}],
  "edges": [{
    "id": "mod:uart.tx->mod:fifo.push",
    "bytes": 1048576,
    "bits_per_cycle": 419.43,
    "gbps": 20.97,
    "toggles": 120034,
    "toggle_rate": 0.75,
    "utilization": 0.83
  }],
  "warnings": ["W05"]
}
```

公式（`width` 来自静态图的 `width_bits`）：

- `bytes = toggles × width / 8`
- `bits_per_cycle = bytes × 8 / cycles`
- `gbps = bytes × freq_hz / cycles / 1e9`（仅 `derived` 带宽有 `freq_hz`；十进制 GB）
- `toggle_rate = toggles / (width × cycles)`
- `utilization = bits_per_cycle / width`；`> 1.0` → `W05`

静态图缺失时只报 `I08`，`utilization` 留空；文件存在但版本过旧同样只提示。

## 5. 命令与退出码

```powershell
rvgen trace normalize tb/out.tsv -o trace/run.jsonl --flavor core
rvgen trace summary trace/run.jsonl --graph node_graph.json -o trace_summary.json
rvgen trace stats trace/run.jsonl
```

| 情况 | 退出码 |
|---|---|
| 成功 | 0 |
| `E11`（格式）/ `E12`（读写） | 1（`E12` 为 IO 时实际按 `DiagnosticSink.io_failure` 返回 3） |
| 仅 `W15`/`W05`，无 `--strict` 入口 | 0 |
| 源文件不存在 | 3 |

## 6. 已知边界

- `trace_summary` 的 `flavor` 只用于展示；plugin 专属聚合未实现，CPU 字段以 `p_cpu` 原样保留。
- 1 000 000 行归一化性能校准用 `RVGEN_PERF=1 pytest tests/perf/test_trace_perf.py`，阈值 25 s。
- 官方 cv32e40p tracer 的真实列序仍**未核实**；`--flavor cpu` 目前只按核心 6 列 + `p_cpu` 透传，不做旧列序映射。
