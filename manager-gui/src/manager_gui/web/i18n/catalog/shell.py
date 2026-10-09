"""Shared Manager GUI shell translations."""

# Catalog templates are kept readable as bilingual pairs.
# ruff: noqa: E501

from collections.abc import Mapping

from ..translator import M

ENTRIES: Mapping[str, M] = {
    "workspace.unsafe": M(
        "暂时无法提供只读快照：工作区可能正在被写入，或读取安全状态无法确认。不能证明读取完整且一致，请稍后重试；不会改用样例数据。",
        "A read-only snapshot is temporarily unavailable: the workspace may be changing, or read safety cannot be confirmed. A complete, consistent read cannot be proven. Please retry later; sample data will not be substituted.",
    ),
    "workspace.wait": M(
        "已自动重试 {attempts}/{limit} 次；下一次将在 {seconds} 秒后重试。",
        "Automatic retries: {attempts}/{limit}; next retry in {seconds} seconds.",
    ),
    "workspace.stopped": M(
        "自动重试已停止（{attempts}/{limit} 次）。安全条件恢复后可人工重试。",
        "Automatic retries stopped ({attempts}/{limit}). Retry manually when safe conditions return.",
    ),
    "workspace.manual": M("人工重试", "Retry manually"),
    "workspace.cancel": M("取消自动重试", "Cancel automatic retry"),
    "workspace.cancelled": M("已取消浏览器自动读取。", "Browser automatic reads cancelled."),
    "workspace.startup_failed": M(
        "无法读取所选工作区。请检查路径、访问权限、版本与完整性；未启动服务，也未改用样例数据。",
        "Cannot read the selected workspace. Check its path, permissions, version and integrity. The server was not started; sample data was not substituted.",
    ),
    "shell.brand": M("{term:manager_gui}", "{term:manager_gui}"),
    "shell.title": M("{view} · {term:manager_gui}", "{view} · {term:manager_gui}"),
    "shell.skip_to_workspace": M("跳到工作区", "Skip to workspace"),
    "shell.brand_home": M("管理界面首页", "Manager GUI home"),
    "shell.workspace_snapshot": M(
        "{term:fixture} · {term:snapshot} {snapshot}",
        "{term:fixture} workspace · {term:snapshot} {snapshot}",
    ),
    "shell.owner_workspace_snapshot": M(
        "工作区只读视图 · {term:snapshot} {snapshot}",
        "Workspace read view · {term:snapshot} {snapshot}",
    ),
    "shell.read_only": M("只读", "READ ONLY"),
    "shell.read_only_aria": M("只读，已禁用变更", "Read-only; mutations are disabled"),
    "shell.global_search": M("全局搜索", "Global search"),
    "shell.search_placeholder": M("搜索只读模型…", "Search read models…"),
    "shell.shared_panels": M("共享面板", "Shared panels"),
    "shell.open_inspector": M("打开检查器", "Open inspector"),
    "shell.open_events": M("打开事件与原始 JSON", "Open events and raw JSON"),
    "shell.inspector": M("{term:inspector}", "{term:inspector}"),
    "shell.read_context": M("读取上下文", "Read context"),
    "shell.read_model": M("读取模型", "Read model"),
    "shell.status": M("状态", "Status"),
    "shell.snapshot": M("{term:snapshot}", "{term:snapshot}"),
    "shell.observed_at": M("观测时间", "Observed at"),
    "shell.sources": M("{term:source}", "{term:source}"),
    "shell.none_recorded": M("未记录", "None recorded"),
    "shell.opaque_reference": M("{term:opaque_reference}", "{term:opaque_reference}"),
    "shell.raw_json": M("{term:raw_json}", "{term:raw_json}"),
    "shell.view_raw_json": M("查看原始 JSON", "View raw JSON"),
    "shell.events_raw_json": M("事件与原始 JSON", "Events & raw JSON"),
    "shell.close_panels": M("关闭面板", "Close panels"),
    "shell.close": M("关闭", "Close"),
    "shell.raw_json_aria": M(
        "原始 ManagerReadModel v0 JSON", "Raw ManagerReadModel v0 JSON"
    ),
    "shell.shared_shell": M("共享外壳 · 样例数据驱动", "Shared shell · fixture-backed"),
    "shell.page_intro": M(
        "本页面仅提供方向与溯源信息；领域页面通过公开读模型钩子接入。",
        "This slice provides orientation and provenance only; domain pages attach through the public read-model hook.",
    ),
    "shell.view": M("视图", "View"),
    "shell.fixture": M("样例数据", "Fixture"),
    "shell.observed": M("截至时间", "Observed"),
    "shell.integration_ready": M("集成点已就绪", "Integration point ready"),
    "shell.placeholder_intro": M(
        "此占位内容不会推断属主事实。未来视图可使用相同的 {schema} 信封，并保留此外壳、详情面板和事件抽屉。",
        "This placeholder deliberately does not infer owner facts. A future view can consume the same {schema} envelope and keep this shell, inspector, and event drawer.",
    ),
    "shell.hook": M("钩子：{hook}", "hook: {hook}"),
    "shell.snapshot_missing": M("无快照令牌", "No snapshot token"),
    "shell.unavailable": M("不可用", "Unavailable"),
    "shell.language": M("语言", "Language"),
    "shell.language_zh": M("中文", "中文"),
    "shell.language_en": M("English", "English"),
    "shell.reader_mode_aria": M("阅读模式切换", "Reader modes"),
    "shell.reader_mode_reader": M("阅读模式", "Reader"),
    "shell.reader_mode_expert": M("专业模式", "Expert"),
    "shell.reader_mode_raw": M("原始模式", "Raw"),
    "shell.sample_data_banner": M("样例数据，不代表真实研究结果", "Sample data; not a real research result."),
}
