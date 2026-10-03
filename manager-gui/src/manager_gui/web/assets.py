"""Small, dependency-free browser assets for the Manager GUI shell."""

# CSS and JavaScript are kept inline so the wheel remains dependency-free and
# the fixture server needs no static-file path or package-data configuration.
# ruff: noqa: E501

from __future__ import annotations

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
  .brand-name { font-size: 14px; }
  .workspace-note { max-width: 160px; }
  .status-block { padding: 17px; }
  .status-block h2 { font-size: 16px; }
  .display-state { margin-left: 4px; }
}
"""

JS = r"""
(() => {
  const links = [...document.querySelectorAll("[data-nav-link]")];
  const inspector = document.querySelector("#inspector");
  const drawer = document.querySelector("#event-drawer");
  const title = document.querySelector("[data-page-title]");
  const params = () => new URLSearchParams(window.location.search);

  function updatePanelUrl(panel) {
    const next = params();
    if (panel) next.set("panel", panel);
    else next.delete("panel");
    const query = next.toString();
    window.history.replaceState({}, "", query ? `${window.location.pathname}?${query}` : window.location.pathname);
  }

  function showPanel(panel, shouldUpdateUrl = true) {
    const inspectorOpen = panel === "inspector" || panel === null;
    const drawerOpen = panel === "events";
    if (inspector) inspector.hidden = !inspectorOpen;
    if (drawer) drawer.hidden = !drawerOpen;
    if (shouldUpdateUrl) updatePanelUrl(panel === "inspector" ? "inspector" : drawerOpen ? "events" : null);
    const target = drawerOpen ? drawer : inspectorOpen ? inspector : title;
    if (target) target.focus({ preventScroll: true });
  }

  links.forEach((link, index) => {
    link.addEventListener("keydown", (event) => {
      if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) return;
      event.preventDefault();
      const direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
      links[(index + direction + links.length) % links.length].focus();
    });
  });

  document.querySelectorAll("[data-panel-target]").forEach((button) => {
    button.addEventListener("click", () => showPanel(button.dataset.panelTarget));
  });
  document.querySelectorAll("[data-close-panels]").forEach((button) => {
    button.addEventListener("click", () => showPanel(null));
  });

  const requestedPanel = params().get("panel");
  if (requestedPanel === "events" || requestedPanel === "inspector") {
    showPanel(requestedPanel, false);
  } else if (title) {
    title.focus({ preventScroll: true });
  }
})();
"""

__all__ = ["CSS", "JS"]
