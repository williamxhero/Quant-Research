# QuantResearch 文档目录

`docs/` 按文档用途归档。根目录只保留本索引；新增或生成文件时，先确定用途再写入对应子目录。

## 分类规则

| 目录 | 存放内容 | 当前示例 |
| --- | --- | --- |
| `agents/` | Agent 工作规则及按需加载的项目说明 | issue tracker、triage labels、domain docs |
| `architecture/` | 已采用或当前有效的系统边界、目录及依赖关系 | `目录结构.md` |
| `contracts/` | 对外或跨模块必须遵守的数据、接口、健康度规则 | 股票行情资格合同、capability 健康规则 |
| `designs/` | 已进入设计阶段的具体能力或模块方案 | ETF 日线接入设计 |
| `plans/` | 有明确范围、状态、Todo 或验收门的实施计划与执行清单 | MarketHub 优化计划、Strategy Reporting 开发计划 |
| `research/` | Provider、产品、技术路线的调查材料和外部参考资料 | 中国期货 Provider 调研、商业平台架构调研 |
| `reports/` | 已发生工作的复盘、审计、验收和性能报告 | capability 审计、API 性能验收、交易复盘 |
| `future-ideas/` | 尚未立项、未承诺实施的个人设想和远期方向 | 两级框架、通用 Strategy Package、实时订阅缓存 |
| `evidence/` | 支撑报告或计划的机器输出、基准原始数据、探针及阶段证据 | JSON benchmark、阶段 gate 报告、复验脚本 |
| `prompts/` | 可复用任务提示词 | Apex 前复权历史修复提示词 |

`reports/` 可继续按报告主题细分；当前使用 `audits/`、`performance/`、`trading/`。同一任务的一组原始证据应留在 `evidence/`，文件名保留任务、阶段和日期，避免散落在 `docs/` 根目录。

## 新文件归档流程

1. 判断文件是事实合同、当前设计、执行计划、研究材料、结果报告、原始证据，还是未来想法。
2. 写入上表中唯一匹配的目录；不要因为文件“暂时不好判断”而放在根目录。
3. 未来想法只有在正式立项并形成明确范围、状态和 Todo 后，才迁入 `designs/` 或 `plans/`。
4. 移动 Markdown 后检查并修复相对链接；引用原始证据时使用相对于当前文件的新路径。
5. 新增稳定类别时同步更新本索引；优先复用现有类别，避免为单个文件创建新类别。

## 当前未来想法

- `future-ideas/两级框架.md`：快速候选验证与正式研究验证的两级模式。
- `future-ideas/完美的结构.md`：Strategy Package 与能力驱动 Quant Runtime 的远期结构。
- `future-ideas/实时数据订阅缓存机制.md`：QuoteMux 独立实时服务设想。

这些文件用于保留方向和思考，不代表当前架构合同、排期或实施承诺。
