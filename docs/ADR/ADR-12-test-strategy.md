# ADR-12 测试策略与质量门禁

> 状态：已采纳；日期：2026-11-25；适用阶段：P0 起。
> 依据：`rvgen完整方案.md` §8、§9；[TESTING.md](../TESTING.md)。

## 决策

| 层 | 工具 | 门禁 |
|---|---|---|
| 单元 | pytest | 全绿；核心模块覆盖率 ≥90%，checker/digest ≥95% |
| 属性 | Hypothesis | 随机合法 YAML 不崩、幂等、`load → emit → load` 契约不变 |
| 黄金 | pytest `--update-golden` | 人工 diff 后才允许更新 |
| 迁移 | pytest + fixture | 每步 schema 校验；dry-run 不落盘 |
| 分层 | `import-linter` | 2 contracts kept |
| 前端单元 | Vitest + jsdom | 全绿；`CI=true` 不自动写快照 |
| 前端 e2e | Playwright Chromium | load/drag/views/offline/reload 全绿 |
| 性能 | pytest / Playwright | 1M 行 <25 s；500 节点 p95 ≥30 FPS |
| 变异 | mutmut（nightly） | 分数 ≥80% |

## 理由

规则码、退出码、生成物字节、图字段都是契约；只测实现细节会在重构时制造假失败。分层覆盖让“改 loader 不跑前端”也能快速反馈。

## 后果

- 新增规则码必须有对应 `-k` 可定位测试。
- 黄金文件更新必须写原因；不允许为了变绿而更新。
- Windows 无 `fork`，mutmut 只在 Linux nightly 跑；本机只测分数脚本。
- CI 含 Playwright，但仓库未推送，`ubuntu-22.04` 实跑仍是未验证项（AC27）。

## 替代方案

- 只跑端到端：否决，定位成本高、反馈慢。
- 快照全自动更新：否决，契约漂移无人发现。
