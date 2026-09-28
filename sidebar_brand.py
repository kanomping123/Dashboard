"""
sidebar_brand.py
----------------
ตกแต่งแถบด้านซ้าย (Sidebar) ให้เป็นแบรนด์บริษัท นิ่มซี่เส็งขนส่ง 1988 จำกัด

- โลโก้บริษัท: อ่านจากไฟล์ logo.png ที่อยู่โฟลเดอร์เดียวกับ app.py
  (ถ้าไม่มีไฟล์ จะแสดงชื่อบริษัทแทน)
- แถบลายเส้นแดง-เหลือง ตามสีโลโก้
- เมนูแบบปุ่ม, การ์ดสถานะข้อมูล, ถนนพร้อมรถวิ่งด้านล่าง
"""

import base64
from datetime import datetime
from html import escape as esc
from pathlib import Path

import streamlit as st

LOGO_PATH = Path("logo.png")
COMPANY_TH = "บริษัท นิ่มซี่เส็งขนส่ง 1988 จำกัด"
COMPANY_EN = "Nim See Seng Transport 1988 Co., Ltd."

THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]

SIDEBAR_CSS = """
<style>
/* ---------- พื้น Sidebar: ขาว-ชมพูพาสเทล ---------- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFFFFF 0%, #FFF4F6 55%, #FDE7EB 100%) !important;
    border-right: 1px solid #F6D3DA;
}
[data-testid="stSidebar"] > div { background: transparent !important; }
[data-testid="stSidebarUserContent"] { padding-top: 0.6rem !important; }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span { color: #5B3A41; }

/* ---------- การ์ดโลโก้ ---------- */
.nss-brand { background: #FFFFFF; border: 1px solid #F6D3DA; border-radius: 18px; overflow: hidden;
             box-shadow: 0 6px 20px rgba(227, 30, 36, .08); margin-bottom: 14px; }
.nss-stripe { height: 8px; background: repeating-linear-gradient(-45deg, #E4262C 0 10px, #FFC72C 10px 20px); }
.nss-brand-body { padding: 14px 16px 14px; text-align: center; }
.nss-brand-body img { width: 100%; max-width: 210px; display: block; margin: 0 auto 8px; }
.nss-name-th { font-size: 14px; font-weight: 800; color: #C8102E; line-height: 1.35; }
.nss-name-en { font-size: 11px; color: #9A7A80; margin-top: 2px; letter-spacing: .2px; }
.nss-tag { display: inline-block; margin-top: 10px; background: #FFF1F3; color: #C8102E; border: 1px solid #F8CDD5;
           font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 99px; }

/* ---------- หัวข้อย่อย ---------- */
.nss-label { font-size: 11.5px; font-weight: 700; color: #B98A93; margin: 14px 4px 6px; letter-spacing: .3px; }

/* ---------- เมนู (radio) เป็นปุ่ม ---------- */
[data-testid="stSidebar"] [role="radiogroup"] { gap: 6px; }
[data-testid="stSidebar"] [role="radiogroup"] > label {
    background: #FFFFFF; border: 1px solid #F6D3DA; border-radius: 12px;
    padding: 10px 12px; margin: 0 !important; width: 100%;
    transition: background .15s ease, border-color .15s ease;
}
[data-testid="stSidebar"] [role="radiogroup"] > label:hover { background: #FFF1F3; border-color: #F4B3BF; }
[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
    background: linear-gradient(120deg, #E25A70, #EE8193); border-color: #E25A70;
    box-shadow: 0 6px 16px rgba(226, 90, 112, .28);
}
[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) p { color: #FFFFFF !important; font-weight: 700; }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] { display: none; }

/* ---------- ปุ่มโหลดข้อมูลใหม่ ---------- */
[data-testid="stSidebar"] .stButton button {
    background: #FFFFFF !important; color: #C23B53 !important; border: 1px dashed #F4A3B1 !important;
    border-radius: 12px !important; font-weight: 700 !important; margin-top: 10px;
}
[data-testid="stSidebar"] .stButton button:hover { background: #FFF1F3 !important; border-style: solid !important; }
[data-testid="stSidebar"] .stButton button p { color: #C23B53 !important; }

/* ---------- การ์ดสถานะ ---------- */
.nss-card { background: #FFFFFF; border: 1px solid #F6D3DA; border-radius: 16px; padding: 12px 14px;
            box-shadow: 0 4px 14px rgba(227, 30, 36, .05); }
.nss-row { display: flex; justify-content: space-between; align-items: center; gap: 10px;
           font-size: 12.5px; padding: 6px 0; border-bottom: 1px dashed #F6DDE2; }
.nss-row:last-child { border-bottom: none; }
.nss-row .k { color: #9A7A80; }
.nss-row .v { color: #3F2A2E; font-weight: 700; text-align: right; font-variant-numeric: tabular-nums; }
.nss-pill { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700;
            padding: 3px 10px; border-radius: 99px; }
.nss-pill.on { background: #E9F9EF; color: #15803D; }
.nss-pill.off { background: #FFF4E5; color: #B45309; }
.nss-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.nss-pill.on .nss-dot { animation: nss-pulse 1.8s ease-in-out infinite; }
@keyframes nss-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
.nss-hint { font-size: 11.5px; color: #9A7A80; margin-top: 8px; line-height: 1.5; }

/* ---------- ถนน + รถวิ่ง ---------- */
.nss-road { position: relative; height: 44px; border-radius: 12px; background: #3B3438; overflow: hidden; margin-top: 16px; }
.nss-road::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 4px;
                    background: repeating-linear-gradient(-45deg, #E4262C 0 8px, #FFC72C 8px 16px); }
.nss-road::after { content: ""; position: absolute; left: 0; right: 0; top: 60%; height: 3px;
                   background: repeating-linear-gradient(90deg, #FDE68A 0 16px, transparent 16px 30px); }
.nss-truck { position: absolute; top: 9px; font-size: 22px; z-index: 1;
             animation: nss-drive 10s linear infinite; }
.nss-truck span { display: inline-block; transform: scaleX(-1); }
@keyframes nss-drive { from { left: -36px; } to { left: 100%; } }
@media (prefers-reduced-motion: reduce) {
    .nss-truck { animation: none; left: 42%; }
    .nss-pill.on .nss-dot { animation: none; }
}
.nss-foot { font-size: 11px; color: #B98A93; text-align: center; margin: 10px 0 4px; line-height: 1.5; }
</style>
"""


def _thai_datetime(dt: datetime, with_time: bool = True) -> str:
    text = f"{dt.day} {THAI_MONTHS[dt.month - 1]} {dt.year + 543}"
    return f"{text} {dt:%H:%M} น." if with_time else text


@st.cache_data(show_spinner=False)
def _logo_data_uri(mtime_ns: int) -> str:
    return "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode()


def render_sidebar_top():
    """โลโก้ + ชื่อบริษัท (เรียกก่อนเมนู)"""
    st.sidebar.markdown(SIDEBAR_CSS, unsafe_allow_html=True)

    if LOGO_PATH.exists():
        logo_html = f'<img src="{_logo_data_uri(LOGO_PATH.stat().st_mtime_ns)}" alt="logo">'
    else:
        logo_html = '<div style="font-size:44px;line-height:1.1">🚚</div>'

    st.sidebar.markdown(
        '<div class="nss-brand"><div class="nss-stripe"></div><div class="nss-brand-body">'
        f'{logo_html}'
        # โลโก้มีชื่อบริษัทภาษาไทยอยู่แล้ว จึงแสดงชื่อไทยเฉพาะตอนไม่มีไฟล์โลโก้
        + ("" if LOGO_PATH.exists() else f'<div class="nss-name-th">{esc(COMPANY_TH)}</div>')
        + f'<div class="nss-name-en">{esc(COMPANY_EN)}</div>'
        + '<div class="nss-tag">📊 Transportation Analytics</div>'
        '</div></div>'
        '<div class="nss-label">เมนูหลัก</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_bottom(db_path: Path, data_folder: Path, trip_rows: int, auto_sync: bool):
    """การ์ดสถานะข้อมูล + ถนนรถวิ่ง (เรียกหลังเมนู)"""
    now = datetime.now()
    files = [
        f for f in data_folder.glob("*.xls*") if not f.name.startswith("~$")
    ] if data_folder.exists() else []
    db_time = (
        _thai_datetime(datetime.fromtimestamp(db_path.stat().st_mtime))
        if db_path.exists() else "ยังไม่มีฐานข้อมูล"
    )

    pill = (
        '<span class="nss-pill on"><span class="nss-dot"></span>เปิดใช้งาน</span>'
        if auto_sync else
        '<span class="nss-pill off"><span class="nss-dot"></span>ต้องกดรีเฟรช</span>'
    )
    hint = (
        "แก้ Excel ในโฟลเดอร์ data แล้วกด Save ระบบจะอัปเดตให้เอง"
        if auto_sync else
        "Streamlit รุ่นนี้ยังไม่รองรับการอัปเดตอัตโนมัติ"
    )

    st.sidebar.markdown(
        '<div class="nss-label">สถานะข้อมูล</div>'
        '<div class="nss-card">'
        f'<div class="nss-row"><span class="k">Auto Sync</span>{pill}</div>'
        f'<div class="nss-row"><span class="k">อัปเดตล่าสุด</span><span class="v">{esc(db_time)}</span></div>'
        f'<div class="nss-row"><span class="k">ไฟล์ Excel</span><span class="v">{len(files):,} ไฟล์</span></div>'
        f'<div class="nss-row"><span class="k">รายการเที่ยว</span><span class="v">{trip_rows:,} รายการ</span></div>'
        f'<div class="nss-hint">{esc(hint)}</div>'
        '</div>'
        '<div class="nss-road"><div class="nss-truck"><span>🚚</span></div></div>'
        f'<div class="nss-foot">วัน{THAI_DAYS[now.weekday()]}ที่ {_thai_datetime(now, with_time=False)}'
        f'<br>© {now.year + 543} {esc(COMPANY_TH)}</div>',
        unsafe_allow_html=True,
    )