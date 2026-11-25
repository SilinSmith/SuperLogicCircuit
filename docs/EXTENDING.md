# 扩展指南

> 核心层零领域知识。任何领域能力都通过 plugin 或显式契约扩展进入，不允许在 `py/slc/` 里写 `is_cpu` 分支。
> 每条流程给出必改文件与验证命令；未列出的文件不要动。

## 1. 新增一种 `kind`

`kind` 是模块的结构角色。核心只内置 `module / bridge / memory / clock_gen`，其余必须由 plugin 注册。

1. 在 plugin 的 `Plugin(kinds=(...))` 里加入新 kind（小写蛇形）。
2. 确认 `schema/slc.schema.json` 的 `modules[].kind` 仍是自由字符串（`$defs/core_kind` 只用于描述，不作为枚举约束）。
3. 如果新 kind 需要额外字段，用 `x-<plugin>-*` 写入 `slc.yaml`，不要改核心 schema 的必填项。
4. 在 plugin 的规则函数里校验这些 `x-*` 字段（如 `x-foo-depth`），使用 `P<PLUGIN>-nn` 规则码。
5. 在前端如需专属外观，扩展 `web/src/flow/nodes/ModuleNode.tsx` 的 `typeLabel` 或新增节点组件；数据仍只读 `node_graph.json`。
6. 补测试：`tests/unit/test_plugins.py`（注册与重名）、`tests/unit/test_model_semantic.py`（未注册 kind → E05）。

验证：`slc check --strict`；`slc graph --write` 后图节点 `type` 仍为 `module_node`。

## 2. 新增一种节点类型

plugin 节点类型必须以 `p_<plugin>:` 开头，否则 plugin 校验失败并按 `W11` 跳过。

1. 选择类型名，如 `p_foo:bar_node`（后缀小写蛇形）。
2. 在 `Plugin(node_types=("p_foo:bar_node",))` 注册。
3. 图节点 `id` 使用 `p_foo:bar_node:<name>`，`type` 使用 `p_foo:bar_node`，符合 `schema/node_graph.schema.json` 的 `plugin_type_pattern` 与 `node_id`。
4. 节点字段放进 `x-foo-*` 或 plugin 自定义字段；核心不解释。
5. 前端：`web/src/views/DataflowView.tsx` 已包含 `p_` 节点；如需专属外观，在 `ModuleNode.typeLabel` 之外新增组件并在 `web/src/flow/FlowCanvas.tsx` 的 `nodeTypes` 注册。
6. 补测试：`tests/unit/test_plugins.py`（前缀错误 → W11）、`web/src/plugins/registry.test.ts`（视图激活）。

## 3. 新增一种视图

1. 新建 `web/src/plugins/<plugin>/<View>.tsx`，props 只用 `{ graph }`。
2. 在 `web/src/plugins/registry.ts` 的 `PLUGIN_VIEWS` 追加 `{ id, title, plugin, applies, Component }`。
3. `applies` 必须只依赖图数据（`p_<plugin>:` 节点或 `x-<plugin>-*` 字段），禁止全局开关；通用图不得出现空视图。
4. 视图内的布局/坐标只写 `layout.json` 或 localStorage，不写图文件。
5. 在 `web/src/App.tsx` 的视图切换里确认新 tab 与核心三视图并列，切换不残留画布。
6. 补测试：`web/src/plugins/registry.test.ts`（有/无 plugin 数据）、`web/e2e/views.spec.ts`（切换与无残留）。

验证：`cd web && npm run typecheck && npm run test:unit && npm run test:e2e`。

## 4. 新增一种 CDC 类型

CDC 类型是**核心契约**（`cdc[].kind` 枚举），不是 plugin 扩展；新增它意味着 schema 变更。

1. 在 `schema/slc.schema.json` 的 `cdc.kind` 枚举与 `oneOf` 分支加入新值及必填字段。
2. 在 `py/slc/emitter.py` 的 `CDC_MODULES` 映射到生成模块名，并实现对应模板（`templates/cdc_bridge.v.j2` 或新模板）。
3. 在 `py/slc/emitter.py` 的 `render_cdc` / `plan_files` 里按 kind 选择模板与参数。
4. 若新类型需要额外字段（如 `almost_full`），在 schema 与 `model.py` 语义校验中同时加约束。
5. 更新 `tests/unit/test_emitter.py`（生成物、幂等、`sync --check`）与 `tests/fixtures/schema/valid/slc.yaml`。
6. 更新 [YAML_REFERENCE.md](YAML_REFERENCE.md) 的 `cdc[]` 表与 `CHANGELOG.md` 的 schema 版本说明。

> 枚举新增值按 minor 处理：加载旧文件不受影响；新文件在旧 CLI 上会被 schema 拒绝。删除/重命名枚举值属 major，必须走 `slc migrate`。

## 5. 新增一组 plugin 规则码

1. 新建 `plugins/<plugin>/rules.py`，函数签名 `def validate(model, config) -> list[Diagnostic]`。
2. 规则码格式 `P<PLUGIN>-<n>`（如 `PCPU-01`），severity 只能是 `E`/`W`/`I`；消息用中文，`Location` 必须带 `file`/`line` 或 `json_path`。
3. 在 `plugins/<plugin>/plugin.py` 的 `Plugin(rules=(validate,))` 注册；核心只在 `slc.yaml` 的 `plugins.<id>.enabled` 为真时执行。
4. 规则异常会被捕获为 `W11` 并跳过，不允许让 plugin 拖垮核心；不要依赖外部状态。
5. 在 `tests/unit/test_plugins.py` 或 plugin 自己的测试里覆盖：合法、非法、抛异常三条路径。
6. 在 `docs/YAML_REFERENCE.md` 诊断表与 `CHANGELOG.md` 记录新规则码。

验证：`slc check --strict`；坏 plugin 场景应只出现 `W11` 且退出码 0。

## 6. 新增一条迁移

1. 在 `py/slc/migrate.py` 的 `STEPS` 追加 `(from, to, fn)`，`fn` 必须是纯函数（输入/输出都是 dict）。
2. 每步结束后必须用目标版本 schema 校验；失败抛 `MigrationError`，不得写半成品。
3. 在 `tests/migration/fixtures/` 放旧版本样例，补 `tests/migration/test_migrate.py`。
4. `migrate_file` 的快照目录 `.slc/snapshots/<UTC>/slc.yaml` 不允许删除或覆盖。
5. `--dry-run` 输出 JSON Patch，不落盘；写模式先快照再原子替换。
6. 更新 `CHANGELOG.md` 与 `YAML_REFERENCE.md` 的版本表。

## 7. 不该扩展的地方

- 不要在核心增加 CPU/总线/协议概念；判定问句：*“一个 UART 或 AXI 交叉开关项目需要它吗？”*
- 不要让前端直接读 YAML；所有展示只经 `node_graph.json` 与 `trace_summary.json`。
- 不要把布局写进 `slc.yaml` 或 `node_graph.json`。
- 不要让 `serve` / watcher / hook 自动改写受控资产。
