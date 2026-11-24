# ADR-03 用户代码保护：marker + fingerprint + orphaned

> 状态：已采纳；日期：2026-11-25；适用阶段：P2 起。
> 依据：`rvgen完整方案.md` 决策三、§6；决策记录 D6–D9。

## 背景

Verilog 缺少稳定 AST 基线，3-way merge 的冲突对用户不可读；重新生成又不能丢用户逻辑。

## 决策

| 机制 | 规则 |
|---|---|
| USER 块 | `// rvgen:user-begin <id>` … `// rvgen:user-end <id>`；块内字节原样保留 |
| 生成区 | 块外整体重写；头部写 `rvgen:fingerprint` |
| 删除块 | 不静默丢弃，落 `.rvgen/orphaned/<ts>/<module>.<id>.v.bak`，stderr 报 `I04`，退出 0 |
| frozen | `status: frozen` 的生成物被改 → `E10`，`sync` 不覆盖；`--force-unfreeze` 显式解除 |
| 契约提示 | `W01` 只写 USER 块外，绝不改块内字节 |
| 生成物落后 | `sync --check` 比较去提示后的文本，落后报 `E15` |

## 理由

marker 是最不容易被 Verilog 语法重构打坏的形式；fingerprint 让“生成物是否被手改”可判定；orphaned 保证删除可恢复。

## 后果

- 用户必须把逻辑写在 marker 内；块外手改会在下次 `sync` 被覆盖（frozen 时改报 E10）。
- `W01` 是一次性提示，`sync --check` 必须忽略提示行，否则会误报落后。
- 块 id 重复/未闭合报 `E06`，并要求人工修复，不猜测。

## 替代方案

- EMF `@generated NOT` 式整文件保留：否决，Verilog 无可挂注解的 AST。
- 3-way merge：否决，冲突不可读且依赖基线。
