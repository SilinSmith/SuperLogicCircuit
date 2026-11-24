# `rvgen` 项目方案：声明式 Verilog/IP 工程脚手架 + 图形化看板 + Git 一致性闭环

> 面向 AI agent 团队的可独立执行文档。任何未参与前期讨论的 agent 读完本文即可开工，遇到本文未覆盖的情况**停下来记 TODO，不要发明规则**。
> 所有"截至日期"统一为 **2026-11-24**；凡未拿到一手证据的结论均显式标注 `未核实` / `需 PoC 验证`。
>
> **定位（v1.1 修订，最重要的一句）**：`rvgen` 是**通用的 Verilog 工程脚手架工具**，不绑定任何 ISA、不绑定任何应用域。RV32I 软核是它的**第一个验收样例（reference design）**，用来证明工具好用，而不是工具的服务对象。
> 因此：**核心层不得出现任何 CPU / RV32I / 流水线专属概念**；所有领域知识只能以 plugin 形式存在。判定一条代码该放核心还是 plugin，只问一句：*"一个 UART 或 AXI 交叉开关项目需要它吗？"* 不需要就进 plugin。
>
> **v1.2 硬化（2026-11-24）**：核心 `kind` 只保留 `module | bridge | memory | clock_gen` 四类结构件，其余 kind 通过 plugin 注册表开放；`stage`、Cache 状态、流水线槽位一律以 `x-<plugin>-*` 扩展字段与 plugin 自带规则码存在，核心 schema 与核心校验器不出现、也不解释这些字段。

## 0. TL;DR 与四条关键决策

**决策一：不自研看板，选 React Flow（`@xyflow/react` v12）+ elkjs/dagre 双布局后端。**
React Flow 是 React 生态里唯一同时具备"受控流式状态 API（`useNodesState`/`applyNodeChanges` 风格）＋自定义节点/边＋小地图/背景/控件开箱可用＋MIT 授权"的节点编辑器。官方性能页给出的优化路径是 memoize 组件与回调、把 `selected` 从 `nodes` 数组里拆出去、用节点 `hidden` 属性做折叠展开、简化节点 CSS（动画/阴影/渐变会明显拖慢）[1]；官方布局指南确认 dagre 是"零配置拿到整齐分层树"的最简方案，elkjs 能力更强但**配置明显更复杂且布局是异步的**，需要封装成 hook 手动驱动 [2]。自研看板至少要多花数人月去补拖拽、缩放、连线吸附、无障碍、移动端触控，收益为零——这是被推翻的旧结论，见第 2 章。

**决策二：`rvgen.yaml` 是唯一声明源，`node_graph.json` 是受控生成物，布局与指标是旁路。**
静态结构只能来自 YAML；`node_graph.json` 由操作者显式更新（`rvgen graph --write`，或 `rvgen sync --update-graph` 这个显式开关），工具**不静默改写图文件**；`layout.json` 只存坐标/折叠/视图偏好，**默认不进 git**（进 `.gitignore`）；`trace_summary.json` 存动态指标，同样不进 git。这样 `check` 只面对静态结构，永远不会被布局噪声或 trace 噪声打扰。这是"单向同步"的含义：YAML → 图 → 视图，任何反向写回都禁止。

**决策三：用户代码靠 marker 区块 + fingerprint + orphaned 目录保护，不靠 3-way merge。**
业界成熟做法有两条路：EMF 的 `@generated NOT` 标注（重新生成时保留用户修改）[3]、以及模板继承/区块机制（Jinja2 的 `extends`/`block` 让子模板只填自己的块，父模板可反复重出）[4]。我们选 marker 区间，因为 Verilog 没有可挂注解的 AST 生态，`// rvgen:user-begin <id>` … `// rvgen:user-end <id>` 是最不容易被语法重构打坏的形式。`--fix` 删掉的块**不许静默丢弃**，一律落 `orphaned/<ts>/<module>.<id>.v.bak` 并在 stderr 打出 `I04`。契约变更提示 `W01` 只写在 USER 块**外**的生成区注释里，绝不改写块内字节。

**决策四：影响图结构的变更必须由操作者显式提交图文件。**
`rvgen sync` 只生成骨架、top、CDC 基础模块与 `.core`，不碰 `node_graph.json`；新增/删除模块、改端口、改连线后必须跑 `rvgen graph --write`，再跑 `rvgen check`。CI 与 pre-commit 只认 `check`，不依赖 `sync` 的副作用。这条保证"受控资产只能被显式动作改写"。

**被推翻的旧结论（明示，避免 agent 回头踩）：**
1. ~~自研 HTML/Canvas 看板~~ → 改用成熟开源节点编辑器 + 薄层魔改（自定义节点/自定义边），理由见决策一。
2. ~~看板直接吃 YAML~~ → 引入 `node_graph.json` 作为唯一图形契约，YAML 与视图之间必须隔一层规范化图。
3. ~~文件变更就 auto-reload 覆写视图~~ → 改为"服务端推送失效提示 + 用户手动点重新加载"，且重载时按节点 id 合并保留已有坐标与折叠态。
4. ~~在 Verilog 里拼 JSON~~ → RTL 只 `$fwrite` 定宽文本，`rvgen trace normalize` 在 Python 侧转 JSONL。

### 0.1 v1.1 通用化修订：六条被推翻的假设（**读文档者必看**）

把工具从"RV32I 专用"改成"通用 Verilog 脚手架"，不是改个名字的事。以下六条旧结论**已作废**，agent 若照旧文档实现即为返工：

| # | 旧结论（作废） | 新结论 | 理由 |
|---|---|---|---|
| 1 | `stage: IF/ID/EX/MEM/WB` 是核心必填字段 | 完全移出核心：YAML 里写 `x-cpu-stage` / `x-cpu-stage_index`，由 **`plugins.cpu` 的 schema 与规则码**校验；核心 schema 无 `stage` 字段 | UART / FIFO / PLL / AXI 交叉开关根本没有流水线级 |
| 2 | 流水线时空图是五大主视图之一 | 改为 **plugin 注册视图**：`plugins.cpu` 注册 `pipeline_slot_node` 与视图渲染器，核心 `figures.py` 不构建、不知道它 | 同上；非流水项目不该看到空图占位 |
| 3 | RV32I 校验规则（PC 低位、x0 写丢弃等）常驻 checker | 核心只保留通用规则码 E/W；领域规则由 plugin 自带 **`P<plugin>-<n>` 规则码**（如 `PCPU-01`），按需注入 | 对非 CPU 项目报"JALR 低位置 0 未验证"是荒谬的 |
| 4 | trace 契约固定为 CPU 的 `pipe`/`icache`/`dcache` JSONL | TSV 只写扁平静态列（核心列 + `Ext` 键值列），JSONL 由 Python 构建；扩展键由 `--flavor` / `meta.schema` 声明 | UART 的 trace 没有 icache，硬套会逼它造假字段 |
| 5 | `top.v` 靠"同名端口自动 connect"拉线 | **显式 `top.ports` 映射表**为唯一依据；自动推导只产出候选建议，且**时钟/复位永不参与同名连接** | 多 IP  SoC 中 `uart.tx` 与顶层引脚 `tx`、`cpu.clk` 与 `uart.clk` 都同名，盲连必错（详见 5.4） |
| 6 | 声明文件名 `design.yaml` | 改为 **`rvgen.yaml`** | 通用工具占用通用文件名会与其他工具撞名 |

**同时新增三项通用化能力**（v1.1 引入，非 RV32I 也能用）：
- **接口库 `interfaces/`**：命名接口（如 `axi4lite`、`apb`、`uart`、`ready_valid`）一次声明，多模块复用，含方向翻转语义。这是通用化真正的杠杆——Chisel 的 `Bundle` 靠"捕获一次、批量连接、一处修改全局生效"三点获得复用价值（Chisel 官方文档），我们用 YAML 表达同样的东西。
- **`rvgen import`**：从已有 `.v` 反向生成 `rvgen.yaml` 骨架（只解析端口/参数/模块头，不解析逻辑）。`BusWrap` 的 `v2yaml.py` 已证明这条路径可行[11]，这是存量 IP 纳管的入口。
- **`rvgen gen cdc`**：生成 `2ff`（`two_ff.v`）/ `pulse_sync` / `handshake` / `async_fifo` / `gray_bus` 五个跨域基础模块到项目根下的 `rtl/gen/cdc/`，`sync` 在 `cdc[]` 非空时自动调用；不再依赖外部库，也不允许生成未定义模块的例化。
- **`rvgen gen fuse-soc`**：生成 FuseSoC `.core` 文件，把文件列表、依赖、参数、target 交给 Edalize 屏蔽 EDA 工具差异[6]。**我们自己不造构建系统**——那是重复劳动且注定做不全。

## 1. 需求澄清

### 1.1 已锁定项（不可协商）

| 项 | 锁定内容 |
|---|---|
| **工具定位** | **通用 Verilog 工程脚手架**；服务对象是"任意 Verilog 项目"，RV32I 仅为首个验收样例 |
| 语言/形态 | 纯 Verilog-2005 可综合子集；用户只写逻辑，不写 IO 声明 |
| 声明源 | **`rvgen.yaml`** 是人写的唯一输入；`top.v` 与各模块骨架均可反复覆写 |
| 分层纪律 | **核心层零领域知识**：`kind` 只有 `module/bridge/memory/clock_gen` 四类，其余 kind 由 plugin 注册；无 ISA / 无流水线 / 无总线专有概念；领域能力一律 plugin |
| 用户代码保护 | USER 区块原样保留；删除的块进 `orphaned/`，不得静默丢失；契约变更提示 W01 写在块外生成区 |
| 图形契约 | `node_graph.json` 唯一且**纯静态**；只有操作者显式 `rvgen graph --write`（或 `sync --update-graph`）才更新；动态指标存 `trace_summary.json` |
| 一致性门禁 | `rvgen check` 语义 diff，非零退出；接 pre-commit 与 CI |
| 跳转 | `rvgen://` 协议（与旧工程命名空间区分）+ 三平台处理脚本，**不做 VSCode 插件** |
| trace | **静态 TSV**：核心列 `Time/Cycle/Loc/State/Ids` + `Ext` 键值列；JSON 由 Python 侧构建；指标进 `trace_summary.json`（不进 git） |
| 看板 | 不自研，用开源节点编辑器；只写自定义节点与自定义边；核心只出数据流/时钟树/统计三视图，其余视图 plugin 注册 |
| 布局存储 | 独立 `layout.json` 或 localStorage；绝不写回 `rvgen.yaml` |
| 构建集成 | 生成 FuseSoC `.core`，不自研构建系统；CDC 基础模块由 `rvgen gen cdc` 生成 |

### 1.2 假设项（agent 可按此实现，若与实测冲突则停下报告）

- 假设目标仿真器至少有一个可用：默认用 **Icarus Verilog**（本机实测 `D:\iverilog\bin\iverilog.exe` 可用），Verilator 为可选项；`$fwrite` 行为以实际使用的仿真器为准。**本机未安装 verilator / fusesoc / verible**，相关验收走替代路径（见 §12 AC02/AC11）。
- 假设项目规模上限：模块 ≤ 300、单模块端口 ≤ 64、图节点 ≤ 500、边 ≤ 1500；超过 500 节点进入第 5.6 节的只读邻域模式，不再是受支持的交互规模。
- 假设用户机器有 Python 3.11.6 与 Node 24.x（本机实测 v24.22.1 + npm 11.19.1，无 nvm/fnm/volta）；`vendor/` 离线镜像可用。
- 假设时钟均为同源或有明确 `domain_id`，不存在门控时钟（generated clock 仅允许 PLL 分频，且必须显式声明）。
- 假设 trace 单文件 ≤ 2 GB；超过则按 200 万行分片。
- **假设 `rvgen import` 只需正确解析"模块头 + 端口列表 + parameter"**：不做表达式解析、不做 `generate` 展开、不做 `include` 依赖求解。含 `` `ifdef `` 包裹的端口一律跳过并记 `I05`，要求人工补。

### 1.3 明确不做（NOT_IN_SCOPE）

1. **不在核心层实现任何 ISA / 应用域知识**。RV32I、AXI、UART、Cache 一致性等一律 plugin；`plugins/cpu` 是随仓库发布的**示例 plugin**，不是特权模块。
2. 不做综合/布局布线脚本、时序约束生成、FPGA 板级 IO 约束。**文件列表与 target 交给 FuseSoC `.core`**（v1.1 新增生成项，但不是自建构建系统）。
3. 不做 VSCode 插件、不做浏览器扩展、`rvgen://` 不做全局 URI Scheme 注册（只给注册脚本，用户自行执行）。
4. 不做 GUI → YAML 的自动写回。GUI 只写 `layout.json`；结构变更必须改 YAML。
5. 不做 diff 可视化、不做波形查看器（只出统计与时空图）。
6. 不做多用户协作、不做服务端持久化数据库、不做鉴权。
7. 不做 formal verification 断言生成（但 `rvgen check` 的静态规则要为其留扩展点）。
8. 不做 SystemVerilog 的 `interface`/`class`/`covergroup` 生成；`rvgen import` 能**读** SV 模块头，但生成恒为 Verilog-2005。
9. 不做 verilator 之外的覆盖率合并。
10. **不做 IP-XACT 读写**，但其数据模型是对齐的参照物（见 2.4）；若将来要做，走 plugin。
11. **不安装/管理外部工具**：verilator、fusesoc、verible、yosys 由用户自备；`rvgen doctor` 只探测并给出安装提示，不自动安装；Node 版本不由本工具切换（当前机器无 nvm/fnm/volta）。
12. **不静默更新受控资产**：`node_graph.json` 只能由显式命令写入，`serve`/watch 永远不得改写它。

### 1.4 启动前口径与样例默认值（Q-A 已定，Q-B 不阻塞）

> v1.2 起 **Q-A 全部已定**，以下表格即口径，不再是待确认项；**Q-B 样例设计**只影响 `examples/rv32i/`，换样例即换答案，不阻塞核心开发。

**Q-A 工具自身（已定口径，阻塞核心开发）**

| # | 问题 | 已定口径 |
|---|---|---|
| A1 | 声明文件名 | **`rvgen.yaml`**（`design.yaml` 作废） |
| A2 | 插件发现机制 | `entry_points(group="rvgen.plugins")` + `abc` 契约[12]；同时支持 `rvgen.yaml` 内 `plugins:` 局部注册 |
| A3 | 内置接口库首发范围 | `ready_valid` / `axi4lite` / `axi4stream` / `apb` / `uart` 五个，其余留给项目自定义 |
| A4 | 顶层连线策略 | **显式 `top.ports` 为准**；自动候选只作补齐建议且需 `--accept-wiring` 才落盘（见 5.4） |
| A5 | `layout.json` 是否进 git | **不进**（`.gitignore`），localStorage 兜底；项目根 `layout.json` 是唯一持久文件，服务端缓存只写 `.rvgen/cache/layout.<view>.json`（可丢，丢了从 `layout.json` 重建） |
| A6 | 带宽默认单位展示 | 内部 `bits/cycle`，UI 附带 GB/s 换算（按该边所在时钟域频率） |
| A7 | 服务器推送通道 | SSE（理由见第 7.2 节） |
| A8 | 前端与后端端口 | dev **5174**（Vite proxy → serve），serve 默认 **8123**；避开旧工程固定的 5173 |
| A9 | trace 采样粒度 | 每周期一行，不压缩（压缩交给 `normalize` 的 JSONL） |
| A10 | 是否生成 FuseSoC `.core` | **是**，v1 就做；它是"通用性"最省力的证明 |
| A11 | 图文件何时更新 | **只在操作者显式 `rvgen graph --write` / `sync --update-graph` 时更新**；`sync` 默认不动 `node_graph.json` |
| A12 | 自定义协议名 | **`rvgen://`**（不使用 `rv://`，避免与旧工程或其他工具撞名） |
| A13 | 本机工具链 | Node **24.x**、React **19**、Vite **7**、Python **3.11.6**；verilator/fusesoc/verible 未安装，验收用 iverilog 替代 |

**Q-B 样例设计 `examples/rv32i`（不阻塞，可并行）**

| # | 问题 | 推荐默认值 |
|---|---|---|
| B1 | 核数 | 单核，`hart_id=0` |
| B2 | 总线接口 | 采用内置 `ready_valid`（32 位） |
| B3 | 流水线级数 | 5 级（由 `plugins/cpu` 的 `lane` 表达） |
| B4 | Cache | I/D 各 2 路 256 行、写回+写分配 |
| B5 | 分支预测 | 静态不跳转（后向跳） |

## 2. 竞品与选型调研结论

### 2.1 节点编辑器横向对比

| 候选 | 授权 | 关键事实 | 结论 |
|---|---|---|---|
| React Flow 12 | MIT（核心库；Pro 为独立付费层，含示例/支持，**未核实**具体价目与功能边界） | 受控流式 API；自定义节点/边；Background/MiniMap/Controls 内置；官方性能页强调 memoize 与 `hidden` 折叠 [1]；布局需外接 dagre/elkjs [2] | **选用** |
| Vue Flow | MIT（**未核实**） | 若走 Vue 技术栈，API 形似 React Flow | 否决：团队侧 React 生态资料更厚，且 Elk/dagre 示例均为 React 官方维护 [2] |
| Cytoscape.js | MIT（**未核实**） | 布局生态最全（cose-bilkent / fcose / dagre / klay 系），可 headless 跑在 Node 侧做图运算 [5]；React 集成靠社区 `react-cytoscapejs`，**维护状态未核实** | 否决为**主编辑器**，保留为**布局候选**：它的强项是"算布局+样式表"，弱项是"表单化交互节点"，我们的节点要放端口表、带宽徽标、跳转按钮，React 自定义节点更直接 |
| jointJS | 社区版 MPL / 商业版双授权（**未核实**具体条款） | 图形元素模型完备，偏 diagramming | 否决：授权双轨 + API 偏重，魔改成本高 |
| GoJS | 商业授权，需付费 | 功能最强，含大量交互模板 | 否决：非开源，违反"用开源节点编辑器"硬约束 |
| 纯 dagre/elk 渲染 SVG | 开源 | 只有布局没有交互 | 否决：等于自研看板，正是被推翻的旧结论 |

> 选型结论已在上表给出；本文不嵌入任何外部图片，保持单文件自包含、离线可读。

### 2.2 布局后端：elkjs 与 dagre 的分工

| 维度 | dagre | elkjs |
|---|---|---|
| 能力 | 分层有向图，方向 LR/TB 一行配置 | 分层 + 正交 + 径向 + 树形 + 部件（ports）约束，算法族多 |
| 接入成本 | 同步调用，官方示例即 `getLayoutedElements` [2] | 异步，官方要求封装 `useLayoutedElements` hook [2] |
| 大图 | 纯 JS 同步计算，>500 节点会阻塞主线程（**推断，需 PoC**） | 官方未承诺 worker；我们**自行放进 Web Worker**（浏览器原生能力，与库无关） |
| 包体积 | 小（**具体 kB 未核实**，需 `npm pack` 实测后写进 ADR） | 大（**具体 kB 未核实**，同上） |

**结论**：核心视图（数据流、时钟树、统计）默认 dagre（快、够用），用户切"精细布局"时走 elkjs Worker；时钟树视图用 elkjs 的树形/径向；**Cache 状态机视图与流水线时空图不属于核心**，由 `plugins.cpu` 注册：Cache 视图用 d3-force（plugin 自带依赖，官方示例确认 force 布局是迭代式、需每 tick 回写节点位置，且必须提供开关避免无限计算 [2]），流水线时空图用网格坐标直算。

### 2.3 被否方案与否决理由（汇总）

| 被否方案 | 否决理由 |
|---|---|
| 自研 Canvas/SVG 看板 | 重复造拖拽/缩放/吸附/无障碍，维护成本远高于薄层魔改 |
| 把 `rvgen.yaml` 直接喂前端 | 前端会被迫理解 YAML 语义，schema 一改两端一起炸；必须有 `node_graph.json` 隔离层 |
| 3-way merge 保护用户代码 | Verilog 无稳定 AST 基线，merge 冲突对用户不可读；marker 方案可预测 |
| 用 Mermaid 作图 | 不可交互、无法挂自定义节点、无法承载动态指标绑定 |
| SSE 换成 WebSocket | 本场景只有服务端→客户端单向下推，SSE 自带重连与事件 id，WS 要自己补心跳与断线重放 |
| 在 RTL 里拼 JSON | `$fwrite` 拼字符串极易产生非法 JSON（逗号、换行、未刷新缓冲），且不可综合、仿真器间行为不一致 |

### 2.4 通用性参照物：三个"YAML/声明 → 硬件"工具的取舍（v1.1 新增）

通用化不是拍脑袋发明格式，而是站在已有实践上做减法。三个参照物各自解决我们的一部分问题：

| 参照物 | 它做对的事 | 我们采纳 | 我们不采纳 |
|---|---|---|---|
| **FuseSoC / Edalize**[6] | core 文件统一描述 RTL 文件、生成文件、接口依赖、testbench、参数、target；Edalize 屏蔽工具差异，一个 core 可换 Verilator / Vivado / VCS | **生成 `.core`，不自建构建系统**；文件列表与 target 由 `rvgen` 产出，`fusesoc run` 负责跑 | 不引入 FuseSoC 作为**库依赖**；不复制它的包管理器与远程库概念（超出范围） |
| **BusWrap**(efabless)[11] | YAML 描述 IP（info / parameters / ports / 外部接口）→ 生成 APB / AHB-Lite / Wishbone 包装 RTL + testbench + C 头 + 文档；`v2yaml.py` 从 `.v` 反生成 YAML 模板 | **接口库 + 多后端生成的思路**；**`rvgen import` 反向导入**（它证明了可行性） | 不把 wrapper 生成做成主功能（我们生成的是骨架 + 例化，不是总线包装）；不做 C 头与位域文档 |
| **IP-XACT (IEEE 1685-2022)**（标准文本） | 标准化组件 / 总线接口 / 连接 / 地址映射 / 寄存器字段的 XML 元数据 + SCR 语义一致性规则 + TGI 生成器接口 | **数据模型对齐**：`component↔module`、`busInterface↔interface`、`addressBlock↔ 预留`、`fileSet↔files`；字段命名尽量可直接映射 | v1 **不实现读写**（XML 繁琐、生态偏大厂工具）；留 plugin 位 |

**从 Chisel `Bundle` 抄来的三条复用原则**（Chisel 官方文档）：接口类要能"① 一次捕获、多处复用 ② 支持批量连接以削减连线代码 ③ 改一处即全局生效"。我们 YAML 的 `interfaces/` 必须同时满足这三点，否则不如不建。

**反例教训（不采纳 Chisel 的部分）**：绑定 JVM/Scala 工具链、生成物不可编辑、API 破坏性变更导致迁移极痛——正是我们坚持"纯 Verilog 输出 + USER 块保护 + `schema_version` 主版本拒绝加载"的原因。

### 2.5 调研中未能核实、必须 PoC 的项

1. cv32e40p `tracer.rst` 的**逐列字段顺序与示例行**：官方仓库文档页在本次调研环境被安全策略拦截，未能读到原文 → **标注 `未核实`**。P1 阶段必须由 agent 直接读 `cv32e40p/docs/source/tracer.rst` 与 `tb/cv32e40p_tracer.sv` 源码，把真实列序写进 `docs/TRACE_SCHEMA.md` 并用一段真实仿真输出做黄金文件。第 4.4 节给出的列序是**按用户指定的兼容目标写的待验证契约**，不是已从官方原文核实的事实。
2. cva6 `trace_core_*.log` 的列格式：同样 `未核实`，仅确认其存在逐行执行日志（未取得一手文档，故不采信任何二手转述）。
3. React Flow v11 → v12 的破坏性变更清单（包名从 `reactflow` 变为 `@xyflow/react`、`defaultPosition`/`defaultZoom` 等 prop 变化）：`未核实`官方迁移文档全文 → P3 开工前由前端 agent 读官方 migration guide 并写进 ADR-06。
4. React Flow 在**非 React 环境**（纯 Vue/原生页面）不可用：官方未承诺框架无关绑定；若将来要嵌入非 React 页面，方案是 **Preact + `preact/compat` 别名**或 iframe 微前端（`未核实`可行性，需 PoC）。
5. `onlyRenderVisibleElements` 的具体阈值收益与"官方建议节点数上限"：官方性能页**没有给出数字上限** [1]，只给了 memoize/折叠/简化样式三条路径 → 因此第 8 章的性能门槛是我们自己定的验收线，需在 P3 用真实 500 节点页面实测校准。
6. elkjs / dagre 精确包体积、`react-cytoscapejs` 维护状态、各库许可证全文：`未核实`，P0 收尾前由 agent 用 `npm view <pkg> license` + `npm pack --dry-run` 实测并写进 `docs/DEPENDENCIES.md`。
7. **本机版本矩阵**：`Node 24.22.1 + React 19 + Vite 7 + @xyflow/react 12` 的实际兼容性与构建体积 `未核实`；P0 用 `npm ls` + 一次真实 `vite build` 验证；不通过则显式改用 Node 22 + React 18.3（本机无 nvm/fnm/volta，属需要用户配合的环境变更，不由工具自动切换）。

## 3. 总体架构

### 3.1 分层与依赖方向（单向、禁环）

```
┌──────────────────────── 展现层 (web/) ────────────────────────┐
│  React Flow 画布 │ 自定义节点/边 │ 视图切换 │ 详情抽屉 │ 统计图表 │
└─────────────── 只依赖 contracts/ 与 /api，禁止 import py/ ─────┘
                          │  HTTP + SSE
┌──────────────────────── 服务层 (py/rvgen/server) ──────────────┐
│  FastAPI：GET /api/graph │ GET /api/events (SSE) │ POST /api/reload │
└───────────┬──────────────────────────────┬──────────────────────┘
            │                              │
┌───────────▼──────────┐        ┌──────────▼───────────┐
│  领域层 (core)        │        │  基础设施层           │
│  loader→model→graph   │        │  gitw / watcher /     │
│  →emitter→checker     │        │  rvopen / digest      │
│  trace / figures      │        │  (可替换，不反向依赖) │
└───────────┬──────────┘        └──────────┬───────────┘
            │                              │
      ┌─────▼──────┐               ┌───────▼────────┐
      │ schema/    │               │ 文件系统 / git │
      │ *.schema.json (唯一契约)    │ 二进制          │
      └────────────┘               └────────────────┘
```

**依赖规则（CI 用 import-linter 强制）**：`cli → server → core → schema`；`infra` 只被 `server`/`cli` 调用；`core` **禁止** import `server`/`infra`；`plugins/*` 只能依赖核心公开接口与 `schema/`，**核心与 server 禁止 import 任何 plugin 实现**，plugin 只能在启动时经 `plugins.discover()` 注册；`web/` 只能消费 `contracts/` 下由 schema 生成的 TS 类型。任何反向 import 即 CI 失败。

**plugin 边界（v1.2）**：plugin 可以向核心注册四样东西——`kind`、`node_type`、`view`、`rule_codes`，以及 trace 的 `flavor`。核心对注册内容只做**结构与引用**检查，不解释领域语义；贡献 `kind`/`node_type` 的 plugin 必须同时提供该类型的 schema 片段与校验函数，否则注册失败（W11 + 跳过）。

### 3.2 数据流（单向闭环）

```
rvgen.yaml ──loader──> DesignModel ──graph.build──> NodeGraph ──graph --write──> node_graph.json
                            │                          │                              │
                            └─emitter─> rtl/*.v        ├─ figures.build ─> 核心视图 Graph │
                                          │            │        │                     │
                                   digest + USER 块合并 │   layout.service (Worker)     │
                                          │            │        │                     │
                                   atomic write         │   React Flow 渲染 <──────────┘
                                                        │
trace/*.tsv ──trace.normalize──> trace/*.jsonl（窗口明细）
             └─trace.summary───> trace_summary.json（指标，不进 git）
                                        └─> 视图按需读取（均不改 node_graph.json）
                                                        │
gitw/git_state ──SSE yaml_changed──> 前端"有更新"徽标 ──用户点击──> GET /api/graph
```

**闭环含义**：改 YAML → `rvgen graph --write` → `rvgen check` → 绿；`check` 失败则改 YAML 或显式重写图，不允许任何命令在后台偷偷改图。`sync` 只负责 RTL/top/CDC/.core，`serve` 只读。CI 与 pre-commit 都跑同一条 `check`，不存在"本地绿、CI 红"的第二套逻辑。

### 3.3 monorepo 目录结构

```
rvgen/                          # 仓库根（工具本身，不是某个具体项目）
├─ pyproject.toml               # Python 3.11.6 精确约束，见第 15 章
├─ .rvgen/                      # 仓库级运行态，不进 git
│  └─ .git-event                # hook → server 的事件文件（watchdog 必须放行）
├─ py/
│  └─ rvgen/
│     ├─ cli.py  loader.py  model.py  graph.py  emitter.py
│     ├─ checker.py  trace.py  digest.py  figures.py  layout.py
│     ├─ plugins.py  importer.py  fusesoc.py
│     ├─ gitw.py  server.py  rvopen.py  diag.py  atomic.py
│     └─ templates/{module.v.j2,top.v.j2,cdc/*.v.j2}   # CDC：two_ff/pulse_sync/handshake/async_fifo/gray_bus
├─ tests/{unit,checker,golden,property,e2e,perf,migration}/   # 唯一测试根，坑位见 8.2
├─ web/
│  ├─ package.json  vite.config.ts  tsconfig.json
│  ├─ src/{App.tsx, api/, store/, flow/{nodes,edges}/, views/, panels/}
│  ├─ contracts/                # 由 schema 生成的 TS 类型（生成物，进 git）
│  └─ e2e/                      # Playwright（也可直接放 tests/e2e）
├─ schema/{rvgen,node_graph,layout,trace}.schema.json
├─ plugins/
│  ├─ cpu/{schema.py,rules.py,views.py,trace.py,plugin.py,web/}   # 示例 plugin，非特权
│  └─ bus/{schema.py,rules.py,views.py,trace.py,plugin.py,web/}
├─ examples/                    # 每个子目录都是**独立项目根**，用 serve --project 选择
│  ├─ uart/
│  │  ├─ rvgen.yaml  node_graph.json  layout.json  trace_summary.json
│  │  ├─ rtl/{<module>.v, gen/cdc/{async_fifo.v,gray_bus.v,handshake.v,pulse_sync.v,two_ff.v}}
│  │  ├─ tb/  trace/
│  │  └─ .rvgen/{cache/,orphaned/,snapshots/,wiring_suggestions.yaml}
│  └─ rv32i/                    # 同构；额外启用 plugins/cpu
├─ docs/                        # 第 13 章交付清单
├─ .pre-commit-config.yaml  .github/workflows/ci.yml
├─ scripts/{rvopen.sh,rvopen.cmd,rvopen.ps1,register.sh,register.ps1,hooks/,npm-offline.sh,npm-offline.ps1}
└─ vendor/                      # 离线 wheel + npm tgz
```

> **路径约定**：除仓库级 `.rvgen/.git-event` 外，本文中所有 `rvgen.yaml`、`node_graph.json`、`rtl/`、`tb/`、`trace/`、`.rvgen/orphaned/` 都是**相对所选项目根**而言，即 `examples/<name>/`；工具内部一律以 `--project` 解析后的目录为工作根，不读仓库根的散落文件。多示例的项目选择见 §7.5 `serve --project`。

## 4. 数据契约（本章最重要）

> 所有 schema 用 **JSON Schema Draft 2020-12**；Python 侧用 `jsonschema` 校验，$schema 字段必填。
> 错误信息友好化做法：用 `Draft202012Validator` 拿到 `iter_errors()`，按 `best_match` 选出最相关错误作为主因，再把 `absolute_path` 转成 `rvgen.yaml` 的点号路径（如 `modules.alu.ports.3.width`），连同 `instance`、`schema` 期望值、以及相邻正确示例一起塞进 `Diagnostic.hint`；批量错误按 `severity` 降序、最多展示 20 条，其余写进 `.rvgen/last_errors.json`。**禁止把 jsonschema 的原始 Exception 直接抛给用户。**
>
> **v1.1 扩展纪律（通用性的命脉）**：核心 schema 一律 `additionalProperties: false`，**且核心层不认识任何领域字段**。领域字段通过两条通道进入，均不污染核心：
> ① **`x-` 扩展属性**：JSON Schema 官方保留前缀，plugin 专属字段写在 `modules[].x-cpu-stage` 这类位置，核心校验器原样透传、不做解释；
> ② **`plugins.<name>` 顶层段**：该 plugin 的独立配置块，由对应 plugin 自己的 schema 校验。
> 多态分支用 `oneOf` + `const` 判别式（判别式派发，避免 O(n) 全分支试匹配与"must match exactly one schema"这类无信息量的报错；依据 JSON Schema 规范的 `oneOf` 语义）。
> **判定标准**：往核心 schema 里加字段前先问"非 CPU、非总线、非缓存的项目需要它吗"，答否则进 plugin。

### 4.0 `rvgen.yaml` 顶层结构（v1.1）

```yaml
schema_version: "1.1.0"      # 合法 semver；主版本不同即拒绝加载
project: { name, top, default_clock, reset: {...} }
clocks:  [...]
cdc:     [...]
interfaces:                   # 命名接口库（可复用总线束）
  - { name: cpu_bus, type: ready_valid, params: {DATA_WIDTH: 32}, dir_flip: true }
modules:
  - name: pipe_if
    kind: module              # 核心四类：module|bridge|memory|clock_gen
    clock: clk_core
    ports: [...]
    x-cpu-stage: IF           # plugin 字段：由 plugins.cpu 的 schema 校验，核心透传
    x-cpu-stage_index: 0
top:
  ports:                      # 显式顶层端口映射（v1.1 起是连线唯一依据，见 5.4）
    - { name: tx,  dir: output, from: uart0.tx }
    - { name: rxd, dir: input,  to:   [uart0.rxd] }
    - { name: clk, dir: input,  role: clock }     # role 声明，永不参与同名推断
    - { name: rst, dir: input,  role: reset, polarity: active_low }
  tieoffs:  [{ port: debug_en, value: "1'b0" }]   # 显式的悬空兜底，不再靠猜
plugins:                      # 领域扩展，核心不解释
  cpu: { enabled: true, lanes: [IF,ID,EX,MEM,WB], halts: [EBREAK] }
  bus: { enabled: true, check_axi_handshake: true }
```

**扩展字段纪律（v1.2）**：核心 schema 的每个 object 都带 `patternProperties: {"^x-": true}`，因此 `x-` 字段能通过校验、被原样透传，再由对应 plugin 的 schema 二次校验；plugin 未启用而 YAML 里出现其 `x-` 字段时，保留字段并报 `I07`，不视为错误。

### 4.1 `rvgen.schema.json`（v1.1.0）逐字段

| 路径 | 类型 | 必填 | 语义与约束 |
|---|---|---|---|
| `schema_version` | string | 是 | 固定 `"1.1.0"`，合法 semver；主版本不同即拒绝加载 |
| `project.name` | string | 是 | `^[a-z][a-z0-9_]{2,31}$`，用作顶层模块名前缀 |
| `project.top` | string | 是 | 顶层模块名，默认 `top` |
| `project.default_clock` | string | 是 | 必须能在 `clocks` 中解析到 |
| `project.reset` | object | 是 | `{name, polarity: active_high\|active_low, sync: bool, levels: int>=2}`；`levels` = 同步复位串级数（异步复位同步释放至少 2 级） |
| `clocks[]` | array | 是 | 至少 1 项；`name` 唯一 |
| `clocks[].freq_hz` | number | 是 | >0；带宽换算的唯一依据 |
| `clocks[].domain_id` | string | 是 | CDC 分组键；同名即同域 |
| `clocks[].source` | enum | 是 | `pll\|pad\|generated`；`generated` 必须填 `parent` |
| `clocks[].parent` | string | 条件 | `source=generated` 时必填且指向已定义 clock |
| `cdc[]` | array | 否 | 跨域桥声明；基础模块由 `rvgen gen cdc` 生成，禁止引用外部未声明模块 |
| `cdc[].id` | string | 是 | 唯一；生成实例名 `u_cdc_<id>` |
| `cdc[].from` / `.to` | string | 是 | 均须是已声明 `domain_id` |
| `cdc[].kind` | enum | 是 | `2ff\|async_fifo\|handshake\|pulse_sync\|gray_bus` |
| `cdc[].width` | int | 条件 | `async_fifo`/`gray_bus` 必填，1..1024 |
| `cdc[].depth` | int | 条件 | `async_fifo` 必填，2 的幂 |
| `cdc[].almost_full` | int | 否 | < depth |
| `interfaces[]`（**顶层接口库**） | array | 否 | 命名接口定义，供多个模块按名复用；`name` 全局唯一 |
| `interfaces[].name` | string | 是 | 库键，`^[a-z][a-z0-9_]*$`；被 `modules[].interfaces[].type` 引用 |
| `interfaces[].type` | string | 是 | 基础模板：内置 `ready_valid\|axi4lite\|axi4stream\|apb\|uart` 或 plugin 注册类型；未注册 → E05 |
| `interfaces[].params` | object | 否 | 模板参数（如 `{DATA_WIDTH: 32}`）；未替换 → W13 |
| `interfaces[].signals[]` | array | 否 | 覆盖模板默认信号集；不填则由 `type` 模板展开 |
| `interfaces[].dir_flip` | bool | 否 | 该库定义的默认方向翻转；模块引用时可覆盖 |
| `top` | object | 是 | 顶层端口与兜底配置；`top.ports` 是连线唯一权威（见 5.4） |
| `top.ports[]` | array | 是 | 每项 `{name, dir, from\|to, role?, polarity?}`；输出用 `from: inst.port`（单驱动），输入用 `to: [inst.port, ...]` |
| `top.ports[].role` | enum | 否 | `clock\|reset\|data`，缺省 `data`；`clock/reset` 永不参与同名推断 |
| `top.ports[].polarity` | enum | 否 | `active_high\|active_low`；`role=reset` 时可覆盖 `project.reset.polarity` |
| `top.tieoffs[]` | array | 否 | `{port, value}` 显式悬空兜底；与 `ports[].default` 同时存在且不一致 → E09 |
| `modules[]` | array | 是 | 至少 1 项；`name` 唯一且 `^[a-z][a-z0-9_]*$` |
| `modules[].name` | string | 是 | 生成文件名 `<name>.v` |
| `modules[].kind` | string | 是 | 核心内置四类 `module\|bridge\|memory\|clock_gen`；其他值必须已在 plugin `kind_registry` 注册（如 `cache`），否则 E05 |
| `modules[].clock` | string | 是 | 引用 `clocks[].name`；**单模块必须单时钟**（多时钟 → E09） |
| `modules[].status` | enum | 否 | `draft\|wip\|stable\|frozen`；`frozen` 模块不再被覆写（E10 保护） |
| `modules[].todo` | string\|null | 否 | 前端显示待办角标；**不参与指纹**，不会触发 W01 |
| `modules[].params[]` | array | 否 | `{name, width\|expr, default, doc}`；`width` 与 `expr` 互斥 |
| `modules[].ports[]` | array | 是 | 至少 1 项；见下 |
| `modules[].x-<plugin>-*` | any | 否 | plugin 扩展字段（如 `x-cpu-stage`、`x-cpu-stage_index`）；核心透传，由 plugin schema 校验；未启用 plugin 时报 I07 但保留 |
| `ports[].name` | string | 是 | 模块内唯一，小写蛇形 |
| `ports[].dir` | enum | 是 | `input\|output\|inout`；`inout` 仅 `kind=memory` 允许 |
| `ports[].width` | int\|string\|null | 否 | 见 §5.1 解析链（1–4 步）；null 且无法解析 → E01 |
| `ports[].kind` | enum | 否 | `data\|valid\|ready\|handshake\|clock\|reset\|param`；缺省 `data`。总线专有语义（axi 等）走 `interfaces` 或 plugin，不进核心枚举 |
| `ports[].domain` | string\|null | 否 | 端口所属 clock 名；跨模块连接时域不一致触发 E08 |
| `ports[].default` | string\|null | 否 | 浮空输入兜底值，如 `"1'b0"`、`"{W{1'b0}}"` |
| `ports[].connect` | string\|null | 否 | 显式指定连到 `inst.port` 或常量；未填不自动连线，只进入候选建议（W12） |
| `ports[].doc` | string\|null | 否 | 生成注释与前端 tooltip |
| `modules[].interfaces[]` | array | 否 | 在模块上使用接口束，一次声明批量连线 |
| `modules[].interfaces[].name` | string | 是 | 接口实例名，模块内唯一 |
| `modules[].interfaces[].type` | string | 是 | 可引用顶层 `interfaces[].name`，或直接写内置/plugin 类型；未注册 → E05 |
| `modules[].interfaces[].params` | object | 否 | 覆盖库定义的模板参数；未替换 → W13 |
| `modules[].interfaces[].signals[]` | array | 否 | 覆盖模板默认信号集；不填则由 `type` 模板展开 |
| `modules[].interfaces[].dir_flip` | bool | 否 | true 时 master↔slave 方向翻转（见 5.4 优先级 3） |

**校验附加规则（非纯 schema 能表达，放 `loader.validate_semantic`）**：时钟引用存在性、CDC 两端域不同（`from == to` → W09）、端口名不重复、参数默认值可综合（禁止 `#(` 里出现函数调用）、`interfaces.type` 已注册、`x-` 字段的 plugin 是否存在（不存在 → I07）。**核心不校验任何 `x-` 字段的取值**；`x-cpu-stage` 的取值集合由 `plugins.cpu.lanes` 校验，规则码为 `PCPU-01`。

**命名口径（v1.2 收紧）**：`project.top`、`project.reset.name`、`clocks[].name/domain_id/parent`、`cdc[].id`、`interfaces[].name` 及其 `signals[].name`、`modules[].name`、`ports[].name`、`modules[].interfaces[].name` 及其 `signals[].name`、`top.ports[].name` 一律必须匹配 `^[a-z][a-z0-9_]*$`，在 **loader/`validate_semantic` 阶段**即报 E09，而不是等到建图；`node_graph` 的 node id / node_port 契约保持不变。参数名 `params[].name` 保留 Verilog 惯例，允许大写（如 `WIDTH`），不纳入本规则。

### 4.2 `node_graph.schema.json`（v1）逐字段

| 路径 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `schema_version` | string | 是 | `"1.0.0"` |
| `generated_by` | string | 是 | `rvgen x.y.z`；**不写 `generated_at`**——时间戳会破坏 `graph --write` 的字节级幂等（AC05），版本信息足以定位生成器 |
| `source_digest` | string | 是 | `rvgen.yaml` 的 sha256:前 16，用于判断是否需要重算 |
| `nodes[]` | array | 是 | 见下表；`id` 全局唯一 |
| `nodes[].id` | string | 是 | 核心格式 `mod:<name>` / `clk:<name>` / `cdc:<id>` / `stats:<name>`；plugin 节点为 `<type>:<name>`，其中 `<type>` 自带前缀（如 `p_cpu:cache_node:l1d`） |
| `nodes[].type` | string | 是 | 核心四种 `module_node\|clock_node\|cdc_node\|stats_node`；其他值由 plugin 注册（如 `p_cpu:cache_node`、`p_cpu:pipeline_slot_node`），未注册 → E04 |
| `nodes[].label` | string | 是 | 展示名 |
| `nodes[].module` | string\|null | 否 | 回指 `modules[].name`，用于 `rvgen://` 跳转；`clock_node` 可带 `clock` |
| `nodes[].loc` | object\|null | 否 | `{file, line, end_line}`，相对仓库根；缺失则节点不可跳转（W10） |
| `nodes[].domain` | string\|null | 否 | 时钟域；未知为 null。流水线级等 plugin 属性放 `nodes[].x-*`，核心不解释 |
| `nodes[].ports[]` | array | 否 | `{name, dir, width_expr, width_bits, kind, domain}`；`width_bits` 是解析结果，解析失败为 `null` + `unresolved: E01` |
| `nodes[].status` / `todo` | string\|null | 否 | 透传自 YAML |
| `edges[]` | array | 是 | 见下 |
| `edges[].id` | string | 是 | `<src>.<port>-><dst>.<port>`，稳定可排序 |
| `edges[].source` / `.target` | string | 是 | 节点 id |
| `edges[].source_port` / `.target_port` | string\|null | 否 | 端口名；`clock_node` 出边为 `null` |
| `edges[].kind` | enum | 是 | `data\|handshake\|clock\|reset\|cdc\|param\|bundle` |
| `edges[].width_bits` | int\|null | 否 | 静态位宽；未知为 null |
| `edges[].bandwidth` | object\|null | 否 | **仅静态**：`explicit` 或 `derived`，见下 |
| `edges[].is_critical` | bool | 否 | 缺省 false；人工标注的静态意图，**参与 check** |

> **`node_graph.json` 是纯静态文件（v1.2 硬约束）**：不包含 `metrics`、`viewport`、任何随仿真变化的字段。动态指标、实测带宽、利用率统一写入独立的 `trace_summary.json`（结构见 4.6），该文件默认不进 git。因此 `check` 只需比较静态结构，`sync`/`trace` 永远不会改动图文件。

**`bandwidth` 的静态两种来源（互斥且优先级从高到低；trace 实测不写进本文件）**：

| 来源 | 写法 | 计算 |
|---|---|---|
| ① 显式覆盖 | `{"source":"explicit","value":"12.8 GB/s","reason":"手册标称峰值"}` | 原样采用；`reason` 必填，否则 E09 |
| ② 静态推导 | `{"source":"derived","width_bits":32,"clock":"clk_core","freq_hz":50000000}` | `bits_per_cycle = width_bits`（每周期一次传输）<br>`GB/s = width_bits × freq_hz / 8 / 1e9` |

**单位规范**：**权威单位是 `bits/cycle`**（与频率解耦，跨时钟域可比）；GB/s 一律按 **十进制** `1e9`，并在 UI 上标注 `GB/s (decimal)`；`KiB/s` 只在 tooltip 里按 `1024` 换算给出。实测带宽、`utilization`、`toggles` 全部只存在于 `trace_summary.json`（见 4.6），计算方式与告警阈值也在那一节定义。

### 4.3 `layout.schema.json`（v1）

| 路径 | 类型 | 语义 |
|---|---|---|
| `schema_version` | string | `"1.0.0"` |
| `views.<viewId>.nodes[<nodeId>]` | object | `{x, y, collapsed, pinned, group}`；`pinned=true` 时布局算法不得移动 |
| `views.<viewId>.edges[<edgeId>]` | object\|null | `{control_points:[[x,y],...], label_offset:[dx,dy]}` |
| `views.<viewId>.viewport` | object | `{x,y,zoom}` |
| `views.<viewId>.prefs` | object | `{layout_algo, direction, show_trace, filter_domain[]}` |
| `_stale` | object | `{<nodeId>: <lastSeenISO8601>}`；从图中消失的节点布局暂存 30 天后清理 |

**进不进 git 的推荐（默认走这条）**：`layout.json` 写入 `.gitignore`，由浏览器 localStorage 作为主存储、`POST /api/layout` 作为可选跨机器同步；仓库里只保留 `layout.example.json` 供新成员起步。**理由**：布局是纯主观偏好，进 git 会产生高频无意义 diff 和多分支冲突，而 `check` 必须忽略它——一个"进了 git 却被 check 忽略"的文件比"不进 git"更危险，因为它会诱导人以为它是受控资产。该问题已在 A5 定案：**不进 git**；`check` 整体剔除 `layout*`。

### 4.4 `trace.schema.json`（v1.1 改为可插拔）

**设计原则（v1.2 重写）**：RTL 只写**定宽、扁平、可 grep 的文本**；结构化（JSON/JSONL）只发生在 Python 侧。没有 JSON 列、没有花括号、没有引号、不允许嵌套。这样既守住"RTL 不拼 JSON"，又让解析失败只可能来自列数或键名。

**TSV 结构**：
- 第一行必须是元数据注释：`#rvgen-meta<TAB>schema=<flavor><TAB>timescale=<unit>`；缺失或不可解析 → E11。
- 数据行固定 6 列：`Time \t Cycle \t Loc \t State \t Ids \t Ext`，制表符分隔，单行，无多余空格。

| 列 | 格式 | 说明 |
|---|---|---|
| `Time` | `%0t` | 仿真时间。tb 必须在写 trace 前调用 `$timeformat(-9, 3, " ns", 0)`；normalize 按 `#rvgen-meta` 的 `timescale` 换算，不再靠猜 `` `timescale `` |
| `Cycle` | `%0d` | 周期计数，从 0 起单调递增；**禁止用 `$time` 代替** |
| `Loc` | `%s` | 通用位置标识：CPU 是 PC，FSM 是状态编码，流处理是计数器。缺省 `-` |
| `State` | `%s` | 通用进度标识：CPU 是指令字，其他设计可填事务 ID / 通道号。缺省 `-` |
| `Ids` | `k=v` 列表 | 仅列被写的存储单元，如 `x1=0000002a,fifo_cnt=3`；多个用 `,` 分隔；无更新写 `-` |
| `Ext` | `k=v` 列表 | 扩展键值，多个用 `;` 分隔；值只允许 `[A-Za-z0-9_.+-]`；无扩展写 `-` |

**硬约束**：任何列内不得出现换行、制表符、引号、花括号或 JSON 片段；违反 → E11 并给出行号与列号，**不允许容错跳过**。RTL 侧只允许一行一个 `$fwrite` 常量格式串，例如：

`` $fwrite(f, "%0t\t%0d\t%s\t%s\t%s\t%s\n", $realtime, cyc, loc, state, ids, ext); ``

> **命名刻意去 CPU 化**：`Loc`/`State`/`Ids` 是 `PC`/`Instr`/`Regs` 的语义超集。CPU 项目读起来稍绕，但非 CPU 项目不必造假字段。
> **兼容层**：`normalize --flavor cpu` 允许旧 RTL 的 `PC/Instr/Regs` 列序，映射到 `Loc/State/Ids`；映射表与真实列序由 P1 用官方 tracer 校准。

**扩展键声明（写在 `Ext` 列，由 flavor 声明）**：

| `Ext` 键 | 归属 | 语义 | 消费方 |
|---|---|---|---|
| `arc=src.port>dst.port:t` | 核心 | 边活跃度，`t` 为本周期是否翻转；零翻转连线在前端标红（疑似死代码） | 带宽/翻转统计 |
| `cdc=id:afull:cnt` | 核心 | 跨域桥水位，任何多时钟设计都有 | CDC 视图、告警 |
| `pipe`、`ctrl`、`regw`、`icache`、`dcache`、`dec` | `plugins/cpu` | 流水线槽位、气泡原因、写回、Cache 状态、解码文本 | 流水线时空图、Cache 视图 |
| `txn`、`stall` | `plugins/bus` | 事务节拍与阻塞原因 | 事务时序图、通道占用率 |
| `fsm` | 用户 / plugin | `name:from:to:cond` | 状态机转移图 |

规则：`Ext` 内多个键用 `;` 分隔，单个键值内用 `:` 分隔，值只允许 `[A-Za-z0-9_.+-]`；**未声明的键 → W15**（保留并在前端表格原样显示，不参与计算）；已声明键但格式非法 → E11。核心只解释 `arc` 与 `cdc`，其余键交给对应 flavor 处理器。

**JSONL 输出（`normalize` 流式转换，不是 RTL 写，产物 `trace/<run>.jsonl`）**：

```jsonl
{"cycle":0,"time_ns":0,"loc":"-","state":"IDLE","ids":{"fifo_cnt":0},"arc":[],"cdc":[]}
{"cycle":1,"time_ns":20,"loc":"-","state":"RX","ids":{"fifo_cnt":1},"arc":[{"edge":"uart0.tx->fifo0.push","toggle":1}],"cdc":[]}
```

CPU 专属字段（`pipe/ctrl/dec`）只在 `--flavor cpu` 时出现，由 plugin 的 trace 处理器补齐并放到 `p_cpu` 命名空间；核心 normalize 不做指令解码，也不做反汇编。

> **核实状态（P1 首要任务）**：cv32e40p 官方 tracer 的真实列序在本次调研中**未核实**（官方文档页抓取被拦截）。P1 必须读 `tb/cv32e40p_tracer.sv` 与 `docs/source/tracer.rst`，把真实字段与示例行写进 `tests/golden/trace/cv32e40p_sample.tsv`；若与 `--flavor cpu` 的映射假设不符，**以官方为准修订 plugin 解析器**，核心 6 列不受影响。

### 4.5 版本兼容与迁移策略

- 每个 schema 文件内 `schema_version` 为**合法 semver**：`rvgen` 为 `1.1.0`，`node_graph`/`layout`/`trace` 为 `1.0.0`。**patch** = 只改描述/示例，不影响校验 → 直接加载；**minor** = 新增 optional 字段或枚举新增取值 → 直接加载并打 `I02`；**major** = 新增/删除 required、改字段语义、删除字段 → 拒绝加载，要求显式 `rvgen migrate`。给新 required 字段补默认值**仍按 major 发布**，不能因为"能补默认"就降级为 minor。
- 迁移链是**有序纯函数列表** `TRANSFORMERS = [("1.0.0"→"1.1.0", fn), ("1.1.0"→"2.0.0", fn)]`，加载时循环套用到当前版本，**不允许跨级跳变**，每步产物立即用目标版本 schema 校验。`1.0.0→1.1.0` 的具体内容：删 `profiles`、`modules[].stage/stage_index` → `x-cpu-stage/x-cpu-stage_index`、`ports[].kind` 去掉 `axi`、`interfaces[].type` 改为开放注册表。
- 迁移前自动把原文件快照到 `.rvgen/snapshots/`；`migrate --dry-run` 只输出 JSON Patch 差异不落盘。
- 前端 `contracts/*.ts` 由 schema 生成（`json-schema-to-typescript`，属前端 devDependency），**生成物进 git**，CI 校验"schema 改了但 contracts 没重新生成"即失败。

### 4.6 `trace_summary.json`（动态指标，不进 git）

由 `rvgen trace summary <run.jsonl>` **独立生成**（输入是 `normalize` 的 JSONL，需同时加载静态 `node_graph.json` 做边映射；不与 `normalize` 绑定），与 `node_graph.json` 完全分离，`check` 永不读取。结构：

```json
{
  "schema_version": "1.0.0",
  "trace": "trace/uart_smoke.jsonl",
  "flavor": "core",
  "cycles": 20000,
  "timescale_ns": 1.0,
  "nodes": [{"id": "mod:uart", "active_cycles": 18342, "util": 0.917}],
  "edges": [{
    "id": "mod:uart.tx->mod:fifo0.push",
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

- `bits_per_cycle = bytes × 8 / cycles`；`gbps = bytes × freq_hz / cycles / 1e9`（十进制 GB）；`toggle_rate = toggles / (width_bits × cycles)`。
- `utilization = 实测 bits_per_cycle / node_graph 里的静态 derived bits_per_cycle`；静态侧没有 derived 时 `utilization=null`；`>1.0` → **W05**（声明位宽不足或统计口径有误）。
- 由 `rvgen trace summary <run.jsonl>` 显式生成；`serve` 通过 `GET /api/trace-summary` 读取；文件缺失或版本过旧 → `I08`，只提示不阻断。
- `trace_summary.json` 与 `trace/*.jsonl` 默认进 `.gitignore`；需要留档时由用户显式 `git add -f`。

## 5. 核心算法规约

### 5.1 端口宽度解析与对齐（E01 / W03）

> 分两段：**解析链**（步骤 1–4，决定 `width_bits`，失败 → E01）与**连接对齐**（步骤 5–6，决定扩展/截断，触发 → W03）。`resolve_width()` 只负责解析链，见附录 C。

```
A. 解析链（resolve_width，纯函数）
  1. port.width 是 int                -> 直接用            (来源 literal)
  2. port.width 是 str 且是已声明参数 -> 取 params 值；若引用参数无 default，
                                        递归解析（深度上限 8，超过 E01 cycle）
  3. port.width 是 str 且是常数表达式 -> 只允许 "A+B" / "A*B" / "A-1" 三形态，
                                        操作数须为 int 或已解析参数，安全求值
  4. port.kind in (valid,ready,clock,reset) -> 隐式 1        (来源 implicit)
B. 连接对齐（graph 建边阶段，不改 port 声明）
  5. 对端宽度已确定               -> 以声明侧为准做扩展/截断 + W03
  6. 两侧都未解析且无法继承        -> E01（一次性列出所有失败端口）
```

**禁止** `eval()`；表达式用 `ast.parse(mode="eval")` + 白名单节点（`BinOp(Add|Mult|Sub)`、`Constant(int)`、`Name`）后手算。

### 5.2 USER 块合并算法（6 步）

> 生成流水线（文字版，替代原图 2）：`load → model → graph → emit（渲染 + USER 块合并）→ digest/fingerprint → atomic write`。六段中只有 `emit` 与 `write` 可能触碰用户文件，保护措施集中在第 5.2、5.3、5.7 节。

```
merge(existing_text, generated_text, module_name) -> (new_text, diags):
  # 步骤 1  解析既有文件
  old = split_markers(existing_text)   # -> {block_id: body}，body 保持原字节
        # marker 正则（re.MULTILINE，兼容 CRLF）：^[ \t]*//[ \t]*rvgen:(user-begin|user-end)[ \t]+([A-Za-z0-9_.-]+)[ \t]*\r?$
        # 嵌套 begin 同名 -> E06；end 无匹配 begin -> E06；跨模块 id -> E06
  # 步骤 2  解析新生成文本，得到本轮期望的 block id 集合 expect_ids
  # 步骤 3  匹配：old.id == gen.id 按 id 合并；gen 里新增的 id 用空 body
  # 步骤 4  指纹比对（见 5.3）：契约未变 -> 原样回填 body；契约变了 ->
  #         仍回填 body（用户代码优先）但发 W01，并在 USER 块**外**的生成区
  #         插入/更新一行 `// rvgen:warn contract changed since <old_fp> -> <new_fp>`
  #         同一 block 只保留一行；USER 块内字节绝不改动
  # 步骤 5  孤儿处理：old 中不在 expect_ids 的块 -> 写
  #         .rvgen/orphaned/<ts>/<module>.<id>.v.bak，记录 I04，绝不丢弃
  # 步骤 6  组装文本：生成区整体用本轮渲染结果替换（不做增量追加），
  #         USER 块 body 从 old 原样回填；然后 -> 写 <file>.tmp.<pid>
  #         -> fsync -> os.replace(tmp, dst) -> fsync 目录（见 5.7）
```

**frozen 模块短路**：`status=frozen` 的模块若已存在文件，`emit` 直接跳过并打 `I03`，除非 `--force-unfreeze`。

### 5.3 指纹（fingerprint）

**进指纹**（任一变化 → 契约变更告警）：端口名/方向/位宽解析结果/端口**声明顺序**、`params` 名与默认值、模块 `clock`、`kind`、接口展开后的信号集合（名/方向/位宽）与 `dir_flip`、参与生成的 `x-<plugin>-*` 字段（如 `x-cpu-stage`）。
**不进指纹**（变了不打扰用户）：`doc`、`todo`、`status`、`loc`、注释、YAML 映射键的书写顺序（数组元素顺序属于契约，见上）、`layout`、`trace_summary`。
算法：`sha256(json.dumps(canonical_contract, sort_keys=True, separators=(",",":")))[:16]`。`canonicalize()` 只排序**对象键**，**不排序端口/模块数组**；否则"端口顺序变了"永远检测不到。

### 5.4 顶层连线与例化（v1.1 重写：显式映射为准，不再靠"同名"猜）

**为什么改**：v1 的"同名端口自动 connect"在单核内成立，在多 IP SoC 里会连错——`uart.tx` 与顶层引脚 `tx`（对外输出）同名、`cpu.clk` 与 `uart.clk` 同名、`debug_en` 悬空时该接 0 还是该引出到顶层无法判断。隐式约定在规模上去之后必然反噬，所以升级为**显式声明 + 机器校验完整性**。

**连线优先级（高→低，命中即停）**

```
resolve_connection(top_port_or_internal_wire):
  1. top.ports[] 显式映射        -> 唯一权威，直接用；同一输出多驱动 / 端口不存在 -> E13
  2. port.connect: "inst.port"   -> 模块级显式覆盖（用于非名匹配的特例）
  3. interfaces[] 束连接         -> 按接口模板的 (信号名, 方向) 批量展开；
                                    dir_flip=true 时主从方向翻转（master↔slave）
  4. 同名推断                    -> **仅作候选**：生成时写入
                                    `.rvgen/wiring_suggestions.yaml`，打 W12，
                                    必须 `rvgen graph --accept-wiring`（隐含 --write）
                                    才会并入 top.ports
  5. 都没有                      -> 输入查 port.default / top.tieoffs，仍无则 E14
```

**四条硬约束（不可放宽）**
- **`role: clock` / `role: reset` 的顶层端口永不参与同名推断**，只能由显式映射或 `modules[].clock` 引用驱动。这是防"把 clk 误连成数据口"的最后一道闸。
- 一个顶层输出只能有**一个**驱动源；两个输出项共用同一 `from`，或同名 `top.ports[].name` 重复声明 → E13。
- `top.ports[]` 未覆盖任何模块的必填输入，且无 `default`/`tieoff` → E14（**列出全部缺失项一次性报出**，不要报一个就停）。
- `top.ports[]` 声明了但找不到对应模块端口 → E02，提示疑似拼写错误并给出 `difflib` 最近邻建议。
- 最终连线结果只由 `rvgen graph --write` 写入 `node_graph.json`；`sync` 只读取该结果生成 Verilog，绝不自行改图。

| 环节 | 规则 |
|---|---|
| wire 命名 | `<inst>_<port>`；同名冲突加 `_<模块名>` 后缀；长度上限 64，超出用 `w<sha1[:6]>` 并记 W08 |
| 单源多扇出 | 一个驱动 → 一条 wire，多个负载直接挂同一 wire，**不复制驱动** |
| 位宽不一致 | 驱动宽 > 负载宽 → 截断 + W03；驱动窄 → 零扩展 + W03；`kind=clock/reset` 位宽不一致 → E08 |
| 浮空输入 | 有 `port.default` 用之；否则 `valid/ready`→`1'b0`、`clock/reset`→ 报错 E07、数据口 → 接 `{(W){1'b0}}` + W02 |
| 未连接输出 | 一律 W04 告警并生成 `/* rvgen: unused output <p> */` 注释，不自动加 `wire` 以免仿真警告被吞 |
| 参数透传 | 子模块参数缺省取 YAML `default`；顶层用 `parameter` 声明并 `defparam` 禁用，统一 `#(.WIDTH(WIDTH))` 具名传递 |
| 多时钟分组 | 按 `domain_id` 分组生成 `/* ===== clock domain: <id> (<freq>) ===== */` 段落，跨域边若没有对应 `cdc[]` 声明 → E08 |
| CDC 桥例化 | 统一从 `rtl/gen/cdc/` 例化：`two_ff` / `pulse_sync` / `handshake` / `async_fifo` / `gray_bus`；文件名与模块名同名，实例名 `u_cdc_<id>`；`cdc[]` 非空但文件缺失 → E05（先跑 `rvgen gen cdc`），不再内联生成 |
| **FuseSoC 集成** | 同目录产出 `<top>.core`：`filesets` 列 `rtl/gen/**/*.v` + `rtl/*.v`、`depend` 列子 core、`parameters` 映射 YAML params、`targets` 给 `sim`(默认 Icarus；可选 Verilator) / `lint`(Icarus `-Wall`；装了 Verible 则优先) / `synth`(Yosys) 三档。**用户跑 `fusesoc run`，我们不实现 runner**；本机未装 fusesoc 时用 `rvgen check --lint` 直接调 iverilog 替代 |

### 5.5 拓扑排序（Kahn）与环路径回溯

```
topsort(nodes, edges, sink) -> order:
  indeg = {n: 入度}; pred = {n: None}; 只算 kind in (data, handshake, bundle) 的边
  q = deque([n for n in nodes if indeg[n]==0 and not is_clock_reset(n)])
  while q: u=q.popleft(); order.append(u)
           for v in succ(u):
               pred[v] = u
               indeg[v]-=1
               if indeg[v]==0: q.append(v)
  if len(order) < len(target):
      # 环路径回溯：从剩余节点里任取 s，沿 pred 链走
      s = first_unvisited(nodes, order); visited={}; path=[]
      while s is not None and s not in visited:
          visited[s]=len(path); path.append(s); s=pred[s]
      cycle = path[visited[s]:] + [s] if s is not None else path
      sink.add(Diagnostic(E03, error, where=cycle,
        hint="组合环：" + " -> ".join(f"{n.module}.{n.port}" for n in cycle)
             + "；在回边插一级寄存器或由 plugin 声明打断点"))
      return []            # 不抛异常：统一走 DiagnosticSink，由调用方决定退出码
  return order
```

**边界条件**：`clock`/`reset`/`param` 边**不参与**拓扑（否则时钟树必然成环）；自环（同模块同端口对）单独报 E03 并给出单行提示；多解时先按 plugin 提供的 `order_key`（如 cpu 的 `x-cpu-stage_index`），再按声明序稳定排序；核心只保证"声明序"这一层，保证生成结果**逐字节可复现**（这是幂等验收的前提）。

### 5.6 布局算法选型与超限降级

| 规模 | 策略 |
|---|---|
| ≤ 80 节点 | 单图，dagre 分层（默认 LR），`pinned` 节点固定 |
| 80 < n ≤ 200 | 按 `domain_id` 或 plugin 提供的分组键拆 subgraph，每簇一张子图 + 簇间聚合边；elkjs 在 Web Worker 里算 |
| 200 < n ≤ 500 | 预渲染 SVG 底图（离线 elk 一次算好存 `.rvgen/cache/layout.<view>.json`），交互只在高亮/悬停层；拖拽时不做重排 |
| > 500 | **超出受支持规模**（§1.2 上限 500），进入只读邻域模式：只提供搜索定位 + 邻域展开（`hidden` 属性控制，符合官方建议 [1]），并打 W06；不承诺交互性能 |

Worker 协议：`{type:"layout", algo, graph, options}` → `{type:"done", positions, algo_version}`；Worker 内 `try/catch` 后必须回 `{type:"error", message}`，主线程超时 10 s 取消并降级到 dagre 同步布局。**ECharts 实例、Worker、ResizeObserver 必须在视图卸载时销毁**，否则切视图次数一多就内存泄漏（第 11 章 R05/R06）。

### 5.7 原子写与崩溃一致性

```
atomic_write(dst, text, bak_dir):
  tmp = dst.parent / f".{dst.name}.tmp.{os.getpid()}"
  fd = os.open(tmp, O_WRONLY|O_CREAT|O_TRUNC, 0o644)
  os.write(fd, text.encode("utf-8")); os.fsync(fd); os.close(fd)
  if dst.exists(): copy2(dst, bak_dir / f"{dst.name}.{ts}")   # 保留最近 20 份
  os.replace(tmp, dst)          # 同文件系统内原子；跨盘会 EXDEV -> 报错不吞
  fsync_dir(dst.parent)         # Windows 不支持目录 fd 的 fsync：跳过并记 I01（msvcrt 无 commit 接口，不伪造）
```

**Windows 特有问题**：`os.replace` 对只读目标、被 VSCode 占用的文件会 `PermissionError` → 重试 3 次（50/150/400 ms 退避），仍失败则报 `E12` 并保留 `.tmp` 文件告知用户路径；路径一律 `pathlib.Path` + `resolve()`，禁止字符串拼 `\\`。

## 6. 模块划分与接口定义

> 通用错误模型（唯一报错方式，禁止裸 `print`）：
> `Diagnostic(code: str, severity: Literal["error","warning","info"], where: Location|list[Location], message: str, hint: str|None = None)`
> `Location = {file: Path|None, line: int|None, col: int|None, json_path: str|None, node_id: str|None}`
> 全局 `DiagnosticSink` 收集 → CLI 渲染成 `file:line:col: code severity message` + 缩进 hint。
> **退出码唯一口径（全项目只此一套）**：`0` 成功；`1` 存在 E 级诊断**或** CLI 用法错误；`2` 只有 W 级诊断且显式 `--strict`；`3` 环境/IO 失败（git 不可用、协议注册失败、权限、解释器/DLL 缺失）。§6.1、§7.4、§7.5、pre-commit 必须与此一致。

### 6.1 模块清单

| 模块（owner 文件） | 职责 | 公开签名 | 错误语义 | 谁可调 / 禁止 |
|---|---|---|---|---|
| `loader.py` | 读 YAML（含锚点展开上限）、**合并 plugin schema**、校验 | `load(path, plugins) -> tuple[DesignModel, list[Diagnostic]]` | 文件缺失/解析失败 → E09；锚点嵌套 >10 → W10；未知 `x-` 前缀外字段 → E09 | `cli`/`server` 可调；**禁止** import graph/emitter |
| `plugins.py` | **plugin 发现与注册**（`entry_points(group="rvgen.plugins")` + `abc` 契约）[12] | `discover() -> list[Plugin]`；`Plugin{id, schema, rules, views, trace_flavors, node_types}` | plugin 加载失败 → W11 并跳过该 plugin，**不得拖垮核心** | 只被 `loader`/`cli` 调；**禁止**被 graph/emitter import |
| `importer.py` | **从 `.v` 反生成 `rvgen.yaml` 骨架**（正则/词法级解析模块头、端口、parameter） | `import_verilog(src) -> tuple[dict, list[Diagnostic]]` | 解析不出的端口 → I05，要求人工补；**不做**表达式与 `generate` 展开 | 只被 `cli import` 调；**禁止**写任何 `.v` |
| `model.py` | `DesignModel` 与子结构（dataclass，frozen） | `DesignModel.validate_semantic() -> list[Diagnostic]` | 引用悬空 → E05 | 只被 loader/graph/emitter 用；**禁止** IO |
| `graph.py` | YAML → `NodeGraph`：建节点、推边、算静态带宽、CDC 检测；**不挂动态指标** | `build(m: DesignModel) -> NodeGraph`；`write(g, path)` | 环 → E03；跨域无边 → E08 | **禁止**读文件（除显式 write）、**禁止**布局、**禁止**写 trace |
| `emitter.py` | Jinja2 渲染 + USER 块合并 + 顶层例化 + CDC 基础模块 | `emit(m, g, out_dir, sink) -> list[Path]`；`render_top(m,g) -> str` | marker 破损 → E06；原子写失败 → E12 | 只被 `cli.sync` 调；**禁止**改 YAML、**禁止**改图 |
| `checker.py` | 语义 diff | `diff(expected: NodeGraph, actual: dict) -> list[Change]`；`check(...) -> int` | 不一致 → 1；仅 W 且 `--strict` → 2；环境/IO → 3 | **禁止**写任何文件（`--fix` 由 cli 调 emitter 与 graph） |
| `trace.py` | TSV → JSONL、`trace_summary.json` 聚合 | `normalize(src, dst, flavor) -> Stats`；`summary(g, jsonl) -> dict` | 列数/Ext 格式非法 → E11；未知 Ext 键 → W15 | **禁止**改 RTL、**禁止**改 `node_graph.json` |
| `digest.py` | 契约规范化与指纹 | `canonicalize(node) -> dict`；`fingerprint(node) -> str` | — | 纯函数，谁都能调，**禁止** IO |
| `figures.py` | 从 NodeGraph 派生**核心三视图**（数据流/时钟树/统计）；plugin 视图走注册表 | `build_core_views(g) -> dict[str, ViewGraph]`；`register_view(plugin, fn)` | 视图类型未知 → E04；plugin 视图缺 renderer → W07 | **禁止**布局（只出逻辑坐标） |
| `layout.py` | **infra 层**：布局服务（dagre/elk 的 Python 侧预计算与缓存），被 server 调 | `layout(view, algo, opts, cache) -> Positions` | 超时 → 降级 + W06 | 被 server 调；**禁止**改图数据；**不属于 core** |
| `gitw.py` | `git status --porcelain` 解析、分支/HEAD 状态 | `state(repo) -> GitState`；`watch(repo, cb, debounce=0.4)` | git 不可用 → W10，不影响主流程 | **禁止**执行写类 git 命令 |
| `server.py` | FastAPI + SSE 事件总线；`serve --project <dir> --port 8123` | `GET /api/graph`、`/api/events`、`/api/trace-summary`、`/api/layout`、`POST /api/layout`、`POST /api/reload`、`GET /api/health` | SSE 断线由客户端重连；**禁止**自动触发覆写；**禁止**写 `node_graph.json` | 调 core，**禁止**被 core import |
| `rvopen.py` | `rvgen://` URL 构造与三平台协议调用 | `url_for(loc) -> str`；`open(loc) -> bool` | 协议未注册 → I06 + 打印手动命令 | 只被 server 调 |
| `fusesoc.py` | 生成 `<top>.core`（filesets / depend / parameters / targets）[6] | `emit_core(m, out_dir) -> Path` | 无模块/无 fileset → E09 | 只被 `cli.gen` 调；**禁止**执行 `fusesoc run` |
| `cli.py` | 命令分发 | `rvgen {init,import,sync,graph,yaml,check,trace,serve,gen,plugin,migrate,doctor}` | 退出码唯一口径见第 6 章开头：`0/1/2/3` | 唯一入口；**禁止**业务逻辑内联 |

**统一禁令**：任何模块不得 `except: pass`；不得 `print`；不得修改 `sys.path`；不得在 `core/` 里 import `fastapi`/`watchdog`。

### 6.2 规则码表

| 码 | 级别 | 触发条件 | 修复建议 |
|---|---|---|---|
| E01 | error | 端口位宽解析链（§5.1 步骤 1–4）失败 / 表达式非法 | 给参数加 `default` 或写死 `width` |
| E02 | error | `top.v` 例化缺模块或端口数不匹配 | 跑 `rvgen sync` 重生成 |
| E03 | error | 组合环（含自环） | 回边插寄存器，或由 plugin 声明打断点 |
| E04 | error | 视图类型/布局算法未知（plugin 未注册） | 检查 `view kind` 拼写与 plugin 注册；renderer 缺失走 W07 |
| E05 | error | 引用悬空（clock/domain/param/interface type/kind 未注册） | 修正引用名或补声明 |
| E06 | error | USER marker 残缺/嵌套/重名 | 手动修复 marker 对，再看 `.rvgen/orphaned/` |
| E07 | error | clock/reset 输入浮空且无 default | 补 `connect` 或 `default` |
| E08 | error | 跨域直连未声明 CDC / 时钟复位位宽不符 | 在 `cdc[]` 补桥声明 |
| E09 | error | schema 校验失败（结构/类型） | 按 hint 的点号路径定位字段 |
| E10 | error | 覆写 `status=frozen` 的模块 | 改 status 或加 `--force-unfreeze` |
| E11 | error | trace 列数不符 / Ext 键值格式非法 / 元数据行缺失 | 检查 RTL `$fwrite` 格式串与 `#rvgen-meta` 行 |
| E12 | error | 原子写失败（权限/占用/跨盘 EXDEV） | 关闭占用进程，检查磁盘与同盘 tmp 目录 |
| E13 | error | `top.ports` 冲突：同一输出多驱动、端口不存在、重复声明 | 修正 `top.ports`，避免同名歧义 |
| E14 | error | 模块必填输入未被 `top.ports`/default/tieoff 覆盖 | 补映射或默认值；工具会一次性列全 |
| E00 | error | CLI 用法/参数错误 | 看 `--help`；退出码仍为 1 |
| W01 | warning | USER 块契约已变更（fp 不同） | 核对端口表，手动适配块内逻辑 |
| W02 | warning | 数据输入浮空被接 0 | 确认这是有意行为，否则补连线 |
| W03 | warning | 位宽截断/扩展 | 显式写 `width` 消除歧义 |
| W04 | warning | 输出未连接 | 接上或加 `/* rvgen: unused */` 注释 |
| W05 | warning | 实测带宽 > 声明带宽（util>1） | 核对位宽与统计口径 |
| W06 | warning | 图规模超限触发降级 | 拆 subgraph 或开启邻域展开 |
| W07 | warning | plugin 注册了视图但前端 renderer 缺失 | 装 plugin 的前端包或禁用该视图 |
| W08 | warning | wire 名超长被哈希 | 缩短实例名或端口名 |
| W09 | warning | CDC 声明两端同域 | 删除无用声明或修正 domain |
| W10 | warning | 缺 `loc` / git 不可用 / 锚点过深 | 补 loc 或忽略（不影响生成） |
| W11 | warning | plugin 加载失败已被跳过 | 检查该 plugin 的依赖与 schema_version 兼容区间 |
| W12 | warning | 同名推断候选未确认（未跑 --accept-wiring） | Review `.rvgen/wiring_suggestions.yaml` 后并入 `top.ports` |
| W13 | warning | `interfaces[]` 模板参数未替换 | 补全 params，否则生成端口名含字面花括号 |
| W14 | warning | `rvgen import` 有端口未能解析 | 手工补进 rvgen.yaml，见 I05 清单 |
| W15 | warning | trace `Ext` 出现未声明的键 | 补 flavor 声明或删除该键；不参与计算 |
| I01 | info | Windows 目录 fsync 跳过 | 无需处理 |
| I02 | info | schema minor 迁移已补默认值 | Review 后提交 |
| I03 | info | frozen 模块已跳过 | — |
| I04 | info | USER 块已删除并备份到 `orphaned/` | 查看备份；确需保留则改回 YAML |
| I05 | info | `import` 跳过了 `` `ifdef `` 包裹或无法解析的端口 | 人工补写，工具不猜 |
| I06 | info | `rvgen://` 协议未注册 | 运行 `scripts/register.*` |
| I07 | info | 检测到未启用 plugin 的 `x-` 字段，已原样保留 | 启用对应 plugin 或删字段 |
| I08 | info | `trace_summary.json` 缺失或版本过旧 | 重跑 `rvgen trace summary` |
| I09 | info | 去抖队列溢出，已丢弃最旧事件 | 降低保存频率；不影响静态文件一致性 |

### 6.3 plugin 规则码（`P<PLUGIN>-<nn>`）

- 格式固定：`P` + plugin 大写 id + `-` + 两位序号，例如 `PCPU-01`、`PBUS-03`；级别仍只用 `error/warning/info`，渲染格式与核心码一致。
- plugin 只能发自己的 `P*` 码，**不得占用 E/W/I 命名空间**；核心也不得发 `P*` 码。
- 示例：`PCPU-01` = `x-cpu-stage` 不在 `plugins.cpu.lanes`；`PCPU-02` = 同 lane 内 `x-cpu-stage_index` 重复；`PBUS-01` = AXI 端口缺 `valid/ready` 配对。
- `--strict` 对 `P*` warning 同样生效；关闭 plugin 时其 `P*` 码不出现。

## 7. Git 闭环设计

### 7.1 watchdog 去抖与事件语义

**已知语义事实**：编辑器保存常触发多次 `on_modified`（VSCode/IDEA 先写临时文件再覆盖，表现为多次修改事件）[7][8]；因此必须去抖 + 比较内容摘要，不能在回调里做重活 [7]。

```
class Debounce(EventHandler):
    def on_any_event(self, e):
        p = Path(e.src_path)
        if e.is_directory: return
        if p.parent.name == ".rvgen":
            if p.name != ".git-event": return          # 只放行 hook 事件文件
        elif p.parent.name in {"node_modules",".git","__pycache__"}: return
        elif p.suffix in {".swp",".swx",".tmp",".part"} or p.name.startswith("."): return  # 编辑器临时文件（先判 .rvgen 再判点文件）
        self.pending[p.resolve()] = time.monotonic()      # 覆盖写：只留最后一次
    # 定时器每 100ms 扫描：距最后事件 >= 0.4s 且内容 sha256 与上轮不同 -> 发事件
```

要点：`FileMovedEvent`/`FileCreatedEvent` 同样入队（原子写表现为 rename，只看 `on_modified` 会漏）；`rvgen.yaml` 用 400 ms 去抖（用户感知即可），`rtl/*.v` 用 800 ms 且只在 `check` 模式下触发；队列满 64 条时丢弃最旧并打 I09。**去抖窗口推荐 300–500 ms，默认 400 ms**（低于 300 ms 会因原子写双事件重复推送，高于 500 ms 手感变钝）。

`git status --porcelain` 解析要点：输出为 `XY PATH`，`X` 是暂存区状态、`Y` 是工作区状态；`??` 未跟踪、`!!` 被忽略、重命名行形如 `R  old -> new`；路径含空格/非 ASCII 时**不要**假设 `core.quotePath=false`，一律加 `-z` 用 `\0` 分隔解析并自己 `codecs.escape_decode`；子模块输出首字节为 `m`。只解析，**不执行**任何写类 git 命令。

### 7.2 SSE 与 WebSocket 的选型结论

**选 SSE**。理由：① 流量单向（服务端→浏览器），WS 的双向能力用不上；② SSE 自带 `id:`/`Last-Event-ID` 与浏览器自动重连；③ 走普通 HTTP，反向代理只需 `proxy_buffering off;`，不升级协议；④ 无需自研心跳与订阅表。`EventSource` 在断线 3 s 后自动重试，服务端每 15 s 发 `:keep-alive` 注释帧防止代理超时。

**断线续推的真实实现（不是口号）**：服务端维护一个容量 64 的环形缓冲 `deque[(event_id, event, data)]`；每次 `publish` 分配单调递增 `id` 并入缓冲。客户端带 `Last-Event-ID` 重连时，先把缓冲中 `id > last_id` 的事件按序补发，再切到实时流；若 `last_id` 已滑出缓冲，则发一条 `event: resync`、`data: {}`，前端据此**主动** `GET /api/graph` 一次（仍然不是自动 reload，只是补齐快照）。每个订阅者一个 `asyncio.Queue(maxsize=128)`；`publish` 使用 `put_nowait`，队列满即把该订阅者标记为 stalled 并断开（前端随后重连走 `Last-Event-ID` 补发），**绝不 `await` 阻塞其他客户端**；慢客户端因此最多丢失"断开前未消费"的事件，静态文件一致性不受影响。

**事件协议**（`Content-Type: text/event-stream`）：

| event | data | 触发 |
|---|---|---|
| `yaml_changed` | `{path, sha256, at}` | debounce 后 rvgen.yaml 内容真变 |
| `rtl_changed` | `{files[]}` | 生成物或 USER 块变化 |
| `regenerated` | `{by, at, diagnostics[]}` | `sync` 完成 |
| `git_state` | `{branch, head, dirty, counts:{M,A,D,UU}}` | 状态变化或每 30 s 心跳 |
| `check_result` | `{ok, changes[], duration_ms}` | check 完成 |
| `resync` | `{}` | `Last-Event-ID` 已滑出 64 条环形缓冲；前端必须全量重拉 graph 与 layout |

**前端手动 reload 与 layout 保留合并策略**：收到 `yaml_changed` 只把顶栏徽标变黄、顶部出现"源已变更，点击重新加载"按钮，**绝不自动请求 graph**。点击后：

```
reload():
  old = store.graph; oldLayout = store.layout
  fresh = await api.getGraph()
  store.graph = fresh
  store.layout = mergeLayout(fresh, oldLayout)   # 按 node.id 匹配
  # 新节点：交给布局算法算初值；消失节点：layout 条目移入 layout._stale（30 天后清理）
  # pinned/collapsed/control_points 一律保留；用户未手动改过的节点位置跟随新布局
```

### 7.3 Git hook 脚本（无守护进程场景的备选通道）

`scripts/hooks/post-commit` 与 `post-checkout`（内容一致，参数不同）：

```sh
#!/usr/bin/env sh
# 骨架，需按接口定义补齐：仅做"标记 + 轻量校验"，不自动覆写工作区
set -eu
repo="$(git rev-parse --show-toplevel)"
case "${1:-}" in post-checkout) [ "${3:-0}" = "1" ] || exit 0 ;; esac   # 仅分支切换
if command -v rvgen >/dev/null 2>&1; then
  rvgen check --quiet || { echo "rvgen: node_graph.json 与 rvgen.yaml 不一致；显式更新：rvgen graph --write" >&2; exit 1; }
fi
mkdir -p "$repo/.rvgen"
touch "$repo/.rvgen/.git-event"     # server 若在运行会拾取并推 git_state；watchdog 必须放行此文件
```

`pre-commit`（走 pre-commit 框架，等价于 JS 侧 husky 的角色 [9]）：

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: rvgen-check
        name: rvgen check（YAML 与图一致性）
        entry: rvgen check
        language: system
        pass_filenames: false
        files: '(rvgen\.yaml|node_graph\.json|py/rvgen/.*\.py|plugins/.*\.py)$'
      - id: rvgen-sync-dry
        name: rvgen sync --check（生成物是否落后）
        entry: rvgen sync --check
        language: system
        pass_filenames: false
```

**等价关系说明**：Python 侧用 `pre-commit` 框架，Node 侧用 husky/lint-staged；二者都在 `git hooks` 生命周期上跑脚本，husky 负责装钩子、`lint-staged` 负责只跑暂存文件 [10]。我们**只用 pre-commit 框架**统一管 Python 与前端检查（它支持 `language: node`），避免两套钩子互相覆盖 `.git/hooks`。

### 7.4 CI 配置示例

```yaml
# .github/workflows/ci.yml（骨架）
name: rvgen-ci
on: [push, pull_request]
jobs:
  gate:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11.6', cache: 'pip' }
      - uses: actions/setup-node@v4
        with: { node-version: '24', cache: 'npm', cache-dependency-path: web/package-lock.json }
      - run: sh scripts/npm-offline.sh        # 从 vendor/npm/*.tgz 填充 npm cache，不联网
      - run: pip install -e .[dev]
      - run: rvgen check --strict             # 图与 YAML 一致；schema_version 严格匹配
      - run: rvgen sync --check               # 生成物是否落后（只读检查）
      - run: cd web && npm ci --offline && npm run typecheck && npm run test:unit && npm run build
      - run: cd web && npx playwright install chromium && npm run test:e2e
      # P0 只跑上面这些；覆盖率门槛从 P1（有测试之后）启用：
      # - run: pytest -q --cov=rvgen --cov-fail-under=90
      # - run: pytest -q tests/checker --cov-fail-under=95
```

`--strict` 的含义：所有 `warning`（含 plugin 的 `P*` warning）也按 error 处理（CI 用，本地不用），并且要求 `node_graph.json` 里的 `generated_by` 版本与当前 CLI 版本一致。**P0 的绿灯标准是**：`check --strict`、`sync --check`、前端 typecheck/build 通过；覆盖率命令在 P1 首次启用，避免"空仓跑覆盖率必红"。

### 7.5 CLI 表面（v1.2 完整命令集）

| 命令 | 作用 | 退出码 |
|---|---|---|
| `rvgen init [PATH] [--preset minimal\|uart\|rv32i]` | 建目录 + `rvgen.yaml` 样例；`--preset` 决定样例域 | 0/1/3 |
| `rvgen import <file.v> [-o rvgen.yaml]` | 从已有 Verilog 反生成声明骨架（W14/I05 报告未解析项） | 0/1/3 |
| `rvgen sync [--dry-run\|--check] [--strict] [--update-graph] [--force-unfreeze]` | 生成骨架 + top + CDC 基础模块 + `.core`，合并 USER 块；**默认不写 `node_graph.json`**；`--update-graph` 等价显式 `graph --write`；`--check` 为只读模式（等价 `--dry-run` 且有问题即非零退出，供 pre-commit/CI 用） | 0/1/2/3 |
| `rvgen graph [--write] [--check] [--accept-wiring] [--list-cdc]` | 计算**静态**图；**只有 `--write` / `--accept-wiring` 才落盘**；`--check` 只比较不写；`--list-cdc` 打印跨域桥清单；trace 指标一律不进此命令 | 0/1/3 |
| `rvgen yaml expand [-o -]` | 展开 YAML 锚点/别名并打印（只读，供 review） | 0/1/3 |
| `rvgen check [--format github\|json] [--fix] [--strict] [--quiet]` | 语义 diff，不写文件（`--fix` 除外） | 0/1/2/3 |
| `rvgen trace normalize <src> [-o out.jsonl] [--flavor core\|cpu\|bus\|auto]` | TSV → JSONL，逐行流式 | 0/1/3 |
| `rvgen trace summary <run.jsonl> [-o trace_summary.json] [--flavor ...]` | 生成独立指标文件（读静态图做边映射；不进 git） | 0/1/3 |
| `rvgen trace stats <f.jsonl>` | 打印 CPI / 气泡构成 / 命中率 / 零翻转连线 Top20 | 0/1/3 |
| `rvgen gen cdc [--out rtl/gen/cdc]` | 生成 `two_ff/pulse_sync/handshake/async_fifo/gray_bus` | 0/1/3 |
| `rvgen gen fuse-soc [--out .]` | 只生成 FuseSoC `.core`，不碰 rtl/ | 0/1/3 |
| `rvgen serve [--project PATH] [--port 8123] [--host 127.0.0.1] [--no-open]` | 启动 HTTP + SSE，是前端**唯一入口**；`--project` 选择 `examples/<name>/` | 0/1/3 |
| `rvgen plugin list` | 列出已发现 plugin 及提供的 schema/规则/视图 | 0/1/3 |
| `rvgen doctor [--json]` | 探测 iverilog / verilator / yosys / fusesoc / verible / Node / 协议注册 | 0/3 |
| `rvgen migrate [--from VER] [--dry-run]` | schema 版本迁移，先快照再改写 | 0/1/3 |

**退出码契约（唯一口径，与第 6 章一致）**：`0` 成功；`1` 存在 E 级诊断**或** CLI 用法错误；`2` 只有 W 级诊断且显式 `--strict`；`3` 环境/IO 错误（git 不可用、协议注册失败、权限、缺必需外部工具）。CI 与 pre-commit 只认退出码，不解析文本。

**`--accept-wiring` 的语义**：把 `.rvgen/wiring_suggestions.yaml` 中的同名候选**并入 `rvgen.yaml` 的 `top.ports`**，并自动执行一次 `graph --write`（因为它改变图结构）；这是唯一被允许的"候选自动落盘"，且必须由操作者显式敲命令。前后各打一次快照，diff 进 commit message。`sync --check` 只比较 YAML 期望与 `rtl/` 生成物是否落后，不检查 `node_graph.json`（那是 `check` 的职责）。

## 8. 单元测试与质量门禁

### 8.1 覆盖率门槛

| 范围 | 行覆盖 | 分支覆盖 | 说明 |
|---|---|---|---|
| `py/rvgen` 核心（loader/model/graph/emitter/digest/figures） | ≥ 90% | ≥ 85% | **不含** `layout/server/gitw/rvopen`（infra 层单独计） |
| `checker.py` + `digest.py` | ≥ 95% | ≥ 95% | 一致性门禁本体，最严 |
| `trace.py` 解析器 | ≥ 92% | ≥ 90% | 含畸形行、缺列、Ext 键值非法、元数据行缺失 |
| `web/src` | 组件快照全覆盖关键路径 | — | Vitest + Testing Library，阈值 80% statements |

> 覆盖率门槛**从 P1 起生效**；P0 没有测试，CI 不跑 `--cov`（见 7.4）。

### 8.2 测试文件清单与必测用例（**规则码必须出现在测试函数名里**）

| 文件 | 必测用例（函数名示例） |
|---|---|
| `tests/unit/test_loader_E01.py` | `test_E01_width_unresolvable`、`test_E01_expr_depth_overflow`、`test_E09_missing_required_field`、`test_no_eval_used_in_expr` |
| `tests/unit/test_marker_E06.py` | `test_E06_unclosed_marker`、`test_E06_nested_duplicate_id`、`test_marker_regex_accepts_crlf`、`test_user_block_preserved_byte_identical`、`test_W01_warn_line_outside_user_block`、`test_merge_clears_generated_region_twice` |
| `tests/unit/test_orphan_I04.py` | `test_I04_deleted_block_goes_to_orphaned`、`test_orphaned_file_content_matches_original`、`test_orphaned_dir_never_deleted` |
| `tests/unit/test_top_E02_E13_E14.py` | `test_E02_port_count_mismatch`、`test_E13_duplicate_driver`、`test_E13_unknown_top_port`、`test_E14_missing_required_input_lists_all`、`test_E07_clock_floating`、`test_E08_cross_domain_without_cdc`、`test_multi_fanout_shares_single_wire`、`test_unused_output_W04`、`test_param_passthrough_named` |
| `tests/unit/test_topsort_E03.py` | `test_E03_self_loop`、`test_E03_two_node_cycle_path_reported`、`test_E03_clock_edge_not_in_cycle`、`test_topsort_is_stable_across_runs` |
| `tests/unit/test_atomic_E12.py` | `test_E12_readonly_target_keeps_tmp`、`test_atomic_write_no_partial_on_oserror`、`test_windows_retry_then_fail` |
| `tests/unit/test_trace_E11.py` | `test_E11_column_count_mismatch`、`test_E11_ext_value_invalid`、`test_E11_meta_line_missing`、`test_W15_unknown_ext_key_kept`、`test_normalize_roundtrip_wellformed`、`test_summary_utilization_W05` |
| `tests/checker/test_diff.py` | `test_ignore_position_and_viewport`、`test_ignore_layout_and_trace_summary`、`test_detect_node_added_removed`、`test_detect_port_width_changed`、`test_detect_bandwidth_source_changed`、`test_strict_promotes_warning`、`test_fix_restores_expected`、`test_graph_write_is_explicit_only` |
| `tests/property/test_random_yaml.py` | `test_random_valid_yaml_always_loads`、`test_parse_print_identity`、`test_normalize_idempotent_twice` |
| `tests/golden/test_golden.py` | `test_golden_top_v_matches`、`test_golden_node_graph_matches`、`test_golden_trace_jsonl_matches` |
| `tests/perf/test_bench.py` | `test_gen_100_modules_20_ports_under_5s`、`test_check_500_nodes_under_2s` |
| `web/src/**/*.test.tsx` | `ModuleNode.snapshot`、`EdgeBandwidthLabel.snapshot`、`ViewSwitcher.test`、`ReloadBanner.test`、`HtmlUrlOpen.test`、`EChartDispose.test` |
| `web/e2e/*.spec.ts` | `load-json.spec`、`drag-node.spec`、`switch-view.spec`、`offline.spec`、`reload-keeps-layout.spec`、`rvgen-protocol.spec` |

### 8.3 黄金文件与 `--update-golden` 纪律

黄金文件放 `tests/golden/<area>/`，**必须逐个 diff 后人工确认才允许更新**。纪律：① `--update-golden` 只能在专职分支上跑，提交信息必须写清"为什么输出会变"（对应哪个规则码/哪个需求）；② 一次 PR 里黄金文件变更超过 3 个 → 必须有人在 review 中逐行确认；③ 黄金文件一律 LF 换行、无 BOM、末尾单换行，`tests/golden/test_golden.py` 里断言这三条；④ 黄金文件里**不得出现**时间戳/绝对路径/机器名，生成前统一用占位符 `<REPO_ROOT>` 等替换（`node_graph.json` 本身不写时间戳，见 4.2）。

### 8.4 属性测试与幂等验收

`hypothesis` 策略：`st_module_names()`、`st_port(width_strategy=one_of(int, param_ref, expr))`、`st_clock_tree(depth<=3)`，组合成随机但合法的 YAML；三条不变式（P1 用，不依赖 emitter）：
1. `load → canonicalize → json.dumps → json.loads → load` 得到的契约指纹与原始相同（canonical 幂等）；
2. `normalize(normalize(g)) == normalize(g)`；
3. 随机图 `topsort` 结果在环不存在时长度等于节点数，且每次运行结果逐字节相同。

P2 追加一条（依赖 emitter）：`load → emit → load` 的 `canonical_contract` 与原始相同；该条在 P2 退出标准里验收，不得前移到 P1。

**幂等性验收（硬门禁）**：
```
rvgen sync && rvgen sync && git diff --exit-code   # 必须为空
```
若非空 → 说明生成器输出含时间戳/字典序不稳定/集合遍历顺序不确定，属 P0 阻断缺陷。

### 8.5 性能基准

| 项 | 门槛 | 测法 |
|---|---|---|
| 生成 | 100 模块 × 20 端口 < 5 s（不含仿真） | `pytest-benchmark`，中位 of 10 次，CI runner 基线 |
| check | 500 节点语义 diff < 2 s | 同上 |
| trace normalize | 100 万行 < 25 s，峰值内存 < 1.5 GB | 流式逐行，不整文件读入 |
| 浏览器 | 500 节点：拖帧 p95 ≥ 30 FPS，首屏 < 3 s | Playwright + `page.metrics()`，p95 of 60 帧 |
| 布局 | elkjs 200 节点 < 1.5 s（Worker 内） | 页面内 `performance.mark` |

### 8.6 变异测试（可选加严）

`mutmut run --paths-to-mutate=py/rvgen/checker.py,py/rvgen/digest.py`，门槛：checker 变异得分 ≥ 80%。**只在 nightly 跑**（慢），不作为 PR 阻塞项；低于门槛说明测试只在断言"没抛异常"而没断言具体差异内容。

## 9. 分阶段交付 P0–P6

> **禁止跨阶段并行写码**：上一阶段退出标准未达成，下一阶段不得开工；允许只读式预研与设计评论。

| 阶段 | 产出 | 验收条件（可验证） | 退出标准 |
|---|---|---|---|
| **P0 地基** | `pyproject.toml`、目录骨架、`schema/*.schema.json`（`rvgen` 1.1.0，`node_graph/layout/trace` 1.0.0；**含 `x-` patternProperties 与 oneOf 判别式**）、`plugins.py` 契约与 `discover()`、`diag.py`、`atomic.py`、CI（只跑 check/sync --check/前端 build，**不跑覆盖率**）、`docs/DEPENDENCIES.md`（含实测体积/许可证）、`vendor/` + `scripts/npm-offline.sh` + `npm-offline.ps1` | `jsonschema` 能校验自身样例；`python -c "import rvgen"` 通过；依赖清单每条有 `npm view`/`pip show` 实测依据；`iverilog` 探测通过、缺失工具在 doctor 里明确列出 | CI 绿（无覆盖率门槛）+ 依赖表无"未核实"条目（tracer 列格式除外，那是 P1 的事） |
| **P1 语义核心** | `loader`/`model`/`graph`/`digest`/`importer` + **`plugins/cpu` 首个 plugin** + 规则码 E01/E02/E03/E05/E07/E08/E09/E10/E11/E13/E14 + **`top.ports` 显式连线解析** + `graph --write` + 黄金文件框架 | 随机合法 YAML 属性测试 3 条核心不变式全绿（不含 emit）；环路径回溯输出可读；`node_graph.json` 只能由 `graph --write` 生成 | loader/model/graph/digest 覆盖 ≥90%；checker 骨架 ≥95% |
| **P2 生成器与保护** | Jinja2 模板、`emitter` 六步合并、顶层例化（**以 `top.ports` 为准**）、`gen cdc`、`wiring_suggestions.yaml`、orphaned、frozen、`fusesoc.py` 产出 `.core`、`rvgen sync/check/import/gen` CLI | `sync && sync && git diff` 为空；`graph --write && graph --write` 第二次 diff 为空；USER 块字节级保留；W01 只出现在块外；删除块能在 orphaned 找回；`check --fix` 可修复 | 100 模块 20 端口 < 5 s；E06/E02/E13/E14/E12 全有用例 |
| **P3 前端骨架** | Vite 7 + React 19 + TS、React Flow 画布、自定义 `ModuleNode`/`BandwidthEdge`、数据流视图 dagre、详情抽屉、`rvgen://` 按钮；dev 端口 5174 | 500 节点拖帧 p95 ≥30 FPS；Node/Edge 快照测试绿；未挂载泄漏检查通过 | Playwright `load-json`/`drag-node` 绿；`npm run build` 成功并记录真实体积（**不设 2 MB 硬门槛，体积进报告**） |
| **P4 多视图 + trace** | 核心三视图：数据流、时钟树（径向）、统计图表；`plugins/cpu` 注册流水线时空图与 Cache 视图；`trace normalize/summary/stats` | 核心三视图必有；启用 cpu plugin 后流水线/Cache 视图出现，UART 项目不出现；`trace_summary.json` 与 `node_graph.json` 分离；E11/W15 用例绿；ECharts/Worker 卸载无泄漏 | 100 万行 trace 归一化 < 25 s；多视图 E2E 绿 |
| **P5 Git 闭环** | `gitw`、`server` SSE（环形缓冲 + Last-Event-ID 补发 + 慢客户端丢弃）、watchdog 去抖、手动 reload + layout 合并、三平台 `rvgen://` 注册脚本、hook、CI 示例；serve 端口 8123 | 改 YAML 后 ≤1.5 s 出现"有更新"徽标且**视图不被覆写**；点击重载后折叠/坐标/pinned 保留；断网 30 s 后重连能补齐事件或 resync | `offline.spec` + `reload-keeps-layout.spec` + SSE 重放单测绿；hook 在 commit/checkout 各触发一次 |
| **P6 硬化与交付** | 文档全套（第 13 章）、ADR ≥10 篇（含「核心零领域知识」「顶层连线显式化」「显式图更新」「trace 静态列」）、HANDOVER、性能报告、变异测试 nightly、迁移 transformer 首例 | 新人按 HANDOVER 半天内跑通 `sync/check/serve`；`check --strict` 全绿；30 条验收场景逐条打勾 | 全部文档无"TBD"；工具版本打 `v1.0.0` tag（schema 版本独立演进，当时 `rvgen` schema 为 1.1.0） |

## 10. agent 分工与子代理接口

### 10.1 主 agent 职责

1. 持有 `rvgen.yaml`、`schema/`、`pyproject.toml`、CI 配置、ADR 的**最终裁决权**（这些文件只有主 agent 能改）。
2. 拆分任务卡、派发、验收（跑验收命令、看 diff）、合并、打 tag。
3. 维护 `docs/DECISIONS.md`：任何规格未覆盖的提问与其默认值决议都记在这里，带日期。
4. 冲突仲裁：子 agent 之间接口不一致时，先改 `schema/` 与本文第 4/6 章，再让各方跟随。

### 10.2 子 agent 切分方式：**按层切，不按文件切**

| 子 agent | 层 | 拥有的目录 | 不得触碰 |
|---|---|---|---|
| A `core-sem` | 语义层（**零领域知识**） | `py/rvgen/{loader,model,graph,digest,figures,plugins,importer}.py`、`tests/unit/test_loader_*.py`、`test_topsort_*.py`、`test_wiring_*.py`、`test_plugin_*.py`、`test_import_*.py` | `emitter`/`web`/`schema`（只读）；**禁止**在核心写 `is_cpu` 之类分支 |
| B `gen` | 生成层 | `py/rvgen/{emitter,atomic}.py`、`templates/`、`tests/unit/test_marker_*.py`、`test_orphan_*.py`、`test_atomic_*.py`、`test_top_*.py` | `graph.py`、`web` |
| C `trace` | 观测层 | `py/rvgen/trace.py`、`tb/`、`tests/unit/test_trace_*.py`、`trace/` | 其余 |
| D `gate` | 门禁层 | `py/rvgen/{checker,cli,fusesoc}.py`、`tests/checker/`、`tests/golden/`、`tests/property/`、`tests/migration/` | `core` 实现（只读接口） |
| E `web-flow` | 前端画布 | `web/src/{flow,views}/`、`web/e2e/` | `web/src/api` 契约（只读 `contracts/`） |
| F `web-shell` | 前端外壳与服务 | `web/src/{App,api,store,panels}/`、`py/rvgen/{server,gitw,rvopen,layout}.py`、`scripts/` | `flow/` 内部、`figures.py`（归 A） |
| G `plugin-cpu` | **领域 plugin（示例）** | `plugins/cpu/{schema,rules,views,trace}.py`、`examples/rv32i/` | **核心层一切文件**（这是零领域知识的纪律保障） |
| H `plugin-bus` | **领域 plugin（示例）** | `plugins/bus/{schema,rules,views,trace}.py`、`examples/uart/` | 核心层一切文件；不得改 `plugins/cpu` |

### 10.3 任务卡模板（每个子任务必须填满）

```
【任务卡】id: P2-B-03    负责人: gen    依赖: P1 退出标准已达成
上下文（必读，按顺序）：
  1) 本文（`rvgen完整方案.md`）第 1.1/5.2/5.3/5.7/6.1/8.2 节
  2) schema/node_graph.schema.json（只读）
  3) docs/DECISIONS.md 全部条目
输入（已存在，可直接 import）：
  rvgen.model.DesignModel / rvgen.graph.NodeGraph / rvgen.diag.Diagnostic /
  rvgen.atomic.atomic_write / rvgen.digest.fingerprint
输出（你新建或修改，且只有你能改）：
  py/rvgen/emitter.py、py/rvgen/templates/*.j2、tests/unit/test_marker_E06.py、
  tests/unit/test_orphan_I04.py、tests/unit/test_atomic_E12.py、docs/golden 说明段落
公开接口（签名冻结，别的 agent 依赖它）：
  emit(m: DesignModel, g: NodeGraph, out_dir: Path, sink: DiagnosticSink) -> list[Path]
禁止事项：
  不许改 rvgen.yaml / schema / graph.py / 任何 web 文件；
  不许 print；不许 except: pass；不许引入 jinja2 之外的新依赖；
  不许删除 .rvgen/orphaned 下任何文件；不许改 tests/golden 之外的黄金文件。
验收命令（全部为 0 退出才算完成）：
  pytest tests/unit/test_marker_E06.py tests/unit/test_orphan_I04.py tests/unit/test_atomic_E12.py -q
  rvgen sync && rvgen sync && git diff --exit-code
  pytest --cov=rvgen/emitter --cov-fail-under=90
交接产物：
  docs/handoff/P2-B-03.md：新增/变更的公开符号、未决问题、留给下一个 agent 的注意事项
```

### 10.4 文件所有权表（每文件唯一 owner）

| 文件/目录 | Owner |
|---|---|
| `rvgen.yaml`、`schema/*`、`pyproject.toml`、`.github/*`、`docs/DECISIONS.md`、`docs/ADR/*`、`rvgen完整方案.md`（本文） | 主 agent |
| `py/rvgen/{loader,model,graph,digest,figures,plugins,importer}.py` | A `core-sem` |
| `py/rvgen/{emitter,atomic}.py`、`py/rvgen/templates/`（含 `cdc/` 基础模块模板） | B `gen` |
| `py/rvgen/trace.py`、`tb/` | C `trace` |
| `py/rvgen/{checker,cli,fusesoc}.py`、`tests/golden/`、`tests/property/`、`tests/migration/` | D `gate` |
| `web/src/flow/`、`web/src/views/`、`web/e2e/` | E `web-flow` |
| `web/src/{App,api,store,panels}.ts(x)`、`py/rvgen/{server,gitw,rvopen,layout}.py`、`scripts/` | F `web-shell` |
| `plugins/cpu/**`、`examples/rv32i/` | G `plugin-cpu` |
| `plugins/bus/**`、`examples/uart/` | H `plugin-bus` |
| `docs/*.md`（除 DECISIONS/ADR） | 各自 owner 写，主 agent 合并修订 |

**越界规则**：需要改别人 owner 的文件 → 停下，写进任务卡的"跨层请求"字段，由主 agent 裁定并派新任务卡。**绝不直接改。**

### 10.5 失败重试与回滚

1. 验收命令失败 → 子 agent 最多自修 2 轮；第 3 轮仍失败，回退到本阶段起点 commit，主 agent 重拆任务卡（把范围砍半）。
2. 每阶段一个 commit，commit 前必须 `git stash -u` 验证无遗漏文件；commit message 格式 `P<n>: <层> <一句话>`，正文列出关闭的规则码。
3. 回滚单位永远是**一个阶段一个 commit**，`git revert <阶段 commit>` 必须能干净回退（不允许阶段内跨 commit 依赖半成品）。
4. 黄金文件冲突 → 以主 agent 的为准，子 agent 重跑 `--update-golden` 后逐条 diff 说明。

## 11. 风险登记表

| # | 风险 | 概率 | 影响 | 缓解措施 | 责任角色 |
|---|---|---|---|---|---|
| R01 | 生成器变质成第二语言（模板里长满 if/else，等于用 Jinja 写硬件） | 中 | 高 | 模板行数上限 200 行/个；模板内禁止 `{% if %}` 嵌套 >2 层；复杂逻辑一律下沉到 Python 函数并单测；ADR 记"生成器不是语言"条款 | 主 agent + B |
| R02 | CDC 漏检导致跨域直连 | 中 | 极高 | 边级强制 `domain` 比对，E08 非零退出；`rvgen graph --list-cdc` 输出清单供人工review；P1 加随机图属性测试覆盖所有跨域组合 | A `core-sem` |
| R03 | 位宽猜错造成静默截断 | 中 | 高 | 四级链 + W03 显式告警；`check --strict` 把 W03 升为 error；UI 上被截断的边画虚线红边 | A + E |
| R04 | 图库大图性能崩（>500 节点拖不动） | 中 | 中 | 第 5.6 节四级降级；`onlyRenderVisibleElements` 打开 + 节点 memoize + `hidden` 折叠 [1]；P3 用 500 节点实测校准门槛 | E `web-flow` |
| R05 | 浏览器内存泄漏（闭包持有旧 graph / Worker 未 terminate） | 中 | 高 | 视图卸载清单：`worker.terminate()`、`ResizeObserver.disconnect()`、事件监听 remove、`AbortController` 取消在途请求；E2E 里切视图 20 次后断言 `performance.memory` 增长 < 20% | E |
| R06 | ECharts 实例未 dispose 导致 canvas 堆积 | 中 | 中 | 统一 `useChart` hook 内 `echarts.getInstanceByDom` + `dispose()`，禁止组件内直接 `init`；加 ESLint 自定义规则禁止裸 `echarts.init` | E |
| R07 | `file://` 下 `fetch` 被 CORS 拦，双击 HTML 打不开 | 高 | 中 | 不做纯静态交付；`rvgen serve` 是唯一入口；离线场景用 `vite build` + 内联 JSON 的 `index.offline.html`（构建期注入），并在 README 首屏写明 | F `web-shell` |
| R08 | Windows 原子写失败/路径分隔符/文件占用 | 中 | 高 | `pathlib` + `os.replace` + 3 次退避重试 + E12 明确提示；CI 加 windows-latest job 跑 `test_atomic_E12.py` | B `gen` |
| R09 | `rvgen://` 协议未注册或注册需管理员权限 | 高 | 中 | 提供 `scripts/rvopen.{sh,cmd,ps1}` + `register.{sh,ps1}`；未注册时打 `I06`，回退"复制 `code -g file:line` 到剪贴板"；macOS 用 `open`、Windows 走 `HKCU` 注册表（不提权）、Linux 用 `xdg-open` + `~/.local/share/applications` | F |
| R10 | trace 文件过大撑爆内存 | 中 | 高 | `normalize` 严格逐行流式；按 200 万行分片输出 `part-0000.jsonl`；前端只加载窗口区间 + `trace_summary.json`（不进 git） | C `trace` |
| R11 | YAML 锚点/别名滥用导致不可读与嵌套爆炸 | 中 | 中 | 锚点嵌套深度 >10 → W10；`rvgen yaml expand` 输出展开后的平铺 YAML 供 review；文档示例一律不用锚点 | A |
| R12 | schema 迁移破坏旧仓库 | 中 | 高 | transformer 链 + `--dry-run` 差 +迁移前快照；CI 用 `tests/migration/fixtures/v1.0.0/` 真实样本跑通到最新 | 主 agent |
| R13 | SSE 被反向代理缓冲导致事件延迟分钟级 | 中 | 中 | 显式要求 `proxy_buffering off`、`X-Accel-Buffering: no`；15 s 心跳注释帧；事件带 `id:`，客户端用 `Last-Event-ID` 续推；给出 nginx/Caddy 两段配置示例 | F |
| R14 | 编辑器原子写触发虚假变更事件（一次保存 N 条） | 高 | 中 | 400 ms 去抖 + 内容 sha256 去重 + 忽略 `.tmp/.swp`、`node_modules/`、`.git/`；**`.rvgen/.git-event` 必须放行**（它是 hook→server 的唯一通道）[7][8]；把"一次保存只推一条"写成 E2E 用例 | F |
| R15 | React Flow 版本升级破坏自定义节点 | 中 | 中 | 锁 `package-lock.json` + `npm ci --offline`；自定义节点/边共 2 个文件，升级影响面可控；v11→v12 迁移指南在 P3 前读完写进 ADR-06 | E |
| R16 | 中文注释在不同编辑器下编码错乱 | 低 | 低 | 全仓 UTF-8 无 BOM + `.editorconfig` + pre-commit `check-encoding` 钩子 | 主 agent |
| R17 | 前端把动态数据写回声明源或图文件 | 低 | 高 | `api` 层只读 `rvgen.yaml`；`POST /api/layout` 只接受 `layout.json`；`trace_summary.json` 只由 `rvgen trace summary` 产出；CI 断言 `rvgen.yaml` 与 `node_graph.json` 均不含 `metrics:`/`viewport` 键，且 `node_graph.nodes[]` 不含 `"x":`/`"y":` 布局键（`x-<plugin>-*` 扩展字段不受影响） | D `gate` |
| R18 | 改结构后忘记更新 `node_graph.json`，看板与 YAML 长期不一致 | 高 | 中 | `check` 独立重算图并与文件比对（主要防线）；pre-commit 与 CI 都跑 `check`；`serve` 顶部常驻"图落后"横幅并给出 `rvgen graph --write` 按钮（只展示命令，不代跑）；**任何工具路径都不静默写图** | A + D |

## 12. 验收场景清单（逐条打勾）

- [ ] AC01 全新 clone 后 `pip install -e .[dev]` + `sh scripts/npm-offline.sh`（Windows：`powershell -File scripts/npm-offline.ps1`）+ `cd web && npm ci --offline` 一次成功，无需联网（cache 由 vendor tgz 填充）。
- [ ] AC02 `rvgen init demo` 生成可编译的 `rvgen.yaml` 样例与 `rtl/top.v`，`iverilog -g2005 -Wall -o /dev/null -s top rtl/*.v`（Windows 用 `-o NUL`）无 error；装了 verilator 时额外跑 `--lint-only`。
- [ ] AC03 用户只在 USER 块里写逻辑，`rvgen sync` 后逻辑原样存在、`git diff` 只显示非 USER 区变化；W01 提示只出现在块外。
- [ ] AC04 删掉一个 USER 块后 `rvgen sync`，`.rvgen/orphaned/` 出现同名 `.v.bak`，stderr 出现 `I04`，退出码 0。
- [ ] AC05 `sync && sync && git diff` 为空；`graph --write && graph --write` 第二次也为空（两个幂等门禁）。
- [ ] AC06 手改 `node_graph.json` 一个端口位宽 → `rvgen check` 退出码 1，输出含点号路径与 hint；`check --fix` 后再次通过。
- [ ] **AC07（通用性核心验收）** `examples/uart/`（`uart` + `fifo` + `baud_gen`，零 CPU 概念）跑通 `init → graph --write → sync → check → serve`，**不启用 `plugins/cpu`**，不出现任何 `P*` 码。
- [ ] **AC08** 同仓 `examples/rv32i`（启用 `plugins/cpu`）与 `examples/uart`（不启用）并存，两套 `node_graph.json` 互不干扰；`serve --project examples/uart` 只加载对应项目；rv32i 出流水线视图，uart 不出且无空图占位。
- [ ] **AC09** `rvgen import examples/uart/rtl/uart.v` 生成骨架：端口名/方向/参数与手写版**逐字段一致**；`kind`、`clock`、`domain`、`top.ports` 采用显式默认值并全部进 W14 待办清单（不承诺自动还原；`` `ifdef `` 包裹的端口才是 I05）。
- [ ] **AC10** `top.ports` 中两个 output 都 `from: uart.tx` → `E13` 并指出冲突双方；`role: clock` 端口改名成与数据口同名 → **不产生连线也不产生候选**。
- [ ] **AC11** `rvgen gen fuse-soc` 产出的 `.core` 能被 `fusesoc run --target lint` 消费；**本机未装 fusesoc**，因此默认验收路径是：用 `jsonschema` 校验 `.core` 的 filesets/parameters/targets 结构 + `rvgen doctor` 明确列出"fusesoc 缺失，已跳过真实消费"；用户装好 fusesoc 后补跑 `fusesoc run --target lint`。
- [ ] **AC12** 核心边界用**字段白名单**校验：`tests/unit/test_core_whitelist.py` 断言 `schema/rvgen.schema.json` 的 `modules[].kind` 枚举恰为四项、不存在 `stage/stage_index/cache` 字段、`node_graph` 核心 `type` 枚举不含裸 `cache_node/pipeline_slot_node`（plugin 只能以 `p_cpu:` 前缀注册）；额外跑 `grep -rnE "is_cpu|rv32i|JALR|pipeline_stage" py/rvgen/` 零命中。
- [ ] **AC13** 伪造坏 plugin（schema 非法 + 抛异常），`rvgen plugin list` 报 W11 并跳过，其余命令仍退出 0。
- [ ] **AC14** `examples/rv32i` 用 `--flavor cpu`、`examples/uart` 用 `--flavor core` 归一化，6 列 TSV 都能进同一前端；UART 的 `Loc/State/Ids/Ext` 正常显示，无 JSON 列。
- [ ] AC15 `node_graph.json` 保持纯静态：写入 `layout`/`trace_summary` 数据到旁路文件后 `check` 仍通过；图文件里搜索不到 `metrics`/`viewport`。
- [ ] AC16 YAML 制造两模块组合环 → `rvgen graph --write` 报 `E03` 并打印完整环路径。
- [ ] AC17 两个不同 `domain_id` 直连 → 报 `E08`；补 `cdc[]` 后通过。
- [ ] AC18 端口位宽写成未声明参数 → 报 `E01`，hint 给出可用参数名列表。
- [ ] AC19 `web/index.html` 经 `rvgen serve` 打开能加载图；核心四种节点（module/clock/cdc/stats）+ 启用 cpu plugin 后的两种节点（`p_cpu:cache_node`/`p_cpu:pipeline_slot_node`）均有自定义外观。
- [ ] AC20 每条边标签显示位宽与静态带宽；`explicit/derived` 图标可区分，悬停给出 GB/s 与 bits/cycle；来自 `trace_summary.json` 的利用率用第三种标记。
- [ ] AC21 切换核心三视图（数据流/时钟树/统计）；启用 cpu plugin 后追加流水线/Cache，坐标不串、无 canvas 残留、切 20 次内存增长 <20%。
- [ ] AC22 改 `rvgen.yaml` 保存一次 → 1.5 s 内出现"源已变更"徽标，**视图内容未变**；点击重载后手动拖动位置、折叠态、pinned 保留。
- [ ] AC23 `layout.json` 不在 `git ls-files`，`rvgen.yaml` 不含 `x:`/`y:`/`position` 字段（`x-<plugin>-*` 扩展字段不算）。
- [ ] AC24 点击节点 → `rvgen://` 脚本在三平台打开 VSCode 并定位；协议未注册时给可复制 fallback 命令。
- [ ] AC25 `rvgen trace normalize tb/out.tsv -o trace/run.jsonl` 产出合法 JSONL，每行 `json.loads` 成功；抽样字段齐全（core：loc/state/ids/arc/cdc；cpu flavor 额外 pipe/ctrl/regw/icache/dcache/dec）。
- [ ] AC26 故意在 RTL 格式串里插入换行 → `normalize` 报 `E11` 给出行号，不产出半截 JSONL。
- [ ] AC27 `git commit` 触发 pre-commit `check`，弄脏图后被阻断；`git checkout` 触发 post-checkout 一次检查；CI（含 Playwright）在 `ubuntu-22.04` 一次通过且 `--strict` 无 warning 漏出。
- [ ] AC28 断网 30 s 后 SSE 自动重连：缓冲内事件按序补发；超出缓冲时收到 `resync` 并主动拉一次图；慢客户端不阻塞其他订阅者。
- [ ] AC29 500 节点拖拽 p95 ≥30 FPS；200 节点 elkjs 布局 Worker 内 <1.5 s；100 万行 trace 归一化 <25 s。
- [ ] AC30 `docs/HANDOVER.md` 交给未参与者，半天内独立完成 AC02–AC05 与一次视图切换。

## 13. 文档交付清单

| 文档 | 必含内容 |
|---|---|
| `README.md` | 30 秒上手：安装 → `init` → `sync` → `graph --write` → `serve` → 打开浏览器；故障速查表前 5 条 |
| `ARCHITECTURE.md` | 第 3 章分层图、依赖方向规则、数据流闭环、monorepo 地图 |
| `ADR-01 为何选开源节点编辑器而非自研看板` | 成本对比、自研需补的能力清单、React Flow 官方性能路径 [1][2] |
| `ADR-02 为何用 marker 区间而非 3-way merge` | EMF `@generated NOT` 与 Jinja2 block 机制对照 [3][4]、Verilog 无 AST 基线、失败模式 |
| `ADR-03 为何单向同步（YAML→图→视图）` | 双向同步的冲突不可判定性；layout 旁路；反向编辑的替代方案（改 YAML） |
| `ADR-04 带宽单位的确定` | 权威单位 bits/cycle、GB/s 十进制、**静态两来源**（explicit/derived）的优先级；实测利用率属 `trace_summary.json`，不进图；util>1 的含义 |
| `ADR-05 为何 trace 兼容 cv32e40p` | 复用现有 tracer 与回归资产；**含"官方列格式未核实、待 P1 用真实输出校准"的显式声明** |
| `ADR-06 前端框架与布局库选型` | React Flow v12 + dagre/elkjs 分工、v11→v12 迁移核对结果、Cytoscape 降级为布局候选 [5] |
| `ADR-07 SSE 而非 WebSocket` | 单向流量、重连与 Last-Event-ID、代理缓冲代价、R13 缓解 |
| `ADR-08 生成器不该变成第二个语言` | 模板复杂度预算、逻辑下沉规则、业界对生成代码不可编辑痛点的教训 |
| `ADR-09 核心零领域知识与四类 kind` | 判定问句（"UART 需要它吗"）、`kind` 注册表、`x-<plugin>-*` 透传、AC12 白名单校验 |
| `ADR-10 顶层连线显式化` | `top.ports` 唯一依据、同名候选只作建议、时钟/复位不参与推断、E13/E14 的引入理由 |
| `ADR-11 图文件显式更新` | 为何不静默写 `node_graph.json`；`sync` 与 `graph --write` 的职责切分；CI/pre-commit 只认 `check` |
| `ADR-12 trace 静态列 + 旁路指标` | RTL 只写 6 列 TSV 的原因、JSON 由 Python 构建、`trace_summary.json` 不进 git、W15 语义 |
| `YAML_REFERENCE.md` | 第 4.1 节全字段表 + 3 个完整示例（单核 5 级 / 带 CDC / 带 Cache） |
| `NODE_GRAPH_REFERENCE.md` | 第 4.2 节全字段 + 带宽**两来源**算例（explicit / derived，含具体数字：32 bit × 50 MHz = 200 Mb/s = 0.2 GB/s）；trace 利用率见 `TRACE_SCHEMA.md` |
| `TRACE_SCHEMA.md` | TSV 6 列定义（`Time/Cycle/Loc/State/Ids/Ext`）+ `#rvgen-meta` 头 + Ext 键表 + `trace_summary.json` 结构 + normalize 输出示例（P1 用真实 tracer 填充） |
| `WEBUI.md` | 核心三视图（数据流/时钟树/统计）说明、plugin 注册视图（流水线/Cache）的开关方式、交互手势、`rvgen://` 使用与三平台注册步骤、离线模式 |
| `EXTENDING.md` | 加一种 kind/一种节点类型/一种视图/一种 CDC 类型/一组 plugin 规则码的各 6 步流程与必改文件清单 |
| `TESTING.md` | 第 8 章门槛、如何跑单个规则码测试、`--update-golden` 纪律、变异测试用法 |
| `HANDOVER.md` | 新人半天 checklist：环境 → 三条命令 → 改一个端口 → 看视图 → 跑 check → 读哪 5 个文件 |
| `NOT_IN_SCOPE.md` | 第 1.3 节全表 + 每条"为什么不做"+"什么条件下会重新评估" |
| `CHANGELOG.md` | Keep a Changelog 格式；每个版本列出变更的规则码与 schema 版本 |

## 14. 给 agent 的执行铁律

1. **一次只做一个阶段**。上一阶段退出标准未达成，不写下一阶段的代码。
2. **不许引入未列出的依赖**。需要新依赖 → 停下，写进任务卡"跨层请求"，由主 agent 决策并更新 `docs/DEPENDENCIES.md`（含许可证与实测体积）。
3. **不许 `except: pass`**，不许裸 `except Exception`；捕获后必须转成 `Diagnostic` 或重新抛出。
4. **所有报错走 `Diagnostic`**，禁止 `print`/`logging.error` 直接面向用户；退出码只有 0/1/2/3 四种含义（见 7.5）。
5. **中文注释、英文标识符**：注释与文档中文，模块/函数/变量/端口/文件一律 ASCII 英文；提交信息中文正文 + 英文类型前缀。
6. **不修别人 owner 的文件**，需要就发跨层请求。
7. **不许自动覆写用户正在看的东西**：服务端只推失效提示，重载必须由用户点击触发。
8. **不许在 RTL 里拼 JSON**，只许 `$fwrite` 定宽文本；结构化在 Python 侧做。
9. **不许把 layout/position/trace 指标写进 `rvgen.yaml` 或 `node_graph.json`**；动态数据只进 `layout.json` 与 `trace_summary.json`，两者都不进 git、都不参与 `check`。
10. **每个阶段一个 commit**，commit 前必跑该阶段验收命令并贴输出进交接产物。
11. **黄金文件必须人工 diff 后才允许 `--update-golden`**，提交信息写明原因与对应规则码。
12. **遇到规格未覆盖的情况停下来问**：写进 `docs/DECISIONS.md` 的"待决议"区，用第 1.4 节的默认值临时推进并标 `TODO(Qn)`，不许自行发明语义。
13. **不许删除或覆盖 `.rvgen/orphaned/` 与 `.rvgen/snapshots/` 中的任何文件**；清理策略由主 agent 定（保留最近 20 份 / 30 天）。
14. **不许用 `eval`/`exec`**，表达式解析一律 `ast` 白名单。
15. **核心层零领域知识**：核心 schema 的 `modules[].kind` 白名单恰为 `module/bridge/memory/clock_gen`，`node_graph` 核心 `type` 白名单不含 plugin 类型；`stage/cache/pipeline slot` 只能以 `x-<plugin>-*` 出现。主门禁是 schema 白名单测试（AC12），`grep -rnE "is_cpu|rv32i|JALR"` 只作辅助。
16. **顶层连线只读 `top.ports`**：同名推断只写 `.rvgen/wiring_suggestions.yaml` 并报 W12，落盘必须经 `--accept-wiring` 显式确认；`role: clock/reset` 的端口永不参与同名推断。
17. **受控资产只能被显式命令改写**：`node_graph.json` 仅由 `rvgen graph --write` / `sync --update-graph` / `graph --accept-wiring` 写入；`serve`、watchdog、hook 一律只读，最多提示或自动跑 `check`。

## 15. 技术栈锁定与版本

| 层 | 锁定 | 约束方式 |
|---|---|---|
| Python | **3.11.6**（精确） | `pyproject.toml`: `requires-python = "==3.11.*"`，README 写明 3.11.6；CI matrix 只跑 3.11.6 |
| 核心依赖 | `pyyaml>=6.0.1`、`jsonschema>=4.21,<5`、`jinja2>=3.1.3`、`watchdog>=4.0`、`fastapi>=0.110`、`uvicorn[standard]>=0.27`、`pytest>=8`、`pytest-cov`、`hypothesis>=6.100`、`pytest-benchmark`、`mutmut`（可选）、`import-linter` | 全部 `==` 精确锁进 `pyproject.toml` 的 `[project.optional-dependencies]`，`pip-tools` 编译出 `requirements.lock`；**前端工具不进 Python 依赖** |
| Node | **24.x**（本机 v24.22.1，`>=24 <25`） | `.nvmrc`(24) + `engines` + `npm config set engine-strict true`；本机无 nvm/fnm/volta，文档只声明版本，不提供切换脚本 |
| 前端 | `react`/`react-dom` **19.x**、`@xyflow/react` **12.x**、`vite` **7.x**、`typescript` **5.x**、`zustand` 5.x、`elkjs` 最新稳定、`@dagrejs/dagre` 最新稳定、`echarts` 5.5.x、`@tanstack/react-query` 5.x、`vitest` 2.x、`@testing-library/react` 16.x、`@playwright/test` 1.4x | `package-lock.json` 进 git；`npm ci --offline`；`engines` + `engine-strict`；小版本以 `npm ls` 实际解析结果为准并记入 `docs/DEPENDENCIES.md` |
| 前端工具链 | `json-schema-to-typescript` 作为 **web 侧 devDependency**（用于 `schema/*.json → contracts/*.ts`），`eslint` + `prettier` | 只在 `web/package.json` 出现；`npm run gen:contracts` 可重复执行且 diff 为空 |
| plugin 专属前端依赖 | `d3-force` 只属于 `plugins/cpu` 的 Cache 视图包，不进核心 `web` 依赖 | 由 plugin 前端包自带 `package.json`，核心构建不解析它 |
| 不使用 | Vue/jointJS/GoJS/Cytoscape 作为主编辑器；Redux（用 `zustand`）；`reactflow` v11 包名 | 违反即 CI 的依赖白名单检查失败 |
| 离线 | `vendor/wheels/`（`pip download -r requirements.lock -d vendor/wheels`）+ `vendor/npm/`（`npm pack` 全量 tgz） | `pip install --no-index --find-links vendor/wheels`；`scripts/npm-offline.sh`（Linux/macOS）与 `scripts/npm-offline.ps1`（Windows）执行 `npm cache add vendor/npm/*.tgz` 后 `npm ci --offline`；CI 断网 job 验证 |
| 版本兼容 | 全仓 UTF-8 无 BOM、**LF 换行**（`.gitattributes` 强制 `*.v text eol=lf`，Windows 侧也统一） | pre-commit `check-yaml`/`end-of-file-fixer`/`trailing-whitespace`/`check-encoding` |

**版本决策理由**：React **19** + Vite **7** + Node **24** 与本机及旧工程 `@slc/web`（React 19.2 + Vite 7.1）一致，避免同机双份 Node/前端版本管理；`@xyflow/react` 12 对 React 19 的兼容以 P3 首日 `npm ls react` + Playwright 冒烟为准，若不兼容则在 P3 内降 React 18.3 并写 ADR，不允许悬空。`jsonschema` 4.x 提供 Draft 2020-12 与 `best_match`，错误友好化够用且不引入额外校验框架。

**前置条件（本机实测，缺失项必须走替代路径）**：

| 工具 | 状态 | 用途 | 缺失时的替代验证 |
|---|---|---|---|
| Python 3.11.6 | ✅ 已装 | 核心运行时 | — |
| Node 24.x / npm 11.x | ✅ 已装 | 前端与离线打包 | — |
| Icarus Verilog | ✅ `D:\iverilog\bin\iverilog.exe` | 默认仿真/编译检查（`-g2005`） | — |
| Yosys | ✅ 已装 | 可选综合语法检查 | `iverilog -g2005` |
| Verilator | ❌ 未装 | 可选 lint / 覆盖率 | `iverilog -g2005 -Wall` + `rvgen check`；`doctor` 打提示，不自动装 |
| FuseSoC | ❌ 未装 | `.core` 消费验证（AC11） | 用 `jsonschema` 校验 `.core` 结构 + `doctor` 说明跳过原因；用户装好后补跑 |
| Verible | ❌ 未装 | 可选格式化/lint | 不做硬依赖，`doctor` 仅提示 |

## 附录 A：`digest.py` 骨架（需按接口定义补齐）

```python
# py/rvgen/digest.py —— 骨架，需按第 5.3、6.1 节接口补齐
from __future__ import annotations
import hashlib, json
from typing import Any
from .model import ModuleDecl

_CONTRACT_FIELDS = ("name", "kind", "clock", "params", "ports", "interfaces", "x")

def canonicalize(m: ModuleDecl) -> dict[str, Any]:
    """只把"契约"字段规范化；doc/todo/status/loc/layout 一律不进。

    注意：只对**对象键** sort_keys，端口/参数/接口数组保持声明顺序。
    """
    out: dict[str, Any] = {
        "name": m.name,
        "kind": m.kind.value,
        "clock": m.clock,
        "params": [                                  # 保持声明顺序
            {"name": p.name, "default": p.default, "width": p.width}
            for p in m.params
        ],
        "ports": [                                   # 保持声明顺序
            {
                "name": p.name, "dir": p.dir.value,
                "width_bits": p.width_bits,          # None = 未解析，仍参与指纹
                "kind": p.kind.value, "domain": p.domain,
            } for p in m.ports
        ],
        "interfaces": [                              # 展开后的信号集合，按信号名排序
            {
                "name": i.name, "type": i.type, "params": i.params,
                "dir_flip": i.dir_flip,
                "signals": sorted(
                    [{"name": s.name, "dir": s.dir.value, "width_bits": s.width_bits}
                     for s in i.expanded_signals],
                    key=lambda d: d["name"],
                ),
            } for i in m.interfaces
        ],
        # 只收录参与生成的 x-<plugin>-* 字段；plugin 自行声明哪些 key 进指纹
        "x": {k: v for k, v in sorted(m.extensions.items())
              if k.startswith("x-") and m.plugin_contract_keys.get(k, False)},
    }
    return {k: out[k] for k in _CONTRACT_FIELDS if out.get(k) not in (None, [], "", {})}

def fingerprint(m: ModuleDecl) -> str:
    blob = json.dumps(canonicalize(m), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
```

> 与旧骨架的差异（这是缺陷修复，不是风格调整）：删掉 `stage`（核心无此字段）；端口不再按名字排序（否则"端口顺序变化"检测不到）；`None` 位宽保留在指纹中并与"端口缺失"区分；`x-` 字段按 plugin 声明的契约键选择性纳入。

## 附录 B：`emitter` USER 块合并骨架（需补齐）

```python
# py/rvgen/emitter.py 节选 —— 骨架，需按第 5.2 节六步与第 6.1 节签名补齐
import re
from .diag import Diagnostic, DiagnosticSink

# 关键点 1：\r? 兼容 CRLF；begin/end 必须同 id 配对（反向引用）
PAIR = re.compile(
    r"(?P<begin>^[ \t]*//[ \t]*rvgen:user-begin[ \t]+(?P<id>[A-Za-z0-9_.-]+)[ \t]*\r?$)"
    r"(?P<body>.*?)"
    r"(?P<end>^[ \t]*//[ \t]*rvgen:user-end[ \t]+(?P=id)[ \t]*\r?$)",
    re.M | re.S,
)
STRAY = re.compile(r"^[ \t]*//[ \t]*rvgen:user-(begin|end)\b.*$", re.M)

def split_markers(text: str, sink: DiagnosticSink, where) -> dict[str, str]:
    """返回 {block_id: body}，body 含首尾换行，保持块内字节原样。"""
    blocks: dict[str, str] = {}
    for m in PAIR.finditer(text):
        bid = m.group("id")
        if bid in blocks:
            sink.add(Diagnostic("E06", "error", where, f"USER 块重名：{bid}"))
        if re.search(r"^[ \t]*//[ \t]*rvgen:user-begin\b", m.group("body"), re.M):
            sink.add(Diagnostic("E06", "error", where, f"USER 块嵌套：{bid}"))
        blocks[bid] = m.group("body")
    rest = PAIR.sub("", text)
    for lineno, line in enumerate(rest.splitlines(), 1):
        if STRAY.match(line):
            sink.add(Diagnostic("E06", "error", where,
                                f"第 {lineno} 行 USER marker 未配对：{line.strip()}"))
    return blocks

def merge(existing: str | None, generated: str, module: str,
          fp_old: str | None, fp_new: str, sink: DiagnosticSink, where) -> str:
    """清空生成区后整体重写：旧文件只贡献 USER 块 body，其余字节全部来自模板。

    幂等性由此保证：模板不变 + 块体不变 -> 输出逐字节不变。
    """
    old = split_markers(existing or "", sink, where) if existing else {}
    expect = {m.group("id") for m in PAIR.finditer(generated)}
    for bid in sorted(set(old) - expect):                 # 步骤 5：孤儿块
        sink.add(Diagnostic("I04", "info", where,
                            f"USER 块 {module}.{bid} 已失效，备份到 .rvgen/orphaned/"))
    if fp_old and fp_old != fp_new:                       # 诊断；文件头注释由模板 contract_notice 渲染
        sink.add(Diagnostic("W01", "warning", where,
                            f"{module} 契约变更 {fp_old}->{fp_new}，请核对 USER 块"))
    out: list[str] = []
    pos = 0
    for m in PAIR.finditer(generated):
        out.append(generated[pos:m.start("begin")])       # 生成区前缀（模板内容）
        bid = m.group("id")
        body = old.get(bid, "\n// TODO(rvgen): 在此写用户逻辑\n")
        out.append(m.group("begin"))
        out.append(body if body.endswith("\n") else body + "\n")
        out.append(m.group("end"))
        pos = m.end("end")
    out.append(generated[pos:])
    return "".join(out)
```

**与旧骨架的差异**：① marker 正则加 `\r?` 并改用 `PAIR` 整体配对，CRLF 下不再漏配；② 明确"清空生成区后重写"，不做逐行 patch；③ W01 同时进 stderr 与**生成区头部注释**（模板变量 `contract_notice`，位于 USER 块外），`// rvgen:fingerprint <fp>` 也由模板生成；④ 嵌套/残缺 marker 都归 `E06`，不让半截块进入输出。

## 附录 C：`graph.py` 位宽解析与带宽推导骨架

```python
# py/rvgen/graph.py 节选 —— 骨架，需按第 5.1、4.2 节补齐
import ast
from .diag import Diagnostic

# 表达式白名单：只允许整数常量、参数名、+ - * // % << >> 与一元正负
_OK_BIN = (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod, ast.LShift, ast.RShift)

def _safe_eval(node: ast.AST, params: dict[str, int], depth: int) -> int:
    if depth > 8:
        raise ValueError("表达式嵌套超过 8 层")
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in params:
            raise KeyError(node.id)
        return params[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _safe_eval(node.operand, params, depth + 1)
        return v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp) and isinstance(node.op, _OK_BIN):
        a = _safe_eval(node.left, params, depth + 1)
        b = _safe_eval(node.right, params, depth + 1)
        if isinstance(node.op, ast.FloorDiv) and b == 0:
            raise ValueError("除零")
        return {
            ast.Add: lambda: a + b, ast.Sub: lambda: a - b,
            ast.Mult: lambda: a * b, ast.FloorDiv: lambda: a // b,
            ast.Mod: lambda: a % b, ast.LShift: lambda: a << b,
            ast.RShift: lambda: a >> b,
        }[type(node.op)]()
    raise ValueError(f"不允许的语法：{type(node).__name__}")

def resolve_width(port, params: dict[str, int], sink, where) -> tuple[int | None, str]:
    w = port.width
    if isinstance(w, int):                                       # 1. 字面量
        if w > 0:
            return w, "literal"
        sink.add(Diagnostic("E01", "error", where, f"端口 {port.name} 位宽必须 > 0：{w}"))
        return None, "unresolved"
    if isinstance(w, str):
        if w in params:                                          # 2. 参数引用
            v = params[w]
            if v > 0:
                return v, "param"
            sink.add(Diagnostic("E01", "error", where, f"参数 {w} 的值为 {v}，不可作位宽"))
            return None, "unresolved"
        try:                                                     # 3. 受限表达式
            v = _safe_eval(ast.parse(w, mode="eval").body, params, 0)
            if v > 0:
                return v, "expr"
            raise ValueError(f"结果 {v} 非正")
        except (SyntaxError, KeyError, ValueError) as e:         # 不吞异常，转诊断
            sink.add(Diagnostic("E01", "error", where,
                                f"端口 {port.name} 位宽无法解析：{w!r}（{e}）",
                                hint=f"可用参数：{sorted(params)}；或把 width 写成正整数"))
            return None, "unresolved"
    if port.kind.value in ("valid", "ready", "clock", "reset"):  # 4. 隐式 1 位
        return 1, "implicit"
    sink.add(Diagnostic("E01", "error", where, f"端口 {port.name} 缺少位宽"))
    return None, "unresolved"

def bandwidth(width_bits: int | None, freq_hz: float | None,
              explicit_bpc: float | None) -> tuple[float | None, float | None, str]:
    """只服务 node_graph 的**静态**带宽（explicit / derived）。

    实测利用率（trace）不进 node_graph，走 trace_summary.json（见 4.6）。
    GB/s 一律十进制 1e9；bits/cycle 为权威单位（ADR-04）。
    """
    if explicit_bpc is not None:                                  # 1. 显式声明
        gbs = explicit_bpc * freq_hz / 1e9 if freq_hz else None
        return float(explicit_bpc), gbs, "explicit"
    if width_bits and freq_hz:                                    # 2. 位宽推导
        bpc = float(width_bits)
        return bpc, bpc * freq_hz / 1e9, "derived"
    return None, None, "unknown"
```

**缺陷修复说明**：旧骨架的 `except Exception: pass` 会把语法错误静默变成"无位宽"，现在按异常类型转 `E01` 并给可用参数列表；`explicit` 分支不再返回 `None` 位宽却声称成功；`trace` 分支已移出——静态图不允许携带实测带宽，否则 `node_graph.json` 每次跑 trace 都会脏。

## 附录 D：`top.v` 生成模板骨架

```jinja
{# py/rvgen/templates/top.v.j2 —— 骨架，需按第 5.4 节规则补齐
   Jinja 环境固定：trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True
   所有宽度/端口映射在 Python 侧预计算（p.range / c.module / c.bindings），模板不做算术。 #}
// 本文件由 rvgen {{ rvgen_version }} 生成；生成区每次整体重写，请勿手改。
// rvgen:fingerprint {{ top_fingerprint }}
// 用户逻辑只允许写在 // rvgen:user-begin <id> 与 // rvgen:user-end <id> 之间。
{% if contract_notice %}// [W01] {{ contract_notice }}
{% endif %}`timescale 1ns/1ps
module {{ project.top }} (
{% for p in ports %}    {{ p.dir }} wire {{ p.range }}{{ p.name }}{{ "," if not loop.last }}
{% endfor %}
);
{% for w in wires %}    wire {{ w.range }}{{ w.name }};   // 单源多扇出，一条 wire 挂多负载
{% endfor %}
{% for c in cdc_insts %}
    // CDC {{ c.id }}: {{ c.from_domain }} -> {{ c.to_domain }} (kind={{ c.kind }})
    {{ c.module }} #(
{% for b in c.param_bindings %}        .{{ b.name }}({{ b.value }}){{ "," if not loop.last }}
{% endfor %}    ) u_cdc_{{ c.id }} (
{% for b in c.port_bindings %}        .{{ b.port }}({{ b.net }}){{ "," if not loop.last }}
{% endfor %}    );
{% endfor %}
{% for m in insts %}
    {{ m.module }} #(
{% for p in m.param_bindings %}        .{{ p.name }}({{ p.expr }}){{ "," if not loop.last }}
{% endfor %}    ) u_{{ m.inst }} (
{% for p in m.port_bindings %}        .{{ p.port }}({{ p.net }}){{ "," if not loop.last }}
{% endfor %}    );
    // rvgen:user-begin inst.{{ m.inst }}
    // TODO(rvgen): 该实例的附加逻辑写在这里
    // rvgen:user-end inst.{{ m.inst }}
{% endfor %}
endmodule
```

**缺陷修复说明**：① 旧模板 `p.width_expr or p.width_bits - 1` 在 `width_expr` 为空且 `width_bits` 未解析时会抛异常，且单比特口会生成 `[0:0]` 而不是标量——改为 Python 侧预计算 `p.range`（单比特为空串）；② 旧模板把 CDC 一律例化成 `async_fifo`，与 `gen cdc` 的 `two_ff/pulse_sync/handshake/gray_bus` 冲突——改为 `c.module` 由 kind→模块名映射表提供；③ 不再为时钟/复位网重复 `wire` 声明（它们来自顶层端口，重复声明即多驱动）；④ W01 提示只出现在文件头的生成区，绝不进入 USER 块。

## 附录 E：`rvopen` 三平台骨架（需补齐）

```python
# py/rvgen/rvopen.py —— 骨架，需按第 6.1 节签名与第 11 章 R09 补齐
import os, platform, subprocess
from pathlib import Path
from urllib.parse import quote
from .diag import Diagnostic

PROTO = "rvgen"                      # 与旧工程 rv:// 命名空间区分（A12）

def _rel(loc, repo_root: Path) -> str:
    try:
        return Path(loc.file).resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return Path(loc.file).resolve().as_posix()   # 仓外文件用绝对路径，不抛

def url_for(loc, repo_root: Path) -> str:
    line = loc.line or 1
    return f"{PROTO}://open?path={quote(_rel(loc, repo_root))}&line={line}&end={loc.end_line or line}"

def fallback_command(loc, repo_root: Path) -> str:
    return f'code -g "{_rel(loc, repo_root)}:{loc.line or 1}"'

def open_loc(loc, repo_root: Path, sink) -> bool:
    url = url_for(loc, repo_root)
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            subprocess.run(["open", url], check=True)                # LaunchServices
        elif sysname == "Windows":
            os.startfile(url)                                        # 依赖 HKCU 注册，不提权
        else:
            subprocess.run(["xdg-open", url], check=True)            # .desktop + xdg-mime
        return True
    except (OSError, subprocess.SubprocessError) as e:               # 未注册/无处理器
        sink.add(Diagnostic("I06", "info", str(repo_root),
                            f"{PROTO}:// 未注册或打开失败：{e}",
                            hint=f"运行 scripts/register.*；或复制：{fallback_command(loc, repo_root)}"))
        return False
```

**缺陷修复说明**：① 协议名统一为 `rvgen://`；② 删掉 `except Exception` 与 `webbrowser.open` 兜底——浏览器打不开自定义协议，失败必须变成 `I06` 并给可复制命令；③ `relative_to` 在仓外文件会抛 `ValueError`，已显式处理。

## 附录 F：SSE 端点与前端消费骨架（需补齐）

```python
# py/rvgen/server.py 节选 —— 骨架，需按第 7.2 节事件表补齐
import asyncio, itertools, json
from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()
_seq = itertools.count(1)
RING_SIZE = 64                 # 7.2 节约定：最多补发 64 条
SUB_Q = 128

class Hub:
    def __init__(self) -> None:
        self.ring: deque[tuple[int, str, dict]] = deque(maxlen=RING_SIZE)
        self.queues: set[asyncio.Queue] = set()
        self.stalled: set[asyncio.Queue] = set()

    async def publish(self, event: str, data: dict) -> None:
        item = (next(_seq), event, data)
        self.ring.append(item)
        for q in list(self.queues):
            try:
                q.put_nowait(item)          # 绝不 await：慢客户端不得拖住别人
            except asyncio.QueueFull:       # 慢客户端：标记后断开，由前端重连补发
                self.stalled.add(q)
                self.queues.discard(q)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=SUB_Q)
        self.queues.add(q)
        return q

    async def events(self, request: Request):
        q = self.subscribe()
        since = int(request.headers.get("Last-Event-ID") or 0)

        async def gen():
            last = since
            try:
                # 先订阅再补发：补发期间的新事件进队列，靠 last 去重
                if since and self.ring and since < self.ring[0][0] - 1:
                    yield "event: resync\ndata: {}\n\n"      # 已滑出缓冲，前端全量重拉
                    last = self.ring[-1][0]
                else:
                    for item in list(self.ring):
                        if item[0] > last:
                            yield _fmt(item)
                            last = item[0]
                while True:
                    if await request.is_disconnected() or q in self.stalled:
                        break
                    try:
                        item = await asyncio.wait_for(q.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"             # 防代理缓冲（R13）
                        continue
                    if item[0] <= last:
                        continue                              # 补发/队列重叠去重
                    last = item[0]
                    yield _fmt(item)
            finally:
                self.queues.discard(q)
                self.stalled.discard(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

def _fmt(item: tuple[int, str, dict]) -> str:
    eid, ev, data = item
    return f"id: {eid}\nevent: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

```ts
// web/src/api/events.ts —— 骨架，需按第 7.2 节事件表补齐
const es = new EventSource("/api/events");       // 浏览器自动重连，带 Last-Event-ID
es.addEventListener("yaml_changed",  (e) => store.setStale(JSON.parse(e.data)));  // 只置徽标
es.addEventListener("git_state",     (e) => store.setGit(JSON.parse(e.data)));
es.addEventListener("check_result",  (e) => store.setCheck(JSON.parse(e.data)));
es.addEventListener("resync",        () => store.requestFullReload());             // 缓冲滑出：全量重拉
es.onerror = () => store.setConn("reconnecting");   // 不自动拉取 graph（重载需用户点击）
```

**缺陷修复说明**：① 旧代码 `await q.put(...)` 会让一个慢浏览器阻塞所有订阅者，改为 `put_nowait` + 队列满即断开；② 旧代码只发 `resync` 不补发，现按 `Last-Event-ID` 重放环形缓冲，并用 `last` 去重；③ `resync` 后不再逐条补发，由前端重拉快照，避免半新半旧。

## 附录 G：pre-commit / post-checkout hook 骨架

```sh
#!/usr/bin/env sh
# scripts/hooks/pre-commit —— 骨架，需按第 7.3 节补齐
set -eu
repo="$(git rev-parse --show-toplevel)"
# 只检查与声明/图相关的改动；退出码沿用全局口径（0/1/2/3）
if git diff --cached --name-only | grep -qE '(^|/)(rvgen\.yaml|node_graph\.json)$'; then
  rvgen check --quiet --format text      # E -> 1；仅 W 且 --strict -> 2；环境错误 -> 3
fi
exit 0
```

```sh
#!/usr/bin/env sh
# scripts/hooks/post-checkout —— 骨架，需按第 7.3 节补齐
set -eu
prev="${1:-}"; cur="${2:-}"; flag="${3:-}"
[ "$flag" = "1" ] || exit 0                 # 只关心分支切换，不关心文件检出
[ "$prev" != "$cur" ] || exit 0
repo="$(git rev-parse --show-toplevel)"
if command -v rvgen >/dev/null 2>&1; then
  if ! rvgen check --quiet; then
    echo "rvgen: 切换后 node_graph.json 与 rvgen.yaml 不一致" >&2
    echo "       显式更新：rvgen graph --write && rvgen check" >&2
    echo "       （工具不会自动改图）" >&2
  fi
fi
mkdir -p "$repo/.rvgen"
: > "$repo/.rvgen/.git-event"               # 供 server 拾取并推 git_state（watchdog 必须放行）
```

**缺陷修复说明**：① 旧提示让人跑 `rvgen sync && git commit`，但 `sync` 按新口径不写图，会得到"检查→仍失败"的死循环；改为 `graph --write && check`；② `.rvgen/` 可能不存在，`set -e` 下重定向会直接失败；③ 新增 pre-commit 骨架，与 §7.3、CI 共用同一退出码口径。

## 引用来源

[1] https://reactflow.dev/learn/advanced-use/performance
> "Components provided as props to the `<ReactFlow>` component, including custom node and edge components, should either be memoized using `React.memo` or declared outside the parent component."；"modifying the node's `hidden` property dynamically to toggle visibility"；"complex CSS styles, particularly those involving animations, shadows, or gradients, can significantly impact performance."

[2] https://reactflow.dev/learn/layouting/layouting
> "With no effort at all we get a well-organized tree layout! Whenever `getLayoutedElements` is called, we'll reset the dagre graph"；"because the layouting algorithm runs asynchronously we need to create a `useLayoutedElements` hook"；"it's a little more complicated to configure and use compared to dagre and d3-hierarchy."

[3] https://baike.baidu.com/item/Eclipse%20Modeling%20Framework
> "当模型改变时，EMF 支持在保留用户修改的前提下重新生成代码，保持模型与代码的同步。"

[4] https://baike.baidu.com/item/Jinja2/8911090
> "该引擎设计思想源自Django模板系统……其中最显著的一个是增加了沙箱执行功能和可选的自动转义功能。"

[5] https://hsgx.nstl.gov.cn/paper_detail.html?doi=10.1093/bioinformatics/btad031
> "Cytoscape.js is an open-source JavaScript-based graph library. Its most common use case is as a visualization software component… It also can be used in a headless manner, useful for graph operations on a server, such as Node.js."

[6] **FuseSoC / Edalize 官方文档**（fusesoc.readthedocs.io）：core 文件描述 RTL 文件、生成文件、接口依赖、testbench、参数与 target；setup 阶段产出 dependency tree 并写入 EDAM，再由 Edalize 交给具体 EDA 工具。

[7] https://news.qq.com/rain/a/20260605A058QI00
> "某些编辑器（如 VS Code）保存文件时会先创建临时文件再覆盖，这可能导致一次保存触发两次 on_modified。建议在代码中加入时间戳判断，过滤掉连续多次的改动。"

[8] https://www.163.com/dy/article/I1VHPNTK0511D3QS.html
> "大多数开发人员讨厌做可以自动化的事情……pre-commit 步骤：在代码进入版本控制系统之前就检测到问题。"

[9] https://www.163.com/dy/article/HJFJRFRR0553SRCA.html
> "在 GitGuardian，我们使用 pre-commit，一个用 Python 编写的多语言钩子包管理器……您会发现用其他语言（例如 JavaScript）编写的不错的替代方案，例如 husky。"

[10] https://www.sohu.com/a/432332970_121118799
> "Husky 可以帮助我们简单直接地实现 git hooks……在 pre-commit 阶段运行 lint，在 pre-push 阶段运行 test。"

[11] **BusWrap**（efabless）：YAML/JSON 描述 IP（info / parameters / ports / 外部接口）→ APB / AHB-Lite / Wishbone 包装 RTL + testbench + C 头 + Markdown 文档；`v2yaml.py` 可从 `.v` 反生成 YAML 模板。
[12] **Python 插件实践**：`entry_points` 作为"可发现清单"由 `importlib.metadata.entry_points(group=...)` 枚举，宿主用 `abc` 抽象类规定 run/configure/lifecycle 契约与异常约定，避免反射扫描的不可控。

> **未核实项汇总（本环境限制，P0/P1 必须补齐）**：cv32e40p `tracer.rst` 与 cva6 `trace_core_*.log` 的真实列格式与示例行；React Flow v11→v12 破坏性变更清单与 `onlyRenderVisibleElements` 的量化收益；React Flow 核心库与 Pro 的授权边界；`@xyflow/react` 在非 React 环境（Preact/微前端）的可行性；elkjs/dagre/jointJS/Cytoscape.js 的精确包体积与许可证全文；`react-cytoscapejs` 维护状态；FuseSoC `.core` 的当前 schema 字段全集（本机未安装 fusesoc，P2 前若安装则按实际版本 `fusesoc file --parse` 校准，否则仅做 JSON Schema 结构校验）；IP-XACT 与核心模型的字段映射是否需 1:1（初版只做命名对齐，不做转换器）。以上均已在正文对应位置显式标注，不得据此直接写实现代码。
