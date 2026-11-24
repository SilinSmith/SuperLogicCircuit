# 性能报告（本机实测，2026-11-25）

> 口径：Windows 本机、Python 3.11.6、Node 24.22.1、Chromium（Playwright headless）。
> 只记录**可复现命令 + 同机数字**；换机器需重跑，不要把数字当 SLA。

## 1. 结论

| 项 | 门槛 | 实测 | 结论 |
|---|---|---|---|
| 100 万行 TSV → JSONL | < 25 s | **6.50 s** | 通过（约 153k 行/s） |
| 500 节点拖动 p95 | ≥ 30 FPS | **60.2 FPS**（59 帧） | 通过 |
| 前端主包 gzip | 记录即可（ADR-06 D21） | **325.43 kB**（983.87 kB raw） | 可接受，首次加载需一次 |
| `sync --check`（uart 样例） | 无硬门槛 | 亚秒级 | 通过 |

## 2. 复现命令

### 2.1 trace 归一化

```powershell
$env:RVGEN_PERF="1"
.venv\Scripts\python.exe -m pytest tests/perf -q -s
Remove-Item Env:\RVGEN_PERF
```

输出样例：

```text
rows=1000000 elapsed=6.50s size=141.9MB
1 passed in 7.22s
```

测试构造 100 万行 6 列 TSV（约 142 MB），调用 `normalize_stream` 解析并丢弃输出，只计解析路径；不含磁盘落盘与 `summary` 聚合。

### 2.2 500 节点交互

```powershell
cd web
$env:PERF="1"
npx playwright test e2e/perf-500.spec.ts
Remove-Item Env:\PERF
```

输出样例：

```text
[perf-500] frames=59 p95=60.2 FPS
```

方法：注入 500 节点链式图，用合成 `mousedown/mousemove/mouseup` 拖动中段节点 60 帧，`requestAnimationFrame` 采样间隔取 p95 帧率。未开启 React StrictMode 双渲染以外的额外优化。

### 2.3 前端体积

```powershell
cd web
npm run build
```

当前：

```text
dist/assets/index-*.js   983.87 kB │ gzip: 325.43 kB
dist/assets/index-*.css   22.13 kB │ gzip:   4.16 kB
```

> Vite 会提示单 chunk > 500 kB。当前不做 code-split：看板是单页工具，首屏需要 React Flow + ECharts；拆包会把首屏交互推迟到二次请求。若后续引入 elkjs，必须按 ADR-06 的懒加载策略拆出独立 chunk。

## 3. 规模假设与降级

| 规模 | 行为 |
|---|---|
| 模块 ≤ 300、节点 ≤ 500、边 ≤ 1500 | 完整交互 |
| 节点 > 500 | 只读邻域模式（不做全图布局与全量边动画） |
| 单 trace ≤ 2 GB / ≤ 200 万行 | 单文件归一化 |
| 超过 200 万行 | 按 200 万行分片，summary 分片聚合 |

当前代码**未实现**自动分片与 500 节点以上的显式降级开关；超限时靠浏览器自然变慢，属于已知偏差（见 [ACCEPTANCE.md](ACCEPTANCE.md) AC21/AC23）。

## 4. 观察与风险

1. `normalize` 的瓶颈在字符串切分与 `float` 解析；6.5 s/100 万行仍有约 3× 余量，无需优化。
2. 500 节点 p95 60.2 FPS 已到 rAF 上限（60 Hz），说明该规模不是瓶颈；真实风险在 1500 条边的边组件数量。
3. 主包 325 kB gzip 中 React Flow 与 ECharts 占大头；后续若加 elkjs（约数百 kB），必须动态 import。
4. `serve` 的 SSE 每事件只推失效提示，不推图；轮询间隔 200 ms + 去抖 400 ms，对 300 模块项目无压力。
5. 未做内存峰值测量；100 万行归一化流式处理，理论内存与单行大小同阶。

## 5. 未测项

- Linux/macOS 上的同机对比。
- 真实 2 GB trace 的分片与内存峰值。
- 1500 条边同时高亮的帧率。
- `serve` 在 300 模块项目上的 `/api/graph` 序列化耗时。
