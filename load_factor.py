"""
load_factor.py
--------------
Load Factor Dashboard (ธีมแดง-ขาวพาสเทล แบบเดียวกับหน้าอื่น)

ตรรกะการคำนวณยึดตามโค้ด load_factor_dashboard_standalone_latest.py ทุกอย่าง:
- 1 แถว = 1 เที่ยว (Trip Key Unique ไม่ซ้ำ)
- LF รวม = ผลรวมน้ำหนัก ÷ ผลรวมความจุ (ไม่ใช่ค่าเฉลี่ยของ LF รายเที่ยว)
- Volume LF > 150% = Check/Outlier: เก็บค่าจริงไว้ในรายละเอียด
  แต่ไม่นำมาคำนวณ Volume LF รวม (ภาพรวม / ชนิดรถ / เส้นทาง)
- Route Key = ระดับเส้นทาง (↔), Trip Direction = ทิศทางวิ่งจริงของเที่ยว (→)

เปลี่ยนเฉพาะหน้าตา: การ์ด KPI, ข้อสังเกตสำคัญ, กราฟสีตามกลุ่ม, ตารางแบบเดียวกับหน้า Transportation
"""

import hashlib
from html import escape as esc

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

FONT = "Noto Sans Thai, IBM Plex Sans Thai, sans-serif"
TEXT = "#1E293B"
MUTED = "#64748B"
GRID = "#F6E6E9"
PLOT_CONFIG = {"displayModeBar": False}

# ช่วง "ระดับการบรรทุกเทียบกับความสามารถของรถ" — ใช้เฉพาะ 4 ช่วงหลัก (≤100%)
# ค่า Load Factor > 100% ไม่ใช่ระดับที่ 5: แยกออกเป็น "รายการที่ต้องตรวจสอบ" ต่างหาก
# (ห้ามใช้ป้าย Low/Medium/High และห้ามสรุปว่า "เกินความสามารถ" / "ผิดปกติ" / "Outlier")
ORDER = ["≤25%", ">25–50%", ">50–75%", ">75–100%"]
CHECK_LABEL = "ตรวจสอบข้อมูล (>100%)"
BOTH = "ดูทั้งคู่"
METRIC_COL = {"น้ำหนัก": "_WeightLF", "ปริมาตร": "_VolumeLF", "ดูทั้งคู่": "_BothLF"}
STATUS_MAP = {g: g for g in ORDER}  # ใช้ช่วง % เป็นป้ายกำกับตรง ๆ ไม่ตีความเป็นระดับ
GROUP_COLORS = {
    ORDER[0]: "#B9D6F2",
    ORDER[1]: "#95B8E6",
    ORDER[2]: "#EFCB64",
    ORDER[3]: "#86CFA3",
}
# สีของ "รายการที่ต้องตรวจสอบ" ต้องแยกจาก 4 สีหลักอย่างชัดเจน (ไม่ใช้ไล่โทนเดียวกัน)
CHECK_COLOR = "#EC7F86"
OUTLIER_COLOR = CHECK_COLOR  # คงชื่อเดิมไว้เพื่อความเข้ากันได้กับส่วนอื่นของไฟล์
# สีทิศทางวิ่งในตารางเส้นทาง: ทิศหลัก (วิ่งบ่อยกว่า) = เข้ม, อีกทิศ = อ่อน
DIR_COLORS = ["#E8687C", "#F7B6C1", "#FAD4DB"]
ARROW = ' <span class="lfx-arrow">→</span> '
# สีตัวเลขในข้อสังเกตสำคัญ (เข้มกว่าสีกราฟ ให้อ่านง่ายบนพื้นขาว)
INS_TEXT = {"#95B8E6": "#4F7CC0", "#86CFA3": "#3E9E6A", "#EC7F86": "#D0505C"}

PAGE_CSS = """
<style>
.lfx-title { font-size: 15px; font-weight: 700; color: #0F172A; margin-bottom: 2px; }

/* KPI */
.lfx-kpi-grid { display: grid; gap: 14px; margin: 8px 0 4px; }
.lfx-kpi-grid.top { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.lfx-kpi-grid.sub { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 12px; }
.lfx-kpi { background: #fff; border: 1px solid #F4D8DE; border-radius: 18px; padding: 16px 18px;
           display: flex; gap: 14px; align-items: center; min-width: 0;
           box-shadow: 0 1px 2px rgba(15, 23, 42, .04), 0 8px 24px rgba(226, 90, 112, .08); }
.lfx-kpi.flat { border: none; box-shadow: none; padding: 4px 0; background: transparent; }
.lfx-kpi.sub-card { padding: 12px 14px; border-radius: 14px; }
.lfx-kpi.sub-card.check { border: 1.5px dashed #EC7F86; background: #FFF5F6; }
.lfx-kpi-icon { width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center;
                font-size: 22px; flex: none; }
.lfx-kpi-body { min-width: 0; flex: 1; }
.lfx-kpi-label { font-size: 12.5px; color: #64748B; font-weight: 600; }
.lfx-kpi-value { font-size: 25px; font-weight: 800; color: #0F172A; line-height: 1.2; white-space: nowrap;
                 overflow: hidden; text-overflow: ellipsis; }
.lfx-kpi-grid.sub .lfx-kpi-value { font-size: 21px; }
.lfx-kpi-sub { font-size: 11.5px; color: #94A3B8; }
.lfx-meter { height: 7px; border-radius: 99px; background: #FBEBEE; margin-top: 8px; overflow: hidden; }
.lfx-meter > span { display: block; height: 100%; border-radius: 99px; }

/* Insights */
.lfx-ins-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 6px 0 4px; }
.lfx-ins { padding: 4px 18px; min-width: 0; }
.lfx-ins + .lfx-ins { border-left: 1px solid #FBEBEE; }
.lfx-ins-title { font-size: 12.5px; font-weight: 600; color: #64748B; display: flex; align-items: center; gap: 8px; }
.lfx-ins-icon { width: 28px; height: 28px; border-radius: 9px; display: grid; place-items: center; font-size: 14px; }
.lfx-ins-metric { font-size: 26px; font-weight: 800; line-height: 1.15; margin-top: 8px; }
.lfx-ins-sub { font-size: 12px; color: #94A3B8; margin-top: 4px; line-height: 1.5; }

/* Legend (กราฟวงกลม + คำอธิบายช่วง) */
.lfx-legend { margin-top: 4px; }
.lfx-leg-row { display: grid; grid-template-columns: 12px minmax(0, 1fr) auto 54px; gap: 10px; align-items: center;
               padding: 8px 4px; border-bottom: 1px dashed #F4E4E7; font-size: 13px; }
.lfx-leg-row:last-child { border-bottom: none; }
.lfx-sw { width: 12px; height: 12px; border-radius: 4px; }
.lfx-leg-name { color: #1E293B; font-weight: 600; min-width: 0; }
.lfx-leg-name small { display: block; color: #94A3B8; font-weight: 500; font-size: 11.5px; }
.lfx-leg-val { color: #334155; font-variant-numeric: tabular-nums; text-align: right; }
.lfx-leg-pct { color: #64748B; text-align: right; font-variant-numeric: tabular-nums; }

/* ตาราง */
.lfx-table-wrap { overflow: auto; background: #FFFFFF; border: 1px solid #F6DDE2; border-radius: 14px; margin: 6px 0 8px; }
.lfx-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; margin: 0 !important; }
.lfx-table thead th {
    position: sticky; top: 0; z-index: 3; background: #FFF3F5; color: #475569;
    font-weight: 700; font-size: 12.5px; text-align: left; padding: 11px 14px;
    border-bottom: 1px solid #F6DDE2; white-space: nowrap;
}
.lfx-table td { padding: 9px 14px; border-bottom: 1px solid #FBEFF1; color: #1E293B; white-space: nowrap; }
.lfx-trunc { overflow: hidden; text-overflow: ellipsis; }
.lfx-wrap { white-space: normal !important; min-width: 170px; line-height: 1.45; }
.lfx-table tbody tr:nth-child(even) td { background: #FFFBFC; }
.lfx-table tbody tr:hover td { background: #FFE8EC; }
.lfx-num { text-align: right !important; font-variant-numeric: tabular-nums; }
.lfx-muted { color: #64748B !important; }
.lfx-rank { color: #94A3B8 !important; font-size: 12px; width: 30px; }
.lfx-arrow { color: #F4A3B1; font-weight: 700; margin: 0 2px; }
.lfx-lf { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.lfx-lf-bar { width: 70px; height: 6px; border-radius: 99px; background: #FBEBEE; overflow: hidden; flex: none; }
.lfx-lf-bar > span { display: block; height: 100%; border-radius: 99px; }
.lfx-dirs-cell { white-space: normal !important; min-width: 300px; }
.lfx-dirs { display: flex; flex-direction: column; gap: 6px; }
.lfx-split { display: flex; height: 5px; border-radius: 99px; overflow: hidden; background: #FBEBEE; margin-bottom: 3px; }
.lfx-split > span { display: block; height: 100%; }
.lfx-dir { display: grid; grid-template-columns: 9px minmax(0, 1fr) auto 36px; gap: 8px; align-items: center;
           font-size: 12.5px; color: #475569; line-height: 1.45; }
.lfx-dir-sw { width: 9px; height: 9px; border-radius: 3px; }
.lfx-dir-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lfx-dir b { color: #1E293B; font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; }
.lfx-dir small { color: #94A3B8; font-size: 11.5px; text-align: right; font-variant-numeric: tabular-nums; }
.lfx-dir-lf { grid-column: 2 / -1; display: flex; flex-wrap: wrap; gap: 2px 12px; font-size: 11.5px; color: #94A3B8;
              margin: -2px 0 4px 17px; }
.lfx-dir-lf > span { white-space: nowrap; }
.lfx-dir-lf b { color: #475569; font-weight: 700; }
.lfx-badge { display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 99px; }
.lfx-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 2px 0; }
.lfx-chip { background: #FFE8EC; color: #C23B53; font-size: 12.5px; font-weight: 600; padding: 4px 12px; border-radius: 99px; }
.lfx-chip-muted { background: #F1F5F9; color: #64748B; font-weight: 500; }
.lfx-note { background: #FFF7F8; border: 1px dashed #F4B3BF; border-radius: 14px; padding: 12px 16px;
            font-size: 12.5px; color: #6B4A51; line-height: 1.6; margin-top: 10px; }
.lfx-source { font-size: 12px; color: #94A3B8; margin: 8px 4px 20px; }

.lfx-prod-cell { white-space: normal !important; min-width: 190px; }
.lfx-prod { display: flex; justify-content: space-between; gap: 10px; font-size: 12.5px; color: #475569; line-height: 1.55; }
.lfx-prod small { color: #94A3B8; font-variant-numeric: tabular-nums; }

.lfx-two { display: flex; gap: 14px; margin-top: 2px; }
.lfx-two span { font-size: 11px; color: #94A3B8; font-weight: 600; }
.lfx-two b { display: block; font-size: 19px; font-weight: 800; color: var(--c); line-height: 1.2;
             font-variant-numeric: tabular-nums; }
.lfx-leg-row.lfx-leg2 { grid-template-columns: 12px minmax(0, 1fr) 96px 96px; }
.lfx-leg2 .lfx-leg-val small { color: #94A3B8; font-size: 11px; }
.lfx-leg-head { font-size: 11.5px; color: #94A3B8; font-weight: 700; border-bottom: 1px solid #F4E4E7 !important; }
.lfx-leg-head span:nth-child(n+3) { text-align: right; }

@media (max-width: 1100px) {
  .lfx-kpi-grid.sub { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .lfx-ins-grid { grid-template-columns: 1fr; }
  .lfx-ins + .lfx-ins { border-left: none; border-top: 1px solid #FBEBEE; padding-top: 12px; }
}
@media (max-width: 700px) {
  .lfx-kpi-grid.top, .lfx-kpi-grid.sub { grid-template-columns: 1fr; }
}
</style>
"""


# =========================================================
# HELPERS (ตรรกะเดิมจากโค้ดของเพื่อน)
# =========================================================

def _lf_numeric_ratio(series):
    """แปลงค่า Load Factor ให้เป็น ratio เช่น 0.68 = 68%"""
    s = pd.to_numeric(series, errors="coerce").astype("Float64")
    valid = s.dropna().abs()
    if valid.empty:
        return s
    q50 = float(valid.quantile(0.50))
    q90 = float(valid.quantile(0.90))
    # Dataset หลักเก็บเป็น ratio; รองรับกรณี source เก็บ 68 แทน 0.68
    if q50 > 3 or q90 > 10:
        s = s / 100.0
    return s


def _lf_safe_ratio(weight, capacity):
    w = pd.to_numeric(weight, errors="coerce").fillna(0).sum()
    c = pd.to_numeric(capacity, errors="coerce").fillna(0).sum()
    return (w / c) if c not in (0, 0.0) else float("nan")


def _group(v):
    """จัดกลุ่ม 4 ช่วงหลัก (≤100%) เท่านั้น
    ค่า > 100% ไม่ใช่ระดับที่ 5 — ให้แยกไปที่ CHECK_LABEL เพื่อการตรวจสอบข้อมูลต่างหาก"""
    if pd.isna(v):
        return "ไม่ระบุ"
    p = float(v) * 100
    if p <= 25:
        return ORDER[0]
    if p <= 50:
        return ORDER[1]
    if p <= 75:
        return ORDER[2]
    if p <= 100:
        return ORDER[3]
    return CHECK_LABEL


def _is_check(v):
    """True เมื่อ Load Factor ของตัวชี้วัดที่เลือกมากกว่า 100% (รายการที่ต้องตรวจสอบ)"""
    return pd.notna(v) and float(v) > 1.0


def _num(series):
    return pd.to_numeric(
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("฿", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip(),
        errors="coerce",
    )


# =========================================================
# HELPERS (หน้าตา)
# =========================================================

def _card(name: str):
    """การ์ดพื้นขาว (CSS อยู่ใน theme.py: div[class*="st-key-tccard_"])"""
    try:
        return st.container(key=f"tccard_lf_{name}")
    except TypeError:
        return st.container(border=True)


def _wkey(base: str, options) -> str:
    """key ที่เปลี่ยนตามรายการตัวเลือก กัน error เวลาตัวเลือกเปลี่ยนตามตัวกรอง"""
    digest = hashlib.md5("|".join(map(str, options)).encode("utf-8")).hexdigest()[:10]
    return f"{base}_{digest}"


def _tint(hex_color: str, amount: float = 0.85) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (round(c + (255 - c) * amount) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def _fmt_amount(value, decimals=0):
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):,.{decimals}f}"


def _fmt_pct(ratio):
    """ratio 0.6812 -> '68.12%'"""
    if ratio is None or pd.isna(ratio):
        return "—"
    return f"{float(ratio) * 100:,.2f}%"


def _lf_cell(ratio):
    """ช่อง LF ในตาราง: ตัวเลข % + แถบสีตามช่วง"""
    if ratio is None or pd.isna(ratio):
        return '<td class="lfx-num lfx-muted">—</td>'
    color = GROUP_COLORS.get(_group(ratio), CHECK_COLOR)
    width = max(0.0, min(float(ratio), 1.5)) / 1.5 * 100
    return (
        f'<td class="lfx-num"><div class="lfx-lf">{_fmt_pct(ratio)}'
        f'<span class="lfx-lf-bar"><span style="width:{width:.1f}%;background:{color}"></span></span></div></td>'
    )


def _table_html(head, body, right_cols=(), max_height=420, col_widths=None) -> str:
    """
    col_widths (ไม่บังคับ): list ความกว้างต่อคอลัมน์ เช่น ["46px", None, "120px", "150px", "150px"]
    ใส่ None ให้คอลัมน์ที่อยากให้ยืด/หดตามพื้นที่ที่เหลือ (เช่น คอลัมน์ชื่อ/เส้นทางที่ตัวอักษรยาวไม่แน่นอน)
    เมื่อระบุ col_widths จะบังคับ table-layout:fixed ทำให้ตารางกว้างเท่ากับการ์ดเสมอ ไม่ล้นจนต้องเลื่อนแนวนอน
    (ซึ่งเป็นสาเหตุที่หัวตาราง/แถวข้อมูลดูไม่ตรงกันเวลาข้อความในคอลัมน์ชื่อยาว)
    """
    ths = "".join(
        f'<th class="{"lfx-num" if i in right_cols else ""}">{esc(h)}</th>' for i, h in enumerate(head)
    )
    colgroup = ""
    table_style = ""
    if col_widths:
        colgroup = "<colgroup>" + "".join(
            f'<col style="width:{w}">' if w else "<col>" for w in col_widths
        ) + "</colgroup>"
        table_style = ' style="table-layout:fixed"'
    return (
        f'<div class="lfx-table-wrap" style="max-height:{max_height}px">'
        f'<table class="lfx-table"{table_style}>{colgroup}<thead><tr>{ths}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def _style(fig):
    fig.update_layout(
        font=dict(family=FONT, color=MUTED, size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="white", bordercolor="#F4D6DC",
                        font=dict(family=FONT, color=TEXT, size=13)),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    try:
        fig.update_layout(barcornerradius=6)
    except (ValueError, TypeError):
        pass
    return fig


def _lf_routes(load: pd.Series, unload: pd.Series):
    """เส้นทางจาก Loading ↔ Unloading: วิ่งสลับทิศนับเป็นเส้นทางเดียวกัน
    ชื่อเส้นทางเรียงตามทิศที่วิ่งบ่อยที่สุด (แบบเดียวกับหน้า Transportation Cost)"""
    def clean(s):
        s = s.astype("string").fillna("").str.replace(r"\s+", " ", regex=True).str.strip()
        return s.mask(s.eq("") | s.str.casefold().isin(["nan", "none", "<na>"]), "ไม่ระบุ")

    a, b = clean(load), clean(unload)
    key = pd.Series(["|".join(sorted(p)) for p in zip(a, b)], index=a.index)
    top = (
        pd.DataFrame({"k": key, "a": a, "b": b})
        .groupby(["k", "a", "b"]).size().reset_index(name="n")
        .sort_values(["k", "n", "a"], ascending=[True, False, True])
        .drop_duplicates("k")
    )
    main = {k: (x, y) for k, x, y in zip(top["k"], top["a"], top["b"])}
    names = []
    for k, x, y in zip(key, a, b):
        p, q = main[k]
        if x == "ไม่ระบุ" and y == "ไม่ระบุ":
            names.append("ไม่ระบุเส้นทาง")
        elif x == y:
            names.append(f"{x} (ภายในพื้นที่)")
        else:
            names.append(f"{p} ↔ {q}")
    return pd.Series(names, index=a.index), (a + " → " + b)


def _level_table(filtered, by, label, top_rank):
    """ตารางระดับชนิดรถ / เส้นทาง: LF = ผลรวม ÷ ผลรวมความจุ (ไม่รวม Volume Outlier ในปริมาตร)"""
    t = (
        filtered.groupby(by, dropna=False)
        .agg({
            "Trip Key Unique": "nunique",
            "_Weight": "sum",
            "_Capacity": "sum",
            "_VolumeAgg": "sum",
            "_VolumeCapacityAgg": "sum",
            "_CPTK_W": "sum",
            "_TK_W": "sum",
            "_CPTK_Mean": "mean",
        })
        .reset_index()
    )
    _add_cptk(t)
    t["LF_W"] = t["_Weight"].div(t["_Capacity"].replace(0, pd.NA))
    t["LF_V"] = t["_VolumeAgg"].div(t["_VolumeCapacityAgg"].replace(0, pd.NA))
    t = t.sort_values("Trip Key Unique", ascending=False).reset_index(drop=True)
    t["_Rank"] = range(1, len(t) + 1)
    return t


# =========================================================
# ต้นทุนต่อตัน-กม. / ประเภทสินค้า (ใช้ในตารางชนิดรถ และสรุปรายเส้นทาง)
# =========================================================

def _add_cptk(t):
    """Cost/ton-km รวมกลุ่ม = ต้นทุนรวม ÷ ton-km รวม (ถัวเฉลี่ยค่าจากไฟล์ถ่วงด้วย ton-km)
    ถ้ากลุ่มไม่มี ton-km เลย ใช้ค่าเฉลี่ยธรรมดาของ Cost/ton-km รายเที่ยว"""
    t["CPTK"] = t["_CPTK_W"].div(t["_TK_W"].replace(0, float("nan"))).fillna(t["_CPTK_Mean"])
    return t


def _cptk_cell(value):
    if value is None or pd.isna(value):
        return '<td class="lfx-num lfx-muted">—</td>'
    return f'<td class="lfx-num">{float(value):,.2f}</td>'


_NO_PRODUCT = {"ไม่เจอ", "ไม่พบ", "ไม่ระบุ", "ไม่มี", "-", "—", "n/a", "na", "nan", "none", "<na>", "#n/a"}


def _product_mix(x, by):
    """ประเภทสินค้า 2 อันดับแรกของแต่ละกลุ่ม พร้อม % ของจำนวนเที่ยว"""
    # ไม่นับค่าที่ไม่ใช่ชื่อสินค้าจริง เช่น "ไม่เจอ" / "ไม่ระบุ" (% คิดจากเที่ยวที่ระบุสินค้าเท่านั้น)
    p = x[x["_Product"].ne("") & ~x["_Product"].str.casefold().isin(_NO_PRODUCT)]
    if p.empty:
        return {}
    cnt = p.groupby([by, "_Product"])["Trip Key Unique"].nunique().reset_index(name="n")
    cnt["pct"] = cnt["n"] / cnt.groupby(by)["n"].transform("sum") * 100
    cnt = cnt.sort_values([by, "n"], ascending=[True, False])
    out = {}
    for key, g in cnt.groupby(by, sort=False):
        out[str(key)] = "".join(
            f'<div class="lfx-prod"><span>{esc(str(name))}</span><small>{pct:.0f}%</small></div>'
            for name, pct in zip(g["_Product"].head(2), g["pct"].head(2))
        )
    return out


# =========================================================
# DASHBOARD
# =========================================================

def render_load_factor_dashboard(raw_load_factor_df, source_labels=None):
    """Load Factor Dashboard — ข้อมูลจริงจากไฟล์ Load Factor เท่านั้น"""
    if raw_load_factor_df is None or raw_load_factor_df.empty:
        st.info("ยังไม่มีข้อมูล Load Factor — ไปที่ Data Management แล้วอัปโหลด "
                "`ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่.xlsx`")
        return

    df = raw_load_factor_df.copy()
    df.columns = [" ".join(str(c).strip().split()) for c in df.columns]

    required = [
        "Trip Key Unique", "Trip Date", "Trip Year", "Trip Vehicle Model",
        "Trip Loading", "Trip Unloading", "Route Key", "Trip Weight",
        "Trip Weight Capacity",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error("ไฟล์ Load Factor ขาดคอลัมน์ที่จำเป็น: " + ", ".join(missing))
        return

    # ---------------- เตรียมข้อมูล (ตรรกะเดิม) ----------------
    df["_TripDate"] = pd.to_datetime(df["Trip Date"], errors="coerce", dayfirst=True)
    df["_MonthNum"] = df["_TripDate"].dt.month
    df["_Weight"] = _num(df["Trip Weight"])
    df["_Capacity"] = _num(df["Trip Weight Capacity"])
    df["_Volume"] = (_num(df["Trip Volume"]) if "Trip Volume" in df.columns
                     else pd.Series(pd.NA, index=df.index, dtype="Float64"))
    df["_VolumeCapacity"] = (_num(df["Trip Volume Capacity"]) if "Trip Volume Capacity" in df.columns
                             else pd.Series(pd.NA, index=df.index, dtype="Float64"))

    if "Trip Weight Loadfactor" in df.columns:
        df["_WeightLF"] = _lf_numeric_ratio(df["Trip Weight Loadfactor"])
    else:
        df["_WeightLF"] = df["_Weight"] / df["_Capacity"].replace(0, pd.NA)

    if "Trip Volume Loadfactor" in df.columns:
        df["_VolumeLF"] = _lf_numeric_ratio(df["Trip Volume Loadfactor"])
    else:
        df["_VolumeLF"] = df["_Volume"] / df["_VolumeCapacity"].replace(0, pd.NA)

    # Volume LF > 150% = Check/Outlier: เก็บแถวและค่าจริงไว้ แต่ไม่นับใน Volume LF รวม
    df["_VolumeOutlier"] = df["_VolumeLF"].notna() & (df["_VolumeLF"] > 1.50)
    df["_VolumeStatus"] = "OK"
    df.loc[df["_VolumeOutlier"], "_VolumeStatus"] = "Check/Outlier"
    df["_VolumeAgg"] = df["_Volume"].where(~df["_VolumeOutlier"], 0.0)
    df["_VolumeCapacityAgg"] = df["_VolumeCapacity"].where(~df["_VolumeOutlier"], 0.0)


    # ---------------- ต้นทุนต่อตัน-กม. (ใช้เมื่อไฟล์มีคอลัมน์ระยะทาง / Total Cost) ----------------
    def _opt_num(col):
        if col in df.columns:
            return _num(df[col]).astype("float64")
        return pd.Series(float("nan"), index=df.index)

    df["_Distance"] = _opt_num("Trip Distance")
    df["_Cost"] = _opt_num("Trip Total Cost")
    # น้ำหนักในไฟล์เป็น กก. หรือ ตัน: ดูจากความจุรถ (ถ้าค่ากลาง > 100 ถือว่าเป็น กก.)
    cap_med = pd.to_numeric(df["_Capacity"], errors="coerce").median()
    ton_div = 1000.0 if pd.notna(cap_med) and cap_med > 100 else 1.0
    tonkm = pd.to_numeric(df["_Weight"], errors="coerce").astype("float64") / ton_div * df["_Distance"]
    # ใช้ค่า Ton-km / Cost per ton-km ที่คำนวณไว้แล้วในไฟล์ก่อน ถ้าไม่มีค่อยคำนวณเอง
    if "Trip Ton-km" in df.columns:
        tonkm = _opt_num("Trip Ton-km").fillna(tonkm)
    df["_TonKm"] = tonkm.where(tonkm > 0)
    calc_cptk = df["_Cost"] / df["_TonKm"]
    if "Trip Cost per Ton-km" in df.columns:
        df["_CostPerTK"] = _opt_num("Trip Cost per Ton-km").fillna(calc_cptk)
    else:
        df["_CostPerTK"] = calc_cptk
    _both = df["_CostPerTK"].notna() & df["_TonKm"].notna()
    df["_CPTK_W"] = (df["_CostPerTK"] * df["_TonKm"]).where(_both)
    df["_TK_W"] = df["_TonKm"].where(_both)
    df["_CPTK_Mean"] = df["_CostPerTK"]
    df["_Product"] = (df["Trip Product Type"].astype("string").fillna("").str.strip()
                      if "Trip Product Type" in df.columns else "")
    if "Trip Run Type" in df.columns:
        df["Trip Run Type"] = df["Trip Run Type"].astype("string").fillna("").str.strip()

    for c in ["Trip Year", "Trip Vehicle Model", "Trip Loading", "Trip Unloading",
              "Route Key", "Trip Key Unique"]:
        df[c] = df[c].astype("string").fillna("").str.strip()

    # Route Key = ระดับเส้นทาง (↔) / Trip Direction = ทิศทางวิ่งจริง (→) — ห้ามสลับกัน
    if "Trip Direction" not in df.columns:
        df["Trip Direction"] = (
            df["Trip Loading"].fillna("").astype(str).str.strip()
            + " → "
            + df["Trip Unloading"].fillna("").astype(str).str.strip()
        ).str.strip(" →")
    df["Trip Direction"] = df["Trip Direction"].astype("string").fillna("").str.strip()
    df["Route Key"] = df["Route Key"].astype("string").fillna("").str.strip()

    # เส้นทางจาก Loading ↔ Unloading (ใช้ในส่วน "สรุปตามเส้นทาง")
    df["_LFRoute"], df["_LFDir"] = _lf_routes(df["Trip Loading"], df["Trip Unloading"])

    # ระดับเที่ยว: 1 แถว = 1 Trip Key ไม่ซ้ำ
    # โหมดดูทั้งคู่: ใช้ค่าที่สูงกว่าระหว่าง LF น้ำหนักกับ LF ปริมาตร
    # → ≤25% เมื่อต่ำกว่า 25% ทั้งคู่ · ช่วงอื่นถึงด้วยน้ำหนักหรือปริมาตรอย่างใดอย่างหนึ่งก็พอ
    df["_BothLF"] = pd.concat(
        [pd.to_numeric(df["_WeightLF"], errors="coerce").astype("float64"),
         pd.to_numeric(df["_VolumeLF"], errors="coerce").astype("float64")], axis=1).max(axis=1)

    trip_df = (
        df[df["Trip Key Unique"].ne("")]
        .sort_index()
        .drop_duplicates(subset=["Trip Key Unique"], keep="first")
        .copy()
    )

    st.markdown(PAGE_CSS, unsafe_allow_html=True)

    # ---------------- ตัวกรอง ----------------
    def opts(c):
        return ["ทั้งหมด"] + sorted({
            str(x).strip() for x in trip_df[c].dropna()
            if str(x).strip() not in {"", "<NA>", "nan"}
        })

    # คอลัมน์ "เที่ยววิ่ง" (ทิศทางการวิ่ง) — แมปมาจากไฟล์ต้นทางเป็น "Trip Run Type"
    # ถ้าไฟล์ยังไม่มีคอลัมน์นี้ ให้ซ่อน filter นี้ไปเฉย ๆ (ไม่ error)
    has_run_type = "Trip Run Type" in trip_df.columns and trip_df["Trip Run Type"].str.strip().ne("").any()
    has_product = trip_df["_Product"].ne("").any()
    has_cptk = trip_df["_CostPerTK"].notna().any()
    RUN_TYPE_OPTIONS = ["ทั้งหมด", "ขาขึ้น", "ขาล่อง", "รถว่างไปสาขา", "ยกเลิก"]

    fcard = _card("filters")
    fcard.markdown('<div class="lfx-title">🔎 ตัวกรองข้อมูล</div>', unsafe_allow_html=True)
    if has_run_type:
        f1, f2, f3, f6, f4, f5 = fcard.columns([0.8, 1.05, 1.3, 1.05, 1.85, 0.85])
    else:
        f1, f2, f3, f4, f5 = fcard.columns([0.85, 1.15, 1.45, 2.3, 0.9])
        f6 = None
    with f1:
        year = st.selectbox("ปี (พ.ศ.)", opts("Trip Year"), key="lf3_year")
    with f2:
        vehicle = st.selectbox("ชนิดรถ", opts("Trip Vehicle Model"), key="lf3_vehicle")
    with f3:
        route = st.selectbox("เส้นทาง (Route Key)", opts("Route Key"), key="lf3_route")
    run_type = "ทั้งหมด"
    if f6 is not None:
        with f6:
            run_type = st.selectbox("ทิศทางการวิ่ง (เที่ยววิ่ง)", RUN_TYPE_OPTIONS, key="lf3_run_type")
    with f4:
        search = st.text_input(
            "ค้นหา (รถ, เส้นทาง, ทะเบียน, ลูกค้า, เลขที่เที่ยว)",
            key="lf3_search", placeholder="ค้นหา...",
        )
    with f5:
        st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if st.button("⟳ รีเฟรชข้อมูล", key="lf3_refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    filtered = trip_df.copy()
    if year != "ทั้งหมด":
        filtered = filtered[filtered["Trip Year"] == year]
    if vehicle != "ทั้งหมด":
        filtered = filtered[filtered["Trip Vehicle Model"] == vehicle]
    if route != "ทั้งหมด":
        filtered = filtered[filtered["Route Key"] == route]
    if has_run_type and run_type != "ทั้งหมด":
        filtered = filtered[filtered["Trip Run Type"].astype(str).str.strip() == run_type]
    if search.strip():
        q = search.strip().casefold()
        search_cols = [c for c in [
            "Trip Vehicle Model", "Route Key", "Trip Direction", "Trip Loading", "Trip Unloading",
            "License Plate", "Customer", "Trip Customer", "Trip Key Unique",
        ] if c in filtered.columns]
        mask = pd.Series(False, index=filtered.index)
        for c in search_cols:
            mask |= filtered[c].astype(str).str.casefold().str.contains(q, na=False, regex=False)
        filtered = filtered[mask]

    if filtered.empty:
        st.warning("ไม่พบข้อมูลตามตัวกรองที่เลือก")
        return

    # ---------------- KPI: จำนวนเที่ยว + อัตราการใช้ความจุ (เลือกน้ำหนัก/ปริมาตร) ----------------
    trips = filtered["Trip Key Unique"].nunique()
    wlf = _lf_safe_ratio(filtered["_Weight"], filtered["_Capacity"])
    vlf = (
        _lf_safe_ratio(filtered["_VolumeAgg"], filtered["_VolumeCapacityAgg"])
        if filtered["_VolumeAgg"].notna().any() and filtered["_VolumeCapacityAgg"].notna().any()
        else None
    )
    n_outlier = int(filtered["_VolumeOutlier"].sum())

    def kpi(icon, bg, label, value, sub, meter_ratio=None):
        meter = ""
        if meter_ratio is not None and pd.notna(meter_ratio):
            color = GROUP_COLORS.get(_group(meter_ratio), "#CBD5E1")
            width = max(0.0, min(float(meter_ratio), 1.0)) * 100
            meter = f'<div class="lfx-meter"><span style="width:{width:.1f}%;background:{color}"></span></div>'
        return (
            f'<div class="lfx-kpi flat"><div class="lfx-kpi-icon" style="background:{bg}">{icon}</div>'
            f'<div class="lfx-kpi-body"><div class="lfx-kpi-label">{esc(label)}</div>'
            f'<div class="lfx-kpi-value">{esc(value)}</div>'
            f'<div class="lfx-kpi-sub">{esc(sub)}</div>{meter}</div></div>'
        )

    vol_sub = (f"ไม่นับ {n_outlier:,} เที่ยวที่ Volume LF > 150%" if n_outlier
               else "ปริมาตรรวม ÷ ความจุปริมาตรรวม")
    with _card("kpi"):
        k1, k2 = st.columns([1, 2.4], gap="large")
        with k1:
            st.markdown(
                kpi("🚚", "#FFE8EC", "จำนวนเที่ยวทั้งหมด", f"{trips:,}", "เที่ยว (นับ Trip Key ไม่ซ้ำ)"),
                unsafe_allow_html=True,
            )
        with k2:
            v1, v2, v3 = st.columns([1.3, 1.3, 1])
            with v3:
                metric = st.selectbox(
                    "ตัวชี้วัด (ใช้กับทั้งหน้า)", [BOTH, "น้ำหนัก", "ปริมาตร"], key="lf3_metric_sel3",
                    help="ดูทั้งคู่ = แสดงน้ำหนักและปริมาตรคู่กันในการ์ด กราฟ และสัดส่วน "
                         "(แท็บรายการเที่ยว/เส้นทางแบ่งกลุ่มตามน้ำหนัก)",
                )
            w_card = kpi("⚖️", "#FFF0E6", "อัตราการใช้ความจุ (น้ำหนัก)", _fmt_pct(wlf),
                         "น้ำหนักรวม ÷ ความจุน้ำหนักรวม", wlf)
            v_card = kpi("📦", "#E6F4FA", "อัตราการใช้ความจุ (ปริมาตร)",
                         _fmt_pct(vlf) if vlf is not None else "—", vol_sub, vlf)
            if metric == BOTH:
                with v1:
                    st.markdown(w_card, unsafe_allow_html=True)
                with v2:
                    st.markdown(v_card, unsafe_allow_html=True)
            else:
                with v1:
                    st.markdown(w_card if metric == "น้ำหนัก" else v_card, unsafe_allow_html=True)

    both = metric == BOTH
    shown = ["น้ำหนัก", "ปริมาตร"] if both else [metric]
    group_metric = metric                                  # ใช้แบ่งแท็บ/สถานะในตารางด้านล่าง
    metric_col = METRIC_COL[group_metric]
    group_label = "น้ำหนักหรือปริมาตร (ค่าที่สูงกว่า)" if both else group_metric
    metric_label = "น้ำหนัก + ปริมาตร" if both else metric

    def _dist(col):
        g = filtered[col].map(_group)
        d = (filtered.assign(_g=g).groupby("_g")["Trip Key Unique"].nunique()
             .reindex(ORDER, fill_value=0).reset_index(name="Trips").rename(columns={"_g": "_LFGroup"}))
        tot = int(d["Trips"].sum())
        d["Pct"] = d["Trips"] / tot * 100 if tot else 0.0
        n_chk = int(filtered.loc[filtered[col].apply(_is_check), "Trip Key Unique"].nunique())
        return d, tot, n_chk

    dists = {m: _dist(METRIC_COL[m]) for m in shown + ([BOTH] if both else [])}

    # ---------------- วิเคราะห์ Load Factor ----------------
    with _card("analysis"):
        st.markdown(f"#### วิเคราะห์ Load Factor ({metric_label})")
        st.caption(
            "ช่วง ≤25%, >25–50%, >50–75% และ >75–100% ใช้สำหรับแสดงระดับการบรรทุกเทียบกับความสามารถของรถ · "
            "เปลี่ยนตัวชี้วัดได้ที่การ์ดอัตราการใช้ความจุด้านบน"
            + (" · **รวม** = ≤25% เมื่อน้ำหนักและปริมาตรต่ำกว่า 25% ทั้งคู่ ส่วนช่วงอื่นใช้ค่าที่สูงกว่าระหว่างน้ำหนักกับปริมาตร "
               "(ถึงช่วงนั้นด้วยอย่างใดอย่างหนึ่งก็นับ) · ตรวจสอบข้อมูล = น้ำหนักหรือปริมาตรเกิน 100% · "
               "แท็บในตารางด้านล่างใช้ตัวเลข รวม" if both else "")
        )
        filtered["_LFGroup"] = filtered[metric_col].map(_group)
        dist, total, n_check = dists[group_metric]
        by_group = dict(zip(dist["_LFGroup"], dist["Trips"]))

        def _val(g):
            if not both:
                d = dists[metric][0]
                n = int(d.loc[d["_LFGroup"] == g, "Trips"].iloc[0])
                return f'<div class="lfx-kpi-value" style="color:{INS_TEXT.get(GROUP_COLORS[g], TEXT)}">{n:,}</div>'
            parts = "".join(
                f'<span>{"รวม" if m == BOTH else m}'
                f'<b>{int(dists[m][0].loc[dists[m][0]["_LFGroup"] == g, "Trips"].iloc[0]):,}</b></span>'
                for m in shown + [BOTH]
            )
            return f'<div class="lfx-two" style="--c:{INS_TEXT.get(GROUP_COLORS[g], TEXT)}">{parts}</div>'

        main_cards = "".join(
            f'<div class="lfx-kpi sub-card"><div class="lfx-kpi-icon" style="background:{_tint(GROUP_COLORS[g])}">📊</div>'
            f'<div class="lfx-kpi-body"><div class="lfx-kpi-label">{esc(g)}</div>{_val(g)}'
            f'<div class="lfx-kpi-sub">เที่ยว</div></div></div>'
            for g in ORDER
        )
        if both:
            chk_val = ('<div class="lfx-two" style="--c:#D0505C">' + "".join(
                f'<span>{"รวม" if m == BOTH else m}<b>{dists[m][2]:,}</b></span>' for m in shown + [BOTH]) + "</div>")
        else:
            chk_val = (f'<div class="lfx-kpi-value" style="color:{INS_TEXT.get(CHECK_COLOR, TEXT)}">'
                       f'{dists[metric][2]:,}</div>')
        check_card = (
            '<div class="lfx-kpi sub-card check">'
            f'<div class="lfx-kpi-icon" style="background:{_tint(CHECK_COLOR)}">🔎</div>'
            '<div class="lfx-kpi-body"><div class="lfx-kpi-label">LF &gt; 100% — ตรวจสอบข้อมูล</div>'
            f'{chk_val}<div class="lfx-kpi-sub">เที่ยว · แยกจาก 4 ช่วงหลัก</div></div></div>'
        )
        st.markdown(
            f'<div class="lfx-kpi-grid sub">{main_cards}</div>'
            f'<div class="lfx-kpi-grid" style="grid-template-columns:1fr;margin-top:10px">{check_card}</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "ค่า Load Factor ที่มากกว่า 100% สูงกว่าความสามารถในการบรรทุกที่ใช้เป็นฐานคำนวณ "
            "แต่จากข้อมูลเพียงอย่างเดียวยังไม่สามารถสรุปได้ว่าเกิดจากการบรรทุกเกินจริง Capacity ไม่ตรง "
            "หรือข้อมูลต้นทางผิด — จึงแยกไว้เป็นรายการสำหรับตรวจสอบข้อมูลเพิ่มเติม โดยยังคงค่าต้นฉบับไว้ทั้งหมด"
        )

    # ---------------- การกระจาย + สัดส่วน ----------------
    a, b = st.columns([1.35, 1], gap="medium")
    with a:
        with _card("dist"):
            st.markdown(f"#### การกระจายของอัตราการใช้ความจุ ({metric_label})")
            st.caption("จำนวนเที่ยวในแต่ละช่วง (รายเที่ยว)"
                       + (" · แท่งทึบ = น้ำหนัก · แท่งลายเส้น = ปริมาตร" if both else ""))
            fig = go.Figure()
            y_max = 1.0
            for m in shown:
                d = dists[m][0]
                y_max = max(y_max, float(d["Trips"].max() or 1))
                fig.add_trace(go.Bar(
                    name=m, x=d["_LFGroup"], y=d["Trips"],
                    marker=dict(color=[GROUP_COLORS[g] for g in d["_LFGroup"]],
                                pattern=dict(shape="/" if (both and m == "ปริมาตร") else "",
                                             fgcolor="white", size=7, solidity=0.35),
                                line=dict(color="white", width=1)),
                    text=[f"{int(n):,}<br>({p:.1f}%)" for n, p in zip(d["Trips"], d["Pct"])],
                    textposition="outside", cliponaxis=False,
                    textfont=dict(color="#334155", size=11 if both else 12),
                    hovertemplate=f"{m} · %{{x}}<br>%{{y:,}} เที่ยว<extra></extra>",
                ))
            fig.update_layout(
                height=360, margin=dict(l=10, r=10, t=30, b=30), showlegend=both, bargap=0.3,
                barmode="group", bargroupgap=0.08, legend=dict(orientation="h", y=1.12, x=0),
                xaxis=dict(title=f"อัตราการใช้ความจุ ({metric_label})"),
                yaxis=dict(title="จำนวนเที่ยว", tickformat=",", range=[0, y_max * 1.3]),
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    def _donut(m, height):
        d, tot, _ = dists[m]
        fig = go.Figure(go.Pie(
            labels=[STATUS_MAP[g] for g in d["_LFGroup"]], values=d["Trips"],
            hole=0.64, sort=False, direction="clockwise",
            marker=dict(colors=[GROUP_COLORS[g] for g in d["_LFGroup"]], line=dict(color="white", width=3)),
            text=[f"{p:.0f}%" if p >= 6 else "" for p in d["Pct"]],
            textinfo="text", textposition="inside",
            insidetextfont=dict(color="#3F2A2E", size=12, family=FONT),
            hovertemplate=f"{m} · %{{label}}<br>%{{value:,}} เที่ยว<br>%{{percent}}<extra></extra>",
        ))
        fig.update_layout(
            height=height, showlegend=False, margin=dict(l=0, r=0, t=10, b=0),
            annotations=[dict(
                text=f"<span style='font-size:12px;color:{MUTED}'>{m}</span>"
                     f"<br><b style='font-size:17px;color:{TEXT}'>{tot:,}</b>",
                x=0.5, y=0.5, showarrow=False,
            )],
        )
        _style(fig)
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    with b:
        with _card("share"):
            st.markdown(f"#### สัดส่วนกลุ่มการใช้งาน ({metric_label})")
            if both:
                c1, c2 = st.columns(2, gap="small")
                with c1:
                    _donut("น้ำหนัก", 220)
                with c2:
                    _donut("ปริมาตร", 220)
                dw, dv = dists["น้ำหนัก"][0], dists["ปริมาตร"][0]
                rows = (
                    '<div class="lfx-leg-row lfx-leg2 lfx-leg-head"><span></span><span>ช่วง</span>'
                    '<span>น้ำหนัก</span><span>ปริมาตร</span></div>'
                    + "".join(
                        f'<div class="lfx-leg-row lfx-leg2"><span class="lfx-sw" style="background:{GROUP_COLORS[g]}"></span>'
                        f'<span class="lfx-leg-name">{esc(g)}</span>'
                        f'<span class="lfx-leg-val">{int(nw):,} <small>({pw:.1f}%)</small></span>'
                        f'<span class="lfx-leg-val">{int(nv):,} <small>({pv:.1f}%)</small></span></div>'
                        for g, nw, pw, nv, pv in zip(dw["_LFGroup"], dw["Trips"], dw["Pct"], dv["Trips"], dv["Pct"])
                    )
                )
                st.markdown(f'<div class="lfx-legend">{rows}</div>', unsafe_allow_html=True)
            else:
                p1, p2 = st.columns([1, 1.25], gap="small")
                with p1:
                    _donut(metric, 280)
                with p2:
                    d = dists[metric][0]
                    rows = "".join(
                        f'<div class="lfx-leg-row"><span class="lfx-sw" style="background:{GROUP_COLORS[g]}"></span>'
                        f'<span class="lfx-leg-name">{esc(g)}<small>ระดับการบรรทุกเทียบกับความสามารถของรถ</small></span>'
                        f'<span class="lfx-leg-val">{int(n):,}</span>'
                        f'<span class="lfx-leg-pct">{p:.1f}%</span></div>'
                        for g, n, p in zip(d["_LFGroup"], d["Trips"], d["Pct"])
                    )
                    st.markdown(f'<div class="lfx-legend">{rows}</div>', unsafe_allow_html=True)

    # ---------------- ตารางชนิดรถ / เส้นทาง ----------------
    def level_card(name, title, by, label, key_base, caption):
        with _card(name):
            st.markdown(f"#### {title}")
            options = ["ทั้งหมด"] + sorted(filtered[by].dropna().astype(str).unique().tolist())
            pick = st.selectbox(f"ตัวกรอง{label}", options, index=0, key=_wkey(key_base, options))
            t = _level_table(filtered, by, label, top_rank=True)
            if pick != "ทั้งหมด":
                t = t[t[by].astype(str).eq(str(pick))]
            else:
                t = t.head(10)
            show_prod = has_product and by == "Trip Vehicle Model"
            mix = _product_mix(filtered, by) if show_prod else {}
            body = []
            for r in t.to_dict("records"):
                name = str(r[by]) or "ไม่ระบุ"
                prod = (f'<td class="lfx-prod-cell">{mix.get(str(r[by]), "—")}</td>'
                        if show_prod else "")
                body.append(
                    "<tr>"
                    f'<td class="lfx-rank">{int(r["_Rank"])}</td>'
                    f'<td class="lfx-trunc" title="{esc(name)}">{esc(name)}</td>'
                    f'<td class="lfx-num">{int(r["Trip Key Unique"]):,}</td>'
                    + prod + _lf_cell(r["LF_W"]) + _lf_cell(r["LF_V"])
                    + (_cptk_cell(r["CPTK"]) if has_cptk else "")
                    + "</tr>"
                )
            head = ["#", label, "จำนวนเที่ยว"]
            if show_prod:
                head.append("ประเภทสินค้าที่ขน")
            head += ["LF น้ำหนัก", "LF ปริมาตร"]
            if has_cptk:
                head.append("Cost/ton-km")
            right = {2} | {i for i, h in enumerate(head) if h.startswith("LF") or h == "Cost/ton-km"}
            table = _table_html(head, body, right_cols=right, max_height=400)
            st.markdown(table, unsafe_allow_html=True)
            st.caption(caption)

    d1, d2 = st.columns(2, gap="medium")
    with d1:
        level_card(
            "vehicle", "10 อันดับ ชนิดรถ (เรียงตามจำนวนเที่ยว)", "Trip Vehicle Model", "ชนิดรถ",
            "lf3_vehicle_filter",
            "LF = ผลรวม ÷ ผลรวมความจุ (ไม่ใช่ค่าเฉลี่ยรายเที่ยว) · เลือกชนิดรถเพื่อดูเฉพาะคัน"
            + (" · ประเภทสินค้าที่ขน = 2 อันดับแรก พร้อม % ของเที่ยวที่ระบุสินค้า" if has_product else "")
            + (" · Cost/ton-km = ต้นทุนรวม ÷ ton-km รวมของชนิดรถนั้น" if has_cptk else ""),
        )
    with d2:
        with _card("route"):
            st.markdown("#### 10 อันดับ ทิศทางการวิ่ง (แยกขาขึ้น/ขาล่อง ไม่รวมกัน)")
            group_cols = ["Trip Direction"]
            if has_run_type:
                group_cols.append("Trip Run Type")
            rt = (
                filtered.groupby(group_cols, dropna=False)
                .agg({
                    "Trip Key Unique": "nunique",
                    "_Weight": "sum", "_Capacity": "sum",
                    "_VolumeAgg": "sum", "_VolumeCapacityAgg": "sum",
                })
                .reset_index()
            )
            rt["LF_W"] = rt["_Weight"].div(rt["_Capacity"].replace(0, pd.NA))
            rt["LF_V"] = rt["_VolumeAgg"].div(rt["_VolumeCapacityAgg"].replace(0, pd.NA))
            rt = rt.sort_values("Trip Key Unique", ascending=False).reset_index(drop=True)

            dir_options = ["ทั้งหมด"] + sorted(filtered["Trip Direction"].dropna().astype(str).unique().tolist())
            pick_dir = st.selectbox("ตัวกรองทิศทาง", dir_options, index=0,
                                    key=_wkey("lf3_dir_filter", dir_options))
            if pick_dir != "ทั้งหมด":
                rt = rt[rt["Trip Direction"].astype(str).eq(str(pick_dir))]
            else:
                rt = rt.head(10)

            head = ["#", "ทิศทางการวิ่ง (เที่ยว)"]
            if has_run_type:
                head.append("เที่ยววิ่ง")
            head += ["จำนวนเที่ยว", "LF น้ำหนัก", "LF ปริมาตร"]
            body = []
            for i, r in enumerate(rt.to_dict("records"), 1):
                direction_raw = str(r["Trip Direction"]) or "ไม่ระบุ"
                direction_txt = esc(direction_raw).replace(" → ", ARROW)
                cells = [f'<td class="lfx-rank">{i}</td>',
                         f'<td class="lfx-wrap" title="{esc(direction_raw)}">{direction_txt}</td>']
                if has_run_type:
                    cells.append(f'<td class="lfx-muted">{esc(str(r.get("Trip Run Type") or "ไม่ระบุ"))}</td>')
                cells.append(f'<td class="lfx-num">{int(r["Trip Key Unique"]):,}</td>')
                cells += [_lf_cell(r["LF_W"]), _lf_cell(r["LF_V"])]
                body.append("<tr>" + "".join(cells) + "</tr>")
            right = {len(head) - 3, len(head) - 2, len(head) - 1}
            st.markdown(
                _table_html(head, body, right_cols=right, max_height=400),
                unsafe_allow_html=True,
            )
            st.caption(
                "แยกเป็นรายทิศทางจริงของเที่ยว (→) ไม่รวมขาขึ้น-ขาล่องของเส้นทางเดียวกันเข้าด้วยกัน "
                "จึงไม่เอาเที่ยวขาไปกับขากลับมาเฉลี่ย LF รวมกัน · LF = ผลรวม ÷ ผลรวมความจุของทิศทางนั้นเท่านั้น"
                + (" · เที่ยววิ่ง = ค่าจากคอลัมน์ เที่ยววิ่ง ของไฟล์ต้นทาง" if has_run_type else "")
            )

    # ---------------- รายการเที่ยว (รายตัว ไม่ใช่รวมตามเส้นทาง) ----------------
    trip_status_color = {g: GROUP_COLORS[g] for g in ORDER}
    trip_status_color["ตรวจสอบข้อมูล"] = CHECK_COLOR

    def trip_badge(text):
        color = trip_status_color.get(text, "#CBD5E1")
        return (f'<span class="lfx-badge" style="background:{_tint(color, 0.7)};color:#3F2A2E">'
                f'{esc(text)}</span>')

    with _card("trip_list"):
        st.markdown(f"#### รายการเที่ยว (เลือกกลุ่มเพื่อดูรายละเอียดเป็นรายเที่ยว — แบ่งกลุ่มตาม{group_label})")
        st.caption(
            "แต่ละแถว = 1 เที่ยว (Trip Key Unique ไม่ซ้ำ) · เลือกแท็บเพื่อกรองตามระดับการบรรทุก · "
            "แท็บ \"ตรวจสอบข้อมูล\" เป็นรายการสำหรับตรวจสอบ ไม่ใช่ระดับการบรรทุกหลัก"
        )
        tl_tab_labels = (
            [f"ทั้งหมด ({trips:,})"]
            + [f"{g} ({by_group.get(g, 0):,})" for g in ORDER]
            + [f"ตรวจสอบข้อมูล (>100%) ({n_check:,})"]
        )
        tl_tabs = st.tabs(tl_tab_labels)
        for tl_tab, tl_grp in zip(tl_tabs, [None] + ORDER + [CHECK_LABEL]):
            with tl_tab:
                tx = filtered if tl_grp is None else filtered[filtered["_LFGroup"] == tl_grp]
                if tx.empty:
                    st.info("ไม่มีเที่ยวในกลุ่มนี้")
                    continue

                def _trip_status(v):
                    if pd.isna(v):
                        return "ไม่ระบุ"
                    g_lf = _group(v)
                    return "ตรวจสอบข้อมูล" if g_lf == CHECK_LABEL else g_lf

                tx_show = tx.sort_values(metric_col, ascending=False, na_position="last").head(300)
                tx_status = tx_show[metric_col].map(_trip_status)
                body = []
                for (_, r), s in zip(tx_show.iterrows(), tx_status):
                    date_txt = r["_TripDate"].strftime("%d/%m/%Y") if pd.notna(r["_TripDate"]) else "—"
                    direction = esc(str(r["Trip Direction"] or r["_LFDir"])).replace(" → ", ARROW)
                    body.append(
                        "<tr>"
                        f'<td class="lfx-muted">{date_txt}</td>'
                        f'<td class="lfx-muted">{esc(str(r["Trip Key Unique"]))}</td>'
                        f"<td>{direction}</td>"
                        f'<td class="lfx-muted">{esc(str(r["Trip Vehicle Model"]))}</td>'
                        + _lf_cell(r["_WeightLF"]) + _lf_cell(r["_VolumeLF"])
                        + f"<td>{trip_badge(s)}</td></tr>"
                    )
                st.caption(f"{len(tx):,} เที่ยว · แสดงสูงสุด 300 เที่ยว (เรียงตาม LF {group_label} มากไปน้อย)")
                st.markdown(
                    _table_html(
                        ["วันที่", "เลขที่เที่ยว", "ทิศทางการวิ่ง", "ชนิดรถ",
                         "LF น้ำหนัก", "LF ปริมาตร", "สถานะ"],
                        body, right_cols={4, 5}, max_height=420,
                    ),
                    unsafe_allow_html=True,
                )
                tl_export = pd.DataFrame({
                    "วันที่": tx["_TripDate"].dt.strftime("%d/%m/%Y"),
                    "เลขที่เที่ยว": tx["Trip Key Unique"],
                    "เส้นทาง (Route Key)": tx["Route Key"],
                    "ทิศทางการวิ่ง": tx["Trip Direction"],
                    "ชนิดรถ": tx["Trip Vehicle Model"],
                    "LF น้ำหนัก (%)": (tx["_WeightLF"].astype("float64") * 100).round(2),
                    "LF ปริมาตร (%)": (tx["_VolumeLF"].astype("float64") * 100).round(2),
                })
                st.download_button(
                    f"⬇️ ดาวน์โหลด {len(tx):,} เที่ยว (CSV)",
                    tl_export.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"load_factor_trips_{(tl_grp or 'all').replace('>', 'gt').replace('–','-').replace('%','pct').replace(' ','_')}.csv",
                    mime="text/csv",
                    key=f"lf3_dl_triplist_{tl_grp or 'all'}",
                )

    # ---------------- สรุปตามเส้นทาง (Loading ↔ Unloading) ----------------
    status_color = {g: GROUP_COLORS[g] for g in ORDER}
    status_color["ตรวจสอบข้อมูล"] = CHECK_COLOR

    def badge(text):
        color = status_color.get(text, "#CBD5E1")
        return (f'<span class="lfx-badge" style="background:{_tint(color, 0.7)};color:#3F2A2E">'
                f'{esc(text)}</span>')

    lf_key = {"น้ำหนัก": "LF_W", "ปริมาตร": "LF_V"}.get(group_metric, "LF_B")

    with _card("trips"):
        st.markdown(f"#### สรุปรวมรายเส้นทาง (ไม่ใช่รายเที่ยว — แบ่งกลุ่มตาม{group_label})")
        st.caption(
            "เส้นทางจาก Loading ↔ Unloading (วิ่งสลับทิศนับเป็นเส้นทางเดียวกัน) · "
            f"แบ่งกลุ่มเที่ยวตาม{group_label} · LF ของแต่ละทิศทางคำนวณแยกจากกัน "
            "(ผลรวม ÷ ผลรวมความจุ เฉพาะเที่ยวของทิศทางนั้น ไม่ปนกับทิศตรงข้าม) · "
            "แท็บ \"ตรวจสอบข้อมูล\" เป็นรายการสำหรับตรวจสอบ ไม่ใช่ระดับการบรรทุกหลัก"
        )

        # ---------- ตัวเลือกเฉพาะการ์ดนี้: เลือกเส้นทาง + ขาขึ้น/ขาล่อง (แยกรายเส้นทาง) ----------
        all_routes = (filtered.groupby("_LFRoute")["Trip Key Unique"]
                      .nunique().sort_values(ascending=False))
        route_pick_opts = all_routes.index.tolist()
        RUN_OPTS = ["ทั้งหมด", "ขาขึ้น", "ขาล่อง"]
        s1, s2 = st.columns([2.6, 1], gap="medium")
        with s1:
            sel_routes = st.multiselect(
                "เลือกเส้นทางที่ต้องการดู (ไม่เลือก = ทุกเส้นทาง)",
                route_pick_opts,
                format_func=lambda r: f"{r}  ({all_routes[r]:,} เที่ยว)",
                key=_wkey("lf3_sum_routes", route_pick_opts),
                placeholder="พิมพ์ค้นหา หรือเลือกได้หลายเส้นทาง",
            )
        sel_run = "ทั้งหมด"      # ใช้เมื่อไม่ได้เลือกเส้นทาง (กรองทุกเส้นทางพร้อมกัน)
        route_run = {}           # {เส้นทาง: ขาขึ้น/ขาล่อง/ทั้งหมด} ใช้เมื่อเลือกเส้นทาง
        with s2:
            if not has_run_type:
                st.caption("ไฟล์ยังไม่มีคอลัมน์ เที่ยววิ่ง (Trip Run Type) จึงกรองขาขึ้น/ขาล่องไม่ได้")
            elif not sel_routes:
                sel_run = st.selectbox("ขาขึ้น / ขาล่อง", RUN_OPTS, key="lf3_sum_run")
            else:
                st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
                st.caption("เลือกขาขึ้น / ขาล่อง แยกแต่ละเส้นทางด้านล่าง")

        # ตัวเลือกขาขึ้น/ขาล่อง แยกรายเส้นทาง (สูงสุด 3 คอลัมน์ต่อแถว)
        if has_run_type and sel_routes:
            run_cols = st.columns(min(len(sel_routes), 3), gap="medium")
            for i, r in enumerate(sel_routes):
                with run_cols[i % len(run_cols)]:
                    route_run[r] = st.radio(
                        r, RUN_OPTS, horizontal=True,
                        key="lf3_sum_run_" + hashlib.md5(r.encode("utf-8")).hexdigest()[:10],
                    )

        run_col = (filtered["Trip Run Type"].astype(str).str.strip()
                   if has_run_type else pd.Series("", index=filtered.index))
        sf = filtered
        if sel_routes:
            sel_mask = pd.Series(False, index=filtered.index)
            for r in sel_routes:
                m = filtered["_LFRoute"] == r
                d = route_run.get(r, "ทั้งหมด")
                if d != "ทั้งหมด":
                    m &= run_col == d
                sel_mask |= m
            sf = filtered[sel_mask]
        elif sel_run != "ทั้งหมด":
            sf = filtered[run_col == sel_run]

        sf_trips = sf["Trip Key Unique"].nunique()
        sf_by_group = sf.groupby("_LFGroup")["Trip Key Unique"].nunique().to_dict()
        sf_check = int(sf.loc[sf[metric_col].apply(_is_check), "Trip Key Unique"].nunique())
        route_total = sf.groupby("_LFRoute")["Trip Key Unique"].nunique()

        tab_labels = (
            [f"ทั้งหมด ({sf_trips:,})"]
            + [f"{g} ({sf_by_group.get(g, 0):,})" for g in ORDER]
            + [f"ตรวจสอบข้อมูล (>100%) ({sf_check:,})"]
        )
        tabs = st.tabs(tab_labels)
        for tab, grp in zip(tabs, [None] + ORDER + [CHECK_LABEL]):
            with tab:
                x = sf if grp is None else sf[sf["_LFGroup"] == grp]
                if x.empty:
                    st.info("ไม่มีเที่ยวในกลุ่มนี้")
                    continue
                rs = (
                    x.groupby("_LFRoute")
                    .agg({
                        "Trip Key Unique": "nunique",
                        "_Weight": "sum", "_Capacity": "sum",
                        "_VolumeAgg": "sum", "_VolumeCapacityAgg": "sum",
                        "_CPTK_W": "sum", "_TK_W": "sum", "_CPTK_Mean": "mean",
                    })
                    .reset_index()
                    .rename(columns={"Trip Key Unique": "Trips"})
                )
                _add_cptk(rs)
                rs["LF_W"] = rs["_Weight"].div(rs["_Capacity"].replace(0, pd.NA))
                rs["LF_V"] = rs["_VolumeAgg"].div(rs["_VolumeCapacityAgg"].replace(0, pd.NA))
                rs["LF_B"] = pd.concat([pd.to_numeric(rs["LF_W"], errors="coerce"),
                                        pd.to_numeric(rs["LF_V"], errors="coerce")], axis=1).max(axis=1)
                rs["Share"] = rs["Trips"] / rs["_LFRoute"].map(route_total) * 100
                rs = rs.sort_values("Trips", ascending=False).reset_index(drop=True)
                outlier_routes = set(x.loc[x["_VolumeOutlier"], "_LFRoute"])

                # LF แยกตามทิศทางวิ่งจริง (→) ของแต่ละเส้นทาง: คำนวณเฉพาะเที่ยวของทิศนั้น
                # ไม่ปนกับทิศตรงข้าม ตามที่ข้อมูลนับเป็นรายเที่ยว
                dir_stats = (
                    x.groupby(["_LFRoute", "_LFDir"])
                    .agg(
                        n=("Trip Key Unique", "nunique"),
                        _Weight=("_Weight", "sum"),
                        _Capacity=("_Capacity", "sum"),
                        _VolumeAgg=("_VolumeAgg", "sum"),
                        _VolumeCapacityAgg=("_VolumeCapacityAgg", "sum"),
                        _CPTK_W=("_CPTK_W", "sum"), _TK_W=("_TK_W", "sum"),
                        _CPTK_Mean=("_CPTK_Mean", "mean"),
                    )
                    .reset_index()
                )
                _add_cptk(dir_stats)
                dir_stats["LF_W"] = dir_stats["_Weight"].div(dir_stats["_Capacity"].replace(0, pd.NA))
                dir_stats["LF_V"] = dir_stats["_VolumeAgg"].div(dir_stats["_VolumeCapacityAgg"].replace(0, pd.NA))
                dir_stats = dir_stats.sort_values(["_LFRoute", "n"], ascending=[True, False])

                def dirs_block(g):
                    """ทิศทางวิ่ง: แถบสัดส่วน + บรรทัดละทิศทาง พร้อม LF เฉพาะทิศนั้น
                    (สีเข้ม = ทิศที่วิ่งบ่อยกว่า) — แต่ละทิศทางเฉลี่ย LF ของตัวเองเท่านั้น ไม่รวมกับทิศตรงข้าม"""
                    total_n = float(g["n"].sum()) or 1.0
                    colors = [DIR_COLORS[min(k, len(DIR_COLORS) - 1)] for k in range(len(g))]
                    bar = "".join(
                        f'<span style="width:{n / total_n * 100:.1f}%;background:{c}"></span>'
                        for n, c in zip(g["n"], colors)
                    )
                    lines = "".join(
                        f'<div class="lfx-dir"><span class="lfx-dir-sw" style="background:{c}"></span>'
                        f'<span class="lfx-dir-name">{esc(str(d)).replace(" → ", ARROW)}</span>'
                        f'<b>{int(n):,}</b><small>{n / total_n * 100:.0f}%</small></div>'
                        f'<div class="lfx-dir-lf"><span>LF น้ำหนัก <b>{_fmt_pct(lfw)}</b></span>'
                        f'<span>LF ปริมาตร <b>{_fmt_pct(lfv)}</b></span>'
                        + (f'<span>Cost/ton-km <b>{_fmt_amount(cp, 2)}</b></span>' if has_cptk else "")
                        + '</div>'
                        for d, n, c, lfw, lfv, cp in zip(g["_LFDir"], g["n"], colors, g["LF_W"], g["LF_V"], g["CPTK"])
                    )
                    return f'<div class="lfx-dirs"><div class="lfx-split">{bar}</div>{lines}</div>'

                dir_text = {r: dirs_block(g) for r, g in dir_stats.groupby("_LFRoute")}

                head = ["#", "เส้นทาง", "จำนวนเที่ยว"]
                if grp is not None:
                    head.append("% ของเที่ยวในเส้นทาง")
                head += ["ทิศทางการวิ่ง (LF แยกตามทิศ)", "LF น้ำหนัก (รวมเส้นทาง)", "LF ปริมาตร (รวมเส้นทาง)"]
                if has_cptk:
                    head.append("Cost/ton-km (รวมเส้นทาง)")
                head.append("สถานะเส้นทาง")
                body = []
                for i, r in enumerate(rs.head(300).to_dict("records"), 1):
                    lf_v = r[lf_key]
                    if pd.notna(lf_v):
                        g_lf = _group(lf_v)
                        status = "ตรวจสอบข้อมูล" if g_lf == CHECK_LABEL else g_lf
                    elif group_metric == "ปริมาตร" and r["_LFRoute"] in outlier_routes:
                        status = "ตรวจสอบข้อมูล"   # มีแต่เที่ยว Volume LF > 150% จึงไม่มี LF รวม
                    else:
                        status = "ไม่ระบุ"
                    cells = [
                        f'<td class="lfx-rank">{i}</td>',
                        f'<td><b>{esc(r["_LFRoute"])}</b></td>',
                        f'<td class="lfx-num">{int(r["Trips"]):,}</td>',
                    ]
                    if grp is not None:
                        cells.append(f'<td class="lfx-num lfx-muted">{r["Share"]:.1f}%</td>')
                    cells.append(f'<td class="lfx-dirs-cell">{dir_text.get(r["_LFRoute"], "")}</td>')
                    cells += [_lf_cell(r["LF_W"]), _lf_cell(r["LF_V"])]
                    if has_cptk:
                        cells.append(_cptk_cell(r["CPTK"]))
                    cells.append(f"<td>{badge(status)}</td>")
                    body.append("<tr>" + "".join(cells) + "</tr>")
                n_num = 4 if grp is not None else 3
                right = {2, n_num + 1, n_num + 2} | ({3} if grp is not None else set()) \
                    | ({n_num + 3} if has_cptk else set())
                st.markdown(_table_html(head, body, right_cols=right, max_height=420),
                            unsafe_allow_html=True)
                st.caption(
                    "หมายเหตุ: \"LF น้ำหนัก (รวมเส้นทาง)\" และ \"LF ปริมาตร (รวมเส้นทาง)\" คำนวณจากทั้งสองทิศทางรวมกัน "
                    "ส่วนตัวเลข LF ในคอลัมน์ \"ทิศทางการวิ่ง\" คำนวณแยกเฉพาะเที่ยวของทิศทางนั้น ๆ เท่านั้น "
                    "(เช่น ท่าลี่→เชียงใหม่ กับ เชียงใหม่→ท่าลี่ จะมีค่า LF ของตัวเอง ไม่เฉลี่ยรวมกัน)"
                )

                export = pd.DataFrame({
                    "เส้นทาง": rs["_LFRoute"],
                    "จำนวนเที่ยว": rs["Trips"],
                    **({"% ของเที่ยวในเส้นทาง": rs["Share"].round(1)} if grp is not None else {}),
                    "LF น้ำหนัก รวมเส้นทาง (%)": (rs["LF_W"].astype("float64") * 100).round(2),
                    "LF ปริมาตร รวมเส้นทาง (%)": (rs["LF_V"].astype("float64") * 100).round(2),
                    **({"Cost/ton-km รวมเส้นทาง": pd.to_numeric(rs["CPTK"], errors="coerce").round(4)}
                       if has_cptk else {}),
                })
                dir_export = dir_stats[dir_stats["_LFRoute"].isin(rs["_LFRoute"])].copy()
                dir_export = pd.DataFrame({
                    "เส้นทาง": dir_export["_LFRoute"],
                    "ทิศทางการวิ่ง": dir_export["_LFDir"],
                    "จำนวนเที่ยว (ทิศนี้)": dir_export["n"],
                    "LF น้ำหนัก ทิศนี้ (%)": (dir_export["LF_W"].astype("float64") * 100).round(2),
                    "LF ปริมาตร ทิศนี้ (%)": (dir_export["LF_V"].astype("float64") * 100).round(2),
                    **({"Cost/ton-km ทิศนี้": pd.to_numeric(dir_export["CPTK"], errors="coerce").round(4)}
                       if has_cptk else {}),
                })
                dl1, dl2 = st.columns(2)
                with dl1:
                    st.download_button(
                        f"⬇️ ดาวน์โหลด {len(rs):,} เส้นทาง — รวมทั้ง 2 ทิศ (CSV)",
                        export.to_csv(index=False).encode("utf-8-sig"),
                        file_name="load_factor_routes.csv", mime="text/csv",
                        key=f"lf3_dl_route_{grp or 'all'}",
                    )
                with dl2:
                    st.download_button(
                        f"⬇️ ดาวน์โหลด {len(dir_export):,} แถว — แยกรายทิศทาง (CSV)",
                        dir_export.to_csv(index=False).encode("utf-8-sig"),
                        file_name="load_factor_routes_by_direction.csv", mime="text/csv",
                        key=f"lf3_dl_route_dir_{grp or 'all'}",
                    )

        # ---------- ดูรายเที่ยวของเส้นทางที่เลือก ----------
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        route_opts = route_total.sort_values(ascending=False).index.tolist()
        r1, r2 = st.columns([2, 1])
        with r1:
            pick_route = st.selectbox(
                "ดูรายเที่ยวของเส้นทาง", ["— เลือกเส้นทาง —"] + route_opts,
                key=_wkey("lf3_trip_route", route_opts),
            )
        if pick_route != "— เลือกเส้นทาง —":
            x = sf[sf["_LFRoute"] == pick_route]
            dir_opts = x["_LFDir"].value_counts().index.tolist()
            with r2:
                pick_dir = st.selectbox("ทิศทางวิ่ง", ["ทั้งหมด"] + dir_opts,
                                        key=_wkey("lf3_trip_dir", dir_opts))
            if pick_dir != "ทั้งหมด":
                x = x[x["_LFDir"] == pick_dir]

            # สรุป LF ของทิศทางที่เลือก (หรือทุกทิศทางแยกกัน ถ้าไม่ได้เลือกทิศใดทิศหนึ่ง)
            pick_dir_summary = (
                x.groupby("_LFDir")
                .agg(
                    n=("Trip Key Unique", "nunique"),
                    _Weight=("_Weight", "sum"), _Capacity=("_Capacity", "sum"),
                    _VolumeAgg=("_VolumeAgg", "sum"), _VolumeCapacityAgg=("_VolumeCapacityAgg", "sum"),
                )
                .reset_index()
            )
            pick_dir_summary["LF_W"] = pick_dir_summary["_Weight"].div(pick_dir_summary["_Capacity"].replace(0, pd.NA))
            pick_dir_summary["LF_V"] = pick_dir_summary["_VolumeAgg"].div(pick_dir_summary["_VolumeCapacityAgg"].replace(0, pd.NA))
            summary_chips = "".join(
                f'<span class="lfx-chip">{esc(str(row["_LFDir"]))}: '
                f'{int(row["n"]):,} เที่ยว · LF น้ำหนัก {_fmt_pct(row["LF_W"])} · LF ปริมาตร {_fmt_pct(row["LF_V"])}</span>'
                for _, row in pick_dir_summary.iterrows()
            )
            if summary_chips:
                st.markdown(f'<div class="lfx-chips">{summary_chips}</div>', unsafe_allow_html=True)

            show = x.head(200)
            # สถานะตามน้ำหนัก (เหมือนเดิม) แต่ Volume LF > 150% จะเป็น "ตรวจสอบข้อมูล" เสมอ
            def _row_status(v):
                if pd.isna(v):
                    return "ไม่ระบุ"
                g_lf = _group(v)
                return "ตรวจสอบข้อมูล" if g_lf == CHECK_LABEL else g_lf

            status = show["_WeightLF"].map(_row_status)
            status = status.where(~show["_VolumeStatus"].eq("Check/Outlier"), "ตรวจสอบข้อมูล")
            body = []
            for (_, r), s in zip(show.iterrows(), status):
                date_txt = r["_TripDate"].strftime("%d/%m/%Y") if pd.notna(r["_TripDate"]) else "—"
                direction = esc(str(r["_LFDir"])).replace(" → ", ' <span class="lfx-arrow">→</span> ')
                body.append(
                    "<tr>"
                    f'<td class="lfx-muted">{date_txt}</td>'
                    f"<td>{direction}</td>"
                    f'<td class="lfx-muted">{esc(str(r["Trip Vehicle Model"]))}</td>'
                    + _lf_cell(r["_WeightLF"]) + _lf_cell(r["_VolumeLF"])
                    + f"<td>{badge(s)}</td></tr>"
                )
            st.caption(f"{len(x):,} เที่ยว · แสดงสูงสุด 200 เที่ยว")
            st.markdown(
                _table_html(
                    ["วันที่", "ทิศทางการวิ่ง", "ชนิดรถ",
                     "อัตราการใช้ความจุ (น้ำหนัก)", "อัตราการใช้ความจุ (ปริมาตร)", "สถานะ"],
                    body, right_cols={3, 4}, max_height=380,
                ),
                unsafe_allow_html=True,
            )
            export = pd.DataFrame({
                "วันที่": x["_TripDate"].dt.strftime("%d/%m/%Y"),
                "เส้นทาง": x["_LFRoute"],
                "ทิศทางการวิ่ง": x["_LFDir"],
                "ชนิดรถ": x["Trip Vehicle Model"],
                "LF น้ำหนัก (%)": (x["_WeightLF"].astype("float64") * 100).round(2),
                "LF ปริมาตร (%)": (x["_VolumeLF"].astype("float64") * 100).round(2),
                "สถานะปริมาตร": x["_VolumeStatus"],
            })
            st.download_button(
                f"⬇️ ดาวน์โหลด {len(x):,} เที่ยว (CSV)",
                export.to_csv(index=False).encode("utf-8-sig"),
                file_name="load_factor_trips.csv", mime="text/csv", key="lf3_dl_trips",
            )


    st.markdown(
        '<div class="lfx-note">📌 ช่วง ≤25%, &gt;25–50%, &gt;50–75% และ &gt;75–100% ใช้สำหรับแสดงระดับการบรรทุก'
        "เทียบกับความสามารถของรถ ส่วนค่า Load Factor ที่มากกว่า 100% จะแยกเป็นรายการสำหรับตรวจสอบข้อมูลเพิ่มเติม "
        "โดยยังคงค่าต้นฉบับไว้ (ไม่ cap ไม่ลบแถว) ทั้งในภาพรวม ชนิดรถ และเส้นทาง — "
        "ค่า Volume LF &gt; 150% ก็จัดอยู่ในรายการตรวจสอบข้อมูลนี้เช่นกัน และไม่นำมาคำนวณ Volume LF รวม · "
        "ในตาราง \"สรุปรวมรายเส้นทาง\" ตัวเลข LF ของแต่ละทิศทาง (เช่น A→B และ B→A) คำนวณแยกจากเที่ยวของทิศนั้นเท่านั้น "
        "ไม่ถูกเฉลี่ยรวมกับทิศตรงข้าม</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="lfx-source">Source (Load Factor only): '
        + esc(" | ".join(source_labels) if source_labels else "ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่.xlsx")
        + "</div>",
        unsafe_allow_html=True,
    )