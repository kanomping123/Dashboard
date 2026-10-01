"""
empty_trip.py
-------------
แดชบอร์ด "เที่ยวเปล่า & รถว่างไปสาขา" — มุมมองเที่ยว (แยกทิศทาง)

แหล่งข้อมูล
- อ่านเฉพาะไฟล์ในโฟลเดอร์ data ที่ชื่อมีคำว่า "เที่ยวเปล่า" เช่น "Dashboard เที่ยวเปล่า.xlsx"
  (ถ้ามีหลายไฟล์ ใช้ไฟล์ที่แก้ไขล่าสุดไฟล์เดียว)
- ราคาต่อเส้นทาง / ต้นทุนเฉลี่ย / ค่าเฉลี่ยหลังตัด outlier อ่านจากคอลัมน์ในไฟล์ตรง ๆ
  (ไม่เปลี่ยนตามตัวกรอง)

ตรรกะเดิม
- เที่ยวเปล่า   = Manifest Type มีคำว่า "ของเหมาตีเปล่า" หรือ "เที่ยวเปล่า"
- รถว่างไปสาขา = Manifest Type มีคำว่า "รถว่างไปสาขา"
- จำนวนเที่ยว  = นับ Travel Req. No. ไม่ซ้ำ
- ต้นทุน       = คอลัมน์ Total Cost

มุมมองเที่ยว (แยกทิศทาง)
- เที่ยว = Loading → Unloading แยกตามทิศทางการวิ่ง
  เช่น "ท่าลี่ → กองลอย" กับ "กองลอย → ท่าลี่" เป็นคนละรายการ
- ราคาต่อเส้นทางจากไฟล์ จับคู่ตามทิศทางก่อน ถ้าทิศนั้นไม่มีราคา ใช้ราคาของคู่สถานที่เดียวกัน
- ตารางและรายละเอียดแสดง "เที่ยวขากลับ" ไว้เทียบกัน
"""

from html import escape as esc
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from transport_cost_route import (
    GRAY,
    KNOWN_COST_COLUMNS,
    PAGE_CSS,
    PALETTE,
    THAI_MONTHS,
    _card,
    _chart_layout,
    _id_text,
    _key,
    _km,
    _money,
    _money_full,
    _num,
    _style,
    _table_html,
    _tint,
    _wkey,
    build_route_colors,
    build_routes,
    find_manifest_col,
)

DATA_FOLDER = Path("data")
SOURCE_KEYWORD = "เที่ยวเปล่า"

EMPTY = "เที่ยวเปล่า"
BRANCH = "รถว่างไปสาขา"
TYPES = [EMPTY, BRANCH]
TRIP_COLORS = {EMPTY: "#F07C8C", BRANCH: "#F6AE6B"}
PRICE_COLOR = "#7CC4D6"
PLOT_CONFIG = {"displayModeBar": False}
NO_ROUTE = "ไม่ระบุเส้นทาง"
ROUTE_LABEL = "เที่ยว (ต้นทาง → ปลายทาง)"

PIE_EXCLUDE = {"Total Cost", "Total Cash"}
PIE_DEFAULT = ["รวมต้นทุนค่าเดินทาง", "รวมต้นทุนค่าซ่อม", "รวมค่าเสื่อม"]
DISTANCE_CANDIDATES = ["ระยะทาง", "Distance", "Total Distance", "Distance (km)", "KM"]

# คอลัมน์ราคาในไฟล์ Dashboard เที่ยวเปล่า
PRICE_NAMES = ["ราคาต่อเส้นทาง"]
AVG_NAMES = ["ต้นทุนเฉลี่ย"]
AVG_KEPT_NAMES = ["ค่าเฉลี่ยหลังตัด outlier"]
OUTLIER_FLAG_NAMES = ["ตัด outlier"]

EXTRA_CSS = """
<style>
.et-dirs-cell { white-space: normal !important; min-width: 220px; }
.et-dir-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12.5px; color: #475569; }
.et-badge { display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 99px; color: #3F2A2E; }
.et-over { color: #C23B53 !important; font-weight: 700; }
.et-under { color: #3E9E6A !important; }
.et-price { color: #2F7F95 !important; font-weight: 700; }
.et-dirtag { display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 99px; margin-right: 8px; min-width: 44px; text-align: center; }
tr.et-grp td { border-top: 2px solid #F3C9D1 !important; }
.et-missing { font-style: italic; text-align: center !important; }
.et-route-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin: 8px 0 12px; }
.et-route-box { background: #FFF8F9; border: 1px solid #F6DDE2; border-radius: 14px; padding: 10px 14px; }
.et-route-box .k { font-size: 12px; color: #64748B; font-weight: 600; }
.et-route-box .v { font-size: 20px; font-weight: 800; color: #0F172A; line-height: 1.25; white-space: nowrap; }
.et-route-box .s { font-size: 11.5px; color: #94A3B8; }
</style>
"""
ARROW = ' <span class="tc-arrow">→</span> '


# =========================================================
# HELPERS
# =========================================================

def _norm(c) -> str:
    return "".join(str(c).split()).casefold()


def _clean(x) -> str:
    return "" if x is None or pd.isna(x) else str(x).strip()


def _dir_label(a, b) -> str:
    """ชื่อเที่ยวแบบแยกทิศทาง เช่น 'ท่าลี่ → กองลอย'"""
    if not a and not b:
        return NO_ROUTE
    return f"{a or 'ไม่ระบุ'} → {b or 'ไม่ระบุ'}"


def _find_col(df, names):
    lookup = {_norm(c): c for c in df.columns}
    for n in names:
        if _norm(n) in lookup:
            return lookup[_norm(n)]
    return None


def find_source_file():
    """ไฟล์ในโฟลเดอร์ data ที่ชื่อมีคำว่า เที่ยวเปล่า (หลายไฟล์ = ใช้ไฟล์ล่าสุด)"""
    if not DATA_FOLDER.exists():
        return None
    files = [
        f for f in DATA_FOLDER.iterdir()
        if f.is_file() and f.suffix.lower() in {".xlsx", ".xlsm", ".xls"}
        and not f.name.startswith("~$")
        and _norm(_key(SOURCE_KEYWORD)) in _norm(_key(f.stem))
    ]
    return max(files, key=lambda f: f.stat().st_mtime_ns).name if files else None


def _first_number(s):
    v = _num(s).dropna()
    return float(v.iloc[0]) if not v.empty else float("nan")


def _parse_date(series: pd.Series) -> pd.Series:
    """แปลงวันที่ให้ครอบคลุม: รูปแบบ ISO (yyyy-mm-dd) / ข้อความ dd/mm/yyyy / เลข serial ของ Excel / ปี พ.ศ."""
    if pd.api.types.is_datetime64_any_dtype(series):
        dt = pd.to_datetime(series, errors="coerce")
    else:
        text = series.astype("string").str.strip()
        dt = pd.to_datetime(text, format="%Y-%m-%d %H:%M:%S", errors="coerce")
        dt = dt.fillna(pd.to_datetime(text, format="%Y-%m-%d", errors="coerce"))
        rest = dt.isna() & text.notna() & text.ne("")
        if rest.any():
            try:
                other = pd.to_datetime(text.where(rest), dayfirst=True, errors="coerce", format="mixed")
            except (TypeError, ValueError):
                other = pd.to_datetime(text.where(rest), dayfirst=True, errors="coerce")
            dt = dt.fillna(other)
        num = pd.to_numeric(text, errors="coerce")
        serial = num.where(num.between(20000, 80000))
        if serial.notna().any():
            dt = dt.where(serial.isna(), pd.to_datetime(serial, unit="D", origin="1899-12-30", errors="coerce"))
    be = dt.dt.year > 2400  # ปี พ.ศ. → ค.ศ.
    if be.any():
        dt = dt.where(~be, dt - pd.DateOffset(years=543))
    return dt


def _badge(text, color):
    return f'<span class="et-badge" style="background:{_tint(color, 0.72)}">{esc(text)}</span>'


def _arrow_html(name) -> str:
    return esc(str(name)).replace(" → ", ARROW)


def _rev_cell(name, trips, cost):
    """ช่องเที่ยวขากลับในตาราง"""
    if not trips or pd.isna(name):
        return '<td class="et-dirs-cell tc-muted">— ไม่มีเที่ยวขากลับ</td>'
    return (
        f'<td class="et-dirs-cell"><div class="et-dir-name">{_arrow_html(name)}</div>'
        f'<small class="tc-muted">{int(trips):,} เที่ยว · {_money(cost)}</small></td>'
    )


# =========================================================
# DASHBOARD
# =========================================================

def render_empty_trip_dashboard(raw_df: pd.DataFrame):
    source_file = find_source_file()
    if source_file is None:
        st.error(
            f"ไม่พบไฟล์ที่ชื่อมีคำว่า “{SOURCE_KEYWORD}” ในโฟลเดอร์ data "
            "— อัปโหลดไฟล์ เช่น “Dashboard เที่ยวเปล่า.xlsx” ในหน้า Data Management ก่อน"
        )
        return
    if raw_df is None or raw_df.empty or "_source_file" not in raw_df.columns:
        st.error("ยังไม่มีข้อมูลในฐานข้อมูล — กด “🔄 โหลดข้อมูลจาก Excel ใหม่” ที่แถบด้านซ้าย")
        return

    src = raw_df[raw_df["_source_file"].map(_key) == _key(source_file)].copy()
    if src.empty:
        st.error(f"ไฟล์ {source_file} ยังไม่ถูกนำเข้าฐานข้อมูล — กด “🔄 โหลดข้อมูลจาก Excel ใหม่” ที่แถบด้านซ้าย")
        return
    missing = [c for c in ["Manifest Type", "Total Cost", "Loading", "Unloading"] if c not in src.columns]
    if missing:
        st.error(f"ไฟล์ {source_file} ขาดคอลัมน์: " + ", ".join(missing))
        return

    price_col = _find_col(src, PRICE_NAMES)
    avg_col = _find_col(src, AVG_NAMES)
    kept_col = _find_col(src, AVG_KEPT_NAMES)
    flag_col = _find_col(src, OUTLIER_FLAG_NAMES)

    # ---------------- ราคาจากไฟล์ (ตามทิศทาง + สำรองตามคู่สถานที่) ----------------
    _r, _d, _m, src_load, src_unload = build_routes(src)
    src_load = [_clean(x) for x in src_load]
    src_unload = [_clean(x) for x in src_unload]
    src["_DirKey"] = [f"{a}|{b}" for a, b in zip(src_load, src_unload)]
    src["_PairKey"] = ["|".join(sorted((a, b))) for a, b in zip(src_load, src_unload)]

    def price_by(key):
        parts = {}
        for name, col in (("Price", price_col), ("AvgFile", avg_col), ("AvgKept", kept_col)):
            parts[name] = (src.groupby(key)[col].agg(_first_number) if col
                           else pd.Series(dtype="float64"))
        return pd.DataFrame(parts)

    price_dir = price_by("_DirKey")
    price_pair = price_by("_PairKey")

    # ---------------- แยกประเภทเที่ยว (ตรรกะเดิม) ----------------
    manifest = src["Manifest Type"].astype("string").fillna("").str.strip()
    is_empty = manifest.str.contains(r"ของเหมาตีเปล่า|เที่ยวเปล่า", regex=True, na=False)
    is_branch = manifest.str.contains("รถว่างไปสาขา", regex=False, na=False)
    work = src[is_empty | is_branch].copy()
    if work.empty:
        st.info("ยังไม่พบ Manifest Type ที่เป็น 'เที่ยวเปล่า' หรือ 'รถว่างไปสาขา'")
        return
    work["_Type"] = EMPTY
    work.loc[is_branch.loc[work.index], "_Type"] = BRANCH
    work["_Cost"] = _num(work["Total Cost"]).fillna(0)

    # ---------------- เที่ยวแยกทิศทาง ----------------
    route, _direction, _main, load, unload = build_routes(work)
    load = [_clean(x) for x in load]
    unload = [_clean(x) for x in unload]
    route = list(route)
    work["_Load"], work["_Unload"] = load, unload
    work["_Pair"] = route  # เส้นทางไป-กลับรวมกัน (แบบเดิม) เก็บไว้อ้างอิง
    work["_Route"] = [NO_ROUTE if r == NO_ROUTE else _dir_label(a, b)
                      for r, a, b in zip(route, load, unload)]
    work["_DirKey"] = [f"{a}|{b}" for a, b in zip(load, unload)]
    work["_RevKey"] = [f"{b}|{a}" for a, b in zip(load, unload)]
    work["_PairKey"] = ["|".join(sorted((a, b))) for a, b in zip(load, unload)]

    # วันที่: ใช้ Disbursement Date เป็นหลัก (ถ้าไม่มีค่อยใช้ Travel Req. Date)
    date_col = _find_col(work, ["Disbursement Date"]) or _find_col(work, ["Travel Req. Date"])
    work["_Date"] = _parse_date(work[date_col]) if date_col else pd.NaT
    years = work["_Date"].dt.year
    work["_Year"] = years.map(lambda y: "" if pd.isna(y) else str(int(y + 543 if y < 2400 else y)))
    work["_MonthNum"] = work["_Date"].dt.month
    dist_col = next((c for c in DISTANCE_CANDIDATES if c in work.columns), None)
    work["_Distance"] = _num(work[dist_col]).fillna(0) if dist_col else 0.0
    work["_Flag"] = work[flag_col].astype("string").fillna("").str.strip() if flag_col else ""

    if "Travel Req. No." in work.columns:
        tid = work["Travel Req. No."].astype("string").fillna("").str.strip()
        work["_TripId"] = tid.mask(tid.eq(""))
    else:
        work["_TripId"] = work.index.astype(str)

    def trip_count(part):
        return int(part["_TripId"].nunique())

    vehicle_col = next((c for c in ["Vehicle Model", "ประเภทรถ"] if c in work.columns), None)
    route_colors = build_route_colors(
        work.groupby("_Route")["_Cost"].sum().sort_values(ascending=False).index
    )

    st.markdown(PAGE_CSS + EXTRA_CSS, unsafe_allow_html=True)

    # ---------------- ตัวกรอง ----------------
    fcard = _card("et_filters")
    fcard.markdown('<div class="tc-filter-title">🔎 ตัวกรองข้อมูล</div>', unsafe_allow_html=True)
    f1, f2, f3, f4, f5 = fcard.columns([0.8, 1.1, 1.1, 1.9, 1.2])
    filtered = work
    with f1:
        year_opts = sorted(y for y in work["_Year"].unique() if y)
        year = st.selectbox("ปี", ["ทั้งหมด"] + year_opts, key="et_year")
    if year != "ทั้งหมด":
        filtered = filtered[filtered["_Year"] == year]
    with f2:
        months = sorted(int(m) for m in filtered["_MonthNum"].dropna().unique())
        chosen_months = st.multiselect("เดือน", [THAI_MONTHS[m] for m in months],
                                       placeholder="ทั้งหมด", key="et_month")
    if chosen_months:
        nums = [n for n, label in THAI_MONTHS.items() if label in chosen_months]
        filtered = filtered[filtered["_MonthNum"].isin(nums)]
    with f3:
        chosen_types = st.multiselect("ประเภทเที่ยว", TYPES, placeholder="ทั้งหมด", key="et_type")
    if chosen_types:
        filtered = filtered[filtered["_Type"].isin(chosen_types)]
    with f4:
        route_opts = sorted(r for r in filtered["_Route"].unique() if r)
        chosen_routes = st.multiselect(ROUTE_LABEL, route_opts, placeholder="ทั้งหมด",
                                       key=_wkey("et_route", route_opts))
    with f5:
        if vehicle_col:
            veh = filtered[vehicle_col].astype("string").fillna("").str.strip()
            veh_opts = sorted(v for v in veh.unique() if v)
            chosen_veh = st.multiselect("ประเภทรถ", veh_opts, placeholder="ทั้งหมด",
                                        key=_wkey("et_vehicle", veh_opts))
            if chosen_veh:
                filtered = filtered[veh.isin(chosen_veh)]
        else:
            st.caption("ไม่มีข้อมูลประเภทรถ")

    # base = ข้อมูลก่อนกรองเที่ยว ใช้หาเที่ยวขากลับ (แม้เลือกดูแค่ทิศเดียว)
    base = filtered
    if chosen_routes:
        filtered = filtered[filtered["_Route"].isin(chosen_routes)]

    if filtered.empty:
        st.info("ไม่มีข้อมูลตามตัวกรองที่เลือก")
        return

    # ---------------- สรุประดับเที่ยว (แยกทิศทาง) ----------------
    rs = (
        filtered.groupby(["_Route", "_Type"])
        .agg(Trips=("_TripId", "nunique"), Cost=("_Cost", "sum"))
        .unstack("_Type", fill_value=0)
    )
    rs.columns = [f"{m}_{t}" for m, t in rs.columns]
    for t in TYPES:
        for m in ("Trips", "Cost"):
            if f"{m}_{t}" not in rs.columns:
                rs[f"{m}_{t}"] = 0
    grp = filtered.groupby("_Route")
    rs["TripsAll"] = grp["_TripId"].nunique()
    rs["CostAll"] = rs[f"Cost_{EMPTY}"] + rs[f"Cost_{BRANCH}"]
    rs["DirKey"] = grp["_DirKey"].first()
    rs["RevKey"] = grp["_RevKey"].first()
    rs["PairKey"] = grp["_PairKey"].first()
    rs = rs.reset_index()
    rs["AvgActual"] = rs["CostAll"] / rs["TripsAll"].replace(0, float("nan"))

    # ราคา: ตามทิศทางก่อน ไม่มีค่อยใช้ราคาของคู่สถานที่เดียวกัน
    rs = rs.merge(price_dir, left_on="DirKey", right_index=True, how="left")
    for c in ("Price", "AvgFile", "AvgKept"):
        if c not in rs.columns:
            rs[c] = float("nan")
        if c in price_pair.columns:
            rs[c] = rs[c].fillna(rs["PairKey"].map(price_pair[c]))
    rs["Diff"] = rs["AvgActual"] - rs["Price"]

    # เที่ยวขากลับ
    rev = base.groupby("_DirKey").agg(
        RevTrips=("_TripId", "nunique"), RevCost=("_Cost", "sum"), RevName=("_Route", "first"),
    )
    rs = rs.merge(rev, left_on="RevKey", right_index=True, how="left")
    same = rs["RevKey"].eq(rs["DirKey"])  # ต้นทาง = ปลายทาง ไม่มีขากลับ
    rs.loc[same, ["RevTrips", "RevCost"]] = 0
    rs["RevTrips"] = rs["RevTrips"].fillna(0)
    rs["RevCost"] = rs["RevCost"].fillna(0)

    valid = rs[rs["_Route"] != NO_ROUTE].copy()
    has_price = bool(valid["Price"].notna().any())

    # ---------------- การ์ดตัวเลข ----------------
    n_routes = int(valid["_Route"].nunique())
    n_empty_routes = int((valid[f"Trips_{EMPTY}"] > 0).sum())
    n_branch_routes = int((valid[f"Trips_{BRANCH}"] > 0).sum())
    total_loss = float(valid["CostAll"].sum())
    total_trips = trip_count(filtered)
    over = valid[valid["Diff"] > 0]

    def kpi(icon, bg, label, value, sub_html, value_color="#0F172A"):
        return (
            f'<div class="tc-kpi"><div class="tc-kpi-icon" style="background:{bg}">{icon}</div>'
            f'<div><div class="tc-kpi-label">{esc(label)}</div>'
            f'<div class="tc-kpi-value" style="color:{value_color}">{esc(value)}</div>'
            f'<div class="tc-kpi-sub">{sub_html}</div></div></div>'
        )

    cards = [
        kpi("🛣️", "#FFE8EC", "จำนวนเที่ยว (แยกทิศทาง)", f"{n_routes:,} รายการ",
            f"มี{EMPTY} {n_empty_routes:,} · {BRANCH} {n_branch_routes:,} รายการ"),
        kpi("💰", "#FFF0E6", "ต้นทุนสูญเสียรวม", _money(total_loss),
            f"เฉลี่ย {_money(total_loss / n_routes if n_routes else 0)} ต่อรายการ · {total_trips:,} เที่ยว"),
    ]
    if has_price:
        prices = valid["Price"].dropna()
        cards.append(kpi(
            "⚠️", "#FDE9EC", "เที่ยวที่ต้นทุนเฉลี่ยเกินราคา", f"{len(over):,} รายการ",
            f"จาก {int(prices.size):,} รายการที่มีราคา · เทียบต้นทุนเฉลี่ยต่อเที่ยวตามตัวกรอง",
            "#C23B53" if len(over) else "#0F172A",
        ))
    st.markdown('<div class="tc-kpi-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)

    # ---------------- ข้อสังเกตสำคัญ ----------------
    if not valid.empty:
        top_loss = valid.loc[valid["CostAll"].idxmax()]
        top_freq = valid.loc[valid["TripsAll"].idxmax()]

        def split_html(row, key):
            tot = float(row[f"{key}_{EMPTY}"] + row[f"{key}_{BRANCH}"]) or 1.0
            bar = "".join(
                f'<span style="width:{row[f"{key}_{t}"] / tot * 100:.1f}%;background:{TRIP_COLORS[t]}"></span>'
                for t in TYPES
            )
            fmt = _money if key == "Cost" else (lambda v: f"{int(v):,} เที่ยว")
            lines = "".join(
                f'<div class="tc-ins-line"><span class="tc-sw" style="background:{TRIP_COLORS[t]}"></span>'
                f'<span>{t}</span><b>{esc(fmt(row[f"{key}_{t}"]))}</b></div>'
                for t in TYPES
            )
            return f'<div class="tc-mini-bar">{bar}</div>{lines}'

        cells = [
            ("#E0566C", "💸", "เที่ยวที่สูญเสียมากที่สุด", _money(top_loss["CostAll"]),
             top_loss["_Route"], split_html(top_loss, "Cost")),
            ("#D0588A", "🔁", "เที่ยวที่เกิดบ่อยที่สุด", f'{int(top_freq["TripsAll"]):,} เที่ยว',
             top_freq["_Route"], split_html(top_freq, "Trips")),
        ]
        # ใช้รายการที่วิ่งอย่างน้อย 5 เที่ยว เพื่อไม่ให้รายการ 1–2 เที่ยวดึงค่าเฉลี่ยจนดูผิดปกติ
        over_reliable = over[over["TripsAll"] >= 5]
        if not over_reliable.empty:
            over = over_reliable
        if not over.empty:
            worst = over.loc[over["Diff"].idxmax()]
            cells.append((
                "#C23B53", "⚠️", "ต้นทุนเฉลี่ยเกินราคามากที่สุด" + (" (≥5 เที่ยว)" if not over_reliable.empty else ""),
                "+" + _money_full(worst["Diff"]),
                worst["_Route"],
                f'<div class="tc-ins-line"><span class="tc-sw" style="background:{TRIP_COLORS[EMPTY]}"></span>'
                f'<span>ต้นทุนเฉลี่ยต่อเที่ยว</span><b>{_money_full(worst["AvgActual"])}</b></div>'
                f'<div class="tc-ins-sub">{int(worst["TripsAll"]):,} เที่ยว · เกินราคา '
                f'{worst["Diff"] / worst["Price"] * 100:.0f}%</div>',
            ))
        elif has_price:
            top_price = valid.loc[valid["Price"].idxmax()]
            cells.append((
                "#2F7F95", "🏷️", "เที่ยวราคาสูงสุด", _money_full(top_price["Price"]),
                top_price["_Route"], f'<div class="tc-ins-sub">{int(top_price["TripsAll"]):,} เที่ยว</div>',
            ))
        html_cells = "".join(
            f'<div class="tc-ins"><div class="tc-ins-top">'
            f'<span class="tc-ins-icon" style="background:{_tint(c, 0.86)}">{icon}</span>'
            f'<span class="tc-ins-title">{esc(title)}</span></div>'
            f'<div class="tc-ins-metric" style="color:{c}">{esc(metric)}</div>'
            f'<div class="tc-ins-main">{esc(main)}</div>{extra}</div>'
            for c, icon, title, metric, main, extra in cells
        )
        st.markdown(
            '<div class="tc-ins-card"><div class="tc-ins-head">ข้อสังเกตสำคัญ</div>'
            f'<div class="tc-ins-grid" style="grid-template-columns:repeat({len(cells)}, minmax(0, 1fr))">'
            f"{html_cells}</div></div>",
            unsafe_allow_html=True,
        )

    # ---------------- อันดับเที่ยว ----------------
    with _card("et_rank"):
        st.markdown("#### อันดับเที่ยว (แยกทิศทาง)")
        metric_opts = ["ต้นทุนสูญเสียรวม", "จำนวนเที่ยว"] + (
            ["ต้นทุนเฉลี่ยต่อเที่ยว เทียบ ราคาต่อเส้นทาง"] if has_price else [])
        o1, o2 = st.columns([1.5, 0.6])
        with o1:
            ov_metric = st.selectbox("ตัวชี้วัด", metric_opts, key=_wkey("et_rank_metric", metric_opts))
        with o2:
            ov_top = st.selectbox("จำนวน Top", [5, 10, 15, 20, 30], index=1, key="et_rank_top")

        if ov_metric.startswith("ต้นทุนเฉลี่ยต่อเที่ยว"):
            plot = valid[valid["Price"].notna()].sort_values("CostAll", ascending=False).head(ov_top).iloc[::-1]
            st.caption("แท่ง = ราคาต่อเส้นทางจากไฟล์ · ◆ = ต้นทุนเฉลี่ยต่อเที่ยวจริงตามตัวกรอง "
                       "(◆ แดง = เกินราคา, ◆ เขียว = ต่ำกว่าราคา) · เรียงตามต้นทุนสูญเสียรวม")
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name="ราคาต่อเส้นทาง", y=plot["_Route"], x=plot["Price"], orientation="h",
                marker_color=_tint(PRICE_COLOR, 0.35),
                text=plot["Price"].map(_money_full), textposition="inside", insidetextanchor="end",
                hovertemplate="%{y}<br>ราคาต่อเส้นทาง: ฿%{x:,.0f}<extra></extra>",
            ))
            fig.add_trace(go.Scatter(
                name="ต้นทุนเฉลี่ยต่อเที่ยว", y=plot["_Route"], x=plot["AvgActual"], mode="markers",
                marker=dict(size=13, symbol="diamond", line=dict(color="white", width=1.5),
                            color=["#D0505C" if d > 0 else "#3E9E6A" for d in plot["Diff"].fillna(0)]),
                customdata=plot[["TripsAll", "Diff"]].to_numpy(),
                hovertemplate=("%{y}<br>ต้นทุนเฉลี่ยต่อเที่ยว: ฿%{x:,.0f}"
                               "<br>ส่วนต่างจากราคา: ฿%{customdata[1]:,.0f}"
                               "<br>%{customdata[0]:,} เที่ยว<extra></extra>"),
            ))
            x_max = float(max(plot["Price"].max(), plot["AvgActual"].max())) if not plot.empty else None
            _chart_layout(fig, max(360, 34 * len(plot) + 120), "บาทต่อเที่ยว", x_max)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
        else:
            key = "Cost" if ov_metric == "ต้นทุนสูญเสียรวม" else "Trips"
            rank_col = "CostAll" if key == "Cost" else "TripsAll"
            plot = valid[valid[rank_col] > 0].sort_values(rank_col, ascending=False).head(ov_top).iloc[::-1]
            st.caption("ต้นทาง → ปลายทาง แยกทิศทาง (เช่น ท่าลี่ → กองลอย กับ กองลอย → ท่าลี่ นับแยกกัน) "
                       "· แยกสีตามประเภทเที่ยว")
            fig = go.Figure()
            val_fmt = "฿%{x:,.0f}" if key == "Cost" else "%{x:,.0f} เที่ยว"
            for t in TYPES:
                fig.add_trace(go.Bar(
                    name=t, y=plot["_Route"], x=plot[f"{key}_{t}"], orientation="h",
                    marker_color=TRIP_COLORS[t],
                    hovertemplate=f"%{{y}}<br>{t}: {val_fmt}<extra></extra>",
                ))
            totals = plot[f"{key}_{EMPTY}"] + plot[f"{key}_{BRANCH}"]
            label_fmt = (lambda v: f"  {_money_full(v)}") if key == "Cost" else (lambda v: f"  {int(v):,}")
            fig.add_trace(go.Scatter(
                y=plot["_Route"], x=totals, mode="text", showlegend=False, hoverinfo="skip",
                text=totals.map(label_fmt), textposition="middle right",
                textfont=dict(color="#334155", size=12),
            ))
            fig.update_layout(barmode="stack")
            _chart_layout(fig, max(360, 34 * len(plot) + 120),
                          "บาท" if key == "Cost" else "จำนวนเที่ยว",
                          float(totals.max()) if not totals.empty else None)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    # ---------------- แนวโน้มรายเดือนตามเที่ยว ----------------
    with _card("et_trend"):
        st.markdown("#### แนวโน้มรายเดือนตามเที่ยว")
        st.caption("แต่ละเส้น = 1 เที่ยว (ต้นทาง → ปลายทาง) สีเดียวกับตาราง · "
                   "เส้นสีเข้ม = รวมทุกเที่ยวตามตัวกรอง (ไม่แยกเส้นทาง)")
        trend_opts = valid.sort_values("CostAll", ascending=False)["_Route"].tolist()
        t1, t2, t3, t4 = st.columns([2.5, 1.3, 1.2, 1])
        with t1:
            trend_routes = st.multiselect("เลือกเที่ยว (สูงสุด 10)", trend_opts, default=trend_opts[:5],
                                          max_selections=10, key=_wkey("et_trend_routes", trend_opts))
        with t2:
            trend_types = st.multiselect("ประเภทเที่ยว", TYPES, placeholder="ทั้งหมด",
                                         key="et_tr_type")
        with t3:
            tr_metric = st.selectbox("ตัวชี้วัด", ["ต้นทุนสูญเสียรวม", "จำนวนเที่ยว", "ต้นทุนเฉลี่ยต่อเที่ยว"],
                                     key="et_tr_metric")
        with t4:
            st.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
            show_total = st.checkbox("เส้นรวมทุกเที่ยว", value=True, key="et_tr_total")

        dated = filtered[filtered["_Date"].notna()]
        if trend_types:
            dated = dated[dated["_Type"].isin(trend_types)]
        total_label = "รวมทุกเที่ยว" if not trend_types else "รวม" + "+".join(trend_types)

        if not trend_routes and not show_total:
            st.info("เลือกอย่างน้อย 1 เที่ยว หรือเปิดเส้นรวมทุกเที่ยว")
        elif dated.empty:
            st.info("ไม่มีข้อมูลตามตัวกรอง (ลองเปลี่ยนประเภทเที่ยว หรือเงื่อนไขด้านบน)")
        else:
            def month_label(p):
                return f"{THAI_MONTHS[p.month]} {str(p.year + 543 if p.year < 2400 else p.year)[-2:]}"

            dated = dated.assign(_P=dated["_Date"].dt.to_period("M"))
            ycol = {"ต้นทุนสูญเสียรวม": "Cost", "จำนวนเที่ยว": "Trips", "ต้นทุนเฉลี่ยต่อเที่ยว": "Avg"}[tr_metric]
            # แกน X ใช้ทุกเดือนที่มีข้อมูล เพื่อให้เส้นรวมกับเส้นแยกเที่ยวเรียงเดือนตรงกัน
            order = [month_label(p) for p in sorted(dated["_P"].unique())]

            g = (
                dated[dated["_Route"].isin(trend_routes)]
                .groupby(["_P", "_Route"])
                .agg(Trips=("_TripId", "nunique"), Cost=("_Cost", "sum"))
                .reset_index().sort_values("_P")
            )
            g["Avg"] = g["Cost"] / g["Trips"].replace(0, float("nan"))
            g["Label"] = g["_P"].map(month_label)

            fig = go.Figure()
            for r in trend_routes:
                gr = g[g["_Route"] == r]
                if gr.empty:
                    continue
                fig.add_trace(go.Scatter(
                    name=r, x=gr["Label"], y=gr[ycol], mode="lines+markers",
                    line=dict(width=2.5, shape="spline", smoothing=0.6, color=route_colors.get(r, GRAY)),
                    marker=dict(size=7, line=dict(color="white", width=1.5)),
                    customdata=gr[["Trips", "Cost"]].to_numpy(),
                    hovertemplate=(f"<b>{esc(r)}</b> • %{{x}}<br>จำนวนเที่ยว: %{{customdata[0]:,}}"
                                   "<br>ต้นทุน: ฿%{customdata[1]:,.0f}<extra></extra>"),
                ))

            # เส้นรวมทุกเที่ยว: ยอดรวม/จำนวนเที่ยวสูงกว่าเส้นแยกมาก จึงใช้แกนขวา
            # (ต้นทุนเฉลี่ยต่อเที่ยวอยู่ระดับเดียวกัน ใช้แกนซ้ายร่วมกันได้)
            use_y2 = show_total and ycol != "Avg" and bool(trend_routes)
            if show_total:
                tot = (
                    dated.groupby("_P")
                    .agg(Trips=("_TripId", "nunique"), Cost=("_Cost", "sum"))
                    .reset_index().sort_values("_P")
                )
                tot["Avg"] = tot["Cost"] / tot["Trips"].replace(0, float("nan"))
                tot["Label"] = tot["_P"].map(month_label)
                fig.add_trace(go.Scatter(
                    name=total_label + (" (แกนขวา)" if use_y2 else ""),
                    x=tot["Label"], y=tot[ycol], mode="lines+markers",
                    yaxis="y2" if use_y2 else "y",
                    line=dict(width=3.5, color="#334155", shape="spline", smoothing=0.6),
                    marker=dict(size=8, color="#334155", line=dict(color="white", width=1.5)),
                    customdata=tot[["Trips", "Cost"]].to_numpy(),
                    hovertemplate=(f"<b>{esc(total_label)}</b> • %{{x}}<br>จำนวนเที่ยว: %{{customdata[0]:,}}"
                                   "<br>ต้นทุน: ฿%{customdata[1]:,.0f}<extra></extra>"),
                ))

            y_title = "จำนวนเที่ยว" if ycol == "Trips" else "บาท"
            layout = dict(
                height=420, margin=dict(l=15, r=15, t=20, b=20),
                legend=dict(orientation="h", y=-0.22, x=0),
                xaxis=dict(title="", type="category", categoryorder="array", categoryarray=order),
                yaxis=dict(title=y_title + (" (รายเที่ยว)" if use_y2 else ""), tickformat=",.0f",
                           rangemode="tozero"),
            )
            if use_y2:
                layout["yaxis2"] = dict(title=y_title + " (รวมทุกเที่ยว)", overlaying="y", side="right",
                                        tickformat=",.0f", rangemode="tozero", showgrid=False)
            fig.update_layout(**layout)
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    # ---------------- องค์ประกอบต้นทุนของเที่ยว ----------------
    with _card("et_pie"):
        st.markdown("#### องค์ประกอบต้นทุนของเที่ยว")
        pie_routes = ["ทุกเที่ยว"] + valid.sort_values("CostAll", ascending=False)["_Route"].tolist()
        p1, p2, p3 = st.columns([1.6, 1, 0.9])
        with p1:
            pie_route = st.selectbox(ROUTE_LABEL, pie_routes, key=_wkey("et_pie_route", pie_routes))
        with p2:
            pie_type = st.selectbox("ประเภทเที่ยว", ["ทั้งหมด"] + TYPES, key="et_pie_type")
        pie_src = filtered if pie_route == "ทุกเที่ยว" else filtered[filtered["_Route"] == pie_route]
        if pie_type != "ทั้งหมด":
            pie_src = pie_src[pie_src["_Type"] == pie_type]
        sums = {
            c: float(_num(pie_src[c]).fillna(0).sum())
            for c in KNOWN_COST_COLUMNS if c in pie_src.columns and c not in PIE_EXCLUDE
        }
        available = [c for c, v in sorted(sums.items(), key=lambda x: -x[1]) if v > 0]
        if not available:
            st.info("ไม่พบองค์ประกอบต้นทุนที่มีมูลค่า")
        else:
            default = [c for c in PIE_DEFAULT if c in available] or available[:4]
            cols_key = _wkey("et_pie_cols", available)
            n_sel = len(st.session_state.get(cols_key, default))
            with p3:
                st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
                picker = (st.popover(f"⚙️ รายการต้นทุน ({n_sel})") if hasattr(st, "popover")
                          else st.expander(f"⚙️ รายการต้นทุน ({n_sel})"))
            with picker:
                chosen = st.multiselect("เลือกต้นทุนที่ต้องการเปรียบเทียบ", available,
                                        default=default, key=cols_key)
            items = sorted([(c, sums[c]) for c in chosen if sums[c] > 0], key=lambda x: -x[1])
            if not items:
                st.info("กด ⚙️ รายการต้นทุน แล้วเลือกอย่างน้อย 1 รายการ")
            else:
                total = sum(v for _, v in items)
                colors = {c: PALETTE[i % len(PALETTE)] for i, (c, _) in enumerate(items)}
                fig = go.Figure(go.Pie(
                    labels=[c for c, _ in items], values=[v for _, v in items], hole=0.64, sort=False,
                    marker=dict(colors=[colors[c] for c, _ in items], line=dict(color="white", width=3)),
                    text=[f"{v / total * 100:.0f}%" if v / total >= 0.05 else "" for _, v in items],
                    textinfo="text", textposition="inside", insidetextfont=dict(color="#4A2A30", size=13),
                    hovertemplate="%{label}<br>฿%{value:,.0f}<br>%{percent}<extra></extra>",
                ))
                fig.update_layout(
                    height=290, showlegend=False, margin=dict(l=0, r=0, t=6, b=6),
                    annotations=[dict(
                        text=f"<span style='font-size:12px;color:#64748B'>รวมที่เลือก</span>"
                             f"<br><b style='font-size:18px;color:#1E293B'>{_money(total)}</b>",
                        x=0.5, y=0.5, showarrow=False,
                    )],
                )
                _style(fig)
                c_pie, c_leg = st.columns([1, 1.3], gap="small")
                with c_pie:
                    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
                with c_leg:
                    rows = "".join(
                        f'<div class="tc-leg-row"><span class="tc-sw" style="background:{colors[c]}"></span>'
                        f'<span class="tc-leg-name">{esc(c)}</span><span class="tc-leg-val">{_money(v)}</span>'
                        f'<span class="tc-leg-pct">{v / total * 100:.1f}%</span></div>'
                        for c, v in items
                    )
                    n = trip_count(pie_src)
                    st.markdown(
                        f'<div class="tc-legend">{rows}</div>'
                        f'<div class="tc-leg-foot">{n:,} เที่ยว · เฉลี่ย ฿{(total / n if n else 0):,.0f} ต่อเที่ยว</div>',
                        unsafe_allow_html=True,
                    )

    # ---------------- ตารางเที่ยว (แยกทิศทางทุกคอลัมน์) ----------------
    with _card("et_table"):
        st.markdown("#### ตารางเที่ยว (แยกทิศทาง)")
        table_routes = valid.sort_values("CostAll", ascending=False)["_Route"].tolist()
        s1, s2 = st.columns([3, 1])
        with s1:
            pick_routes = st.multiselect(
                "เลือกเที่ยว (ไม่เลือก = แสดงทั้งหมด)", table_routes,
                placeholder="พิมพ์ชื่อสถานที่เพื่อค้นหา", key=_wkey("et_table_routes", table_routes),
            )
        sort_opts = ["ต้นทุนสูญเสียรวม", "จำนวนเที่ยว", "ชื่อเที่ยว"]
        with s2:
            sort_label = st.selectbox("เรียงตาม", sort_opts, key=_wkey("et_table_sort", sort_opts))
        sort_by, asc = {
            "ต้นทุนสูญเสียรวม": ("CostAll", False), "จำนวนเที่ยว": ("TripsAll", False),
            "ราคาต่อเส้นทาง": ("Price", False), "ชื่อเที่ยว": ("Name", True),
        }[sort_label]

        # จับคู่ขาไป-ขากลับของสถานที่คู่เดียวกันไว้ติดกัน แต่ทุกคอลัมน์แยกค่าตามทิศทาง
        shown = valid if not pick_routes else valid[valid["_Route"].isin(pick_routes)]
        grp_rows = valid[valid["PairKey"].isin(shown["PairKey"].unique())]
        pair_agg = grp_rows.groupby("PairKey").agg(
            CostAll=("CostAll", "sum"), TripsAll=("TripsAll", "sum"),
            Price=("Price", "max"), Name=("_Route", "min"),
        )
        pair_order = pair_agg.sort_values(sort_by, ascending=asc, na_position="last").index.tolist()

        head = ["#", "ทิศทาง (ต้นทาง → ปลายทาง)", EMPTY, BRANCH,
                "ต้นทุนสูญเสียรวม", "ต้นทุนเฉลี่ย/เที่ยว"]
        max_cost = float(valid["CostAll"].max() or 1)
        TAG_COLORS = {"ขาไป": "#E0566C", "ขากลับ": "#3B82B0"}

        def type_cell(trips, cost):
            if not trips:
                return '<td class="tc-num tc-muted">—</td>'
            return (f'<td class="tc-num">{int(trips):,} เที่ยว<br>'
                    f'<small class="tc-muted">{_money(cost)}</small></td>')

        body, export_rows = [], []
        n_dir_rows = 0
        for rank, pk in enumerate(pair_order, 1):
            members = (grp_rows[grp_rows["PairKey"] == pk]
                       .sort_values(["CostAll", "TripsAll"], ascending=False).to_dict("records"))
            a, b = str(members[0]["DirKey"]).split("|", 1)
            if len(members) == 1 and a != b:
                members.append({"_missing": True, "_Route": _dir_label(b, a)})
            for i, r in enumerate(members):
                tag = "ขาไป" if i == 0 else "ขากลับ"
                tc = TAG_COLORS[tag]
                color = route_colors.get(r["_Route"], GRAY)
                tr_cls = ' class="et-grp"' if i == 0 else ""
                rank_cell = f'<td class="tc-rank">{rank if i == 0 else ""}</td>'
                dir_cell = (
                    f'<td><span class="et-dirtag" style="background:{_tint(tc, 0.85)};color:{tc}">{tag}</span>'
                    f'<span class="tc-dot" style="background:{color}"></span><b>{_arrow_html(r["_Route"])}</b></td>'
                )
                if r.get("_missing"):
                    body.append(
                        f"<tr{tr_cls}>{rank_cell}{dir_cell}"
                        f'<td colspan="{len(head) - 2}" class="tc-muted et-missing">ไม่มีเที่ยวทิศนี้ตามตัวกรอง</td></tr>'
                    )
                    export_rows.append({"ลำดับ": rank, "ทิศ": tag, "เที่ยว (ต้นทาง → ปลายทาง)": r["_Route"]})
                    continue
                n_dir_rows += 1
                cells = [
                    rank_cell, dir_cell,
                    type_cell(r[f"Trips_{EMPTY}"], r[f"Cost_{EMPTY}"]),
                    type_cell(r[f"Trips_{BRANCH}"], r[f"Cost_{BRANCH}"]),
                    f'<td class="tc-num"><b>{_money_full(r["CostAll"])}</b>'
                    f'<div class="tc-bar"><span style="width:{r["CostAll"] / max_cost * 100:.1f}%;'
                    f'background:{color}"></span></div></td>',
                    f'<td class="tc-num">{_money_full(r["AvgActual"])}</td>',
                ]
                body.append(f"<tr{tr_cls}>" + "".join(cells) + "</tr>")
                export_rows.append({
                    "ลำดับ": rank, "ทิศ": tag, "เที่ยว (ต้นทาง → ปลายทาง)": r["_Route"],
                    f"{EMPTY} (เที่ยว)": r[f"Trips_{EMPTY}"], f"ต้นทุน{EMPTY}": r[f"Cost_{EMPTY}"],
                    f"{BRANCH} (เที่ยว)": r[f"Trips_{BRANCH}"], f"ต้นทุน{BRANCH}": r[f"Cost_{BRANCH}"],
                    "ต้นทุนสูญเสียรวม": r["CostAll"], "ต้นทุนเฉลี่ยต่อเที่ยว": round(r["AvgActual"], 2),
                })

        st.caption(
            f"แสดง {len(pair_order):,} คู่สถานที่ · {n_dir_rows:,} ทิศทาง · "
            "แต่ละคู่แสดง 2 แถว: ขาไป (ทิศที่ต้นทุนสูงกว่า) และ ขากลับ · ทุกคอลัมน์เป็นค่าของทิศนั้นเท่านั้น · "
            "ต้นทุนเฉลี่ย/เที่ยว = ต้นทุนรวม ÷ จำนวนเที่ยวตามตัวกรอง"
        )
        st.markdown(_table_html(head, body, right_cols=set(range(2, len(head))), max_height=520),
                    unsafe_allow_html=True)
        st.download_button(
            "⬇️ ดาวน์โหลดตารางเที่ยว (CSV)",
            pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8-sig"),
            file_name="empty_trip_directions.csv", mime="text/csv", key="et_route_download",
        )

    # ---------------- รายละเอียดเที่ยว ----------------
    with _card("et_detail"):
        st.markdown("#### รายละเอียดเที่ยว")
        route_opts2 = valid.sort_values("CostAll", ascending=False)["_Route"].tolist()
        if not route_opts2:
            st.info("ไม่มีเที่ยวตามตัวกรอง")
        else:
            pick = st.selectbox("เลือกเที่ยว", route_opts2, key=_wkey("et_detail_route", route_opts2))
            row = valid[valid["_Route"] == pick].iloc[0]
            d = filtered[filtered["_Route"] == pick].sort_values("_Cost", ascending=False)
            boxes = [
                ("จำนวนเที่ยว", f'{int(row["TripsAll"]):,}',
                 f'{EMPTY} {int(row[f"Trips_{EMPTY}"]):,} · {BRANCH} {int(row[f"Trips_{BRANCH}"]):,}'),
                ("ต้นทุนสูญเสียรวม", _money(row["CostAll"]),
                 f'{EMPTY} {_money(row[f"Cost_{EMPTY}"])} · {BRANCH} {_money(row[f"Cost_{BRANCH}"])}'),
                ("ต้นทุนเฉลี่ยต่อเที่ยว", _money_full(row["AvgActual"]), "ตามตัวกรอง"),
            ]
            if row["RevTrips"] > 0:
                boxes.append(("เที่ยวขากลับ", f'{int(row["RevTrips"]):,} เที่ยว',
                              f'{row["RevName"]} · {_money(row["RevCost"])}'))
            else:
                boxes.append(("เที่ยวขากลับ", "—", "ไม่มีเที่ยวขากลับตามตัวกรอง"))
            st.markdown(
                '<div class="et-route-grid">' + "".join(
                    f'<div class="et-route-box"><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div>'
                    f'<div class="s">{esc(s)}</div></div>' for k, v, s in boxes
                ) + "</div>",
                unsafe_allow_html=True,
            )

            with st.expander(f"ดูรายเที่ยวของ {pick} ({trip_count(d):,} เที่ยว)"):
                mf_col = find_manifest_col(d)
                has_id = "Travel Req. No." in d.columns
                head = (["วันที่"] + (["Manifest No."] if mf_col else []) + (["Trip ID"] if has_id else [])
                        + ["ประเภทเที่ยว"] + (["ประเภทรถ"] if vehicle_col else [])
                        + ["ระยะทาง", "ต้นทุนรวม"] + (["ตัด outlier"] if flag_col else []))
                body = []
                for r in d.head(300).to_dict("records"):
                    date_txt = r["_Date"].strftime("%d/%m/%Y") if pd.notna(r["_Date"]) else "—"
                    cells = [f'<td class="tc-muted">{date_txt}</td>']
                    if mf_col:
                        cells.append(f'<td class="tc-mono"><b>{esc(_id_text(r.get(mf_col)))}</b></td>')
                    if has_id:
                        cells.append(f'<td class="tc-mono">{esc(_id_text(r.get("Travel Req. No.")))}</td>')
                    cells.append(f'<td>{_badge(r["_Type"], TRIP_COLORS[r["_Type"]])}</td>')
                    if vehicle_col:
                        cells.append(f'<td class="tc-muted">{esc(_id_text(r.get(vehicle_col)))}</td>')
                    cells += [
                        f'<td class="tc-num tc-muted">{_km(r["_Distance"])}</td>',
                        f'<td class="tc-num"><b>{_money_full(r["_Cost"])}</b></td>',
                    ]
                    if flag_col:
                        flag = str(r["_Flag"])
                        flag_color = "#EC7F86" if flag == "ตัด" else "#86CFA3"
                        cells.append(f"<td>{_badge(flag or '—', flag_color)}</td>")
                    body.append("<tr>" + "".join(cells) + "</tr>")
                num_cols = {head.index("ระยะทาง"), head.index("ต้นทุนรวม")}
                st.caption("เรียงจากต้นทุนสูงสุด · แสดงสูงสุด 300 เที่ยว"
                           + (" · ตัด = เที่ยวที่ไฟล์ไม่นำมาคิดค่าเฉลี่ยหลังตัด outlier" if flag_col else ""))
                st.markdown(_table_html(head, body, right_cols=num_cols, max_height=420),
                            unsafe_allow_html=True)
                export = pd.DataFrame({
                    "วันที่": d["_Date"].dt.strftime("%d/%m/%Y"),
                    **({"Manifest No.": d[mf_col].map(_id_text)} if mf_col else {}),
                    **({"Trip ID": d["Travel Req. No."].map(_id_text)} if has_id else {}),
                    "ต้นทาง (Loading)": d["_Load"], "ปลายทาง (Unloading)": d["_Unload"],
                    "ประเภทเที่ยว": d["_Type"],
                    **({"ประเภทรถ": d[vehicle_col]} if vehicle_col else {}),
                    "ระยะทาง (กม.)": d["_Distance"], "ต้นทุนรวม": d["_Cost"],
                    **({"ตัด outlier": d["_Flag"]} if flag_col else {}),
                })
                st.download_button(
                    f"⬇️ ดาวน์โหลด {len(d):,} เที่ยว (CSV)", export.to_csv(index=False).encode("utf-8-sig"),
                    file_name="empty_trip_direction_detail.csv", mime="text/csv", key="et_detail_download",
                )

    note = "" if has_price else " · ไม่พบคอลัมน์ ราคาต่อเส้นทาง ในไฟล์"
    st.markdown(
        f'<div class="tc-source">ข้อมูลจาก {esc(source_file)} · {len(work):,} เที่ยว (เที่ยวเปล่า + รถว่างไปสาขา)'
        f" · แสดง {total_trips:,} เที่ยวตามตัวกรอง{note}</div>",
        unsafe_allow_html=True,
    )