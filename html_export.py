"""
html_export.py
--------------
ประกอบเนื้อหาที่ theme.py จดไว้ (กราฟ Plotly / HTML การ์ด-ตาราง / คำอธิบาย)
เป็นไฟล์ HTML ไฟล์เดียว ฝัง plotly.js ไว้ในไฟล์ จึงเปิดออฟไลน์ได้
"""
import re
from html import escape as esc

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from theme import THEME_CSS

_SPACER = re.compile(r"^\s*<div style=['\"]height:[^'\"]*['\"]></div>\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")

EXPORT_CSS = """
<style>
body { margin: 0; font-family: 'Noto Sans Thai', 'IBM Plex Sans Thai', sans-serif; color: #1E293B; }
.ex-wrap { max-width: 1280px; margin: 0 auto; padding: 1.6rem 1.2rem 3rem; }
.ex-wrap h1, .ex-wrap h2, .ex-wrap h3, .ex-wrap h4 { color: #0F172A; margin: 22px 0 4px; }
.ex-wrap h4 { font-size: 17px; font-weight: 700; }
.ex-wrap p { margin: 4px 0; }
.ex-cap { font-size: 12.5px; color: #64748B; margin: 2px 0 8px; }
.ex-chart { background: #fff; border: 1px solid #F4D8DE; border-radius: 18px; padding: 10px 12px; margin: 8px 0 12px;
            box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(226,90,112,.08); }
.ex-foot { font-size: 12px; color: #94A3B8; margin-top: 24px; text-align: center; }
@media print { .ex-chart { break-inside: avoid; } }
</style>
"""


def _inline(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text))


def _plain_md(text: str) -> str:
    out = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = _HEADING.match(line)
        if m:
            n = min(len(m.group(1)), 6)
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        else:
            out.append(f"<p>{_inline(line)}</p>")
    return "".join(out)


def build_page_html(items, title="Dashboard", generated_at="") -> bytes:
    parts = []
    for kind, payload in items:
        if kind == "md":
            body, unsafe = payload
            if not body.strip() or _SPACER.match(body):
                continue
            parts.append(body if unsafe else _plain_md(body))
        elif kind == "caption":
            parts.append(f'<div class="ex-cap">{_inline(payload)}</div>')
        elif kind == "chart":
            try:
                fig = payload if hasattr(payload, "to_html") else go.Figure(payload)
                html = fig.to_html(
                    full_html=False, include_plotlyjs=False, default_width="100%",
                    config={"displayModeBar": False, "responsive": True},
                )
            except Exception:
                continue
            parts.append(f'<div class="ex-chart">{html}</div>')

    page = (
        '<!DOCTYPE html><html lang="th"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)}</title>"
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;500;600;700;800&display=swap">'
        f"{THEME_CSS}{EXPORT_CSS}"
        f"<script>{get_plotlyjs()}</script></head>"
        '<body><div class="stApp"><div class="ex-wrap">'
        + "".join(parts)
        + f'<div class="ex-foot">ส่งออกเมื่อ {esc(generated_at)}</div>'
        "</div></div></body></html>"
    )
    return page.encode("utf-8")
