# 测试指南

> 原则：测试只验证契约，不为实现细节背书；规则码、退出码、生成物字节、图文件字段都是契约。
> 当前基线：Python **234 passed / 1 skipped**（性能校准默认跳过）；前端 unit 37 项，e2e 6 个 spec。

## 1. 环境

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd web; npm ci; cd ..
```

## 2. Python 测试

### 2.1 全量

```powershell
.venv\Scripts\python.exe -m pytest -q
```

- `tests/unit/`：loader/model/graph/emitter/diag/plugins/hooks/server/gitw/rvopen 等。
- `tests/checker/`：`check` 的 schema lint 与内部路径。
- `tests/property/`：Hypothesis 随机合法 YAML 的不变量。
- `tests/golden/`：`node_graph.json` 黄金文件与 `graph --write` 字节幂等。
- `tests/migration/`：schema 迁移链、fixture、dry-run。
- `tests/perf/`：默认跳过，`SLC_PERF=1` 才跑。

### 2.2 按规则码定位

```powershell
.venv\Scripts\python.exe -m pytest -q tests/unit/test_graph.py -k E03
.venv\Scripts\python.exe -m pytest -q tests/unit/test_loader.py -k E09
.venv\Scripts\python.exe -m pytest -q tests/unit/test_emitter.py -k "E10 or E15 or I04"
.venv\Scripts\python.exe -m pytest -q tests/unit/test_trace_E11.py
```

### 2.3 覆盖率门禁（CI 同款）

```powershell
.venv\Scripts\python.exe -m pytest -q tests/unit tests/checker tests/property tests/golden `
  --cov=slc.loader --cov=slc.model --cov=slc.graph --cov=slc.digest --cov=slc.emitter `
  --cov-report=term-missing --cov-fail-under=90

.venv\Scripts\python.exe -m pytest -q tests/checker tests/unit/test_digest.py `
  --cov=slc.checker --cov=slc.digest `
  --cov-report=term-missing --cov-fail-under=95
```

### 2.4 分层契约

```powershell
.venv\Scripts\lint-imports.exe
```

必须输出 `Contracts: 2 kept, 0 broken`。新增核心→infra 依赖会直接失败。

### 2.5 黄金文件纪律

```powershell
.venv\Scripts\python.exe -m pytest tests/golden --update-golden
```

- **先人工 diff**。只允许因显式契约变更或修复规则码而更新。
- 提交信息写明原因与对应规则码（例如 `fix(graph): E03 环路径排序稳定`）。
- 不允许为了“让测试变绿”而改黄金文件。

### 2.6 性能校准

```powershell
$env:SLC_PERF="1"; .venv\Scripts\python.exe -m pytest tests/perf -q -s; Remove-Item Env:\SLC_PERF
```

阈值：100 万行 TSV 归一化 < 25 s。实测数据见 [PERF.md](PERF.md)。

### 2.7 变异测试

```powershell
pip install mutmut
mutmut run
mutmut export-cicd-stats
python scripts/mutation_score.py --min 80
```

- `[tool.mutmut]` 只变异 `py/slc`，测试选择 `tests/unit`，跳过 `__init__.py`。
- CI 由 `.github/workflows/nightly.yml` 每天 UTC 18:00 跑，分数 <80% 退出 1。
- **Windows 不可用**：mutmut 依赖 `fork`，Windows 上无法运行；本机只验证 `mutation_score.py` 的纯函数与门槛（`tests/unit/test_mutation_score.py`），真实变异在 Linux nightly 执行。

## 3. 前端测试

```powershell
cd web
npm run typecheck
npm run test:unit
npm run build
npm run test:e2e
```

- `test:unit`：Vitest + jsdom，覆盖 `layout`、`events`、`graph`、`radial`、`registry`、`EChart` 卸载、详情抽屉。
- `test:e2e`：Playwright Chromium，`load-json`、`drag-node`、`views`、`offline`、`reload-keeps-layout`；`perf-500` 默认跳过。
- 性能 e2e：`$env:PERF="1"; npx playwright test e2e/perf-500.spec.ts; Remove-Item Env:\PERF`。
- 快照：`CI=true` 时 Vitest 不自动写新快照；确需更新用 `npx vitest run -u` 并人工检查 diff。

## 4. CLI 冒烟（提交前）

```powershell
cd examples\uart
..\..\.venv\Scripts\slc.exe graph --write
..\..\.venv\Scripts\slc.exe sync
..\..\.venv\Scripts\slc.exe sync --check
..\..\.venv\Scripts\slc.exe check --strict
```

四条都应退出 0；`git diff` 只允许出现本次预期的生成物变化。

## 5. 退出码断言

新增测试必须显式断言退出码，而不是只看输出：

| 场景 | 期望 |
|---|---|
| 全绿 | 0 |
| 任一 `E` 或 CLI 用法错误 | 1 |
| 仅 `W` 且 `--strict` | 2 |
| 缺文件 / 端口占用 / 写失败 | 3 |

`DiagnosticSink.exit_code(strict=...)` 是唯一实现，不要在各命令里手写映射。

## 6. 提交前清单

1. `pytest -q` 全绿（性能测试可跳）。
2. `lint-imports` 2 kept。
3. 前端 `typecheck` / `test:unit` / `build` / `test:e2e` 全绿。
4. `examples/uart` 四条命令退出 0。
5. 黄金文件、快照、`node_graph.json` 的 diff 已人工确认。
6. 新规则码/新行为已写入 `CHANGELOG.md` 与 `docs/decisions-log.md`。
