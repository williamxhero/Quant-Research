"""Small, dependency-free browser assets for the Manager GUI shell."""

# CSS and JavaScript are kept inline so the wheel remains dependency-free and
# the fixture server needs no static-file path or package-data configuration.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Mapping

from .i18n import Translator

CSS = r"""
:root {
  color-scheme: light;
  --ink: #19252f;
  --muted: #62717a;
  --line: #d8e0df;
  --paper: #f5f7f4;
  --surface: #ffffff;
  --surface-alt: #edf2ef;
  --accent: #087f8c;
  --accent-soft: #d8f0ef;
  --positive: #27745b;
  --positive-soft: #e1f1e9;
  --warning: #956514;
  --warning-soft: #fff2d7;
  --danger: #a33f44;
  --danger-soft: #fbe7e6;
  --shadow: 0 18px 42px rgb(28 48 52 / 8%);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
}

:lang(zh-CN) {
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", Inter, ui-sans-serif,
    system-ui, sans-serif;
}

:lang(zh-CN) .eyebrow,
:lang(zh-CN) .status-label,
:lang(zh-CN) .display-state,
:lang(zh-CN) .panel-kicker,
:lang(zh-CN) .nav-short,
:lang(zh-CN) .page-title,
:lang(zh-CN) .panel-heading h2 {
  letter-spacing: normal;
  text-transform: none;
}

* { box-sizing: border-box; }
html { background: var(--paper); }
body { margin: 0; min-width: 280px; color: var(--ink); background: var(--paper); }
button, input { font: inherit; }
button, a { -webkit-tap-highlight-color: transparent; }
a { color: inherit; }
:focus-visible { outline: 3px solid #f2a65a; outline-offset: 3px; }
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}

.skip-link {
  position: fixed; z-index: 10; top: 10px; left: 10px; transform: translateY(-150%);
  padding: 9px 12px; color: white; background: var(--ink); border-radius: 5px;
}
.skip-link:focus { transform: translateY(0); }

.app-shell { display: grid; grid-template-rows: auto auto 1fr; min-height: 100vh; }
.professional-navigation > summary { padding: 10px 28px; cursor: pointer; }
.reading-task-link { padding: 10px 12px; text-decoration: none; overflow-wrap: anywhere; }
.reading-task-link[aria-current="true"] { font-weight: 700; background: var(--accent-soft); }
.reading-navigation { flex-wrap: wrap; }
.topbar {
  display: flex; align-items: center; gap: 24px; padding: 14px 28px; color: white;
  background: #18343a; box-shadow: 0 1px 0 rgb(255 255 255 / 10%);
}
.brand { display: flex; flex: 0 0 auto; align-items: center; gap: 10px; text-decoration: none; }
.brand-mark {
  display: grid; width: 29px; height: 29px; place-items: center; color: #18343a;
  font-size: 12px; font-weight: 800; background: #f2a65a; border-radius: 50%;
}
.brand-name { font-size: 16px; font-weight: 700; letter-spacing: .05em; }
.topbar-meta { display: flex; flex: 1; align-items: center; gap: 11px; min-width: 0; }
.workspace-note { overflow: hidden; color: #bdd0cf; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.read-only-badge {
  display: inline-flex; flex: 0 0 auto; align-items: center; gap: 6px; padding: 5px 9px;
  color: #18343a; font-size: 11px; font-weight: 800; letter-spacing: .08em;
  background: #f2a65a; border-radius: 4px;
}
.read-only-badge::before { width: 6px; height: 6px; content: ""; background: #18343a; border-radius: 50%; }
:lang(zh-CN) .read-only-badge { letter-spacing: normal; text-transform: none; }
.reader-mode-switch { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 4px; }
.reader-mode-link {
  padding: 5px 7px; color: #c8d9d7; font-size: 11px; text-decoration: none;
  border: 1px solid transparent; border-radius: 4px;
}
.reader-mode-link:hover, .reader-mode-link[aria-current="page"], .reader-mode-link[aria-current="true"] {
  color: #18343a; background: #f2a65a; border-color: #f2a65a;
}
.material-reading { min-width: 0; overflow-wrap: anywhere; }
.material-reading pre { white-space: pre-wrap; overflow-wrap: anywhere; max-width: 100%; }
.plain-result article { margin: 20px 0; padding: 22px; background: var(--surface); border: 1px solid var(--line); overflow-wrap: anywhere; }
.plain-result p, .plain-result dd { font-size: 16px; line-height: 1.7; }
.plain-definition { color: var(--ink); background: var(--positive-soft); border-left: 3px solid var(--positive); padding: 12px 15px; }
.plain-definition strong { display: block; color: var(--positive); margin-bottom: 4px; }
.plain-outcome { font-weight: 650; }
.plain-result dl { display: grid; gap: 12px; }
.plain-result dl > div { padding-bottom: 8px; border-bottom: 1px solid var(--line); }
.plain-result dt { font-weight: 650; }
.plain-result dd { margin: 4px 0 0; }
.source-support { margin: 20px 0; padding: 20px; background: var(--surface); border: 1px solid var(--line); overflow-wrap: anywhere; scroll-margin-top: 20px; }
.source-support p, .source-support a { font-size: 16px; line-height: 1.7; }
.source-support pre { white-space: pre-wrap; overflow-wrap: anywhere; max-width: 100%; }
.support-impact { border-left: 3px solid var(--warning); padding: 10px 14px; background: var(--warning-soft); }
.reader-sample-banner {
  margin: 0 0 18px; padding: 11px 14px; color: #6b4a0b; font-size: 13px;
  background: var(--warning-soft); border: 1px solid #e7c979; border-radius: 4px;
}
.search-form { display: flex; flex: 0 1 280px; min-width: 150px; }
.search-input {
  width: 100%; padding: 9px 12px; color: white; background: #24474d;
  border: 1px solid #4c6c70; border-radius: 5px;
}
.search-input::placeholder { color: #b4c7c5; }

.nav-strip {
  display: flex; gap: 4px; overflow-x: auto; padding: 10px 28px 0; background: var(--surface);
  border-bottom: 1px solid var(--line); scrollbar-width: thin;
}
.nav-link {
  display: inline-flex; flex: 0 0 auto; align-items: center; gap: 8px; min-height: 42px;
  padding: 0 13px; color: var(--muted); font-size: 13px; font-weight: 650; text-decoration: none;
  border-bottom: 3px solid transparent; transition: color .16s ease, border-color .16s ease;
}
.nav-link:hover, .nav-link[aria-current="page"] { color: var(--ink); border-bottom-color: var(--accent); }
.nav-short { display: none; color: var(--accent); font-size: 10px; letter-spacing: .08em; }

.workspace {
  display: grid; grid-template-columns: minmax(0, 1fr) 290px; align-items: start; gap: 22px;
  width: min(1500px, 100%); margin: 0 auto; padding: 30px 28px 130px;
}
.main-column { min-width: 0; }
.eyebrow {
  margin: 0 0 8px; color: var(--accent); font-size: 11px; font-weight: 800;
  letter-spacing: .13em; text-transform: uppercase;
}
.page-title { margin: 0; font-size: clamp(28px, 4vw, 46px); letter-spacing: -.045em; line-height: 1.04; }
.page-intro { max-width: 720px; margin: 12px 0 24px; color: var(--muted); font-size: 15px; line-height: 1.55; }
.context-line { display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 0 0 22px; color: var(--muted); font-size: 12px; }
.context-line strong { color: var(--ink); font-weight: 700; }

.status-block {
  position: relative; margin: 0 0 18px; padding: 20px 22px; background: var(--surface);
  border: 1px solid var(--line); border-left: 4px solid var(--accent); box-shadow: var(--shadow);
}
.status-line { display: flex; align-items: center; gap: 9px; margin-bottom: 12px; }
.status-mark { width: 9px; height: 9px; background: var(--accent); border-radius: 50%; }
.status-label { font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.display-state {
  margin-left: auto; padding: 3px 7px; color: var(--muted); font-size: 10px; font-weight: 750;
  letter-spacing: .08em; text-transform: uppercase; background: var(--surface-alt); border-radius: 3px;
}
.status-block h2 { max-width: 720px; margin: 0 0 7px; font-size: 18px; letter-spacing: -.02em; line-height: 1.35; }
.status-block p { max-width: 760px; margin: 0; color: var(--muted); font-size: 13px; line-height: 1.5; }
.status-source-note { margin-top: 12px !important; }
.status-source-note strong { color: var(--ink); }
.status-errors { margin: 14px 0 0; padding: 12px 12px 12px 28px; color: var(--danger); font-size: 12px;
  background: var(--danger-soft); border-radius: 4px; line-height: 1.55; }
.tone-positive { border-left-color: var(--positive); }
.tone-positive .status-mark { background: var(--positive); }
.tone-accent { border-left-color: var(--accent); }
.tone-warning { border-left-color: var(--warning); }
.tone-warning .status-mark { background: var(--warning); }
.tone-warning .display-state { color: var(--warning); background: var(--warning-soft); }
.tone-danger { border-left-color: var(--danger); }
.tone-danger .status-mark { background: var(--danger); }
.tone-danger .display-state { color: var(--danger); background: var(--danger-soft); }
.tone-quiet { border-left-color: #9da9a8; }
.tone-quiet .status-mark { background: #9da9a8; }

.hook-surface { padding: 22px; background: transparent; border: 1px dashed #b9c6c3; }
.hook-surface h2 { margin: 0 0 8px; font-size: 16px; }
.hook-surface p { max-width: 680px; margin: 0; color: var(--muted); font-size: 13px; line-height: 1.55; }
.hook-label { display: inline-block; margin-top: 15px; color: var(--accent); font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px; }

.inspector {
  position: sticky; top: 18px; min-width: 0; padding: 18px; background: var(--surface);
  border: 1px solid var(--line); box-shadow: var(--shadow);
}
.panel-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.panel-heading h2 { margin: 0; font-size: 14px; letter-spacing: .02em; }
.panel-kicker { color: var(--muted); font-size: 10px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
.inspector-list { display: grid; gap: 14px; margin: 0; }
.inspector-item { display: grid; gap: 4px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.inspector-item:last-child { padding-bottom: 0; border-bottom: 0; }
.inspector-item dt { color: var(--muted); font-size: 11px; }
.inspector-item dd { overflow-wrap: anywhere; margin: 0; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
.panel-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.panel-button {
  padding: 8px 10px; color: var(--ink); font-size: 11px; font-weight: 700; background: var(--surface-alt);
  border: 1px solid var(--line); border-radius: 4px; cursor: pointer;
}
.panel-button:hover { border-color: var(--accent); }
.copy-reference {
  display: inline-flex; align-items: center; margin-left: 6px; padding: 3px 6px;
  color: var(--accent); font-size: 10px; font-weight: 700; background: transparent;
  border: 1px solid var(--line); border-radius: 3px; cursor: pointer;
}
.copy-reference:hover { border-color: var(--accent); background: var(--accent-soft); }
.copy-status { min-height: 1.2em; margin: 9px 0 0; color: var(--muted); font-size: 11px; }
.view-mode-controls {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 12px 0;
}
.view-mode-controls [aria-pressed="true"] { color: white; background: var(--accent); border-color: var(--accent); }
[data-view-panel][hidden] { display: none; }
.lineage-graph-scroll, .lineage-table-view > [role="region"] { max-width: 100%; overflow-x: auto; }
.lineage-text-view { overflow-wrap: anywhere; }
.lineage-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.lineage-table th, .lineage-table td { padding: 8px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); }
.lineage-table th { color: var(--muted); font-size: 11px; }

.event-drawer {
  position: fixed; z-index: 5; right: 0; bottom: 0; left: 0; max-height: min(48vh, 430px); padding: 18px 28px;
  overflow: auto; background: #1b2e33; color: #e5efec; border-top: 3px solid var(--accent);
  box-shadow: 0 -12px 32px rgb(28 48 52 / 18%); animation: drawer-in .18s ease-out;
}
.event-drawer[hidden] { display: none; }
.event-drawer .panel-heading { margin-bottom: 10px; }
.event-drawer .panel-heading h2 { color: white; }
.event-drawer .panel-kicker { color: #9db7b4; }
.raw-json { margin: 0; color: #d5e7e2; font: 11px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
.drawer-close { color: #d5e7e2; background: transparent; border-color: #49676b; }

@keyframes drawer-in { from { transform: translateY(15px); opacity: .5; } to { transform: translateY(0); opacity: 1; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; } }
@media (max-width: 860px) {
  .topbar { flex-wrap: wrap; gap: 12px 18px; padding: 13px 18px; }
  .topbar-meta { order: 3; flex-basis: 100%; }
  .search-form { flex-basis: min(360px, 100%); }
  .nav-strip { padding-right: 18px; padding-left: 18px; }
  .workspace { grid-template-columns: 1fr; gap: 18px; padding: 24px 18px 120px; }
  .inspector { position: static; }
  .nav-short { display: inline; }
  .nav-link { padding: 0 10px; }
  .nav-label { display: none; }
  .event-drawer { padding-right: 18px; padding-left: 18px; }
}
@media (max-width: 480px) {
  .topbar-meta { flex-wrap: wrap; }
  .brand-name { font-size: 14px; }
  .workspace-note { max-width: 160px; }
  .status-block { padding: 17px; }
  .status-block h2 { font-size: 16px; }
  .display-state { margin-left: 4px; }
}
"""

JS_TEMPLATE = r"""
(() => {
  const messages = JSON.parse(document.getElementById("gui-messages")?.textContent || "{}");
  const links = [...document.querySelectorAll("[data-nav-link]")];
  const inspector = document.querySelector("#inspector");
  const drawer = document.querySelector("#event-drawer");
  const title = document.querySelector("[data-page-title]");
  const copyStatus = document.querySelector("#copy-status");
  const params = () => new URLSearchParams(window.location.search);
  let lastTrigger = null;

  function updatePanelUrl(panel) {
    const next = params();
    if (panel) next.set("panel", panel);
    else next.delete("panel");
    const query = next.toString();
    window.history.replaceState({}, "", query ? `${window.location.pathname}?${query}` : window.location.pathname);
  }

  // The inspector is the default side panel; only the raw-JSON drawer replaces it.
  function syncPanelButtons(panel) {
    document.querySelectorAll("[data-panel-target]").forEach((button) => {
      const expanded = button.dataset.panelTarget === "events" ? panel === "events" : panel !== "events";
      button.setAttribute("aria-expanded", expanded ? "true" : "false");
    });
  }

  function showPanel(panel, shouldUpdateUrl = true) {
    const inspectorOpen = panel === "inspector" || panel === null;
    const drawerOpen = panel === "events";
    if (inspector) inspector.hidden = !inspectorOpen;
    if (drawer) drawer.hidden = !drawerOpen;
    if (shouldUpdateUrl) updatePanelUrl(panel === "inspector" ? "inspector" : drawerOpen ? "events" : null);
    syncPanelButtons(panel);
    // Closing returns focus to the control that opened the panel, never to <body>.
    const target = drawerOpen ? drawer : inspectorOpen && panel ? inspector : lastTrigger || title;
    if (target && typeof target.focus === "function") target.focus({ preventScroll: true });
  }

  function focusNav(index) {
    if (!links.length) return;
    links[(index + links.length) % links.length].focus();
  }

  links.forEach((link, index) => {
    link.addEventListener("keydown", (event) => {
      if (["Home", "End"].includes(event.key)) {
        event.preventDefault();
        focusNav(event.key === "Home" ? 0 : links.length - 1);
        return;
      }
      if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) return;
      event.preventDefault();
      const direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
      focusNav(index + direction);
    });
  });

  document.querySelectorAll("[data-panel-target]").forEach((button) => {
    button.addEventListener("click", () => {
      lastTrigger = button;
      showPanel(button.dataset.panelTarget);
    });
  });
  document.querySelectorAll("[data-close-panels]").forEach((button) => {
    button.addEventListener("click", () => showPanel(null));
  });

  // The drawer is a non-modal overlay, so Escape closes it without trapping Tab.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawer && !drawer.hidden) {
      event.preventDefault();
      showPanel(null);
    }
  });

  const supportPanels = [...document.querySelectorAll('.source-support')];
  let activeSupport = null;
  let supportTrigger = null;
  supportPanels.forEach(panel => { panel.hidden = true; });
  function closeSupport() {
    if (!activeSupport) return;
    activeSupport.hidden = true;
    activeSupport = null;
    if (supportTrigger && document.contains(supportTrigger)) {
      supportTrigger.setAttribute('aria-expanded', 'false');
      supportTrigger.focus();
    }
  }
  document.querySelectorAll('[data-source-support]').forEach(link => {
    link.setAttribute('aria-expanded', 'false');
    link.addEventListener('click', event => {
      const panel = document.getElementById(link.dataset.sourceSupport);
      if (!panel) return;
      event.preventDefault();
      closeSupport();
      supportTrigger = link;
      activeSupport = panel;
      panel.hidden = false;
      link.setAttribute('aria-expanded', 'true');
      panel.focus();
      panel.scrollIntoView({ block: 'start' });
    });
  });
  document.querySelectorAll('[data-support-close]').forEach(link => {
    link.addEventListener('click', event => {
      event.preventDefault();
      closeSupport();
    });
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && activeSupport) {
      event.preventDefault();
      closeSupport();
    }
  });

  async function copyValue(value) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    const area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    if (!copied) throw new Error();
  }

  function announce(key) {
    if (copyStatus) copyStatus.textContent = messages[key] || "";
  }

  document.querySelectorAll("[data-copy-value]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await copyValue(button.dataset.copyValue || "");
        announce("copy_success");
      } catch (error) {
        announce("copy_unavailable");
      }
    });
  });

  // Every alternative-view root owns its controls, so a page may render several
  // graph/table pairs (for example one per failure) without sharing identifiers.
  function setViewMode(root, mode, shouldUpdateUrl = true) {
    const selected = mode === "graph" ? "graph" : "table";
    root.dataset.viewMode = selected;
    root.querySelectorAll(":scope > .view-mode-controls [data-view-mode]").forEach((button) => {
      button.setAttribute("aria-pressed", button.dataset.viewMode === selected ? "true" : "false");
    });
    root.querySelectorAll(":scope > [data-view-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.viewPanel !== selected;
    });
    if (shouldUpdateUrl) {
      const next = params();
      next.set("presentation", selected);
      window.history.replaceState({}, "", `${window.location.pathname}?${next.toString()}`);
      document.querySelectorAll("[data-alternative-view]").forEach((other) => {
        if (other !== root) setViewMode(other, selected, false);
      });
    }
  }

  document.querySelectorAll("[data-alternative-view]").forEach((root) => {
    root.querySelectorAll(":scope > .view-mode-controls [data-view-mode]").forEach((button) => {
      button.addEventListener("click", () => setViewMode(root, button.dataset.viewMode));
    });
  });
  const requestedPresentation = params().get("presentation");
  if (requestedPresentation) {
    document.querySelectorAll("[data-alternative-view]").forEach((root) => {
      setViewMode(root, requestedPresentation, false);
    });
  }

  document.querySelectorAll("[data-export-current-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const payload = button.dataset.exportPayload;
      if (!payload) {
        announce("export_unavailable");
        return;
      }
      try {
        const blob = new Blob([payload], { type: "application/json;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = button.dataset.exportFilename || "manager-gui-current-view.json";
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(link.href), 0);
        announce("export_success");
      } catch (error) {
        announce("export_unavailable");
      }
    });
  });

  const requestedPanel = params().get("panel");
  if (requestedPanel === "events" || requestedPanel === "inspector") {
    showPanel(requestedPanel, false);
  } else {
    syncPanelButtons(null);
    if (title) title.focus({ preventScroll: true });
  }
})();
"""

JS_MESSAGE_KEYS = (
    "copy_success",
    "copy_unavailable",
    "export_success",
    "export_unavailable",
)
_JS_MESSAGE_CATALOG = {
    "copy_success": "client.copy_success",
    "copy_unavailable": "client.copy_unavailable",
    "export_success": "client.export_success",
    "export_unavailable": "client.export_unavailable",
}


def js_messages(translator: Translator) -> dict[str, str]:
    """Return the explicit client-message map for one request locale."""

    return {name: translator.t(_JS_MESSAGE_CATALOG[name]) for name in JS_MESSAGE_KEYS}


def render_js(
    messages: Mapping[str, str] | None = None, *, translator: Translator | None = None
) -> str:
    """Return static JS, or its safe per-request message/data script pair.

    With no arguments this returns the executable source used by ``JS``.  Passing
    a translator or explicit message map returns two script elements: an inert
    JSON data element followed by that unchanged executable source.  Keeping the
    data out of executable JS means user-facing copy never becomes a JS literal.
    """

    if messages is None and translator is None:
        return JS_TEMPLATE
    if messages is not None and translator is not None:
        raise TypeError("pass messages or translator, not both")
    selected = js_messages(translator) if translator is not None else dict(messages or {})
    payload = json.dumps(selected, ensure_ascii=False, separators=(",", ":"))
    payload = (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace(chr(0x2028), "\\u2028")
        .replace(chr(0x2029), "\\u2029")
    )
    return (
        '<script type="application/json" id="gui-messages">'
        f"{payload}</script>"
        f"<script>{JS_TEMPLATE}</script>"
    )


# Keep the current shell contract static and safe; a locale-aware shell can use
# ``render_js(translator=...)`` without changing the JavaScript source.
JS = render_js()

__all__ = ["CSS", "JS", "JS_MESSAGE_KEYS", "js_messages", "render_js"]
