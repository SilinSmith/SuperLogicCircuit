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

## 前端依赖（P3 起安装；版本按第 15 章锁定）

| 包 | 锁定版本 | 许可证 | 实测安装体积 | 实测依据 |
|---|---|---|---|---|
| react | 19.3.1 | MIT | 174.5 KiB | `npm view react@19.3.1 license dist.unpackedSize` |
| react-dom | 19.3.1 | MIT | 7878.5 KiB | `npm view react-dom@19.3.1 license dist.unpackedSize` |
| @xyflow/react | 12.12.1 | MIT | 1187.9 KiB | `npm view @xyflow/react@12.12.1 license dist.unpackedSize` |
| vite | 7.3.8 | MIT | 2191.9 KiB | `npm view vite@7.3.8 license dist.unpackedSize` |
| typescript | 5.9.3 | Apache-2.0 | 23071.4 KiB | `npm view typescript@5.9.3 license dist.unpackedSize` |
| zustand | 5.1.0 | MIT | 109.1 KiB | `npm view zustand@5.1.0 license dist.unpackedSize` |
| elkjs | 0.12.1 | EPL-2.0 OR GPL-3.0-or-later | 8037.6 KiB | `npm view elkjs@0.12.1 license dist.unpackedSize` |
| @dagrejs/dagre | 3.1.3 | MIT | 1390.1 KiB | `npm view @dagrejs/dagre@3.1.3 license dist.unpackedSize` |
| echarts | 5.5.1 | Apache-2.0 | 51571.2 KiB | `npm view echarts@5.5.1 license dist.unpackedSize` |
| @tanstack/react-query | 5.108.4 | MIT | 1761.7 KiB | `npm view @tanstack/react-query@5.108.4 license dist.unpackedSize` |
| vitest | 2.1.9 | MIT | 1602.1 KiB | `npm view vitest@2.1.9 license dist.unpackedSize` |
| @testing-library/react | 16.3.3 | MIT | 331.6 KiB | `npm view @testing-library/react@16.3.3 license dist.unpackedSize` |
| @playwright/test | 1.49.1 | Apache-2.0 | 24.8 KiB（另有 playwright-core 7779.9 KiB） | `npm view @playwright/test@1.49.1 license dist.unpackedSize` |
| json-schema-to-typescript | 16.0.0 | MIT | 287.5 KiB | `npm view json-schema-to-typescript@16.0.0 license dist.unpackedSize` |
| eslint | 10.15.0 | MIT | 2889.5 KiB | `npm view eslint@10.15.0 license dist.unpackedSize` |
| prettier | 3.10.1 | MIT | 11174.0 KiB | `npm view prettier@3.10.1 license dist.unpackedSize` |

> 版本选择说明：文档锁定 React 19 / Vite 7 / `@xyflow/react` 12 / TypeScript 5 / Vitest 2 / Testing Library 16 / Playwright 1.4x；表中取各主版本当前可用的最高次版本。Playwright 取 1.49.1（1.4x 线），而非 registry 当前最新的 1.65.1。
> `elkjs` 为 EPL-2.0 / GPL-3.0 双许可；按文档作为布局候选保留，未进入 P0 安装面。

## 工具链与前置条件

| 工具 | 实测状态 | 证据 | 缺失时的处理 |
|---|---|---|---|
| Python 3.11.6 | 已装 | `python --version` → `Python 3.11.6` | 必需；否则不满足 `requires-python` |
| Node v24.22.1 | 已装 | `node --version` | P3 起必需 |
| npm 11.19.1 | 已装 | `npm --version` | P3 起必需 |
| Icarus Verilog 14.0 | 已装 | `iverilog -V` | 必需；`rvgen doctor` 报缺失 |
| Yosys 0.56 | 已装 | `yosys -V` | 可选；缺失时用 `iverilog -g2005` |
| Verilator | 未装 | `verilator --version` 命令不存在 | 可选；`doctor` 只提示，不自动安装 |
| FuseSoC | 未装 | `fusesoc --version` 命令不存在 | 可选；AC11 用 jsonschema 校验 `.core` 结构 |
| Verible | 未装 | `verible-verilog-lint --version` 命令不存在 | 可选；`doctor` 只提示 |
| Git | 已装 | `git --version` → `2.55.0.windows.3` | 必需；缺失时 `doctor` 退出 3 |

## 离线方案与 P0 状态

- Python：`vendor/wheels/` 存 `pip download -r requirements.lock` 的产物；离线安装命令
  `pip install --no-index --find-links vendor/wheels -r requirements.lock`。
- npm：`scripts/npm-offline.sh` 与 `scripts/npm-offline.ps1` 只做 `npm cache add vendor/npm/*.tgz`，不联网。
- 当前仓库没有 `web/package.json`（前端骨架属 P3），因此 `vendor/npm/` 在 P0 为空，脚本会打印说明并以 0 退出；P3 引入 `web/package.json` 后必须补齐 tgz 并让 `npm ci --offline` 通过。
- P0 的 Python 离线包按当前 Windows / CPython 3.11 平台生成；CI 的 Linux job 若要走离线安装，需要另行提供对应平台的 wheel。
