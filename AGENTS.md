# 项目写入范围

- `QuantResearch` 是一个项目；工作区根目录及其中的 `MarketHub`、`QuoteMux`、`QuoteMux_Packages` 均属于本项目的正常可写范围，可为完成用户请求直接修改。
- 项目外仓库保持只读，除非用户明确将其纳入范围。

# 原则：

- 外部 provider 能直出的，放对应 provider package。 

- 单 provider 原始数据可推导的，放对应 provider package，比如 Tushare 的资金流字段汇总。

- 多 provider/本地缓存计算出来的，不应在 QuoteMux core 暗算；如果确实要保留，应建明确的 source package，例如 derived_core，并在 capability 上标明它是派生 provider。

## Git 提交约束

本目录下的 `MarketHub`、`QuoteMux`、`QuoteMux_Packages` 三个 Git 仓库都遵守以下规则：

- 默认不得暂存或提交仓库根目录下这些路径中的任何文件：`vendor/`、`ops/`、`docs/`、`AGENTS.md`、`tests/`、`services/`、`runtime/`、`scripts/`、`.runtime/`。
- 提交时不得使用可能把这些目录一起暂存的 `git add .`、`git add -A`、`git commit -a`；必须逐个明确列出允许提交的文件路径。
- 提交前必须运行 `git diff --cached --name-only` 检查暂存清单。如果上述目录中的文件被误暂存，先取消暂存，再继续提交。
- 只有能够明确证明某个具体文件对公开环境的构建、运行、部署、迁移、验证或使用确有必要时，才允许提交；提交前必须说明必要性，并使用精确路径单独 `git add`，不得因此暂存同目录中的其他文件。
- 文件已经被 Git 跟踪不构成继续公开提交的理由。新 thread 应主动遵守本约束，无需用户重复提醒。

## Agent skills

### Issue tracker

Issues for the workspace shell are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default five canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This workspace uses a single-context domain-doc layout. See `docs/agents/domain.md`.

