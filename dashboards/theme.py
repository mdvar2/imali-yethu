"""Visual layer for the Imali Yethu dashboard: app shell, styles and HTML components.

All dynamic text is escaped: invoice content is untrusted input.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

import streamlit as st

from dashboards import core

ASSETS = Path(__file__).resolve().parent / "assets"

TONE_HEX = {
    "ok": "#1E7B4F",
    "bad": "#B42318",
    "warn": "#B54708",
    "info": "#1D5FA7",
    "muted": "#5B6673",
    "brand": "#00594C",
}

STEP_GLYPH = {"pass": "✓", "fail": "✕", "skip": "!", "na": "–"}
STEP_TEXT = {"pass": "Passed", "fail": "Failed", "skip": "Bypassed", "na": "Not reached"}

# 20x20 stroke icons for KPI cards
_ICONS = {
    "paid": '<path d="M4 10.5l4 4 8-9"/>',
    "shield": '<path d="M10 2.5l6 2.5v4.5c0 4-2.6 6.9-6 8-3.4-1.1-6-4-6-8V5z"/><path d="M7.5 10l2 2 3-3.5"/>',
    "doc": '<path d="M5 2.5h7l3 3v12H5z"/><path d="M8 9h5M8 12h5M8 15h3"/>',
    "alert": '<path d="M10 3l8 14H2z"/><path d="M10 8v4M10 14.5v.5"/>',
    "count": '<path d="M3 16h14M5 13V9M10 13V5M15 13v-6"/>',
}

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --iy-ink: #101828;
  --iy-ink-2: #344054;
  --iy-muted: #667085;
  --iy-line: #E4E7EC;
  --iy-surface: #FFFFFF;
  --iy-bg: #F5F7F9;
  --iy-brand: #00594C;
  --iy-side: #0A2925;
  --iy-gold: #C99A2E;
  --iy-ok: #1E7B4F;   --iy-ok-bg: #E7F5EE;
  --iy-bad: #B42318;  --iy-bad-bg: #FEECEB;
  --iy-warn: #B54708; --iy-warn-bg: #FEF4E6;
  --iy-info: #1D5FA7; --iy-info-bg: #EAF1FB;
  --iy-mute: #5B6673; --iy-mute-bg: #EFF1F4;
  --iy-shadow: 0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.04);
}

html { font-size: 15px; }
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp button, .stApp textarea {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
.stApp { background: var(--iy-bg); }

/* ---------- Streamlit chrome ---------- */
[data-testid="stHeader"] { background: transparent; pointer-events: none; }
[data-testid="stHeader"] * { pointer-events: auto; }
[data-testid="stDecoration"], [data-testid="stToolbarActions"], [data-testid="stMainMenu"], #MainMenu,
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stExpandSidebarButton"] { background: var(--iy-surface); border: 1px solid var(--iy-line);
  border-radius: 8px; box-shadow: var(--iy-shadow); }
[data-testid="stMainBlockContainer"], .block-container {
  max-width: 100%; padding: 0 2rem 1.5rem;
}
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--iy-surface); border-radius: 10px; box-shadow: var(--iy-shadow);
}
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; color: var(--iy-ink); }
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--iy-line); }
.stTabs [data-baseweb="tab"] { padding: 8px 12px; font-weight: 500; }

/* ---------- Sidebar (dark app navigation) ---------- */
[data-testid="stSidebar"] { background: var(--iy-side); border-right: 0; }
[data-testid="stSidebar"] > div:first-child { background: var(--iy-side); }
[data-testid="stSidebarHeader"] { padding-top: 1.1rem; padding-bottom: .6rem; }
[data-testid="stSidebar"] [data-testid="stLogo"] { height: 2.1rem; max-width: 100%; }
[data-testid="stSidebar"], [data-testid="stSidebar"] p, [data-testid="stSidebar"] span,
[data-testid="stSidebar"] label, [data-testid="stSidebar"] small { color: #C9D8D4; }
[data-testid="stSidebar"] svg { color: #9FB8B2; fill: currentColor; }
[data-testid="stNavSectionHeader"], [data-testid="stNavSectionHeader"] * {
  color: #7FA39B !important; font-size: .7rem !important; font-weight: 600 !important;
  letter-spacing: .08em; text-transform: uppercase;
}
[data-testid="stSidebarNavLink"] { border-radius: 6px; margin: 1px 0; padding: 6px 10px; }
[data-testid="stSidebarNavLink"]:hover { background: rgba(255,255,255,.06); }
[data-testid="stSidebarNavLink"] span { color: #C9D8D4 !important; font-weight: 500; }
[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: rgba(255,255,255,.10); box-shadow: inset 3px 0 0 var(--iy-gold);
}
[data-testid="stSidebarNavLink"][aria-current="page"] span { color: #FFFFFF !important; font-weight: 600; }
[data-testid="stSidebarNavSeparator"] { border-color: rgba(255,255,255,.08); }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.08); }
[data-testid="stSidebar"] .stButton button {
  background: transparent; border: 1px solid rgba(255,255,255,.18); color: #E6EFEC;
}
[data-testid="stSidebar"] .stButton button:hover { background: rgba(255,255,255,.06); border-color: rgba(255,255,255,.3); }
[data-testid="stSidebar"] .stButton button * { color: #E6EFEC !important; }

/* ---------- Top bar ---------- */
.iy-topbar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  margin: 0 -2rem 1.4rem; padding: .7rem 2rem; min-height: 56px;
  background: var(--iy-surface); border-bottom: 1px solid var(--iy-line);
}
.iy-crumbs { display: flex; align-items: center; gap: 8px; font-size: .86rem; color: var(--iy-muted); }
.iy-crumbs i { font-style: normal; color: #C0C6CF; }
.iy-crumbs b { color: var(--iy-ink); font-weight: 600; }
.iy-top-right { display: flex; align-items: center; gap: 14px; font-size: .84rem; color: var(--iy-ink-2); }
.iy-chip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--iy-line); border-radius: 999px;
  padding: 3px 10px; font-weight: 500; font-size: .78rem; color: var(--iy-ink-2); background: #FAFBFC; }
.iy-chip::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--iy-info); }
.iy-user { display: inline-flex; align-items: center; gap: 8px; font-weight: 500; }
.iy-avatar { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center;
  background: var(--iy-brand); color: #fff; font-size: .7rem; font-weight: 700; letter-spacing: .02em; }
.iy-sep { width: 1px; height: 20px; background: var(--iy-line); }

/* ---------- Page heading ---------- */
.stApp h1.iy-title { font-size: 1.45rem; font-weight: 700; color: var(--iy-ink); margin: 0; padding: 0;
  line-height: 1.3; letter-spacing: -.01em; }
.iy-sub { color: var(--iy-muted); font-size: .92rem; margin: 4px 0 1.1rem; max-width: 820px; line-height: 1.5; }

/* ---------- Card section header ---------- */
.iy-sec-title { font-size: .95rem; font-weight: 600; color: var(--iy-ink); margin: 0; }
.iy-sec-sub { font-size: .82rem; color: var(--iy-muted); margin: 2px 0 10px; line-height: 1.4; }

/* ---------- KPI cards ---------- */
.iy-kpi { background: var(--iy-surface); border: 1px solid var(--iy-line); border-radius: 10px;
  padding: 14px 16px; box-shadow: var(--iy-shadow); height: 100%; }
.iy-kpi-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.iy-kpi-label { font-size: .82rem; font-weight: 500; color: var(--iy-muted); }
.iy-kpi-icon { width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center; flex: none; }
.iy-kpi-icon svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.8;
  stroke-linecap: round; stroke-linejoin: round; }
.iy-kpi-icon.ok { background: var(--iy-ok-bg); color: var(--iy-ok); }
.iy-kpi-icon.bad { background: var(--iy-bad-bg); color: var(--iy-bad); }
.iy-kpi-icon.warn { background: var(--iy-warn-bg); color: var(--iy-warn); }
.iy-kpi-icon.info { background: var(--iy-info-bg); color: var(--iy-info); }
.iy-kpi-value { font-size: 1.55rem; font-weight: 700; color: var(--iy-ink); margin: 6px 0 2px; line-height: 1.2;
  font-variant-numeric: tabular-nums; letter-spacing: -.01em; overflow-wrap: anywhere; }
.iy-kpi-note { font-size: .8rem; color: var(--iy-muted); }

/* ---------- Status pills ---------- */
.iy-pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px; border-radius: 999px;
  font-size: .76rem; font-weight: 600; white-space: nowrap; line-height: 1.6; }
.iy-pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.iy-pill.ok { color: var(--iy-ok); background: var(--iy-ok-bg); }
.iy-pill.bad { color: var(--iy-bad); background: var(--iy-bad-bg); }
.iy-pill.warn { color: var(--iy-warn); background: var(--iy-warn-bg); }
.iy-pill.info { color: var(--iy-info); background: var(--iy-info-bg); }
.iy-pill.muted { color: var(--iy-mute); background: var(--iy-mute-bg); }

/* ---------- Activity table ---------- */
.iy-table { width: 100%; border-collapse: collapse; font-size: .86rem; }
.iy-table th { text-align: left; font-size: .74rem; font-weight: 600; color: var(--iy-muted); text-transform: uppercase;
  letter-spacing: .05em; padding: 8px 10px; background: #F9FAFB; border-bottom: 1px solid var(--iy-line); }
.iy-table td { padding: 10px; border-bottom: 1px solid var(--iy-line); color: var(--iy-ink-2); vertical-align: middle; }
.iy-table tr:last-child td { border-bottom: 0; }
.iy-table tr:hover td { background: #FAFBFC; }
.iy-table .num { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; color: var(--iy-ink); white-space: nowrap; }
.iy-table .strong { font-weight: 600; color: var(--iy-ink); white-space: nowrap; }
.iy-table .reason { color: var(--iy-muted); max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.iy-table .nowrap { white-space: nowrap; }
.iy-table-wrap { overflow-x: auto; border: 1px solid var(--iy-line); border-radius: 8px; }

/* ---------- Decision trail ---------- */
.iy-trail { list-style: none; margin: 4px 0 0; padding: 0; }
.iy-step { display: flex; gap: 12px; position: relative; padding-bottom: 14px; }
.iy-step:not(:last-child)::after { content: ""; position: absolute; left: 12px; top: 26px; bottom: 2px;
  width: 2px; background: var(--iy-line); }
.iy-dot { flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center;
  font-weight: 700; font-size: .8rem; }
.iy-step.pass .iy-dot { background: var(--iy-ok-bg); color: var(--iy-ok); }
.iy-step.fail .iy-dot { background: var(--iy-bad-bg); color: var(--iy-bad); }
.iy-step.skip .iy-dot { background: var(--iy-warn-bg); color: var(--iy-warn); }
.iy-step.na .iy-dot { background: var(--iy-mute-bg); color: var(--iy-mute); }
.iy-step-title { font-weight: 600; color: var(--iy-ink); font-size: .88rem; line-height: 26px; }
.iy-step-state { font-weight: 500; color: var(--iy-muted); font-size: .76rem; margin-left: 6px; }
.iy-step-detail { color: var(--iy-ink-2); font-size: .84rem; overflow-wrap: anywhere; }

/* ---------- Sidebar status ---------- */
.iy-side-title { font-size: .7rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  color: #7FA39B; margin: 2px 0 6px; }
.iy-side-line { display: flex; justify-content: space-between; align-items: center; gap: 8px;
  font-size: .84rem; padding: 4px 0; }

/* ---------- Notes, empty states, verdicts ---------- */
.iy-note { border: 1px solid #C9DAF3; background: var(--iy-info-bg); color: var(--iy-ink-2);
  padding: 9px 12px; border-radius: 8px; font-size: .85rem; margin: 4px 0 12px; }
.iy-note.warn { border-color: #F6D9AE; background: var(--iy-warn-bg); }
.iy-empty { text-align: center; padding: 28px 16px; color: var(--iy-muted); font-size: .88rem; }
.iy-empty b { display: block; color: var(--iy-ink); font-size: .95rem; margin-bottom: 4px; }
.iy-empty code { background: var(--iy-mute-bg); padding: 2px 6px; border-radius: 4px; }
.iy-verdict { display: flex; gap: 12px; align-items: center; border-radius: 8px; padding: 12px 14px;
  font-weight: 600; margin: 4px 0 12px; font-size: .92rem; }
.iy-verdict.ok { background: var(--iy-ok-bg); color: var(--iy-ok); }
.iy-verdict.bad { background: var(--iy-bad-bg); color: var(--iy-bad); }
.iy-verdict span { color: var(--iy-ink-2); font-weight: 400; font-size: .85rem; }

/* ---------- Footer ---------- */
.iy-footer { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-top: 2rem;
  padding-top: 1rem; border-top: 1px solid var(--iy-line); font-size: .78rem; color: var(--iy-muted); }

/* ---------- Small screens ---------- */
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"], .block-container { padding: 0 1rem 1rem; }
  .iy-topbar { margin: 0 -1rem 1rem; padding: 3.2rem 1rem .7rem; }
  .iy-top-right .iy-date, .iy-sep { display: none; }
  .iy-kpi { margin-bottom: 8px; height: auto; }
}
</style>
"""


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def inject_css() -> None:
    _html(_CSS)


def logo() -> None:
    st.logo(str(ASSETS / "logo.svg"), icon_image=str(ASSETS / "icon.svg"), size="large")


def page_header(title: str, subtitle: str = "", section: str = "", audience: str | None = None) -> None:
    """Top bar (breadcrumb, network, date, viewer) followed by the page heading."""
    if audience is None:
        from dashboards import auth

        audience = auth.role_label()
    crumbs = "".join(f"<span>{escape(c)}</span><i>/</i>" for c in ("Imali Yethu", section) if c)
    initials = "".join(w[0] for w in audience.split()[:2]).upper()
    today = datetime.now(core.SAST).strftime("%a, %d %b %Y")
    _html(
        '<div class="iy-topbar">'
        f'<nav class="iy-crumbs" aria-label="Breadcrumb">{crumbs}<b>{escape(title)}</b></nav>'
        '<div class="iy-top-right"><span class="iy-chip">XRPL Testnet</span>'
        f'<span class="iy-date">{escape(today)}</span><span class="iy-sep"></span>'
        f'<span class="iy-user"><span class="iy-avatar" aria-hidden="true">{escape(initials)}</span>'
        f'{escape(audience)}</span></div></div>'
    )
    sub = f'<p class="iy-sub">{escape(subtitle)}</p>' if subtitle else ""
    _html(f'<h1 class="iy-title">{escape(title)}</h1>{sub}')


def section(title: str, subtitle: str = "") -> None:
    sub = f'<div class="iy-sec-sub">{escape(subtitle)}</div>' if subtitle else ""
    _html(f'<div class="iy-sec-title">{escape(title)}</div>{sub}')


def kpi_row(cards: list[tuple[str, str, str, str, str]]) -> None:
    """cards: (label, value, note, tone, icon)"""
    for col, (label, value, note, tone, icon) in zip(st.columns(len(cards)), cards):
        with col:
            svg = f'<svg viewBox="0 0 20 20" aria-hidden="true">{_ICONS.get(icon, "")}</svg>'
            _html(
                f'<div class="iy-kpi"><div class="iy-kpi-head"><span class="iy-kpi-label">{escape(label)}</span>'
                f'<span class="iy-kpi-icon {escape(tone)}">{svg}</span></div>'
                f'<div class="iy-kpi-value">{escape(value)}</div>'
                f'<div class="iy-kpi-note">{escape(note)}</div></div>'
            )


def pill(status_code: str | None) -> str:
    s = core.status_of(status_code)
    return f'<span class="iy-pill {s.tone}">{escape(s.label)}</span>'


def pill_text(label: str, tone: str) -> str:
    return f'<span class="iy-pill {escape(tone)}">{escape(label)}</span>'


def activity_table(records: list[dict], suppliers: dict[str, str]) -> None:
    rows = []
    for r in records:
        reasons = r.get("reasons") or []
        detail = reasons[0] if reasons else core.status_of(r.get("status")).description
        rows.append(
            f'<tr><td class="strong">{escape(r.get("invoice_number") or "-")}</td>'
            f'<td class="nowrap">{escape(core.supplier_name(r, suppliers))}</td>'
            f'<td class="reason" title="{escape(detail)}">{escape(detail)}</td>'
            f'<td class="nowrap">{escape(core.fmt_time(r.get("timestamp")))}</td>'
            f'<td class="num">{escape(core.fmt_zar(core.amount(r)))}</td>'
            f'<td>{pill(r.get("status"))}</td></tr>'
        )
    _html(
        '<div class="iy-table-wrap"><table class="iy-table"><thead><tr><th>Invoice</th><th>Supplier</th>'
        '<th>Detail</th><th>Date (SAST)</th><th style="text-align:right">Amount</th><th>Status</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def trail(steps: list[tuple[str, str, str]]) -> None:
    items = "".join(
        f'<li class="iy-step {state}"><span class="iy-dot" aria-hidden="true">{STEP_GLYPH[state]}</span>'
        f'<div><div class="iy-step-title">{escape(title)}'
        f'<span class="iy-step-state">{STEP_TEXT[state]}</span></div>'
        + (f'<div class="iy-step-detail">{escape(detail)}</div>' if detail else "") + '</div></li>'
        for title, state, detail in steps
    )
    _html(f'<ol class="iy-trail">{items}</ol>')


def checklist(items: list[tuple[str, str]]) -> None:
    trail([(label, state, "") for label, state in items])


def verdict(passed: bool, headline: str, detail: str) -> None:
    tone, glyph = ("ok", "✓") if passed else ("bad", "✕")
    _html(f'<div class="iy-verdict {tone}"><b aria-hidden="true">{glyph}</b>'
          f'<div>{escape(headline)}<br><span>{escape(detail)}</span></div></div>')


def note(text: str, tone: str = "") -> None:
    _html(f'<div class="iy-note {escape(tone)}">{escape(text)}</div>')


def empty_state(title: str, body: str, command: str = "") -> None:
    cmd = f'<p><code>{escape(command)}</code></p>' if command else ""
    _html(f'<div class="iy-empty"><b>{escape(title)}</b>{escape(body)}{cmd}</div>')


def sidebar_status(lines: list[tuple[str, str, str]]) -> None:
    """lines: (label, value, tone)"""
    body = "".join(
        f'<div class="iy-side-line"><span>{escape(label)}</span>{pill_text(value, tone)}</div>'
        for label, value, tone in lines
    )
    _html(f'<div class="iy-side-title">System status</div>{body}')


def footer() -> None:
    now = datetime.now(core.SAST).strftime("%H:%M")
    _html(
        '<div class="iy-footer"><span>Imali Yethu · Municipal Payment Integrity System · Pilot on XRPL Testnet</span>'
        f'<span>Data as at {now} SAST · Amounts in South African rand</span></div>'
    )
