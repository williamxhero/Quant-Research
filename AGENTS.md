# 项目写入范围

- `QuantResearch` 是一个项目；工作区根目录及其中的 `MarketHub`、`QuoteMux`、`QuoteMux_Packages` 均属于本项目的正常可写范围，可为完成用户请求直接修改。
- 项目外仓库保持只读，除非用户明确将其纳入范围。

# 原则：

- 外部 provider 能直出的，放对应 provider package。 

- 单 provider 原始数据可推导的，放对应 provider package，比如 Tushare 的资金流字段汇总。

- 多 provider/本地缓存计算出来的，不应在 QuoteMux core 暗算；如果确实要保留，应建明确的 source package，例如 derived_core，并在 capability 上标明它是派生 provider。

## 文档归档

- 在 `docs/` 新建、生成或迁入文件前，先阅读并遵守 `docs/README.md` 的分类规则；`docs/` 根目录只放该索引。
- 尚未立项、未承诺实施的个人设想统一放入 `docs/future-ideas/`，不得混入当前架构、设计或实施计划。

## Git 提交约束

以下规则适用于 QuantResearch 根仓库及工作区内所有项目自有 Git 仓库；更具体的仓库规则可以继续收紧：

- 本地专用目录为 `runtime/`、`tests/`、`tools/`、`artifacts/`、`dist/`、`docs/`。默认将其中内容保留在本地并排除出 Git 索引。
- 本地专用文件只有两类提交例外：用户明确要求提交；或能够证明该具体文件是全新环境安装、编译或发布不可缺少的输入。便利脚本、诊断材料、历史证据和“已经被跟踪”均不构成例外。
- 采用例外前必须说明具体必要性，并使用精确路径单独暂存；不得因此暂存同目录的其他文件。
- `vendor/`、`ops/`、`AGENTS.md`、`services/`、`scripts/`、`.runtime/` 同样默认不提交，只有用户明确要求或公开环境的安装、编译、发布确实必需时才可按精确路径暂存。
- 提交时使用逐个明确路径；不使用 `git add .`、`git add -A` 或 `git commit -a`。
- 提交前必须运行 `git diff --cached --name-only`，逐项核对暂存清单。误暂存的本地专用文件先取消暂存。发现这类文件已被跟踪时，使用 `git rm --cached` 从索引移除并保留本地文件。
- 新 thread 必须主动执行这些规则，无需用户重复提醒。

## Agent skills

### Issue tracker

Issues for the workspace shell are tracked in GitHub Issues. When the local file exists, see `docs/agents/issue-tracker.md`.

### Triage labels

Use the default five canonical triage labels. When the local file exists, see `docs/agents/triage-labels.md`.

### Domain docs

This workspace uses a single-context domain-doc layout. When the local file exists, see `docs/agents/domain.md`.

