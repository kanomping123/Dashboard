"""
direction_overview.py
---------------------
แดชบอร์ด "ภาพรวมรายทิศทาง" — ดูรายได้ ต้นทุน กำไร CM Load Factor
และเที่ยวเปล่า / รถว่างไปสาขา ของแต่ละทิศทางในหน้าเดียว

แหล่งข้อมูล (ไฟล์เดียว): ชื่อไฟล์มีคำว่า "ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่" ในโฟลเดอร์ data
- ชีต "รายงานค่าเดินทาง"     : 1 แถว = 1 ใบงาน  → รายได้ (Total Freight), ต้นทุน (Total cost), กำไรสุทธิ, CM,
                                เที่ยววิ่ง (ขาขึ้น/ขาล่อง), Manifest Type
- ชีต "รายงานค่าเดินทาง3ปี"  : ใช้คอลัมน์ Manifest No. + Trip Key เป็นสะพานเชื่อมไปหาเที่ยว
                                (คอลัมน์ Trip Key Unique ในชีตนี้เป็นรายการแยก ไม่ตรงแถว จึงไม่ใช้)
- ชีต "Loadfactor_Data"       : 1 แถว = 1 เที่ยว → น้ำหนัก ความจุ ปริมาตร Ton-km

การคำนวณ
- กำไรสุทธิ = Total Freight − Total cost   (ใช้ค่าจากไฟล์ ถ้าไม่มีคอลัมน์จึงคำนวณเอง)
- CM        = Total Freight − ต้นทุนผันแปร (ใช้ค่าจากไฟล์)
- ทิศทาง     = Loading → Unloading · ขาขึ้น/ขาล่อง ของทิศทาง = ค่าที่พบบ่อยที่สุดในคอลัมน์ เที่ยววิ่ง
- ประเภทเที่ยว (ดูจาก Manifest Type + เที่ยววิ่ง แบบเดียวกับหน้าอื่น):
    รถว่างไปสาขา · เที่ยวเปล่า (ของเหมาตีเปล่า/เที่ยวเปล่า) · ยกเลิก · นอกนั้น = เที่ยววิ่งปกติ
- Load Factor ของกลุ่ม = น้ำหนักรวม ÷ ความจุรวม (นับแต่ละเที่ยวครั้งเดียว)
  ปริมาตร: ไม่นับเที่ยวที่ Volume LF > 150% (เหมือนหน้า Load Factor)
- ต้นทุนต่อตัน-กม. = ต้นทุนของเที่ยวที่มีข้อมูล Load Factor ÷ Ton-km รวม
"""

import math
import re
from html import escape as esc
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from transport_cost_route import (
    GRAY,
    PAGE_CSS,
    THAI_MONTHS,
    _card,
    _style,
    _table_html,
    _tint,
    _wkey,
    build_route_colors,
)

DATA_FOLDER = Path("data")
FILE_KEYWORD = "ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่"
NO_ROUTE = "ไม่ระบุเส้นทาง"
PLOT_CONFIG = {"displayModeBar": False}

C_REV = "#7CC4D6"
C_COST = "#F4A3AE"
C_POS = "#3E9E6A"
C_NEG = "#D0505C"
C_LF = "#9B7BD1"
C_DARK = "#334155"

# ประเภทเที่ยว
TT_NORMAL, TT_EMPTY, TT_BRANCH, TT_CANCEL = "เที่ยววิ่งปกติ", "เที่ยวเปล่า", "รถว่างไปสาขา", "ยกเลิก"
TRIP_TYPES = [TT_NORMAL, TT_EMPTY, TT_BRANCH, TT_CANCEL]
TT_COLORS = {TT_NORMAL: "#86CFA3", TT_EMPTY: "#F07C8C", TT_BRANCH: "#F6AE6B", TT_CANCEL: "#BBA0E3"}

# ขาขึ้น / ขาล่อง (สีเดียวกับหน้า Transportation Cost)
RUN_BG = {"ขาขึ้น": "#F07C8C", "ขาล่อง": "#7CC4D6"}
RUN_FG = {"ขาขึ้น": "#C23B53", "ขาล่อง": "#2F7F95"}

# ชื่อคอลัมน์ (เรียงตามลำดับความสำคัญ เทียบแบบไม่สนช่องว่าง/ตัวพิมพ์)
COST_COLS = {
    "date": ["Disbursement Date"],
    "req_date": ["Travel Req. Date"],
    "req_no": ["Travel Req. No."],
    "branch": ["Branch", "สาขา"],
    "vehicle": ["Vehicle Model"],
    "plate": ["License Plate"],
    "manifest": ["Manifest No."],
    "mtype": ["Manifest Type"],
    "run": ["เที่ยววิ่ง"],
    "revenue": ["Total Freight"],
    "load": ["Loading"],
    "unload": ["Unloading"],
    "distance": ["ระยะทาง"],
    "travel_cost": ["รวมต้นทุนค่าเดินทาง"],
    "repair_cost": ["รวมต้นทุนค่าซ่อม"],
    "depr": ["รวมค่าเสื่อม"],
    "cost": ["Total cost"],
    "profit": ["กำไรสุทธิ"],
    "cm": ["CM"],
}
BRIDGE_COLS = {"manifest": ["Manifest No."], "year": ["Travel Year"], "trip_key": ["Trip Key"]}
LF_COLS = {
    "key": ["Trip Key Unique"],
    "weight": ["Trip Weight", "Trip Weight (kg)"],
    "cap": ["Trip Weight Capacity", "Weight Capacity (kg)"],
    "volume": ["Trip Volume (m³)", "Trip Volume (m3)", "Trip Volume"],
    "vcap": ["Trip Volume Capacity", "Volume Capacity (m³)"],
    "tonkm": ["Ton-km"],
}

EXTRA_CSS = """
<style>
.do-kpi-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; margin:6px 0 12px; }
.do-kpi-grid .tc-kpi { min-width:0; padding:14px 16px; gap:12px; }
.do-kpi-grid .tc-kpi > div:last-child { min-width:0; }
.do-kpi-grid .tc-kpi-icon { width:40px; height:40px; font-size:19px; border-radius:12px; }
.do-kpi-grid .tc-kpi-value { font-size:22px; overflow:hidden; text-overflow:ellipsis; }
.do-kpi-grid .tc-kpi-sub { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
@media (max-width:1100px){ .do-kpi-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width:640px){ .do-kpi-grid { grid-template-columns:1fr; } }
.do-lf2 { display:flex; gap:14px; flex-wrap:wrap; margin-top:2px; }
.do-lf2 span { font-size:12px; color:#64748B; font-weight:600; }
.do-lf2 b { display:block; font-size:20px; font-weight:800; color:#0F172A; line-height:1.15; }
.do-lf2 .on b { color:#7C5CC4; }
.do-pos { color:#2E8B57 !important; font-weight:700; }
.do-neg { color:#C23B53 !important; font-weight:700; }
.do-dirtag { display:inline-block; font-size:11px; font-weight:700; padding:1px 8px; border-radius:99px; margin-right:8px; min-width:44px; text-align:center; }
.do-badge { display:inline-block; font-size:11.5px; font-weight:700; padding:1px 8px; border-radius:99px; white-space:nowrap; }
tr.do-grp td { border-top:2px solid #F3C9D1 !important; }
.do-missing { font-style:italic; text-align:center !important; }
.do-quad { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px; margin:4px 0 8px; }
.do-quad div { border-radius:12px; padding:8px 12px; font-size:12.5px; color:#475569; }
.do-quad b { display:block; font-size:18px; color:#0F172A; }
.do-quad small { display:block; color:#64748B; }
.do-how { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; padding:8px 12px; font-size:12.5px; color:#475569; line-height:1.6; margin:4px 0 6px; }
.do-box-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:10px; margin:8px 0 12px; }
.do-box { background:#FFF8F9; border:1px solid #F6DDE2; border-radius:14px; padding:10px 14px; min-width:0; }
.do-box .k { font-size:12px; color:#64748B; font-weight:600; }
.do-box .v { font-size:20px; font-weight:800; color:#0F172A; line-height:1.25; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.do-box .s { font-size:11.5px; color:#94A3B8; }
@media (max-width:900px){ .do-quad { grid-template-columns:repeat(2, minmax(0,1fr)); } }
</style>
"""
ARROW = ' <span class="tc-arrow">→</span> '


# =========================================================
# FORMAT HELPERS
# =========================================================

def _nz(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def fm(v):
    """เงินแบบย่อ มีเครื่องหมายลบ"""
    v = _nz(v)
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    a = abs(v)
    return f"{sign}฿{a / 1e6:,.2f}M" if a >= 1_000_000 else f"{sign}฿{a:,.0f}"


def ff(v):
    """เงินเต็มจำนวน มีเครื่องหมายลบ"""
    v = _nz(v)
    if v is None:
        return "—"
    return f"{'-' if v < 0 else ''}฿{abs(v):,.0f}"


def fp(v):
    v = _nz(v)
    return "—" if v is None else f"{v * 100:,.1f}%"


def fck(v):
    """ต้นทุนต่อตัน-กม."""
    v = _nz(v)
    return "—" if v is None else f"฿{v:,.2f}"


def sign_cls(v):
    v = _nz(v)
    if v is None:
        return ""
    return "do-pos" if v >= 0 else "do-neg"


def _norm(v) -> str:
    return re.sub(r"\s+", "", str(v)).casefold()


def _div(a, b):
    a, b = _nz(a), _nz(b)
    if a is None or not b:
        return float("nan")
    return a / b


def _arrow_html(name) -> str:
    return esc(str(name)).replace(" → ", ARROW)


def _run_tag(run) -> str:
    run = run or "ไม่ระบุ"
    bg = RUN_BG.get(run, "#CBD5E1")
    fg = RUN_FG.get(run, "#475569")
    return f'<span class="do-dirtag" style="background:{_tint(bg, 0.78)};color:{fg}">{esc(run)}</span>'


def _tt_badge(t) -> str:
    c = TT_COLORS.get(t, "#CBD5E1")
    return f'<span class="do-badge" style="background:{_tint(c, 0.72)};color:#3F2A2E">{esc(t)}</span>'


# =========================================================
# DATA
# =========================================================

def find_source_file():
    if not DATA_FOLDER.exists():
        return None
    target = re.sub(r"[\s_\-]+", "", FILE_KEYWORD.casefold())
    files = [
        f for f in DATA_FOLDER.iterdir()
        if f.is_file() and f.suffix.lower() in {".xlsx", ".xlsm", ".xls"}
        and not f.name.startswith("~$")
        and target in re.sub(r"[\s_\-]+", "", f.stem.casefold())
    ]
    return max(files, key=lambda f: f.stat().st_mtime_ns) if files else None


def _pick_sheet(names, exact=None, contains=None):
    for s in names:
        if exact is not None and _norm(s) == _norm(exact):
            return s
    for s in names:
        if contains is not None and _norm(contains) in _norm(s):
            return s
    return None


def _read(xl, sheet, spec):
    """อ่านเฉพาะคอลัมน์ที่ต้องใช้ เลือกชื่อตามลำดับความสำคัญใน spec แล้วเปลี่ยนเป็นชื่อกลาง"""
    header = [str(c) for c in xl.parse(sheet, nrows=0).columns]
    by_norm = {}
    for c in header:
        by_norm.setdefault(_norm(c), c)
    chosen = {}
    for key, aliases in spec.items():
        for a in aliases:
            hit = by_norm.get(_norm(a))
            if hit is not None and hit not in chosen.values():
                chosen[key] = hit
                break
    if not chosen:
        return pd.DataFrame()
    wanted = set(chosen.values())
    df = xl.parse(sheet, usecols=lambda c: str(c) in wanted)
    df.columns = [str(c) for c in df.columns]
    return df[[chosen[k] for k in chosen]].rename(columns={v: k for k, v in chosen.items()})


def _num(s):
    out = pd.to_numeric(
        s.astype("string").str.replace(",", "", regex=False).str.strip(), errors="coerce"
    )
    return out.astype("float64")


def _manifest_key(s):
    """Manifest No. ให้เป็นข้อความเดียวกัน ไม่ว่าในไฟล์จะเก็บเป็นตัวเลขหรือข้อความ"""
    txt = s.astype("string").str.strip()
    num = pd.to_numeric(txt, errors="coerce")
    as_int = num.where(num.notna() & (num == num.round())).astype("Int64").astype("string")
    out = as_int.fillna(txt.str.replace(r"\.0$", "", regex=True))
    return out.mask(out.isin(["", "<NA>", "nan", "None"]))


def _parse_date(series):
    if pd.api.types.is_datetime64_any_dtype(series):
        dt = pd.to_datetime(series, errors="coerce")
    else:
        text = series.astype("string").str.strip()
        num = pd.to_numeric(text, errors="coerce")
        serial = num.where(num.between(20000, 80000))
        try:
            dt = pd.to_datetime(text.where(serial.isna()), dayfirst=True, errors="coerce", format="mixed")
        except (TypeError, ValueError):
            dt = pd.to_datetime(text.where(serial.isna()), dayfirst=True, errors="coerce")
        if serial.notna().any():
            dt = dt.fillna(pd.to_datetime(serial, unit="D", origin="1899-12-30", errors="coerce"))
    be = dt.dt.year > 2400
    if be.any():
        dt = dt.where(~be, dt - pd.DateOffset(years=543))
    return dt


def _be_year(y):
    y = _nz(y)
    if y is None:
        return ""
    y = int(y)
    return str(y + 543 if y < 2400 else y)


def _mode_run(s):
    """ขาขึ้น/ขาล่อง ของทิศทาง: ค่าที่พบบ่อยที่สุด (ให้ความสำคัญกับ ขาขึ้น/ขาล่อง ก่อนค่าอื่น)"""
    s = s[s.ne("")]
    ud = s[s.isin(list(RUN_BG))]
    src = ud if not ud.empty else s
    return src.value_counts().index[0] if not src.empty else ""


def build_dataset(path):
    """คืน (ข้อมูลรายใบงาน, ข้อมูล Load Factor รายเที่ยว, ข้อมูลสรุปการจับคู่)"""
    xl = pd.ExcelFile(path)
    names = xl.sheet_names

    cost_sheet = _pick_sheet(names, exact="รายงานค่าเดินทาง")
    bridge_sheet = _pick_sheet(names, exact="รายงานค่าเดินทาง3ปี", contains="3ปี")
    lf_sheet = _pick_sheet(names, exact="Loadfactor_Data", contains="loadfactor")
    if cost_sheet is None:
        raise ValueError("ไม่พบชีต “รายงานค่าเดินทาง” ในไฟล์")

    c = _read(xl, cost_sheet, COST_COLS)
    missing = [k for k in ("revenue", "cost", "load", "unload") if k not in c.columns]
    if missing:
        names_th = {"revenue": "Total Freight", "cost": "Total cost", "load": "Loading", "unload": "Unloading"}
        raise ValueError("ชีต รายงานค่าเดินทาง ขาดคอลัมน์: " + ", ".join(names_th[m] for m in missing))

    out = pd.DataFrame(index=c.index)
    date_src = c["date"] if "date" in c else c.get("req_date")
    out["_Date"] = _parse_date(date_src) if date_src is not None else pd.NaT
    if "req_date" in c and "date" in c:
        out["_Date"] = out["_Date"].fillna(_parse_date(c["req_date"]))
    out["_Year"] = out["_Date"].dt.year.map(_be_year)
    out["_MonthNum"] = out["_Date"].dt.month

    def text(k):
        if k not in c:
            return pd.Series("", index=c.index, dtype="string")
        return c[k].astype("string").fillna("").str.strip()

    out["_Branch"] = text("branch")
    out["_Vehicle"] = text("vehicle")
    out["_Plate"] = text("plate")
    out["_MType"] = text("mtype")
    out["_Run"] = text("run")
    out["_ReqNo"] = text("req_no")
    out["_Manifest"] = _manifest_key(c["manifest"]) if "manifest" in c else pd.NA
    out["_Load"] = text("load")
    out["_Unload"] = text("unload")
    has_route = out["_Load"].ne("") | out["_Unload"].ne("")
    out["_Dir"] = (out["_Load"].replace("", "ไม่ระบุ") + " → " + out["_Unload"].replace("", "ไม่ระบุ")).where(
        has_route, NO_ROUTE)
    out["_DirKey"] = out["_Load"] + "|" + out["_Unload"]
    out["_RevKey"] = out["_Unload"] + "|" + out["_Load"]
    out["_PairKey"] = ["|".join(sorted((a, b))) for a, b in zip(out["_Load"], out["_Unload"])]

    # ประเภทเที่ยว (ตรรกะเดียวกับหน้า Transportation Cost / เที่ยวเปล่า)
    both = out["_MType"] + " " + out["_Run"]
    is_branch = both.str.contains("รถว่างไปสาขา", regex=False, na=False)
    is_empty = both.str.contains(r"ของเหมาตีเปล่า|เที่ยวเปล่า", regex=True, na=False) & ~is_branch
    is_cancel = both.str.contains("ยกเลิก", regex=False, na=False) & ~is_branch & ~is_empty
    out["_TType"] = TT_NORMAL
    out.loc[is_empty, "_TType"] = TT_EMPTY
    out.loc[is_branch, "_TType"] = TT_BRANCH
    out.loc[is_cancel, "_TType"] = TT_CANCEL

    out["_Rev"] = _num(c["revenue"]).fillna(0)
    out["_Cost"] = _num(c["cost"]).fillna(0)
    out["_Profit"] = _num(c["profit"]).fillna(out["_Rev"] - out["_Cost"]) if "profit" in c else out["_Rev"] - out["_Cost"]
    out["_CM"] = _num(c["cm"]) if "cm" in c else float("nan")
    for k, col in (("travel_cost", "_TravelCost"), ("repair_cost", "_RepairCost"), ("depr", "_Depr")):
        out[col] = _num(c[k]).fillna(0) if k in c else 0.0
    out["_Distance"] = _num(c["distance"]).fillna(0) if "distance" in c else 0.0

    # ตัดแถวว่าง (ไม่มีเส้นทาง และไม่มีทั้งรายได้และต้นทุน)
    out = out[~(out["_Dir"].eq(NO_ROUTE) & out["_Rev"].eq(0) & out["_Cost"].eq(0))].copy()

    # ---------- สะพาน Manifest → Trip Key ----------
    out["_TripKey"] = pd.NA
    if bridge_sheet is not None:
        b = _read(xl, bridge_sheet, BRIDGE_COLS)
        if {"manifest", "trip_key"} <= set(b.columns):
            b["mf"] = _manifest_key(b["manifest"])
            b["tk"] = b["trip_key"].astype("string").str.strip()
            b = b[b["mf"].notna() & b["tk"].notna() & b["tk"].ne("")]
            if "year" in b.columns:
                b["yk"] = b["year"].map(_be_year) + "|" + b["mf"]
                by_year = b.drop_duplicates("yk").set_index("yk")["tk"]
                out["_TripKey"] = (out["_Year"] + "|" + out["_Manifest"].fillna("")).map(by_year)
            # สำรอง: จับด้วยเลข Manifest อย่างเดียว เฉพาะเลขที่ไม่ซ้ำในชีตสะพาน
            uniq = b.drop_duplicates(["mf", "tk"])
            uniq = uniq[~uniq["mf"].duplicated(keep=False)].set_index("mf")["tk"]
            out["_TripKey"] = out["_TripKey"].fillna(out["_Manifest"].map(uniq))
    out["_TripKey"] = out["_TripKey"].astype("string")

    # เที่ยว = Trip Key ถ้าจับคู่ได้ ไม่งั้นใช้เลขใบงานค่าเดินทาง
    fallback = ("REQ|" + out["_ReqNo"]).where(out["_ReqNo"].ne(""), "ROW|" + out.index.astype(str))
    out["_Trip"] = out["_TripKey"].fillna(fallback)

    # ---------- Load Factor รายเที่ยว ----------
    lf = pd.DataFrame(columns=["key", "weight", "cap", "volume", "vcap", "tonkm"])
    if lf_sheet is not None:
        raw = _read(xl, lf_sheet, LF_COLS)
        if {"key", "weight", "cap"} <= set(raw.columns):
            lf = pd.DataFrame({"key": raw["key"].astype("string").str.strip()})
            for k in ("weight", "cap", "volume", "vcap", "tonkm"):
                lf[k] = _num(raw[k]) if k in raw else float("nan")
            lf = lf[lf["key"].notna() & lf["key"].ne("")].drop_duplicates("key")
            lf.loc[lf["cap"] <= 0, "cap"] = float("nan")
            # ปริมาตรเก็บเป็น ซม.³ → แปลงเป็น ม.³
            vr = (lf["volume"] / lf["vcap"]).replace([float("inf")], float("nan")).dropna()
            if not vr.empty and vr.median() > 100:
                lf["volume"] = lf["volume"] / 1_000_000
            # Volume LF > 150% = ตรวจสอบข้อมูล ไม่นับในปริมาตรรวม (เหมือนหน้า Load Factor)
            bad = (lf["volume"] / lf["vcap"]) > 1.5
            lf.loc[bad | lf["vcap"].le(0), ["volume", "vcap"]] = float("nan")
    lf = lf.set_index("key")
    out["_HasLF"] = out["_TripKey"].isin(lf.index)

    info = {
        "file": Path(path).name,
        "rows": len(out),
        "sheets": f"{cost_sheet} + {bridge_sheet or '—'} + {lf_sheet or '—'}",
    }
    return out, lf, info


@st.cache_data(show_spinner=False)
def load_direction_data(path_str: str, signature):
    return build_dataset(path_str)


# =========================================================
# AGGREGATION
# =========================================================

def summarize(df, lf, by):
    """สรุปตามกลุ่ม: เงินรวมจากรายใบงาน, Load Factor รวมจากรายเที่ยว (เที่ยวละครั้ง)"""
    g = df.groupby(by, dropna=False)
    s = g.agg(
        Trips=("_Trip", "nunique"),
        Revenue=("_Rev", "sum"),
        Cost=("_Cost", "sum"),
        Profit=("_Profit", "sum"),
        CM=("_CM", "sum"),
        TravelCost=("_TravelCost", "sum"),
        RepairCost=("_RepairCost", "sum"),
        Depr=("_Depr", "sum"),
    )
    s["CostLF"] = df[df["_HasLF"]].groupby(by, dropna=False)["_Cost"].sum()
    for label, col in ((TT_EMPTY, "Empty"), (TT_BRANCH, "Branch")):
        sub = df[df["_TType"] == label]
        if sub.empty:
            s[f"{col}Trips"], s[f"{col}Cost"] = 0.0, 0.0
        else:
            a = sub.groupby(by, dropna=False).agg(T=("_Trip", "nunique"), C=("_Cost", "sum"))
            s[f"{col}Trips"], s[f"{col}Cost"] = a["T"], a["C"]
    trips = df.loc[df["_HasLF"], [by, "_TripKey"]].drop_duplicates()
    if not trips.empty and not lf.empty:
        t = trips.join(lf, on="_TripKey")
        a = t.groupby(by, dropna=False).agg(
            LFTrips=("_TripKey", "nunique"), W=("weight", "sum"), Cap=("cap", "sum"),
            V=("volume", "sum"), VCap=("vcap", "sum"), TonKm=("tonkm", "sum"),
        )
        s = s.join(a)
    for col in ("LFTrips", "W", "Cap", "V", "VCap", "TonKm", "CostLF",
                "EmptyTrips", "EmptyCost", "BranchTrips", "BranchCost"):
        if col not in s:
            s[col] = 0.0
        s[col] = s[col].fillna(0)
    nan = float("nan")
    s["LossTrips"] = s["EmptyTrips"] + s["BranchTrips"]
    s["LossCost"] = s["EmptyCost"] + s["BranchCost"]
    s["LF"] = s["W"] / s["Cap"].where(s["Cap"] > 0, nan)
    s["VLF"] = s["V"] / s["VCap"].where(s["VCap"] > 0, nan)
    s["Margin"] = s["Profit"] / s["Revenue"].where(s["Revenue"] != 0, nan)
    s["CMPct"] = s["CM"] / s["Revenue"].where(s["Revenue"] != 0, nan)
    s["CostTonKm"] = s["CostLF"] / s["TonKm"].where(s["TonKm"] > 0, nan)
    s["RevPerTrip"] = s["Revenue"] / s["Trips"].where(s["Trips"] > 0, nan)
    s["ProfitPerTrip"] = s["Profit"] / s["Trips"].where(s["Trips"] > 0, nan)
    return s


def totals(df, lf):
    s = summarize(df.assign(_All="all"), lf, "_All")
    return s.iloc[0] if not s.empty else None


# =========================================================
# DASHBOARD
# =========================================================

def render_direction_overview_dashboard():
    path = find_source_file()
    if path is None:
        st.error(
            f"ไม่พบไฟล์ที่ชื่อมีคำว่า “{FILE_KEYWORD}” ในโฟลเดอร์ data "
            "— อัปโหลดไฟล์ในหน้า Data Management ก่อน"
        )
        return
    stat = path.stat()
    try:
        with st.spinner("กำลังอ่านไฟล์และจับคู่ข้อมูล (ครั้งแรกอาจใช้เวลาสักครู่)..."):
            data, lf, info = load_direction_data(str(path), (path.name, stat.st_mtime_ns, stat.st_size, "v2"))
    except Exception as e:
        st.error(f"อ่านไฟล์ {path.name} ไม่สำเร็จ: {e}")
        return
    if data.empty:
        st.info("ไม่มีข้อมูลในชีต รายงานค่าเดินทาง")
        return

    st.markdown(PAGE_CSS + EXTRA_CSS, unsafe_allow_html=True)

    # ---------------- ตัวกรอง ----------------
    fcard = _card("do_filters")
    fcard.markdown('<div class="tc-filter-title">🔎 ตัวกรองข้อมูล</div>', unsafe_allow_html=True)
    f1, f2, f3, f4, f5 = fcard.columns([0.8, 1.1, 1.4, 1.2, 1.0])
    filtered = data
    with f1:
        year_opts = sorted((y for y in data["_Year"].unique() if y), reverse=True)
        year = st.selectbox("ปี", ["ทั้งหมด"] + year_opts, key="do_year")
    if year != "ทั้งหมด":
        filtered = filtered[filtered["_Year"] == year]
    with f2:
        months = sorted(int(m) for m in filtered["_MonthNum"].dropna().unique())
        chosen_months = st.multiselect("เดือน", [THAI_MONTHS[m] for m in months],
                                       placeholder="ทั้งหมด", key=_wkey("do_month", months))
    if chosen_months:
        nums = [n for n, lab in THAI_MONTHS.items() if lab in chosen_months]
        filtered = filtered[filtered["_MonthNum"].isin(nums)]
    with f3:
        tt_opts = [t for t in TRIP_TYPES if (filtered["_TType"] == t).any()]
        chosen_tt = st.multiselect("ประเภทเที่ยว", tt_opts, placeholder="ทั้งหมด (รวมเที่ยวเปล่า/รถว่าง)",
                                   key=_wkey("do_ttype", tt_opts),
                                   help="เที่ยวเปล่า = Manifest Type ของเหมาตีเปล่า/เที่ยวเปล่า · "
                                        "รถว่างไปสาขา ดูจาก Manifest Type หรือ เที่ยววิ่ง")
    if chosen_tt:
        filtered = filtered[filtered["_TType"].isin(chosen_tt)]
    with f4:
        veh_opts = sorted(v for v in filtered["_Vehicle"].unique() if v)
        chosen_veh = st.multiselect("ประเภทรถ", veh_opts, placeholder="ทั้งหมด", key=_wkey("do_vehicle", veh_opts))
    if chosen_veh:
        filtered = filtered[filtered["_Vehicle"].isin(chosen_veh)]
    with f5:
        br_opts = sorted(v for v in filtered["_Branch"].unique() if v)
        if br_opts:
            chosen_br = st.multiselect("สาขา", br_opts, placeholder="ทั้งหมด", key=_wkey("do_branch", br_opts))
            if chosen_br:
                filtered = filtered[filtered["_Branch"].isin(chosen_br)]
        else:
            st.caption("ไม่มีข้อมูลสาขา")

    g1, g2, g3, g4, g5 = fcard.columns([2.2, 1, 1, 1.05, 1.05])
    with g1:
        dir_opts = sorted(d for d in filtered["_Dir"].unique() if d and d != NO_ROUTE)
        chosen_dirs = st.multiselect("ทิศทาง (ต้นทาง → ปลายทาง)", dir_opts,
                                     placeholder="ทั้งหมด — พิมพ์ชื่อสถานที่เพื่อค้นหา",
                                     key=_wkey("do_dirs", dir_opts))
    with g2:
        run_opts = sorted(v for v in filtered["_Run"].unique() if v)
        chosen_run = st.multiselect("ขาขึ้น / ขาล่อง", run_opts, placeholder="ทั้งหมด", key=_wkey("do_run", run_opts))
    if chosen_run:
        filtered = filtered[filtered["_Run"].isin(chosen_run)]
    with g3:
        mt_opts = sorted(v for v in filtered["_MType"].unique() if v)
        chosen_mt = st.multiselect("ประเภทใบงาน", mt_opts, placeholder="ทั้งหมด", key=_wkey("do_mtype", mt_opts))
    if chosen_mt:
        filtered = filtered[filtered["_MType"].isin(chosen_mt)]
    with g4:
        basis = st.radio("วัดกำไรด้วย", ["กำไรสุทธิ", "CM"], horizontal=True, key="do_basis",
                         help="กำไรสุทธิ = รายได้ − ต้นทุนทั้งหมด · CM = รายได้ − ต้นทุนผันแปร")
    with g5:
        lf_basis = st.radio("Load Factor ใช้วัด", ["น้ำหนัก", "ปริมาตร"], horizontal=True, key="do_lf_basis",
                            help="ใช้กับกราฟจัดกลุ่ม อันดับ และข้อสังเกต · ตารางแสดงทั้งสองค่าเสมอ")
    base = filtered  # ก่อนกรองทิศทาง ใช้หาขากลับ
    if chosen_dirs:
        filtered = filtered[filtered["_Dir"].isin(chosen_dirs)]
    if filtered.empty:
        st.info("ไม่มีข้อมูลตามตัวกรองที่เลือก")
        return

    P = "Profit" if basis == "กำไรสุทธิ" else "CM"
    PP = "Margin" if P == "Profit" else "CMPct"
    P_LABEL = basis
    LFK = "LF" if lf_basis == "น้ำหนัก" else "VLF"
    LF_LABEL = f"LF {lf_basis}"

    dirs = summarize(filtered, lf, "_Dir")
    valid = dirs.drop(index=NO_ROUTE, errors="ignore").copy()
    first = filtered.groupby("_Dir")[["_Load", "_Unload", "_DirKey", "_RevKey", "_PairKey"]].first()
    first["Run"] = filtered.groupby("_Dir")["_Run"].agg(_mode_run)
    valid = valid.join(first)
    valid.index.name = "_Dir"
    valid = valid.reset_index()
    route_colors = build_route_colors(valid.sort_values("Revenue", ascending=False)["_Dir"])
    tot = totals(filtered, lf)

    # ---------------- การ์ดตัวเลข ----------------
    def kpi(icon, bg, label, value, sub, value_cls=""):
        return (
            f'<div class="tc-kpi"><div class="tc-kpi-icon" style="background:{bg}">{icon}</div>'
            f'<div><div class="tc-kpi-label">{esc(label)}</div>'
            f'<div class="tc-kpi-value {value_cls}" title="{esc(value)}">{esc(value)}</div>'
            f'<div class="tc-kpi-sub" title="{esc(sub)}">{esc(sub)}</div></div></div>'
        )

    lf_cover = _div(tot["LFTrips"], tot["Trips"])
    cards = [
        kpi("🚚", "#FFE8EC", "จำนวนเที่ยว", f'{int(tot["Trips"]):,}',
            f'{int(valid["_Dir"].nunique()):,} ทิศทาง'),
        kpi("💵", "#E6F4FA", "รายได้", fm(tot["Revenue"]), f'เฉลี่ย {ff(tot["RevPerTrip"])} ต่อเที่ยว'),
        kpi("🧾", "#FFF0E6", "ต้นทุนรวม", fm(tot["Cost"]),
            f'เฉลี่ย {ff(_div(tot["Cost"], tot["Trips"]))} ต่อเที่ยว'),
        kpi("📈", "#E7F6EE", "กำไรสุทธิ", fm(tot["Profit"]), f'อัตรากำไร {fp(tot["Margin"])}',
            sign_cls(tot["Profit"])),
        kpi("➕", "#EEF2FF", "CM", fm(tot["CM"]), f'{fp(tot["CMPct"])} ของรายได้', sign_cls(tot["CM"])),
        (f'<div class="tc-kpi"><div class="tc-kpi-icon" style="background:#F3EEFB">⚖️</div>'
         f'<div><div class="tc-kpi-label">Load Factor</div><div class="do-lf2">'
         f'<span class="{"on" if LFK == "LF" else ""}">น้ำหนัก<b>{fp(tot["LF"])}</b></span>'
         f'<span class="{"on" if LFK == "VLF" else ""}">ปริมาตร<b>{fp(tot["VLF"])}</b></span></div>'
         f'<div class="tc-kpi-sub">มีข้อมูล {fp(lf_cover)} ของเที่ยว</div></div></div>'),
        kpi("🛣️", "#FFF7E0", "ต้นทุนต่อตัน-กม.", fck(tot["CostTonKm"]), f'{tot["TonKm"]:,.0f} ตัน-กม.'),
        kpi("🅾️", "#FDE9EC", "เที่ยวเปล่า + รถว่างไปสาขา", fm(tot["LossCost"]),
            f'เปล่า {int(tot["EmptyTrips"]):,} · รถว่าง {int(tot["BranchTrips"]):,} เที่ยว',
            "do-neg" if tot["LossCost"] > 0 else ""),
    ]
    st.markdown('<div class="do-kpi-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)

    # ---------------- ข้อสังเกตสำคัญ ----------------
    min_trips_insight = 5
    rel = valid[valid["Trips"] >= min_trips_insight]
    if rel.empty:
        rel = valid
    if not rel.empty:
        cells = []
        best = rel.loc[rel[P].idxmax()]
        cells.append(("#3E9E6A", "🏆", f"ทิศทางที่{P_LABEL}สูงสุด", fm(best[P]), best["_Dir"],
                      f'{int(best["Trips"]):,} เที่ยว · อัตรา {fp(best[PP])} · LF น้ำหนัก {fp(best["LF"])} · ปริมาตร {fp(best["VLF"])}'))
        worst = rel.loc[rel[P].idxmin()]
        if worst[P] < 0:
            cells.append(("#C23B53", "🚨", "ทิศทางที่ขาดทุนมากที่สุด", fm(worst[P]), worst["_Dir"],
                          f'{int(worst["Trips"]):,} เที่ยว · อัตรา {fp(worst[PP])} · LF น้ำหนัก {fp(worst["LF"])} · ปริมาตร {fp(worst["VLF"])}'))
        loss_dirs = valid[valid["LossCost"] > 0]
        if not loss_dirs.empty:
            top_loss = loss_dirs.loc[loss_dirs["LossCost"].idxmax()]
            cells.append(("#D9772B", "🅾️", "เที่ยวเปล่า/รถว่าง สูงสุด", fm(top_loss["LossCost"]), top_loss["_Dir"],
                          f'เปล่า {int(top_loss["EmptyTrips"]):,} · รถว่าง {int(top_loss["BranchTrips"]):,} เที่ยว'))
        lf_rel = rel[rel[LFK].notna()]
        if not lf_rel.empty:
            low = lf_rel.loc[lf_rel[LFK].idxmin()]
            cells.append(("#7C5CC4", "📦", f"บรรทุกน้อยที่สุด ({LF_LABEL})", fp(low[LFK]), low["_Dir"],
                          f'{int(low["Trips"]):,} เที่ยว · {P_LABEL} {fm(low[P])}'))
        html_cells = "".join(
            f'<div class="tc-ins"><div class="tc-ins-top">'
            f'<span class="tc-ins-icon" style="background:{_tint(c, 0.86)}">{icon}</span>'
            f'<span class="tc-ins-title">{esc(title)}</span></div>'
            f'<div class="tc-ins-metric" style="color:{c}">{esc(metric)}</div>'
            f'<div class="tc-ins-main" title="{esc(str(main))}">{esc(str(main))}</div>'
            f'<div class="tc-ins-sub">{esc(sub)}</div></div>'
            for c, icon, title, metric, main, sub in cells
        )
        note = f" (ทิศทางที่วิ่ง ≥{min_trips_insight} เที่ยว)" if rel is not valid else ""
        st.markdown(
            f'<div class="tc-ins-card"><div class="tc-ins-head">ข้อสังเกตสำคัญ{note}</div>'
            f'<div class="tc-ins-grid" style="grid-template-columns:repeat({len(cells)}, minmax(0, 1fr))">'
            f"{html_cells}</div></div>",
            unsafe_allow_html=True,
        )

    # ---------------- จัดกลุ่มทิศทาง: บรรทุก × กำไร ----------------
    with _card("do_quad"):
        st.markdown(f"#### จัดกลุ่มทิศทาง: บรรทุกเต็มแค่ไหน ({LF_LABEL}) × {P_LABEL}ดีแค่ไหน")
        q1, q2, _q3 = st.columns([1, 1, 2])
        with q1:
            lf_target = st.selectbox(f"ถือว่า “บรรทุกดี” เมื่อ {LF_LABEL} ถึง", [40, 50, 60, 70, 80], index=1,
                                     format_func=lambda v: f"{v}%", key="do_lf_target2")
        with q2:
            min_trips = st.selectbox("แสดงทิศทางที่วิ่งอย่างน้อย", [1, 5, 10, 20, 50], index=2,
                                     format_func=lambda v: f"{v} เที่ยว", key="do_min_trips2")
        q = valid[(valid["Trips"] >= min_trips) & valid[LFK].notna() & (valid["Revenue"] != 0)].copy()
        if q.empty:
            st.info(f"ไม่มีทิศทางที่มีทั้งข้อมูลรายได้และ {LF_LABEL} ตามเงื่อนไข")
        else:
            t = lf_target
            q["x_real"] = q[LFK] * 100
            q["y_real"] = q[PP] * 100
            q["x"] = q["x_real"].clip(upper=110)
            q["y"] = q["y_real"].clip(-100, 100)
            groups = [
                ("fix", "🚨 บรรทุกน้อย + ขาดทุน", "แก้ก่อน: รวมเที่ยว/ลดรอบวิ่ง", C_NEG,
                 (q["x_real"] < t) & (q[P] < 0)),
                ("price", "💲 บรรทุกดี แต่ขาดทุน", "ดูราคาค่าขนส่ง/ต้นทุน", "#F6AE6B",
                 (q["x_real"] >= t) & (q[P] < 0)),
                ("room", "📦 มีกำไร แต่ยังเติมของได้", "หาของเพิ่ม/ใช้รถเล็กลง", C_REV,
                 (q["x_real"] < t) & (q[P] >= 0)),
                ("good", "✅ บรรทุกดี + มีกำไร", "รักษาไว้", C_POS,
                 (q["x_real"] >= t) & (q[P] >= 0)),
            ]
            q["grp"] = ""
            for key, _n, _a, _c, m in groups:
                q.loc[m, "grp"] = key

            st.markdown(
                '<div class="do-how">📖 <b>วิธีอ่าน:</b> แต่ละวงกลม = 1 ทิศทาง · '
                f'<b>ยิ่งไปทางขวา</b> = บรรทุกเต็มกว่า วัดด้วย{LF_LABEL} (เส้นประแนวตั้ง = {t}%) · '
                f'<b>ยิ่งสูง</b> = {P_LABEL}ต่อรายได้ดีกว่า (เส้นประแนวนอน = 0%) · '
                'วงใหญ่ = วิ่งบ่อย · ชื่อที่แสดง = 8 ทิศทางที่วิ่งบ่อยที่สุด · '
                'ดูรายชื่อทั้งหมดของแต่ละกลุ่มได้ในแท็บด้านล่างกราฟ</div>',
                unsafe_allow_html=True,
            )

            y_lo = max(-105.0, min(float(q["y"].min()), 0.0) - 12)
            y_hi = min(105.0, max(float(q["y"].max()), 0.0) + 12)
            x_hi = max(100.0, float(q["x"].max())) + 6
            mx = float(q["Trips"].max()) or 1
            q["size"] = 8 + 26 * (q["Trips"] / mx) ** 0.5
            top_names = set(q.nlargest(8, "Trips")["_Dir"])

            fig = go.Figure()
            shade = [(0, t, 0, y_hi, C_REV), (t, x_hi, 0, y_hi, C_POS),
                     (0, t, y_lo, 0, C_NEG), (t, x_hi, y_lo, 0, "#F6AE6B")]
            for x0, x1, y0, y1, col in shade:
                if y1 > y0:
                    fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, fillcolor=_tint(col, 0.9),
                                  line=dict(width=0), layer="below")
            for key, name, _a, col, _m in groups:
                n = int((q["grp"] == key).sum())
                fig.add_trace(go.Scatter(
                    name=f"{name} ({n})", x=q.loc[q["grp"] == key, "x"], y=q.loc[q["grp"] == key, "y"],
                    mode="markers+text",
                    marker=dict(size=q.loc[q["grp"] == key, "size"], color=col, opacity=0.8,
                                line=dict(color="white", width=1.2)),
                    text=[d if d in top_names else "" for d in q.loc[q["grp"] == key, "_Dir"]],
                    textposition="top center", textfont=dict(size=10.5, color=C_DARK),
                    customdata=q.loc[q["grp"] == key, ["_Dir", "Trips", "Revenue", "Cost", P, "y_real",
                                                       "LossTrips"]].assign(
                        _w=q["LF"] * 100, _v=q["VLF"] * 100).to_numpy(),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>%{customdata[1]:,} เที่ยว"
                        "<br>รายได้ ฿%{customdata[2]:,.0f} · ต้นทุน ฿%{customdata[3]:,.0f}"
                        f"<br>{P_LABEL} ฿%{{customdata[4]:,.0f}} (%{{customdata[5]:.1f}}%)"
                        "<br>LF น้ำหนัก %{customdata[7]:.1f}% · LF ปริมาตร %{customdata[8]:.1f}%"
                        "<br>เที่ยวเปล่า/รถว่าง %{customdata[6]:,.0f} เที่ยว<extra></extra>"
                    ),
                ))
            fig.add_vline(x=t, line=dict(color="#94A3B8", width=1.5, dash="dash"))
            fig.add_hline(y=0, line=dict(color="#94A3B8", width=1.5, dash="dash"))
            fig.update_layout(
                height=500, margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", y=-0.14, x=0, font=dict(size=12)),
                xaxis=dict(title=f"{LF_LABEL} (%) — ยิ่งขวายิ่งบรรทุกเต็ม", ticksuffix="%",
                           range=[0, x_hi], zeroline=False),
                yaxis=dict(title=f"อัตรา{P_LABEL} (% ของรายได้)", ticksuffix="%", range=[y_lo, y_hi],
                           zeroline=False),
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
            if (q["x_real"] > 110).any() or (q["y_real"].abs() > 100).any():
                st.caption("ทิศทางที่ Load Factor เกิน 110% หรืออัตรากำไรเกิน ±100% จะแสดงที่ขอบกราฟ "
                           "(ค่าจริงดูได้เมื่อชี้เมาส์ หรือในตารางด้านล่าง)")

            st.markdown(
                '<div class="do-quad">' + "".join(
                    f'<div style="background:{_tint(col, 0.88)}">{esc(name)}'
                    f'<b>{int((q["grp"] == key).sum()):,} ทิศทาง</b>'
                    f'{fm(q.loc[q["grp"] == key, P].sum())} · {int(q.loc[q["grp"] == key, "Trips"].sum()):,} เที่ยว'
                    f'<small>👉 {esc(action)}</small></div>'
                    for key, name, action, col, _m in groups
                ) + "</div>",
                unsafe_allow_html=True,
            )

            tabs = st.tabs([f"{name} ({int((q['grp'] == key).sum()):,})" for key, name, _a, _c, _m in groups])
            for tab, (key, name, _a, col, _m) in zip(tabs, groups):
                with tab:
                    part = q[q["grp"] == key].sort_values("Trips", ascending=False)
                    if part.empty:
                        st.info("ไม่มีทิศทางในกลุ่มนี้")
                        continue
                    body = []
                    for i, r in enumerate(part.head(100).to_dict("records"), 1):
                        body.append(
                            "<tr>"
                            f'<td class="tc-rank">{i}</td>'
                            f'<td>{_run_tag(r["Run"])}<b>{_arrow_html(r["_Dir"])}</b></td>'
                            f'<td class="tc-num">{int(r["Trips"]):,}</td>'
                            f'<td class="tc-num">{ff(r["Revenue"])}</td>'
                            f'<td class="tc-num {sign_cls(r[P])}">{ff(r[P])}</td>'
                            f'<td class="tc-num {sign_cls(r[PP])}">{fp(r[PP])}</td>'
                            f'<td class="tc-num">{fp(r["LF"])}</td>'
                            f'<td class="tc-num">{fp(r["VLF"])}</td>'
                            f'<td class="tc-num tc-muted">{int(r["LossTrips"]):,}</td>'
                            "</tr>"
                        )
                    st.caption(f"{len(part):,} ทิศทาง · เรียงตามจำนวนเที่ยว · แสดงสูงสุด 100 ทิศทาง")
                    st.markdown(_table_html(
                        ["#", "ทิศทาง", "เที่ยว", "รายได้", P_LABEL, f"อัตรา{P_LABEL}", "LF น้ำหนัก",
                         "LF ปริมาตร", "เที่ยวเปล่า/รถว่าง"],
                        body, right_cols={2, 3, 4, 5, 6, 7, 8}, max_height=380), unsafe_allow_html=True)

    # ---------------- อันดับทิศทาง: รายได้ vs ต้นทุน ----------------
    with _card("do_rank"):
        st.markdown("#### อันดับทิศทาง: รายได้ เทียบ ต้นทุน")
        sort_map = {
            "รายได้สูงสุด": ("Revenue", False),
            "ต้นทุนสูงสุด": ("Cost", False),
            f"{P_LABEL}สูงสุด": (P, False),
            "ขาดทุนมากที่สุด": (P, True),
            "ต้นทุนเที่ยวเปล่า + รถว่างไปสาขา สูงสุด": ("LossCost", False),
            "จำนวนเที่ยวมากที่สุด": ("Trips", False),
            f"{LF_LABEL} ต่ำสุด": (LFK, True),
        }
        r1, r2 = st.columns([1.6, 0.6])
        with r1:
            sort_label = st.selectbox("เรียงตาม", list(sort_map), key=_wkey("do_rank_sort", list(sort_map)))
        with r2:
            top_n = st.selectbox("จำนวน Top", [5, 10, 15, 20, 30], index=1, key="do_rank_top")
        col, asc = sort_map[sort_label]
        pool = valid
        if sort_label == "ขาดทุนมากที่สุด":
            pool = pool[pool[P] < 0]
        if col == "LossCost":
            pool = pool[pool["LossCost"] > 0]
        if col in ("LF", "VLF"):
            pool = pool[pool[col].notna()]
        plot = pool.sort_values(col, ascending=asc, na_position="last").head(top_n).iloc[::-1]
        st.caption(f"แท่งฟ้า = รายได้ · แท่งชมพู = ต้นทุน · ◆ = {P_LABEL} (เขียว = กำไร, แดง = ขาดทุน)"
                   + (" · แท่งส้ม = ต้นทุนของเที่ยวเปล่า + รถว่างไปสาขา" if col == "LossCost" else ""))
        if plot.empty:
            st.info("ไม่มีทิศทางตามเงื่อนไขนี้")
        else:
            fig = go.Figure()
            fig.add_trace(go.Bar(name="รายได้", y=plot["_Dir"], x=plot["Revenue"], orientation="h",
                                 marker_color=C_REV, hovertemplate="%{y}<br>รายได้ ฿%{x:,.0f}<extra></extra>"))
            fig.add_trace(go.Bar(name="ต้นทุน", y=plot["_Dir"], x=plot["Cost"], orientation="h",
                                 marker_color=C_COST, hovertemplate="%{y}<br>ต้นทุน ฿%{x:,.0f}<extra></extra>"))
            if col == "LossCost":
                fig.add_trace(go.Bar(
                    name="ต้นทุนเที่ยวเปล่า + รถว่าง", y=plot["_Dir"], x=plot["LossCost"], orientation="h",
                    marker_color="#F6AE6B",
                    customdata=plot[["EmptyTrips", "BranchTrips"]].to_numpy(),
                    hovertemplate=("%{y}<br>ต้นทุนเที่ยวเปล่า+รถว่าง ฿%{x:,.0f}"
                                   "<br>เปล่า %{customdata[0]:,.0f} · รถว่าง %{customdata[1]:,.0f} เที่ยว<extra></extra>"),
                ))
            fig.add_trace(go.Scatter(
                name=P_LABEL, y=plot["_Dir"], x=plot[P], mode="markers+text",
                marker=dict(size=12, symbol="diamond", color=[C_POS if v >= 0 else C_NEG for v in plot[P]],
                            line=dict(color="white", width=1.5)),
                text=[f"  {fm(v)}" for v in plot[P]], textposition="middle right",
                textfont=dict(size=11, color=C_DARK),
                customdata=plot[["Trips", PP, "LF", "VLF"]].to_numpy(),
                hovertemplate=(f"%{{y}}<br>{P_LABEL} ฿%{{x:,.0f}} (%{{customdata[1]:.1%}})"
                               "<br>%{customdata[0]:,} เที่ยว · LF น้ำหนัก %{customdata[2]:.1%}"
                               " · LF ปริมาตร %{customdata[3]:.1%}<extra></extra>"),
            ))
            fig.update_layout(
                barmode="group", bargap=0.25, height=max(380, 50 * len(plot) + 120),
                margin=dict(l=15, r=40, t=10, b=20),
                legend=dict(orientation="h", y=1.04, x=0),
                xaxis=dict(title="บาท", tickformat=",.0f", zeroline=True, zerolinecolor="#CBD5E1"),
                yaxis=dict(title="", automargin=True, tickfont=dict(size=11)),
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    # ---------------- แนวโน้มรายเดือน ----------------
    with _card("do_trend"):
        st.markdown("#### แนวโน้มรายเดือน")
        trend_opts = ["ทุกทิศทางตามตัวกรอง"] + valid.sort_values("Revenue", ascending=False)["_Dir"].tolist()
        t1, t2 = st.columns([2.2, 1])
        with t1:
            trend_dir = st.selectbox("ทิศทาง", trend_opts, key=_wkey("do_trend_dir", trend_opts))
        with t2:
            st.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
            show_lf = st.checkbox("แสดงเส้น LF น้ำหนัก + ปริมาตร (แกนขวา)", value=True, key="do_trend_lf")
        src = filtered if trend_dir == trend_opts[0] else filtered[filtered["_Dir"] == trend_dir]
        src = src[src["_Date"].notna()]
        if src.empty:
            st.info("ไม่มีข้อมูลวันที่ตามตัวกรอง")
        else:
            src = src.assign(_P=src["_Date"].dt.to_period("M"))
            m = summarize(src, lf, "_P").sort_index()
            labels = [f"{THAI_MONTHS[p.month]} {str(p.year + 543)[-2:]}" for p in m.index]
            fig = go.Figure()
            fig.add_trace(go.Bar(name="รายได้", x=labels, y=m["Revenue"], marker_color=C_REV,
                                 hovertemplate="%{x}<br>รายได้ ฿%{y:,.0f}<extra></extra>"))
            fig.add_trace(go.Bar(name="ต้นทุน", x=labels, y=m["Cost"], marker_color=C_COST,
                                 hovertemplate="%{x}<br>ต้นทุน ฿%{y:,.0f}<extra></extra>"))
            if m["LossCost"].sum() > 0:
                fig.add_trace(go.Bar(name="ต้นทุนเที่ยวเปล่า + รถว่าง", x=labels, y=m["LossCost"],
                                     marker_color="#F6AE6B",
                                     hovertemplate="%{x}<br>เที่ยวเปล่า+รถว่าง ฿%{y:,.0f}<extra></extra>"))
            fig.add_trace(go.Scatter(
                name=P_LABEL, x=labels, y=m[P], mode="lines+markers",
                line=dict(color=C_DARK, width=3),
                marker=dict(size=8, color=[C_POS if v >= 0 else C_NEG for v in m[P]],
                            line=dict(color="white", width=1.5)),
                customdata=m[["Trips", PP]].to_numpy(),
                hovertemplate=(f"%{{x}}<br>{P_LABEL} ฿%{{y:,.0f}} (%{{customdata[1]:.1%}})"
                               "<br>%{customdata[0]:,} เที่ยว<extra></extra>"),
            ))
            layout = dict(
                barmode="group", height=420, margin=dict(l=15, r=15, t=20, b=20),
                legend=dict(orientation="h", y=-0.18, x=0),
                xaxis=dict(title="", type="category"),
                yaxis=dict(title="บาท", tickformat=",.0f"),
            )
            if show_lf and (m["LF"].notna().any() or m["VLF"].notna().any()):
                for lk, lname, lcol, dash in (("LF", "LF น้ำหนัก", C_LF, "dot"), ("VLF", "LF ปริมาตร", "#E08BC0", "dash")):
                    fig.add_trace(go.Scatter(
                        name=f"{lname} (แกนขวา)", x=labels, y=m[lk] * 100, yaxis="y2", mode="lines+markers",
                        line=dict(color=lcol, width=2.5, dash=dash), marker=dict(size=7, color=lcol),
                        hovertemplate=f"%{{x}}<br>{lname} %{{y:.1f}}%<extra></extra>",
                    ))
                layout["yaxis2"] = dict(title="Load Factor (%)", overlaying="y", side="right", ticksuffix="%",
                                        rangemode="tozero", showgrid=False)
            fig.update_layout(**layout)
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    # ---------------- ตารางทิศทาง (ขาขึ้น / ขาล่อง คู่กัน) ----------------
    with _card("do_table"):
        st.markdown("#### ตารางทิศทาง (ขาขึ้น / ขาล่อง ของเส้นทางเดียวกันอยู่คู่กัน)")
        s1, s2 = st.columns([3, 1])
        table_routes = valid.sort_values("Revenue", ascending=False)["_Dir"].tolist()
        with s1:
            pick_routes = st.multiselect("เลือกทิศทาง (ไม่เลือก = แสดงทั้งหมด)", table_routes,
                                         placeholder="พิมพ์ชื่อสถานที่เพื่อค้นหา", key=_wkey("do_table_routes", table_routes))
        tsort = {"รายได้": ("Revenue", False), f"{P_LABEL} (น้อย → มาก)": (P, True),
                 f"{P_LABEL} (มาก → น้อย)": (P, False), "เที่ยวเปล่า + รถว่าง": ("LossCost", False),
                 "จำนวนเที่ยว": ("Trips", False), "ชื่อ": ("Name", True)}
        with s2:
            tsort_label = st.selectbox("เรียงคู่ตาม", list(tsort), key=_wkey("do_table_sort", list(tsort)))
        sort_by, asc = tsort[tsort_label]

        shown = valid if not pick_routes else valid[valid["_Dir"].isin(pick_routes)]
        grp_rows = valid[valid["_PairKey"].isin(shown["_PairKey"].unique())]
        pair_agg = grp_rows.groupby("_PairKey").agg(
            Revenue=("Revenue", "sum"), Profit=("Profit", "sum"), CM=("CM", "sum"),
            LossCost=("LossCost", "sum"), Trips=("Trips", "sum"), Name=("_Dir", "min"))
        pair_order = pair_agg.sort_values(sort_by, ascending=asc).index.tolist()
        MAX_PAIRS = 300
        cut = len(pair_order) > MAX_PAIRS
        pair_order = pair_order[:MAX_PAIRS]
        run_rank = {"ขาขึ้น": 0, "ขาล่อง": 1}

        head = ["#", "ทิศทาง", "เที่ยว", "รายได้", "ต้นทุน", P_LABEL, f"อัตรา{P_LABEL}",
                "LF น้ำหนัก", "LF ปริมาตร", "เที่ยวเปล่า / รถว่าง", "ต้นทุน/ตัน-กม."]
        body, export_rows = [], []
        for rank, pk in enumerate(pair_order, 1):
            members = grp_rows[grp_rows["_PairKey"] == pk].copy()
            members["_o"] = members["Run"].map(run_rank).fillna(2)
            members = members.sort_values(["_o", "Revenue"], ascending=[True, False]).to_dict("records")
            a, b = str(members[0]["_DirKey"]).split("|", 1)
            if len(members) == 1 and a != b:
                other = {"ขาขึ้น": "ขาล่อง", "ขาล่อง": "ขาขึ้น"}.get(members[0]["Run"], "")
                members.append({"_missing": True, "Run": other, "_Dir": f"{b or 'ไม่ระบุ'} → {a or 'ไม่ระบุ'}"})
            for i, r in enumerate(members):
                tr_cls = ' class="do-grp"' if i == 0 else ""
                rank_cell = f'<td class="tc-rank">{rank if i == 0 else ""}</td>'
                dot = route_colors.get(r["_Dir"], GRAY)
                dir_cell = (f'<td>{_run_tag(r["Run"])}'
                            f'<span class="tc-dot" style="background:{dot}"></span><b>{_arrow_html(r["_Dir"])}</b></td>')
                if r.get("_missing"):
                    body.append(f'<tr{tr_cls}>{rank_cell}{dir_cell}<td colspan="{len(head) - 2}" '
                                f'class="tc-muted do-missing">ไม่มีเที่ยวทิศนี้ตามตัวกรอง</td></tr>')
                    continue
                if r["LossTrips"] > 0:
                    loss_cell = (f'<td class="tc-num">เปล่า {int(r["EmptyTrips"]):,} · รถว่าง {int(r["BranchTrips"]):,}'
                                 f'<br><small class="do-neg">{ff(r["LossCost"])}</small></td>')
                else:
                    loss_cell = '<td class="tc-num tc-muted">—</td>'
                cells = [
                    rank_cell, dir_cell,
                    f'<td class="tc-num">{int(r["Trips"]):,}</td>',
                    f'<td class="tc-num">{ff(r["Revenue"])}</td>',
                    f'<td class="tc-num">{ff(r["Cost"])}</td>',
                    f'<td class="tc-num {sign_cls(r[P])}">{ff(r[P])}</td>',
                    f'<td class="tc-num {sign_cls(r[PP])}">{fp(r[PP])}</td>',
                    f'<td class="tc-num">{fp(r["LF"])}</td>',
                    f'<td class="tc-num">{fp(r["VLF"])}</td>',
                    loss_cell,
                    f'<td class="tc-num tc-muted">{fck(r["CostTonKm"])}</td>',
                ]
                body.append(f"<tr{tr_cls}>" + "".join(cells) + "</tr>")
                export_rows.append({
                    "ลำดับคู่": rank, "เที่ยววิ่ง": r["Run"], "ทิศทาง": r["_Dir"], "จำนวนเที่ยว": int(r["Trips"]),
                    "รายได้": r["Revenue"], "ต้นทุน": r["Cost"], "กำไรสุทธิ": r["Profit"], "CM": r["CM"],
                    "อัตรากำไรสุทธิ": r["Margin"], "อัตรา CM": r["CMPct"],
                    "กำไรสุทธิต่อเที่ยว": r["ProfitPerTrip"],
                    "Load Factor น้ำหนัก": r["LF"], "Load Factor ปริมาตร": r["VLF"],
                    "เที่ยวเปล่า (เที่ยว)": int(r["EmptyTrips"]), "ต้นทุนเที่ยวเปล่า": r["EmptyCost"],
                    "รถว่างไปสาขา (เที่ยว)": int(r["BranchTrips"]), "ต้นทุนรถว่างไปสาขา": r["BranchCost"],
                    "Ton-km": r["TonKm"], "ต้นทุนต่อตัน-กม.": r["CostTonKm"],
                    "ต้นทุนค่าเดินทาง": r["TravelCost"], "ต้นทุนค่าซ่อม": r["RepairCost"], "ค่าเสื่อม": r["Depr"],
                })
        st.caption(
            f"แสดง {len(pair_order):,} คู่สถานที่" + (f" (แสดงสูงสุด {MAX_PAIRS} คู่)" if cut else "")
            + " · ป้าย ขาขึ้น/ขาล่อง มาจากคอลัมน์ เที่ยววิ่ง ในไฟล์ (ค่าที่พบบ่อยที่สุดของทิศทางนั้น)"
            + " · LF น้ำหนัก = น้ำหนักรวม ÷ ความจุน้ำหนักรวม · LF ปริมาตร = ปริมาตรรวม ÷ ความจุปริมาตรรวม"
              " (ไม่นับเที่ยวที่ LF ปริมาตรเกิน 150%) · ต้นทุน/ตัน-กม. คิดเฉพาะเที่ยวที่มีข้อมูลน้ำหนัก"
        )
        st.markdown(_table_html(head, body, right_cols=set(range(2, len(head))), max_height=540),
                    unsafe_allow_html=True)
        st.download_button(
            "⬇️ ดาวน์โหลดตารางทิศทาง (CSV)",
            pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8-sig"),
            file_name="direction_overview.csv", mime="text/csv", key="do_table_download",
        )

    # ---------------- เจาะรายทิศทาง ----------------
    with _card("do_detail"):
        st.markdown("#### เจาะรายทิศทาง")
        opts = valid.sort_values("Revenue", ascending=False)["_Dir"].tolist()
        if not opts:
            st.info("ไม่มีทิศทางตามตัวกรอง")
        else:
            pick = st.selectbox("เลือกทิศทาง", opts, key=_wkey("do_detail_dir", opts))
            row = valid[valid["_Dir"] == pick].iloc[0]
            rev_sum = summarize(base[base["_DirKey"] == row["_RevKey"]], lf, "_DirKey") \
                if row["_RevKey"] != row["_DirKey"] else pd.DataFrame()
            boxes = [
                ("จำนวนเที่ยว", f'{int(row["Trips"]):,}',
                 f'{row["Run"] or "ไม่ระบุขา"} · มีข้อมูล LF {int(row["LFTrips"]):,} เที่ยว'),
                ("รายได้", fm(row["Revenue"]), f'เฉลี่ย {ff(row["RevPerTrip"])} ต่อเที่ยว'),
                ("ต้นทุนรวม", fm(row["Cost"]),
                 f'เดินทาง {fm(row["TravelCost"])} · ซ่อม {fm(row["RepairCost"])} · ค่าเสื่อม {fm(row["Depr"])}'),
                ("กำไรสุทธิ", fm(row["Profit"]), f'อัตรากำไร {fp(row["Margin"])}'),
                ("CM", fm(row["CM"]), f'{fp(row["CMPct"])} ของรายได้'),
                ("LF น้ำหนัก", fp(row["LF"]), "น้ำหนักรวม ÷ ความจุน้ำหนัก"),
                ("LF ปริมาตร", fp(row["VLF"]), "ปริมาตรรวม ÷ ความจุปริมาตร"),
                ("ต้นทุนต่อตัน-กม.", fck(row["CostTonKm"]), f'{row["TonKm"]:,.0f} ตัน-กม.'),
                ("เที่ยวเปล่า + รถว่างไปสาขา", f'{int(row["LossTrips"]):,} เที่ยว',
                 f'เปล่า {int(row["EmptyTrips"]):,} · รถว่าง {int(row["BranchTrips"]):,} · ต้นทุน {fm(row["LossCost"])}'),
            ]
            if not rev_sum.empty:
                rr = rev_sum.iloc[0]
                boxes.append(("ทิศกลับ", fm(rr[P]),
                              f'{P_LABEL} · {int(rr["Trips"]):,} เที่ยว · LF น้ำหนัก {fp(rr["LF"])} · ปริมาตร {fp(rr["VLF"])}'))
            else:
                boxes.append(("ทิศกลับ", "—", "ไม่มีเที่ยวทิศกลับตามตัวกรอง"))
            st.markdown(
                '<div class="do-box-grid">' + "".join(
                    f'<div class="do-box"><div class="k">{esc(k)}</div><div class="v" title="{esc(v)}">{esc(v)}</div>'
                    f'<div class="s">{esc(s)}</div></div>' for k, v, s in boxes
                ) + "</div>",
                unsafe_allow_html=True,
            )

            d = filtered[filtered["_Dir"] == pick]
            trips = d.groupby("_Trip").agg(
                Date=("_Date", "min"), Plate=("_Plate", "first"), Vehicle=("_Vehicle", "first"),
                Run=("_Run", "first"), TType=("_TType", "first"),
                Manifests=("_Manifest", "nunique"), Revenue=("_Rev", "sum"), Cost=("_Cost", "sum"),
                Profit=("_Profit", "sum"), CM=("_CM", "sum"), TripKey=("_TripKey", "first"),
            )
            if not lf.empty:
                trips = trips.join(lf[["weight", "cap", "volume", "vcap"]], on="TripKey")
                trips["LF"] = trips["weight"] / trips["cap"]
                trips["VLF"] = trips["volume"] / trips["vcap"]
            else:
                trips["weight"], trips["LF"], trips["volume"], trips["VLF"] = (float("nan"),) * 4
            trips = trips.sort_values(P)

            with st.expander(f"ดูรายเที่ยวของ {pick} ({len(trips):,} เที่ยว)"):
                head = ["วันที่", "ทะเบียนรถ", "ประเภทรถ", "ประเภทเที่ยว", "ใบงาน", "น้ำหนัก (กก.)", "LF น้ำหนัก",
                        "ปริมาตร (ม³)", "LF ปริมาตร", "รายได้", "ต้นทุน", P_LABEL]
                body = []
                for r in trips.head(300).to_dict("records"):
                    date_txt = r["Date"].strftime("%d/%m/%Y") if pd.notna(r["Date"]) else "—"
                    w = "—" if _nz(r["weight"]) is None else f'{r["weight"]:,.0f}'
                    vol = "—" if _nz(r["volume"]) is None else f'{r["volume"]:,.2f}'
                    body.append(
                        "<tr>"
                        f'<td class="tc-muted">{date_txt}</td>'
                        f'<td>{esc(str(r["Plate"] or "—"))}</td>'
                        f'<td class="tc-muted">{esc(str(r["Vehicle"] or "—"))}</td>'
                        f'<td>{_tt_badge(r["TType"])}</td>'
                        f'<td class="tc-num">{int(r["Manifests"]):,}</td>'
                        f'<td class="tc-num tc-muted">{w}</td>'
                        f'<td class="tc-num">{fp(r["LF"])}</td>'
                        f'<td class="tc-num tc-muted">{vol}</td>'
                        f'<td class="tc-num">{fp(r["VLF"])}</td>'
                        f'<td class="tc-num">{ff(r["Revenue"])}</td>'
                        f'<td class="tc-num">{ff(r["Cost"])}</td>'
                        f'<td class="tc-num {sign_cls(r[P])}"><b>{ff(r[P])}</b></td>'
                        "</tr>"
                    )
                st.caption(f"เรียงจาก{P_LABEL}น้อยไปมาก (ขาดทุนขึ้นก่อน) · แสดงสูงสุด 300 เที่ยว · "
                           "1 เที่ยวอาจมีหลายใบงาน รายได้และต้นทุนรวมทุกใบงานในเที่ยวนั้น")
                st.markdown(_table_html(head, body, right_cols=set(range(4, len(head))), max_height=420),
                            unsafe_allow_html=True)
                export = trips.reset_index().rename(columns={
                    "_Trip": "เที่ยว", "Date": "วันที่", "Plate": "ทะเบียนรถ", "Vehicle": "ประเภทรถ",
                    "Run": "เที่ยววิ่ง", "TType": "ประเภทเที่ยว",
                    "Manifests": "จำนวนใบงาน", "Revenue": "รายได้", "Cost": "ต้นทุน", "Profit": "กำไรสุทธิ",
                    "weight": "น้ำหนัก (กก.)", "LF": "LF น้ำหนัก", "volume": "ปริมาตร (ม³)", "VLF": "LF ปริมาตร",
                })
                export = export[[c for c in ["เที่ยว", "วันที่", "ทะเบียนรถ", "ประเภทรถ", "เที่ยววิ่ง", "ประเภทเที่ยว",
                                             "จำนวนใบงาน", "น้ำหนัก (กก.)", "LF น้ำหนัก", "ปริมาตร (ม³)",
                                             "LF ปริมาตร", "รายได้", "ต้นทุน",
                                             "กำไรสุทธิ", "CM"]
                                 if c in export.columns]]
                st.download_button(
                    f"⬇️ ดาวน์โหลด {len(trips):,} เที่ยว (CSV)", export.to_csv(index=False).encode("utf-8-sig"),
                    file_name="direction_trips.csv", mime="text/csv", key="do_detail_download",
                )

    cover = _div(data["_HasLF"].sum(), len(data))
    tt_counts = data["_TType"].value_counts()
    tt_note = " · ".join(f"{t} {int(tt_counts.get(t, 0)):,}" for t in TRIP_TYPES if tt_counts.get(t, 0))
    st.markdown(
        f'<div class="tc-source">ข้อมูลจาก {esc(info["file"])} ({esc(info["sheets"])}) · '
        f'{info["rows"]:,} ใบงาน ({esc(tt_note)}) · จับคู่ Load Factor ได้ {fp(cover)} ของใบงาน</div>',
        unsafe_allow_html=True,
    )