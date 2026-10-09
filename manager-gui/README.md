# Manager GUI owner package

`manager-gui` is the independent QuantResearch workspace owner for the first
Manager GUI slice. It is a local, read-only contract package; it does not
implement Apex Research, Quant Runtime, Strategy Workspace, or Strategy
Reporting domain behavior.

The dedicated [Reader Guide](READER_GUIDE.md) documents Reader modes, truth
states, sample/owner boundaries, known limitations, and the manual accessibility
checklist.

## Package and commands

The package is a standalone Python 3.11+ project. Fixture mode has no production
dependencies; the optional `workspace` extra supports real Workspace reads.
From the QuantResearch repository root, run:

```console
# Focused S1 test suite and full package regression suite
uv run --directory manager-gui pytest -q

# Lint the package (the source tree is intentionally dependency-free)
uv run --directory manager-gui ruff check .

# Build the isolated wheel and source distribution
uv build --directory manager-gui

# Temporary type check (keeps mypy out of production dependencies)
uv run --directory manager-gui --with mypy --with pytest mypy --python-version 3.11 src

# Full S6 verification helpers
uv run --directory manager-gui pytest -q
uv run --directory manager-gui ruff check .
python -m compileall -q manager-gui/src
uv run --directory manager-gui python -m manager_gui --fixture complete --pretty

# Start the integrated, fixture-backed WebUI shell
uv run --directory manager-gui manager-gui-web --fixture complete --port 8765
# Equivalent module invocation
uv run --directory manager-gui python -m manager_gui.web --fixture complete --port 8765

# Offline Dossier v2 audit (readback files are named by exact SHA-256 ID)
uv run --directory manager-gui manager-gui-dossier rebuild \
  --model path/to/dossier-model.json --readback-dir path/to/public-readback \
  --baseline-ref <root-id> --current-root-id <root-id> --old-publication-id <old-id>
```

`manager-gui-dossier inspect`, `verify`, and `rebuild` only consume the explicit
canonical model and operator-exported public readback bytes. They do not discover
records, access SQLite/private storage, call Runtime or Holdout APIs, or write a
publication. Every command reports `published`, `runtime_submission_calls`, exact
old-record/publication byte identity, and HTML boundary/accessibility checks.

## 真实 Workspace 模式：受支持的一条命令

前置条件：Windows 上已安装 `uv` 和 Python 3.11+（验收使用 Python 3.12）；
从 QuantResearch 检出目录执行，目录中有 `./manager-gui` 和
`./strategy-workspace` 源码克隆。StrategyWorkspace 分发版本至少为 `0.2.0`，
实际 `WorkspaceClient` API 必须显式接受 `read_only` 关键字，并提供可调用的
`list_runs`、`list_records`、`get_registered_package`、`query_lineage` 和
`read_artifact`。同版本旧 wheel 不一定具备这些 API；不要用模块 `__version__`
代替分发元数据或实际 API 检查。已安装的 `site-packages` 不是源码安装路径。

`workspace` 可选依赖组声明 `strategy-workspace>=0.2.0` 和 Windows 时区数据库
`tzdata`；`jsonschema` 和 `referencing` 由 StrategyWorkspace 的生产依赖传递安装。
首次安装需要能访问包索引和构建依赖；无需全局安装 owner 包、手工补依赖或设置
`PYTHONPATH`。安装目录和缓存必须位于研究工作区之外。

工作区须已由 owner 公共写接口准备、完成迁移并冻结，当前不含
`-wal`、`-shm` 或 `-journal` 边车。此模式只支持 StrategyWorkspace 已审计的
Windows 零写入只读 API；其他平台或不满足只读安全条件的工作区将安全拒绝，
不是通过初始化、迁移、建锁、checkpoint 或删除边车来补救。
不要让安装命令操作真实研究工作区，也不要为演示改变其数据或边车。

在 PowerShell 中把示例工作区路径替换为已有冻结工作区的绝对路径，并选择空闲端口：

```powershell
uv run --no-project --isolated --refresh-package quantresearch-manager-gui --refresh-package strategy-workspace --with "./manager-gui[workspace]" --with "./strategy-workspace" python -I -m manager_gui.web --provider workspace --workspace-root 'C:/research/frozen-workspace' --port 8765
```

打开 `http://127.0.0.1:8765/?view=atlas`，或切换至其他视图。
`--provider workspace` 必须有 `--workspace-root`，不得同时指定 `--fixture`；
缺依赖或 API 不兼容会在打开存储客户端之前显示中文原因及可复制命令，退出而非
回退到样例数据。API 不兼容诊断记录分发版本、实际导入文件及不符的公开 API。
路径使用 PowerShell 单引号；若路径含单引号，写为两个单引号，避免 shell 解释。

命令中的两个 `--refresh-package` 都是必需的：本地源码内容变化而版本号未变化时，
普通 `uv run --with` 可能命中旧 wheel。每次启动均刷新 GUI 和 StrategyWorkspace
的同版本本地构建；`--isolated` 使用新的隔离运行环境，`--no-project` 不同步或
重建当前项目的 venv，`python -I` 忽略继承的 `PYTHONPATH` 和用户 site-packages。
无需删除用户缓存。这里支持的是显式本地源码安装，不是猜测包索引上同名包的内容。

**不要在运行实例的 venv 目录里跑会重建 venv 的 uv 命令**。
例如 `uv run --python` 切换解释器可能清空或替换运行实例的 `site-packages`。
保持源码检出目录、构建／依赖缓存、隔离运行环境和冻结工作区分离；不要激活或
向正在运行的 venv 塞依赖。更新时在源码检出目录更新两个克隆，再执行上述完整命令，
先用另一空闲端口验证新实例及实际记录内容，然后按需停止旧实例；不要修改旧 venv。
验收覆盖空缓存／新隔离环境、同版本旧 wheel 暖缓存、缺依赖和不兼容 API，
并核对冻结工作区目录清单、内容哈希、大小和修改时间零变化，以及另一运行中 venv
未改变。只读 HTTP `200` 本身不是数据或零写入证明。

## 语言与 `lang` 查询参数

WebUI 只从 URL 的 `lang` 查询参数读取界面语言，不使用 cookie 或
`Accept-Language`。默认语言为 `zh-CN`；`zh`、`zh_CN`、`zh-Hans`、`en-US` 和
`en-GB` 会规范化为 `zh-CN` 或 `en`。未指定、空值和非法值回退到应用默认语言，
并且不会继续出现在生成的内部链接或 GET 表单中。显式有效的语言会以规范值保留在
内部链接、分页、筛选表单和语言切换器中；切换器使用普通链接，并保留原 URL 的全部
查询状态（包括重复参数与空值）。可用 `manager-gui-web --lang {zh-CN,en}` 设置
应用默认语言，URL 中显式的有效 `lang` 仍优先于该默认值。

`/api/read-model` 的 ManagerReadModel v0 响应不包含语言状态，在不同 `lang` 或未
指定语言时逐字节相同。`/api/export` 以及页面内嵌的导出载荷会从 `query` 和
`query_params` 中剥离 `lang`，因此导出内容也与界面语言无关。

## 全站多语言契约与最终 Exit Gate

`ManagerGUIApp.render()` 为每个请求创建一个 `Translator`，并以关键字参数传给全部
17 个页面入口；共用状态、交互、分页、导出和图谱/表格 helper 也只接受该请求语言。
页面入口可以保留默认值以兼容独立调用，但集成 shell 必须显式传递请求语言，不能在页面
内重新推导语言。Search 和 Portal 也使用同一请求 `Translator`，不会改变读模型或 API。

共用目录由 `web/i18n/catalog/` 按命名空间拥有：`shell.py`、`nav.py`、`status.py`、
`interaction.py`、`client.py` 和 `pagination.py` 只能通过 `CatalogRegistry` 追加注册，
不得覆盖已有键。L3、L4、L5 页面目录分别由各自的 `l3_*`、`l4_*` 和 `l5_search.py` /
`l5_portal.py` 拥有，并且仅在 `catalog/__init__.py` 中注册一次。注册表拒绝重复键；
所有页面 helper 使用 shell 传入的请求 `Translator`。`models.py`、共享 shell、
`/api/read-model` 和 `/api/export` 保持语言中立。

最终 `MIGRATED_ROUTES` 精确包含全部 17 条路由：`atlas`、`stories`、`strategies`、
`strategy-conditions`、`strategy-genome-comparison`、`memory`、`memory-failures`、
`failure-patterns`、`evidence`、`lineage`、`evidence-object-comparison`、
`derived-failure-grouping`、`methodology`、`history`、`source-documents`、`search`、
`portal`。严格 Exit Gate 对 17 路由 × 11 个 fixture 状态 × 2 种语言执行 374 份文档的
伪语言泄漏、DOM 骨架、语言文字、链接/表单和可访问性审计；Search/Portal 另外执行
Search/Portal 页面状态、枚举词表及样例内容审计。L3 专项覆盖 Stories 的 `narrative`、
`evidence`、`timeline` 三种模式；History/Source Documents 覆盖 `A0`、`S3`、`CPA`、
`V1.x` 四个范围；所有内部链接保留 `fixture`、记录 ID 和显式语言状态。

所有界面文案、封闭枚举和程序生成说明均走目录；Search 的字段、记录类型、状态以及
Portal 的制品、核验和重建状态均要求显式中英文标签。属主标题、摘要、reason、错误信息、
ID、locator、范围和时间戳保持原文，只转义一次并以 `translate="no"` 或属主文本标记；
不使用宽泛的英文白名单掩盖 UI 泄漏。不存在 `*_ZH` 导出、`label_zh` 参数或双语
`*-label-zh` 选择器。

L3 页面入口接收 shell 创建的请求 `Translator`，不可在页面内重新推导语言。封闭枚举
（生命周期、模式、事件类型、文档类型和索引状态）通过 `translator.label`，计数通过
`translator.count`；程序生成的说明使用目录键和具名参数。属主标题、摘要、reason、
错误信息、ID、locator、范围和时间戳保持原文并只转义一次，机器值用
`translate="no"` 标记。Qualification 仍表示历史研究成熟度，不表示生产资格或交易准入。

页面属主自由文本（标题、摘要、`reason`、错误信息、ID、locator 和时间戳）原样保留，
由 `Translator.source_text()` 只转义一次；全站不翻译、不猜测其源语言。程序生成的
共用文案必须走目录，状态块必须用当前语言的状态标题和说明，再以带标签的“来源说明”
显示属主 `reason`。内联客户端文案通过 `<script type="application/json" id="gui-messages">`
注入；可执行 JS 保持静态且不含用户可见文案。CSS 在 `:lang(zh-CN)` 下使用中文字体
栈并取消中文标签的大写/字距规则，不保留双语 `X / 中文` 或旧的 `*-label-zh` 选择器。

最终 Manager GUI Exit Gate 的精确检查命令（均从 QuantResearch 根目录执行）为：

```console
uv run --directory manager-gui pytest -q
uv run --directory manager-gui ruff check .
uv run --directory manager-gui --with mypy --with pytest mypy --python-version 3.11 src
uv build --directory manager-gui
python -m compileall -q manager-gui/src
git diff --check
```

此外必须运行 wheel 安装后的无源码 shell 冒烟：安装刚构建的
`manager-gui/dist/quantresearch_manager_gui-*.whl` 到临时环境，分别渲染默认
`zh-CN` 和 `?lang=en`；并启动 `manager-gui-web --fixture complete`，对全部 17 个
`view` 执行中文/英文 HTML、`/api/read-model`、`/api/export` GET，确认 API 与导出
逐字节一致，且 `/`、两个 API、`/health` 的 `POST`/`PUT`/`PATCH`/`DELETE` 均返回
`405 Allow: GET, HEAD`。这些检查不改变 fixture 的只读性质，也不接触 SQLite、私有存储
或任意文件系统。

## 中文排版与术语规范

- 中文文案使用全角标点；不得写成 ASCII 逗号紧跟汉字。并列项目使用「、」，句内连接使用「和」或「与」，不以斜线代替连接词。
- 中文与拉丁词之间保留一个半角空格，例如「原始 JSON」「API 不可用」；`ID`、`JSON`、`API`、`URL`、`SHA-256`、`Schema`、`GUI` 和 `ManagerReadModel v0` 是允许保留的拉丁词。
- 术语统一从 `manager_gui.web.i18n.glossary.TERMS` 取值：`artifact` 为「制品」，`lineage` 为「谱系」，`Evidence Ledger` 为「证据账本」，`Candidate` 为「候选对象」，`Known` 为「已记录」，`Blocked` 为「已阻塞」，`Stale` 为「已过时」，`fixture` 为「样例数据」，`reverse citations` 为「被引用于」，`Portal` 为「报告门户」。
- `Candidate` 是 Factor、Model、Strategy 的共同总称；「候选策略」只用于明确的 Strategy 子类。`Qualification` 暂定为「资格评定」，其关口语义仍待 owner 确认。
- 术语禁用译法由 glossary 的 `forbidden_zh` 冻结并由测试审计；页面目录不得自行创造同义译法。

Open `http://127.0.0.1:8765/`. The shared shell mounts Atlas, Research Story,
Genome, Genome Conditions, Genome Comparison, Memory, Memory Failures,
Failure Patterns, Evidence, Lineage, Evidence Comparison, Derived Failure
Grouping, Methodology, History, Source Documents, Search, and Portal:

- `/?view=atlas&fixture=complete` renders the Atlas hook;
- `/?view=stories&fixture=complete&mode=evidence` renders the Story hook;
- `/?view=strategies&fixture=complete&genome_id=genome-fixture-1` renders the Genome hook;
- `/?view=strategy-conditions&fixture=complete&genome_id=genome-fixture-1` renders condition evidence;
- `/?view=strategy-genome-comparison&fixture=complete&left_genome_id=genome-left&right_genome_id=genome-right` renders comparison;
- `/?view=methodology&fixture=complete&scope=A0` renders the versioned method archive;
- `/?view=history&fixture=complete&scope=S3` renders source-recorded history;
- `/?view=source-documents&fixture=complete&scope=CPA` renders the approved document index;
- `/?view=memory&fixture=complete&memory_id=memory-fixture-1` mounts the S3-T1 Memory catalog/detail hook;
- `/?view=memory-failures&fixture=complete&failure_id=memory-fixture-1` mounts the Memory failure/lineage projection;
- `/?view=failure-patterns&fixture=complete&pattern_id=pattern-fixture-1` mounts ordinary failures and explicitly Derived patterns;
- `/?view=evidence&fixture=complete` mounts the Evidence Ledger with the conclusion → evidence → source/artifact → lineage trace;
- `/?view=lineage&fixture=complete&record_id=conclusion-1` mounts the bounded Lineage graph, table, inspector, and shortest evidence path;
- `/?view=evidence-object-comparison&fixture=complete` mounts the general object/evidence comparison (not the S2 Genome comparison);
- `/?view=derived-failure-grouping&fixture=complete` mounts explicitly Derived success/failure groups;
- `/?view=search&fixture=complete&q=campaign` mounts deterministic Search across approved index entries;
- `/?view=portal&fixture=complete` mounts Strategy Reporting source/artifact metadata.

The fixture-backed path is read-only and preserves `fixture`, `scope`, `panel`, `q`,
`snapshot_token`, Atlas/Memory/failure filters, story root identifiers, `record_id`,
`document_id`, and `mode` in stable links. The shared top bar, navigation, read-only badge, status
block, Inspector, and raw JSON drawer remain owned by the shell. Methodology links
its explicit document and record references to Source Documents and History; History
links source artifacts, records, and documents; Source Documents links record
citations and reverse citations in both directions. No write or mutation route is
exposed: `POST` requests return `405 Allow: GET, HEAD`.

The command emits one JSON `ManagerReadModel v0` envelope when using the
contract entry point. Fixtures are synthetic and do not stand in for a
connected data gate.

## Verification and release checks

Run the complete package gate from the QuantResearch repository root:

```console
uv run --directory manager-gui pytest -q
uv run --directory manager-gui ruff check .
uv run --directory manager-gui --with mypy --with pytest mypy --python-version 3.11 src
uv build --directory manager-gui
python -m compileall -q manager-gui/src
git diff --check
```

CLI smoke:

```console
uv run --directory manager-gui python -m manager_gui --fixture complete --pretty
uv run --directory manager-gui manager-gui-web --fixture complete --port 8765
```

With the server running on `127.0.0.1:8765`, live HTTP smoke checks every route
and the read-only API boundary:

```console
python -c "import urllib.request; views=['atlas','stories','strategies','strategy-conditions','strategy-genome-comparison','memory','memory-failures','failure-patterns','evidence','lineage','evidence-object-comparison','derived-failure-grouping','methodology','history','source-documents','search','portal']; base='http://127.0.0.1:8765'; [urllib.request.urlopen(f'{base}/?view={v}&fixture=complete').read() for v in views]; [urllib.request.urlopen(f'{base}/api/read-model?view={v}&fixture=complete').read() for v in views]; urllib.request.urlopen(f'{base}/api/export?view=search&fixture=complete').read(); print('GET route/read-model/export smoke passed')"
```

`POST`, `PUT`, `PATCH`, and `DELETE` to `/`, `/api/read-model`,
`/api/export`, and `/health` must return `405` with `Allow: GET, HEAD`.

## ManagerReadModel v0

The envelope is defined in `src/manager_gui/models.py` and contains exactly the
following public fields in addition to its schema identifier:

- `data`: JSON-compatible value from the requested read;
- `source_refs`: stable, public source pointers;
- `as_of`: source observation time, or `null` when unavailable;
- `snapshot_token`: opaque source snapshot identity, or `null`;
- `derivation`: direct/derived/interpreted rule and named inputs;
- `availability`: completeness, status, reason, and retryability;
- `errors`: explicit non-silent limitations or failures.

The machine-readable schemas are exported as
`MANAGER_READ_MODEL_JSON_SCHEMA`, `SOURCE_REFERENCE_JSON_SCHEMA`,
`AVAILABILITY_JSON_SCHEMA`, and `ERROR_JSON_SCHEMA`. The only status values are
`known`, `derived`, `interpreted`, `missing`, `blocked`, `stale`,
`incomparable`, `integrity_failure`, and `api_unavailable`.

## Shared WebUI contract

Shared WebUI code lives under `src/manager_gui/web/`; no Atlas or Research Story
owner behavior is implemented here. `navigation.py` owns URL-stable view IDs
and integration hooks. `status.py` owns reusable rendering for all nine
read-model statuses plus `ready`, `loading`, `empty`, `partial`, and `error`
operational states. `app.py` consumes only `ManagerDataProvider.read` and
renders the shell around the unchanged v0 envelope.

The stable URL query keys are:

- `view`: `atlas`, `stories`, `strategies`, `strategy-conditions`,
  `strategy-genome-comparison`, `memory`, `memory-failures`, `failure-patterns`,
  `evidence`, `lineage`, `evidence-object-comparison`, `derived-failure-grouping`,
  `methodology`, `history`, `source-documents`, `search`, or `portal`;
- `fixture`: one of the deterministic shell fixture states (`empty`, `complete`,
  `partial`, `blocked`, `stale`, `incomparable`, `integrity_failure`,
  `api_unavailable`, `not_evaluated`, `cursor_expired`, `snapshot_drift`);
- `scope`: `A0`, `S3`, `CPA`, or `V1.x` on History and Source Documents;
- `panel`: `inspector` or `events` (optional);
- `q`: literal, case-insensitive Search terms (optional; all whitespace-delimited terms must match);
- `type`/`record_type` and `source`: Search filters; `cursor` is an opaque Search continuation token;
- `mode`: `narrative`, `evidence`, or `timeline` on the Stories route;
- `page` and `page_size`: bounded presentation pagination for already-read entries;
- `record_type`, `state`, `date`, `source`, and `availability` on Atlas;
- `genome_id` on Genome and condition evidence; `left_genome_id` and
  `right_genome_id` on Genome comparison;
- `family`, `stage`, `outcome`, `failure_category`, `subject`, and `campaign` on
  Memory/failure filters; `memory_id`, `failure_id`, and `pattern_id` on detail views;
- `record_id`, `document_id`, `campaign`, `study`, and `strategy_family` are opaque
  object/root context retained by detail and mode links; Search result links use
  `genome_id`, `memory_id`, `record_id`, or `document_id` for the owning route;
- `report_id`, `source_publication_id`, and `artifact_id` select Portal metadata context;
- `record_id`, `artifact_id`, and `source_id` select the Evidence detail panel;
  `record_id` is the Lineage root; `node`, `path_to`, `direction`, `relations`,
  `record_types`, `depth`, `page_size`, `cursor`, and `snapshot_token` bound a Lineage page.

All page hooks register or consume a `NavigationItem`, use the public provider seam,
and keep the same `ManagerReadModel v0` envelope. The shell passes a cached copy of
the envelope to hooks that accept a provider, so an integrated route performs one
owner read. The current public hook contract is:

- `manager_gui.web.atlas.render_atlas_view(provider, filters=..., query_context=..., snapshot_token=...)`
  mounts `data-integration-hook="atlas-view"`;
- `manager_gui.web.research_story.render_research_story(model, mode=..., base_path=..., query=...)`
  mounts `data-integration-hook="research-story-view"`;
- `manager_gui.web.methodology.render_methodology_view(provider_or_model, snapshot_token=..., query_context=...)`
  mounts `data-integration-hook="methodology-view"`;
- `manager_gui.web.history.render_history_view(provider_or_model, scope=..., base_path=..., query=..., snapshot_token=...)`
  mounts `data-integration-hook="history-view"`;
- `manager_gui.web.documents.render_source_documents_view(provider_or_model, scope=..., boundary=..., base_path=..., query=..., snapshot_token=...)`
  mounts `data-integration-hook="source-documents-view"`;
- `manager_gui.web.memory.render_memory_view(provider, filters=..., query_context=..., memory_id=..., snapshot_token=...)`
  mounts `data-integration-hook="memory-view"`;
- `manager_gui.web.failure_patterns.render_memory_failure_view(provider_or_model, filters=..., query_context=..., failure_id=..., pattern_id=..., snapshot_token=...)`
  mounts the shared `data-integration-hook="failure-patterns-view"` for formal Memory failure/lineage;
- `manager_gui.web.failure_patterns.render_failure_patterns_view(provider_or_model, filters=..., query_context=..., failure_id=..., pattern_id=..., snapshot_token=...)`
  mounts the same hook for ordinary failures and explicitly Derived patterns;
- `manager_gui.web.evidence.render_evidence_view(provider_or_model, snapshot_token=..., query_context=...)`
  mounts `data-integration-hook="evidence-view"` (resource `evidence`);
- `manager_gui.web.lineage.render_lineage_view(provider_or_model, query_context=..., snapshot_token=..., record_id=..., route=...)`
  mounts `data-integration-hook="lineage-view"` (resource `lineage`);
- `manager_gui.web.evidence_comparison.render_evidence_comparison_view(provider_or_model, snapshot_token=..., query_context=...)`
  mounts `data-integration-hook="evidence-comparison-view"` (resource `evidence_comparison`);
- `manager_gui.web.failure_grouping.render_failure_grouping_view(provider_or_model, snapshot_token=..., query_context=...)`
  mounts `data-integration-hook="failure-grouping-view"` (resource `failure_grouping`).
- `manager_gui.web.search.render_search_view(provider_or_model, query_context=..., snapshot_token=...)`
  mounts `data-integration-hook="search-view"` (resource `search`) and links each
  explicit hit to a mounted Atlas, Genome, Memory, Evidence, Lineage, or Source Documents route.
- `manager_gui.web.portal.render_portal_view(provider_or_model, query_context=..., snapshot_token=...)`
  mounts `data-integration-hook="portal-view"` (resource `report_source`) and keeps
  source publication, generated artifact, renderer/version, verify, and rebuild metadata distinct.

The S3 routes keep Formal Research Memory, ordinary failure records, and Derived
patterns visibly separate. A missing or zero-entry Memory scope is rendered as
missing/not recorded; blocked, stale, integrity-failure, and API-unavailable
states never get relabeled as empty. Lineage is six-dimensional (campaign,
candidate, run, evidence, artifact, and source document); each absent or blocked
edge remains visibly `Missing / Unconfirmed`. Explicit fixture IDs link Memory to
failure/Derived views and onward to campaign, run, evidence, and source-document
locators. No similarity or LLM promotion, private-storage fallback, dereference,
or mutation endpoint is used. S3 integrated tests cover complete, zero-entry,
empty, partial, blocked, stale, integrity-failure, API-unavailable, missing-lineage,
context-preserving links, and one-read provider audits.

### S4 Evidence, Lineage and comparison routes / exit evidence for #639

S4-T4 mounts the four S4 page hooks through the shared read-only shell. The shell
still owns the top bar, navigation, read-only badge, status block, Inspector, raw
JSON drawer, export control, and URL state; each route performs exactly one public
provider read of its own resource through the cached envelope.

| `view` | Hook (`data-integration-hook`) | Renderer | Resource |
| --- | --- | --- | --- |
| `evidence` | `evidence-view` | `evidence.render_evidence_view` | `evidence` |
| `lineage` | `lineage-view` | `lineage.render_lineage_view` | `lineage` |
| `evidence-object-comparison` | `evidence-comparison-view` | `evidence_comparison.render_evidence_comparison_view` | `evidence_comparison` |
| `derived-failure-grouping` | `failure-grouping-view` | `failure_grouping.render_failure_grouping_view` | `failure_grouping` |

The general comparison is separate from the S2 Genome comparison: it has its own view
ID, hook, and resource, and the S2 route (`strategy-genome-comparison`, resource
`genome_comparison`) is unchanged. Derived groups are always labelled Derived and never
become an owner fact, a success rate, or a ranking.

**Conclusion → evidence → source/artifact → lineage.** `web/evidence_trace.py` renders
a trace after the Evidence Ledger and gives the ledger's `record_id` / `artifact_id` /
`source_id` links a real selected-detail panel. It follows only explicit published
pointers: `conclusion_id` on the ledger and `lineage_id` on a record or artifact name
the Lineage root to open. Nothing is matched by similarity. A pointer, locator, record,
or artifact that is not published is shown as `Missing / Unconfirmed`; that is not a
failure and not proof of absence. These two pointer names are the read-seam contract
this GUI consumes; until an owner publishes them, the lineage hop stays Missing.

Rules every S4 route follows:

- **Snapshots are never mixed.** Each resource owns its snapshot. Links from Evidence to
  Lineage, comparison, or grouping do not forward `snapshot_token`, `page`, `page_size`,
  or `cursor`; links inside one route keep them. A Lineage page pinned to a snapshot it
  did not read fails closed with `snapshot_drift`.
- **Locators.** `web/locators.py` decides which locator may become a link. Only public
  (`http`/`https` without credentials) and fixture/`workspace`/`artifact` locators do;
  local paths, `file:` URLs, and credential-bearing URLs are withheld and shown as
  Missing. No locator is ever dereferenced.
- **Unreadable is never empty.** Blocked, stale, integrity-failure, and API-unavailable
  sources render the shared `error` state; only a `missing` source renders `empty`.

Shell `fixture` values map onto every S4 seam in `web/s4_fixtures.py` (built from each
owning module's own builder):

| `fixture` | Evidence | Lineage | Comparison / grouping |
| --- | --- | --- | --- |
| `complete` | known ledger, both evidence classes | ready graph and path | derived axes / groups |
| `empty` | `missing`, empty state | `missing`, empty state | `missing`, empty state |
| `partial` | known, incomplete | partial page, next cursor, no absence claim | known, incomplete |
| `blocked` | blocked outcome, never `fail` | withheld, `source_blocked` | error state |
| `not_evaluated` | `not_evaluated` outcome | nodes keep `not_evaluated` status | not evaluated / excluded from both groups |
| `stale` | stale, retained for history | stale label, not withheld | error state |
| `incomparable` | incomparable outcome | withheld, `incomparable` | `incomparable` status, per-axis reasons kept |
| `integrity_failure` | artifact `hash_mismatch` with its reason | withheld, `integrity_failure` | error state |
| `api_unavailable` | nothing published | withheld, `source_unavailable` | error state |
| `cursor_expired` | stale, cause `cursor_expired` | withheld, `cursor_expired`, clean restart link | stale, cause named |
| `snapshot_drift` | stale, cause `snapshot_drift` | withheld, `snapshot_drift`, clean restart link | stale, cause named |

`not_evaluated`, `cursor_expired`, and `snapshot_drift` are S4-only selector values:
every other route receives the shared generic envelope for them, so S1/S2/S3/S5
behavior is unchanged. The fixture provider serves only the first Lineage page, so
following its next-cursor link fails closed with `cursor_mismatch`; it does not emulate
a mutable backend.

Exit evidence for S4 (#611 acceptance criteria; the issue stays open until the release
owner closes it):

1. Conclusion to source/artifact, evidence level, and limitations:
   `test_s4_integration.py::test_conclusion_leads_to_evidence_sources_artifacts_and_lineage`.
2. Bounded expansion, pagination, snapshot, and table alternative: `test_lineage.py`
   plus the integrated Lineage routes in `test_s4_integration.py`.
3. Per-axis equal/different/missing/incomparable: `test_evidence_comparison.py` and
   `test_incomparable_keeps_the_per_axis_reason_and_is_never_ranked`.
4. Blocked and not-evaluated never read as failure:
   `test_blocked_is_never_shown_as_a_failure_or_as_empty`,
   `test_not_evaluated_stays_distinct_from_failure_on_every_route`.
5. Artifact hash failure keeps its reason:
   `test_integrity_failure_keeps_the_specific_artifact_reason`.
6. Incomplete pagination, expired cursor, unknown schema, snapshot drift: the fixture
   matrix in `test_s4_integration.py` and `test_lineage.py`.
7. Read-only and single-read audit, large graph: `test_each_s4_route_reads_exactly_its_resource_once_with_the_requested_snapshot`,
   `test_large_lineage_graph_stays_bounded_inside_the_shell`, and the S6-T3 interaction suite,
   which now also covers the four S4 routes (accessibility, read-only controls, export,
   status vocabulary).

Known limits: fixtures are synthetic and do not stand in for a connected data gate; the
Evidence trace shows at most 20 rows per step and defers to the ledger for the rest.

### S6-T4 consumption contract for S4

S6-T4 may link Search results and Portal sections to the S4 routes, and only through
the shared URL state:

1. Build links with `context_link(context, view=ViewId.EVIDENCE | ViewId.LINEAGE, record_id=...)`;
   keep `fixture`, `q`, `panel`, and opaque context, and drop `snapshot_token`, `page`,
   `page_size`, and `cursor` when the target is a different resource.
2. Treat a lineage `record_id` as a Lineage root only when the owner published it; do not
   derive it from an Evidence `record_id` or any similar-looking id.
3. Render a locator as a link only through `web.locators.public_locator`.
4. Do not call S4 renderers with a second provider read; pass the cached envelope.
5. Keep Search and Portal outside S4's domain resources; S6-T4 composes their
   cached read envelopes and may link into S4 only through published stable IDs.

### S3 route integration / exit evidence for #628

The S3 read-only loop is:
`Research Memory → Memory failure/lineage or ordinary failure → explicit Derived
pattern → campaign/run/evidence/source document (or Missing)`. The route hooks
consume the existing `ManagerReadModel v0` envelope and cached shell read, so each
integrated route performs exactly one public provider read. This note records the
S3-T3 exit evidence; it does not close issue #628 and does not implement S4 or S6.

### S2 Genome route integration / exit evidence for #626

The S2-T3 shell mounts the existing read-only page hooks without replacing the
shared document chrome or introducing a second envelope:

- `/?view=strategies&fixture=complete&genome_id=genome-fixture-1` mounts
  `manager_gui.web.genome.render_genome_view` at
  `data-integration-hook="strategy-genome-view"`;
- `/?view=strategy-conditions&fixture=complete&genome_id=genome-fixture-1`
  mounts `manager_gui.web.conditions.render_genome_conditions_view` at
  `data-integration-hook="strategy-genome-conditions-view"`;
- `/?view=strategy-genome-comparison&fixture=complete&left_genome_id=genome-left&right_genome_id=genome-right`
  mounts `manager_gui.web.comparison.render_genome_comparison_view` at
  `data-integration-hook="strategy-genome-comparison-view"`.

The stable Genome query key is `genome_id`; comparison uses
`left_genome_id` and `right_genome_id`. Genome detail links retain fixture,
panel, query, snapshot token, and comparison context when linking to condition
evidence and comparison. Condition evidence links back to Genome and comparison;
comparison links back to both Genome identities and left-side condition evidence.
Published source and lineage locators remain explicit source links, and the
shared Inspector/raw JSON drawer retains the complete `ManagerReadModel v0`
envelope including source refs, as-of, snapshot, derivation, availability, and
errors. No page hook reads private storage or exposes a mutation operation.

S2 integrated fixtures cover complete, empty, partial, blocked, stale,
incomparable, integrity-failure, and API-unavailable routes. Empty Genome and
condition scopes render missing/not-recorded semantics; partial records remain
partial; blocked, stale, incomparable, integrity-failure, and API-unavailable
states remain distinct. The provider audit verifies one `read` call per mounted
resource and no publish/propose/retry/delete/retire/revalidate/create/update/
write method. These checks are the S2 exit evidence for #626; the issue remains
open until the release owner closes it.

S3's Memory and failure modules are mounted through the shared read-only shell.
S4 can consume the stable Memory/failure source, lineage, condition, and comparison
hooks through the same v0 read seam; S3-T3 does not implement an S4 evidence portal.
S6 can compose these hooks for future
search, portal, and accessibility work without changing the route keys or
introducing page-specific envelopes.

Methodology is the canonical methodology-record surface: usage, results, validity
evidence, limitations, failure cases, versions, and superseded state are separate
fields. History admits only explicit source-event times and categories. Source
Documents is an interpreted-document index: document metadata, plans, reports,
retrospectives, future ideas, external sources, and raw evidence never become
canonical facts merely because they are indexed. Each page has explicit boundary
copy and stable links to the related view.

The app remains responsible for the document chrome, top bar, navigation,
read-only badge, shared status/operational-state rendering, Inspector, raw JSON
drawer, and URL state. Page hooks must not add mutation endpoints, infer owner
facts from private storage, or replace the shared Inspector/event drawer.

### S1 exit evidence / integration note for #618

The S1 fixture path is a single read-only loop:
`Atlas object → Research Story mode → explicit source reference`. The `complete`
fixture supplies a campaign, study, strategy family, lifecycle records, story
chapters, and a source locator; `empty`, `partial`, `blocked`, `stale`,
`incomparable`, `integrity_failure`, and `api_unavailable` remain distinct
fixture states on both integrated routes. The integration tests verify the
route markers, stable query/root/filter/mode context, source links, shell chrome,
`/api/read-model`, `/health`, and `405` responses to mutation attempts. The
provider audit verifies that the fixture adapter exposes only `read`; no S1 code
opens SQLite/private storage or calls publish, retry, delete, retire, or
revalidation operations. This note is evidence for issue #618 and does not
close the issue or implement S2–S6.

### S6-T4 Search, Portal, and final S6 exit gate

S6 is integrated through the same read-only shell and `ManagerReadModel v0`
seam as S1-S5. Search and Portal are mounted routes, not placeholders, while
remaining outside the canonical research-state owners.

#### Full mounted route table

| `view` | Hook (`data-integration-hook`) | Read resource | Stable selectors / purpose |
| --- | --- | --- | --- |
| `atlas` | `atlas-view` | `atlas` | lifecycle filters and `record_id` |
| `stories` | `research-story-view` | `stories` | `mode`, campaign/study/family roots |
| `strategies` | `strategy-genome-view` | `genomes` | `genome_id` |
| `strategy-conditions` | `strategy-genome-conditions-view` | `genome_conditions` | `genome_id` |
| `strategy-genome-comparison` | `strategy-genome-comparison-view` | `genome_comparison` | left/right Genome IDs |
| `memory` | `memory-view` | `memory` | Memory filters and `memory_id` |
| `memory-failures` | `failure-patterns-view` | `memory` | `failure_id` / Memory lineage |
| `failure-patterns` | `failure-patterns-view` | `failure_patterns` | failure/pattern filters and IDs |
| `evidence` | `evidence-view` | `evidence` | `record_id`, `artifact_id`, `source_id` |
| `lineage` | `lineage-view` | `lineage` | published `record_id`, cursor, snapshot |
| `evidence-object-comparison` | `evidence-comparison-view` | `evidence_comparison` | declared comparison axes |
| `derived-failure-grouping` | `failure-grouping-view` | `failure_grouping` | explicit Derived groups |
| `methodology` | `methodology-view` | `methodology` | `scope` and method references |
| `history` | `history-view` | `history` | `scope` and source-event records |
| `source-documents` | `source-documents-view` | `source_documents` | `scope`, `document_id` |
| `search` | `search-view` | `search` | `q`, `type`/`record_type`, `source`, cursor |
| `portal` | `portal-view` | `report_source` | `report_id`, publication/artifact IDs |

Search performs deterministic literal matching over the approved index only.
Every result keeps source provenance and links to a real mounted owner surface:
record → Atlas, Genome → Strategies, Memory → Memory, Evidence → Evidence,
Lineage → Lineage, and document → Source Documents. Links retain fixture,
query, panel, opaque context, and the requested snapshot token while dropping
presentation pagination/cursor state that belongs only to the Search page.
An incomplete page is explicitly partial and never claims a global no-match.

Portal displays source publication metadata separately from generated artifact
metadata, including renderer/version, verification status, rebuild status, and
digest. It is always labelled as read-only publication metadata and never as
canonical research state. It has no rebuild, run, publish, retry, or mutation
control. Private/local locators are withheld through `public_locator`; no
locator is dereferenced.

#### Shared interaction and accessibility contract

- `web/status.py` is the one source-status vocabulary for every route; blocked,
  stale, incomparable, integrity-failure, API-unavailable, empty, and partial
  states remain distinct and retain English/Chinese accessible labels.
- `web/interaction.py` owns opaque copy controls, local JSON export, graph/table
  alternatives, and stable `/api/export` compatibility reads. Export embeds the
  already-read envelope and never writes a ledger or performs a second read.
- The shell owns document chrome, navigation, read-only badge, keyboard/focus
  behavior, Inspector, raw JSON drawer, URL state, and Chinese labels. Every
  mounted route uses a cached envelope and therefore performs one provider read.
- `POST`, `PUT`, `PATCH`, and `DELETE` return `405 Allow: GET, HEAD`; providers
  expose only `read`.

#### Exit evidence

`test_s6_integration.py` is the final S6 exit gate. It covers all 17 mounted
routes across every shared fixture selector, Search partial pagination and
honest unavailable/empty/blocked states, Search cross-route identity links,
Portal source/artifact separation, navigation/accessibility, one-read provider
audits, no arbitrary filesystem access, `/api/read-model`, `/api/export`, and
HTTP mutation rejection. Existing S1-S5 suites remain green and continue to
cover their owner-specific boundaries.

## Read-only boundary

`ManagerDataProvider` in `src/manager_gui/provider.py` exposes one operation:
`read(resource, snapshot_token=...)`. It intentionally has no publish,
propose, retry, delete, retire, revalidation, create, update, or write method.
All source adapters must return the envelope and preserve provenance. No
provider may read private SQLite/storage or use CLI stdout as an internal API.

`src/manager_gui/fixtures.py` supplies deterministic `empty`, `partial`,
`blocked`, `stale`, `incomparable`, `integrity_failure`, `api_unavailable`,
`not_evaluated`, `cursor_expired`, and `snapshot_drift` states. The integrated
`web/s6_fixtures.py` maps the same selectors onto Search and Portal-specific
complete/partial/empty/integrity/API envelopes where those seams define them;
other selectors retain their generic owner status. The empty state is represented
as `missing`; partial state remains `known` with `complete: false` and an
explicit limitation. This prevents “not recorded” from becoming “did not happen”.

## Public seam decisions

The declarations in `src/manager_gui/seams.py` are decisions for later slices,
not implementations of other owners:

| Seam | Owner | Decision in T1 | Until available |
| --- | --- | --- | --- |
| Package catalog | `strategy-workspace` | Consume a versioned public `WorkspaceClient` package-catalog record via `list_records(record_type="package_catalog")` and `get_record`. | Report `api_unavailable`; never read the private `packages` table, SQLite, or scrape CLI output. |
| Historical-document index | `manager-gui` adapter | Use an explicit configured index with stable `document_id`, type, revision, source ref, and relations. | Do not scan arbitrary paths or treat filenames as identity; document interpretation stays `interpreted`. |

These are public-read seams only. T1 does not add an owner API, a database
adapter, a page, a mutation, a retry, or a fallback.

## S5 directory and document boundary

`SourceDocumentsViewModel` consumes an explicit approved document index through
`ManagerDataProvider.read("source_documents")`. It uses stable `document_id`, type,
version, source locator, update time, forward citations, and reverse citations. It
never treats a filename as identity, scans a directory, opens a document, reads
SQLite, or dereferences a private path. URI/fixture locators are renderable public
references. A local `file:` or Windows path is renderable only when it is beneath
an explicitly configured `ApprovedDirectoryBoundary` (for example,
`ManagerGUIApp(..., approved_directories=("D:/approved-documents",))`); otherwise
its locator is withheld and the page reports `boundary-blocked`.

The index keeps `missing`, `version-conflict`, `not-indexed`, `api-unavailable`,
and `boundary-blocked` distinct. A version conflict retains all versions and never
silently chooses the newest one. History and Methodology can link into the Source
Documents route, but a link does not imply that a document interpretation is a
canonical owner fact.

### S5 exit evidence / integration note for #629

The S5 read-only loop is:
`Methodology record → explicit document/record refs → Source Documents ↔ History
record/event → source artifact/document`. Integrated routes preserve the shared
shell, source refs, `as_of`, snapshot token, status/error envelope, raw JSON, and
opaque query context. Deterministic scope fixtures cover `A0`, `S3`, `CPA`, and
`V1.x`; shell fixtures exercise missing, partial, blocked, stale, incomparable,
integrity-failure, and API-unavailable states. Tests verify source-event-only
history, canonical-fact versus document-interpretation boundaries, document and
record navigation, bounded pagination, provider read-only shape, and approved
directory blocking. This evidence does not close issue #629 from the worktree;
the final S6 Search/Portal integration and exit evidence are recorded below.
## Planned Manager GUI S1–S6 ownership

All later slices consume `ManagerReadModel v0`; they do not introduce a second
page-specific envelope. S2-S5 remain mounted consumers, and S6 is integrated here
through the Search and Portal public read seams.

| Slice | Owner | Dependency | Read-model contract |
| --- | --- | --- | --- |
| S1 / T1 base contract | `manager-gui` | none | defines v0 |
| S1 / T2 shared WebUI shell | `manager-gui` | T1 | shared shell, statuses, navigation, inspector, raw JSON |
| S1 / T3 Atlas and Research Story | `manager-gui` | T1/T2 plus approved public read seams | v0 |
| S2 Genome and conditions | `manager-gui` | T1; Apex public read seam | v0 |
| S3 Memory and failure knowledge | `manager-gui` | T1; Apex public read seam | v0 |
| S4 Evidence, lineage, comparison | `manager-gui` | T1; owner-published evidence/read seams | v0, integrated in S4-T4 |
| S5 Methodology, history, source documents | `manager-gui` | T1; document-index seam | v0, integrated in S5-T3 |
| S6 Search, portal, accessibility | `manager-gui` | T1 and S2–S5 read seams | v0 |

### S2–S6 consumption contract
`ManagerDataProvider.read(resource, snapshot_token=...)` boundary. A page may add
its own exported renderer and URL-stable `NavigationItem`, but it must:

1. preserve `source_refs`, `as_of`, `snapshot_token`, `derivation`,
   `availability`, and `errors` without guessing missing owner facts;
2. use the shared status renderer and distinguish empty, partial, blocked, stale,
   incomparable, integrity-failure, and API-unavailable states;
3. keep the shared shell's Inspector, raw JSON drawer, read-only badge, and
   query-context behavior rather than introducing a page-specific envelope;
4. expose only approved public reads, with no SQLite/private-storage fallback,
   CLI stdout scraping, mutation method, retry, publish, delete, retire, or
   revalidation call; and
5. keep page-specific facts in the owning slice and publish a stable hook for
   S6 search/portal/accessibility consumption.

S2 consumes Genome/condition reads, S3 consumes Memory/failure reads, S4 consumes
Evidence/lineage/comparison reads, S5 consumes Methodology/History/document-index
reads, and S6 composes those read seams for Search and Portal integration. S6-T4
owns the shared-route mounts and final regression/accessibility exit gate without
changing any domain repository or adding a mutation seam.

## Locale-aware shared shell

The shared shell defaults to Simplified Chinese (`zh-CN`). Add `?lang=en` to any
HTML route for English; the locale is URL state, not a cookie or an
`Accept-Language` negotiation. Supported aliases (`zh`, `zh-Hans`, `en-US`, and
`en-GB`) are normalized to the canonical URL tokens.

Shell and navigation labels are resolved through the per-request `Translator`.
The no-JavaScript language switcher preserves the full query string, including
repeated opaque parameters, and exposes `lang`, `hreflang`, and the current
locale state. Internal navigation and GET controls retain explicit language state
when it was requested; raw JSON and API/export payloads remain language-neutral.

Page-specific prose is intentionally not translated by the shared shell slice.
Its page hooks receive the same request translator so later route migrations can
add catalog entries without introducing a second i18n layer.

## Reader R1 contract and shell consumption

Reader R1 is a UI-only projection over one already-read `ManagerReadModel v0`.
It does not replace or extend the owner envelope. `ManagerGUIApp.reader_projection(url)`
and the HTML `reader-contract` seam expose the same immutable projection to future
Reader pages. The seam carries `data`, optional `summary`, `claims`, `limitations`,
`unknowns`, `source_refs`, `as_of`, `snapshot_token`, `derivation`, and
`availability`, plus the retained v0 `raw_source`. Claims always name source
references and a derivation; Reader copy stores stable catalog keys and typed
parameters rather than generated prose.

The shell mounts that contract on all 17 routes without implementing a concrete
Reader page. The global `mode=reader|expert|raw` links are ordinary GET links and
retain repeated opaque query parameters, blank values, `lang`, fixture, scope,
root, filters, and snapshot context. Reader mode consumes the projection; Expert
and Raw remain compatibility references to the unchanged `ManagerReadModel v0`
bytes. `/api/read-model` and `/api/export` do not include Reader projection data or
presentation-only mode state, and remain byte-stable across language and mode
changes.

Fixture-backed shell reads pass explicit `sample_data` and show the fixed sample
banner. An injected owner provider never receives fixture metadata or a sample
banner, even when its source values resemble a fixture. Source references and
owner free text remain verbatim (escaped once at the HTML boundary); no URL,
locator, count, or status is promoted to an owner fact.

`known`, `derived`, and `interpreted` retain their stated semantics. `missing`,
`blocked`, `not_evaluated`, `stale`, `incomparable`, integrity failure, and API
unavailability remain explicit gaps or limitations and are never relabeled as
success or failure. `partial` means incomplete scope, not a negative result.
Reader explanations come only from reproducible templates and typed source facts;
there is no LLM call, private-storage/SQLite read, file-system scan, recalculation,
write, retry, publish, or mutation seam. The central i18n registry registers the
Reader catalog once and validates bilingual placeholder parity and duplicate-key
rejection before use.

### R2–R5 consumption rules

R2 Overview and Research Story, R3 Strategy/Genome, R4 Memory/Failure, and R5
Evidence/Lineage/Comparison may consume the projection only through the shell
contract or `reader_projection` helper. Each page must:

1. preserve `source_refs`, `as_of`, `snapshot_token`, `derivation`, and
   `availability`, and keep `claims`, `limitations`, and `unknowns` visibly
   distinct;
2. label every GUI computation as `Derived` with a named rule and version, and
   never upgrade it or owner free text to a canonical fact;
3. render missing, blocked, not-evaluated, stale, and incomparable states using
   the fixed Reader catalog language without mapping them to a pass/fail outcome;
4. keep Reader, Expert, and Raw URL state shareable and preserve all opaque query
   pairs, while leaving v0 API/export and the read-only HTTP boundary unchanged;
5. use the approved public `ManagerDataProvider.read` seam only; no SQLite,
   private storage, owner mutation, LLM, revalidation, or fallback inference; and
6. keep page-specific structure in the owning R2–R5 route and consume the shared
   shell's mode controls, sample boundary, status/ARIA surfaces, Inspector, and
   raw JSON drawer rather than adding a second envelope.
