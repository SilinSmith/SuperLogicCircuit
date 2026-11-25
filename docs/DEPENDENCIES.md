# 依赖与工具链清单（P0 实测）

> 实测日期：2026-11-24；实测机器：Windows，Python 3.11.6，Node v24.22.1，npm 11.19.1。
> Python 体积为 `.venv` 中该发行版 `dist-info/RECORD` 列出的文件字节数（含包内数据，不含其传递依赖）。
> 前端体积取 `npm view <pkg>@<version> dist.unpackedSize`（registry 报告的安装后字节数），不是压缩包体积。
> 本表不含“未核实”条目；trace tracer 的真实列格式按文档留给 P1 校准，不属于依赖表。

## Python 直接依赖

| 包 | 锁定版本 | 许可证 | 实测安装体积 | 实测依据 |
|---|---|---|---|---|
| pyyaml | 6.0.4 | MIT | 748.1 KiB | `pip show pyyaml`；RECORD 文件求和 |
| jsonschema | 4.26.0 | MIT | 1092.3 KiB | `pip show jsonschema`；RECORD 文件求和 |
| jinja2 | 3.1.6 | BSD-3-Clause（Classifier） | 1186.5 KiB | `pip show jinja2`；RECORD 文件求和 |
| watchdog | 7.1.1 | Apache-2.0 | 922.0 KiB | `pip show watchdog`；RECORD 文件求和 |
| fastapi | 0.165.0 | MIT | 1780.8 KiB | `pip show fastapi`；RECORD 文件求和 |
| uvicorn[standard] | 0.54.0 | BSD-3-Clause | 794.5 KiB | `pip show uvicorn`；RECORD 文件求和 |

## Python 开发依赖（`[dev]`）

| 包 | 锁定版本 | 许可证 | 实测安装体积 | 实测依据 |
|---|---|---|---|---|
| pytest | 9.2.0 | MIT | 3470.6 KiB | `pip show pytest`；RECORD 文件求和 |
| pytest-cov | 7.1.0 | MIT | 117.9 KiB | `pip show pytest-cov`；RECORD 文件求和 |
| hypothesis | 6.170.17 | MPL-2.0 | 4407.8 KiB | `pip show hypothesis`；RECORD 文件求和 |
| pytest-benchmark | 5.3.1 | BSD-2-Clause | 553.6 KiB | `pip show pytest-benchmark`；RECORD 文件求和 |
| mutmut | 3.8.1 | BSD-3-Clause | 694.6 KiB | `pip show mutmut`；RECORD 文件求和 |
| import-linter | 2.17 | BSD-2-Clause | 2046.1 KiB | `pip show import-linter`；RECORD 文件求和 |
| pip-tools | 7.7.0 | BSD-3-Clause | 680.5 KiB | `pip show pip-tools`；RECORD 文件求和 |
| pre-commit | 4.7.0 | MIT | 841.5 KiB | `pip show pre-commit`；RECORD 文件求和 |

完整传递依赖锁在根目录 `requirements.lock`（由 `pip-compile --extra=dev pyproject.toml` 生成）。

## 前端依赖（P3 实际安装面，`web/package-lock.json` 锁定）

> 体积为 `web/node_modules/<pkg>` 目录文件字节求和（P3 实测，2026-11-25）；含包内数据，不含其传递依赖。

| 包 | 锁定版本 | 许可证 | 实测安装体积 | 用途 |
|---|---|---|---|---|
| react | 19.3.1 | MIT | 174.5 KiB | UI 运行时 |
| react-dom | 19.3.1 | MIT | 7878.5 KiB | UI 渲染 |
| @xyflow/react | 12.12.1 | MIT | 1187.9 KiB | 节点编辑器（画布/拖拽/小地图） |
| dagre | 0.8.5 | MIT | 824.8 KiB | 数据流视图分层布局（同步） |
| echarts | 5.6.0 | Apache-2.0 | 38384.0 KiB（另 zrender 5.6.1） | 统计视图柱状图（`echarts/core` 按需注册） |
| zustand | 4.5.7 | MIT | 319.4 KiB | `@xyflow/react` 的传递依赖，非直接依赖 |
| vite | 7.3.8 | MIT | 2191.9 KiB | dev server / 构建 |
| typescript | 5.9.3 | Apache-2.0 | 23071.4 KiB | 类型检查 |
| vitest | 3.2.7 | MIT | 1349.0 KiB | 单元测试与快照 |
| jsdom | 26.1.0 | MIT | 3105.2 KiB | 单测 DOM 环境 |
| @testing-library/react | 16.3.3 | MIT | 331.6 KiB | 组件测试 |
| @testing-library/jest-dom | 6.9.1 | MIT | 562.0 KiB | DOM 断言 |
| @vitejs/plugin-react | 5.2.0 | MIT | 45.2 KiB | React 插件 |
| @playwright/test | 1.65.1 | Apache-2.0 | 27.9 KiB | e2e |
| playwright-core | 1.65.1 | Apache-2.0 | 13644.0 KiB | `@playwright/test` 的传递依赖 |
| esbuild | 0.28.2 | MIT | 143.9 KiB | Vite 的传递依赖 |

> 版本选择：方案第 15 章锁定 React 19 / Vite 7 / `@xyflow/react` 12 / TypeScript 5 / Vitest 2 / Playwright 1.4x。
> P3 实际取各主版本当前可用的最高次版本；Vitest 3.2.7、Playwright 1.65.1、`dagre` 0.8.5（React Flow 官方示例同款，`@types/dagre` 提供类型）与表格原计划的 Vitest 2 / Playwright 1.49 / `@dagrejs/dagre` 有差异，记录见 `docs/decisions-log.md` D15。
> `elkjs` 为 EPL-2.0 / GPL-3.0 双许可，P3 未安装；P4 若引入时钟树精细布局再评估。

## 工具链与前置条件

| 工具 | 实测状态 | 证据 | 缺失时的处理 |
|---|---|---|---|
| Python 3.11.6 | 已装 | `python --version` → `Python 3.11.6` | 必需；否则不满足 `requires-python` |
| Node v24.22.1 | 已装 | `node --version` | P3 起必需 |
| npm 11.19.1 | 已装 | `npm --version` | P3 起必需 |
| Chromium（Playwright） | 已装 | `npx playwright install chromium` | 仅 e2e/性能校准需要 |
| Icarus Verilog 14.0 | 已装 | `iverilog -V` | 必需；`slc doctor` 报缺失 |
| Yosys 0.56 | 已装 | `yosys -V` | 可选；缺失时用 `iverilog -g2005` |
| Verilator | 未装 | `verilator --version` 命令不存在 | 可选；`doctor` 只提示，不自动安装 |
| FuseSoC | 未装 | `fusesoc --version` 命令不存在 | 可选；AC11 用 jsonschema 校验 `.core` 结构 |
| Verible | 未装 | `verible-verilog-lint --version` 命令不存在 | 可选；`doctor` 只提示 |
| Git | 已装 | `git --version` → `2.55.0.windows.3` | 必需；缺失时 `doctor` 退出 3 |

## 离线方案与 P0 状态

- Python：`vendor/wheels/` 存 `pip download -r requirements.lock` 的产物；离线安装命令
  `pip install --no-index --find-links vendor/wheels -r requirements.lock`。
- npm：仓库**不内置** `vendor/npm/*.tgz`。有网时运行 `scripts/npm-prefetch.ps1`（Windows）或 `scripts/npm-prefetch.sh`（Linux/macOS），把 `web/` 依赖预取到本机 npm cache；之后可断网执行 `npm ci --offline`。
  - 验证路径：`npm-prefetch.ps1 -Cache <dir>` 退出 0；临时目录仅含 `package.json`+`package-lock.json` 时 `npm ci --offline --cache <dir>` 退出 0（192 包）。
  - 限制：离线安装依赖“这台机器事先预取过”，不是全新 clone 即可离线；CI 走联网 `npm ci`，见 `.github/workflows/ci.yml` 与 D45。
- P0 的 Python 离线包按当前 Windows / CPython 3.11 平台生成；CI 的 Linux job 若要走离线安装，需要另行提供对应平台的 wheel。
