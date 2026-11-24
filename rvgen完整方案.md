# `rvgen` 项目方案：声明式 Verilog/IP 工程脚手架 + 图形化看板 + Git 一致性闭环

> 面向 AI agent 团队的可独立执行文档。任何未参与前期讨论的 agent 读完本文即可开工，遇到本文未覆盖的情况**停下来记 TODO，不要发明规则**。
> 所有"截至日期"统一为 **2026-11-24**；凡未拿到一手证据的结论均显式标注 `未核实` / `需 PoC 验证`。
>
> **定位（v1.1 修订，最重要的一句）**：`rvgen` 是**通用的 Verilog 工程脚手架工具**，不绑定任何 ISA、不绑定任何应用域。RV32I 软核是它的**第一个验收样例（reference design）**，用来证明工具好用，而不是工具的服务对象。
> 因此：**核心层不得出现任何 CPU / RV32I / 流水线专属概念**；所有领域知识只能以 plugin 形式存在。判定一条代码该放核心还是 plugin，只问一句：*"一个 UART 或 AXI 交叉开关项目需要它吗？"* 不需要就进 plugin。

## 0. TL;DR 与三条最关键决策

**决策一：不自研看板，选 React Flow（`@xyflow/react` v12）+ elkjs/dagre 双布局后端。**
React Flow 是 React 生态里唯一同时具备"受控流式状态 API（`useNodesState`/`applyNodeChanges` 风格）＋自定义节点/边＋小地图/背景/控件开箱可用＋MIT 授权"的节点编辑器。官方性能页给出的优化路径是 memoize 组件与回调、把 `selected` 从 `nodes` 数组里拆出去、用节点 `hidden` 属性做折叠展开、简化节点 CSS（动画/阴影/渐变会明显拖慢）[1]；官方布局指南确认 dagre 是"零配置拿到整齐分层树"的最简方案，elkjs 能力更强但**配置明显更复杂且布局是异步的**，需要封装成 hook 手动驱动 [2]。自研看板至少要多花数人月去补拖拽、缩放、连线吸附、无障碍、移动端触控，收益为零——这是被推翻的旧结论，见第 2 章。

**决策二：单一事实源是 `node_graph.json`，`rvgen.yaml` 是它的唯一上游，布局与 metrics 是旁路。**
静态结构只能来自 YAML；动态数据只能来自 trace；`layout.json` 只存坐标/折叠/视图偏好，**默认不进 git**（进 `.gitignore`），因此 `rvgen check` 永远不会被布局噪声打扰。这是"单向同步"的含义：YAML → 图 → 视图，任何反向写回都禁止。

**决策三：用户代码靠 marker 区块 + fingerprint + orphaned 目录保护，不靠 3-way merge。**
业界成熟做法有两条路：EMF 的 `@generated NOT` 标注（重新生成时保留用户修改）[3]、以及模板继承/区块机制（Jinja2 的 `extends`/`block` 让子模板只填自己的块，父模板可反复重出）[4]。我们选 marker 区间，因为 Verilog 没有可挂注解的 AST 生态，`// rvgen:user-begin <id>` … `// rvgen:user-end <id>` 是最不容易被语法重构打坏的形式。`--fix` 删掉的块**不许静默丢弃**，一律落 `orphaned/<ts>/<module>.<id>.sv.bak` 并在 stderr 打出 `I04`。

**被推翻的旧结论（明示，避免 agent 回头踩）：**
1. ~~自研 HTML/Canvas 看板~~ → 改用成熟开源节点编辑器 + 薄层魔改（自定义节点/自定义边），理由见决策一。
2. ~~看板直接吃 YAML~~ → 引入 `node_graph.json` 作为唯一图形契约，YAML 与视图之间必须隔一层规范化图。
3. ~~文件变更就 auto-reload 覆写视图~~ → 改为"服务端推送失效提示 + 用户手动点重新加载"，且重载时按节点 id 合并保留已有坐标与折叠态。
4. ~~在 Verilog 里拼 JSON~~ → RTL 只 `$fwrite` 定宽文本，`rvgen trace normalize` 在 Python 侧转 JSONL。

### 0.1 v1.1 通用化修订：六条被推翻的假设（**读文档者必看**）

把工具从"RV32I 专用"改成"通用 Verilog 脚手架"，不是改个名字的事。以下六条旧结论**已作废**，agent 若照旧文档实现即为返工：

| # | 旧结论（作废） | 新结论 | 理由 |
|---|---|---|---|
| 1 | `stage: IF/ID/EX/MEM/WB` 是核心必填字段 | 降级为 **`plugins.cpu` 的可选扩展字段**，核心 schema 不认识 `stage` | UART / FIFO / PLL / AXI 交叉开关根本没有流水线级 |
| 2 | 流水线时空图是五大主视图之一 | 改为**条件视图**：图中存在 `lane` 属性才出现，否则不渲染 | 同上；非流水项目看到空图是纯噪音 |
| 3 | RV32I 校验规则（PC 低位、x0 写丢弃等）常驻 checker | 拆为 **core 通用规则（常驻）+ plugin 领域规则（按需注入）** | 对非 CPU 项目报"JALR 低位置 0 未验证"是荒谬的 |
| 4 | trace 契约固定为 CPU 的 `pipe`/`icache`/`dcache` JSONL | `meta.schema` 声明式扩展；核心只认 `cy/pc/instr/disasm/regw`，其余由 plugin 声明 | UART 的 trace 没有 icache，硬套会逼它造假字段 |
| 5 | `top.v` 靠"同名端口自动 connect"拉线 | **显式 `top.ports` 映射表**为唯一依据；自动推导降级为"生成候选 + 标 TODO"，且**时钟/复位永不参与同名连接** | 多 IP  SoC 中 `uart.tx` 与顶层引脚 `tx`、`cpu.clk` 与 `uart.clk` 都同名，盲连必错（详见 5.4） |
| 6 | 声明文件名 `rvgen.yaml` | 改为 **`rvgen.yaml`** | 通用工具占用通用文件名会与其他工具撞名 |

**同时新增三项通用化能力**（v1.1 引入，非 RV32I 也能用）：
- **接口库 `interfaces/`**：命名接口（如 `axi4lite`、`apb`、`uart`、`ready_valid`）一次声明，多模块复用，含方向翻转语义。这是通用化真正的杠杆——Chisel 的 `Bundle` 靠"捕获一次、批量连接、一处修改全局生效"三点获得复用价值[citation:1]，我们用 YAML 表达同样的东西。
- **`rvgen import`**：从已有 `.v` 反向生成 `rvgen.yaml` 骨架（只解析端口/参数/模块头，不解析逻辑）。`BusWrap` 的 `v2yaml.py` 已证明这条路径可行[citation:13]，这是存量 IP 纳管的入口。
- **`rvgen gen fuse-soc`**：生成 FuseSoC `.core` 文件，把文件列表、依赖、参数、target 交给 Edalize 屏蔽 EDA 工具差异[citation:6][citation:5]。**我们自己不造构建系统**——那是重复劳动且注定做不全。

## 1. 需求澄清

### 1.1 已锁定项（不可协商）

| 项 | 锁定内容 |
|---|---|
| **工具定位** | **通用 Verilog 工程脚手架**；服务对象是"任意 Verilog 项目"，RV32I 仅为首个验收样例 |
| 语言/形态 | 纯 Verilog-2005 可综合子集；用户只写逻辑，不写 IO 声明 |
| 声明源 | **`rvgen.yaml`** 是人写的唯一输入；`top.v` 与各模块骨架均可反复覆写 |
| 分层纪律 | **核心层零领域知识**（无 ISA / 无流水线 / 无总线专有概念）；领域能力一律 plugin |
| 用户代码保护 | USER 区块原样保留；删除的块进 `orphaned/`，不得静默丢失 |
| 图形契约 | `node_graph.json` 唯一；静态来自 YAML，动态来自 trace |
| 一致性门禁 | `rvgen check` 语义 diff，非零退出；接 pre-commit 与 CI |
| 跳转 | `rv://` 协议 + 三平台处理脚本，**不做 VSCode 插件** |
| trace | **可插拔 schema**：核心列 `cy/pc/instr/disasm/regw` + `meta.schema` 声明扩展；RTL 内禁止拼 JSON |
| 看板 | 不自研，用开源节点编辑器；只写自定义节点与自定义边；视图按 plugin 注册 |
| 布局存储 | 独立 `layout.json` 或 localStorage；绝不写回 `rvgen.yaml` |
| 构建集成 | 生成 FuseSoC `.core`，不自研构建系统 |

### 1.2 假设项（agent 可按此实现，若与实测冲突则停下报告）

- 假设目标仿真器是 Verilator 与 Icarus Verilog 二者之一，`$fwrite` 行为一致；**若只有其一可用，以该仿真器实测为准**。
- 假设项目规模上限：模块 ≤ 300、单模块端口 ≤ 64、图节点 ≤ 800、边 ≤ 2400。超出即触发第 5.6 节的降级策略。（v1.1 上调：通用场景比单核规模更大）
- 假设用户机器有 Python 3.11.6 与 Node 20 LTS；`vendor/` 离线镜像可用。
- 假设时钟均为同源或有明确 `domain_id`，不存在门控时钟（generated clock 仅允许 PLL 分频，且必须显式声明）。
- 假设 trace 单文件 ≤ 2 GB；超过则按 200 万行分片。
- **假设 `rvgen import` 只需正确解析"模块头 + 端口列表 + parameter"**：不做表达式解析、不做 `generate` 展开、不做 `include` 依赖求解。含 `` `ifdef `` 包裹的端口一律跳过并记 `I05`，要求人工补。

### 1.3 明确不做（NOT_IN_SCOPE）

1. **不在核心层实现任何 ISA / 应用域知识**。RV32I、AXI、UART、Cache 一致性等一律 plugin；`plugins/cpu` 是随仓库发布的**示例 plugin**，不是特权模块。
2. 不做综合/布局布线脚本、时序约束生成、FPGA 板级 IO 约束。**文件列表与 target 交给 FuseSoC `.core`**（v1.1 新增生成项，但不是自建构建系统）。
3. 不做 VSCode 插件、不做浏览器扩展、`rv://` 不做全局 URI Scheme 注册（只给注册脚本，用户自行执行）。
4. 不做 GUI → YAML 的自动写回。GUI 只写 `layout.json`；结构变更必须改 YAML。
5. 不做 diff 可视化、不做波形查看器（只出统计与时空图）。
6. 不做多用户协作、不做服务端持久化数据库、不做鉴权。
7. 不做 formal verification 断言生成（但 `rvgen check` 的静态规则要为其留扩展点）。
8. 不做 SystemVerilog 的 `interface`/`class`/`covergroup` 生成；`rvgen import` 能**读** SV 模块头，但生成恒为 Verilog-2005。
9. 不做 verilator 之外的覆盖率合并。
10. **不做 IP-XACT 读写**，但其数据模型是对齐的参照物（见 2.5）；若将来要做，走 plugin。

### 1.4 启动前需用户确认的开放问题（未确认即按默认值走并记 TODO）

> v1.1 拆为两组：**Q-A 工具自身**（通用，必须现在定）；**Q-B 样例设计**（只影响 `examples/rv32i/`，换样例即换答案，不阻塞核心开发）。

**Q-A 工具自身（阻塞核心开发）**

| # | 问题 | 推荐默认值 |
|---|---|---|
| A1 | 声明文件名 | **`rvgen.yaml`**（`rvgen.yaml` 作废） |
| A2 | 插件发现机制 | `entry_points(group="rvgen.plugins")` + `abc` 契约[citation:14]；同时支持 `rvgen.yaml` 内 `plugins:` 局部注册 |
| A3 | 内置接口库首发范围 | `ready_valid` / `axi4lite` / `axi4stream` / `apb` / `uart` 五个，其余留给项目自定义 |
| A4 | 顶层连线策略 | **显式 `top.ports` 为准**；自动候选只作补齐建议且需 `--accept-wiring` 才落盘（见 5.4） |
| A5 | `layout.json` 是否进 git | **不进**（`.gitignore`），靠 localStorage 兜底 |
| A6 | 带宽默认单位展示 | 内部 `bits/cycle`，UI 附带 GB/s 换算（按该边所在时钟域频率） |
| A7 | 服务器推送通道 | SSE（理由见第 7.2 节） |
| A8 | 前端与后端同端口还是分端口 | 同端口，Vite dev 走 proxy，生产由 FastAPI 托管静态产物 |
| A9 | trace 采样粒度 | 每周期一行，不压缩（压缩交给 `normalize` 的 JSONL） |
| A10 | 是否生成 FuseSoC `.core` | **是**，v1 就做；它是"通用性"最省力的证明 |

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

*图 1：候选方案按本项目加权维度（生态/受控 API/布局适配/魔改成本/授权）的判定分。数据来源：官方文档与仓库事实 [1][2][5]，评分是本项目判断而非第三方基准。*

### 2.2 布局后端：elkjs 与 dagre 的分工

| 维度 | dagre | elkjs |
|---|---|---|
| 能力 | 分层有向图，方向 LR/TB 一行配置 | 分层 + 正交 + 径向 + 树形 + 部件（ports）约束，算法族多 |
| 接入成本 | 同步调用，官方示例即 `getLayoutedElements` [2] | 异步，官方要求封装 `useLayoutedElements` hook [2] |
| 大图 | 纯 JS 同步计算，>500 节点会阻塞主线程（**推断，需 PoC**） | 官方未承诺 worker；我们**自行放进 Web Worker**（浏览器原生能力，与库无关） |
| 包体积 | 小（**具体 kB 未核实**，需 `npm pack` 实测后写进 ADR） | 大（**具体 kB 未核实**，同上） |

**结论**：数据流视图默认 dagre（快、够用），用户切"精细布局"时走 elkjs Worker；时钟树视图用 elkjs 的树形/径向；Cache 状态机用 d3-force（官方示例确认 force 布局是迭代式、需每 tick 回写节点位置，且必须提供开关避免无限计算 [2]）；流水线时空图不用图布局，用网格坐标直算。

### 2.3 被否方案与否决理由（汇总）

| 被否方案 | 否决理由 |
|---|---|
| 自研 Canvas/SVG 看板 | 重复造拖拽/缩放/吸附/无障碍，维护成本远高于薄层魔改 |
| 把 `rvgen.yaml` 直接喂前端 | 前端会被迫理解 YAML 语义，schema 一改两端一起炸；必须有 `node_graph.json` 隔离层 |
| 3-way merge 保护用户代码 | Verilog 无稳定 AST 基线，merge 冲突对用户不可读；marker 方案可预测 |
| 用 Mermaid 作图 | 不可交互、无法挂自定义节点、无法承载 metrics 绑定 |
| SSE 换成 WebSocket | 本场景只有服务端→客户端单向下推，SSE 自带重连与事件 id，WS 要自己补心跳与断线重放 |
| 在 RTL 里拼 JSON | `$fwrite` 拼字符串极易产生非法 JSON（逗号、换行、未刷新缓冲），且不可综合、仿真器间行为不一致 |

### 2.5 通用性参照物：三个"YAML/声明 → 硬件"工具的取舍（v1.1 新增）

通用化不是拍脑袋发明格式，而是站在已有实践上做减法。三个参照物各自解决我们的一部分问题：

| 参照物 | 它做对的事 | 我们采纳 | 我们不采纳 |
|---|---|---|---|
| **FuseSoC / Edalize**[citation:6][citation:5] | core 文件统一描述 RTL 文件、生成文件、接口依赖、testbench、参数、target；Edalize 屏蔽工具差异，一个 core 可换 Verilator / Vivado / VCS | **生成 `.core`，不自建构建系统**；文件列表与 target 由 `rvgen` 产出，`fusesoc run` 负责跑 | 不引入 FuseSoC 作为**库依赖**；不复制它的包管理器与远程库概念（超出范围） |
| **BusWrap**(efabless)[citation:13] | YAML 描述 IP（info / parameters / ports / 外部接口）→ 生成 APB / AHB-Lite / Wishbone 包装 RTL + testbench + C 头 + 文档；`v2yaml.py` 从 `.v` 反生成 YAML 模板 | **接口库 + 多后端生成的思路**；**`rvgen import` 反向导入**（它证明了可行性） | 不把 wrapper 生成做成主功能（我们生成的是骨架 + 例化，不是总线包装）；不做 C 头与位域文档 |
| **IP-XACT (IEEE 1685-2022)**[citation:7] | 标准化组件 / 总线接口 / 连接 / 地址映射 / 寄存器字段的 XML 元数据 + SCR 语义一致性规则 + TGI 生成器接口 | **数据模型对齐**：`component↔module`、`busInterface↔interface`、`addressBlock↔ 预留`、`fileSet↔files`；字段命名尽量可直接映射 | v1 **不实现读写**（XML 繁琐、生态偏大厂工具）；留 plugin 位 |

**从 Chisel `Bundle` 抄来的三条复用原则**[citation:1]：接口类要能"① 一次捕获、多处复用 ② 支持批量连接以削减连线代码 ③ 改一处即全局生效"。我们 YAML 的 `interfaces/` 必须同时满足这三点，否则不如不建。

**反例教训（不采纳 Chisel 的部分）**：绑定 JVM/Scala 工具链、生成物不可编辑、API 破坏性变更导致迁移极痛——正是我们坚持"纯 Verilog 输出 + USER 块保护 + `schema_version` 主版本拒绝加载"的原因。

### 2.4 调研中未能核实、必须 PoC 的项

1. cv32e40p `tracer.rst` 的**逐列字段顺序与示例行**：官方仓库文档页在本次调研环境被安全策略拦截，未能读到原文 → **标注 `未核实`**。P1 阶段必须由 agent 直接读 `cv32e40p/docs/source/tracer.rst` 与 `tb/cv32e40p_tracer.sv` 源码，把真实列序写进 `docs/TRACE_SCHEMA.md` 并用一段真实仿真输出做黄金文件。第 4.4 节给出的列序是**按用户指定的兼容目标写的待验证契约**，不是已从官方原文核实的事实。
2. cva6 `trace_core_*.log` 的列格式：同样 `未核实`，仅确认其存在逐行执行日志（[6] 为链路追踪的一般性材料，不构成证据，故不采信）。
3. React Flow v11 → v12 的破坏性变更清单（包名从 `reactflow` 变为 `@xyflow/react`、`defaultPosition`/`defaultZoom` 等 prop 变化）：`未核实`官方迁移文档全文 → P3 开工前由前端 agent 读官方 migration guide 并写进 ADR-06。
4. React Flow 在**非 React 环境**（纯 Vue/原生页面）不可用：官方未承诺框架无关绑定；若将来要嵌入非 React 页面，方案是 **Preact + `preact/compat` 别名**或 iframe 微前端（`未核实`可行性，需 PoC）。
5. `onlyRenderVisibleElements` 的具体阈值收益与"官方建议节点数上限"：官方性能页**没有给出数字上限** [1]，只给了 memoize/折叠/简化样式三条路径 → 因此第 8 章的性能门槛是我们自己定的验收线，需在 P3 用真实 500 节点页面实测校准。
6. elkjs / dagre 精确包体积、`react-cytoscapejs` 维护状态、各库许可证全文：`未核实`，P0 收尾前由 agent 用 `npm view <pkg> license` + `npm pack --dry-run` 实测并写进 `docs/DEPENDENCIES.md`。

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

**依赖规则（CI 用 import-linter 强制）**：`cli → server → core → schema`；`infra` 只被 `server`/`cli` 调用；`core` **禁止** import `server`/`infra`；`web/` 只能消费 `contracts/` 下由 schema 生成的 TS 类型。任何反向 import 即 CI 失败。

### 3.2 数据流（单向闭环）

```
rvgen.yaml ──loader──> DesignModel ──graph.build──> NodeGraph
                            │                          │
                            └─emitter─> rtl/*.v        ├─ figures.build ─> 各视图 Graph
                                          │            │        │
                                   digest 合并 USER 块  │   layout.service (Worker)
                                          │            │        │
                                   atomic write         │   React Flow 渲染
                                                        │
trace/*.log ──trace.normalize──> JSONL ──trace.attach──> metrics 挂到边/节点
                                                        │
gitw/git_state ──SSE yaml_changed──> 前端"有更新"徽标 ──用户点击──> GET /api/graph
```

**闭环含义**：`check` 失败 → 修 YAML 或跑 `rvgen sync --fix` → 重新 `check` → 绿。CI 与 pre-commit 都跑同一条命令，不存在"本地绿、CI 红"的第二套逻辑。

### 3.3 monorepo 目录结构

```
rvgen/
├─ pyproject.toml            # Python 3.11.6 精确约束，见第 15 章
├─ rvgen.yaml               # 人写，唯一声明源
├─ node_graph.json           # 生成物，进 git，被 check 守护
├─ layout.json               # 视图偏好，默认 .gitignore
├─ .rvgen/
│  ├─ cache/digest.json      # USER 块指纹快照
│  ├─ orphaned/<ts>/         # 被删除/被改名的 USER 块备份
│  └─ snapshots/<ts>/        # 覆写前整文件快照（保留最近 20 份）
├─ py/
│  ├─ rvgen/
│  │  ├─ cli.py  loader.py  model.py  graph.py  emitter.py
│  │  ├─ checker.py  trace.py  digest.py  figures.py  layout.py
│  │  ├─ gitw.py  server.py  rvopen.py  diag.py  atomic.py
│  │  └─ templates/{module.v.j2,top.v.j2}
│  └─ tests/{unit,golden,property,e2e,perf}/
├─ web/
│  ├─ package.json  vite.config.ts  tsconfig.json
│  ├─ src/{App.tsx, api/, store/, flow/{nodes,edges}/, views/, panels/}
│  ├─ contracts/             # 由 schema 生成的 TS 类型（生成物，进 git）
│  └─ e2e/                   # Playwright
├─ schema/{design,node_graph,layout,trace}.schema.json
├─ rtl/                      # 生成 + USER 块；只手改 USER 区
├─ tb/                       # tracer、测试平台
├─ trace/                    # 原始 TSV + normalize 后的 JSONL
├─ docs/                     # 第 13 章交付清单
├─ tests/golden/             # 黄金文件（含 --update-golden 纪律）
├─ .pre-commit-config.yaml  .github/workflows/ci.yml
├─ scripts/{rvopen.sh,rvopen.cmd,rvopen.py,hooks/}
└─ vendor/                   # 离线 wheel + npm tgz
```

## 4. 数据契约（本章最重要）

> 所有 schema 用 **JSON Schema Draft 2020-12**；Python 侧用 `jsonschema` 校验，$schema 字段必填。
> 错误信息友好化做法：用 `Draft202012Validator` 拿到 `iter_errors()`，按 `best_match` 选出最相关错误作为主因，再把 `absolute_path` 转成 `rvgen.yaml` 的点号路径（如 `modules.alu.ports.3.width`），连同 `instance`、`schema` 期望值、以及相邻正确示例一起塞进 `Diagnostic.hint`；批量错误按 `severity` 降序、最多展示 20 条，其余写进 `.rvgen/last_errors.json`。**禁止把 jsonschema 的原始 Exception 直接抛给用户。**
>
> **v1.1 扩展纪律（通用性的命脉）**：核心 schema 一律 `additionalProperties: false`，**且核心层不认识任何领域字段**。领域字段通过两条通道进入，均不污染核心：
> ① **`x-` 扩展属性**：JSON Schema 官方保留前缀，plugin 专属字段写在 `modules[].x-cpu-stage` 这类位置，核心校验器原样透传、不做解释；
> ② **`plugins.<name>` 顶层段**：该 plugin 的独立配置块，由对应 plugin 自己的 schema 校验。
> 多态分支用 `oneOf` + `const` 判别式（判别式派发，避免 O(n) 全分支试匹配与"must match exactly one schema"这类无信息量的报错）[citation:9]。
> **判定标准**：往核心 schema 里加字段前先问"非 CPU、非总线、非缓存的项目需要它吗"，答否则进 plugin。

### 4.0 `rvgen.yaml` 顶层结构（v1.1）

```yaml
schema_version: "1.1"        # 主版本不同即拒绝加载
project: { name, top, default_clock, reset: {...} }
profiles: [asic, fpga]        # 可选；影响生成风格与规则开关，见 4.5
clocks:  [...]
cdc:     [...]
interfaces:                   # 命名接口库（可复用总线束）
  - { name: cpu_bus, type: ready_valid, params: {DATA_WIDTH: 32}, dir_flip: true }
modules: [...]
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

### 4.1 `rvgen.schema.json`（v1.1）逐字段（`"通用核心"` 标记者为所有项目共用）

| 路径 | 类型 | 必填 | 语义与约束 |
|---|---|---|---|
| `schema_version` | string | 是 | 固定 `"1.0.0"`，semver；主版本不同即拒绝加载 |
| `project.name` | string | 是 | `^[a-z][a-z0-9_]{2,31}$`，用作顶层模块名前缀 |
| `project.top` | string | 是 | 顶层模块名，默认 `top` |
| `project.default_clock` | string | 是 | 必须能在 `clocks` 中解析到 |
| `project.reset` | object | 是 | `{name, polarity: active_high\|active_low, sync: bool, levels: int>=2}` |
| `clocks[]` | array | 是 | 至少 1 项；`name` 唯一 |
| `clocks[].freq_hz` | number | 是 | >0；带宽换算的唯一依据 |
| `clocks[].domain_id` | string | 是 | CDC 分组键；同名即同域 |
| `clocks[].source` | enum | 是 | `pll\|pad\|generated`；`generated` 必须填 `parent` |
| `clocks[].parent` | string | 条件 | `source=generated` 时必填且指向已定义 clock |
| `cdc[]` | array | 否 | 跨域桥声明 |
| `cdc[].id` | string | 是 | 唯一 |
| `cdc[].from` / `.to` | string | 是 | 均须是已声明 `domain_id` |
| `cdc[].kind` | enum | 是 | `2ff\|async_fifo\|handshake\|pulse_sync\|gray_bus` |
| `cdc[].width` | int | 条件 | `async_fifo`/`gray_bus` 必填，1..1024 |
| `cdc[].depth` | int | 条件 | `async_fifo` 必填，2 的幂 |
| `cdc[].almost_full` | int | 否 | < depth |
| `modules[]` | array | 是 | 至少 1 项；`name` 唯一且 `^[a-z][a-z0-9_]*$` |
| `modules[].name` | string | 是 | 生成文件名 `<name>.v` |
| `modules[].kind` | enum | 是 | `module\|bridge\|memory\|cache\|clock_gen\|pac`；决定节点类型 |
| `modules[].stage` | string\|null | 否 | **〔plugin:cpu〕** 流水线级名；核心只当透传字符串，不校验取值集合；取值由 `plugins.cpu.lanes` 定义。未填则不进流水线视图（W07 降为 I05） |
| `modules[].stage_index` | int\|null | 否 | **〔plugin:cpu〕** 同级内排序，缺省按声明序 |
| `modules[].clock` | string | 是 | 引用 `clocks[].name`；**单模块必须单时钟**（多时钟 → E09） |
| `modules[].status` | enum | 否 | `draft\|wip\|stable\|frozen`；`frozen` Modules 不再被覆写（E10 保护） |
| `modules[].todo` | string\|null | 否 | 前端显示待办角标，不参与 diff 忽略 |
| `modules[].params[]` | array | 否 | `{name, width\|expr, default, doc}`；`width` 与 `expr` 互斥 |
| `modules[].ports[]` | array | 是 | 至少 1 项；见下 |
| `ports[].name` | string | 是 | 模块内唯一，小写蛇形 |
| `ports[].dir` | enum | 是 | `input\|output\|inout`；`inout` 仅 `kind=memory` 允许 |
| `ports[].width` | int\|string\|null | 否 | 见 5.1 的四级优先链；null 且无法解析 → E01 |
| `ports[].kind` | enum | 否 | `data\|valid\|ready\|handshake\|clock\|reset\|param\|axi`；缺省 `data` |
| `ports[].domain` | string\|null | 否 | 端口所属 clock 名；跨模块连接时域不一致触发 E08 |
| `ports[].default` | string\|null | 否 | 浮空输入兜底值，如 `"1'b0"`、`"{W{1'b0}}"` |
| `ports[].connect` | string\|null | 否 | 显式指定连到 `inst.port` 或常量；不填则按同名推断 |
| `ports[].doc` | string\|null | 否 | 生成注释与前端 tooltip |
| `interfaces[]` | array | 否 | 命名总线束，供多端口一次连线 |
| `interfaces[].name` / `.type` / `.signals[]` | — | 是 | `type` 当前仅允许 `rv_ready_valid`；`signals` 与 type 模板比对 |

**校验附加规则（非纯 schema 能表达，放 `loader.validate_semantic`）**：时钟引用存在性、CDC 两端域不同（`from == to` → W09）、端口名不重复、参数默认值可综合（禁止 `#(` 里出现函数调用）、`stage` 引用未在 `stages` 声明 → E05。

### 4.2 `node_graph.schema.json`（v1）逐字段

| 路径 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `schema_version` | string | 是 | `"1.0.0"` |
| `generated_by` / `generated_at` | string | 是 | `rvgen x.y.z` / ISO-8601 UTC；**不参与语义 diff** |
| `source_digest` | string | 是 | `rvgen.yaml` 的 sha256:前 16，用于判断是否需要重算 |
| `nodes[]` | array | 是 | 见下表；`id` 全局唯一 |
| `nodes[].id` | string | 是 | `mod:<name>` / `clk:<name>` / `cdc:<id>` / `cache:<name>` / `stats:<name>` / `slot:<stage>:<idx>` |
| `nodes[].type` | enum | 是 | `module_node\|clock_node\|cdc_node\|cache_node\|stats_node\|pipeline_slot_node` |
| `nodes[].label` | string | 是 | 展示名 |
| `nodes[].module` | string\|null | 否 | 回指 `modules[].name`，用于 `rv://` 跳转；`clock_node` 可带 `clock` |
| `nodes[].loc` | object\|null | 否 | `{file, line, end_line}`，相对仓库根；缺失则节点不可跳转（W10） |
| `nodes[].stage` / `.domain` | string\|null | 否 | 流水线级 / 时钟域 |
| `nodes[].ports[]` | array | 否 | `{name, dir, width_expr, width_bits, kind, domain}`；`width_bits` 是解析结果，解析失败为 `null` + `unresolved: E01` |
| `nodes[].status` / `todo` | string\|null | 否 | 透传自 YAML |
| `nodes[].metrics` | object\|null | 否 | **动态**：`{cycles, active_cycles, util, toggles, stalls, flushes}`；不参与 check |
| `edges[]` | array | 是 | 见下 |
| `edges[].id` | string | 是 | `<src>.<port>-><dst>.<port>`，稳定可排序 |
| `edges[].source` / `.target` | string | 是 | 节点 id |
| `edges[].source_port` / `.target_port` | string\|null | 否 | 端口名；`clock_node` 出边为 `null` |
| `edges[].kind` | enum | 是 | `data\|handshake\|clock\|reset\|cdc\|param\|bundle` |
| `edges[].width_bits` | int\|null | 否 | 静态位宽；未知为 null |
| `edges[].bandwidth` | object\|null | 否 | **本章核心，见下** |
| `edges[].metrics` | object\|null | 否 | `{bytes, toggles, util, peak}`；动态，不参与 check |
| `edges[].is_critical` | bool | 否 | 缺省 false；来自 trace 或人工标注，**参与 check**（人工标注是静态意图） |
| `viewport` | object\|null | 否 | `{x, y, zoom}`；**check 忽略**，且推荐根本不写进仓库文件 |

**`bandwidth` 的三种来源（互斥且优先级从高到低）**：

| 来源 | 写法 | 计算 |
|---|---|---|
| ① 显式覆盖 | `{"source":"explicit","value":"12.8 GB/s"}` | 原样采用，必须在 `overrides` 里说明理由 |
| ② 静态推导 | `{"source":"derived","width_bits":32,"clock":"clk_core","freq_hz":50000000}` | `bits_per_cycle = width_bits`（每周期一次传输）<br>`GB/s = width_bits × freq_hz / 8 / 1e9` |
| ③ trace 实测 | `{"source":"trace","bytes":1048576,"cycles":20000,"freq_hz":50000000}` | `bits_per_cycle = bytes×8/cycles`<br>`GB/s = bytes × freq_hz / cycles / 1e9` |

**单位规范**：**权威单位是 `bits/cycle`**（与频率解耦，跨时钟域可比）；GB/s 一律按 **十进制** `1e9`，并在 UI 上标注 `GB/s (decimal)`；`KiB/s` 只在 tooltip 里按 `1024` 换算给出。推导源与实测源**同时存在时**，二者分别存 `bandwidth.derived` 与 `bandwidth.traced`，并计算 `utilization = traced.bits_per_cycle / derived.bits_per_cycle`（>1.0 → W05，说明声明位宽不足或 trace 统计口径有误）。`toggles` 单位为"该边信号在采样窗口内的 0/1 翻转次数"，`toggle_rate = toggles / (width_bits × cycles)`。

### 4.3 `layout.schema.json`（v1）

| 路径 | 类型 | 语义 |
|---|---|---|
| `schema_version` | string | `"1.0.0"` |
| `views.<viewId>.nodes[<nodeId>]` | object | `{x, y, collapsed, pinned, group}`；`pinned=true` 时布局算法不得移动 |
| `views.<viewId>.edges[<edgeId>]` | object\|null | `{control_points:[[x,y],...], label_offset:[dx,dy]}` |
| `views.<viewId>.viewport` | object | `{x,y,zoom}` |
| `views.<viewId>.prefs` | object | `{layout_algo, direction, show_metrics, filter_domain[]}` |

**进不进 git 的推荐（默认走这条）**：`layout.json` 写入 `.gitignore`，由浏览器 localStorage 作为主存储、`/api/layout` 作为可选跨机器同步；仓库里只保留 `layout.example.json` 供新成员起步。**理由**：布局是纯主观偏好，进 git 会产生高频无意义 diff 和多分支冲突，而 `check` 必须忽略它——一个"进了 git 却被 check 忽略"的文件比"不进 git"更危险，因为它会诱导人以为它是受控资产。若用户坚持进 git（需确认 Q6），则必须同时加 `.gitattributes -merge` 且 `check` 依旧整体剔除 `layout*`。

### 4.4 `trace.schema.json`（v1.1 改为可插拔）

**设计原则**：核心只认"任何数字设计都有"的五个字段，领域字段由 `meta.schema` 声明，核心不解释、只透传与统计。UART 项目的 trace 没有 `icache`，不该被逼着造假字段。

**核心列（必填，所有项目通用）**——TSV 主体，制表符分隔，逐字固定，RTL 只 `$fwrite` 这些：

```
Time \t Cycle \t Loc \t State \t Ids \t JSON \n
```

| 列 | 格式 | 说明 |
|---|---|---|
| `Time` | `%0t` | 仿真时间，单位由 `` `timescale `` 决定，normalize 统一换算成 ns |
| `Cycle` | `%0d` | 周期计数，从 0 起单调递增；**禁止用 `$time` 代替** |
| `Loc` | `%s` | **通用位置标识**：CPU 是 PC，FSM 是状态编码，流处理是计数器。缺省 `-` |
| `State` | `%s` | **通用进度标识**：CPU 是指令字，其他设计可填当前事务 ID / 通道号。缺省 `-` |
| `Ids` | 定宽增量，仅列被写的存储单元 | CPU 是 `x1=0000002a`；通用设计是 `fifo_cnt=3`；多个用 `,` 分隔；无更新写 `-` |
| `JSON` | 单行、扁平键值对、**无嵌套空格** | 由 `rvgen trace normalize` 解析；RTL 侧只用 `%s`/`%0d` 拼，见下 |

> **命名刻意去 CPU 化**：v1 的 `PC`/`Instr`/`Regs` 三列改名 `Loc`/`State`/`Ids`，语义超集。CPU 项目读起来稍绕，但换来非 CPU 项目不必造假字段——这是通用化的必要代价。
> **兼容层**：`normalize --flavor cpu` 把 `PC/Instr/Regs` 三列别名映射到 `Loc/State/Ids`，老 RTL 与 cv32e40p 风格 trace 继续可用。

**扩展声明（plugin 专属字段，写在 JSON 列里）**：schema 文件用 `oneOf` + `const` 判别式分发[citation:9]，`meta.schema` 取值决定校验分支：

| `meta.schema` | 提供方 | 额外字段 | 解锁的视图 |
|---|---|---|---|
| `rvgen/core` | 核心 | 无（仅核心列） | 周期视图、带宽/翻转统计 |
| `rvgen/cpu@v1` | `plugins/cpu` | `pipe[]`、`ctrl{stall,flush,reason,fwd,taken}`、`icache{}`、`dcache{}` | 流水线时空图、Cache 状态图、气泡构成 |
| `rvgen/bus@v1` | `plugins/bus` | `txn{id,addr,beat,last,kind}`、`stall{reason,cycles}` | 事务时序图、通道占用率 |
| `rvgen/fsm@v1` | 用户自定义 | `fsm{name,from,to,cond}` | 状态机转移图（通用，任何 FSM 都能用） |
| `<项目自定义>` | 项目 | 自定 | 需同时注册前端 renderer，否则只出表格 |

未注册 schema 的字段**不报错**，核心原样保留并在前端以 JSON 表格呈现（降级显示，不崩）。

> **核实状态（未变，仍是 P1 首要任务）**：cv32e40p 官方 tracer 的真实列序在本次调研中**未核实**（官方文档页抓取被拦截）。P1 首要任务是读 `tb/cv32e40p_tracer.sv` 与 `docs/source/tracer.rst`，把真实字段与示例行写进 `tests/golden/trace/cv32e40p_sample.tsv`；若与别名映射假设不符，**以官方为准修订 flavor 解析器**，核心列不受影响。

**JSON 列约定（RTL 侧只允许这样拼）**——前 4 个键是**通用核心**（任何项目都该有），其余为 plugin 扩展：

```
{"meta":{"schema":"rvgen/cpu@v1"},
 "cy":128,
 "cdc":[{"id":"dcpu2io","afull":0,"cnt":3}],
 "arc":[{"e":"alu.result->wb.data","t":1},{"e":"pc->if.addr","t":0}],
 "pipe":[{"s":"IF","pc":"00001000"},{"s":"ID","pc":"00000ffc"},{"s":"EX","pc":"00000ff8"},{"s":"MEM","pc":"00000ff4"},{"s":"WB","pc":"00000ff0"}],
 "ctrl":{"stall":0,"flush":1,"reason":"branch_miss","fwd":"ex2id_rs1","taken":1},
 "icache":{"state":"TAG_CMP","hit":1,"mshr":0},
 "dcache":{"state":"REFILL","hit":0,"beat":2}}
```

| 键 | 归属 | 语义 |
|---|---|---|
| `meta.schema` | 核心 | 判别式，决定走哪个扩展校验分支[citation:9]；缺失按 `rvgen/core` 处理 |
| `cy` | 核心 | 冗余携带 Cycle，便于 JSON 独立消费 |
| `arc[]` | 核心 | 边活跃度：`<src.port>-><dst.port>` + `t` 本周期是否翻转；**零翻转连线在前端标红**（疑似死代码） |
| `cdc[]` | 核心 | 跨域桥水位，任何多时钟设计都有 |
| `pipe[]` / `ctrl` / `icache` / `dcache` | `plugins/cpu` | 流水线槽位、气泡原因、Cache 状态 |
| `txn` / `stall` | `plugins/bus` | 事务节拍与阻塞原因 |
| `fsm{}` | 通用扩展 | `{name,from,to,cond}`，任何状态机都能用，无需写 plugin |

RTL 中的写法必须是**逐字段 `fwrite` 常量格式串**，例如：
`` $fwrite(f, "{\"pipe\":[{\"s\":\"IF\",\"pc\":\"%08x\"},...", if_pc, ...); `` —— 每条格式串一行、字段顺序写死、字符串字面量只含 ASCII、不含换行；`normalize` 用 `json.loads` 严格解析，**解析失败即 `E11` 并报出行号**，不允许容错跳过。

**JSONL 输出（normalize 产物 `trace/<run>.jsonl`）每行**：

```json
{"cycle":128,"time_ns":2560.0,"pc":"0x00001000","instr":"0x002081b3","decoded":{"op":"add","rd":"x3","rs1":"x1","rs2":"x2"},"regw":[{"reg":"x3","value":"0x0000002a"}],"pipe":[{"stage":"IF","pc":"0x00001010"},{"stage":"ID","pc":"0x0000100c"},{"stage":"EX","pc":"0x00001008"},{"stage":"MEM","pc":"0x00001004"},{"stage":"WB","pc":"0x00001000"}],"ctrl":{"stall":false,"flush":true,"reason":"branch_miss","fwd":"ex2id_rs1","taken":true},"icache":{"state":"TAG_CMP","hit":true,"mshr":0},"dcache":{"state":"REFILL","hit":false,"beat":2},"cdc":[{"id":"dcpu2io","almost_full":false,"count":3}],"arc":[{"edge":"alu.result->wb.data","toggle":1}]}
```

### 4.5 版本兼容与迁移策略

- 每个 schema 文件内 `schema_version` 为 semver。**patch** 变化（新增 optional 字段）→ 直接加载；**minor** 变化（新增 required 字段但可给默认）→ 走 transformer 补默认值并打 `I02`；**major** 变化 → 拒绝加载，要求显式跑 `rvgen migrate`。
- 迁移链是**有序纯函数列表** `TRANSFORMERS = [("1.0.0"→"1.1.0", fn), ("1.1.0"→"2.0.0", fn)]`，加载时循环套用到当前版本，**不允许跨级跳变**，每步产物立即用目标版本 schema 校验。
- 迁移前自动把原文件快照到 `.rvgen/snapshots/`；`migrate --dry-run` 只输出 JSON Patch 差异不落盘。
- 前端 `contracts/*.ts` 由 schema 生成（`json-schema-to-typescript`），**生成物进 git**，CI 校验"schema 改了但 contracts 没重新生成"即失败。

## 5. 核心算法规约

### 5.1 端口宽度四级优先链（E01）

```
resolve_width(port):
  1. port.width 是 int                -> 直接用            (来源 literal)
  2. port.width 是 str 且能解析为参数 -> 在 module.params 找同名，取 default，
                                        递归解析（深度上限 8，超过 E01 cycle）
  3. port.width 是 str 且是常数表达式 -> 只允许 "A+B" / "A*B" / "A-1" 三形态，
                                        操作数须为 int 或已解析参数，安全求值
  4. port.kind in (valid,ready,clock,reset) -> 隐式 1        (来源 implicit)
  5. 连接对端已有确定宽度         -> 反向继承 + W03 告警
  6. 以上皆失败                    -> Diagnostic(E01, error, where=port,
       hint="无法解析位宽：请先给 modules.<m>.params.<p> 加 default，或写死 width")
```

**禁止** `eval()`；表达式用 `ast.parse(mode="eval")` + 白名单节点（`BinOp(Add|Mult|Sub)`、`Constant(int)`、`Name`）后手算。

### 5.2 USER 块合并算法（6 步）

*图 2：六段流水线中只有 emit 与 write 可能破坏用户代码。数据来源：本方案第 5.2、5.7 节。*

```
merge(existing_text, generated_text, module_name) -> (new_text, diags):
  # 步骤 1  解析既有文件
  old = split_markers(existing_text)   # -> [(head, id, body, tail), ...]
        # marker 正则：^[ \t]*//[ \t]*rvgen:(user-begin|user-end)[ \t]+([A-Za-z0-9_.-]+)
        # 嵌套 begin 同名 -> E06；end 无匹配 begin -> E06；跨模块 id -> E06
  # 步骤 2  解析新生成文本，得到本轮期望的 block id 集合 expect_ids
  # 步骤 3  匹配：old.id == gen.id 按 id 合并；gen 里新增的 id 用空 body
  # 步骤 4  指纹比对（见 5.3）：契约未变 -> 原样回填 body；契约变了 ->
  #         仍回填 body（用户代码优先）但发 W01 + 在 body 上方插入一行
  #         `// rvgen:warn contract changed since <old_fp> -> <new_fp>, see .rvgen/`
  # 步骤 5  孤儿处理：old 中不在 expect_ids 的块 -> 写
  #         .rvgen/orphaned/<ts>/<module>.<id>.sv.bak，记录 I04，绝不丢弃
  # 步骤 6  组装文本 -> 写 <file>.tmp.<pid> -> fsync -> os.replace(tmp, dst)
  #         -> fsync 目录（见 5.7）
```

**frozen 模块短路**：`status=frozen` 的模块若已存在文件，`emit` 直接跳过并打 `I03`，除非 `--force-unfreeze`。

### 5.3 指纹（fingerprint）

**进指纹**（任一变化 → 契约变更告警）：端口名/方向/位宽解析结果/端口顺序、`params` 名与默认值、模块 `clock`、`kind`、接口签名（`rv_ready_valid` 展开后的信号集合）、`stage`。
**不进指纹**（变了不打扰用户）：`doc`、`todo`、`status`、`loc`、注释、端口在 YAML 中的书写顺序（只在最终 Verilog 端口顺序真的变了才进）、`layout`、`metrics`、`generated_at`。
算法：`sha256(json.dumps(canonical_contract, sort_keys=True, separators=(",",":")))[:16]`，`canonical_contract` 必须经第 6 章 `canonicalize()` 规范化（排序、去默认值、单位归一）。

### 5.4 顶层连线与例化（v1.1 重写：显式映射为准，不再靠"同名"猜）

**为什么改**：v1 的"同名端口自动 connect"在单核内成立，在多 IP SoC 里会连错——`uart.tx` 与顶层引脚 `tx`（对外输出）同名、`cpu.clk` 与 `uart.clk` 同名、`debug_en` 悬空时该接 0 还是该引出到顶层无法判断。隐式约定在规模上去之后必然反噬，所以升级为**显式声明 + 机器校验完整性**。

**连线优先级（高→低，命中即停）**

```
resolve_connection(top_port_or_internal_wire):
  1. top.ports[] 显式映射        -> 唯一权威，直接用；冲突即 E11
  2. port.connect: "inst.port"   -> 模块级显式覆盖（用于非名匹配的特例）
  3. interfaces[] 束连接         -> 按接口模板的 (信号名, 方向) 批量展开；
                                    dir_flip=true 时主从方向翻转（master↔slave）
  4. 同名推断                    -> **仅作候选**：生成时写入
                                    `.rvgen/wiring_suggestions.yaml`，打 W10，
                                    必须 `rvgen sync --accept-wiring` 才会并入 top.ports
  5. 都没有                      -> 输入查 port.default / top.tieoffs，仍无则 E07
```

**四条硬约束（不可放宽）**
- **`role: clock` / `role: reset` 的顶层端口永不参与同名推断**，只能由显式映射或 `modules[].clock` 引用驱动。这是防"把 clk 误连成数据口"的最后一道闸。
- 一个顶层输出只能有**一个**驱动源；两个 `from` 指向同一 `top.ports[].name` → E11。
- `top.ports[]` 未覆盖任何模块的必填输入，且无 `default`/`tieoff` → E07（**列出全部缺失项一次性报出**，不要报一个就停）。
- `top.ports[]` 声明了但找不到对应模块端口 → E02，提示疑似拼写错误并给出 `difflib` 最近邻建议。

| 环节 | 规则 |
|---|---|
| wire 命名 | `<inst>_<port>`；同名冲突加 `_<模块名>` 后缀；长度上限 64，超出用 `w<sha1[:6]>` 并记 W08 |
| 单源多扇出 | 一个驱动 → 一条 wire，多个负载直接挂同一 wire，**不复制驱动** |
| 位宽不一致 | 驱动宽 > 负载宽 → 截断 + W03；驱动窄 → 零扩展 + W03；`kind=clock/reset` 位宽不一致 → E08 |
| 浮空输入 | 有 `port.default` 用之；否则 `valid/ready`→`1'b0`、`clock/reset`→ 报错 E07、数据口 → 接 `{(W){1'b0}}` + W02 |
| 未连接输出 | 一律 W04 告警并生成 `/* rvgen: unused output <p> */` 注释，不自动加 `wire` 以免仿真警告被吞 |
| 参数透传 | 子模块参数缺省取 YAML `default`；顶层用 `parameter` 声明并 `defparam` 禁用，统一 `#(.WIDTH(WIDTH))` 具名传递 |
| 多时钟分组 | 按 `domain_id` 分组生成 `/* ===== clock domain: <id> (<freq>) ===== */` 段落，跨域边若没有对应 `cdc[]` 声明 → E08 |
| CDC 桥例化 | `cdc.kind=async_fifo` 生成带 `async_fifo#(.WIDTH,.DEPTH)` 的例化 + `almost_full` 透出；`2ff` 内联生成两级触发器，不额外建模块 |
| **FuseSoC 集成** | 同目录产出 `<top>.core`：`filesets` 列 `rtl/gen/*.v` + `rtl/*.v`、`depend` 列子 core、`parameters` 映射 YAML params、`targets` 给 `sim`(Verilator+cocotb) / `lint`(Verilator+Verible) / `synth`(Yosys) 三档。**用户跑 `fusesoc run`，我们不实现 runner** |

### 5.5 拓扑排序（Kahn）与环路径回溯

```
topsort(nodes, edges):
  indeg = {n: 入度}; 只算 kind in (data, handshake, bundle) 的边
  q = deque([n for n in nodes if indeg[n]==0 and not is_clock_reset(n)])
  while q: u=q.popleft(); order.append(u)
           for v in succ(u): indeg[v]-=1; if indeg[v]==0: q.append(v)
  if len(order) < len(target):
      # 环路径回溯：从剩余节点里任取 s，沿"前驱指针"走 parent 链
      visited={}; path=[]
      while s not in visited: visited[s]=len(path); path.append(s); s=pred[s]
      cycle = path[visited[s]:] + [s]
      raise Diagnostic(E03, error, where=cycle,
        hint="组合环：" + " -> ".join(f"{n.module}.{n.port}" for n in cycle)
             + "；在回边插一级寄存器或声明 stage 打断")
```

**边界条件**：`clock`/`reset`/`param` 边**不参与**拓扑（否则时钟树必然成环）；自环（同模块同端口对）单独报 E03 并给出单行提示；多解时按 `(stage_index, 声明序)` 稳定排序，保证生成结果**逐字节可复现**（这是幂等验收的前提）。

### 5.6 布局算法选型与超限降级

| 规模 | 策略 |
|---|---|
| ≤ 80 节点 | 单图，dagre 分层（默认 LR），`pinned` 节点固定 |
| 80 < n ≤ 200 | 按 `domain_id` 或 `stage` 拆 subgraph，每簇一张子图 + 簇间聚合边；elkjs 在 Web Worker 里算 |
| 200 < n ≤ 500 | 预渲染 SVG 底图（离线 elk 一次算好存 `layout.cache.json`），交互只在高亮/悬停层；拖拽时不做重排 |
| > 500 | 拒绝交互布局，只提供搜索定位 + 邻域展开（`hidden` 属性控制，符合官方建议 [1]），并打 W06 |

Worker 协议：`{type:"layout", algo, graph, options}` → `{type:"done", positions, algo_version}`；Worker 内 `try/catch` 后必须回 `{type:"error", message}`，主线程超时 10 s 取消并降级到 dagre 同步布局。**ECharts 实例、Worker、ResizeObserver 必须在视图卸载时销毁**，否则切视图次数一多就内存泄漏（第 11 章 R05/R06）。

### 5.7 原子写与崩溃一致性

```
atomic_write(dst, text, bak_dir):
  tmp = dst.parent / f".{dst.name}.tmp.{os.getpid()}"
  fd = os.open(tmp, O_WRONLY|O_CREAT|O_TRUNC, 0o644)
  os.write(fd, text.encode("utf-8")); os.fsync(fd); os.close(fd)
  if dst.exists(): copy2(dst, bak_dir / f"{dst.name}.{ts}")   # 保留最近 20 份
  os.replace(tmp, dst)          # 同文件系统内原子；跨盘会 EXDEV -> 报错不吞
  fsync_dir(dst.parent)         # Windows 无 fd 目录 fsync -> 用 msvcrt.commit 或跳过并记 I01
```

**Windows 特有问题**：`os.replace` 对只读目标、被 VSCode 占用的文件会 `PermissionError` → 重试 3 次（50/150/400 ms 退避），仍失败则报 `E12` 并保留 `.tmp` 文件告知用户路径；路径一律 `pathlib.Path` + `resolve()`，禁止字符串拼 `\\`。

## 6. 模块划分与接口定义

> 通用错误模型（唯一报错方式，禁止裸 `print`）：
> `Diagnostic(code: str, severity: Literal["error","warning","info"], where: Location|list[Location], message: str, hint: str|None = None)`
> `Location = {file: Path|None, line: int|None, col: int|None, json_path: str|None, node_id: str|None}`
> 全局 `DiagnosticSink` 收集 → CLI 渲染成 `file:line:col: code severity message` + 缩进 hint；`error` 数 >0 即退出码 2。

### 6.1 模块清单

| 模块（owner 文件） | 职责 | 公开签名 | 错误语义 | 谁可调 / 禁止 |
|---|---|---|---|---|
| `loader.py` | 读 YAML（含锚点展开上限）、**合并 plugin schema**、校验 | `load(path, plugins) -> tuple[DesignModel, list[Diagnostic]]` | 文件缺失/解析失败 → E09；锚点嵌套 >10 → W10；未知 `x-` 前缀外字段 → E09 | `cli`/`server` 可调；**禁止** import graph/emitter |
| `plugins.py` | **plugin 发现与注册**（`entry_points(group="rvgen.plugins")` + `abc` 契约）[citation:14] | `discover() -> list[Plugin]`；`Plugin{id, schema, rules, views, trace_flavors, node_types}` | plugin 加载失败 → W11 并跳过该 plugin，**不得拖垮核心** | 只被 `loader`/`cli` 调；**禁止**被 graph/emitter import |
| `importer.py` | **从 `.v` 反生成 `rvgen.yaml` 骨架**（正则/词法级解析模块头、端口、parameter） | `import_verilog(src) -> tuple[dict, list[Diagnostic]]` | 解析不出的端口 → I05，要求人工补；**不做**表达式与 `generate` 展开 | 只被 `cli import` 调；**禁止**写任何 `.v` |
| `model.py` | `DesignModel` 与子结构（dataclass，frozen） | `DesignModel.validate_semantic() -> list[Diagnostic]` | 引用悬空 → E05 | 只被 loader/graph/emitter 用；**禁止** IO |
| `graph.py` | YAML → `NodeGraph`：建节点、推边、算带宽、CDC 检测 | `build(m: DesignModel) -> NodeGraph`；`attach_metrics(g, records) -> NodeGraph` | 环 → E03；跨域无边 → E08 | **禁止**读文件、**禁止**布局 |
| `emitter.py` | Jinja2 渲染 + USER 块合并 + 顶层例化 | `emit(m, g, out_dir, sink) -> list[Path]`；`render_top(m,g) -> str` | marker 破损 → E06；原子写失败 → E12 | 只被 `cli.sync` 调；**禁止**改 YAML |
| `checker.py` | 语义 diff | `diff(expected: NodeGraph, actual: dict) -> list[Change]`；`check(...) -> int` | 不一致 → 非零退出 | **禁止**写任何文件（`--fix` 由 cli 调 emitter） |
| `trace.py` | TSV → JSONL、metrics 聚合 | `normalize(src, dst, flavor) -> Stats`；`attach(g, jsonl) -> NodeGraph` | JSON 解析失败 → E11；列数不符 → E11 | **禁止**改 RTL |
| `digest.py` | 契约规范化与指纹 | `canonicalize(node) -> dict`；`fingerprint(node) -> str` | — | 纯函数，谁都能调，**禁止** IO |
| `figures.py` | 从 NodeGraph 派生五种视图的子图 | `build_views(g, kind) -> dict[str, ViewGraph]` | 视图类型未知 → E04 | **禁止**布局（只出逻辑坐标） |
| `layout.py` | 布局服务（dagre/elk 的 Python 侧预计算与缓存） | `layout(view, algo, opts, cache) -> Positions` | 超时 → 降级 + W06 | 被 server 调；**禁止**改图数据 |
| `gitw.py` | `git status --porcelain` 解析、分支/HEAD 状态 | `state(repo) -> GitState`；`watch(repo, cb, debounce=0.4)` | git 不可用 → W10，不影响主流程 | **禁止**执行写类 git 命令 |
| `server.py` | FastAPI + SSE 事件总线 | `GET /api/graph`、`/api/events`、`/api/layout`、`POST /api/reload`、`GET /api/health` | SSE 断线由客户端重连；**禁止**自动触发覆写 | 调 core，**禁止**被 core import |
| `rvopen.py` | `rv://` URL 构造与三平台协议调用 | `url_for(loc) -> str`；`open(loc) -> bool` | 协议未注册 → I04 + 打印手动命令 | 只被 server 调 |
| `fusesoc.py` | 生成 `<top>.core`（filesets / depend / parameters / targets）[citation:6] | `emit_core(m, out_dir) -> Path` | 文件列表为空 → W04 | 只被 `cli.gen` 调；**禁止**执行 `fusesoc run` |
| `cli.py` | 命令分发 | `rvgen {init,sync,check,trace,serve,graph,migrate}` | 退出码：0 成功 / 1 用法错 / 2 有 error diagnostic | 唯一入口；**禁止**业务逻辑内联 |

**统一禁令**：任何模块不得 `except: pass`；不得 `print`；不得修改 `sys.path`；不得在 `core/` 里 import `fastapi`/`watchdog`。

### 6.2 规则码表

| 码 | 级别 | 触发条件 | 修复建议 |
|---|---|---|---|
| E01 | error | 端口位宽四级链全部失败 / 表达式非法 | 给参数加 `default` 或写死 `width` |
| E02 | error | `top.v` 例化缺模块或端口数不匹配 | 跑 `rvgen sync` 重生成 |
| E03 | error | 组合环（含自环） | 回边插寄存器或加 `stage` 打断 |
| E04 | error | 视图类型/布局算法未知 | 检查 `view kind` 拼写 |
| E05 | error | 引用悬空（clock/domain/stage/param） | 修正引用名或补声明 |
| E06 | error | USER marker 残缺/嵌套/重名 | 手动修复 marker 对，再看 `.rvgen/orphaned/` |
| E07 | error | clock/reset 输入浮空且无 default | 补 `connect` 或 `default` |
| E08 | error | 跨域直连未声明 CDC / 时钟复位位宽不符 | 在 `cdc[]` 补桥声明 |
| E09 | error | schema 校验失败（结构/类型） | 按 hint 的点号路径定位字段 |
| E10 | error | 覆写 `status=frozen` 的模块 | 改 status 或加 `--force-unfreeze` |
| E11 | error | trace 列数不符 / JSON 列解析失败 | 检查 RTL `$fwrite` 格式串是否含换行或多余逗号 |
| E12 | error | 原子写失败（权限/占用/跨盘 EXDEV） | 关闭占用进程，检查磁盘与同盘 tmp 目录 |
| W01 | warning | USER 块契约已变更（fp 不同） | 核对端口表，手动适配块内逻辑 |
| W02 | warning | 数据输入浮空被接 0 | 确认这是有意行为，否则补连线 |
| W03 | warning | 位宽截断/扩展 | 显式写 `width` 消除歧义 |
| W04 | warning | 输出未连接 | 接上或加 `/* rvgen: unused */` 注释 |
| W05 | warning | 实测带宽 > 声明带宽（util>1） | 核对位宽与统计口径 |
| W06 | warning | 图规模超限触发降级 | 拆 subgraph 或开启邻域展开 |
| W07 | warning | `kind=module` 未填 `stage` | 补 stage 以进入流水线视图 |
| W08 | warning | wire 名超长被哈希 | 缩短实例名或端口名 |
| W09 | warning | CDC 声明两端同域 | 删除无用声明或修正 domain |
| W10 | warning | 缺 `loc` / git 不可用 / 锚点过深 | 补 loc 或忽略（不影响生成） |
| W11 | warning | plugin 加载失败已被跳过 | 检查该 plugin 的依赖与 schema_version 兼容区间 |
| W12 | warning | 同名推断候选未确认（未跑 --accept-wiring） | Review `.rvgen/wiring_suggestions.yaml` 后并入 `top.ports` |
| W13 | warning | `interfaces[]` 模板参数未替换 | 补全 params，否则生成端口名含字面花括号 |
| W14 | warning | `rvgen import` 有端口未能解析 | 手工补进 rvgen.yaml，见 I05 清单 |
| I05 | info | import 跳过了 `ifdef 包裹或无法解析的端口 | 人工补写，工具不猜 |
| I01 | info | Windows 目录 fsync 跳过 | 无需处理 |
| I02 | info | schema minor 迁移已补默认值 | Review 后提交 |
| I03 | info | frozen 模块已跳过 | — |
| I04 | info | USER 块已备份到 orphaned / 协议未注册 | 查看备份或运行注册脚本 |

## 7. Git 闭环设计

### 7.1 watchdog 去抖与事件语义

**已知语义事实**：编辑器保存常触发多次 `on_modified`（VSCode/IDEA 先写临时文件再覆盖，表现为多次修改事件）[7][8]；因此必须去抖 + 比较内容摘要，不能在回调里做重活 [7]。

```
class Debounce(EventHandler):
    def on_any_event(self, e):
        p = Path(e.src_path)
        if e.is_directory: return
        if p.suffix in {".swp",".swx",".tmp",".part"} or p.name.startswith("."): return   # vim/编辑器临时文件
        if p.name.endswith(".tmp") or ".tmp." in p.name: return                            # 我们自己的原子写中间产物
        if p.parent.name in {"node_modules",".git",".rvgen","__pycache__"}: return
        self.pending[p.resolve()] = time.monotonic()      # 覆盖写：只留最后一次
    # 定时器每 100ms 扫描：距最后事件 >= 0.4s 且内容 sha256 与上轮不同 -> 发事件
```

要点：`FileMovedEvent`/`FileCreatedEvent` 同样入队（原子写表现为 rename，只看 `on_modified` 会漏）；`rvgen.yaml` 用 400 ms 去抖（用户感知即可），`rtl/*.v` 用 800 ms 且只在 `check` 模式下触发；队列满 64 条时丢弃最旧并打 W10。**去抖窗口推荐 300–500 ms，默认 400 ms**（低于 300 ms 会因原子写双事件重复推送，高于 500 ms 手感变钝）。

`git status --porcelain` 解析要点：输出为 `XY PATH`，`X` 是暂存区状态、`Y` 是工作区状态；`??` 未跟踪、`!!` 被忽略、重命名行形如 `R  old -> new`；路径含空格/非 ASCII 时**不要**假设 `core.quotePath=false`，一律加 `-z` 用 `\0` 分隔解析并自己 `codecs.escape_decode`；子模块输出首字节为 `m`。只解析，**不执行**任何写类 git 命令。

### 7.2 SSE 与 WebSocket 的选型结论

**选 SSE**。理由：① 流量单向（服务端→浏览器），WS 的双向能力用不上；② SSE 自带 `id:`/`Last-Event-ID` 与浏览器自动重连，断线续推只需缓存最后一事件号；③ 走普通 HTTP，反向代理只需 `proxy_buffering off;`，不升级协议；④ 无需自研心跳与订阅表。`EventSource` 在断线 3 s 后自动重试，服务端需要每 15 s 发 `:keep-alive` 注释帧防止代理超时。

**事件协议**（`Content-Type: text/event-stream`）：

| event | data | 触发 |
|---|---|---|
| `yaml_changed` | `{path, sha256, at}` | debounce 后 rvgen.yaml 内容真变 |
| `rtl_changed` | `{files[]}` | 生成物或 USER 块变化 |
| `regenerated` | `{by, at, diagnostics[]}` | `sync` 完成 |
| `git_state` | `{branch, head, dirty, counts:{M,A,D,UU}}` | 状态变化或每 30 s 心跳 |
| `check_result` | `{ok, changes[], duration_ms}` | check 完成 |

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
  rvgen check --quiet || { echo "rvgen: node_graph.json 与 rvgen.yaml 不一致，运行 rvgen sync" >&2; exit 1; }
fi
touch "$repo/.rvgen/.git-event"     # server 若在运行会拾取并推 git_state
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
        files: '(design\.yaml|node_graph\.json|py/rvgen/.*\.py)$'
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
      - run: pip install -e .[dev]
      - run: rvgen check --strict          # 含 schema_version 严格校验
      - run: rvgen sync --check            # 生成物与仓库一致
      - run: pytest -q --cov=rvgen --cov-fail-under=90
      - run: pytest -q tests/checker --cov-fail-under=95
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: web/package-lock.json }
      - run: cd web && npm ci --offline && npm run typecheck && npm run test:unit && npm run build
      - run: cd web && npx playwright install chromium && npm run test:e2e
```

`--strict` 的含义：所有 `warning` 也按 error 处理（CI 用，本地不用），并且要求 `node_graph.json` 里的 `generated_by` 版本与当前 CLI 版本一致。

## 7.5 CLI 表面（v1.1 完整命令集）

| 命令 | 作用 | 退出码 |
|---|---|---|
| `rvgen init [PATH] [--preset minimal\|uart\|rv32i]` | 建目录 + `rvgen.yaml` 样例；`--preset` 决定样例域 | 0/3 |
| `rvgen sync [--dry-run] [--strict] [--accept-wiring] [--force-unfreeze]` | 生成骨架 + top + `.core`，合并 USER 块 | 0/1/2/3 |
| `rvgen check [--format github\|json] [--fix] [--strict]` | 语义 diff，不写文件（`--fix` 除外） | 0/1/2 |
| `rvgen import <file.v> [-o rvgen.yaml]` | 从已有 Verilog 反生成声明骨架（W14/I05 报告未解析项） | 0/1 |
| `rvgen gen fuse-soc [--out .]` | 只生成 FuseSoC `.core`，不碰 rtl/ | 0/3 |
| `rvgen graph [--with-trace F] [--view KIND] [--list-cdc]` | 输出 `node_graph.json`；`--list-cdc` 打印跨域桥清单供人工 review | 0/1 |
| `rvgen trace normalize <src> [-o out.jsonl] [--flavor cpu\|auto]` | TSV → JSONL，逐行流式 | 0/1 |
| `rvgen trace stats <f.jsonl>` | 打印 CPI / 气泡构成 / 命中率 / 零翻转连线 Top20 | 0/1 |
| `rvgen plugin list` | 列出已发现 plugin 及提供的 schema/规则/视图 | 0 |
| `rvgen doctor` | 探测 iverilog / verilator / yosys / fusesoc / code 可用性 | 0 |
| `rvgen migrate [--from VER] [--dry-run]` | schema 版本迁移，先快照再改写 | 0/1/3 |
| `rvgen serve [--port 8000] [--no-open]` | 启动 HTTP + SSE，是前端**唯一入口** | 0/3 |

**退出码契约**：`0` 成功；`1` 存在 E 级诊断；`2` 仅 W 级且 `--strict`；`3` 环境/IO 错误。CI 与 pre-commit 只认退出码，不解析文本。

**`--accept-wiring` 的语义**：把 `.rvgen/wiring_suggestions.yaml` 中的同名候选**并入 `rvgen.yaml` 的 `top.ports`**（这是唯一被允许的自动写回，因为它是把隐式候选显式化，不是猜测结论）。并入前后各打一次快照，diff 进 commit message。

## 8. 单元测试与质量门禁

### 8.1 覆盖率门槛

| 范围 | 行覆盖 | 分支覆盖 | 说明 |
|---|---|---|---|
| `py/rvgen/core`（loader/model/graph/emitter/digest/figures/layout） | ≥ 90% | ≥ 85% | `pytest --cov-fail-under=90` |
| `checker.py` + `digest.py` | ≥ 95% | ≥ 95% | 一致性门禁本体，最严 |
| `trace.py` 解析器 | ≥ 92% | ≥ 90% | 含畸形行、缺列、非法 JSON |
| `web/src` | 组件快照全覆盖关键路径 | — | Vitest + Testing Library，阈值 80% statements |

### 8.2 测试文件清单与必测用例（**规则码必须出现在测试函数名里**）

| 文件 | 必测用例（函数名示例） |
|---|---|
| `tests/unit/test_loader_E01.py` | `test_E01_width_unresolvable`、`test_E01_expr_depth_overflow`、`test_E09_missing_required_field`、`test_no_eval_used_in_expr` |
| `tests/unit/test_marker_E06.py` | `test_E06_unclosed_marker`、`test_E06_nested_duplicate_id`、`test_user_block_preserved_byte_identical`、`test_W01_contract_changed_inserts_warn` |
| `tests/unit/test_orphan_I04.py` | `test_I04_deleted_block_goes_to_orphaned`、`test_orphaned_file_content_matches_original`、`test_orphaned_dir_never_deleted` |
| `tests/unit/test_top_E02_E07_E08.py` | `test_E02_port_count_mismatch`、`test_E07_clock_floating`、`test_E08_cross_domain_without_cdc`、`test_multi_fanout_shares_single_wire`、`test_unused_output_W04`、`test_param_passthrough_named` |
| `tests/unit/test_topsort_E03.py` | `test_E03_self_loop`、`test_E03_two_node_cycle_path_reported`、`test_E03_clock_edge_not_in_cycle`、`test_topsort_is_stable_across_runs` |
| `tests/unit/test_atomic_E12.py` | `test_E12_readonly_target_keeps_tmp`、`test_atomic_write_no_partial_on_oserror`、`test_windows_retry_then_fail` |
| `tests/unit/test_trace_E11.py` | `test_E11_column_count_mismatch`、`test_E11_json_column_invalid`、`test_normalize_roundtrip_wellformed`、`test_decoded_field_no_whitespace` |
| `tests/checker/test_diff.py` | `test_ignore_position_and_viewport`、`test_ignore_metrics`、`test_detect_node_added_removed`、`test_detect_port_width_changed`、`test_detect_bandwidth_source_changed`、`test_strict_promotes_warning`、`test_fix_restores_expected` |
| `tests/property/test_random_yaml.py` | `test_random_valid_yaml_always_loads`、`test_parse_print_identity`、`test_normalize_idempotent_twice` |
| `tests/golden/test_golden.py` | `test_golden_top_v_matches`、`test_golden_node_graph_matches`、`test_golden_trace_jsonl_matches` |
| `tests/perf/test_bench.py` | `test_gen_100_modules_20_ports_under_5s`、`test_check_500_nodes_under_2s` |
| `web/src/**/*.test.tsx` | `ModuleNode.snapshot`、`EdgeBandwidthLabel.snapshot`、`ViewSwitcher.test`、`ReloadBanner.test`、`HtmlUrlOpen.test`、`EChartDispose.test` |
| `web/e2e/*.spec.ts` | `load-json.spec`、`drag-node.spec`、`switch-view.spec`、`offline.spec`、`reload-keeps-layout.spec`、`rv-protocol.spec` |

### 8.3 黄金文件与 `--update-golden` 纪律

黄金文件放 `tests/golden/<area>/`，**必须逐个 diff 后人工确认才允许更新**。纪律：① `--update-golden` 只能在专职分支上跑，提交信息必须写清"为什么输出会变"（对应哪个规则码/哪个需求）；② 一次 PR 里黄金文件变更超过 3 个 → 必须有人在 review 中逐行确认；③ 黄金文件一律 LF 换行、无 BOM、末尾单换行，`tests/golden/test_golden.py` 里断言这三条；④ 黄金文件里**不得出现** `generated_at`/绝对路径/机器名，生成前统一用占位符 `<GENERATED_AT>`、`<REPO_ROOT>` 替换。

### 8.4 属性测试与幂等验收

`hypothesis` 策略：`st_module_names()`、`st_port(width_strategy=one_of(int, param_ref, expr))`、`st_clock_tree(depth<=3)`，组合成随机但合法的 YAML；三条不变式：
1. `load → emit → load` 得到的 `canonical_contract` 与原始相同（print-parse identity）；
2. `normalize(normalize(g)) == normalize(g)`；
3. 随机图 `topsort` 结果在环不存在时长度等于节点数，且每次运行结果逐字节相同。

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
| **P0 地基** | `pyproject.toml`、目录骨架、`schema/*.schema.json` v1.1（**含 `x-` 扩展位与 oneOf 判别式**）、`plugins.py` 契约与 `discover()`、`diag.py`、`atomic.py`、CI 空跑、`docs/DEPENDENCIES.md`（含实测体积/许可证）、`vendor/` | `jsonschema` 能校验自身样例；`python -c "import rvgen"` 通过；依赖清单每条有 `npm view`/`pip show` 实测依据 | CI 绿 + 依赖表无"未核实"条目（tracer 列格式除外，那是 P1 的事） |
| **P1 语义核心** | `loader`/`model`/`graph`/`digest`/`importer` + **`plugins/cpu` 首个 plugin** + 规则码 E01/E02/E03/E05/E07/E08/E09/E11/E12/W03/W04/W09/W12/W14 + **`top.ports` 显式连线解析** + 黄金文件框架 | 随机合法 YAML 属性测试 3 条不变式全绿；环路径回溯输出可读；`node_graph.json` 可生成 | core 覆盖 ≥90%，checker 模块骨架 ≥95% |
| **P2 生成器与保护** | Jinja2 模板、`emitter` 六步合并、顶层例化（**以 `top.ports` 为准**）、`wiring_suggestions.yaml`、orphaned、frozen、`fusesoc.py` 产出 `.core`、`rvgen sync/check/import/gen fuse-soc` CLI | `sync && sync && git diff` 为空；USER 块字节级保留；删除块能在 orphaned 找回；`check --fix` 可修复 | 100 模块 20 端口 < 5 s；E06/E02/E07/E12 全有用例 |
| **P3 前端骨架** | Vite+React+TS、React Flow 画布、自定义 `ModuleNode`/`BandwidthEdge`、数据流视图 dagre、详情抽屉、`rv://` 按钮 | 500 节点拖帧 p95 ≥30 FPS；Node/Edge 快照测试绿；未挂载泄漏检查通过 | Playwright `load-json`/`drag-node` 绿；`npm run build` 产物 < 2 MB gzip（**门槛待 PoC 校准**） |
| **P4 多视图 + trace** | 时钟树（径向）、流水线时空图（网格）、Cache 状态机（force）、统计图表、`trace normalize` + `attach` | 六种节点类型全部有视图；带宽三来源在 UI 上可区分；E11 用例绿；ECharts/Worker 卸载无泄漏 | 100 万行 trace 归一化 < 25 s；多视图 E2E 绿 |
| **P5 Git 闭环** | `gitw`、`server` SSE、watchdog 去抖、手动 reload + layout 合并、三平台 `rvopen` 脚本、hook、CI 示例 | 改 YAML 后 ≤1.5 s 出现"有更新"徽标且**视图不被覆写**；点击重载后折叠/坐标/pinned 保留；断网 30 s 后自动重连 | `offline.spec` + `reload-keeps-layout.spec` 绿；hook 在 commit/checkout 各触发一次 |
| **P6 硬化与交付** | 文档全套（第 13 章）、ADR ≥8 篇（新增「核心零领域知识」与「顶层连线显式化」）、HANDOVER、性能报告、变异测试 nightly、迁移 transformer 首例 | 新人按 HANDOVER 半天内跑通 `sync/check/serve`；`check --strict` 全绿；12+ 验收场景逐条打勾 | 全部文档无"TBD"；版本号打 `1.0.0` tag |

## 10. agent 分工与子代理接口

### 10.1 主 agent 职责

1. 持有 `rvgen.yaml`、`schema/`、`pyproject.toml`、CI 配置、ADR 的**最终裁决权**（这些文件只有主 agent 能改）。
2. 拆分任务卡、派发、验收（跑验收命令、看 diff）、合并、打 tag。
3. 维护 `docs/DECISIONS.md`：任何规格未覆盖的提问与其默认值决议都记在这里，带日期。
4. 冲突仲裁：子 agent 之间接口不一致时，先改 `schema/` 与本文第 4/6 章，再让各方跟随。

### 10.2 子 agent 切分方式：**按层切，不按文件切**

| 子 agent | 层 | 拥有的目录 | 不得触碰 |
|---|---|---|---|
| A `core-sem` | 语义层（**零领域知识**） | `py/rvgen/{loader,model,graph,digest,plugins,importer}.py`、`tests/unit/test_loader_*.py`、`test_topsort_*.py`、`test_wiring_*.py`、`test_plugin_*.py`、`test_import_*.py` | `emitter`/`web`/`schema`（只读）；**禁止**在核心写 `is_cpu` 之类分支 |
| B `gen` | 生成层 | `py/rvgen/{emitter,atomic}.py`、`templates/`、`tests/unit/test_marker_*.py`、`test_orphan_*.py`、`test_atomic_*.py`、`test_top_*.py` | `graph.py`、`web` |
| C `trace` | 观测层 | `py/rvgen/trace.py`、`tb/`、`tests/unit/test_trace_*.py`、`trace/` | 其余 |
| D `gate` | 门禁层 | `py/rvgen/{checker,cli,fusesoc}.py`、`tests/checker/`、`tests/golden/`、`tests/property/`、`tests/migration/` | `core` 实现（只读接口） |
| E `web-flow` | 前端画布 | `web/src/{flow,views}/`、`web/e2e/` | `web/src/api` 契约（只读 `contracts/`） |
| F `web-shell` | 前端外壳与服务 | `web/src/{App,api,store,panels}/`、`py/rvgen/{server,gitw,rvopen,layout,figures}.py`、`scripts/` | `flow/` 内部 |
| G `plugin-cpu` | **领域 plugin（示例）** | `plugins/cpu/{schema,rules,views,trace}.py`、`examples/rv32i/`、`examples/uart/` | **核心层一切文件**（这是 G01/G02 的纪律保障） |

### 10.3 任务卡模板（每个子任务必须填满）

```
【任务卡】id: P2-B-03    负责人: gen    依赖: P1 退出标准已达成
上下文（必读，按顺序）：
  1) result.md 第 1.1/5.2/5.3/5.7/6.1/8.2 节
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
| `rvgen.yaml`、`schema/*`、`pyproject.toml`、`.github/*`、`docs/DECISIONS.md`、`docs/ADR/*`、`result.md` | 主 agent |
| `py/rvgen/{loader,model,graph,digest,plugins,importer}.py` | A `core-sem` |
| `py/rvgen/{emitter,atomic}.py`、`templates/` | B `gen` |
| `py/rvgen/trace.py`、`tb/` | C `trace` |
| `py/rvgen/{checker,cli,fusesoc}.py`、`tests/golden/`、`tests/property/`、`tests/migration/` | D `gate` |
| `web/src/flow/`、`web/src/views/`、`web/e2e/` | E `web-flow` |
| `web/src/{App,api,store,panels}.ts(x)`、`py/rvgen/{server,gitw,rvopen,layout,figures}.py`、`scripts/` | F `web-shell` |
| `plugins/**`、`examples/**` | G `plugin-cpu` |
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
| R09 | `rv://` 协议未注册或注册需管理员权限 | 高 | 中 | 提供 `scripts/rvopen.{sh,cmd,ps1}` + `register.{sh,ps1}`；未注册时回退复制命令到剪贴板并打印 URL；macOS 用 `open`、Windows 用 `start`/注册表 `HKCU`（不提权）、Linux 用 `xdg-open` + `~/.local/share/applications` | F |
| R10 | trace 文件过大撑爆内存 | 中 | 高 | `normalize` 严格逐行流式；按 200 万行分片输出 `part-0000.jsonl`；前端只加载窗口区间 + 汇总 JSON | C `trace` |
| R11 | YAML 锚点/别名滥用导致不可读与嵌套爆炸 | 中 | 中 | 锚点嵌套深度 >10 → W10；`rvgen graph --expand-yaml` 输出展开后的平铺 YAML 供 review；文档示例一律不用锚点 | A |
| R12 | schema 迁移破坏旧仓库 | 中 | 高 | transformer 链 + `--dry-run` 差 +迁移前快照；CI 用 `tests/migration/fixtures/v1.0.0/` 真实样本跑通到最新 | 主 agent |
| R13 | SSE 被反向代理缓冲导致事件延迟分钟级 | 中 | 中 | 显式要求 `proxy_buffering off`、`X-Accel-Buffering: no`；15 s 心跳注释帧；事件带 `id:`，客户端用 `Last-Event-ID` 续推；给出 nginx/Caddy 两段配置示例 | F |
| R14 | 编辑器原子写触发虚假变更事件（一次保存 N 条） | 高 | 中 | 400 ms 去抖 + 内容 sha256 去重 + 过滤 `.tmp/.swp` 与 `node_modules/.git/.rvgen` [7][8]；把"一次保存只推一条"写成 E2E 用例 | F |
| R15 | React Flow 版本升级破坏自定义节点 | 中 | 中 | 锁 `package-lock.json` + `npm ci --offline`；自定义节点/边共 2 个文件，升级影响面可控；v11→v12 迁移指南在 P3 前读完写进 ADR-06 | E |
| R16 | 中文注释在不同编辑器下编码错乱 | 低 | 低 | 全仓 UTF-8 无 BOM + `.editorconfig` + pre-commit `check-encoding` 钩子 | 主 agent |
| R17 | 前端把 metrics 写回 YAML 污染声明源 | 低 | 高 | `api` 层只读；`layout`/`metrics` 的 POST 端点只接受 `layout.json`；CI 断言 `rvgen.yaml` 不含 `metrics:` 键 | D `gate` |

## 12. 验收场景清单（逐条打勾）

- [ ] AC01 全新 clone 后 `pip install -e .[dev] && cd web && npm ci --offline` 一次成功，无需联网。
- [ ] AC02 `rvgen init demo` 生成可编译的 `rvgen.yaml` 样例与 `rtl/top.v`，`verilator --lint-only rtl/*.v` 无 error。
- [ ] AC03 用户只在 USER 块里写逻辑，`rvgen sync` 后逻辑原样存在、`git diff` 只显示非 USER 区变化。
- [ ] AC04 删掉一个 USER 块后 `rvgen sync`，`.rvgen/orphaned/` 出现同名 `.bak`，stderr 出现 `I04`，退出码 0。
- [ ] AC05 `sync && sync && git diff` 为空（幂等）。
- [ ] AC06 手改 `node_graph.json` 一个端口位宽 → `rvgen check` 非零退出，输出含点号路径与修复 hint。
- [ ] **AC07（通用性核心验收）** 用 `examples/uart/`（含 `uart` + `fifo` + `baud_gen` 三模块、**零 CPU 概念**）跑通 `init → sync → check → serve`，全程**不启用 `plugins/cpu`**，且不出现任何 W07/I05 以外的告警。
- [ ] **AC08** 同一仓库内 `examples/rv32i`（启用 `plugins/cpu`）与 `examples/uart`（不启用）并存，两套 `node_graph.json` 互不干扰；`rv32i` 出流水线时空图，`uart` **不出**该视图且无空图占位。
- [ ] **AC09** `rvgen import examples/uart/rtl/uart.v` 生成 `rvgen.yaml` 骨架，端口/参数与手写版**逐字段一致**；`ifdef 包裹的端口进 I05 清单而非被猜出来。
- [ ] **AC10** 声明 `top.ports` 中两个 output 都 `from: uart.tx` → `E11` 且明确指出冲突双方；把 `role: clock` 端口改名成与某数据口同名 → **不产生连线**，仅 W12 候选。
- [ ] **AC11** `rvgen gen fuse-soc` 产出的 `.core` 能被 `fusesoc run --target lint` 直接消费（若环境无 fusesoc，则以 `fusesoc file --parse` 等价校验替代，并记入 `doctor` 跳过说明）。
- [ ] **AC12** 在核心层 `grep -rnE "is_cpu|rv32i|JALR|pipeline_stage" py/rvgen/` **零命中**（CI 硬门禁，见 15.1 铁律 11）。
- [ ] **AC13** 伪造一个坏 plugin（schema 非法 + 抛异常），`rvgen plugin list` 报 W11 并跳过，**其余命令仍正常退出 0**。
- [ ] **AC14** `examples/rv32i` 的 trace 用 `--flavor cpu` 归一化，`examples/uart` 用核心列（`meta.schema=rvgen/core`）归一化，两者都能进同一前端；UART 的 `Loc/State/Ids` 正常显示且 JSON 列不报错。
- [ ] AC07 `rvgen check --fix` 能把上一步的手改恢复成规范图，且再次 `check` 通过。
- [ ] AC08 `node_graph.json` 里改 `viewport`/`nodes[].position`/`metrics` → `check` **依然通过**（证明忽略字段生效）。
- [ ] AC09 在 YAML 里制造一个两模块组合环 → `sync` 报 `E03`，消息里打印完整环路径。
- [ ] AC10 声明两个不同 `domain_id` 之间直连 → 报 `E08`；补上 `cdc[]` 后通过。
- [ ] AC11 端口位宽写错成未声明参数 → 报 `E01`，hint 里给出可用的参数名列表。
- [ ] AC12 `web/index.html` 用 `rvgen serve` 打开，能加载 `node_graph.json`，五种节点类型均有自定义外观。
- [ ] AC13 每条边的标签同时显示位宽与带宽，三种来源（explicit/derived/trace）图标可区分，鼠标悬停给出 GB/s 与 bits/cycle 双单位。
- [ ] AC14 切换数据流/时钟树/流水线/Cache 状态机/统计五视图，坐标不串、无 canvas 残留、内存增长 <20%（切 20 次）。
- [ ] AC15 另开终端改 `rvgen.yaml` 保存一次 → 页面在 1.5 s 内出现"源已变更"徽标，**视图内容未变**；点击重新加载后图更新，且手动拖动过的节点位置、折叠态、pinned 全部保留。
- [ ] AC16 `layout.json` 不在 `git ls-files` 中（默认配置下），`rvgen.yaml` 中不含任何 `x`/`y`/`position` 字段。
- [ ] AC17 点击节点 → 三平台脚本之一打开 VSCode 并定位到 `rtl/<m>.v:<line>`；协议未注册时给出可复制的 fallback 命令。
- [ ] AC18 `rvgen trace normalize tb/out.tsv trace/run.jsonl` 产出合法 JSONL，每行可被 `json.loads` 解析，抽样 100 行字段齐全（pipe/ctrl/regw/icache/dcache/cdc/arc）。
- [ ] AC19 故意在 RTL `$fwrite` 格式串里插入换行 → `normalize` 报 `E11` 并给出行号，不产出半截 JSONL。
- [ ] AC20 `git commit` 触发 pre-commit 跑 `rvgen check`；故意弄脏 `node_graph.json` 后 commit 被阻断。
- [ ] AC21 `git checkout` 切分支后 post-checkout 钩子触发一次 `check`，脏图能被发现。
- [ ] AC22 CI 全流程（含 Playwright）在 `ubuntu-22.04` 上一次通过；`--strict` 模式下无 warning 漏出。
- [ ] AC23 断网 30 s 后 SSE 自动重连，重连期间页面可正常拖拽，恢复后补发一次 `git_state`。
- [ ] AC24 500 节点图拖拽 p95 帧率 ≥30 FPS；200 节点 elkjs 布局在 Worker 内 <1.5 s 且拖动不卡。
- [ ] AC25 `docs/HANDOVER.md` 交给一名未参与者，半天内独立完成 AC02–AC05 与一次视图切换。

## 13. 文档交付清单

| 文档 | 必含内容 |
|---|---|
| `README.md` | 30 秒上手：安装 → `init` → `sync` → `serve` → 打开浏览器；故障速查表前 5 条 |
| `ARCHITECTURE.md` | 第 3 章分层图、依赖方向规则、数据流闭环、monorepo 地图 |
| `ADR-01 为何选开源节点编辑器而非自研看板` | 成本对比、自研需补的能力清单、React Flow 官方性能路径 [1][2] |
| `ADR-02 为何用 marker 区间而非 3-way merge` | EMF `@generated NOT` 与 Jinja2 block 机制对照 [3][4]、Verilog 无 AST 基线、失败模式 |
| `ADR-03 为何单向同步（YAML→图→视图）` | 双向同步的冲突不可判定性；layout 旁路；反向编辑的替代方案（改 YAML） |
| `ADR-04 带宽单位的确定` | 权威单位 bits/cycle、GB/s 十进制、三来源优先级、util>1 的含义 |
| `ADR-05 为何 trace 兼容 cv32e40p` | 复用现有 tracer 与回归资产；**含"官方列格式未核实、待 P1 用真实输出校准"的显式声明** |
| `ADR-06 前端框架与布局库选型` | React Flow v12 + dagre/elkjs 分工、v11→v12 迁移核对结果、Cytoscape 降级为布局候选 [5] |
| `ADR-07 SSE 而非 WebSocket` | 单向流量、重连与 Last-Event-ID、代理缓冲代价、R13 缓解 |
| `ADR-08 生成器不该变成第二个语言` | 模板复杂度预算、逻辑下沉规则、业界对生成代码不可编辑痛点的教训 |
| `YAML_REFERENCE.md` | 第 4.1 节全字段表 + 3 个完整示例（单核 5 级 / 带 CDC / 带 Cache） |
| `NODE_GRAPH_REFERENCE.md` | 第 4.2 节全字段 + 带宽三来源算例（含具体数字：32 bit × 50 MHz = 200 Mb/s = 0.2 GB/s） |
| `TRACE_SCHEMA.md` | TSV 列定义 + JSON 列字段表 + 一段真实样例（P1 用官方 tracer 实跑填充）+ normalize 输出示例 |
| `WEBUI.md` | 五视图说明、交互手势、`rv://` 使用与三平台注册步骤、离线模式 |
| `EXTENDING.md` | 加一种节点类型/一种视图/一种 CDC 类型的 6 步流程与必改文件清单 |
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
9. **不许把 metrics/layout/position 写进 `rvgen.yaml` 或让它影响 `check`**。
10. **每个阶段一个 commit**，commit 前必跑该阶段验收命令并贴输出进交接产物。
11. **黄金文件必须人工 diff 后才允许 `--update-golden`**，提交信息写明原因与对应规则码。
12. **遇到规格未覆盖的情况停下来问**：写进 `docs/DECISIONS.md` 的"待决议"区，用第 1.4 节的默认值临时推进并标 `TODO(Qn)`，不许自行发明语义。
13. **不许删除或覆盖 `.rvgen/orphaned/` 与 `.rvgen/snapshots/` 中的任何文件**；清理策略由主 agent 定（保留最近 20 份 / 30 天）。
14. **不许用 `eval`/`exec`**，表达式解析一律 `ast` 白名单。
15. **核心层零领域知识**：`py/rvgen/` 下任何文件不得出现 `is_cpu`、不得判断 `stage` 取值、不得出现 ISA 专有字段名；CI 用 `grep -rnE` 硬门禁（AC12）。
16. **顶层连线只读 `top.ports`**：同名推断只写 `.rvgen/wiring_suggestions.yaml` 并报 W12，落盘必须经 `--accept-wiring` 显式确认；`role: clock/reset` 的端口永不参与同名推断。

## 15. 技术栈锁定与版本

| 层 | 锁定 | 约束方式 |
|---|---|---|
| Python | **3.11.6**（精确） | `pyproject.toml`: `requires-python = "==3.11.*"`，README 写明 3.11.6；CI matrix 只跑 3.11.6 |
| 核心依赖 | `pyyaml>=6.0.1`、`jsonschema>=4.21,<5`、`jinja2>=3.1.3`、`watchdog>=4.0`、`fastapi>=0.110`、`uvicorn[standard]>=0.27`、`pytest>=8`、`pytest-cov`、`hypothesis>=6.100`、`pytest-benchmark`、`mutmut`（可选）、`import-linter`、`json-schema-to-typescript`（CLI） | 全部 `==` 精确锁进 `pyproject.toml` 的 `[project.optional-dependencies]`，`pip-tools` 编译出 `requirements.lock` |
| Node | **20 LTS**（`>=20.11 <21`） | `.nvmrc` + `engines` 字段 + CI |
| 前端 | `react`/`react-dom` **18.3.x**、`@xyflow/react` **12.x**、`vite` **5.x**、`typescript` **5.4.x**、`elkjs` 最新稳定、`@dagrejs/dagre` 最新稳定、`echarts` **5.5.x**、`@tanstack/react-query` 5.x、`vitest` 1.x、`@testing-library/react` 14.x、`@playwright/test` 1.4x | `package-lock.json` 进 git；`npm ci --offline`；`engines` + `npm config set engine-strict true` |
| 不使用 | Vue/jointJS/GoJS/Cytoscape 作为主编辑器；Redux（用 `zustand`）；`reactflow` v11 包名 | 违反即 CI 的依赖白名单检查失败 |
| 离线 | `vendor/wheels/`（`pip download -r requirements.lock -d vendor/wheels`）+ `vendor/npm/`（`npm pack` 全量 tgz + 本地 registry 或 `file:` 依赖） | `pip install --no-index --find-links vendor/wheels`；`npm ci --offline`；CI 断网 job 验证 |
| 版本兼容 | 全仓 UTF-8 无 BOM、LF 换行；`.editorconfig` + `.gitattributes` 强制 | pre-commit `check-yaml`/`end-of-file-fixer`/`trailing-whitespace` |

**版本决策理由**：React 18.3 而非 19 —— `@xyflow/react` 与 Testing Library 对 19 的兼容矩阵**未核实**，锁 18.3 Risk 最低，19 升级留作独立 ADR；Vite 5 而非 6/7 —— 生态插件兼容成熟，**6/7 的具体差异未核实**；`jsonschema` 4.x 提供 Draft 2020-12 与 `best_match`，错误友好化够用且不引入额外校验框架。

## 附录 A：`digest.py` 骨架（需按接口定义补齐）

```python
# py/rvgen/digest.py —— 骨架，需按第 5.3、6.1 节接口补齐
from __future__ import annotations
import hashlib, json
from typing import Any
from .model import ModuleDecl, PortDecl

_CONTRACT_FIELDS = ("name", "kind", "clock", "stage", "params", "ports", "interfaces")

def canonicalize(m: ModuleDecl) -> dict[str, Any]:
    """只把"契约"字段规范化；doc/todo/status/loc 一律不进。"""
    out: dict[str, Any] = {
        "name": m.name,
        "kind": m.kind.value,
        "clock": m.clock,
        "stage": m.stage,
        "params": sorted(
            [{"name": p.name, "default": p.default, "width": p.width} for p in m.params],
            key=lambda d: d["name"],
        ),
        "ports": sorted(
            [{
                "name": p.name, "dir": p.dir.value,
                "width_bits": p.width_bits,      # 已是解析结果，None 表示未解析
                "kind": p.kind.value, "domain": p.domain,
            } for p in m.ports],
            key=lambda d: d["name"],             # 按名字排序：书写顺序不进指纹
        ),
        "ifaces": sorted(i.type for i in m.interfaces),
    }
    return {k: out[k] for k in _CONTRACT_FIELDS if out.get(k) not in (None, [], "")}

def fingerprint(m: ModuleDecl) -> str:
    blob = json.dumps(canonicalize(m), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
```

## 附录 B：`emitter` USER 块合并骨架（需补齐）

```python
# py/rvgen/emitter.py 节选 —— 骨架，需按第 5.2 节六步与第 6.1 节签名补齐
import re
from pathlib import Path
from .atomic import atomic_write
from .diag import Diagnostic, DiagnosticSink

BEGIN = re.compile(r"^[ \t]*//[ \t]*rvgen:user-begin[ \t]+([A-Za-z0-9_.-]+)[ \t]*$", re.M)
END   = re.compile(r"^[ \t]*//[ \t]*rvgen:user-end[ \t]+([A-Za-z0-9_.-]+)[ \t]*$", re.M)

def split_markers(text: str, sink: DiagnosticSink, where) -> dict[str, str]:
    blocks: dict[str, str] = {}
    stack: list[str] = []
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        mb, me = BEGIN.match(line.rstrip("\n")), END.match(line.rstrip("\n"))
        if mb:
            if stack: sink.add(Diagnostic("E06", "error", where, f"USER 块嵌套：{mb.group(1)}"))
            stack.append(mb.group(1)); out.append(line); continue
        if me:
            if not stack or stack[-1] != me.group(1):
                sink.add(Diagnostic("E06", "error", where, f"user-end 无匹配 begin：{me.group(1)}"))
            else:
                blocks[stack.pop()] = "".join(out).split("\n", 1)[-1]  # 占位，实际需按索引切片
            out.append(line); continue
        if stack: out.append(line)
    if stack: sink.add(Diagnostic("E06", "error", where, f"未闭合 USER 块：{stack}"))
    return blocks

def merge(existing: str | None, generated: str, module: str,
          fp_old: str | None, fp_new: str, sink: DiagnosticSink, where) -> str:
    old = split_markers(existing or "", sink, where) if existing else {}
    expect = set(BEGIN.findall(generated))
    for bid, body in old.items():                     # 步骤 5：孤儿
        if bid not in expect:
            sink.add(Diagnostic("I04", "info", where,
                                f"USER 块 {module}.{bid} 已失效，备份到 .rvgen/orphaned/"))
    if fp_old and fp_old != fp_new:
        sink.add(Diagnostic("W01", "warning", where,
                            f"{module} 契约变更 {fp_old}->{fp_new}，请核对 USER 块"))
    def repl(m: re.Match) -> str:                     # 步骤 3/4：按 id 回填
        bid = m.group(1)
        return m.group(0) + (old.get(bid, "") if bid in old else _placeholder(bid))
    return BEGIN.sub(repl, generated)
```

## 附录 C：`graph.py` 位宽解析与带宽推导骨架

```python
# py/rvgen/graph.py 节选 —— 骨架，需按第 5.1、4.2 节补齐
import ast
from .diag import Diagnostic

def resolve_width(port, params: dict[str, int], sink, where) -> tuple[int | None, str]:
    w = port.width
    if isinstance(w, int) and w > 0:
        return w, "literal"
    if isinstance(w, str) and w in params:                     # 2. 参数引用
        return params[w], "param"
    if isinstance(w, str):                                     # 3. 受限表达式
        try:
            tree = ast.parse(w, mode="eval")
            v = _safe_eval(tree.body, params, depth=0)
            if v is not None and v > 0:
                return v, "expr"
        except Exception:
            pass
    if port.kind in ("valid", "ready", "clock", "reset"):      # 4. 隐式 1 位
        return 1, "implicit"
    sink.add(Diagnostic("E01", "error", where,
                        f"端口 {port.name} 位宽无法解析：{w!r}",
                        hint="可在 params 中加 default，或把 width 写成整数")) 
    return None, "unresolved"

def bandwidth_bits_per_cycle(width: int | None, freq_hz: float, cycles: int,
                             bytes_traced: int | None, explicit: str | None):
    """返回 (bits_per_cycle, gb_s_decimal, source)。GB/s 一律十进制 1e9。"""
    if explicit is not None:
        return None, float(explicit.split()[0]), "explicit"     # 解析需补齐单位表
    if bytes_traced is not None and cycles > 0:
        bpc = bytes_traced * 8 / cycles
        return bpc, bytes_traced * freq_hz / cycles / 1e9, "trace"
    if width and freq_hz > 0:
        return float(width), width * freq_hz / 8 / 1e9, "derived"
    return None, None, "unknown"
```

## 附录 D：`top.v` 生成模板骨架

```jinja
{# py/rvgen/templates/top.v.j2 —— 骨架，需按第 5.4 节规则补齐 #}
// 本文件由 rvgen {{ rvgen_version }} 生成，请勿手改生成区。
// 用户逻辑只允许写在 // rvgen:user-begin <id> 与 // rvgen:user-end <id> 之间。
`timescale 1ns/1ps
module {{ project.top }} #(
{% for p in top_params %}    parameter {{ p.name }} = {{ p.default }}{{ "," if not loop.last }}
{% endfor %}
) (
{% for p in ports %}    {{ p.dir }} {{ "wire " if p.dir == "output" else "" }}[{{ p.width_expr or p.width_bits - 1 }}:0] {{ p.name }}{{ ", " if not loop.last }}
{% endfor %}
);
{% for d in clock_domains %}
    // ===== clock domain: {{ d.domain_id }} ({{ d.freq_hz/1e6 | round(3) }} MHz) =====
    wire {{ d.clock_net }};
    wire {{ d.reset_net }};
{% endfor %}
{% for w in wires %}
    wire [{{ w.width_expr }}:0] {{ w.name }};   {# 单源多扇出：一条 wire 挂多负载 #}
{% endfor %}
{% for c in cdc_insts %}
    // CDC {{ c.id }}: {{ c.from_domain }} -> {{ c.to_domain }} ({{ c.kind }})
    async_fifo #(.WIDTH({{ c.width }}), .DEPTH({{ c.depth }})) u_cdc_{{ c.id }} (
        .wr_clk({{ c.wr_clk }}), .wr_rst({{ c.wr_rst }}), .wr_en({{ c.wr_en }}),
        .din({{ c.din }}), .full({{ c.full }}), .almost_full({{ c.almost_full_net }}),
        .rd_clk({{ c.rd_clk }}), .rd_rst({{ c.rd_rst }}), .rd_en({{ c.rd_en }}),
        .dout({{ c.dout }}), .empty({{ c.empty }})
    );
{% endfor %}
{% for m in insts %}
    {{ m.module }} #(
{% for p in m.param_bindings %}        .{{ p.name }}({{ p.expr }}){{ "," if not loop.last }}
{% endfor %}
    ) u_{{ m.inst }} (
{% for p in m.port_bindings %}        .{{ p.port }}({{ p.net }}){{ "," if not loop.last }}
{% endfor %}
    );
    // rvgen:user-begin inst.{{ m.inst }}
    // rvgen:user-end inst.{{ m.inst }}
{% endfor %}
endmodule
```

## 附录 E：`rvopen` 三平台骨架（需补齐）

```python
# py/rvgen/rvopen.py —— 骨架，需按第 6.1 节签名与第 11 章 R09 补齐
import os, platform, subprocess, webbrowser
from pathlib import Path
from urllib.parse import quote

def url_for(loc, repo_root: Path) -> str:
    rel = Path(loc.file).resolve().relative_to(repo_root.resolve())
    return f"rv://open?path={quote(str(rel))}&line={loc.line or 1}&end={loc.end_line or loc.line or 1}"

def open_loc(loc, repo_root: Path) -> bool:
    url = url_for(loc, repo_root)
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            subprocess.run(["open", url], check=True)                 # macOS：LaunchServices
        elif sysname == "Windows":
            os.startfile(url)                                          # Windows：HKCU 注册的 URL Protocol
        else:
            subprocess.run(["xdg-open", url], check=True)              # Linux：.desktop + xdg-mime
        return True
    except Exception:
        webbrowser.open(url)                                           # 兜底，通常失败
        return False   # 调用方据 False 打印 I04 + 可复制的 `code -g file:line` 命令
```

## 附录 F：SSE 端点与前端消费骨架（需补齐）

```python
# py/rvgen/server.py 节选 —— 骨架
import asyncio, json, time
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()
subscribers: set[asyncio.Queue] = set()
_last_event_id = 0

async def publish(event: str, data: dict) -> None:
    global _last_event_id
    _last_event_id += 1
    for q in list(subscribers):
        await q.put((_last_event_id, event, data))

@app.get("/api/events")
async def events(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    subscribers.add(q)
    async def gen():
        try:
            since = int(request.headers.get("Last-Event-ID") or 0)
            if since < _last_event_id:
                yield ": resync\n\n"          # 断线补发由调用方按需实现
            while True:
                if await request.is_disconnected():
                    break
                try:
                    eid, ev, data = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"id: {eid}\nevent: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"  # 防代理缓冲（第 11 章 R13）
        finally:
            subscribers.discard(q)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
```

```ts
// web/src/api/events.ts —— 骨架，需按第 7.2 节事件表补齐
const es = new EventSource("/api/events");       // 浏览器自动重连，带 Last-Event-ID
es.addEventListener("yaml_changed", (e) => store.setStale(JSON.parse(e.data)));   // 只置徽标
es.addEventListener("git_state",   (e) => store.setGit(JSON.parse(e.data)));
es.addEventListener("check_result", (e) => store.setCheck(JSON.parse(e.data)));
es.onerror = () => store.setConn("reconnecting");   // 不自动拉取 graph
```

## 附录 G：pre-commit / post-checkout hook 骨架

```sh
#!/usr/bin/env sh
# scripts/hooks/post-checkout —— 骨架，需按第 7.3 节补齐
set -eu
prev="${1:-}"; cur="${2:-}"; flag="${3:-}"
[ "$flag" = "1" ] || exit 0                 # 只关心分支切换，不关心文件检出
[ "$prev" != "$cur" ] || exit 0
repo="$(git rev-parse --show-toplevel)"
if command -v rvgen >/dev/null 2>&1; then
  rvgen check --quiet || {
    echo "rvgen: 切换后 node_graph.json 与 rvgen.yaml 不一致" >&2
    echo "       运行：rvgen sync && git commit -am 'rvgen: resync after checkout'" >&2
    exit 1
  }
fi
: > "$repo/.rvgen/.git-event"               # 供 server 拾取并推 git_state
```

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

[6] https://www.peopleapp.com/rmharticle/30009818341
> "Cytoscape软件拥有大量的分析插件，是一款非常强大的网络图可视化与分析工具。"（通用背景材料，未用于 tracer 格式结论）

[7] https://news.qq.com/rain/a/20260605A058QI00
> "某些编辑器（如 VS Code）保存文件时会先创建临时文件再覆盖，这可能导致一次保存触发两次 on_modified。建议在代码中加入时间戳判断，过滤掉连续多次的改动。"

[8] https://www.163.com/dy/article/I1VHPNTK0511D3QS.html
> "大多数开发人员讨厌做可以自动化的事情……pre-commit 步骤：在代码进入版本控制系统之前就检测到问题。"

[9] https://www.163.com/dy/article/HJFJRFRR0553SRCA.html
> "在 GitGuardian，我们使用 pre-commit，一个用 Python 编写的多语言钩子包管理器……您会发现用其他语言（例如 JavaScript）编写的不错的替代方案，例如 husky。"

[10] https://www.sohu.com/a/432332970_121118799
> "Husky 可以帮助我们简单直接地实现 git hooks……在 pre-commit 阶段运行 lint，在 pre-push 阶段运行 test。"

[11] https://finance.sina.com.cn/roll/2026-11-01/doc-inixhhcs3325281.shtml
> "一段能跑的代码，和一个能进仓库、能被接手、能被追溯的工程产物，中间隔着依赖管理、架构约束、验收标准和责任归属……规范驱动开发正在变成一条被验证过的路径：把接口定义、架构边界、验收标准先锁定。"

[12] https://news.qq.com/rain/a/20260930A04P0H00
> "代码过于密集难以阅读，测试定义行为并成为文档……应对的原则是让测试定义行为：当你写出的代码过于 dense 而难以阅读时，理解其行为的唯一方式是通过大量测试用例。"

- [13] **FuseSoC 官方文档**（fusesoc.readthedocs.io）：core 文件描述 RTL 文件、生成文件、接口依赖、testbench、参数与 target；setup 阶段产出 dependency tree 并写入 EDAM，再由 Edalize 交给具体 EDA 工具。
- [14] **Python 插件实践**：`entry_points` 作为"可发现清单"由 `importlib.metadata.entry_points(group=...)` 枚举，宿主用 `abc` 抽象类规定 run/configure/lifecycle 契约与异常约定，避免反射扫描的不可控。
- [15] **BusWrap**（efabless）：YAML/JSON 描述 IP（info / parameters / ports / 外部接口）→ APB / AHB-Lite / Wishbone 包装 RTL + testbench + C 头 + Markdown 文档；`v2yaml.py` 可从 `.v` 反生成 YAML 模板。

> **未核实项汇总（本环境限制，P0/P1 必须补齐）**：cv32e40p `tracer.rst` 与 cva6 `trace_core_*.log` 的真实列格式与示例行；React Flow v11→v12 破坏性变更清单与 `onlyRenderVisibleElements` 的量化收益；React Flow 核心库与 Pro 的授权边界；`@xyflow/react` 在非 React 环境（Preact/微前端）的可行性；elkjs/dagre/jointJS/Cytoscape.js 的精确包体积与许可证全文；`react-cytoscapejs` 维护状态；FuseSoC `.core` 的当前 schema 字段全集（P2 前需按本机安装版本 `fusesoc file --parse` 实测校准）；IP-XACT 与核心模型的字段映射是否需 1:1（初版只做命名对齐，不做转换器）。以上均已在正文对应位置显式标注，不得据此直接写实现代码。cv32e40p `tracer.rst` 与 cva6 `trace_core_*.log` 的真实列格式与示例行；React Flow v11→v12 破坏性变更清单与 `onlyRenderVisibleElements` 的量化收益；React Flow 核心库与 Pro 的授权边界；`@xyflow/react` 在非 React 环境（Preact/微前端）的可行性；elkjs/dagre/jointJS/Cytoscape.js 的精确包体积与许可证全文；`react-cytoscapejs` 维护状态。所有未核实项均已在本报告中显式标注，不得据此直接写实现代码。
