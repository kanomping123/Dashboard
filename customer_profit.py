"""
customer_profit.py
------------------
แดชบอร์ด "กำไรลูกค้าและประเภทสินค้า" (ธีมเดียวกับหน้าอื่น)

แหล่งข้อมูล
- อ่านไฟล์ Excel ในโฟลเดอร์ data ที่ชื่อมีคำว่า "กำไรลูกค้า" เช่น "กำไรลูกค้าและประเภทสินค้า.xlsx"
  (ถ้ามีหลายไฟล์ ใช้ไฟล์ที่แก้ไขล่าสุด) — อ่านจากไฟล์โดยตรง ไม่ผ่านฐานข้อมูล
- 1 แถว = 1 ลูกค้า (ถ้าลูกค้าซ้ำ จะรวมยอดให้)

คอลัมน์ที่ใช้ (อ่านค่าจากไฟล์ตรง ๆ ไม่คำนวณใหม่)
- ผู้รับ_encoded                           → รหัสลูกค้า
- รายได้รวมลูกค้า                          → รายได้
- ต้นทุนที่ปันส่วนตามยอดรายได้ของลูกค้า    → ต้นทุนปันส่วน
- กำไรลูกค้ารวม                            → กำไร
- ประเภทสินค้ารายได้สูงสุด                  → ประเภทสินค้า
ค่าที่คำนวณเพิ่มเพื่อแสดงผลอย่างเดียว: อัตรากำไร = กำไร ÷ รายได้
"""

import hashlib
import unicodedata
from html import escape as esc
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from transport_cost_route import (
    PAGE_CSS,
    PALETTE,
    _card,
    _money as _money_raw,
    _money_full as _money_full_raw,
    _neg,
    _style,
    _table_html,
    _tint,
    _wkey,
)

DATA_FOLDER = Path("data")
SOURCE_KEYWORD = "กำไรลูกค้า"
PLOT_CONFIG = {"displayModeBar": False}

COLS = {
    "customer": ["ผู้รับ_encoded", "ผู้รับ", "รหัสลูกค้า", "ลูกค้า", "ชื่อลูกค้า"],
    "revenue": ["รายได้รวมลูกค้า", "รายได้รวม", "รายได้"],
    "cost": ["ต้นทุนที่ปันส่วนตามยอดรายได้ของลูกค้า", "ต้นทุนที่ปันส่วน", "ต้นทุน"],
    "profit": ["กำไรลูกค้ารวม", "กำไรรวม", "กำไร"],
    "ptype": ["ประเภทสินค้ารายได้สูงสุด", "ประเภทสินค้า"],
}
REV_COLOR, COST_COLOR, PROFIT_COLOR, LOSS_COLOR = "#7CC4D6", "#F07C8C", "#86CFA3", "#EC7F86"

EXTRA_CSS = """
<style>
.cp-badge { display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 99px; color: #3F2A2E; }
.cp-id { font-variant-numeric: tabular-nums; color: #334155; font-weight: 600; }
.cp-margin { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.cp-margin-bar { width: 70px; height: 6px; border-radius: 99px; background: #FBEBEE; overflow: hidden; flex: none; }
.cp-margin-bar > span { display: block; height: 100%; border-radius: 99px; }
.cp-pos { color: #2F8A5B !important; }
.cp-seg-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 6px; }
.cp-seg { background: #FFFFFF; border: 1px solid #F4D8DE; border-top: 4px solid var(--c); border-radius: 16px; padding: 14px 16px; }
.cp-seg-head { display: flex; gap: 10px; align-items: center; }
.cp-seg-icon { width: 36px; height: 36px; border-radius: 11px; display: grid; place-items: center; font-size: 18px; flex: none; }
.cp-seg-name { font-size: 15px; font-weight: 800; color: #0F172A; }
.cp-seg-rule { font-size: 12px; color: #94A3B8; }
.cp-seg-big { font-size: 26px; font-weight: 800; color: var(--c); margin-top: 10px; line-height: 1.1; }
.cp-seg-big small { font-size: 13px; font-weight: 600; color: #64748B; }
.cp-seg-bar { height: 6px; border-radius: 99px; background: #FBEBEE; overflow: hidden; margin: 10px 0 8px; }
.cp-seg-bar > span { display: block; height: 100%; border-radius: 99px; }
.cp-seg-row { display: grid; grid-template-columns: 56px auto 1fr; gap: 8px; align-items: baseline; font-size: 13px; color: #64748B; line-height: 1.8; }
.cp-seg-row b { color: #1E293B; font-variant-numeric: tabular-nums; }
.cp-seg-row small { color: #94A3B8; text-align: right; }
.cp-seg-loss { display: inline-block; margin-top: 6px; font-size: 12px; font-weight: 700; color: #C23B53; background: #FFE8EC; padding: 2px 10px; border-radius: 99px; }
.cp-seg-top { margin-top: 8px; font-size: 12px; color: #94A3B8; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.cp-seg-top span { width: 100%; }
.cp-seg-top code { background: #F8FAFC; border: 1px solid #E2E8F0; color: #334155; border-radius: 8px; padding: 1px 8px; font-size: 12px; }
.cp-seg-action { font-size: 12.5px; color: #475569; margin-top: 8px; }
.cp-seg-axis { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; font-size: 12px; font-weight: 700; color: #94A3B8; text-align: center; margin-top: 4px; }
@media (max-width: 800px) { .cp-seg-grid, .cp-seg-axis { grid-template-columns: 1fr; } .cp-seg-axis { display: none; } }

</style>
"""


# =========================================================
# ข้อมูล
# =========================================================

def _norm(text) -> str:
    return "".join(unicodedata.normalize("NFC", str(text)).split()).casefold()


def find_source_file():
    if not DATA_FOLDER.exists():
        return None
    files = [
        f for f in DATA_FOLDER.iterdir()
        if f.is_file() and f.suffix.lower() in {".xlsx", ".xlsm", ".xls"}
        and not f.name.startswith("~$") and _norm(SOURCE_KEYWORD) in _norm(f.stem)
    ]
    return max(files, key=lambda f: f.stat().st_mtime_ns) if files else None


def _find(df, names):
    lookup = {_norm(c): c for c in df.columns}
    for n in names:  # ชื่อตรงก่อน
        if _norm(n) in lookup:
            return lookup[_norm(n)]
    for n in names:  # แล้วค่อยหาแบบมีคำนี้อยู่ในชื่อ
        for k, c in lookup.items():
            if _norm(n) in k:
                return c
    return None


def _to_num(s):
    return pd.to_numeric(
        s.astype("string").str.replace(",", "", regex=False).str.replace("฿", "", regex=False).str.strip(),
        errors="coerce",
    ).astype("float64")


@st.cache_data(show_spinner=False)
def load_customer_profit(path_str: str, mtime_ns: int):
    """อ่านไฟล์ + หาแถวหัวตาราง (รองรับหัวรายงานด้านบน) คืน (DataFrame มาตรฐาน, ชื่อคอลัมน์ที่ใช้)"""
    path = Path(path_str)
    try:  # python-calamine อ่าน Excel เร็วกว่ามาก (ถ้าติดตั้งไว้)
        xls = pd.ExcelFile(path, engine="calamine")
    except Exception:
        xls = pd.ExcelFile(path)
    # ชีตที่ชื่อบอกว่าเป็นกำไร/ลูกค้า ให้ลองก่อน จะได้ไม่ต้องเปิดชีตข้อมูลดิบขนาดใหญ่
    sheets = sorted(xls.sheet_names, key=lambda n: 0 if ("กำไร" in n or "ลูกค้า" in n) else 1)
    for sheet in sheets:
        preview = xls.parse(sheet, header=None, nrows=30)
        for i in range(len(preview)):
            cells = [str(v) for v in preview.iloc[i].tolist() if pd.notna(v)]
            probe = pd.DataFrame(columns=cells)
            if _find(probe, COLS["customer"]) and _find(probe, COLS["profit"]):
                raw = xls.parse(sheet, header=i)
                raw.columns = [" ".join(str(c).split()) for c in raw.columns]
                used = {k: _find(raw, v) for k, v in COLS.items()}
                out = pd.DataFrame({
                    "Customer": raw[used["customer"]].astype("string").str.strip(),
                    "Revenue": _to_num(raw[used["revenue"]]) if used["revenue"] else float("nan"),
                    "Cost": _to_num(raw[used["cost"]]) if used["cost"] else float("nan"),
                    "Profit": _to_num(raw[used["profit"]]),
                    "Type": (raw[used["ptype"]].astype("string").str.strip()
                             .str.replace(r"\s+", " ", regex=True) if used["ptype"] else "ไม่ระบุ"),
                })
                out = out[out["Customer"].notna() & out["Customer"].ne("")]
                out["Type"] = out["Type"].fillna("ไม่ระบุ").replace("", "ไม่ระบุ")
                # กันกรณีคอลัมน์ต้นฉบับมีหลายประเภทซ้อนกันในค่าเดียว เช่น
                # "สินค้าทั่วไป, สินค้าแช่เย็น" (เกิดจากไฟล์ต้นทางตอนหาประเภทรายได้สูงสุดแล้วเสมอกัน)
                # ให้ยึดประเภทแรกเพียงอันเดียวเสมอ ลูกค้าหนึ่งรายต้องมีประเภทสินค้าเดียว
                out["Type"] = out["Type"].str.split(",").str[0].str.strip()
                # ลูกค้าซ้ำ: รวมยอด ประเภทสินค้าใช้ค่าจากแถวที่รายได้สูงสุด
                if out["Customer"].duplicated().any():
                    type_of = (out.sort_values("Revenue", ascending=False)
                               .drop_duplicates("Customer").set_index("Customer")["Type"])
                    out = out.groupby("Customer", as_index=False)[["Revenue", "Cost", "Profit"]].sum()
                    out["Type"] = out["Customer"].map(type_of)
                return out.reset_index(drop=True), {k: v for k, v in used.items() if v}, sheet
    return pd.DataFrame(), {}, None


def _money(value) -> str:
    """ยอดเงินแบบย่อ — ช่องว่างในไฟล์ (NaN) แสดงเป็น —"""
    return "—" if value is None or pd.isna(value) else _money_raw(value)


def _money_full(value) -> str:
    """ยอดเงินเต็ม — ช่องว่างในไฟล์ (NaN) แสดงเป็น —"""
    return "—" if value is None or pd.isna(value) else _money_full_raw(value)


def _short_id(cid: str) -> str:
    cid = str(cid)
    return cid if len(cid) <= 14 else f"{cid[:10]}…"


def _margin_cell(profit, revenue, color):
    if pd.isna(revenue) or not revenue or pd.isna(profit):
        return '<td class="tc-num tc-muted">—</td>'
    m = profit / revenue
    width = max(0.0, min(abs(m), 1.0)) * 100
    bar_color = color if m >= 0 else LOSS_COLOR
    cls = "tc-neg" if m < 0 else ""
    return (f'<td class="tc-num {cls}"><div class="cp-margin">{m * 100:,.1f}%'
            f'<span class="cp-margin-bar"><span style="width:{width:.1f}%;background:{bar_color}"></span>'
            f"</span></div></td>")


# =========================================================
# DASHBOARD
# =========================================================

def render_customer_profit_dashboard():
    path = find_source_file()
    if path is None:
        st.error(
            f"ไม่พบไฟล์ที่ชื่อมีคำว่า “{SOURCE_KEYWORD}” ในโฟลเดอร์ data — "
            "อัปโหลดไฟล์ เช่น “กำไรลูกค้าและประเภทสินค้า.xlsx” ในหน้า Data Management ก่อน"
        )
        return
    with st.spinner(f"กำลังอ่านไฟล์ {path.name} ... (ครั้งแรกอาจใช้เวลาสักครู่ ครั้งต่อไปจะเร็ว)"):
        data, used, sheet = load_customer_profit(str(path), path.stat().st_mtime_ns)
    if data.empty:
        st.error(f"อ่านไฟล์ {path.name} ไม่ได้ — ต้องมีคอลัมน์รหัสลูกค้า (เช่น ผู้รับ_encoded) และ กำไรลูกค้ารวม")
        return

    types_by_rev = data.groupby("Type")["Revenue"].sum().sort_values(ascending=False).index.tolist()
    type_colors = {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(types_by_rev)}

    def type_badge(t):
        c = type_colors.get(t, "#CBD5E1")
        return f'<span class="cp-badge" style="background:{_tint(c, 0.7)}">{esc(t)}</span>'

    st.markdown(PAGE_CSS + EXTRA_CSS, unsafe_allow_html=True)

    # ---------------- ตัวกรอง ----------------
    fcard = _card("cp_filters")
    fcard.markdown('<div class="tc-filter-title">🔎 ตัวกรองข้อมูล</div>', unsafe_allow_html=True)
    f1, f2, f3 = fcard.columns([1.6, 1, 1.6])
    with f1:
        pick_types = st.multiselect("ประเภทสินค้า", types_by_rev, placeholder="ทั้งหมด",
                                    key=_wkey("cp_types", types_by_rev))
    with f2:
        status = st.selectbox("สถานะกำไร", ["ทั้งหมด", "มีกำไร", "ขาดทุน"], key="cp_status")
    with f3:
        search = st.text_input("ค้นหารหัสลูกค้า", placeholder="พิมพ์บางส่วนของรหัส เช่น c0538e", key="cp_search")

    df = data
    if pick_types:
        df = df[df["Type"].isin(pick_types)]
    if status == "มีกำไร":
        df = df[df["Profit"] >= 0]
    elif status == "ขาดทุน":
        df = df[df["Profit"] < 0]
    if search.strip():
        df = df[df["Customer"].str.contains(search.strip(), case=False, na=False, regex=False)]
    if df.empty:
        st.info("ไม่มีข้อมูลตามตัวกรองที่เลือก")
        return

    # ---------------- การ์ดตัวเลข ----------------
    n_cust = len(df)
    rev, cost, profit = df["Revenue"].sum(), df["Cost"].sum(), df["Profit"].sum()
    margin = profit / rev if rev else float("nan")
    n_loss = int((df["Profit"] < 0).sum())

    def kpi(icon, bg, label, value, sub, value_cls=""):
        return (
            f'<div class="tc-kpi"><div class="tc-kpi-icon" style="background:{bg}">{icon}</div>'
            f'<div><div class="tc-kpi-label">{esc(label)}</div>'
            f'<div class="tc-kpi-value {value_cls}">{esc(value)}</div>'
            f'<div class="tc-kpi-sub">{esc(sub)}</div></div></div>'
        )

    cards = [
        kpi("👥", "#FFE8EC", "จำนวนลูกค้า", f"{n_cust:,} ราย", f"ขาดทุน {n_loss:,} ราย"),
        kpi("🧾", "#E6F4FA", "รายได้รวม", _money(rev), "บาท"),
        kpi("💰", "#FFF0E6", "ต้นทุนปันส่วน", _money(cost), "ปันส่วนตามยอดรายได้ของลูกค้า"),
        kpi("📈", "#E7F6EC", "กำไรลูกค้ารวม", _money(profit),
            f"อัตรากำไร {margin * 100:,.1f}% ของรายได้" if pd.notna(margin) else "—", _neg(profit)),
    ]
    st.markdown('<div class="tc-kpi-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)

    # ---------------- ข้อสังเกตสำคัญ ----------------
    by_type = (
        df.groupby("Type")
        .agg(Customers=("Customer", "count"), Revenue=("Revenue", "sum"),
             Cost=("Cost", "sum"), Profit=("Profit", "sum"))
        .reset_index()
    )
    by_type["Margin"] = by_type["Profit"] / by_type["Revenue"].replace(0, float("nan"))
    by_type = by_type.sort_values("Profit", ascending=False).reset_index(drop=True)

    top_c = df.loc[df["Profit"].idxmax()]
    top_t = by_type.iloc[0]
    k = min(10, n_cust)
    top_share = df.nlargest(k, "Profit")["Profit"].sum() / profit * 100 if profit > 0 else float("nan")
    cells = [
        ("#3E9E6A", "🏆", "ลูกค้ากำไรสูงสุด", _money(top_c["Profit"]), _short_id(top_c["Customer"]),
         f'<div class="tc-ins-sub">รายได้ {esc(_money(top_c["Revenue"]))} · {type_badge(top_c["Type"])}</div>'),
        ("#D0588A", "📦", "ประเภทสินค้ากำไรสูงสุด", _money(top_t["Profit"]), top_t["Type"],
         f'<div class="tc-ins-sub">{int(top_t["Customers"]):,} ลูกค้า · อัตรากำไร '
         f'{(top_t["Margin"] * 100 if pd.notna(top_t["Margin"]) else 0):,.1f}%</div>'),
        ("#D99A2B", "🎯", f"{k} ลูกค้าแรกรวมกัน",
         f"{top_share:.1f}%" if pd.notna(top_share) else "—", "ของกำไรลูกค้ารวม",
         '<div class="tc-ins-sub">ยิ่งสูง = กำไรพึ่งลูกค้าไม่กี่รายมาก</div>'),
    ]
    st.markdown(
        '<div class="tc-ins-card"><div class="tc-ins-head">ข้อสังเกตสำคัญ</div>'
        f'<div class="tc-ins-grid" style="grid-template-columns:repeat({len(cells)}, minmax(0, 1fr))">'
        + "".join(
            f'<div class="tc-ins"><div class="tc-ins-top">'
            f'<span class="tc-ins-icon" style="background:{_tint(c, 0.86)}">{icon}</span>'
            f'<span class="tc-ins-title">{esc(title)}</span></div>'
            f'<div class="tc-ins-metric" style="color:{c}">{esc(metric)}</div>'
            f'<div class="tc-ins-main">{esc(main)}</div>{extra}</div>'
            for c, icon, title, metric, main, extra in cells
        ) + "</div></div>",
        unsafe_allow_html=True,
    )

    # ---------------- ตามประเภทสินค้า ----------------
    a, b = st.columns([1.35, 1], gap="medium")
    chart_types = st.multiselect(
        "เลือกประเภทสินค้าที่ต้องการดู (กราฟด้านล่าง)",
        types_by_rev,
        default=types_by_rev,
        key=_wkey("cp_chart_types", types_by_rev),
    )
    chart_data = by_type[by_type["Type"].isin(chart_types)] if chart_types else by_type.iloc[0:0]

    with a:
        with _card("cp_type_bar"):
            st.markdown("#### รายได้ ต้นทุน และกำไร ตามประเภทสินค้า")
            st.caption("ประเภทสินค้า = ประเภทที่ทำรายได้สูงสุดของลูกค้าแต่ละราย")
            if chart_data.empty:
                st.info("เลือกอย่างน้อย 1 ประเภทสินค้าเพื่อดูกราฟ")
            else:
                fig = go.Figure()
                for name, col, color in (("รายได้", "Revenue", REV_COLOR), ("ต้นทุนปันส่วน", "Cost", COST_COLOR),
                                         ("กำไร", "Profit", PROFIT_COLOR)):
                    fig.add_trace(go.Bar(
                        name=name, x=chart_data["Type"], y=chart_data[col], marker_color=color,
                        hovertemplate=f"%{{x}}<br>{name}: ฿%{{y:,.0f}}<extra></extra>",
                    ))
                fig.update_layout(
                    barmode="group", height=380, bargap=0.18, bargroupgap=0.05,
                    margin=dict(l=10, r=10, t=20, b=20), legend=dict(orientation="h", y=1.12, x=0),
                    xaxis=dict(title=""), yaxis=dict(title="บาท", tickformat=".2s"), hovermode="x unified",
                )
                _style(fig)
                st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
    with b:
        with _card("cp_type_share"):
            st.markdown("#### สัดส่วนกำไรตามประเภทสินค้า")
            pos = chart_data[chart_data["Profit"] > 0]
            rows = "".join(
                f'<div class="tc-leg-row"><span class="tc-sw" style="background:{type_colors.get(r["Type"], "#CBD5E1")}"></span>'
                f'<span class="tc-leg-name">{esc(r["Type"])} <small class="tc-muted">({int(r["Customers"]):,} ราย)</small></span>'
                f'<span class="tc-leg-val {_neg(r["Profit"])}">{_money(r["Profit"])}</span>'
                f'<span class="tc-leg-pct">{(r["Margin"] * 100 if pd.notna(r["Margin"]) else 0):.1f}%</span></div>'
                for r in chart_data.to_dict("records")
            )
            legend_html = (f'<div class="tc-legend">{rows}</div>'
                           '<div class="tc-leg-foot">ตัวเลขขวาสุด = อัตรากำไร (กำไร ÷ รายได้)</div>')
            if pos.empty:
                st.info("ไม่มีประเภทสินค้าที่มีกำไร")
                st.markdown(legend_html, unsafe_allow_html=True)
            else:
                total_pos = float(pos["Profit"].sum())
                c_pie, c_leg = st.columns([1.05, 1.15], gap="small")
                with c_pie:
                    fig = go.Figure(go.Pie(
                        labels=pos["Type"], values=pos["Profit"], hole=0.6, sort=False,
                        marker=dict(colors=[type_colors[t] for t in pos["Type"]], line=dict(color="white", width=3)),
                        text=[f"{v / total_pos * 100:.0f}%" if v / total_pos >= 0.05 else "" for v in pos["Profit"]],
                        textinfo="text", textposition="inside", insidetextfont=dict(color="#3F2A2E", size=13),
                        hovertemplate="%{label}<br>กำไร ฿%{value:,.0f}<br>%{percent}<extra></extra>",
                    ))
                    fig.update_layout(
                        height=340, showlegend=False, margin=dict(l=0, r=0, t=6, b=6),
                        annotations=[dict(
                            text=f"<span style='font-size:12px;color:#64748B'>กำไรรวม (ตามที่เลือก)</span>"
                                 f"<br><b style='font-size:18px;color:#1E293B'>{_money(float(chart_data['Profit'].sum()))}</b>",
                            x=0.5, y=0.5, showarrow=False,
                        )],
                    )
                    _style(fig)
                    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
                with c_leg:
                    st.markdown(legend_html, unsafe_allow_html=True)

    # ---------------- อันดับลูกค้า ----------------
    with _card("cp_rank"):
        st.markdown("#### อันดับลูกค้า")
        r1, r2, r3 = st.columns([1.3, 1, 0.7])
        with r1:
            rank_metric = st.selectbox("ตัวชี้วัด", ["กำไร", "รายได้", "อัตรากำไร"], key="cp_rank_metric")
        with r2:
            rank_dir = st.selectbox("แสดง", ["มากที่สุด", "น้อยที่สุด / ขาดทุน"], key="cp_rank_dir")
        with r3:
            rank_n = st.selectbox("จำนวน", [10, 15, 20, 30], key="cp_rank_n")
        d = df.assign(Margin=df["Profit"] / df["Revenue"].replace(0, float("nan")))
        col = {"กำไร": "Profit", "รายได้": "Revenue", "อัตรากำไร": "Margin"}[rank_metric]
        d = d.dropna(subset=[col])
        d = (d.nlargest(rank_n, col) if rank_dir == "มากที่สุด" else d.nsmallest(rank_n, col)).iloc[::-1]
        values = d[col] * 100 if col == "Margin" else d[col]
        colors = [LOSS_COLOR if v < 0 else type_colors.get(t, "#CBD5E1") for v, t in zip(values, d["Type"])]
        labels = [f"{v:,.1f}%" if col == "Margin" else _money_full(v) for v in values]
        fig = go.Figure(go.Bar(
            y=[_short_id(c) for c in d["Customer"]], x=values, orientation="h",
            marker_color=colors, text=labels, textposition="outside", cliponaxis=False,
            customdata=d[["Customer", "Type", "Revenue", "Cost", "Profit"]].to_numpy(),
            hovertemplate=("<b>%{customdata[0]}</b><br>ประเภทสินค้า: %{customdata[1]}"
                           "<br>รายได้: ฿%{customdata[2]:,.0f}<br>ต้นทุนปันส่วน: ฿%{customdata[3]:,.0f}"
                           "<br>กำไร: ฿%{customdata[4]:,.0f}<extra></extra>"),
        ))
        lo, hi = float(min(values.min(), 0)), float(max(values.max(), 0))
        span = (hi - lo) or 1
        fig.update_layout(
            height=max(340, 30 * len(d) + 110), margin=dict(l=10, r=30, t=10, b=30), showlegend=False,
            xaxis=dict(title="%" if col == "Margin" else "บาท", tickformat=",.0f",
                       range=[lo - span * 0.15 if lo < 0 else 0, hi + span * 0.18]),
            yaxis=dict(title="", automargin=True), bargap=0.3,
        )
        _style(fig)
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
        st.caption("สีแท่ง = ประเภทสินค้าของลูกค้า · แดง = ติดลบ · ชี้เมาส์เพื่อดูรหัสลูกค้าเต็ม")

    # ---------------- กลุ่มลูกค้า: รายได้ × อัตรากำไร ----------------
    with _card("cp_segment"):
        st.markdown("#### กลุ่มลูกค้าตามรายได้และอัตรากำไร")
        seg = df[df["Revenue"] > 0].assign(Margin=lambda x: x["Profit"] / x["Revenue"])
        if seg.empty:
            st.info("ไม่มีลูกค้าที่มีรายได้")
        else:
            rev_cut = float(seg["Revenue"].quantile(0.80))
            avg_margin = float(seg["Profit"].sum() / seg["Revenue"].sum())
            high_rev = seg["Revenue"] >= rev_cut
            good_m = seg["Margin"] >= avg_margin
            st.caption(
                f"รายได้สูง = กลุ่ม 20% แรกตามรายได้ (ตั้งแต่ {_money(rev_cut)} ขึ้นไป) · "
                f"กำไรดี = อัตรากำไรตั้งแต่ค่าเฉลี่ยรวม {avg_margin * 100:,.1f}% ขึ้นไป"
            )
            total_profit = float(seg["Profit"].sum()) or 1.0
            groups = [
                ("⭐", "ลูกค้าดาวเด่น", "รายได้สูง · กำไรดี", "รักษาไว้ ดูแลเป็นพิเศษ",
                 "#3E9E6A", high_rev & good_m),
                ("🏋️", "ลูกค้าหลัก กำไรบาง", "รายได้สูง · กำไรต่ำกว่าเฉลี่ย", "ทบทวนราคา/ต้นทุนการขนส่ง",
                 "#D9772B", high_rev & ~good_m),
                ("🌱", "ลูกค้าเล็ก กำไรดี", "รายได้ต่ำ · กำไรดี", "โอกาสขยายยอดขาย",
                 "#2F7F95", ~high_rev & good_m),
                ("⚠️", "ลูกค้าเล็ก กำไรบาง", "รายได้ต่ำ · กำไรต่ำกว่าเฉลี่ย", "พิจารณาเงื่อนไข/ขั้นต่ำการส่ง",
                 "#C23B53", ~high_rev & ~good_m),
            ]
            boxes = []
            for icon, name, rule, action, color, mask in groups:
                g = seg[mask]
                n = len(g)
                prof = float(g["Profit"].sum())
                rev_g = float(g["Revenue"].sum())
                loss_n = int((g["Profit"] < 0).sum())
                share = prof / total_profit * 100
                boxes.append(
                    f'<div class="cp-seg" style="--c:{color}">'
                    f'<div class="cp-seg-head"><span class="cp-seg-icon" style="background:{_tint(color, 0.85)}">{icon}</span>'
                    f'<div><div class="cp-seg-name">{esc(name)}</div><div class="cp-seg-rule">{esc(rule)}</div></div></div>'
                    f'<div class="cp-seg-big">{n:,} <small>ราย ({n / len(seg) * 100:,.1f}%)</small></div>'
                    f'<div class="cp-seg-bar"><span style="width:{max(min(share, 100), 0):.1f}%;background:{color}"></span></div>'
                    f'<div class="cp-seg-row"><span>กำไร</span><b class="{_neg(prof)}">{_money(prof)}</b>'
                    f'<small>{share:,.1f}% ของกำไรรวม</small></div>'
                    f'<div class="cp-seg-row"><span>รายได้</span><b>{_money(rev_g)}</b>'
                    f'<small>อัตรากำไร {(prof / rev_g * 100 if rev_g else 0):,.1f}%</small></div>'
                    + (f'<div class="cp-seg-loss">ขาดทุน {loss_n:,} ราย</div>' if loss_n else "")
                    + f'<div class="cp-seg-top"><span>ลูกค้าหลักในกลุ่ม (รายได้สูงสุด)</span>'
                    + "".join(
                        f'<code title="{esc(c)}">{esc(_short_id(c))}</code>'
                        for c in g.nlargest(3, "Revenue")["Customer"]
                    )
                    + "</div>"
                    + f'<div class="cp-seg-action">👉 {esc(action)}</div></div>'
                )
            st.markdown(
                '<div class="cp-seg-axis"><span>กำไรดี</span><span>กำไรต่ำกว่าเฉลี่ย</span></div>'
                f'<div class="cp-seg-grid">{boxes[0]}{boxes[1]}{boxes[2]}{boxes[3]}</div>',
                unsafe_allow_html=True,
            )

            # ---------- รายชื่อลูกค้าในแต่ละกลุ่ม ----------
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            st.markdown("##### รายชื่อลูกค้าในแต่ละกลุ่ม")
            tabs = st.tabs([f"{icon} {name} ({int(mask.sum()):,})" for icon, name, _r, _a, _c, mask in groups])
            for tab, (icon, name, _rule, _act, color, mask), gkey in zip(tabs, groups, ["star", "big", "small", "thin"]):
                with tab:
                    g = seg[mask]
                    if g.empty:
                        st.info("ไม่มีลูกค้าในกลุ่มนี้")
                        continue
                    q1, q2 = st.columns([1.2, 0.8])
                    with q1:
                        g_sort = st.selectbox(
                            "เรียงตาม", ["รายได้มากสุด", "กำไรมากสุด", "ขาดทุนมากสุด", "อัตรากำไรต่ำสุด"],
                            key=f"cp_seg_sort_{gkey}",
                        )
                    with q2:
                        g_n = st.selectbox("แสดง", [20, 50, 100, 200], index=1, key=f"cp_seg_n_{gkey}",
                                           format_func=lambda n: f"{n} ราย")
                    col, asc = {
                        "รายได้มากสุด": ("Revenue", False), "กำไรมากสุด": ("Profit", False),
                        "ขาดทุนมากสุด": ("Profit", True), "อัตรากำไรต่ำสุด": ("Margin", True),
                    }[g_sort]
                    gg = (g.nsmallest(g_n, col) if asc else g.nlargest(g_n, col))
                    body = []
                    for i, r in enumerate(gg.to_dict("records"), 1):
                        body.append(
                            "<tr>"
                            f'<td class="tc-rank">{i}</td>'
                            f'<td><span class="cp-id" title="{esc(r["Customer"])}">{esc(_short_id(r["Customer"]))}</span></td>'
                            f"<td>{type_badge(r['Type'])}</td>"
                            f'<td class="tc-num">{_money_full(r["Revenue"])}</td>'
                            f'<td class="tc-num">{_money_full(r["Cost"])}</td>'
                            f'<td class="tc-num {_neg(r["Profit"]) or "cp-pos"}"><b>{_money_full(r["Profit"])}</b></td>'
                            + _margin_cell(r["Profit"], r["Revenue"], color)
                            + "</tr>"
                        )
                    st.caption(f"{len(g):,} ลูกค้าในกลุ่ม · แสดง {len(gg):,} รายแรก · ชี้เมาส์ที่รหัสเพื่อดูรหัสเต็ม")
                    st.markdown(
                        _table_html(["#", "ลูกค้า", "ประเภทสินค้า", "รายได้", "ต้นทุนปันส่วน", "กำไร", "อัตรากำไร"],
                                    body, right_cols={3, 4, 5, 6}, max_height=420),
                        unsafe_allow_html=True,
                    )
                    sig = f"{gkey}|{len(g)}|{float(g['Profit'].sum()):.2f}"
                    if st.button(f"📄 เตรียมไฟล์ CSV กลุ่มนี้ ({len(g):,} ลูกค้า)", key=f"cp_seg_csv_{gkey}"):
                        out = g.sort_values(col, ascending=asc)
                        st.session_state[f"cp_seg_csv_{gkey}_data"] = (sig, pd.DataFrame({
                            "กลุ่มลูกค้า": name, "รหัสลูกค้า": out["Customer"],
                            "ประเภทสินค้ารายได้สูงสุด": out["Type"], "รายได้รวมลูกค้า": out["Revenue"],
                            "ต้นทุนที่ปันส่วน": out["Cost"], "กำไรลูกค้ารวม": out["Profit"],
                            "อัตรากำไร (%)": (out["Margin"] * 100).round(2),
                        }).to_csv(index=False).encode("utf-8-sig"))
                    saved = st.session_state.get(f"cp_seg_csv_{gkey}_data")
                    if saved and saved[0] == sig:
                        st.download_button(f"⬇️ ดาวน์โหลดรายชื่อ {name} (CSV)", saved[1],
                                           file_name=f"customers_{gkey}.csv", mime="text/csv",
                                           key=f"cp_seg_dl_{gkey}")

    # ---------------- ตารางลูกค้า ----------------
    with _card("cp_table"):
        st.markdown("#### ตารางกำไรลูกค้า")
        s1, s2 = st.columns([1, 1])
        with s1:
            sort_label = st.selectbox("เรียงตาม", ["กำไร", "รายได้", "ต้นทุนปันส่วน", "อัตรากำไร"],
                                      key="cp_table_sort")
        with s2:
            n_show = st.selectbox("แสดง", [50, 100, 200, 500], index=1, key="cp_table_rows",
                                  format_func=lambda n: f"{n} ราย")
        t = df.assign(
            Margin=df["Profit"] / df["Revenue"].replace(0, float("nan")),
            Rank=df["Profit"].rank(method="first", ascending=False),
        )
        sort_col = {"กำไร": "Profit", "รายได้": "Revenue", "ต้นทุนปันส่วน": "Cost", "อัตรากำไร": "Margin"}[sort_label]
        t = t.sort_values(sort_col, ascending=False, na_position="last").reset_index(drop=True)
        max_rev = float(df["Revenue"].max() or 1)
        st.caption(f"{len(t):,} ลูกค้า · # = อันดับตามกำไร · อัตรากำไร = กำไร ÷ รายได้")
        body = []
        for r in t.head(n_show).to_dict("records"):
            color = type_colors.get(r["Type"], "#CBD5E1")
            body.append(
                "<tr>"
                f'<td class="tc-rank">{int(r["Rank"]) if pd.notna(r["Rank"]) else ""}</td>'
                f'<td><span class="cp-id" title="{esc(r["Customer"])}">{esc(_short_id(r["Customer"]))}</span></td>'
                f"<td>{type_badge(r['Type'])}</td>"
                f'<td class="tc-num">{_money_full(r["Revenue"])}'
                f'<div class="tc-bar"><span style="width:{(r["Revenue"] or 0) / max_rev * 100:.1f}%;'
                f'background:{REV_COLOR}"></span></div></td>'
                f'<td class="tc-num">{_money_full(r["Cost"])}</td>'
                f'<td class="tc-num {_neg(r["Profit"]) or "cp-pos"}"><b>{_money_full(r["Profit"])}</b></td>'
                + _margin_cell(r["Profit"], r["Revenue"], PROFIT_COLOR)
                + "</tr>"
            )
        st.markdown(_table_html(["#", "ลูกค้า", "ประเภทสินค้า", "รายได้", "ต้นทุนปันส่วน", "กำไร", "อัตรากำไร"],
                                body, right_cols={3, 4, 5, 6}, max_height=500),
                    unsafe_allow_html=True)
        # ไฟล์ CSV ของลูกค้าหลายแสนรายใหญ่มาก จึงสร้างเมื่อกดปุ่มเท่านั้น
        csv_sig = f"{len(t)}|{sort_col}|{float(t['Profit'].sum()):.2f}"
        if st.button(f"📄 เตรียมไฟล์ CSV ({len(t):,} ลูกค้า)", key="cp_make_csv"):
            export = pd.DataFrame({
                "รหัสลูกค้า": t["Customer"], "ประเภทสินค้ารายได้สูงสุด": t["Type"],
                "รายได้รวมลูกค้า": t["Revenue"], "ต้นทุนที่ปันส่วน": t["Cost"],
                "กำไรลูกค้ารวม": t["Profit"], "อัตรากำไร (%)": (t["Margin"] * 100).round(2),
            })
            st.session_state["cp_csv"] = (csv_sig, export.to_csv(index=False).encode("utf-8-sig"))
        saved = st.session_state.get("cp_csv")
        if saved and saved[0] == csv_sig:
            st.download_button(f"⬇️ ดาวน์โหลด {len(t):,} ลูกค้า (CSV)", saved[1],
                               file_name="customer_profit.csv", mime="text/csv", key="cp_download")

    st.markdown(
        f'<div class="tc-source">ข้อมูลจาก {esc(path.name)} · ชีต {esc(str(sheet))} · '
        f"{len(data):,} ลูกค้าทั้งไฟล์ · แสดง {n_cust:,} ลูกค้าตามตัวกรอง</div>",
        unsafe_allow_html=True,
    )