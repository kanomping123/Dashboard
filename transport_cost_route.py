"""
transport_cost_route.py
-----------------------
Transportation Cost Dashboard แบบ "เส้นทาง"

- อ่านเฉพาะข้อมูลจากไฟล์ที่ชื่อมีคำว่า "กล้วยไม้"
  (ถ้ามีหลายไฟล์ เช่น กล้วยไม้_2.xlsx จะใช้ไฟล์ที่แก้ไขล่าสุดไฟล์เดียว กันนับซ้ำ)
- ใช้คอลัมน์ Total Cost เป็นต้นทุนหลัก
- ทุกจุดที่แสดง Total Cost จะแสดง Revenue, กำไรสุทธิ และ CM คู่กันด้วย
  (อ่านจากคอลัมน์ของแต่ละค่าในไฟล์ตรง ๆ ไม่คำนวณเอง)
    * Revenue    = คอลัมน์ "Total Freight" ในไฟล์ (แสดงชื่อเป็น Revenue) ถ้าไม่มี ใช้คอลัมน์ "Revenue"
    * กำไรสุทธิ  = คอลัมน์ "กำไรสุทธิ"
    * CM         = คอลัมน์ "CM"
  (ทุกที่ที่แสดงคอลัมน์ Total Freight จะใช้ชื่อ Revenue — ดู DISPLAY_NAMES)
- 1 แถว = 1 เที่ยว
- เส้นทาง: Loading (ต้นทาง) + Unloading (ปลายทาง) โดยวิ่งสลับทิศนับเป็นเส้นทางเดียวกัน
  เช่น เชียงใหม่ → ปากคลองตลาด และ ปากคลองตลาด → เชียงใหม่
  = เส้นทาง "เชียงใหม่ ↔ ปากคลองตลาด"
- ทิศทางวิ่ง: แสดงตามข้อมูลจริงของแต่ละเที่ยว คือ "Loading → Unloading"
"""

import hashlib
import re
from html import escape as esc
import unicodedata
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA_FOLDER = Path("data")
SOURCE_KEYWORD = "กล้วยไม้"
DASHBOARD_VERSION = "v25.09-S"  # ใช้เช็กว่าแดชบอร์ดโหลดไฟล์ล่าสุดแล้ว
COST_COL = "Total Cost"

UNKNOWN_PLACE = "ไม่ระบุ"
UNKNOWN_ROUTE = "ไม่ระบุเส้นทาง"

COLOR_MAIN = "#E8687C"

THAI_MONTHS = {
    1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.", 5: "พ.ค.", 6: "มิ.ย.",
    7: "ก.ค.", 8: "ส.ค.", 9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค.",
}

# ชื่อคอลัมน์ในไฟล์ -> ชื่อที่แสดงบนหน้าจอ
DISPLAY_NAMES = {"Total Freight": "Revenue"}


def _disp(name) -> str:
    return DISPLAY_NAMES.get(name, name)


DISTANCE_CANDIDATES = ["Distance", "Total Distance", "ระยะทาง", "Distance (km)", "KM"]

# ชื่อคอลัมน์ที่รองรับ (เทียบแบบตัดช่องว่าง/ขีด/วงเล็บ และไม่สนตัวพิมพ์)
REVENUE_EXACT = {"revenue", "totalrevenue", "รายได้", "รายได้รวม"}
NET_PROFIT_EXACT = {"กำไรสุทธิ", "netprofit", "กำไรสุทธิบาท"}
CM_EXACT = {"cm", "contributionmargin", "cmบาท"}
# คอลัมน์ที่เป็น % / ต่อหน่วย ไม่ใช่ยอดเงิน
NOT_AMOUNT_TOKENS = ("%", "ต่อ", "per", "เปอร์เซ็นต์", "percent")


# =========================================================
# HELPERS
# =========================================================

def _key(text) -> str:
    """เทียบชื่อไฟล์ภาษาไทยให้ตรงกันแม้ encoding ต่างกันเล็กน้อย"""
    return unicodedata.normalize("NFC", str(text)).casefold()


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("฿", "", regex=False)
        .str.strip(),
        errors="coerce",
    ).astype("float64")


def _money(value) -> str:
    value = float(value or 0)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        return f"{sign}฿{value / 1_000_000:,.2f}M"
    return f"{sign}฿{value:,.0f}"


def _money_full(value) -> str:
    value = float(value or 0)
    sign = "-" if round(value) < 0 else ""
    return f"{sign}฿{abs(value):,.0f}"


def _neg(value) -> str:
    """class สีแดงสำหรับค่าติดลบ (ใช้กับกำไรสุทธิ CM)"""
    try:
        return "tc-neg" if float(value) < 0 else ""
    except (TypeError, ValueError):
        return ""


def _norm_name(c) -> str:
    return re.sub(r"[\s_\-\(\)\.]+", "", str(c)).casefold()


def _find_amount_col(df: pd.DataFrame, exact, match, exclude=()):
    """หาคอลัมน์ยอดเงิน: ชื่อตรงก่อน แล้วค่อยเดาจากชื่อ (ต้องมีตัวเลขอย่างน้อย 1 ค่า)"""
    def has_numbers(c):
        return bool(_num(df[c]).notna().any())

    for c in df.columns:
        if _norm_name(c) in exact and has_numbers(c):
            return c
    for c in df.columns:
        k = _norm_name(c)
        if k.startswith("_") or any(t in k for t in NOT_AMOUNT_TOKENS + tuple(exclude)):
            continue
        if match(k) and has_numbers(c):
            return c
    return None


def find_revenue_col(df: pd.DataFrame):
    """Revenue = คอลัมน์ Total Freight ในไฟล์ (แสดงชื่อ Revenue) ถ้าไม่มีใช้คอลัมน์ Revenue"""
    col = _find_amount_col(df, {"totalfreight"}, lambda k: False)
    return col or _find_amount_col(df, REVENUE_EXACT, lambda k: "revenue" in k, exclude=("cost",))


def find_net_profit_col(df: pd.DataFrame):
    return _find_amount_col(
        df, NET_PROFIT_EXACT, lambda k: "กำไรสุทธิ" in k or "netprofit" in k, exclude=("cm",)
    )


def find_cm_col(df: pd.DataFrame):
    return _find_amount_col(
        df, CM_EXACT,
        lambda k: k.startswith("cm") or k.endswith("cm") or "contributionmargin" in k,
        exclude=("กำไรสุทธิ", "netprofit"),
    )


FONT = "Noto Sans Thai, IBM Plex Sans Thai, sans-serif"
TEXT = "#1E293B"
MUTED = "#64748B"
GRID = "#EEF2F7"
PLOT_CONFIG = {"displayModeBar": False}

PAGE_CSS = """
<style>
/* ---------- พื้นหลังหน้า + โครงหน้า ---------- */
.stApp { background: linear-gradient(160deg, #FAD4DB 0%, #FCE4E8 38%, #FFF3F5 100%) fixed !important; }

/* ---------- หัวแดชบอร์ด ---------- */
.top-header {
    background: linear-gradient(120deg, #E25A70 0%, #EE8193 55%, #F6AAB6 100%);
    border-radius: 20px; padding: 22px 28px; margin-bottom: 14px;
    box-shadow: 0 10px 30px rgba(226, 90, 112, .25);
}
.top-header h1 { color: #FFFFFF !important; margin: 0 !important; font-size: 28px !important; }
.top-header p { color: rgba(255, 255, 255, .82) !important; margin: 4px 0 0 !important; font-size: 14px; }

/* ---------- การ์ด ---------- */
div[class*="st-key-tccard_"] {
    background: #FFFFFF; border: 1px solid #F4D8DE; border-radius: 18px;
    padding: 18px 20px 16px; margin-top: 4px; box-shadow: 0 1px 2px rgba(15, 23, 42, .04), 0 8px 24px rgba(226, 90, 112, .08);
}
div[class*="st-key-tccard_"] h4 {
    font-size: 17px !important; font-weight: 700 !important; color: #0F172A !important;
    padding: 0 0 2px !important; margin: 0 !important;
}
div[class*="st-key-tccard_"] label p { color: #475569 !important; font-size: 12.5px !important; font-weight: 600 !important; }
.tc-filter-title { font-size: 15px; font-weight: 700; color: #0F172A; margin-bottom: 2px; }

/* ---------- ช่องเลือก / แท็ก / แท็บ ---------- */
div[data-baseweb="select"] > div { background: #FFF8F9 !important; border-color: #F4D6DC !important; border-radius: 10px !important; }
span[data-baseweb="tag"] { background: #FFE8EC !important; color: #C23B53 !important; border-radius: 8px !important; }
span[data-baseweb="tag"] span { color: #C23B53 !important; }
button[data-baseweb="tab"] p { font-weight: 600 !important; color: #64748B !important; }
button[data-baseweb="tab"][aria-selected="true"] p { color: #E25A70 !important; }
div[data-baseweb="tab-highlight"] { background: #E25A70 !important; }
.stDownloadButton button, div[data-testid="stPopover"] button {
    border-radius: 10px !important; border: 1px solid #FAD1D9 !important;
    background: #FFF3F5 !important; color: #C23B53 !important; font-weight: 600 !important;
}

/* ---------- KPI ---------- */
.tc-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; margin: 8px 0 4px; }
.tc-kpi { background: #fff; border: 1px solid #F6DDE2; border-radius: 18px; padding: 16px 18px;
          display: flex; gap: 14px; align-items: center;
          box-shadow: 0 1px 2px rgba(15, 23, 42, .04), 0 8px 24px rgba(226, 90, 112, .08); }
.tc-kpi-icon { width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center;
               font-size: 22px; flex: none; }
.tc-kpi-label { font-size: 12.5px; color: #64748B; font-weight: 600; }
.tc-kpi-value { font-size: 25px; font-weight: 800; color: #0F172A; line-height: 1.2; white-space: nowrap; }
.tc-kpi-sub { font-size: 11.5px; color: #94A3B8; }
.tc-neg { color: #C23B53 !important; }

/* ---------- Insights ---------- */
.tc-ins-card { background: #fff; border: 1px solid #F4D8DE; border-radius: 18px; padding: 16px 8px 18px;
               margin: 6px 0 10px; box-shadow: 0 1px 2px rgba(15, 23, 42, .04), 0 8px 24px rgba(226, 90, 112, .09); }
.tc-ins-head { font-size: 17px; font-weight: 700; color: #0F172A; padding: 0 16px 12px; }
.tc-ins-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.tc-ins { padding: 2px 18px; min-width: 0; }
.tc-ins + .tc-ins { border-left: 1px solid #FBEBEE; }
.tc-ins-top { display: flex; align-items: center; gap: 8px; }
.tc-ins-icon { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; font-size: 15px; flex: none; }
.tc-ins-title { font-size: 12.5px; font-weight: 600; color: #64748B; }
.tc-ins-metric { font-size: 26px; font-weight: 800; line-height: 1.15; margin-top: 10px; white-space: nowrap; }
.tc-ins-main { font-size: 14px; font-weight: 600; color: #0F172A; margin-top: 2px;
               overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tc-ins-sub { font-size: 12px; color: #94A3B8; margin-top: 6px; line-height: 1.5; }
.tc-ins-tag { display: inline-block; background: #FFF1F3; color: #C23B53; font-weight: 700;
               font-size: 12px; padding: 2px 9px; border-radius: 8px; margin-bottom: 2px; }
.tc-mini-bar { display: flex; height: 6px; border-radius: 99px; overflow: hidden; background: #FBEBEE; margin: 10px 0 6px; }
.tc-mini-bar > span { display: block; height: 100%; }
.tc-ins-line { display: grid; grid-template-columns: 10px 1fr auto; gap: 8px; align-items: center;
               font-size: 12px; color: #64748B; line-height: 1.7; }
.tc-ins-line span:nth-child(2) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tc-ins-line b { color: #334155; font-weight: 600; font-variant-numeric: tabular-nums; }
.tc-ins-line .tc-sw { width: 10px; height: 10px; border-radius: 3px; }

/* ---------- ตาราง ---------- */
.tc-table-wrap { overflow: auto; background: #FFFFFF; padding: 0 !important; border: 1px solid #F6DDE2; border-radius: 14px; margin: 6px 0 10px; }
.tc-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; margin: 0 !important; }
.tc-table thead { position: sticky; top: 0; z-index: 3; }
.tc-table thead th {
    position: sticky; top: 0 !important; z-index: 3; background: #FFF3F5; color: #475569;
    box-shadow: 0 1px 0 #F6DDE2, 0 -12px 0 #FFF3F5;
    font-weight: 700; font-size: 12.5px; text-align: left; padding: 11px 14px;
    border-bottom: 1px solid #F6DDE2; white-space: nowrap;
}
.tc-table td { padding: 10px 14px; border-bottom: 1px solid #FBEFF1; color: #1E293B; white-space: nowrap; }
.tc-table tbody tr:nth-child(even) td { background: #FFFBFC; }
.tc-table tbody tr:hover td { background: #FFE8EC; }
.tc-table tr.tc-group td { border-top: 1px solid #F6DDE2; }
.tc-table td.tc-neg { color: #C23B53 !important; }
.tc-num { text-align: right !important; font-variant-numeric: tabular-nums; }
.tc-muted { color: #64748B !important; }
.tc-mono { font-variant-numeric: tabular-nums; color: #475569 !important; }
.tc-rank { color: #94A3B8 !important; font-size: 12px; width: 34px; }
.tc-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 9px; vertical-align: 1px; }
.tc-arrow { color: #F4A3B1; font-weight: 700; margin: 0 2px; }
.tc-bar { height: 5px; border-radius: 99px; background: #FFE8EC; margin-top: 5px; min-width: 110px; }
.tc-bar > span { display: block; height: 100%; border-radius: 99px; margin-left: auto; }
.tc-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 2px 0 2px; }
.tc-chip { background: #FFE8EC; color: #C23B53; font-size: 12.5px; font-weight: 600; padding: 4px 12px; border-radius: 99px; }
.tc-chip-muted { background: #F1F5F9; color: #64748B; font-weight: 500; }

/* ---------- Legend ของกราฟวงกลม ---------- */
.tc-legend { max-height: 330px; overflow: auto; padding-right: 4px; margin-top: 10px; }
.tc-leg-row { display: grid; grid-template-columns: 12px 1fr auto 52px; gap: 10px; align-items: center;
              padding: 11px 4px; border-bottom: 1px dashed #EEF2F7; font-size: 13.5px; }
.tc-sw { width: 12px; height: 12px; border-radius: 4px; }
.tc-leg-name { color: #1E293B; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tc-leg-val { color: #334155; font-variant-numeric: tabular-nums; }
.tc-leg-pct { color: #64748B; text-align: right; font-variant-numeric: tabular-nums; }
.tc-leg-foot { font-size: 12px; color: #64748B; margin-top: 10px; }
.tc-leg-foot + .tc-leg-foot { margin-top: 4px; }
.tc-source { font-size: 12px; color: #94A3B8; margin: 6px 4px 20px; }

@media (max-width: 1100px) {
  .tc-ins-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 18px; }
  .tc-ins:nth-child(3) { border-left: none; }
}
@media (max-width: 700px) {
  .tc-ins-grid { grid-template-columns: 1fr; }
  .tc-ins + .tc-ins { border-left: none; border-top: 1px solid #FBEBEE; padding-top: 14px; }
}
</style>
"""


def _card(name: str):
    """กล่องการ์ดพื้นขาว (ใช้ key ของ st.container เพื่อแต่งด้วย CSS)"""
    try:
        return st.container(key=f"tccard_{name}")
    except TypeError:  # Streamlit รุ่นเก่าที่ยังไม่รองรับ key
        return st.container(border=True)


def _km(value) -> str:
    try:
        return "—" if pd.isna(value) else f"{float(value):,.0f} กม."
    except (TypeError, ValueError):
        return "—"


def _id_text(value) -> str:
    """เลขที่เที่ยว/ทะเบียน: ตัด .0 ท้ายตัวเลขที่ถูกอ่านเป็นทศนิยม"""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def find_manifest_col(df: pd.DataFrame):
    """หาคอลัมน์ Manifest No. (รองรับการสะกดต่างกันเล็กน้อย เช่น Manifest No / ManifestNo)"""
    targets = {"manifestno", "manifestno."}
    for c in df.columns:
        if re.sub(r"[\s_\-]+", "", str(c)).casefold() in targets:
            return c
    return None


def _table_html(head, body, right_from=None, right_cols=None, max_height=460) -> str:
    right = set(right_cols or ())
    if right_from is not None:
        right |= set(range(right_from, len(head)))
    ths = "".join(
        f'<th class="{"tc-num" if i in right else ""}">{esc(h)}</th>' for i, h in enumerate(head)
    )
    return (
        f'<div class="tc-table-wrap" style="max-height:{max_height}px">'
        f'<table class="tc-table"><thead><tr>{ths}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def _style(fig):
    """หน้าตากราฟแบบเดียวกันทั้งหน้า: ฟอนต์ไทย เส้นกริดจาง พื้นโปร่ง"""
    fig.update_layout(
        font=dict(family=FONT, color=MUTED, size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="white", bordercolor="#F4D6DC",
                        font=dict(family=FONT, color=TEXT, size=13)),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID,
                     title_font=dict(color=MUTED, size=12))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID,
                     tickfont=dict(color="#334155", size=12))
    try:  # มุมโค้งของแท่ง (Plotly 5.19 ขึ้นไป)
        fig.update_layout(barcornerradius=6)
    except (ValueError, TypeError):
        pass
    return fig


def _chart_layout(fig, height, x_title, x_max=None, x_min=0):
    xaxis = dict(title=x_title, tickformat=",.0f")
    hi = 0.0 if x_max is None or pd.isna(x_max) else max(float(x_max), 0.0)
    lo = 0.0 if x_min is None or pd.isna(x_min) else min(float(x_min), 0.0)
    span = hi - lo
    if span > 0:
        # เผื่อที่ให้ตัวเลขนอกแท่งตามช่วงข้อมูลทั้งหมด ไม่ใช่แค่ขนาดของค่าติดลบ
        # กันตัวเลขของแท่งติดลบ (กำไรสุทธิ / CM) ไปทับชื่อแกน Y
        pad = span * 0.30
        xaxis["range"] = [lo - pad if lo < 0 else 0, hi + pad if hi > 0 else pad * 0.3]
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=30, t=20, b=40),
        xaxis=xaxis,
        yaxis=dict(title="", automargin=True),
        legend=dict(orientation="h", y=1.08, x=0),
        bargap=0.3,
    )
    _style(fig)
    fig.update_traces(textfont=dict(color="#334155", size=12), selector=dict(type="bar"))
    if lo < 0:  # มีค่าติดลบ แสดงเส้น 0 ให้เห็นชัดว่าแท่งไหนติดลบ
        fig.update_xaxes(zeroline=True, zerolinecolor="#CBD5E1", zerolinewidth=1)


# ชุดสีหลักของแดชบอร์ด: โทนกลาง ไม่สดจัด เข้ากับหัวสีน้ำเงินของแอป
# เส้นทางได้สีตามอันดับต้นทุน (ไม่ซ้ำกันใน 20 อันดับแรก) และใช้สีเดิมในทุกกราฟ
PALETTE = [
    "#F07C8C", "#7CC4D6", "#F6AE6B", "#95B8E6", "#E68FBF",
    "#86CFA3", "#BBA0E3", "#EFCB64", "#E98A7C", "#86B2C4",
    "#F4A6B6", "#AFD481", "#D9A47F", "#A3AAE6", "#EE9A9A",
    "#7FC9C0", "#F9C98A", "#CD99D6", "#8FC3EE", "#A5D6A7",
]
GRAY = "#EAD7DB"

# คอลัมน์ต้นทุนที่เลือกแสดงในกราฟวงกลมได้
KNOWN_COST_COLUMNS = [
    "Total Cost", "รวมต้นทุนค่าเดินทาง", "รวมต้นทุนค่าซ่อม", "รวมค่าเสื่อม", "Total Cash",
    "Total Freight", "Fuel (Cash)", "Driver Allowance", "Backup Driver Allowance",
    "Off-Route", "Off-Route Fuel", "Tarpaulin Fee", "Goods Fuel", "Pickup Cost",
    "Police Fee", "โยกค่าน้ำมันขาขึ้น", "โยกต้นทุนเที่ยวยกเลิก", "ค่าน้ำมันตามจริง",
    "ยอดปันส่วนค่าน้ำมันตามจริง", "โยกค่าน้ำมันตามจริง", "ยอดปันส่วนโยกค่าน้ำมันตามจริง",
]
# ยอดรวม/ยอดสรุป ไม่เลือกไว้ตั้งแต่แรก เพื่อไม่ให้กราฟวงกลมนับซ้ำ (ผู้ใช้เลือกเพิ่มเองได้)
PIE_EXCLUDE_DEFAULT = {
    "Total Cost", "รวมต้นทุนค่าเดินทาง", "รวมต้นทุนค่าซ่อม", "รวมค่าเสื่อม", "Total Cash", "Total Freight",
}


def _tint(hex_color: str, amount: float = 0.5) -> str:
    """ทำสีให้อ่อนลง (ผสมขาว) ใช้กับทิศทางวิ่งที่สองของเส้นทางเดียวกัน"""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (round(c + (255 - c) * amount) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def build_route_colors(routes) -> dict:
    """ให้สีเส้นทางตามลำดับ (เส้นทางต้นทุนสูงสุดได้สีแรก) ไม่ซ้ำกันใน 20 อันดับแรก"""
    colors, i = {}, 0
    for r in routes:
        if r == UNKNOWN_ROUTE:
            colors[r] = GRAY
        else:
            colors[r] = PALETTE[i % len(PALETTE)]
            i += 1
    return colors


def _nice_step(span: float, n: int = 4) -> float:
    """ระยะห่างตัวเลขบนแกนแบบอ่านง่าย (1, 2, 2.5, 5 × 10^k)"""
    import math
    if not span or span <= 0:
        return 1.0
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _wkey(base: str, options) -> str:
    """key ของ widget ที่ตัวเลือกเปลี่ยนตามตัวกรอง — เปลี่ยน key เมื่อตัวเลือกเปลี่ยน กัน error"""
    digest = hashlib.md5("|".join(map(str, options)).encode("utf-8")).hexdigest()[:10]
    return f"{base}_{digest}"




def find_source_file():
    """หาไฟล์ Excel ที่ชื่อมีคำว่า กล้วยไม้ (ถ้ามีหลายไฟล์ ใช้ไฟล์ที่แก้ไขล่าสุด)"""
    if not DATA_FOLDER.exists():
        return None
    files = [
        f for f in DATA_FOLDER.iterdir()
        if f.is_file()
        and f.suffix.lower() in {".xlsx", ".xlsm", ".xls"}
        and not f.name.startswith("~$")
        and _key(SOURCE_KEYWORD) in _key(f.stem)
    ]
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime_ns).name


def _place(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(UNKNOWN_PLACE, index=df.index, dtype="string")
    s = (
        df[col].astype("string").fillna("")
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    return s.mask(s.eq("") | s.str.casefold().isin(["nan", "none", "<na>"]), UNKNOWN_PLACE)


def build_routes(df: pd.DataFrame):
    """
    คืน (เส้นทาง, ทิศทางวิ่ง, เป็นทิศหลักหรือไม่, ต้นทาง, ปลายทาง)
    - เส้นทาง: A → B และ B → A รวมเป็น "A ↔ B" (ชื่อเรียงตามทิศที่วิ่งบ่อยกว่า)
    - ทิศทางวิ่ง: "Loading → Unloading" ตามข้อมูลจริงของเที่ยวนั้น
    """
    load = _place(df, "Loading")
    unload = _place(df, "Unloading")

    work = pd.DataFrame(
        {
            "key": ["|".join(sorted((a, b))) for a, b in zip(load, unload)],
            "a": load.to_numpy(),
            "b": unload.to_numpy(),
        },
        index=df.index,
    )

    main_direction = (
        work.groupby(["key", "a", "b"]).size().reset_index(name="n")
        .sort_values(["key", "n", "a"], ascending=[True, False, True])
        .drop_duplicates("key")
    )
    main_map = {
        k: (a, b)
        for k, a, b in zip(main_direction["key"], main_direction["a"], main_direction["b"])
    }

    routes, directions, is_main = [], [], []
    for k, a, b in zip(work["key"], work["a"], work["b"]):
        first, second = main_map[k]
        directions.append(f"{a} → {b}")
        is_main.append((a, b) == (first, second))
        if a == UNKNOWN_PLACE and b == UNKNOWN_PLACE:
            routes.append(UNKNOWN_ROUTE)
        elif a == b:
            routes.append(f"{a} (ภายในพื้นที่)")
        else:
            routes.append(f"{first} ↔ {second}")

    return (
        pd.Series(routes, index=df.index),
        pd.Series(directions, index=df.index),
        pd.Series(is_main, index=df.index),
        load,
        unload,
    )


def _prepare(src: pd.DataFrame, rev_col=None, np_col=None, cm_col=None) -> pd.DataFrame:
    work = src.copy()
    work["_Cost"] = _num(work[COST_COL]).fillna(0)

    # Revenue / กำไรสุทธิ / CM อ่านตรงจากคอลัมน์ในไฟล์ (ไม่มีคอลัมน์ = 0 และไม่แสดงในหน้า)
    for out_col, source in (("_Revenue", rev_col), ("_NP", np_col), ("_CM", cm_col)):
        work[out_col] = _num(work[source]).fillna(0) if source else 0.0

    route, direction, is_main, load, unload = build_routes(work)
    work["_Route"] = route
    work["_Direction"] = direction
    work["_IsMainDir"] = is_main
    work["_Load"] = load
    work["_Unload"] = unload

    if "Travel Req. Date" in work.columns:
        dt = pd.to_datetime(work["Travel Req. Date"], errors="coerce")
    else:
        dt = pd.Series(pd.NaT, index=work.index, dtype="datetime64[ns]")
    work["_Date"] = dt

    work["_Year"] = dt.dt.year.map(
        lambda y: "" if pd.isna(y) else str(int(y + 543 if y < 2400 else y))
    )
    if "Year" in work.columns:
        missing = work["_Year"].eq("")
        work.loc[missing, "_Year"] = (
            work.loc[missing, "Year"].astype("string").fillna("").str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )

    month = dt.dt.month
    if month.isna().all() and "Month" in work.columns:
        m = _num(work["Month"])
        month = m.where(m.between(1, 12))
    work["_MonthNum"] = month

    dist_col = next((c for c in DISTANCE_CANDIDATES if c in work.columns), None)
    work["_Distance"] = _num(work[dist_col]) if dist_col else float("nan")
    return work


def route_summary(d: pd.DataFrame, has_distance: bool) -> pd.DataFrame:
    """สรุประดับเส้นทาง (รวมทั้งสองทิศทางวิ่ง)"""
    agg = dict(
        Trips=("_Cost", "size"),
        Cost=("_Cost", "sum"),
        Revenue=("_Revenue", "sum"),
        NP=("_NP", "sum"),
        CM=("_CM", "sum"),
        Directions=("_Direction", "nunique"),
    )
    if has_distance:
        agg["AvgDistance"] = ("_Distance", "mean")
    s = d.groupby("_Route", as_index=False).agg(**agg)
    s["CostPerTrip"] = s["Cost"] / s["Trips"]
    total = s["Cost"].sum()
    s["SharePct"] = (s["Cost"] / total * 100) if total else 0.0
    return s


def direction_summary(d: pd.DataFrame, has_distance: bool) -> pd.DataFrame:
    """สรุประดับทิศทางวิ่ง (Loading → Unloading) ภายในแต่ละเส้นทาง"""
    agg = dict(
        Loading=("_Load", "first"),
        Unloading=("_Unload", "first"),
        IsMain=("_IsMainDir", "first"),
        Trips=("_Cost", "size"),
        Cost=("_Cost", "sum"),
        Revenue=("_Revenue", "sum"),
        NP=("_NP", "sum"),
        CM=("_CM", "sum"),
    )
    if has_distance:
        agg["AvgDistance"] = ("_Distance", "mean")
    s = d.groupby(["_Route", "_Direction"], as_index=False).agg(**agg)
    s["CostPerTrip"] = s["Cost"] / s["Trips"]
    return s


# =========================================================
# มุมมอง "เที่ยว" (Loading → Unloading แยกตามคอลัมน์ เที่ยววิ่ง)
# =========================================================

TRIP_TYPE_NAMES = ["เที่ยววิ่ง"]
TYPE_ORDER = ["ขาขึ้น", "ขาล่อง"]
TYPE_COLORS = {"ขาขึ้น": "#F07C8C", "ขาล่อง": "#7CC4D6", "ยกเลิก": "#BBA0E3", "ไม่ระบุ": "#CBD5E1"}
TYPE_TEXT = {"ขาขึ้น": "#C23B53", "ขาล่อง": "#2F7F95", "ยกเลิก": "#7B5BB5", "ไม่ระบุ": "#64748B"}
EXTRA_TYPE_PALETTE = ["#F6AE6B", "#86CFA3", "#EFCB64", "#E68FBF", "#95B8E6"]

LEG_CSS = """
<style>
.tc-type { display: inline-block; font-size: 12px; font-weight: 700; padding: 2px 10px; border-radius: 99px; }
.tc-type-row { display: grid; grid-template-columns: 10px 1fr auto auto; gap: 8px; align-items: center;
               font-size: 12px; color: #64748B; line-height: 1.8; }
.tc-type-row b { color: #334155; font-variant-numeric: tabular-nums; }
.tc-type-row small { color: #94A3B8; font-variant-numeric: tabular-nums; }
</style>
"""


def find_trip_type_col(df: pd.DataFrame):
    lookup = {_norm_name(c): c for c in df.columns}
    for n in TRIP_TYPE_NAMES:
        if _norm_name(n) in lookup:
            return lookup[_norm_name(n)]
    return None


def _type_colors(types) -> dict:
    colors, i = {}, 0
    for t in types:
        if t in TYPE_COLORS:
            colors[t] = TYPE_COLORS[t]
        else:
            colors[t] = EXTRA_TYPE_PALETTE[i % len(EXTRA_TYPE_PALETTE)]
            i += 1
    return colors


def _type_badge(t, colors) -> str:
    c = colors.get(t, "#CBD5E1")
    fg = TYPE_TEXT.get(t, "#3F2A2E")
    return f'<span class="tc-type" style="background:{_tint(c, 0.72)};color:{fg}">{esc(t)}</span>'


def leg_summary(d: pd.DataFrame, has_distance: bool) -> pd.DataFrame:
    """สรุประดับเที่ยว: ต้นทาง → ปลายทาง แยกตามเที่ยววิ่ง (ขาขึ้น / ขาล่อง / ยกเลิก)"""
    agg = dict(
        Route=("_Route", "first"),
        Load=("_Load", "first"), Unload=("_Unload", "first"), Dir=("_LegDir", "first"),
        Type=("_Type", "first"),
        Trips=("_Cost", "size"), Cost=("_Cost", "sum"),
        Revenue=("_Revenue", "sum"), NP=("_NP", "sum"), CM=("_CM", "sum"),
    )
    if has_distance:
        agg["AvgDistance"] = ("_Distance", "mean")
    s = d.groupby("_Leg", as_index=False).agg(**agg)
    for k in ("Cost", "Revenue", "NP", "CM"):
        s[f"{k}PerTrip"] = s[k] / s["Trips"]
    total = s["Cost"].sum()
    s["SharePct"] = (s["Cost"] / total * 100) if total else 0.0
    return s


def _route_grouped(df: pd.DataFrame, sort_col: str, ascending: bool = False) -> pd.DataFrame:
    """
    เรียงแถวใหม่ให้ขาขึ้น/ขาล่อง ของ "เส้นทางเดียวกัน" (Route แบบไม่สนทิศ) อยู่ติดกันเสมอ
    แทนที่จะเรียงแยกจากกันตามค่า sort_col เพียงอย่างเดียว

    ลำดับของแต่ละกลุ่มเส้นทาง: เรียงตามผลรวม sort_col ของทุกทิศในเส้นทางนั้น
    ลำดับภายในกลุ่ม: เรียงตาม sort_col ของแต่ละทิศเอง
    """
    if pd.api.types.is_numeric_dtype(df[sort_col]):
        route_metric = df.groupby("Route")[sort_col].sum()
    else:
        route_metric = df.groupby("Route")[sort_col].agg("min" if ascending else "max")
    route_order = route_metric.sort_values(ascending=ascending).index
    rank_map = {r: i for i, r in enumerate(route_order)}
    out = df.assign(_RouteRank=df["Route"].map(rank_map))
    out = out.sort_values(["_RouteRank", sort_col], ascending=[True, ascending])
    return out.drop(columns="_RouteRank")


# =========================================================
# DASHBOARD
# =========================================================

def render_transport_cost_dashboard(df: pd.DataFrame):
    # ---------------- SOURCE LOCK: ไฟล์กล้วยไม้เท่านั้น ----------------
    source_file = find_source_file()
    if source_file is None:
        st.error(
            f"ไม่พบไฟล์ที่ชื่อมีคำว่า “{SOURCE_KEYWORD}” ในโฟลเดอร์ data "
            "— อัปโหลดไฟล์ในหน้า Data Management ก่อน"
        )
        return
    if df.empty or "_source_file" not in df.columns:
        st.error("ยังไม่มีข้อมูลรายเที่ยวในฐานข้อมูล — กด “🔄 โหลดข้อมูลจาก Excel ใหม่” ที่แถบด้านซ้าย")
        return
    src = df[df["_source_file"].map(_key) == _key(source_file)].copy()
    if src.empty:
        st.error(
            f"ไฟล์ {source_file} ยังไม่ถูกนำเข้าเป็นข้อมูลรายเที่ยว — ตรวจว่าหัวตารางมีคอลัมน์ "
            "Loading, Unloading และ Total Cost แล้วกด “🔄 โหลดข้อมูลจาก Excel ใหม่”"
        )
        return
    missing = [c for c in [COST_COL, "Loading", "Unloading"] if c not in src.columns or src[c].isna().all()]
    if missing:
        st.error(f"ไฟล์ {source_file} ไม่มีข้อมูลในคอลัมน์: " + ", ".join(missing))
        return

    # Revenue / กำไรสุทธิ / CM — อ่านตรงจากไฟล์
    rev_col = find_revenue_col(src)
    np_col = find_net_profit_col(src)
    cm_col = find_cm_col(src)
    extra = []
    if rev_col:
        extra.append(("Revenue", "Revenue", "_Revenue"))
    if np_col:
        extra.append(("กำไรสุทธิ", "NP", "_NP"))
    if cm_col:
        extra.append(("CM", "CM", "_CM"))
    extra_keys = [k for _, k, _ in extra]
    extra_pre = [e for e in extra if e[1] == "Revenue"]
    extra_post = [e for e in extra if e[1] != "Revenue"]

    work = _prepare(src, rev_col, np_col, cm_col)
    has_distance = bool(work["_Distance"].notna().any())

    # เที่ยววิ่ง (ขาขึ้น / ขาล่อง / ยกเลิก)
    type_col = find_trip_type_col(work)
    if type_col:
        tt = work[type_col].astype("string").fillna("").str.strip()
        work["_Type"] = tt.mask(tt.eq(""), "ไม่ระบุ")
    else:
        work["_Type"] = "ไม่ระบุ"
    # ไม่นับ รถว่างไปสาขา / ของเหมาตีเปล่า (เที่ยวเปล่า) / ยกเลิก
    # ดูจากทั้งคอลัมน์ Manifest Type และ เที่ยววิ่ง
    mt = (work["Manifest Type"].astype("string").fillna("") if "Manifest Type" in work.columns
          else pd.Series("", index=work.index, dtype="string"))
    both = mt + " " + work["_Type"].astype("string")
    ex_branch = both.str.contains("รถว่างไปสาขา", regex=False, na=False)
    ex_empty = both.str.contains(r"ของเหมาตีเปล่า|เที่ยวเปล่า", regex=True, na=False) & ~ex_branch
    ex_cancel = both.str.contains("ยกเลิก", regex=False, na=False) & ~ex_branch & ~ex_empty
    excluded = {"รถว่างไปสาขา": int(ex_branch.sum()), "ของเหมาตีเปล่า": int(ex_empty.sum()),
                "ยกเลิก": int(ex_cancel.sum())}
    work = work[~(ex_branch | ex_empty | ex_cancel)].copy()
    if work.empty:
        st.warning("ไม่มีเที่ยววิ่งปกติ (ทุกเที่ยวเป็นรถว่างไปสาขา / ของเหมาตีเปล่า / ยกเลิก)")
        return
    excluded_note = " · ".join(f"{k} {v:,}" for k, v in excluded.items() if v)

    work["_LegDir"] = work["_Load"] + " → " + work["_Unload"]
    work["_Leg"] = work["_LegDir"] + " · " + work["_Type"]
    types_all = [t for t in TYPE_ORDER if t in set(work["_Type"])] + sorted(
        t for t in work["_Type"].unique() if t not in TYPE_ORDER
    )
    type_colors = _type_colors(types_all)

    # ---------------- FILTERS ----------------
    st.markdown(PAGE_CSS + LEG_CSS, unsafe_allow_html=True)
    filter_card = _card("filters")
    filter_card.markdown('<div class="tc-filter-title">🔎 ตัวกรองข้อมูล</div>', unsafe_allow_html=True)
    f1, f2, f3, f4, f5, f6, f7 = filter_card.columns([0.7, 1, 1, 1, 1, 1, 1.8])
    filtered = work

    with f1:
        years = sorted(y for y in work["_Year"].unique() if y)
        year = st.selectbox("ปี", ["ทั้งหมด"] + years, key="tc_year")
    if year != "ทั้งหมด":
        filtered = filtered[filtered["_Year"] == year]
    with f2:
        months = sorted(int(m) for m in filtered["_MonthNum"].dropna().unique())
        chosen_months = st.multiselect("เดือน", [THAI_MONTHS[m] for m in months], placeholder="ทั้งหมด",
                                       key="tc_month")
    if chosen_months:
        nums = [n for n, label in THAI_MONTHS.items() if label in chosen_months]
        filtered = filtered[filtered["_MonthNum"].isin(nums)]

    def multi_filter(container, label, column, key):
        nonlocal filtered
        with container:
            if column not in filtered.columns or filtered[column].isna().all():
                st.caption(f"ไม่มีข้อมูล{label}")
                return
            values = filtered[column].astype("string").fillna("").str.strip()
            options = sorted(v for v in values.unique() if v)
            chosen = st.multiselect(label, options, placeholder="ทั้งหมด", key=_wkey(key, options))
        if chosen:
            filtered = filtered[values.isin(chosen)]

    with f3:
        chosen_types = st.multiselect("เที่ยววิ่ง", types_all, placeholder="ทั้งหมด", key="tc_type")
    if chosen_types:
        filtered = filtered[filtered["_Type"].isin(chosen_types)]
    multi_filter(f4, "สาขา", "Branch", "tc_branch")
    multi_filter(f5, "ประเภทรถ", "Vehicle Type", "tc_vtype")
    multi_filter(f6, "ชนิดรถ", "Vehicle Model", "tc_vmodel")
    multi_filter(f7, "เที่ยว (ต้นทาง → ปลายทาง)", "_LegDir", "tc_legdir")

    if excluded_note:
        st.markdown(
            f'<div class="tc-chips"><span class="tc-chip tc-chip-muted">ไม่นับเที่ยว: {esc(excluded_note)} เที่ยว '
            "(ดูเที่ยวเปล่าและรถว่างไปสาขาได้ที่หน้า 🚚 เที่ยวเปล่า &amp; รถว่างไปสาขา)</span></div>",
            unsafe_allow_html=True,
        )

    if filtered.empty:
        st.warning("ไม่พบข้อมูลตามตัวกรองที่เลือก")
        return

    legs = leg_summary(filtered, has_distance)
    leg_list = legs.sort_values("Cost", ascending=False)["_Leg"].tolist()
    leg_colors = build_route_colors(
        work.groupby("_Leg")["_Cost"].sum().sort_values(ascending=False).index
    )

    metric_defs = [("ต้นทุนเฉลี่ยต่อเที่ยว", "CostPerTrip", "บาท/เที่ยว")]
    for label, key, _r in extra:
        metric_defs.append((f"{label} เฉลี่ยต่อเที่ยว", f"{key}PerTrip", "บาท/เที่ยว"))
    metric_defs.append(("ต้นทุนรวม (Total Cost)", "Cost", "บาท"))
    for label, key, _r in extra:
        metric_defs.append((f"{label} รวม", key, "บาท"))
    metric_defs.append(("จำนวนเที่ยว", "Trips", "เที่ยว"))
    metric_labels = [m[0] for m in metric_defs]
    metric_col = {label: col for label, col, _ in metric_defs}
    metric_unit = {col: unit for _, col, unit in metric_defs}

    # ---------------- KPI ----------------
    trips = len(filtered)
    total_cost = float(filtered["_Cost"].sum())
    total_revenue = float(filtered["_Revenue"].sum())
    type_counts = filtered["_Type"].value_counts()
    type_sub = " · ".join(f"{t} {int(type_counts.get(t, 0)):,}" for t in types_all if type_counts.get(t, 0))
    kpi_look = {"Revenue": ("🧾", "#E6F4FA"), "NP": ("💵", "#E7F6EC"), "CM": ("📈", "#EEF0FB")}
    extra_cards = {}
    for label, key, row_col in extra:
        value = float(filtered[row_col].sum())
        sub = "บาท"
        if key != "Revenue" and rev_col and total_revenue:
            sub = f"บาท • {value / total_revenue * 100:,.1f}% ของ Revenue"
        icon, bg = kpi_look[key]
        extra_cards[key] = (icon, bg, label, _money(value), sub, value < 0)
    cards = [("🚚", "#FFE8EC", "จำนวนเที่ยว", f"{trips:,}", type_sub or "เที่ยว", False)]
    if "Revenue" in extra_cards:
        cards.append(extra_cards.pop("Revenue"))
    cards.append(("💰", "#FFF0E6", "Total Cost", _money(total_cost),
                  f"เฉลี่ย ฿{total_cost / trips:,.0f} ต่อเที่ยว" if trips else "บาท", False))
    cards += list(extra_cards.values())
    st.markdown(
        '<div class="tc-kpi-grid">' + "".join(
            f'<div class="tc-kpi"><div class="tc-kpi-icon" style="background:{bg}">{icon}</div>'
            f'<div><div class="tc-kpi-label">{esc(label)}</div>'
            f'<div class="tc-kpi-value {"tc-neg" if neg else ""}">{esc(value)}</div>'
            f'<div class="tc-kpi-sub">{esc(sub)}</div></div></div>'
            for icon, bg, label, value, sub, neg in cards
        ) + "</div>",
        unsafe_allow_html=True,
    )

    # ---------------- KEY INSIGHTS ----------------
    if not legs.empty:
        reliable = legs[legs["Trips"] >= 1]
        pool = reliable if not reliable.empty else legs
        top_avg = pool.loc[pool["CostPerTrip"].idxmax()]
        top_trips = legs.loc[legs["Trips"].idxmax()]
        by_type = (
            filtered.groupby("_Type").agg(Trips=("_Cost", "size"), Cost=("_Cost", "sum")).reindex(types_all).dropna()
        )

        type_bar = "".join(
            f'<span style="width:{n / max(trips, 1) * 100:.1f}%;background:{type_colors[t]}"></span>'
            for t, n in by_type["Trips"].items()
        )
        type_lines = "".join(
            f'<div class="tc-type-row"><span class="tc-sw" style="background:{type_colors[t]}"></span>'
            f'<span>{esc(t)}</span><b>{int(r["Trips"]):,} เที่ยว</b>'
            f'<small>เฉลี่ย ฿{r["Cost"] / r["Trips"]:,.0f}</small></div>'
            for t, r in by_type.iterrows()
        )

        cells = [
            ("#E0566C", "💰", "ต้นทุนเฉลี่ยต่อเที่ยวสูงสุด",
             f'฿{top_avg["CostPerTrip"]:,.0f} / เที่ยว', top_avg["Dir"],
             f'<div class="tc-ins-sub">{_type_badge(top_avg["Type"], type_colors)} · '
             f'{_money(top_avg["Cost"])} ÷ {int(top_avg["Trips"]):,} เที่ยว</div>'),
            ("#D0588A", "🧭", "สัดส่วนเที่ยววิ่ง", f"{trips:,} เที่ยว", "ขาขึ้น · ขาล่อง",
             f'<div class="tc-mini-bar">{type_bar}</div>{type_lines}'),
            ("#D99A2B", "🚚", "เที่ยวที่วิ่งบ่อยที่สุด", f'{int(top_trips["Trips"]):,} เที่ยว', top_trips["Dir"],
             f'<div class="tc-ins-sub">{_type_badge(top_trips["Type"], type_colors)} · '
             f'เฉลี่ย ฿{top_trips["CostPerTrip"]:,.0f} ต่อเที่ยว</div>'),
        ]
        st.markdown(
            '<div class="tc-ins-card"><div class="tc-ins-head">ข้อสังเกตสำคัญ</div>'
            f'<div class="tc-ins-grid" style="grid-template-columns:repeat({len(cells)}, minmax(0, 1fr))">'
            + "".join(
                f'<div class="tc-ins"><div class="tc-ins-top">'
                f'<span class="tc-ins-icon" style="background:{_tint(c, 0.86)}">{icon}</span>'
                f'<span class="tc-ins-title">{esc(title)}</span></div>'
                f'<div class="tc-ins-metric" style="color:{c}">{esc(metric)}</div>'
                f'<div class="tc-ins-main">{esc(main)}</div>{extra_html}</div>'
                for c, icon, title, metric, main, extra_html in cells
            ) + "</div></div>",
            unsafe_allow_html=True,
        )

    # ---------------- อันดับเที่ยว ----------------
    with _card("ranking"):
        st.markdown("#### อันดับเที่ยว (ต้นทาง → ปลายทาง)")
        c1, c2, c3 = st.columns([1.5, 0.7, 1])
        with c1:
            metric = st.selectbox("ตัวชี้วัด", metric_labels, key=_wkey("tc_rank_metric", metric_labels))
        with c2:
            top_n = st.selectbox("จำนวน Top ทิศทาง", [5, 10, 15, 20, 30], index=1, key="tc_rank_top")
        with c3:
            min_trips = st.number_input(
                "จำนวนเที่ยวขั้นต่ำ", min_value=1, value=1, step=1, key="tc_rank_min",
                help="ตั้งเป็น 1 = แสดงทุกเที่ยว แม้วิ่งแค่ครั้งเดียว · ปรับเพิ่มได้ถ้าอยากตัดเที่ยวที่วิ่งน้อยออก เพราะทำให้ค่าเฉลี่ยต่อเที่ยวแกว่งผิดปกติ",
            )
        sort_col = metric_col[metric]
        pool = legs[legs["Trips"] >= min_trips]
        # Top N = N ทิศทาง (N แท่ง) ที่มีค่าตัวชี้วัดสูงสุด
        top_pool = pool.sort_values(sort_col, ascending=False).head(top_n)
        # จัดให้ทิศทางของเส้นทางเดียวกันอยู่ติดกัน: กลุ่มที่มีแท่งสูงสุดขึ้นก่อน ภายในกลุ่มเรียงจากมากไปน้อย
        group_rank = top_pool.groupby("Route")[sort_col].transform("max")
        ordered = (
            top_pool.assign(_GroupMax=group_rank)
            .sort_values(["_GroupMax", "Route", sort_col], ascending=[False, True, False])
            .drop(columns="_GroupMax")
        )
        plot = ordered.iloc[::-1]
        st.caption(
            "แต่ละแถว = เที่ยว Loading → Unloading แยกตามเที่ยววิ่ง · สีตามเที่ยววิ่ง · "
            f"จำนวน Top = {top_n} ทิศทาง ({top_n} แท่ง) · "
            "ถ้าขาขึ้นและขาล่องของเส้นทางเดียวกันติด Top ทั้งคู่ จะอยู่ติดกัน · "
            "ค่าเฉลี่ยต่อเที่ยว = ยอดรวมของทุกเที่ยว ÷ จำนวนเที่ยว"
        )
        if plot.empty:
            st.info("ไม่มีเที่ยวที่ตรงเงื่อนไข")
        elif plot[sort_col].fillna(0).abs().sum() == 0:
            st.warning(
                f"⚠️ ค่า “{metric}” ของทุกเที่ยวที่แสดงเป็น 0 หรือไม่มีข้อมูล "
                "— ตรวจสอบว่าคอลัมน์ต้นทาง (เช่น Total Cost) ในไฟล์ Excel มีตัวเลขจริง "
                "และไม่มีอักขระแปลกปนอยู่ (เช่น ช่องว่าง, ตัวอักษร)"
            )
        else:
            fmt = (lambda v: f"{v:,.0f}") if sort_col == "Trips" else _money_full

            # ---- แถบพื้นหลังสลับสี ทีละกลุ่มเส้นทาง (ขาขึ้น/ขาล่อง อยู่ติดกัน) ----
            route_seq = plot["Route"].tolist()
            band_shapes = []
            i = 0
            band_toggle = False
            while i < len(route_seq):
                j = i
                while j < len(route_seq) and route_seq[j] == route_seq[i]:
                    j += 1
                if band_toggle:
                    band_shapes.append(dict(
                        type="rect", xref="paper", yref="y",
                        x0=0, x1=1, y0=i - 0.5, y1=j - 0.5,
                        fillcolor="rgba(226,90,112,0.045)", line=dict(width=0), layer="below",
                    ))
                band_toggle = not band_toggle
                i = j

            # ---- label แกน y: จุดสีตามเที่ยววิ่ง + ชื่อเส้นทาง ----
            plot = plot.assign(
                _TickLabel=plot.apply(
                    lambda r: f"<span style='color:{type_colors.get(r['Type'], '#94A3B8')}'>●</span>  {r['Dir']}",
                    axis=1,
                )
            )

            fig = go.Figure()
            for t in types_all:
                pt = plot[plot["Type"] == t]
                if pt.empty:
                    continue
                fig.add_trace(go.Bar(
                    name=t, y=pt["Dir"], x=pt[sort_col], orientation="h",
                    marker=dict(color=type_colors[t], line=dict(width=0)),
                    text=pt[sort_col].map(fmt),
                    textfont=dict(size=12.5, color="#334155", family=FONT),
                    textposition="outside", cliponaxis=False,
                    customdata=pt[["Trips", "Cost", "CostPerTrip"]].to_numpy(),
                    hovertemplate=("<b>%{y}</b><br>จำนวนเที่ยว: %{customdata[0]:,.0f}"
                                   "<br>ต้นทุนรวม: ฿%{customdata[1]:,.0f}"
                                   "<br>ต้นทุนเฉลี่ยต่อเที่ยว: ฿%{customdata[2]:,.0f}<extra></extra>"),
                ))

            fig.update_yaxes(
                categoryorder="array", categoryarray=plot["Dir"].tolist(),
                tickmode="array",
                tickvals=plot["Dir"].tolist(),
                ticktext=plot["_TickLabel"].tolist(),
                tickfont=dict(size=13, color="#1E293B", family=FONT),
                ticklabelstandoff=8,
                automargin=True,
            )

            row_h = 38
            _chart_layout(fig, max(380, row_h * len(plot) + 140), metric_unit[sort_col],
                          x_max=plot[sort_col].max(), x_min=plot[sort_col].min())
            fig.update_layout(
                barmode="relative",
                bargap=0.38,
                shapes=band_shapes,
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=20, r=30, t=20, b=40),
                legend=dict(
                    orientation="h", y=1.06, x=0,
                    font=dict(size=12.5, color="#475569"),
                ),
            )
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    # ---------------- เปรียบเทียบเฉลี่ยต่อเที่ยว ----------------
    if extra:
        with _card("compare"):
            st.markdown("#### เปรียบเทียบ Revenue / Total Cost / กำไรสุทธิ / CM เฉลี่ยต่อเที่ยว")
            series = []
            if rev_col:
                series.append(("Revenue", "RevenuePerTrip", "#7CC4D6"))
            series.append(("Total Cost", "CostPerTrip", "#F07C8C"))
            if np_col:
                series.append(("กำไรสุทธิ", "NPPerTrip", "#86CFA3"))
            if cm_col:
                series.append(("CM", "CMPerTrip", "#BBA0E3"))
            labels = [x[0] for x in series]
            m1, m2 = st.columns([1.3, 0.7])
            with m1:
                cmp_sort = st.selectbox("เรียงเที่ยวตาม", labels, key=_wkey("tc_cmp_sort", labels))
            with m2:
                cmp_top = st.selectbox("จำนวน Top", [5, 8, 10, 15, 20], index=1, key="tc_cmp_top")
            sort_key = dict((x[0], x[1]) for x in series)[cmp_sort]
            pool = legs[legs["Trips"] >= 1] if (legs["Trips"] >= 1).any() else legs
            top = pool.sort_values(sort_key, ascending=False).head(cmp_top)
            st.caption(f"แสดง {len(top):,} เที่ยว · ค่าเฉลี่ยต่อเที่ยว · เรียงจาก {cmp_sort} มากไปน้อย")
            fig = go.Figure()
            for label, key, color in series:
                fig.add_trace(go.Bar(
                    name=label, x=top["Dir"], y=top[key], marker_color=color,
                    hovertemplate=f"{label} เฉลี่ย: ฿%{{y:,.0f}} / เที่ยว<extra></extra>",
                ))
            fig.update_layout(
                barmode="group", height=480, bargap=0.25, bargroupgap=0.06,
                margin=dict(l=10, r=10, t=20, b=20), legend=dict(orientation="h", y=1.1, x=0),
                xaxis=dict(title="", tickangle=-25, automargin=True),
                yaxis=dict(title="บาท/เที่ยว", tickformat=",.0f"), hovermode="x unified",
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    # ---------------- แนวโน้มรายเดือน ----------------
    with _card("trend"):
        st.markdown("#### แนวโน้มรายเดือนตามเที่ยว")
        st.caption("แต่ละเส้น = 1 เที่ยว (ต้นทาง → ปลายทาง · เที่ยววิ่ง)")
        t1, t2 = st.columns([3, 1.2])
        with t1:
            trend_legs = st.multiselect("เลือกเที่ยว (สูงสุด 10)", leg_list, default=leg_list[:5],
                                        max_selections=10, key=_wkey("tc_trend_legs", leg_list))
        with t2:
            trend_metric = st.selectbox("ตัวชี้วัด", metric_labels, key=_wkey("tc_trend_metric", metric_labels))
        t = filtered[filtered["_Leg"].isin(trend_legs) & filtered["_Date"].notna()]
        if not trend_legs:
            st.info("เลือกอย่างน้อย 1 เที่ยว")
        elif t.empty:
            st.info("ไม่มีข้อมูลวันที่สำหรับสร้างแนวโน้มรายเดือน")
        else:
            g = (
                t.assign(_P=t["_Date"].dt.to_period("M"))
                .groupby(["_P", "_Leg"])
                .agg(Trips=("_Cost", "size"), Cost=("_Cost", "sum"), Revenue=("_Revenue", "sum"),
                     NP=("_NP", "sum"), CM=("_CM", "sum"))
                .reset_index().sort_values("_P")
            )
            for k in ("Cost", "Revenue", "NP", "CM"):
                g[f"{k}PerTrip"] = g[k] / g["Trips"]
            g["Label"] = g["_P"].map(
                lambda p: f"{THAI_MONTHS[p.month]} {str(p.year + 543 if p.year < 2400 else p.year)[-2:]}"
            )
            y_col = metric_col[trend_metric]
            order = list(dict.fromkeys(g["Label"]))
            fig = go.Figure()
            for leg in trend_legs:
                gl = g[g["_Leg"] == leg]
                if gl.empty:
                    continue
                fig.add_trace(go.Scatter(
                    name=leg, x=gl["Label"], y=gl[y_col], mode="lines+markers",
                    line=dict(width=2.5, shape="spline", smoothing=0.6, color=leg_colors.get(leg, GRAY)),
                    marker=dict(size=7, line=dict(color="white", width=1.5)),
                    customdata=gl[["Trips", "Cost", "CostPerTrip"]].to_numpy(),
                    hovertemplate=(f"<b>{esc(leg)}</b> • %{{x}}<br>จำนวนเที่ยว: %{{customdata[0]:,}}"
                                   "<br>ต้นทุนรวม: ฿%{customdata[1]:,.0f}"
                                   "<br>เฉลี่ยต่อเที่ยว: ฿%{customdata[2]:,.0f}<extra></extra>"),
                ))
            fig.update_layout(
                height=420, margin=dict(l=15, r=15, t=20, b=20), legend=dict(orientation="h", y=-0.25, x=0),
                xaxis=dict(title="", type="category", categoryorder="array", categoryarray=order),
                yaxis=dict(title=metric_unit[y_col], tickformat=",.0f", rangemode="tozero"),
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

       # ---------------- COST PIE + VEHICLE ----------------
    left, right = st.columns([1, 1], gap="medium")
    with left:
        with _card("pie"):
            st.markdown("#### สัดส่วนต้นทุน")
            pie_opts = ["ทุกเที่ยว"] + leg_list
            p1, p3 = st.columns([2.2, 0.9])
            with p1:
                pie_leg = st.selectbox("เที่ยว", pie_opts, key=_wkey("tc_pie_leg", pie_opts))
            pie_src = filtered if pie_leg == "ทุกเที่ยว" else filtered[filtered["_Leg"] == pie_leg]
            cost_sums = {
                c: float(_num(pie_src[c]).fillna(0).sum())
                for c in KNOWN_COST_COLUMNS if c in pie_src.columns
            }
            available = [c for c, v in sorted(cost_sums.items(), key=lambda x: -x[1]) if v > 0]
            chosen_cols = []
            if available:
                default_cols = [c for c in available if c not in PIE_EXCLUDE_DEFAULT] or available[:1]
                cols_key = _wkey("tc_pie_cols", available)
                n_sel = len(st.session_state.get(cols_key, default_cols))
                with p3:
                    st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
                    picker = (st.popover(f"⚙️ รายการต้นทุน ({n_sel})") if hasattr(st, "popover")
                              else st.expander(f"⚙️ รายการต้นทุน ({n_sel})"))
                with picker:
                    chosen_cols = st.multiselect(
                        "เลือกรายการต้นทุนที่จะแสดง", available, default=default_cols, key=cols_key,
                        format_func=_disp,
                        help="ยอดรวม เช่น Total Cost / รวมต้นทุนค่าเดินทาง ไม่ได้เลือกไว้ตั้งแต่แรก "
                             "เพราะรวมรายการย่อยอยู่แล้ว ถ้าเลือกคู่กันสัดส่วนจะนับซ้ำ",
                    )
            if not available:
                st.info("ไม่พบคอลัมน์ต้นทุนที่มีมูลค่าในข้อมูลที่เลือก")
            elif not chosen_cols:
                st.info("กด ⚙️ รายการต้นทุน แล้วเลือกอย่างน้อย 1 รายการ")
            else:
                pie_df = (
                    pd.DataFrame({"รายการ": [_disp(c) for c in chosen_cols],
                                  "มูลค่า": [cost_sums[c] for c in chosen_cols]})
                    .sort_values("มูลค่า", ascending=False).reset_index(drop=True)
                )
                pie_total = pie_df["มูลค่า"].sum()
                n_trips = len(pie_src)
                small = pie_df["มูลค่า"] < pie_total * 0.02
                group_small = small.sum() >= 2
                item_colors, i_color = {}, 0
                for name, is_small in zip(pie_df["รายการ"], small):
                    if group_small and is_small:
                        item_colors[name] = GRAY
                    else:
                        item_colors[name] = PALETTE[i_color % len(PALETTE)]
                        i_color += 1
                pie_plot = pie_df
                if group_small:
                    others_name = f"อื่น ๆ ({int(small.sum())} รายการ)"
                    pie_plot = pd.concat([
                        pie_df[~small],
                        pd.DataFrame({"รายการ": [others_name], "มูลค่า": [pie_df.loc[small, "มูลค่า"].sum()]}),
                    ], ignore_index=True)
                    item_colors[others_name] = GRAY
                shares = pie_plot["มูลค่า"] / pie_total * 100
                fig = go.Figure(go.Pie(
                    labels=pie_plot["รายการ"], values=pie_plot["มูลค่า"], hole=0.6,
                    sort=False, direction="clockwise",
                    marker=dict(colors=[item_colors[n] for n in pie_plot["รายการ"]],
                                line=dict(color="white", width=3)),
                    text=[f"{p:.0f}%" if p >= 5 else "" for p in shares],
                    textinfo="text", textposition="inside",
                    insidetextfont=dict(color="#4A2A30", size=13, family=FONT),
                    hovertemplate="%{label}<br>฿%{value:,.0f}<br>%{percent}<extra></extra>",
                ))
                fig.update_layout(
                    height=420, showlegend=False, margin=dict(l=90, r=90, t=6, b=6),
                    annotations=[dict(
                        text=f"<span style='font-size:12px;color:{MUTED}'>รวมที่เลือก</span>"
                             f"<br><b style='font-size:19px;color:{TEXT}'>{_money(pie_total)}</b>",
                        x=0.5, y=0.5, showarrow=False,
                    )],
                )
                _style(fig)
                st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

                rows = "".join(
                    f'<div class="tc-leg-row"><span class="tc-sw" style="background:{item_colors[n]}"></span>'
                    f'<span class="tc-leg-name">{esc(n)}</span><span class="tc-leg-val">{_money(v)}</span>'
                    f'<span class="tc-leg-pct">{(v / pie_total * 100 if pie_total else 0):.1f}%</span></div>'
                    for n, v in zip(pie_df["รายการ"], pie_df["มูลค่า"])
                )
                per_trip = pie_total / n_trips if n_trips else 0
                sel_parts = [f"Total Cost {_money(float(pie_src['_Cost'].sum()))}"]
                for label, _k, row_col in extra:
                    sel_v = float(pie_src[row_col].sum())
                    sel_parts.append(f'{esc(label)} <span class="{_neg(sel_v)}">{_money(sel_v)}</span>')
                st.markdown(
                    f'<div class="tc-legend">{rows}</div>'
                    f'<div class="tc-leg-foot">{n_trips:,} เที่ยว · เฉลี่ย ฿{per_trip:,.0f} ต่อเที่ยว</div>'
                    f'<div class="tc-leg-foot">{" · ".join(sel_parts)}</div>',
                    unsafe_allow_html=True,
                )

    with right:
        with _card("vehicle"):
            st.markdown("#### ต้นทุนและกำไรตามประเภทรถ / ชนิดรถ")
            st.caption("ใช้ตัวกรองด้านบนเพื่อดูเฉพาะเที่ยวที่สนใจ • กำไรสุทธิ/CM อ่านจากคอลัมน์ในไฟล์")
            dims = {
                label: col
                for label, col in {
                    "ประเภทรถ": "Vehicle Type",
                    "ชนิดรถ": "Vehicle Model",
                    "ทะเบียนรถ": "License Plate",
                }.items()
                if col in filtered.columns and filtered[col].notna().any()
            }
            if not dims:
                st.info("ไม่พบข้อมูล Vehicle Type / Vehicle Model / License Plate")
            else:
                veh_colors = {"Cost": "#F07C8C", "Revenue": "#7CC4D6", "NP": "#86CFA3", "CM": "#BBA0E3"}
                veh_series = [("Total Cost", "Cost")] + [(label, key) for label, key, _r in extra]
                veh_labels = [s[0] for s in veh_series]
                veh_key = dict(veh_series)
                veh_default = [l for l in ["Total Cost", "กำไรสุทธิ"] if l in veh_labels] or veh_labels[:1]

                v1, v2, v3 = st.columns([1, 0.7, 1.1])
                with v1:
                    dim_label = st.selectbox("มิติ", list(dims), key="tc_dim_v2")
                with v2:
                    n_dim = st.selectbox("จำนวน", [5, 8, 10, 15, 20], index=1, key="tc_dim_top")
                with v3:
                    veh_mode = st.radio("แสดงเป็น", ["รวม", "เฉลี่ยต่อเที่ยว"], horizontal=True, key="tc_dim_mode")
                col = dims[dim_label]
                vd = filtered.assign(_Dim=filtered[col].astype("string").fillna("").str.strip())
                vd = vd[vd["_Dim"] != ""]
                # ตัวเลือกเรียงตามต้นทุนรวมมากไปน้อย
                dim_opts = vd.groupby("_Dim")["_Cost"].sum().sort_values(ascending=False).index.tolist()
                # แยกคนละบรรทัด เต็มความกว้าง จะได้เห็นรายการที่เลือกครบ
                chosen_series = st.multiselect("ตัวชี้วัด", veh_labels, default=veh_default,
                                               key=_wkey("tc_dim_series", veh_labels))
                picked_dims = st.multiselect(
                    f"เลือก{dim_label}ที่ต้องการดู", dim_opts,
                    placeholder=f"ไม่เลือก = แสดง Top {n_dim} · พิมพ์เพื่อค้นหา",
                    key=_wkey("tc_dim_pick", [dim_label] + dim_opts),
                )
                if not chosen_series:
                    st.info("เลือกตัวชี้วัดอย่างน้อย 1 รายการ")
                else:
                    if picked_dims:
                        vd = vd[vd["_Dim"].isin(picked_dims)]
                    g = (
                        vd.groupby("_Dim")
                        .agg(Trips=("_Cost", "size"), Cost=("_Cost", "sum"),
                             Revenue=("_Revenue", "sum"), NP=("_NP", "sum"), CM=("_CM", "sum"))
                        .reset_index()
                    )
                    per_trip_mode = veh_mode == "เฉลี่ยต่อเที่ยว"
                    if per_trip_mode:
                        for k in ("Cost", "Revenue", "NP", "CM"):
                            g[k] = g[k] / g["Trips"]
                    sort_key = veh_key[chosen_series[0]]
                    g = g.sort_values(sort_key, ascending=False)
                    if not picked_dims:  # เลือกเองแล้ว = แสดงทุกตัวที่เลือก ไม่ตัดตามจำนวน Top
                        g = g.head(n_dim)
                    g = g.iloc[::-1].copy()
                    g["Label"] = g.apply(lambda r: f"{r['_Dim']}<br>({int(r['Trips']):,} เที่ยว)", axis=1)
                    fig = go.Figure()
                    all_vals = []
                    for label in reversed(chosen_series):
                        key = veh_key[label]
                        all_vals += g[key].tolist()
                        fig.add_trace(go.Bar(
                            name=label, y=g["Label"], x=g[key], orientation="h",
                            marker_color=veh_colors[key],
                            text=g[key].map(lambda v: _money_full(v)),
                            textposition="outside", cliponaxis=False,
                            customdata=g[["Trips"]].to_numpy(),
                            hovertemplate=(
                                "%{y}<br>" + label + (" เฉลี่ยต่อเที่ยว" if per_trip_mode else "")
                                + ": ฿%{x:,.0f}<br>จำนวนเที่ยว: %{customdata[0]:,}<extra></extra>"
                            ),
                        ))
                    fig.update_yaxes(categoryorder="array", categoryarray=g["Label"].tolist())
                    _chart_layout(
                        fig, max(380, len(g) * (26 * len(chosen_series) + 14) + 120),
                        "บาท/เที่ยว" if per_trip_mode else "บาท",
                        x_max=max(all_vals), x_min=min(all_vals),
                    )
                    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.05,
                                      legend=dict(orientation="h", y=1.06, x=0, traceorder="reversed"))
                    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    # ---------------- ตารางเที่ยว ----------------
    with _card("tables"):
        st.markdown("#### ตารางต้นทุนตามเที่ยว (ต้นทาง → ปลายทาง · เที่ยววิ่ง)")
        tf1, tf2 = st.columns([3, 1])
        with tf1:
            pick_legs = st.multiselect(
                "เลือกเที่ยว (ไม่เลือก = แสดงทั้งหมด)", leg_list,
                placeholder="พิมพ์ชื่อสถานที่เพื่อค้นหา เช่น เชียงใหม่", key=_wkey("tc_table_legs", leg_list),
            )
        sort_options = ["ต้นทุนเฉลี่ย/เที่ยว", "Total Cost"] + [l for l, _k, _r in extra] + \
            ["จำนวนเที่ยว"] + (["ระยะทางเฉลี่ย"] if has_distance else []) + ["ชื่อเที่ยว"]
        with tf2:
            sort_label = st.selectbox("เรียงตาม", sort_options, key=_wkey("tc_table_sort", sort_options))
        sort_by, sort_asc = {
            "ต้นทุนเฉลี่ย/เที่ยว": ("CostPerTrip", False), "Total Cost": ("Cost", False),
            **{label: (key, False) for label, key, _r in extra},
            "จำนวนเที่ยว": ("Trips", False), "ระยะทางเฉลี่ย": ("AvgDistance", False),
            "ชื่อเที่ยว": ("_Leg", True),
        }[sort_label]
        tbl = legs if not pick_legs else legs[legs["_Leg"].isin(pick_legs)]
        tbl = _route_grouped(tbl, sort_by, ascending=sort_asc).reset_index(drop=True)
        st.caption(
            f"แสดง {len(tbl):,} จาก {len(legs):,} เที่ยว · ขาขึ้น/ขาล่อง ของเส้นทางเดียวกันจะอยู่ติดกันเสมอ · "
            "เฉลี่ย/เที่ยว = ยอดรวมของทุกเที่ยว ÷ จำนวนเที่ยว"
            + ("" if type_col else " · ไม่พบคอลัมน์ เที่ยววิ่ง ในไฟล์")
        )
        max_avg = float(legs["CostPerTrip"].max() or 1)
        head = ["เที่ยว (ต้นทาง → ปลายทาง)", "เที่ยววิ่ง", "จำนวนเที่ยว", "ต้นทุนเฉลี่ย/เที่ยว"]
        if np_col:
            head.append("กำไรสุทธิเฉลี่ย/เที่ยว")
        head += [l for l, _k, _r in extra_pre] + ["Total Cost"] + [l for l, _k, _r in extra_post]
        if has_distance:
            head.append("ระยะทางเฉลี่ย")
        head.append("สัดส่วนต้นทุน")
        body = []
        for r in tbl.to_dict("records"):
            color = type_colors.get(r["Type"], GRAY)
            cells = [
                f'<td>{esc(r["Load"])} <span class="tc-arrow">→</span> {esc(r["Unload"])}</td>',
                f"<td>{_type_badge(r['Type'], type_colors)}</td>",
                f'<td class="tc-num">{int(r["Trips"]):,}</td>',
                f'<td class="tc-num"><b>฿{r["CostPerTrip"]:,.0f}</b>'
                f'<div class="tc-bar"><span style="width:{r["CostPerTrip"] / max_avg * 100:.1f}%;'
                f'background:{color}"></span></div></td>',
            ]
            if np_col:
                cells.append(f'<td class="tc-num {_neg(r["NPPerTrip"])}">{_money_full(r["NPPerTrip"])}</td>')
            for _l, key, _r in extra_pre:
                cells.append(f'<td class="tc-num {_neg(r[key])}">{_money_full(r[key])}</td>')
            cells.append(f'<td class="tc-num">{_money_full(r["Cost"])}</td>')
            for _l, key, _r in extra_post:
                cells.append(f'<td class="tc-num {_neg(r[key])}">{_money_full(r[key])}</td>')
            if has_distance:
                cells.append(f'<td class="tc-num tc-muted">{_km(r.get("AvgDistance"))}</td>')
            cells.append(f'<td class="tc-num tc-muted">{r["SharePct"]:.1f}%</td>')
            body.append("<tr>" + "".join(cells) + "</tr>")
        st.markdown(_table_html(head, body, right_from=2), unsafe_allow_html=True)

        export = pd.DataFrame({
            "ต้นทาง (Loading)": tbl["Load"], "ปลายทาง (Unloading)": tbl["Unload"], "เที่ยววิ่ง": tbl["Type"],
            "จำนวนเที่ยว": tbl["Trips"], "ต้นทุนเฉลี่ยต่อเที่ยว": tbl["CostPerTrip"].round(2),
            **({"กำไรสุทธิเฉลี่ยต่อเที่ยว": tbl["NPPerTrip"].round(2)} if np_col else {}),
            **{label: tbl[key] for label, key, _r in extra_pre},
            "Total Cost": tbl["Cost"],
            **{label: tbl[key] for label, key, _r in extra_post},
            **({"ระยะทางเฉลี่ย": tbl["AvgDistance"].round(1)} if has_distance else {}),
            "% ของต้นทุนรวม": tbl["SharePct"].round(2),
        })
        st.download_button("⬇️ ดาวน์โหลดตาราง (CSV)", export.to_csv(index=False).encode("utf-8-sig"),
                           file_name="trip_leg_cost.csv", mime="text/csv", key="tc_leg_download")

    # ---------------- เปรียบเทียบขาขึ้น–ขาล่อง ต่อเส้นทาง ----------------
    with _card("balance"):
        st.markdown("#### ⚖️ เปรียบเทียบขาขึ้น–ขาล่อง ต่อเส้นทาง")
        st.caption(
            "เทียบต้นทุน/รายได้/กำไรของสองทิศทางในเส้นทางเดียวกัน เพื่อดูว่าทิศไหน \"แพงกว่า\" หรือ "
            "\"กำไรน้อยกว่า\" — ใช้ตัดสินใจเรื่องราคาค่าขนส่งขากลับ หรือหาโหลดเที่ยวกลับ (backhaul) "
            "เพื่อลดต้นทุนรวมของเส้นทาง"
        )

        bal_options = [("ต้นทุนเฉลี่ย/เที่ยว", "CostPerTrip")]
        if rev_col:
            bal_options.append(("Revenue เฉลี่ย/เที่ยว", "RevenuePerTrip"))
        if np_col:
            bal_options.append(("กำไรสุทธิเฉลี่ย/เที่ยว", "NPPerTrip"))
        if cm_col:
            bal_options.append(("CM เฉลี่ย/เที่ยว", "CMPerTrip"))
        bal_labels = [b[0] for b in bal_options]
        bal_key = dict(bal_options)

        e1, e2, e3 = st.columns([1.4, 1, 0.8])
        with e1:
            bal_metric = st.selectbox("เปรียบเทียบด้วยตัวชี้วัด", bal_labels, key=_wkey("tc_bal_metric", bal_labels))
        with e2:
            bal_min_trips = st.number_input(
                "จำนวนเที่ยวขั้นต่ำต่อทิศทาง", min_value=1, value=1, step=1, key="tc_bal_min",
                help="ตั้งเป็น 1 = แสดงทุกเส้นทาง แม้วิ่งฝั่งใดฝั่งหนึ่งแค่ครั้งเดียว · ปรับเพิ่มได้ถ้าอยากตัดเส้นทางที่วิ่งน้อยเกินไปออก เพราะค่าเฉลี่ยแกว่งง่าย",
            )
        with e3:
            bal_top_n = st.selectbox("จำนวน Top", [10, 15, 20, 30], index=1, key="tc_bal_top")
        bal_col = bal_key[bal_metric]
        higher_word = "แพงกว่า" if bal_col == "CostPerTrip" else "สูงกว่า"

        def _side(d, side):
            part = d[(d["Type"] == side) & (d["Trips"] >= bal_min_trips)]
            return part.groupby("Route", as_index=False).agg(
                Load=("Load", "first"), Unload=("Unload", "first"),
                Value=(bal_col, "sum"), Trips=("Trips", "sum"),
            )

        up = _side(legs, "ขาขึ้น")
        down = _side(legs, "ขาล่อง")
        pair = up.merge(down, on="Route", suffixes=("_up", "_down"))

        if pair.empty:
            st.info(
                "ไม่พบเส้นทางที่มีทั้งขาขึ้นและขาล่องตรงตามจำนวนเที่ยวขั้นต่ำที่กำหนด "
                "ลองลดจำนวนเที่ยวขั้นต่ำต่อทิศทางดู"
            )
        else:
            pair["ส่วนต่าง"] = pair["Value_down"] - pair["Value_up"]
            pair["ส่วนต่างเปอร์เซ็นต์"] = (
                pair["ส่วนต่าง"] / pair["Value_up"].abs().replace(0, pd.NA) * 100
            )
            pair = pair.reindex(pair["ส่วนต่าง"].abs().sort_values(ascending=False).index)
            top_pair = pair.head(bal_top_n).iloc[::-1]

            up_color, down_color = TYPE_COLORS["ขาขึ้น"], TYPE_COLORS["ขาล่อง"]
            st.markdown(
                f'<div class="tc-chips"><span class="tc-chip">{len(pair):,} เส้นทางที่มีครบทั้งสองทิศ</span>'
                f'<span class="tc-chip" style="background:{_tint(down_color,0.75)};color:#2F7F95">■ ขาล่อง{higher_word}</span>'
                f'<span class="tc-chip" style="background:{_tint(up_color,0.75)};color:#C23B53">■ ขาขึ้น{higher_word}</span>'
                f'<span class="tc-chip tc-chip-muted">เรียงจากส่วนต่างมากไปน้อย · แสดง Top {min(bal_top_n, len(pair)):,}</span></div>',
                unsafe_allow_html=True,
            )

            # ส่วนต่างไม่ใช่การขาดทุน: แสดงเป็นค่าบวกเสมอ แค่วางคนละฝั่ง
            # ซ้าย = ขาขึ้นสูง/แพงกว่า · ขวา = ขาล่องสูง/แพงกว่า
            # เครื่องหมายลบใช้เฉพาะค่าที่ขาดทุนจริง (กำไรสุทธิ / CM ติดลบ)
            up_word, down_word = f"ขาขึ้น{higher_word}", f"ขาล่อง{higher_word}"
            is_profit = bal_col != "CostPerTrip"

            def _winner(diff):
                if diff > 0:
                    return down_word
                if diff < 0:
                    return up_word
                return "เท่ากัน"

            def _loss_note(r):
                if not is_profit:
                    return ""
                loss = [s for s, v in (("ขาขึ้น", r["Value_up"]), ("ขาล่อง", r["Value_down"])) if v < 0]
                return (" · " + " และ ".join(loss) + "ขาดทุน") if loss else ""

            bar_colors = [down_color if v > 0 else up_color for v in top_pair["ส่วนต่าง"]]
            bar_text = top_pair.apply(lambda r: f'฿{abs(r["ส่วนต่าง"]):,.0f}{_loss_note(r)}', axis=1)
            # เส้นทางที่มีทิศขาดทุน = ตัวอักษรสีแดง
            text_colors = ["#C23B53" if _loss_note(r) else "#334155" for r in top_pair.to_dict("records")]
            hover_data = top_pair.apply(
                lambda r: [
                    _money_full(r["Value_up"]), _money_full(r["Value_down"]),
                    f'{int(r["Trips_up"]):,}', f'{int(r["Trips_down"]):,}',
                    f'฿{abs(r["ส่วนต่าง"]):,.0f}', _winner(r["ส่วนต่าง"]),
                ],
                axis=1,
            ).tolist()
            fig = go.Figure(go.Bar(
                x=top_pair["ส่วนต่าง"],
                y=top_pair.apply(lambda r: f'{r["Load_up"]} ↔ {r["Unload_up"]}', axis=1),
                orientation="h", marker_color=bar_colors,
                text=bar_text, textposition="outside", cliponaxis=False,
                customdata=hover_data,
                hovertemplate=(
                    "<b>%{y}</b><br>ขาขึ้น: %{customdata[0]} (%{customdata[2]} เที่ยว)"
                    "<br>ขาล่อง: %{customdata[1]} (%{customdata[3]} เที่ยว)"
                    "<br>%{customdata[5]} %{customdata[4]}<extra></extra>"
                ),
            ))
            fig.add_vline(x=0, line_color="#CBD5E1", line_width=1)
            _chart_layout(
                fig, max(360, 32 * len(top_pair) + 150), f"ส่วนต่าง {bal_metric} (บาท)",
                x_max=top_pair["ส่วนต่าง"].max(), x_min=top_pair["ส่วนต่าง"].min(),
            )
            fig.update_traces(textfont=dict(color=text_colors, size=12, family=FONT))
            # ตัวเลขแกน X แสดงเป็นค่าบวกทั้งสองฝั่ง
            max_abs = float(top_pair["ส่วนต่าง"].abs().max() or 1)
            step = _nice_step(max_abs)
            n_steps = int(max_abs // step) + 2
            ticks = [i * step for i in range(-n_steps, n_steps + 1)]
            fig.update_xaxes(tickmode="array", tickvals=ticks, ticktext=[f"{abs(v):,.0f}" for v in ticks])
            # ป้ายบอกความหมายของแต่ละฝั่ง
            fig.add_annotation(xref="paper", yref="paper", x=0, y=1.0, xanchor="left", yanchor="bottom",
                               text=f"◀ {up_word}", showarrow=False,
                               font=dict(color="#C23B53", size=12.5, family=FONT))
            fig.add_annotation(xref="paper", yref="paper", x=1, y=1.0, xanchor="right", yanchor="bottom",
                               text=f"{down_word} ▶", showarrow=False,
                               font=dict(color="#2F7F95", size=12.5, family=FONT))
            fig.update_layout(margin=dict(l=10, r=30, t=40, b=40))
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

            head = ["เส้นทาง", "ขาขึ้น (Load → Unload)", f"ขาขึ้น {bal_metric}",
                    "ขาล่อง (Load → Unload)", f"ขาล่อง {bal_metric}", "ส่วนต่าง", "ส่วนต่าง %",
                    f"ทิศที่{higher_word}"]
            body = []
            for r in pair.head(bal_top_n).to_dict("records"):
                diff, pct = r["ส่วนต่าง"], r["ส่วนต่างเปอร์เซ็นต์"]
                pct_txt = f"{abs(pct):,.1f}%" if pd.notna(pct) else "—"
                color = down_color if diff > 0 else up_color
                win = _winner(diff)
                win_fg = "#2F7F95" if diff > 0 else ("#C23B53" if diff < 0 else "#64748B")
                win_bg = _tint(down_color if diff > 0 else up_color, 0.78) if diff else "#F1F5F9"
                cells = [
                    f'<td>{esc(r["Route"])}</td>',
                    f'<td class="tc-muted">{esc(r["Load_up"])} → {esc(r["Unload_up"])}</td>',
                    f'<td class="tc-num {_neg(r["Value_up"])}">{_money_full(r["Value_up"])}</td>',
                    f'<td class="tc-muted">{esc(r["Load_down"])} → {esc(r["Unload_down"])}</td>',
                    f'<td class="tc-num {_neg(r["Value_down"])}">{_money_full(r["Value_down"])}</td>',
                    f'<td class="tc-num"><b style="color:{color}">฿{abs(diff):,.0f}</b></td>',
                    f'<td class="tc-num tc-muted">{pct_txt}</td>',
                    f'<td><span class="tc-type" style="background:{win_bg};color:{win_fg}">{esc(win)}</span></td>',
                ]
                body.append("<tr>" + "".join(cells) + "</tr>")
            st.markdown(_table_html(head, body, right_cols={2, 4, 5, 6}, max_height=420), unsafe_allow_html=True)

            export = pair.assign(
                _abs=pair["ส่วนต่าง"].abs(),
                _pct=pair["ส่วนต่างเปอร์เซ็นต์"].abs(),
                _win=pair["ส่วนต่าง"].map(_winner),
            ).rename(columns={
                "Load_up": "ขาขึ้น ต้นทาง", "Unload_up": "ขาขึ้น ปลายทาง", "Value_up": f"ขาขึ้น {bal_metric}",
                "Load_down": "ขาล่อง ต้นทาง", "Unload_down": "ขาล่อง ปลายทาง", "Value_down": f"ขาล่อง {bal_metric}",
                "_abs": "ส่วนต่าง (บาท)", "_pct": "ส่วนต่าง %", "_win": f"ทิศที่{higher_word}",
            })[["Route", "ขาขึ้น ต้นทาง", "ขาขึ้น ปลายทาง", f"ขาขึ้น {bal_metric}",
                "ขาล่อง ต้นทาง", "ขาล่อง ปลายทาง", f"ขาล่อง {bal_metric}",
                "ส่วนต่าง (บาท)", "ส่วนต่าง %", f"ทิศที่{higher_word}"]]
            st.download_button("⬇️ ดาวน์โหลดตารางเปรียบเทียบ (CSV)", export.to_csv(index=False).encode("utf-8-sig"),
                               file_name="route_direction_balance.csv", mime="text/csv", key="tc_balance_download")

    sheets = ", ".join(sorted(src["_source_sheet"].astype(str).unique())) if "_source_sheet" in src.columns else "-"
    src_cols = {"Revenue": rev_col, "กำไรสุทธิ": np_col, "CM": cm_col, "เที่ยววิ่ง": type_col}
    note = "".join(f" · {name} = “{esc(str(c))}”" for name, c in src_cols.items() if c)
    absent = [name for name, c in src_cols.items() if not c]
    if absent:
        note += " · ไม่พบคอลัมน์ " + ", ".join(absent) + " ในไฟล์"
    if excluded_note:
        note += f" · ไม่นับ {excluded_note} เที่ยว"
    st.markdown(
        f'<div class="tc-source">ข้อมูลจาก {esc(source_file)} · ชีต {esc(sheets)} · '
        f'{len(work):,} เที่ยววิ่งปกติทั้งไฟล์ · แสดง {len(filtered):,} เที่ยวตามตัวกรอง{note} · {DASHBOARD_VERSION}</div>',
        unsafe_allow_html=True,
    )