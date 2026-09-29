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
- เกณฑ์ Load Factor (รายเที่ยว):
    ผ่านเกณฑ์      = LF น้ำหนัก ≥ 75% หรือ LF ปริมาตร ≥ 75% อย่างใดอย่างหนึ่ง
    กลุ่มที่ต้องสนใจ = ต่ำกว่า 75% ทั้งน้ำหนักและปริมาตร
    (ค่าที่เกิน 100% ถือเป็นข้อมูลที่ต้องตรวจสอบ ไม่นำมาตัดสิน)
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

# เกณฑ์ Load Factor: น้ำหนัก "หรือ" ปริมาตร ≥ 75% = ผ่าน · ต่ำกว่า 75% ทั้งคู่ = ต้องสนใจ
PASS_LF = 0.75
LF_BEST = "เกณฑ์รวม"
LF_BASES = {LF_BEST: "BLF", "น้ำหนัก": "LF", "ปริมาตร": "VLF"}

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
.do-kpi-grid .tc-kpi-sub.do-sub-wrap { white-space:normal; overflow:visible; line-height:1.45; }
.do-sub-wrap b { color:#3E9E6A; }
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
/* เกณฑ์ Load Factor 75% */
.do-crit-card { background:#fff; border:1px solid #F4D8DE; border-radius:18px; padding:16px 18px; margin:0 0 12px;
                box-shadow:0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(226,90,112,.08); }
.do-crit-title { font-size:17px; font-weight:700; color:#0F172A; }
.do-crit-note { font-size:12.5px; color:#64748B; margin:2px 0 10px; }
.do-crit-grid { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:12px; }
.do-crit { border-radius:16px; padding:14px 16px; border:1px solid; min-width:0; }
.do-crit.ok { background:#F1FAF4; border-color:#BFE5CD; }
.do-crit.attn { background:#FFF8EC; border-color:#F6D9A6; }
.do-crit-head { font-size:14px; font-weight:700; color:#0F172A; }
.do-crit-head small { display:block; font-size:12px; font-weight:500; color:#64748B; margin-top:2px; }
.do-crit-num { font-size:28px; font-weight:800; margin-top:6px; font-variant-numeric:tabular-nums; }
.do-crit.ok .do-crit-num { color:#3E9E6A; }
.do-crit.attn .do-crit-num { color:#D97706; }
.do-crit-num span { font-size:13px; font-weight:600; color:#64748B; }
.do-crit-chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.do-crit-chip { background:#fff; border:1px solid #F1E4E7; border-radius:99px; padding:3px 10px; font-size:12px; color:#64748B; }
.do-crit-chip b { color:#1E293B; font-variant-numeric:tabular-nums; }
.do-st-ok { color:#2E8B57; font-weight:700; white-space:nowrap; }
.do-st-attn { color:#B45309; font-weight:700; white-space:nowrap; }
@media (max-width:900px){ .do-crit-grid { grid-template-columns:1fr; } }
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


def _crit_status(blf) -> str:
    """สถานะเกณฑ์ LF ของเที่ยว (blf = ค่าที่ดีกว่าระหว่างน้ำหนัก/ปริมาตร ที่ไม่เกิน 100%)"""
    v = _nz(blf)
    if v is None:
        return "—"
    return "✅ ผ่าน" if v >= PASS_LF else "⚠️ ต้องสนใจ"


def _crit_html(blf) -> str:
    s = _crit_status(blf)
    if s == "—":
        return '<span class="tc-muted">—</span>'
    return f'<span class="{"do-st-ok" if s.startswith("✅") else "do-st-attn"}">{s}</span>'


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
    lf = pd.DataFrame(columns=["key", "weight", "cap", "volume", "vcap", "tonkm",
                               "blf", "eval", "pass", "passby"])
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

            # เกณฑ์ LF รายเที่ยว: ใช้ค่าที่ดีกว่าระหว่างน้ำหนักกับปริมาตร (เฉพาะค่าที่ไม่เกิน 100%)
            w = (lf["weight"] / lf["cap"]).replace([float("inf")], float("nan"))
            v = (lf["volume"] / lf["vcap"]).replace([float("inf")], float("nan"))
            w_ok, v_ok = w.where(w <= 1.0), v.where(v <= 1.0)
            lf["blf"] = pd.concat([w_ok, v_ok], axis=1).max(axis=1)
            lf["eval"] = lf["blf"].notna().astype("float64")
            lf["pass"] = lf["blf"].ge(PASS_LF).astype("float64")
            pw, pv = w_ok.ge(PASS_LF), v_ok.ge(PASS_LF)
            lf["passby"] = ""
            lf.loc[pw & ~pv, "passby"] = "น้ำหนัก"
            lf.loc[~pw & pv, "passby"] = "ปริมาตร"
            lf.loc[pw & pv, "passby"] = "ทั้งคู่"
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
            PassTrips=("pass", "sum"), EvalTrips=("eval", "sum"),
        )
        s = s.join(a)
    for col in ("LFTrips", "W", "Cap", "V", "VCap", "TonKm", "CostLF",
                "EmptyTrips", "EmptyCost", "BranchTrips", "BranchCost", "PassTrips", "EvalTrips"):
        if col not in s:
            s[col] = 0.0
        s[col] = s[col].fillna(0)
    nan = float("nan")
    s["LossTrips"] = s["EmptyTrips"] + s["BranchTrips"]
    s["LossCost"] = s["EmptyCost"] + s["BranchCost"]
    s["LF"] = s["W"] / s["Cap"].where(s["Cap"] > 0, nan)
    s["VLF"] = s["V"] / s["VCap"].where(s["VCap"] > 0, nan)
    # เกณฑ์รวม: ค่าที่ดีกว่าระหว่าง LF น้ำหนักกับ LF ปริมาตร (ใช้ค่าที่ไม่เกิน 100% ก่อน)
    best_ok = pd.concat([s["LF"].where(s["LF"] <= 1.0), s["VLF"].where(s["VLF"] <= 1.0)], axis=1).max(axis=1)
    s["BLF"] = best_ok.fillna(pd.concat([s["LF"], s["VLF"]], axis=1).max(axis=1))
    s["AttnTrips"] = s["EvalTrips"] - s["PassTrips"]
    s["PassRate"] = s["PassTrips"] / s["EvalTrips"].where(s["EvalTrips"] > 0, nan)
    s["Margin"] = s["Profit"] / s["Revenue"].where(s["Revenue"] != 0, nan)
    s["CMPct"] = s["CM"] / s["Revenue"].where(s["Revenue"] != 0, nan)
    s["CostTonKm"] = s["CostLF"] / s["TonKm"].where(s["TonKm"] > 0, nan)
    s["RevPerTrip"] = s["Revenue"] / s["Trips"].where(s["Trips"] > 0, nan)
    s["ProfitPerTrip"] = s["Profit"] / s["Trips"].where(s["Trips"] > 0, nan)
    return s


def totals(df, lf):
    s = summarize(df.assign(_All="all"), lf, "_All")
    return s.iloc[0] if not s.empty else None


def _pass_cell(r) -> str:
    """เซลล์ % เที่ยวผ่านเกณฑ์ LF พร้อมจำนวนเที่ยวที่ต้องสนใจ"""
    rate = _nz(r["PassRate"])
    if rate is None:
        return '<td class="tc-num tc-muted">—</td>'
    cls = "do-pos" if rate >= 0.5 else "do-neg"
    return (f'<td class="tc-num"><span class="{cls}">{fp(rate)}</span>'
            f'<br><small class="tc-muted">ต้องสนใจ {int(r["AttnTrips"]):,}</small></td>')


# =========================================================
# DASHBOARD
# =========================================================

def _render_direction_main():
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
            data, lf, info = load_direction_data(str(path), (path.name, stat.st_mtime_ns, stat.st_size, "v3"))
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

    g1, g2, g3, g4, g5 = fcard.columns([2.2, 1, 1, 1.05, 1.3])
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
        lf_basis = st.radio("Load Factor ใช้วัด", list(LF_BASES), horizontal=True, key="do_lf_basis2",
                            help="เกณฑ์รวม = ใช้ค่าที่สูงกว่าระหว่าง LF น้ำหนักกับ LF ปริมาตร "
                                 "(ผ่านเมื่ออย่างใดอย่างหนึ่ง ≥75%) · ใช้กับกราฟจัดกลุ่ม อันดับ และข้อสังเกต · "
                                 "ตารางแสดงทั้งสองค่าเสมอ")
    base = filtered  # ก่อนกรองทิศทาง ใช้หาขากลับ
    if chosen_dirs:
        filtered = filtered[filtered["_Dir"].isin(chosen_dirs)]
    if filtered.empty:
        st.info("ไม่มีข้อมูลตามตัวกรองที่เลือก")
        return

    P = "Profit" if basis == "กำไรสุทธิ" else "CM"
    PP = "Margin" if P == "Profit" else "CMPct"
    P_LABEL = basis
    LFK = LF_BASES[lf_basis]
    LF_LABEL = "LF เกณฑ์รวม" if LFK == "BLF" else f"LF {lf_basis}"

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
    on_w = "on" if LFK in ("LF", "BLF") else ""
    on_v = "on" if LFK in ("VLF", "BLF") else ""
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
         f'<span class="{on_w}">น้ำหนัก<b>{fp(tot["LF"])}</b></span>'
         f'<span class="{on_v}">ปริมาตร<b>{fp(tot["VLF"])}</b></span></div>'
         f'<div class="tc-kpi-sub do-sub-wrap">ผ่านเกณฑ์ 75%: <b>{fp(tot["PassRate"])}</b> ของเที่ยว'
         f'<br>มีข้อมูล LF {fp(lf_cover)} ของเที่ยว</div>'
         f'</div></div>'),
        kpi("🛣️", "#FFF7E0", "ต้นทุนต่อตัน-กม.", fck(tot["CostTonKm"]), f'{tot["TonKm"]:,.0f} ตัน-กม.'),
        kpi("🅾️", "#FDE9EC", "เที่ยวเปล่า + รถว่างไปสาขา", fm(tot["LossCost"]),
            f'เปล่า {int(tot["EmptyTrips"]):,} · รถว่าง {int(tot["BranchTrips"]):,} เที่ยว',
            "do-neg" if tot["LossCost"] > 0 else ""),
    ]
    st.markdown('<div class="do-kpi-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)

    # ---------------- เกณฑ์ Load Factor 75% (รายเที่ยว) ----------------
    trip_keys = filtered.loc[filtered["_HasLF"], "_TripKey"].dropna().unique()
    ct = lf.loc[lf.index.intersection(trip_keys)] if not lf.empty else lf
    ev = ct[ct["eval"] > 0] if not ct.empty else ct
    if not ev.empty:
        n_eval = len(ev)
        ok = ev[ev["blf"] >= PASS_LF]
        attn = ev[ev["blf"] < PASS_LF]
        by_pass = ok["passby"].value_counts().to_dict()
        rng = pd.cut(attn["blf"], [-0.001, 0.25, 0.50, PASS_LF], right=False,
                     labels=["0–25%", "25–50%", "50–75%"]).value_counts().to_dict()

        def pct(n):
            return f"{n / n_eval * 100:.1f}%" if n_eval else "—"

        def chips(items):
            return "".join(f'<span class="do-crit-chip">{esc(k)} <b>{int(v):,}</b></span>' for k, v in items)

        st.markdown(
            '<div class="do-crit-card"><div class="do-crit-title">เกณฑ์ Load Factor 75%</div>'
            '<div class="do-crit-note">ผ่านเกณฑ์ = น้ำหนัก <b>หรือ</b> ปริมาตร ≥75% อย่างใดอย่างหนึ่ง · '
            'ต้องสนใจ = ต่ำกว่า 75% <b>ทั้ง</b>น้ำหนักและปริมาตร · '
            f'คิดจาก {n_eval:,} เที่ยวที่มีข้อมูล LF (ไม่นับค่าที่เกิน 100%)</div>'
            '<div class="do-crit-grid">'
            '<div class="do-crit ok"><div class="do-crit-head">✅ ผ่านเกณฑ์'
            '<small>ใช้ความจุรถคุ้มแล้ว</small></div>'
            f'<div class="do-crit-num">{len(ok):,} <span>เที่ยว · {pct(len(ok))}</span></div>'
            '<div class="do-crit-chips">'
            + chips([("ผ่านด้วยน้ำหนัก", by_pass.get("น้ำหนัก", 0)),
                     ("ผ่านด้วยปริมาตร", by_pass.get("ปริมาตร", 0)),
                     ("ผ่านทั้งคู่", by_pass.get("ทั้งคู่", 0))])
            + '</div></div>'
            '<div class="do-crit attn"><div class="do-crit-head">⚠️ กลุ่มที่ต้องสนใจ'
            '<small>แบ่งตามค่าที่สูงกว่าระหว่างน้ำหนักกับปริมาตร</small></div>'
            f'<div class="do-crit-num">{len(attn):,} <span>เที่ยว · {pct(len(attn))}</span></div>'
            '<div class="do-crit-chips">'
            + chips([(k, rng.get(k, 0)) for k in ("0–25%", "25–50%", "50–75%")])
            + '</div></div></div></div>',
            unsafe_allow_html=True,
        )

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
        attn_rel = rel[rel["AttnTrips"] > 0]
        if not attn_rel.empty:
            top_attn = attn_rel.loc[attn_rel["AttnTrips"].idxmax()]
            cells.append(("#D97706", "⚠️", "เที่ยวต้องสนใจ (LF <75% ทั้งคู่) มากสุด",
                          f'{int(top_attn["AttnTrips"]):,} เที่ยว', top_attn["_Dir"],
                          f'ผ่านเกณฑ์ {fp(top_attn["PassRate"])} · LF น้ำหนัก {fp(top_attn["LF"])} · ปริมาตร {fp(top_attn["VLF"])}'))
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
        st.markdown(f"#### จัดกลุ่มทิศทาง: บรรทุกผ่านเกณฑ์หรือไม่ ({LF_LABEL}) × {P_LABEL}ดีแค่ไหน")
        q1, q2, _q3 = st.columns([1, 1, 2])
        target_opts = [40, 50, 60, 70, 75, 80]
        with q1:
            lf_target = st.selectbox(f"เกณฑ์ “บรรทุกผ่าน” เมื่อ {LF_LABEL} ถึง", target_opts,
                                     index=target_opts.index(int(PASS_LF * 100)),
                                     format_func=lambda v: f"{v}%", key="do_lf_target3")
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
                ("fix", f"🚨 LF ต่ำกว่า {t}% + ขาดทุน", "ต้องสนใจก่อน: รวมเที่ยว/ลดรอบวิ่ง", C_NEG,
                 (q["x_real"] < t) & (q[P] < 0)),
                ("price", f"💲 LF ผ่าน {t}% แต่ขาดทุน", "ดูราคาค่าขนส่ง/ต้นทุน", "#F6AE6B",
                 (q["x_real"] >= t) & (q[P] < 0)),
                ("room", f"📦 มีกำไร แต่ LF ต่ำกว่า {t}%", "ต้องสนใจ: หาของเพิ่ม/ใช้รถเล็กลง", C_REV,
                 (q["x_real"] < t) & (q[P] >= 0)),
                ("good", f"✅ LF ผ่าน {t}% + มีกำไร", "รักษาไว้", C_POS,
                 (q["x_real"] >= t) & (q[P] >= 0)),
            ]
            q["grp"] = ""
            for key, _n, _a, _c, m in groups:
                q.loc[m, "grp"] = key

            lf_how = ("ใช้ค่าที่สูงกว่าระหว่าง LF น้ำหนักกับ LF ปริมาตร — ผ่านเมื่ออย่างใดอย่างหนึ่งถึงเกณฑ์"
                      if LFK == "BLF" else f"วัดด้วย{LF_LABEL}")
            st.markdown(
                '<div class="do-how">📖 <b>วิธีอ่าน:</b> แต่ละวงกลม = 1 ทิศทาง · '
                f'<b>ยิ่งไปทางขวา</b> = บรรทุกเต็มกว่า ({lf_how}; เส้นประแนวตั้ง = {t}%) · '
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
                        _w=q["LF"] * 100, _v=q["VLF"] * 100, _p=q["PassRate"] * 100).to_numpy(),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>%{customdata[1]:,} เที่ยว"
                        "<br>รายได้ ฿%{customdata[2]:,.0f} · ต้นทุน ฿%{customdata[3]:,.0f}"
                        f"<br>{P_LABEL} ฿%{{customdata[4]:,.0f}} (%{{customdata[5]:.1f}}%)"
                        "<br>LF น้ำหนัก %{customdata[7]:.1f}% · LF ปริมาตร %{customdata[8]:.1f}%"
                        "<br>เที่ยวผ่านเกณฑ์ 75% %{customdata[9]:.1f}%"
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
                            + _pass_cell(r) +
                            f'<td class="tc-num tc-muted">{int(r["LossTrips"]):,}</td>'
                            "</tr>"
                        )
                    st.caption(f"{len(part):,} ทิศทาง · เรียงตามจำนวนเที่ยว · แสดงสูงสุด 100 ทิศทาง")
                    st.markdown(_table_html(
                        ["#", "ทิศทาง", "เที่ยว", "รายได้", P_LABEL, f"อัตรา{P_LABEL}", "LF น้ำหนัก",
                         "LF ปริมาตร", "เที่ยวผ่านเกณฑ์ 75%", "เที่ยวเปล่า/รถว่าง"],
                        body, right_cols={2, 3, 4, 5, 6, 7, 8, 9}, max_height=380), unsafe_allow_html=True)

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
            "เที่ยวต้องสนใจ (LF <75% ทั้งคู่) มากที่สุด": ("AttnTrips", False),
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
        if col == "AttnTrips":
            pool = pool[pool["AttnTrips"] > 0]
        if col in ("LF", "VLF", "BLF"):
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
                customdata=plot[["Trips", PP, "LF", "VLF", "PassRate"]].to_numpy(),
                hovertemplate=(f"%{{y}}<br>{P_LABEL} ฿%{{x:,.0f}} (%{{customdata[1]:.1%}})"
                               "<br>%{customdata[0]:,} เที่ยว · LF น้ำหนัก %{customdata[2]:.1%}"
                               " · LF ปริมาตร %{customdata[3]:.1%}"
                               "<br>เที่ยวผ่านเกณฑ์ 75% %{customdata[4]:.1%}<extra></extra>"),
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
                 "เที่ยวต้องสนใจ (LF <75%)": ("AttnTrips", False),
                 "จำนวนเที่ยว": ("Trips", False), "ชื่อ": ("Name", True)}
        with s2:
            tsort_label = st.selectbox("เรียงคู่ตาม", list(tsort), key=_wkey("do_table_sort", list(tsort)))
        sort_by, asc = tsort[tsort_label]

        shown = valid if not pick_routes else valid[valid["_Dir"].isin(pick_routes)]
        grp_rows = valid[valid["_PairKey"].isin(shown["_PairKey"].unique())]
        pair_agg = grp_rows.groupby("_PairKey").agg(
            Revenue=("Revenue", "sum"), Profit=("Profit", "sum"), CM=("CM", "sum"),
            LossCost=("LossCost", "sum"), AttnTrips=("AttnTrips", "sum"),
            Trips=("Trips", "sum"), Name=("_Dir", "min"))
        pair_order = pair_agg.sort_values(sort_by, ascending=asc).index.tolist()
        MAX_PAIRS = 300
        cut = len(pair_order) > MAX_PAIRS
        pair_order = pair_order[:MAX_PAIRS]
        run_rank = {"ขาขึ้น": 0, "ขาล่อง": 1}

        head = ["#", "ทิศทาง", "เที่ยว", "รายได้", "ต้นทุน", P_LABEL, f"อัตรา{P_LABEL}",
                "LF น้ำหนัก", "LF ปริมาตร", "เที่ยวผ่านเกณฑ์ 75%", "เที่ยวเปล่า / รถว่าง", "ต้นทุน/ตัน-กม."]
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
                    _pass_cell(r),
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
                    "เที่ยวผ่านเกณฑ์ LF 75%": int(r["PassTrips"]),
                    "เที่ยวต้องสนใจ (LF <75% ทั้งคู่)": int(r["AttnTrips"]),
                    "% เที่ยวผ่านเกณฑ์": r["PassRate"],
                    "เที่ยวเปล่า (เที่ยว)": int(r["EmptyTrips"]), "ต้นทุนเที่ยวเปล่า": r["EmptyCost"],
                    "รถว่างไปสาขา (เที่ยว)": int(r["BranchTrips"]), "ต้นทุนรถว่างไปสาขา": r["BranchCost"],
                    "Ton-km": r["TonKm"], "ต้นทุนต่อตัน-กม.": r["CostTonKm"],
                    "ต้นทุนค่าเดินทาง": r["TravelCost"], "ต้นทุนค่าซ่อม": r["RepairCost"], "ค่าเสื่อม": r["Depr"],
                })
        st.caption(
            f"แสดง {len(pair_order):,} คู่สถานที่" + (f" (แสดงสูงสุด {MAX_PAIRS} คู่)" if cut else "")
            + " · ป้าย ขาขึ้น/ขาล่อง มาจากคอลัมน์ เที่ยววิ่ง ในไฟล์ (ค่าที่พบบ่อยที่สุดของทิศทางนั้น)"
            + " · LF น้ำหนัก = น้ำหนักรวม ÷ ความจุน้ำหนักรวม · LF ปริมาตร = ปริมาตรรวม ÷ ความจุปริมาตรรวม"
              " (ไม่นับเที่ยวที่ LF ปริมาตรเกิน 150%)"
            + " · เที่ยวผ่านเกณฑ์ 75% = % ของเที่ยวที่น้ำหนักหรือปริมาตร ≥75% · ต้องสนใจ = ต่ำกว่า 75% ทั้งคู่"
            + " · ต้นทุน/ตัน-กม. คิดเฉพาะเที่ยวที่มีข้อมูลน้ำหนัก"
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
                ("เที่ยวผ่านเกณฑ์ LF 75%", fp(row["PassRate"]),
                 f'{int(row["PassTrips"]):,} จาก {int(row["EvalTrips"]):,} เที่ยว · ต้องสนใจ {int(row["AttnTrips"]):,}'),
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
                trips = trips.join(lf[["weight", "cap", "volume", "vcap", "blf"]], on="TripKey")
                trips["LF"] = trips["weight"] / trips["cap"]
                trips["VLF"] = trips["volume"] / trips["vcap"]
            else:
                trips["weight"], trips["LF"], trips["volume"], trips["VLF"], trips["blf"] = (float("nan"),) * 5
            trips["เกณฑ์ LF 75%"] = trips["blf"].map(_crit_status)
            trips = trips.sort_values(P)

            with st.expander(f"ดูรายเที่ยวของ {pick} ({len(trips):,} เที่ยว)"):
                head = ["วันที่", "ทะเบียนรถ", "ประเภทรถ", "ประเภทเที่ยว", "ใบงาน", "น้ำหนัก (กก.)", "LF น้ำหนัก",
                        "ปริมาตร (ม³)", "LF ปริมาตร", "เกณฑ์ LF 75%", "รายได้", "ต้นทุน", P_LABEL]
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
                        f'<td class="tc-num">{_crit_html(r["blf"])}</td>'
                        f'<td class="tc-num">{ff(r["Revenue"])}</td>'
                        f'<td class="tc-num">{ff(r["Cost"])}</td>'
                        f'<td class="tc-num {sign_cls(r[P])}"><b>{ff(r[P])}</b></td>'
                        "</tr>"
                    )
                st.caption(f"เรียงจาก{P_LABEL}น้อยไปมาก (ขาดทุนขึ้นก่อน) · แสดงสูงสุด 300 เที่ยว · "
                           "1 เที่ยวอาจมีหลายใบงาน รายได้และต้นทุนรวมทุกใบงานในเที่ยวนั้น · "
                           "เกณฑ์ LF 75%: ผ่าน = น้ำหนักหรือปริมาตร ≥75% · ต้องสนใจ = ต่ำกว่า 75% ทั้งคู่")
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
                                             "LF ปริมาตร", "เกณฑ์ LF 75%", "รายได้", "ต้นทุน",
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



# =========================================================
# ภาพรวมลูกค้า: กำไร × พฤติกรรมการจ่ายหนี้ (ไฟล์ เชื่อมลูกหนี้ลูกค้า)
# =========================================================

CUST_KEYWORD = "เชื่อมลูกหนี้"
C_GOOD, C_OK, C_WARN, C_BAD = "#3E9E6A", "#7CC4D6", "#F2A541", "#D0505C"

CUST_COLS = {
    "name": ["ชื่อลูกหนี้", "ชื่อลูกค้า", "ลูกค้า", "ผู้รับ_encoded", "ผู้รับ", "รหัสลูกค้า"],
    "bills": ["จำนวนบิลทั้งหมด"],
    "late_bills": ["จำนวนบิลที่ช้า"],
    "sum_delay": ["รวมวันช้า"],
    "max_delay": ["วันช้าสูงสุด"],
    "late_rate": ["เปอร์เซนต์บิลที่ช้า", "เปอร์เซ็นต์บิลที่ช้า", "%บิลที่ช้า"],
    "aging": ["กลุ่มช่วงอายุลูกหนี้", "กลุ่มอายุลูกหนี้"],
    "cls": ["การแบ่งชั้นลูกหนี้TFRS9", "แบ่งชั้นลูกหนี้TFRS9", "การแบ่งชั้นลูกหนี้", "แบ่งชั้นลูกหนี้", "ชั้นลูกหนี้"],
    "risk": ["ความเสี่ยง"],
    "b0": ["ยอดไม่ค้าง0วัน", "ยอดไม่ค้าง"],
    "b1": ["ยอดค้าง130วัน"],
    "b2": ["ยอดค้าง3160วัน"],
    "b3": ["ยอดค้าง6190วัน"],
    "b4": ["ยอดค้างเกิน90วัน"],
    "billed": ["รวมยอดทั้งหมด"],
    "wrisk": ["ความเสี่ยงถ่วงน้ำหนัก"],
    "revenue": ["รายได้รวมลูกค้า", "รายได้รวม", "รายได้"],
    "cost": ["ต้นทุนที่ปันส่วน", "ต้นทุนที่ปันส่วนตามยอดรายได้ของลูกค้า", "ต้นทุนรวม", "ต้นทุน"],
    "profit": ["กำไร", "กำไรลูกค้ารวม", "กำไรรวม", "กำไรสุทธิ"],
    "product": ["ประเภทสินค้ารายได้สูงสุด", "ประเภทสินค้าหลัก", "ประเภทสินค้า"],
}
AGE_LABELS = ["ตรงเวลา", "ช้า 1–30 วัน", "ช้า 31–60 วัน", "ช้า 61–90 วัน", "ช้าเกิน 90 วัน"]
AGE_COLORS = ["#2F6690", "#8FB3DE", "#F2B880", "#E07A5F", "#C8102E"]  # ตรงเวลา → เกิน 90 วัน
CLS_NAMES = ["ลูกหนี้ชั้นดี", "ลูกหนี้เฝ้าติดตาม", "ลูกหนี้ด้อยคุณภาพ (NPL)", "ไม่ระบุ"]
CLS_COLORS = ["#86CFA3", "#F6AE6B", "#E0566C", "#CBD5E1"]

CUST_CSS = """
<style>
.cu-kpi { display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:10px; margin:6px 0 10px; }
.cu-kpi div.b { background:#FFF8F9; border:1px solid #F6DDE2; border-radius:14px; padding:10px 14px; min-width:0; }
.cu-kpi .k { font-size:12px; color:#64748B; font-weight:600; }
.cu-kpi .v { font-size:20px; font-weight:800; color:#0F172A; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cu-kpi .s { font-size:11.5px; color:#94A3B8; }
@media (max-width:1100px){ .cu-kpi { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.cu-name { max-width:260px; display:inline-block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; vertical-align:bottom; }
.cu-beh { display:inline-block; font-size:11.5px; font-weight:700; padding:2px 9px; border-radius:99px; white-space:nowrap; }
.cu-age { display:flex; height:10px; border-radius:99px; overflow:hidden; background:#F1F5F9; min-width:120px; }
.cu-age span { display:block; height:100%; }
.cu-story { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:14px; padding:12px 16px; font-size:14px;
            color:#1E293B; line-height:1.7; margin:8px 0 4px; }
.cu-story b { font-variant-numeric:tabular-nums; }
.cu-rec { margin-top:6px; font-weight:700; }
</style>
"""


def _nk(v) -> str:
    return re.sub(r"[\s_\-\.\(\)]+", "", str(v)).casefold()


def find_customer_file():
    if not DATA_FOLDER.exists():
        return None
    key = _nk(CUST_KEYWORD)
    files = [f for f in DATA_FOLDER.iterdir()
             if f.is_file() and f.suffix.lower() in {".xlsx", ".xlsm"} and not f.name.startswith("~$")
             and key in _nk(f.stem)]
    return max(files, key=lambda f: f.stat().st_mtime_ns) if files else None


def _cls_idx(v) -> int:
    k = _nk(v) if isinstance(v, str) else ""
    if not k:
        return 3
    if any(t in k for t in ("ด้อย", "npl", "nonperforming", "สูญ")):
        return 2
    if any(t in k for t in ("เฝ้า", "ติดตาม", "underperforming")):
        return 1
    return 0 if "ดี" in k or "performing" in k else 3


NUM_FIELDS = (("bills", "Bills"), ("late_bills", "LateBills"), ("sum_delay", "SumDelay"),
              ("max_delay", "MaxDelay"), ("late_rate", "LateRate"), ("risk", "Risk"),
              ("billed", "Billed"), ("wrisk", "WRisk"), ("revenue", "Revenue"),
              ("cost", "Cost"), ("profit", "Profit"),
              ("b0", "B0"), ("b1", "B1"), ("b2", "B2"), ("b3", "B3"), ("b4", "B4"))
PAY_FIELDS = ["Bills", "LateBills", "SumDelay", "MaxDelay", "LateRate", "Risk", "Billed", "WRisk",
              "B0", "B1", "B2", "B3", "B4"]
PAY_KEYS = ["bills", "late_bills", "late_rate", "max_delay", "b0", "b1", "b2", "b3", "b4", "cls"]
PAY_HEADER_HINTS = CUST_COLS["bills"] + CUST_COLS["late_rate"] + CUST_COLS["late_bills"] + CUST_COLS["cls"]


def find_ar_report():
    """ไฟล์รายงานลูกหนี้ (ชื่อมีคำว่า ลูกหนี้ แต่ไม่ใช่ไฟล์ เชื่อมลูกหนี้…) ใช้อ่านชีต สรุปลูกหนี้"""
    if not DATA_FOLDER.exists():
        return None
    files = [f for f in DATA_FOLDER.iterdir()
             if f.is_file() and f.suffix.lower() in {".xlsx", ".xlsm"} and not f.name.startswith("~$")
             and "ลูกหนี้" in _nk(f.stem) and "เชื่อม" not in _nk(f.stem)]
    return max(files, key=lambda f: ("รายงาน" in _nk(f.stem), f.stat().st_mtime_ns)) if files else None


def _header_row(xl, sheet, hints):
    raw = xl.parse(sheet, header=None, nrows=20)
    names = {_nk(n) for n in CUST_COLS["name"]}
    want = {_nk(n) for n in hints}
    for i, row in raw.iterrows():
        keys = {_nk(v) for v in row.tolist() if isinstance(v, str)}
        if keys & names and keys & want:
            return i
    return None


def _col_map(df) -> dict:
    by = {}
    for c in df.columns:
        by.setdefault(_nk(c), c)
    col = {}
    for key, names in CUST_COLS.items():
        hit = next((by[_nk(n)] for n in names if _nk(n) in by and by[_nk(n)] not in col.values()), None)
        if hit is not None:
            col[key] = hit
    return col


def _frame(df, col) -> pd.DataFrame:
    out = pd.DataFrame({"Name": df[col["name"]].astype("string").fillna("").str.strip()})
    for key, name in NUM_FIELDS:
        out[name] = _num(df[col[key]]) if key in col else float("nan")
    out["Aging"] = df[col["aging"]].astype("string").fillna("").str.strip() if "aging" in col else ""
    out["Product"] = df[col["product"]].astype("string").fillna("").str.strip() if "product" in col else ""
    if "product" in col:
        out["Product"] = out["Product"].mask(out["Product"].isin(["0", "nan", "None", "<NA>", "-"]), "")
    out["Cls"] = df[col["cls"]].map(_cls_idx) if "cls" in col else 3
    return out[out["Name"].ne("")]


def _summary_sheets(xl):
    exact = [s for s in xl.sheet_names if "สรุปลูกหนี้" in _nk(s)]
    return exact or [s for s in xl.sheet_names if "สรุป" in _nk(s)]


@st.cache_data(show_spinner=False)
def load_customer_file(path_str: str, mtime_ns: int, ar_path_str: str = "", ar_mtime_ns: int = 0):
    """คืน (ตารางรายลูกค้า, คอลัมน์การจ่ายที่พบ, แหล่งข้อมูล)
    หลัก: ชีต สรุปลูกหนี้ ในไฟล์ เชื่อมลูกหนี้ลูกค้า (1 แถว = 1 ลูกหนี้ มีทั้งการจ่ายหนี้และรายได้/ต้นทุน/กำไร)
    สำรอง: ถ้าชีตที่ใช้ไม่มีคอลัมน์การจ่าย จะไปจับคู่ชื่อกับชีต สรุปลูกหนี้ อื่น (ไฟล์นี้ก่อน แล้วไฟล์รายงานลูกหนี้)"""
    xl = pd.ExcelFile(path_str)
    profit_sheet, header = None, None
    # ชีต "สรุปลูกหนี้" ของไฟล์เชื่อม (มีทั้งการจ่ายหนี้ + รายได้/ต้นทุน/กำไร) ใช้ก่อนชีตอื่น
    order = sorted(xl.sheet_names, key=lambda s: 0 if "สรุปลูกหนี้" in _nk(s) else 1)
    for sheet in order:
        h = _header_row(xl, sheet, CUST_COLS["revenue"] + CUST_COLS["profit"])
        if h is not None:
            profit_sheet, header = sheet, h
            break
    if profit_sheet is None:
        raise ValueError("ไม่พบชีตที่มีคอลัมน์ ชื่อลูกค้า และ รายได้/กำไร")
    df = xl.parse(profit_sheet, header=header)
    col = _col_map(df)
    out = _frame(df, col)
    out = out[out[["Revenue", "Cost", "Profit", "Bills", "Billed"]].notna().any(axis=1)]
    pay_found = [k for k in PAY_KEYS if k in col]
    pay_src = f"{Path(path_str).name} › {profit_sheet}" if pay_found else ""

    # ---- ชีตที่ใช้ไม่มีข้อมูลการจ่าย: ไปหาจากชีต สรุปลูกหนี้ อื่น (ในไฟล์นี้ก่อน แล้วค่อยไฟล์รายงานลูกหนี้) ----
    sources = [] if pay_found else [(xl, s, Path(path_str).name) for s in _summary_sheets(xl) if s != profit_sheet]
    if ar_path_str and not pay_found:
        try:
            xa = pd.ExcelFile(ar_path_str)
            sources += [(xa, s, Path(ar_path_str).name) for s in _summary_sheets(xa)]
        except Exception:
            pass
    for x, sheet, fname in sources:
        h = _header_row(x, sheet, PAY_HEADER_HINTS)
        if h is None:
            continue
        sd = x.parse(sheet, header=h)
        sc = _col_map(sd)
        pay = _frame(sd, sc)
        has = pay[PAY_FIELDS].notna().any(axis=1) | pay["Aging"].ne("") | pay["Cls"].ne(3)
        pay = pay[has].drop_duplicates("Name", keep="last").set_index("Name")
        if pay.empty:
            continue
        out = out.set_index("Name")
        for f in PAY_FIELDS:  # ค่าจากชีตสรุปลูกหนี้มาก่อน
            out[f] = pay[f].reindex(out.index).combine_first(out[f])
        aging = pay["Aging"].reindex(out.index).fillna("")
        out["Aging"] = aging.where(aging.ne(""), out["Aging"])
        cls = pay["Cls"].reindex(out.index)
        out["Cls"] = cls.where(cls.notna() & cls.ne(3), out["Cls"]).fillna(3).astype(int)
        out = out.reset_index()
        pay_found = sorted(set(pay_found) | {k for k in PAY_KEYS if k in sc}, key=PAY_KEYS.index)
        pay_src = f"{fname} › {sheet} (จับคู่ด้วยชื่อลูกหนี้)"
        break

    for i in range(5):
        out[f"B{i}"] = out[f"B{i}"].fillna(0.0)
    out = out.copy()
    if out["LateRate"].isna().all() and out["Bills"].notna().any():
        out["LateRate"] = out["LateBills"] / out["Bills"].where(out["Bills"] > 0)
    rate = out["LateRate"].dropna()
    if not rate.empty and rate.abs().median() > 1.5:  # เก็บเป็น 25 แทน 0.25
        out["LateRate"] = out["LateRate"] / 100
    out["Profit"] = out["Profit"].fillna(out["Revenue"] - out["Cost"])
    out["Billed"] = out["Billed"].fillna(out[[f"B{i}" for i in range(5)]].sum(axis=1))
    out["Margin"] = out["Profit"] / out["Revenue"].where(out["Revenue"] != 0)
    out["LateAmt"] = out[["B1", "B2", "B3", "B4"]].sum(axis=1)
    out["LateAmtShare"] = out["LateAmt"] / out["Billed"].where(out["Billed"] > 0)
    out["AvgDelay"] = out["SumDelay"] / out["LateBills"].where(out["LateBills"] > 0)
    out["HasPay"] = (out["Bills"].notna() | out["LateRate"].notna()
                     | out[[f"B{i}" for i in range(5)]].sum(axis=1).gt(0))
    # ---- กลุ่มลูกค้าตามเกณฑ์ของฝ่ายบัญชี (คอลัมน์ในชีตสรุปลูกหนี้) ----
    ci = out["Cls"].where(out["HasPay"], 3).fillna(3).astype(int)
    out["ClsIdx"] = ci
    ai = out["Aging"].map(_age_idx)
    # ไม่มีข้อความกลุ่มอายุ: ใช้ช่วงที่แย่ที่สุดที่มียอดในคอลัมน์ ยอดค้าง…
    worst = pd.Series(0, index=out.index)
    for i in range(1, 5):
        worst = worst.where(out[f"B{i}"].le(0), i)
    ai = ai.fillna(worst.where(out["HasPay"])).fillna(5).astype(int)
    out["AgeIdx"] = ai.where(out["HasPay"], 5)
    out = out.drop_duplicates("Name", keep="last").reset_index(drop=True)
    return out, pay_found, pay_src, profit_sheet


def _grp_cell(basis, i) -> str:
    groups = GROUP_BASES[basis][1]
    i = int(i) if pd.notna(i) else len(groups) - 1
    if i >= len(groups) - 1:
        return '<td class="tc-muted">—</td>'
    return f"<td>{_beh_badge(groups[i][0], groups[i][1])}</td>"


def _beh_badge(text, color) -> str:
    return f'<span class="cu-beh" style="background:{_tint(color, 0.78)};color:{color}">{esc(str(text))}</span>'


def _age_bar(r) -> str:
    total = sum(float(r[f"B{i}"]) for i in range(5))
    if total <= 0:
        return '<span class="tc-muted">—</span>'
    parts = "".join(
        f'<span style="width:{float(r[f"B{i}"]) / total * 100:.1f}%;background:{AGE_COLORS[i]}" '
        f'title="{AGE_LABELS[i]} {ff(r[f"B{i}"])}"></span>'
        for i in range(5) if r[f"B{i}"] > 0
    )
    return f'<div class="cu-age">{parts}</div>'



# เกณฑ์ของฝ่ายบัญชี (ความหมายตามชีต เงื่อนไข ของรายงานลูกหนี้)
GROUP_BASES = {
    "การแบ่งชั้นลูกหนี้ (TFRS 9)": ("ClsIdx", [
        ("ลูกหนี้ชั้นดี", "#2F6690", "ไม่ค้างชำระ หรือค้างไม่เกิน 30 วัน — ความเสี่ยงด้านเครดิตยังไม่เพิ่มขึ้น ถือเป็นลูกหนี้ปกติ"),
        ("ลูกหนี้เฝ้าติดตาม", "#F2B880", "ค้างชำระ 31–90 วัน — ความเสี่ยงด้านเครดิตเพิ่มขึ้นอย่างมีนัยสำคัญ ควรเพิ่มความเข้มงวดในการติดตามทวงถาม"),
        ("ลูกหนี้ด้อยคุณภาพ (NPL)", "#C8102E", "ค้างชำระเกิน 90 วัน — ผิดนัดชำระและมีการด้อยค่าด้านเครดิต อาจต้องพิจารณาระงับการขายและตั้งสำรองหนี้สูญ"),
        ("ไม่มีข้อมูลลูกหนี้", "#CBD5E1", "—"),
    ]),
    "กลุ่มช่วงอายุลูกหนี้": ("AgeIdx", [
        ("ชำระตรงเวลา", "#2F6690", "ความเสี่ยงต่ำสุด ไม่ต้องตั้งค่าเผื่อหนี้สงสัยจะสูญ"),
        ("ค้างชำระ 1–30 วัน", "#8FB3DE", "ความเสี่ยงต่ำ ยังอยู่ในเกณฑ์ติดตามทวงถามได้ปกติ"),
        ("ค้างชำระ 31–60 วัน", "#F2B880", "ความเสี่ยงปานกลาง ควรเพิ่มความเข้มงวดในการติดตาม"),
        ("ค้างชำระ 61–90 วัน", "#E07A5F", "ความเสี่ยงสูง อาจพิจารณาระงับการขายชั่วคราว"),
        ("ค้างชำระเกิน 90 วัน", "#C8102E", "ความเสี่ยงสูงมาก ถือเป็นหนี้ด้อยคุณภาพ (NPL) ควรพิจารณาตั้งค่าเผื่อหนี้สงสัยจะสูญในอัตราที่สูง"),
        ("ไม่มีข้อมูลลูกหนี้", "#CBD5E1", "—"),
    ]),
}


def _age_idx(v):
    """ข้อความกลุ่มช่วงอายุลูกหนี้ -> 0 ตรงเวลา / 1 1–30 / 2 31–60 / 3 61–90 / 4 เกิน 90 (ไม่รู้ = None)"""
    k = _nk(v) if isinstance(v, str) else ""
    if not k:
        return None
    if "ตรงเวลา" in k or "ยังไม่ถึง" in k or "ไม่ค้าง" in k:
        return 0
    if "เกิน90" in k or "91" in k:
        return 4
    if "6190" in k:
        return 3
    if "3160" in k:
        return 2
    if "130" in k:
        return 1
    return None


def _apply_group(df: pd.DataFrame, basis: str) -> pd.DataFrame:
    col, groups = GROUP_BASES[basis]
    idx = df[col].clip(0, len(groups) - 1).astype(int)
    return df.assign(Behavior=idx.map(lambda i: groups[i][0]), BehColor=idx.map(lambda i: groups[i][1]),
                     Advice=idx.map(lambda i: groups[i][2]))


def _short(name, n=14) -> str:
    s = str(name)
    return s if len(s) <= n else s[:n - 1] + "…"


def _customer_charts(view: pd.DataFrame, view_pay: bool, basis: str):
    groups = GROUP_BASES[basis][1]
    BEH_ORDER = [g[0] for g in groups]
    BEH_COLORS = {g[0]: g[1] for g in groups}
    nodata = groups[-1][0]
    short = "ชั้นลูกหนี้ (TFRS 9)" if "TFRS" in basis else "ช่วงอายุลูกหนี้"
    """กราฟสรุป 4 ภาพ: กำไรตามพฤติกรรม · ยอดวางบิลตามความช้า · 10 รายกำไรสูงสุด · สินค้าหลัก × พฤติกรรม"""
    a, b = st.columns([1.25, 1], gap="medium")

    # 1) รายได้-ต้นทุน-กำไร ตามพฤติกรรมการจ่าย
    with a:
        st.markdown(f"##### รายได้ ต้นทุน กำไร ตาม{short}")
        g = (view.groupby("Behavior")
             .agg(N=("Name", "size"), Rev=("Revenue", "sum"), Cost=("Cost", "sum"), Profit=("Profit", "sum"))
             .reindex([x for x in BEH_ORDER if x in set(view["Behavior"])]))
        if not view_pay:
            g = g.drop(index=nodata, errors="ignore")
        if g.empty:
            st.info("ไม่มีข้อมูลการจ่ายหนี้สำหรับแยกกลุ่ม")
        else:
            g["Margin"] = g["Profit"] / g["Rev"].where(g["Rev"] != 0)
            labels = [f"{k}<br><span style='font-size:11px;color:#64748B'>{int(r.N):,} ราย</span>"
                      for k, r in g.iterrows()]
            fig = go.Figure()
            for name, col, colr in (("รายได้", "Rev", "#1F3A5F"), ("ต้นทุน", "Cost", "#B8C4D6"),
                                    ("กำไร", "Profit", "#2A9D8F")):
                fig.add_trace(go.Bar(name=name, x=labels, y=g[col], marker_color=colr,
                                     hovertemplate=f"{name} ฿%{{y:,.0f}}<extra></extra>"))
            fig.add_trace(go.Scatter(
                name="อัตรากำไร", x=labels, y=g["Margin"] * 100, yaxis="y2", mode="lines+markers+text",
                line=dict(color="#C8102E", width=2.5), marker=dict(size=8, color="#C8102E"),
                text=[f"{v * 100:.0f}%" if pd.notna(v) else "" for v in g["Margin"]], textposition="top center",
                textfont=dict(color="#C8102E"),
                hovertemplate="อัตรากำไร %{y:.1f}%<extra></extra>",
            ))
            fig.update_layout(
                barmode="group", height=360, margin=dict(l=10, r=10, t=20, b=10), bargap=0.25,
                legend=dict(orientation="h", y=1.12, x=0),
                yaxis=dict(title="บาท", tickformat=",.0f"),
                yaxis2=dict(overlaying="y", side="right", ticksuffix="%", showgrid=False, rangemode="tozero"),
                xaxis=dict(type="category"),
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
            st.caption(f"กลุ่มตาม{short} จากชีตสรุปลูกหนี้ (เกณฑ์ฝ่ายบัญชี) · ดูว่ากลุ่มเสี่ยงยังทำกำไรคุ้มหรือไม่ · "
                       "เส้น = อัตรากำไรของกลุ่ม")

    # 2) ยอดวางบิลแยกตามความช้า
    with b:
        st.markdown("##### ยอดวางบิลแยกตามความช้าในการจ่าย")
        amt = pd.Series([float(view[f"B{i}"].sum()) for i in range(5)], index=AGE_LABELS)
        if amt.sum() <= 0:
            st.info("ไม่มีข้อมูลยอดวางบิล")
        else:
            late_share = amt.iloc[1:].sum() / amt.sum()
            fig = go.Figure(go.Pie(
                labels=AGE_LABELS, values=amt.values, hole=0.62, sort=False,
                marker=dict(colors=AGE_COLORS, line=dict(color="white", width=2)),
                textinfo="percent", textposition="outside",
                hovertemplate="%{label}<br>฿%{value:,.0f}<br>%{percent}<extra></extra>",
            ))
            fig.update_layout(
                height=360, margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(orientation="h", y=-0.08, x=0, font=dict(size=11)),
                annotations=[dict(text=f"<span style='font-size:11px;color:#64748B'>จ่ายช้า</span><br>"
                                       f"<b style='font-size:20px;color:#C8102E'>{late_share * 100:.0f}%</b><br>"
                                       f"<span style='font-size:11px;color:#64748B'>ของยอด {fm(amt.sum())}</span>",
                                  x=0.5, y=0.5, showarrow=False)],
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    c, d = st.columns([1, 1], gap="medium")

    # 3) 10 ลูกค้ากำไรสูงสุด (สีตามพฤติกรรม)
    with c:
        mode = st.radio("10 ลูกค้า", ["กำไรสูงสุด", "ขาดทุน/กำไรต่ำสุด", "รายได้สูงสุด"], horizontal=True,
                        key="do_cu_top10_mode")
        col, asc = {"กำไรสูงสุด": ("Profit", False), "ขาดทุน/กำไรต่ำสุด": ("Profit", True),
                    "รายได้สูงสุด": ("Revenue", False)}[mode]
        top = view.sort_values(col, ascending=asc).head(10).iloc[::-1]
        if top.empty:
            st.info("ไม่มีข้อมูล")
        else:
            fig = go.Figure(go.Bar(
                y=[_short(n) for n in top["Name"]], x=top[col], orientation="h",
                marker=dict(color=[BEH_COLORS.get(bh, "#CBD5E1") for bh in top["Behavior"]],
                            line=dict(color="white", width=1)),
                text=[f"  {fm(v)} · {fp(m)}" for v, m in zip(top[col], top["Margin"])],
                textposition="outside", cliponaxis=False, textfont=dict(color="#334155", size=11),
                customdata=top[["Name", "Revenue", "Cost", "Profit", "Behavior"]].to_numpy(),
                hovertemplate=("<b>%{customdata[0]}</b><br>รายได้ ฿%{customdata[1]:,.0f} · ต้นทุน ฿%{customdata[2]:,.0f}"
                               "<br>กำไร ฿%{customdata[3]:,.0f}<br>%{customdata[4]}<extra></extra>"),
            ))
            span = float(top[col].abs().max()) or 1.0
            lo = min(0.0, float(top[col].min())) * 1.35
            fig.update_layout(
                height=380, margin=dict(l=10, r=30, t=10, b=10), showlegend=False,
                xaxis=dict(title="บาท", tickformat=",.0f", range=[lo, max(span, float(top[col].max())) * 1.45]),
                yaxis=dict(automargin=True, tickfont=dict(size=11)),
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
            st.caption(f"สีแท่ง = {short} · " + " · ".join(
                f'<span style="color:{BEH_COLORS[x]}">■</span> {x}' for x in BEH_ORDER[:-1]),
                unsafe_allow_html=True)

    # 4) สินค้าหลัก × พฤติกรรมการจ่าย
    with d:
        st.markdown(f"##### รายได้ตามสินค้าหลัก แยก{short}")
        prod = view["Product"].astype("string").fillna("").str.strip()
        prod = prod.mask(prod.isin(["", "0", "nan", "None", "<NA>", "-"]), "ไม่ระบุ")
        pv = (view.assign(Product=prod)
              .pivot_table(index="Product", columns="Behavior", values="Revenue", aggfunc="sum", fill_value=0))
        if pv.empty:
            st.info("ไม่มีข้อมูลประเภทสินค้า")
        else:
            pv = pv.loc[pv.sum(axis=1).sort_values().index].tail(10)
            fig = go.Figure()
            for bh in BEH_ORDER:
                if bh in pv.columns and pv[bh].sum() > 0:
                    fig.add_trace(go.Bar(name=bh, y=pv.index, x=pv[bh], orientation="h",
                                         marker=dict(color=BEH_COLORS[bh], line=dict(color="white", width=1)),
                                         hovertemplate=f"%{{y}}<br>{bh}: ฿%{{x:,.0f}}<extra></extra>"))
            fig.update_layout(
                barmode="stack", height=380 + 10 * max(0, len(pv) - 6), margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=11), traceorder="normal"),
                bargap=0.35,
                xaxis=dict(title="รายได้ (บาท)", tickformat=",.2s"), yaxis=dict(automargin=True, type="category"),
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
            st.caption("ดูว่าสินค้าประเภทไหน มีสัดส่วนลูกค้ากลุ่มเสี่ยงมาก")


def render_customer_overview():
    path = find_customer_file()
    if path is None:
        return  # ยังไม่มีไฟล์ ไม่ต้องแสดงส่วนนี้
    try:
        ar_path = find_ar_report()
        cu, pay_cols, pay_src, src_sheet = load_customer_file(
            str(path), path.stat().st_mtime_ns,
            str(ar_path) if ar_path else "", ar_path.stat().st_mtime_ns if ar_path else 0)
    except Exception as e:
        st.warning(f"อ่านไฟล์ {path.name} ไม่สำเร็จ: {e}")
        return
    if cu.empty:
        st.info(f"ไฟล์ {path.name} ไม่มีข้อมูลลูกค้า")
        return

    st.markdown(CUST_CSS, unsafe_allow_html=True)
    with _card("do_customers"):
        st.markdown("#### ภาพรวมลูกค้า: รายได้ ต้นทุน กำไร × พฤติกรรมการจ่ายหนี้")
        st.caption(f"รายได้/ต้นทุน/กำไร จากไฟล์ {path.name} › {src_sheet}"
                   + (f" · การจ่ายหนี้จาก {pay_src}" if pay_src else "")
                   + " · ตัวกรองด้านบนของหน้านี้ไม่มีผลกับส่วนนี้")

        n_all, n_pay = len(cu), int(cu["HasPay"].sum())
        if n_pay == 0:
            st.info(
                f"ไฟล์นี้มีข้อมูลรายได้/ต้นทุน/กำไร {n_all:,} ราย แต่**ไม่มีข้อมูลการจ่ายหนี้**เลย "
                + ("(ไม่พบชีต สรุปลูกหนี้ ทั้งในไฟล์นี้และไฟล์รายงานลูกหนี้)"
                   if not pay_cols else f"(พบชีต {pay_src} แต่ชื่อลูกค้าจับคู่กับชื่อลูกหนี้ไม่ได้เลย)")
                + " · ตอนนี้จึงแสดงเฉพาะส่วนกำไร"
            )
        only_pay = False
        if 0 < n_pay < n_all:
            only_pay = st.toggle(
                f"แสดงเฉพาะลูกค้าที่มีข้อมูลการจ่ายหนี้ ({n_pay:,} จาก {n_all:,} ราย)", value=True,
                key="do_cu_only_pay",
                help="ลูกค้าที่ไม่มีข้อมูลลูกหนี้ มักเป็นลูกค้าเงินสด หรือชื่อจับคู่กับรายงานลูกหนี้ไม่ได้",
            )
        base_cu = cu[cu["HasPay"]] if only_pay else cu
        basis = st.radio("แบ่งกลุ่มลูกค้าตามเกณฑ์ฝ่ายบัญชี", list(GROUP_BASES), horizontal=True, key="do_cu_basis",
                         help="ใช้ค่าในคอลัมน์ของชีตสรุปลูกหนี้โดยตรง · ความหมายของแต่ละกลุ่มตามชีตเงื่อนไข")
        base_cu = _apply_group(base_cu, basis)
        grp_names = [g[0] for g in GROUP_BASES[basis][1]]

        c1, c2, c3 = st.columns([1.2, 1.4, 2.4])
        with c1:
            prods = sorted(p for p in base_cu["Product"].unique() if p)
            pick_prod = st.multiselect("ประเภทสินค้าหลัก", prods, placeholder="ทั้งหมด",
                                       key=_wkey("do_cu_prod", prods))
        with c2:
            behs = [b for b in grp_names if (base_cu["Behavior"] == b).any()]
            pick_beh = st.multiselect("ชั้นลูกหนี้" if "TFRS" in basis else "ช่วงอายุลูกหนี้", behs,
                                      placeholder="ทั้งหมด", key=_wkey("do_cu_beh", behs))
        with c3:
            search = st.text_input("ค้นหาลูกค้า", placeholder="พิมพ์ชื่อบางส่วน", key="do_cu_search")
        view = base_cu
        if pick_prod:
            view = view[view["Product"].isin(pick_prod)]
        if pick_beh:
            view = view[view["Behavior"].isin(pick_beh)]
        if search.strip():
            view = view[view["Name"].str.contains(search.strip(), case=False, regex=False, na=False)]
        if view.empty:
            st.info("ไม่มีลูกค้าตามตัวกรอง")
            return

        rev, cost, prof = view["Revenue"].sum(), view["Cost"].sum(), view["Profit"].sum()
        on_time = int((view["LateRate"] == 0).sum())
        with_rate = int((view["LateRate"].notna() & view["HasPay"]).sum())
        view_pay = bool(view["HasPay"].any())
        late_amt, billed = view["LateAmt"].sum(), view["Billed"].sum()
        loss_n = int((view["Profit"] < 0).sum())
        st.markdown(
            '<div class="cu-kpi">'
            f'<div class="b"><div class="k">ลูกค้า</div><div class="v">{len(view):,} ราย</div>'
            f'<div class="s">ขาดทุน {loss_n:,} ราย</div></div>'
            f'<div class="b"><div class="k">รายได้รวม</div><div class="v">{fm(rev)}</div>'
            f'<div class="s">เฉลี่ย {fm(rev / len(view))} ต่อราย</div></div>'
            f'<div class="b"><div class="k">ต้นทุนที่ปันส่วน</div><div class="v">{fm(cost)}</div>'
            f'<div class="s">{fp(_div(cost, rev))} ของรายได้</div></div>'
            f'<div class="b"><div class="k">กำไร</div><div class="v {sign_cls(prof)}">{fm(prof)}</div>'
            f'<div class="s">อัตรากำไร {fp(_div(prof, rev))}</div></div>'
            f'<div class="b"><div class="k">จ่ายตรงเวลาเสมอ</div>'
            f'<div class="v">{fp(_div(on_time, with_rate))}</div>'
            + (f'<div class="s">จาก {with_rate:,} รายที่มีข้อมูล · ยอดที่จ่ายช้า {fp(_div(late_amt, billed))} ของยอดวางบิล</div></div>'
               if view_pay else '<div class="s">ไม่มีข้อมูลการจ่ายหนี้</div></div>')
            + '</div>',
            unsafe_allow_html=True,
        )

        # ---------- กราฟสรุป ----------
        try:
            _customer_charts(view, view_pay, basis)
        except Exception as e:  # กราฟชุดนี้ผิดพลาด ไม่ให้กระทบส่วนอื่น
            if getattr(type(e), "__module__", "").startswith("streamlit"):
                raise
            st.warning(f"กราฟสรุปลูกค้าแสดงไม่ได้ ({type(e).__name__}: {e})")

        # ---------- กราฟ กำไร × จ่ายช้า ----------
        q = view[view["Margin"].notna() & view["LateRate"].notna() & view["HasPay"] & (view["Revenue"] > 0)]
        q_cut = len(q) > 3000
        q = q.nlargest(3000, "Revenue").copy() if q_cut else q.copy()
        if not q.empty:
            p1, p2, _p3 = st.columns([1, 1, 2])
            overall_margin = _div(q["Profit"].sum(), q["Revenue"].sum())
            with p1:
                m_opts = ["ค่าเฉลี่ยทุกลูกค้า", "0% (กำไร/ขาดทุน)", "20%", "30%", "40%"]
                m_pick = st.selectbox("เส้นแบ่ง “กำไรดี”", m_opts, key="do_cu_mline")
            with p2:
                late_line = st.selectbox("เส้นแบ่ง “จ่ายช้า” เมื่อบิลช้าเกิน", [10, 25, 50], index=1,
                                         format_func=lambda v: f"{v}%", key="do_cu_lline")
            m_line = {"ค่าเฉลี่ยทุกลูกค้า": overall_margin, "0% (กำไร/ขาดทุน)": 0.0,
                      "20%": 0.2, "30%": 0.3, "40%": 0.4}[m_pick]
            m_line = 0.0 if pd.isna(m_line) else m_line
            q["x"] = (q["Margin"] * 100).clip(-100, 100)
            q["y"] = q["LateRate"] * 100
            good_m, late = q["Margin"] >= m_line, q["LateRate"] > late_line / 100
            groups = [
                ("⭐ กำไรดี + จ่ายตรง", "รักษาไว้ / ขยายงาน", C_GOOD, good_m & ~late),
                ("💸 กำไรดี แต่จ่ายช้า", "ตามหนี้ / ลดเครดิตเทอม", C_WARN, good_m & late),
                ("🏷️ จ่ายตรง แต่กำไรต่ำ", "ทบทวนราคา / ต้นทุน", C_OK, ~good_m & ~late),
                ("⚠️ กำไรต่ำ + จ่ายช้า", "ขึ้นราคา / เข้มงวดเงื่อนไขชำระ", C_BAD, ~good_m & late),
            ]
            mx = float(q["Revenue"].max()) or 1.0
            fig = go.Figure()
            for name, _a, colr, m in groups:
                part = q[m]
                if part.empty:
                    continue
                fig.add_trace(go.Scatter(
                    name=f"{name} ({len(part):,})", x=part["x"], y=part["y"], mode="markers",
                    marker=dict(size=8 + 30 * (part["Revenue"] / mx) ** 0.5, color=colr, opacity=0.75,
                                line=dict(color="white", width=1.2)),
                    customdata=part[["Name", "Revenue", "Profit", "Bills", "LateBills", "MaxDelay",
                                     "Behavior"]].to_numpy(),
                    hovertemplate=("<b>%{customdata[0]}</b><br>รายได้ ฿%{customdata[1]:,.0f} · "
                                   "กำไร ฿%{customdata[2]:,.0f} (%{x:.1f}%)"
                                   "<br>บิลช้า %{customdata[4]:,.0f}/%{customdata[3]:,.0f} (%{y:.0f}%) · "
                                   "ช้าสุด %{customdata[5]:,.0f} วัน<br>%{customdata[6]}<extra></extra>"),
                ))
            fig.add_vline(x=m_line * 100, line=dict(color="#94A3B8", width=1.5, dash="dash"))
            fig.add_hline(y=late_line, line=dict(color="#94A3B8", width=1.5, dash="dash"))
            fig.update_layout(
                height=440, margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", y=-0.16, x=0),
                xaxis=dict(title="อัตรากำไร (% ของรายได้) — ยิ่งขวายิ่งกำไรดี", ticksuffix="%", zeroline=False),
                yaxis=dict(title="% บิลที่จ่ายช้า — ยิ่งสูงยิ่งจ่ายช้า", ticksuffix="%", range=[-5, 105],
                           zeroline=False),
            )
            _style(fig)
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
            st.markdown(
                '<div class="do-quad">' + "".join(
                    f'<div style="background:{_tint(colr, 0.88)}">{esc(name)}<b>{int(m.sum()):,} ราย</b>'
                    f'รายได้ {fm(q.loc[m, "Revenue"].sum())} · กำไร {fm(q.loc[m, "Profit"].sum())}'
                    f'<small>👉 {esc(action)}</small></div>'
                    for name, action, colr, m in groups
                ) + "</div>",
                unsafe_allow_html=True,
            )
            st.caption("วงกลม = ลูกค้า 1 ราย · วงใหญ่ = รายได้สูง · ชี้เมาส์เพื่อดูรายละเอียด · "
                       "อัตรากำไรที่เกิน ±100% แสดงที่ขอบกราฟ"
                       + (" · แสดง 3,000 รายที่รายได้สูงสุด" if q_cut else ""))

        # ---------- ตารางลูกค้า ----------
        sort_map = {"รายได้สูงสุด": ("Revenue", False), "กำไรสูงสุด": ("Profit", False),
                    "ขาดทุนมากสุด": ("Profit", True), "อัตรากำไรต่ำสุด": ("Margin", True),
                    "% บิลช้ามากสุด": ("LateRate", False), "ช้าสูงสุด (วัน)": ("MaxDelay", False),
                    "ยอดจ่ายช้ามากสุด": ("LateAmt", False)}
        s1, s2 = st.columns([1.4, 0.6])
        with s1:
            sort_label = st.selectbox("เรียงตาม", list(sort_map), key="do_cu_sort")
        with s2:
            top_n = st.selectbox("แสดง", [20, 50, 100, 300], index=1, format_func=lambda v: f"{v} ราย",
                                 key="do_cu_top")
        col, asc = sort_map[sort_label]
        tb = view.sort_values([col, "Revenue"], ascending=[asc, False], na_position="last")
        head = ["#", "ลูกค้า", "สินค้าหลัก", "รายได้", "ต้นทุน", "กำไร", "อัตรากำไร"]
        if view_pay:
            head += ["บิล (ช้า/ทั้งหมด)", "ช้าสูงสุด", "ยอดวางบิลตามความช้า", "ชั้นลูกหนี้ (TFRS 9)", "กลุ่มช่วงอายุลูกหนี้"]
        body = []
        for i, r in enumerate(tb.head(top_n).to_dict("records"), 1):
            bills = "—" if pd.isna(r["Bills"]) else f'{int(r["LateBills"] or 0):,} / {int(r["Bills"]):,}'
            maxd = "—" if pd.isna(r["MaxDelay"]) else f'{int(r["MaxDelay"]):,} วัน'
            ci = int(r["Cls"])
            body.append(
                "<tr>"
                f'<td class="tc-rank">{i}</td>'
                f'<td><b><span class="cu-name" title="{esc(r["Name"])}">{esc(r["Name"])}</span></b></td>'
                f'<td class="tc-muted">{esc(r["Product"] or "—")}</td>'
                f'<td class="tc-num">{ff(r["Revenue"])}</td>'
                f'<td class="tc-num tc-muted">{ff(r["Cost"])}</td>'
                f'<td class="tc-num {sign_cls(r["Profit"])}">{ff(r["Profit"])}</td>'
                f'<td class="tc-num {sign_cls(r["Margin"])}">{fp(r["Margin"])}</td>'
                + ((f'<td class="tc-num">{bills}</td>'
                    f'<td class="tc-num">{maxd}</td>'
                    f"<td>{_age_bar(r)}</td>"
                    + _grp_cell("การแบ่งชั้นลูกหนี้ (TFRS 9)", r["ClsIdx"])
                    + _grp_cell("กลุ่มช่วงอายุลูกหนี้", r["AgeIdx"])) if view_pay else "")
                + "</tr>"
            )
        st.caption(f"แสดง {min(top_n, len(tb)):,} จาก {len(tb):,} ราย"
                   + ((" · แถบสี = สัดส่วนยอดวางบิลที่จ่าย "
                       + " / ".join(f'<span style="color:{c}">■</span> {l}' for l, c in zip(AGE_LABELS, AGE_COLORS)))
                      if view_pay else ""),
                   unsafe_allow_html=True)
        st.markdown(_table_html(head, body, right_cols={3, 4, 5, 6, 7, 8}, max_height=480), unsafe_allow_html=True)
        export = pd.DataFrame({
            "ลูกค้า": tb["Name"], "สินค้าหลัก": tb["Product"], "รายได้": tb["Revenue"], "ต้นทุนที่ปันส่วน": tb["Cost"],
            "กำไร": tb["Profit"], "อัตรากำไร": tb["Margin"], "จำนวนบิล": tb["Bills"], "บิลที่ช้า": tb["LateBills"],
            "% บิลที่ช้า": tb["LateRate"], "วันช้าสูงสุด": tb["MaxDelay"], "วันช้าเฉลี่ย (บิลที่ช้า)": tb["AvgDelay"],
            **{f"ยอด{AGE_LABELS[i]}": tb[f"B{i}"] for i in range(5)},
            "ชั้นลูกหนี้ (TFRS 9)": tb["ClsIdx"].map(lambda i: GROUP_BASES["การแบ่งชั้นลูกหนี้ (TFRS 9)"][1][int(i)][0]),
            "กลุ่มช่วงอายุลูกหนี้": tb["AgeIdx"].map(lambda i: GROUP_BASES["กลุ่มช่วงอายุลูกหนี้"][1][int(i)][0]),
            "ความหมายตามเกณฑ์ที่เลือก": tb["Advice"],
        })
        st.download_button("⬇️ ดาวน์โหลดรายชื่อลูกค้า (CSV)", export.to_csv(index=False).encode("utf-8-sig"),
                           file_name="customer_profit_payment.csv", mime="text/csv", key="do_cu_dl")

        # ---------- เจาะรายลูกค้า ----------
        st.markdown("##### เจาะรายลูกค้า")
        opts = view.nlargest(1000, "Revenue")["Name"].tolist()
        pick = st.selectbox("เลือกลูกค้า (รายได้สูงสุด 1,000 ราย · ใช้ช่องค้นหาด้านบนเพื่อหารายอื่น)", opts,
                            key=_wkey("do_cu_pick", opts[:50]))
        r = view[view["Name"] == pick].iloc[0]
        rank = int((cu["Revenue"] > r["Revenue"]).sum()) + 1
        boxes = [
            ("รายได้", fm(r["Revenue"]), f"อันดับ {rank:,} จาก {len(cu):,} ราย"),
            ("ต้นทุนที่ปันส่วน", fm(r["Cost"]), f'{fp(_div(r["Cost"], r["Revenue"]))} ของรายได้'),
            ("กำไร", fm(r["Profit"]), f'อัตรากำไร {fp(r["Margin"])}'),
            ("สินค้าหลัก", r["Product"] or "—", "ประเภทสินค้าที่ทำรายได้สูงสุด"),
            ("บิลที่จ่ายช้า", "—" if pd.isna(r["Bills"]) else f'{int(r["LateBills"] or 0):,} / {int(r["Bills"]):,}',
             f'{fp(r["LateRate"])} ของบิลทั้งหมด'),
            ("ช้าสูงสุด / เฉลี่ย", "—" if pd.isna(r["MaxDelay"]) else f'{int(r["MaxDelay"]):,} วัน',
             "—" if pd.isna(r["AvgDelay"]) else f'เฉลี่ย {r["AvgDelay"]:,.1f} วันต่อบิลที่ช้า'),
            ("ยอดวางบิลที่จ่ายช้า", fm(r["LateAmt"]), f'{fp(r["LateAmtShare"])} ของยอดวางบิล {fm(r["Billed"])}'),
            ("ชั้นลูกหนี้", CLS_NAMES[int(r["Cls"])], r["Aging"] or "—"),
        ]
        st.markdown(
            '<div class="do-box-grid">' + "".join(
                f'<div class="do-box"><div class="k">{esc(k)}</div><div class="v" title="{esc(str(v))}">{esc(str(v))}</div>'
                f'<div class="s">{esc(str(s))}</div></div>' for k, v, s in boxes
            ) + "</div>",
            unsafe_allow_html=True,
        )
        profit_txt = ("มีกำไร" if r["Profit"] >= 0 else "ขาดทุน")
        story = (
            f'ลูกค้ารายนี้สร้างรายได้ <b>{fm(r["Revenue"])}</b> (อันดับ {rank:,} จาก {len(cu):,} ราย) '
            f'หลังหักต้นทุน <b>{fm(r["Cost"])}</b> {profit_txt} <b class="{sign_cls(r["Profit"])}">{fm(r["Profit"])}</b> '
            f'(อัตรากำไร {fp(r["Margin"])} เทียบค่าเฉลี่ย {fp(_div(cu["Profit"].sum(), cu["Revenue"].sum()))})'
        )
        if pd.notna(r["Bills"]):
            story += (f' · วางบิล {int(r["Bills"]):,} บิล จ่ายช้า {int(r["LateBills"] or 0):,} บิล '
                      f'({fp(r["LateRate"])})')
            if pd.notna(r["MaxDelay"]) and r["MaxDelay"] > 0:
                story += f' ช้าสุด {int(r["MaxDelay"]):,} วัน'
        story += f' · {esc(basis)}: {_beh_badge(r["Behavior"], r["BehColor"])}'
        if r["Advice"] != "—":
            story += f'<div class="cu-rec">👉 {esc(r["Advice"])}</div>'
            story += '<div style="font-size:12px;color:#64748B">ความหมายตามชีตเงื่อนไข (เกณฑ์ฝ่ายบัญชี)</div>'
        st.markdown(f'<div class="cu-story">{story}</div>', unsafe_allow_html=True)
        if r["HasPay"] and r["Billed"] > 0:
            st.markdown(_age_bar(r), unsafe_allow_html=True)
            st.caption("แถบสี = สัดส่วนยอดวางบิลของลูกค้ารายนี้ แยกตามความช้าในการจ่าย")


def render_direction_overview_dashboard():
    """ภาพรวมรายทิศทาง + ภาพรวมลูกค้า (สองส่วนทำงานแยกกัน ส่วนหนึ่งพังไม่กระทบอีกส่วน)"""
    _render_direction_main()
    try:
        render_customer_overview()
    except Exception as e:
        if getattr(type(e), "__module__", "").startswith("streamlit"):
            raise
        st.warning(f"ส่วน “ภาพรวมลูกค้า” แสดงไม่ได้ ({type(e).__name__}: {e})")