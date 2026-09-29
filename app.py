import re

import hashlib
from html import escape as esc
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from datetime import datetime
from database import rebuild_database
from auth import require_login
from html_export import build_page_html
from transport_cost_route import render_transport_cost_dashboard
from sidebar_brand import render_sidebar_top, render_sidebar_bottom
from theme import apply_theme, PALETTE, GOOD, WATCH, BAD
from load_factor import render_load_factor_dashboard
from empty_trip import render_empty_trip_dashboard as render_empty_trip_page
from customer_profit import render_customer_profit_dashboard
# [แก้ไข 1/2] หน้าลูกหนี้ใหม่ อยู่ในไฟล์ ar_dashboard.py
from ar_dashboard import render_ar_dashboard as render_ar_page
# หน้าภาพรวมรายทิศทาง (รายได้ ต้นทุน กำไร CM Load Factor) อยู่ในไฟล์ direction_overview.py
from direction_overview import render_direction_overview_dashboard

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Transportation Cost Dashboard",
    page_icon="🚚",
    layout="wide",
)

# ธีมสีแดง-ขาวพาสเทล ใช้ร่วมกันทุกแดชบอร์ด (อยู่ในไฟล์ theme.py)
apply_theme()

# ต้องใส่รหัสผ่านก่อนเห็นอะไรทั้งหมด
require_login()

DATA_FOLDER = Path("data")
DB_PATH = Path("dashboard.duckdb")
DATA_FOLDER.mkdir(exist_ok=True)

# Viewer mode is disabled by default so the existing Data Management menu remains available.
try:
    VIEWER_MODE = bool(st.secrets.get("VIEWER_MODE", False))
except Exception:
    VIEWER_MODE = False
# ==========================
# Modern Dashboard Font Style
# ==========================

st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;500;600;700;800&display=swap');


/* Global Font — apply to text elements only.
   Do NOT apply font-family to every child element because Streamlit
   uses Material icon fonts for upload/expand/dropdown icons. */
.stApp {
    font-family: 'Noto Sans Thai', 'IBM Plex Sans Thai', sans-serif !important;
}

.stApp p,
.stApp label,
.stApp input,
.stApp textarea,
.stApp button,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stMetricLabel"],
.stApp [data-testid="stMetricValue"] {
    font-family: 'Noto Sans Thai', 'IBM Plex Sans Thai', sans-serif !important;
}

/* Keep Streamlit Material icons as icons — prevents text such as
   "upload" / "keyboard_arrow_down" from appearing visibly. */
.material-symbols-rounded,
.material-icons,
.material-icons-round,
[data-testid="stIconMaterial"] {
    font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
}


/* Main content only */


/* Heading เท่านั้น */
h1, h2, h3 {
    font-family: 'Noto Sans Thai', sans-serif !important;
}


/* Metric */
[data-testid="stMetricValue"] {
    font-family: 'Noto Sans Thai', sans-serif !important;
    font-weight: 800 !important;
}




/* Compact typography - fit common laptop/desktop screens */
h1 {
    font-family: 'Noto Sans Thai', sans-serif !important;
    font-size: clamp(26px, 2.1vw, 32px) !important;
    line-height: 1.2 !important;
    font-weight: 800 !important;
    letter-spacing: -0.4px !important;
}

h2 {
    font-size: clamp(21px, 1.7vw, 25px) !important;
    line-height: 1.25 !important;
    font-weight: 700 !important;
}

h3 {
    font-size: clamp(17px, 1.35vw, 20px) !important;
    line-height: 1.3 !important;
    font-weight: 650 !important;
}

/* Metric ตัวเลข */
[data-testid="stMetricValue"] {
    font-family: 'Noto Sans Thai', sans-serif !important;
    font-size: clamp(24px, 2vw, 29px) !important;
    line-height: 1.15 !important;
    font-weight: 750 !important;
}

/* Label */
label {
    font-size: 13px !important;
    line-height: 1.3 !important;
    font-weight: 500 !important;
}


/* Selectbox text */
div[data-baseweb="select"] {
    min-height: 42px !important;
    height: 42px !important;
}

div[data-baseweb="select"] [role="button"] {
    min-height: 42px !important;
    height: 42px !important;
    line-height: 1.4 !important;
}

/* ระยะห่างแบบกระชับ ไม่ให้หน้าเว็บยาวเกิน */
[data-testid="stVerticalBlock"] {
    gap: 0.75rem !important;
}


/* KPI Card spacing */
div[data-testid="column"] {
    padding-right: 12px !important;
}


/* KPI Card */
.stMetric {
    padding: 13px 14px !important;
}


/* KPI Label */
[data-testid="stMetricLabel"] {
    font-size: 12px !important;
    line-height: 1.3 !important;
}


/* KPI Number */
[data-testid="stMetricValue"] {
    margin-top: 4px !important;
}


/* =========================
   LOAD FACTOR REFERENCE UI
   ========================= */
.lf-new-header {
    display:flex; align-items:center; gap:14px;
    background:linear-gradient(135deg,#0b4f9c,#0a6dcc);
    color:#fff; border-radius:10px; padding:12px 18px;
    margin:0 0 10px 0; box-shadow:0 2px 7px rgba(0,0,0,.12);
}
.lf-header-icon{font-size:38px;line-height:1}
.lf-header-title{font-size:24px;font-weight:800;line-height:1.2}
.lf-header-subtitle{font-size:13px;font-weight:600;margin-top:3px;opacity:.96}
.lf-header-right{margin-left:auto;text-align:right;font-size:12px;line-height:1.45}
.lf-header-right span{opacity:.9}
.lf-filter-title{font-size:18px;font-weight:800;color:#0b4f9c;margin:2px 0 2px}
.lf-kpi-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;margin:7px 0 10px}
.lf-kpi{background:#fff;border:1px solid #d8e7f4;border-radius:7px;padding:8px 9px;min-height:76px;box-shadow:0 1px 4px rgba(0,60,120,.08);position:relative;overflow:hidden}
.lf-kpi-icon{position:absolute;left:8px;top:8px;font-size:25px;color:#0b4f9c}
.lf-kpi-label{margin-left:34px;color:#0754a1;font-size:11px;font-weight:700;line-height:1.25;min-height:27px}
.lf-kpi-value{color:#0754a1;font-size:23px;font-weight:800;line-height:1.05;margin-top:2px;white-space:nowrap}
.lf-kpi-unit{color:#0754a1;font-size:11px;font-weight:600;line-height:1.1}
.lf-panel-title{color:#0754a1}
@media (max-width:1200px){.lf-kpi-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.lf-header-right{display:none}.lf-header-title{font-size:20px}}
@media (max-width:800px){.lf-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.lf-header-title{font-size:18px}}

/* Header spacing */
h2 {
    margin-bottom: 18px !important;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# LOAD FACTOR HELPERS
# =========================================================

def _normalize_profit_col_name(value):
    return "".join(str(value).strip().lower().replace("_", " ").split())


VEHICLE_PERF_ALIASES = {
    "date": [
        "Travel Req. Date",
        "วันที่",
        "Date",
        "วันที่เดินทาง",
    ],
    "year": [
        "Year",
        "ปี",
    ],
    "vehicle_type": [
        "Vehicle Model",
        "ชนิดรถ",
        "Vehicle Type",
        "ชนิดรถ",
        "Truck Type",
    ],
    "vehicle_id": [
        "License Plate",
        "ทะเบียนรถ",
        "ทะเบียน",
        "Vehicle No",
    ],
    "branch": [
        "Branch",
        "สาขา",
        "ต้นทาง",
        "Loading",
    ],
    "route": [
        "Route",
        "เส้นทาง",
        "รวมเส้นทาง",
    ],
    "total_cost": [
        "Total Cost",
        "ต้นทุนรวม",
        "รวมต้นทุน",
        "Total Transportation Cost",
    ],
    "load_factor": [
        "Load Factor",
        "Load Factor %",
        "Loadfactor",
        "Loadfactor %",
        "% Load Factor",
        "Average Loadfactor",
        "Average Load Factor",
        "Load Factor%",
        "LF",
        "LF%",
    ],
    "load_factor_weight": [
        "Load Factor Weight",
        "Load Factor by Weight",
        "Load Factor น้ำหนัก",
        "% Load Factor น้ำหนัก",
        "Load Factor Weight %",
        "LF Weight",
    ],
    "load_factor_volume": [
        "Load Factor Volume",
        "Load Factor by Volume",
        "Load Factor ปริมาตร",
        "% Load Factor ปริมาตร",
        "Load Factor Volume %",
        "LF Volume",
    ],
    "ton_km": [
        "Ton-km",
        "Ton Km",
        "TonKM",
        "Ton_Km",
        "ตัน-กม.",
        "ตัน กม.",
        "Ton-kilometer",
    ],
    "cost_per_ton_km": [
        "Cost per Ton-km",
        "Cost per Ton-Km",
        "Cost/Ton-km",
        "Cost / Ton-km",
        "Cost per Ton Km",
        "Cost per ton km",
        "ต้นทุนต่อตัน-กม.",
        "ต้นทุนต่อตัน กม.",
        "ต้นทุนต่อ Ton-km",
    ],
    "distance": [
        "Distance",
        "ระยะทาง",
        "ระยะทางรวม",
        "Distance (km)",
        "KM",
    ],
}


def _vehicle_find_column(
    columns,
    alias_group,
):
    normalized = {
        _normalize_profit_col_name(c): c
        for c in columns
    }

    aliases = [
        _normalize_profit_col_name(a)
        for a in VEHICLE_PERF_ALIASES[
            alias_group
        ]
    ]

    for alias in aliases:
        if alias in normalized:
            return normalized[alias]

    for alias in aliases:
        if len(alias) < 3:
            continue

        for norm_col, original in normalized.items():
            if (
                alias in norm_col
                or norm_col in alias
            ):
                return original

    return None


def _vehicle_mapping(
    df,
):
    cols = list(
        df.columns
    )

    return {
        key: _vehicle_find_column(
            cols,
            key,
        )
        for key in VEHICLE_PERF_ALIASES
    }


@st.cache_data(show_spinner=False)
def load_vehicle_performance_files(folder_signature):
    """
    LOAD FACTOR SOURCE LOCK
    -----------------------
    หน้านี้อ่านข้อมูลจากไฟล์
    `ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่.xlsx` เท่านั้น
    ห้าม fallback ไปอ่าน Excel ไฟล์อื่นเด็ดขาด

    ถ้าระบบอัปโหลดแล้วเติม _2 / _3 ต่อท้ายชื่อไฟล์ จะเลือกไฟล์ชื่อเดียวกัน
    ที่แก้ไขล่าสุด แต่ยังต้องมีชื่อฐาน `ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่`
    อยู่ในชื่อไฟล์เสมอ
    """
    import re

    # LOAD FACTOR SOURCE ISOLATION: ห้ามใช้ Cost/Excel อื่น
    TARGET = "ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่"

    def norm(v):
        return re.sub(r"[\s_\-]+", "", str(v).strip().casefold())

    target_norm = norm(TARGET)

    # สำคัญ: จำกัดไฟล์ตั้งแต่ตรงนี้เลย ไม่อ่าน cost dashboard หรือไฟล์อื่น
    source_files = []
    if DATA_FOLDER.exists():
        for f in DATA_FOLDER.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
                continue
            if f.name.startswith("~$"):
                continue
            if target_norm in norm(f.stem):
                source_files.append(f)

    if not source_files:
        return pd.DataFrame(), []

    source_files.sort(key=lambda x: x.stat().st_mtime_ns, reverse=True)
    file = source_files[0]

    try:
        excel = pd.ExcelFile(file)
    except Exception:
        return pd.DataFrame(), []

    # เลือกชีตที่เป็น Load Factor ภายในไฟล์นี้เท่านั้น
    # ไม่สนใจชื่อชีตตายตัว เพื่อรองรับ Load Factor_Data / Load Factor_Dataปรับชื่อ
    def sheet_score(sheet):
        n = norm(sheet)
        score = 0
        if "loadfactor" in n:
            score += 100
        if "tripweightloadfactor" in n:
            score += 30
        if "data" in n:
            score += 10
        return score

    sheets = sorted(excel.sheet_names, key=sheet_score, reverse=True)
    matched_sheet = sheets[0] if sheets and sheet_score(sheets[0]) > 0 else None

    # ถ้าชื่อชีตไม่บอกว่า Load Factor ให้เลือกชีตที่มีคอลัมน์ Load Factor มากที่สุด
    if matched_sheet is None:
        best_score = -1
        for sh in excel.sheet_names:
            try:
                sample = pd.read_excel(file, sheet_name=sh, nrows=5)
                score = sum(
                    1 for c in sample.columns
                    if any(k in norm(c) for k in ["loadfactor", "weight", "capacity"])
                )
                if score > best_score:
                    best_score = score
                    matched_sheet = sh
            except Exception:
                continue

    if matched_sheet is None:
        return pd.DataFrame(), []

    try:
        df = pd.read_excel(file, sheet_name=matched_sheet)
    except Exception:
        return pd.DataFrame(), []

    df.columns = [" ".join(str(c).strip().split()) for c in df.columns]

    def find_col(aliases, required=False):
        # exact normalized match first
        lookup = {norm(c): c for c in df.columns}
        for a in aliases:
            if norm(a) in lookup:
                return lookup[norm(a)]
        # partial match second
        for a in aliases:
            na = norm(a)
            for c in df.columns:
                nc = norm(c)
                if na and (na in nc or nc in na):
                    return c
        return None

    # Map คอลัมน์จากไฟล์ต้นทางให้เป็นชื่อกลางของ Dashboard
    aliases = {
        "Trip Key Unique": [
            "Trip Key Unique", "Trip Key", "Manifest No.", "Manifest No", "เลขที่ใบงาน",
            "เลขที่เที่ยว", "Travel Req. No.", "Travel Req No", "Trip No.", "Trip No"
        ],
        "Trip Date": [
            "Trip Date", "Disbursement Date", "Travel Req. Date", "วันที่เดินทาง", "วันที่", "Date"
        ],
        "Trip Year": ["Trip Year", "Year", "ปี"],
        "Trip Vehicle Model": [
            "Trip Vehicle Model", "Vehicle Model", "Vehicle Type", "ชนิดรถ", "Truck Type"
        ],
        "Trip Loading": ["Trip Loading", "Loading", "ต้นทาง", "จุดขึ้น"],
        "Trip Unloading": ["Trip Unloading", "Unloading", "ปลายทาง", "จุดลง"],
        "Trip Direction": ["Trip Direction", "Direction", "ทิศทาง"],
        "Route Key": ["Route Key", "Route", "เส้นทาง", "รวมเส้นทาง"],
        "Trip Weight": [
            "Trip Weight", "Weight", "น้ำหนัก", "น้ำหนักรวม", "น้ำหนักสินค้า", "Total Weight",
            "Weight (kg)", "น้ำหนัก (กก.)"
        ],
        "Trip Weight Capacity": [
            "Trip Weight Capacity", "Weight Capacity", "Capacity", "ความจุ", "น้ำหนักที่บรรทุกได้",
            "น้ำหนักบรรทุกสูงสุด", "Capacity (kg)", "น้ำหนัก Capacity"
        ],
        "Trip Volume": ["Trip Volume", "Volume", "ปริมาตร", "ปริมาตรรวม", "ปริมาตรสินค้า", "Total Volume", "Volume (cu.m.)", "Volume (m3)", "CBM", "ลูกบาศก์เมตร"],
        "Trip Volume Capacity": ["Trip Volume Capacity", "Volume Capacity", "Capacity Volume", "ความจุปริมาตร", "ปริมาตรที่บรรทุกได้", "Volume Capacity (m3)", "Capacity (cu.m.)", "Capacity (CBM)"],
        "Trip Weight Loadfactor": [
            "Trip Weight Loadfactor", "Trip Weight Load Factor", "Load Factor", "Loadfactor",
            "Load Factor %", "Loadfactor %", "% Load Factor", "LF", "LF%"
        ],
        "Trip Weight Loadfactor Group check": [
            "Trip Weight Loadfactor Group check", "Load Factor Group", "Loadfactor Group",
            "กลุ่ม Load Factor"
        ],
        "Trip Weight Status": ["Trip Weight Status", "Weight Status", "สถานะน้ำหนัก", "Status"],
    }

    mapped = {k: find_col(v) for k, v in aliases.items()}

    # คอลัมน์เสริม: เทียบชื่อแบบตรงตัวเท่านั้น (ไม่เดาจากชื่อบางส่วน กันหยิบผิดคอลัมน์)
    exact_extra = {
        "Trip Volume Loadfactor": ["Trip Volume Loadfactor", "Trip Volume Load Factor"],
        "License Plate": ["License Plate", "Trip License Plate", "ทะเบียนรถ"],
        "Customer": ["Customer", "Trip Customer", "ลูกค้า"],
        # สำหรับ Ton-km / Cost per ton-km และตารางรายเที่ยว
        "Trip Run Type": ["Trip Run Type", "เที่ยววิ่ง", "Run Type"],
        "Trip Distance": ["Trip Distance", "Distance", "Total Distance", "ระยะทาง",
                          "Distance (km)", "ระยะทาง (กม.)", "KM"],
        "Trip Total Cost": ["Trip Total Cost", "Total Cost", "ต้นทุนรวม", "รวมต้นทุน", "Trip Cost"],
        "Trip Ton-km": ["Trip Ton-km", "Ton-km", "Ton km", "Tonkm", "Ton-KM", "Ton.km", "Ton*km",
                        "ตัน-กม.", "ตัน-กม", "ตันกม", "ตัน-กิโลเมตร"],
        "Trip Cost per Ton-km": ["Trip Cost per Ton-km", "Cost per ton-km", "Cost per Ton km",
                                 "Cost/ton-km", "Cost/Ton km", "Cost/Ton/KM", "Cost/Ton-Km",
                                 "Cost per ton km", "Cost/tkm", "ต้นทุนต่อตัน-กม.", "ต้นทุนต่อตัน-กม",
                                 "ต้นทุน/ตัน-กม.", "ต้นทุน/ตัน/กม."],
        "Trip Product Type": ["Trip Product Type", "Product Type", "ประเภทสินค้า", "Goods Type",
                              "Product Group", "กลุ่มสินค้า", "Commodity", "Product",
                              "Product Type Clean"],
    }
    norm_lookup = {norm(c): c for c in df.columns}
    for canonical, names in exact_extra.items():
        hit = next((norm_lookup[norm(n)] for n in names if norm(n) in norm_lookup), None)
        if hit is not None and canonical not in mapped:
            mapped[canonical] = hit

    # สร้างคอลัมน์กลางจากไฟล์ต้นทางเท่านั้น
    out = pd.DataFrame(index=df.index)
    for canonical, source_col in mapped.items():
        if source_col is not None:
            out[canonical] = df[source_col]

    # Trip Key: ถ้าไม่มีคอลัมน์เฉพาะ ให้ใช้เลข Manifest จากไฟล์ต้นทาง
    # ถ้าไม่มีจริง ๆ ใช้ index เป็น key ของแถวต้นทาง ไม่สร้างข้อมูลจากไฟล์อื่น
    if "Trip Key Unique" not in out:
        out["Trip Key Unique"] = pd.Series(df.index.astype(str), index=df.index)

    # Date / Year
    if "Trip Date" not in out:
        out["Trip Date"] = pd.NaT
    parsed_date = pd.to_datetime(out["Trip Date"], errors="coerce", dayfirst=True)
    out["Trip Date"] = parsed_date
    if "Trip Year" not in out:
        out["Trip Year"] = parsed_date.dt.year.astype("Int64").astype("string")
    else:
        out["Trip Year"] = out["Trip Year"].astype("string").str.strip()
        missing_year = out["Trip Year"].isna() | out["Trip Year"].eq("")
        out.loc[missing_year, "Trip Year"] = parsed_date.loc[missing_year].dt.year.astype("Int64").astype("string")

    # Loading / Unloading
    for c in ["Trip Loading", "Trip Unloading"]:
        if c not in out:
            out[c] = ""
        out[c] = out[c].astype("string").str.strip()

    # Direction / Route สร้างจากคอลัมน์ในไฟล์เดียวกันเท่านั้น
    if "Trip Direction" not in out:
        out["Trip Direction"] = (
            out["Trip Loading"].fillna("").astype(str).str.strip()
            + " → "
            + out["Trip Unloading"].fillna("").astype(str).str.strip()
        ).str.strip(" →")
    if "Route Key" not in out:
        out["Route Key"] = (
            out["Trip Loading"].fillna("").astype(str).str.strip()
            + " ↔ "
            + out["Trip Unloading"].fillna("").astype(str).str.strip()
        ).str.strip(" ↔")

    # Vehicle
    if "Trip Vehicle Model" not in out:
        out["Trip Vehicle Model"] = "ไม่ระบุ"

    # Weight / Capacity
    for c in ["Trip Weight", "Trip Weight Capacity"]:
        if c not in out:
            out[c] = pd.NA
        out[c] = pd.to_numeric(out[c], errors="coerce")

    # Load Factor: ใช้ค่าที่อยู่ในไฟล์ต้นทางก่อน
    # ถ้าไฟล์ไม่มีคอลัมน์ LF แต่มี Weight + Capacity ให้คำนวณจากสองคอลัมน์ในไฟล์เดียวกัน
    if "Trip Weight Loadfactor" not in out:
        cap = out["Trip Weight Capacity"]
        wt = out["Trip Weight"]
        out["Trip Weight Loadfactor"] = wt.div(cap.where(cap.ne(0)))

    out["Trip Weight Loadfactor"] = pd.to_numeric(
        out["Trip Weight Loadfactor"], errors="coerce"
    )

    # Group check: ถ้าไม่มีใน source ให้สร้างจาก LF ใน source เดียวกัน
    if "Trip Weight Loadfactor Group check" not in out:
        lf = _lf_numeric_ratio(out["Trip Weight Loadfactor"])
        def group(v):
            if pd.isna(v): return "ไม่ระบุ"
            pct = float(v) * 100
            if pct == 0: return "0%"
            if pct <= 100: return ">0–100%"
            if pct <= 150: return "100–150%"
            if pct <= 200: return "150–200%"
            return ">200%"
        out["Trip Weight Loadfactor Group check"] = lf.map(group)

    # Status: ใช้ source ถ้ามี; ถ้าไม่มีให้ derive จาก Weight/LF ในไฟล์เดียวกัน
    if "Trip Weight Status" not in out:
        out["Trip Weight Status"] = "OK"
        out.loc[out["Trip Weight"].isna(), "Trip Weight Status"] = "Missing Weight"
        ratio = _lf_numeric_ratio(out["Trip Weight Loadfactor"])
        out.loc[ratio > 2, "Trip Weight Status"] = "Outlier"

    out["_source_file"] = file.name
    out["_source_sheet"] = matched_sheet

    return out.copy(), [f"{file.name} • {matched_sheet}"]


def _lf_numeric_ratio(series):
    """แปลง Trip Weight Loadfactor ให้เป็น ratio (เช่น 0.68 = 68%)."""
    s = pd.to_numeric(series, errors="coerce").astype("Float64")
    valid = s.dropna().abs()
    if valid.empty:
        return s

    # Dataset หลักจาก Excel ใช้ค่าแบบ ratio (1.00 = 100%).
    # เผื่อกรณีอ่านไฟล์ที่เก็บเป็น 68 แทน 0.68 ให้ normalize เป็น ratio.
    q50 = float(valid.quantile(0.50))
    q90 = float(valid.quantile(0.90))
    if q50 > 3 or q90 > 10:
        s = s / 100.0
    return s


def _lf_safe_ratio(weight, capacity):
    w = pd.to_numeric(weight, errors="coerce").fillna(0).sum()
    c = pd.to_numeric(capacity, errors="coerce").fillna(0).sum()
    return (w / c) if c not in (0, 0.0) else float("nan")


def _lf_format_int(value):
    try:
        return f"{int(round(float(value))):,}"
    except Exception:
        return "—"


def _lf_format_pct(value):
    try:
        if pd.isna(value):
            return "—"
        return f"{float(value) * 100:,.1f}%"
    except Exception:
        return "—"


def render_vehicle_performance_dashboard(raw_vehicle_df, source_labels=None):
    """Load Factor Dashboard: new reference layout, using only the locked Load Factor source."""
    required=["Trip Key Unique","Trip Date","Trip Year","Trip Vehicle Model","Trip Loading","Trip Unloading","Route Key","Trip Weight","Trip Weight Capacity"]
    if raw_vehicle_df.empty:
        st.info("ยังไม่มีข้อมูล Load Factor — ไปที่ Data Management แล้วอัปโหลด `ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่.xlsx`")
        return
    df=raw_vehicle_df.copy()
    df.columns=[" ".join(str(c).strip().split()) for c in df.columns]
    missing=[c for c in required if c not in df.columns]
    if missing:
        st.error("ไฟล์ Load Factor ขาดคอลัมน์ที่จำเป็น: "+", ".join(missing)); return
    months={1:"ม.ค.",2:"ก.พ.",3:"มี.ค.",4:"เม.ย.",5:"พ.ค.",6:"มิ.ย.",7:"ก.ค.",8:"ส.ค.",9:"ก.ย.",10:"ต.ค.",11:"พ.ย.",12:"ธ.ค."}
    df["_TripDate"]=pd.to_datetime(df["Trip Date"],errors="coerce",dayfirst=True)
    df["_MonthNum"]=df["_TripDate"].dt.month
    def num(x):
        return pd.to_numeric(x.astype("string").str.replace(",","",regex=False).str.replace("%","",regex=False),errors="coerce")
    df["_Weight"]=num(df["Trip Weight"]); df["_Capacity"]=num(df["Trip Weight Capacity"])
    df["_Volume"]=num(df["Trip Volume"]) if "Trip Volume" in df.columns else pd.Series(pd.NA,index=df.index,dtype="Float64")
    df["_VolumeCapacity"]=num(df["Trip Volume Capacity"]) if "Trip Volume Capacity" in df.columns else pd.Series(pd.NA,index=df.index,dtype="Float64")
    if "Trip Weight Loadfactor" in df.columns:
        df["_WeightLF"]=num(df["Trip Weight Loadfactor"])
        if len(df["_WeightLF"].dropna()) and df["_WeightLF"].dropna().gt(1).mean()>.5: df["_WeightLF"]/=100
    else: df["_WeightLF"]=df["_Weight"]/df["_Capacity"].replace(0,pd.NA)
    for c in ["Trip Year","Trip Vehicle Model","Trip Loading","Trip Unloading","Route Key","Trip Key Unique"]:
        df[c]=df[c].astype("string").fillna("").str.strip()
    df["_RouteDisplay"]=df["Route Key"]
    blank=df["_RouteDisplay"].eq("")
    df.loc[blank,"_RouteDisplay"]=(df.loc[blank,"Trip Loading"].astype(str)+" - "+df.loc[blank,"Trip Unloading"].astype(str)).str.strip(" -")
    trip_df=df[df["Trip Key Unique"].ne("")].copy()

    st.markdown("""
    <div class="lf-new-header"><div class="lf-header-icon">🚚</div><div><div class="lf-header-title">แดชบอร์ดการใช้ความสามารถในการบรรทุกของรถขนส่ง</div><div class="lf-header-subtitle">วิเคราะห์การใช้ความสามารถในการบรรทุก (น้ำหนัก และ ปริมาตร)</div></div><div class="lf-header-right"><b>“ใช้ข้อมูลจริง เพื่อการจัดรถที่คุ้มค่า”</b><br><span>Load Factor Dashboard</span></div></div>
    """,unsafe_allow_html=True)
    st.markdown("<div class='lf-filter-title'>ตัวกรองข้อมูล</div>",unsafe_allow_html=True)
    f1,f2,f3,f4,f5=st.columns([.9,1.25,1.25,2.4,.75])
    def opts(c): return ["ทั้งหมด"]+sorted({str(x).strip() for x in trip_df[c].dropna() if str(x).strip() not in {"","<NA>","nan"}})
    with f1: year=st.selectbox("ปี (พ.ศ.)",opts("Trip Year"),key="lf2_year")
    with f2: vehicle=st.selectbox("ชนิดรถ",opts("Trip Vehicle Model"),key="lf2_vehicle")
    with f3: route=st.selectbox("เส้นทาง (ต้นทาง - ปลายทาง)",opts("_RouteDisplay"),key="lf2_route")
    with f4: search=st.text_input("ค้นหา (รถ, เส้นทาง, ทะเบียน, ลูกค้า, เลขที่เที่ยว)",key="lf2_search",placeholder="ค้นหา...")
    with f5:
        st.write(""); st.write("")
        if st.button("⟳ รีเฟรชข้อมูล",key="lf2_refresh",use_container_width=True): st.cache_data.clear(); st.rerun()
    filtered=trip_df.copy()
    if year!="ทั้งหมด": filtered=filtered[filtered["Trip Year"]==year]
    if vehicle!="ทั้งหมด": filtered=filtered[filtered["Trip Vehicle Model"]==vehicle]
    if route!="ทั้งหมด": filtered=filtered[filtered["_RouteDisplay"]==route]
    if search.strip():
        q=search.strip().casefold(); cols=[c for c in ["Trip Vehicle Model","_RouteDisplay","Trip Loading","Trip Unloading","Trip Key Unique","License Plate","Customer","Trip Customer"] if c in filtered.columns]
        mask=pd.Series(False,index=filtered.index)
        for c in cols: mask|=filtered[c].astype(str).str.casefold().str.contains(q,na=False,regex=False)
        filtered=filtered[mask]
    trips=filtered["Trip Key Unique"].nunique(); weight=filtered["_Weight"].sum(); wcap=filtered["_Capacity"].sum(); wlf=_lf_safe_ratio(filtered["_Weight"],filtered["_Capacity"])
    volume=filtered["_Volume"].sum() if filtered["_Volume"].notna().any() else None; vcap=filtered["_VolumeCapacity"].sum() if filtered["_VolumeCapacity"].notna().any() else None; vlf=_lf_safe_ratio(filtered["_Volume"],filtered["_VolumeCapacity"]) if volume is not None and vcap is not None else None
    def card(icon,label,value,unit):
        if value is None or pd.isna(value): val="—"
        elif isinstance(value,float): val=f"{value:,.2f}"
        else: val=f"{int(value):,}"
        return '<div class="lf-kpi"><div class="lf-kpi-icon">'+icon+'</div><div class="lf-kpi-label">'+label+'</div><div class="lf-kpi-value">'+val+'</div><div class="lf-kpi-unit">'+unit+'</div></div>'
    cards=[card("🚚","จำนวนเที่ยวทั้งหมด",trips,"เที่ยว"),card("⚖️","น้ำหนักรวม",weight,"กิโลกรัม"),card("📦","ปริมาตรรวม",volume,"ลูกบาศก์เมตร"),card("⚖️","ความสามารถบรรทุกน้ำหนักรวม",wcap,"กิโลกรัม"),card("📦","ความสามารถบรรทุกปริมาตรรวม",vcap,"ลูกบาศก์เมตร"),card("◔","อัตราการใช้ความจุ (น้ำหนัก)",wlf*100 if wlf is not None else None,"%"),card("◔","อัตราการใช้ความจุ (ปริมาตร)",vlf*100 if vlf is not None else None,"%")]
    st.markdown('<div class="lf-kpi-grid">'+''.join(cards)+'</div>',unsafe_allow_html=True)
    def group(v):
        if pd.isna(v): return "ไม่ระบุ"
        p=float(v)*100
        return "0 – 40%" if p<=40 else ">40 – 70%" if p<=70 else ">70 – 100%" if p<=100 else ">100 – 150%" if p<=150 else ">150%"
    filtered["_LFGroup"]=filtered["_WeightLF"].map(group); order=["0 – 40%",">40 – 70%",">70 – 100%",">100 – 150%",">150%"]
    dist=filtered.groupby("_LFGroup")["Trip Key Unique"].nunique().reindex(order,fill_value=0).reset_index(name="จำนวนเที่ยว"); total=dist["จำนวนเที่ยว"].sum(); dist["pct"]=dist["จำนวนเที่ยว"]/total*100 if total else 0
    status_map={order[0]:"ใช้ความจุต่ำ",order[1]:"ใช้ความจุปานกลาง",order[2]:"ใช้ความจุสูง",order[3]:"เกินความสามารถบรรทุก",order[4]:"ผิดปกติ"}; status=dist.copy(); status["สถานะ"]=status["_LFGroup"].map(status_map)
    a,b,c=st.columns([1.35,1.0,1.15], gap="small")
    with a:
        with st.container(border=True):
            st.markdown("### การกระจายของอัตราการใช้ความจุ (รายเที่ยว)")
            fig=px.bar(dist,x="_LFGroup",y="จำนวนเที่ยว",text=dist.apply(lambda r:f"{int(r['จำนวนเที่ยว']):,}<br>({r['pct']:.1f}%)",axis=1)); fig.update_traces(textposition="outside",cliponaxis=False); fig.update_layout(height=350,margin=dict(l=20,r=15,t=15,b=30),xaxis_title="อัตราการใช้ความจุ (น้ำหนัก) (%)",yaxis_title="จำนวนเที่ยว",showlegend=False); st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})
    with b:
        with st.container(border=True):
            st.markdown("### คำอธิบายช่วงอัตราการใช้ความจุ")
            expl=pd.DataFrame({"ช่วงอัตราการใช้ความจุ":order,"ความหมาย":["ใช้ความจุต่ำ (น้ำหนักบรรทุกน้อย)","ใช้ความจุปานกลาง (เริ่มมีการใช้ความจุ)","ใช้ความจุสูง (ใช้ความจุค่อนข้างมาก)","เกินความสามารถบรรทุก (ควรตรวจสอบข้อมูล/การปฏิบัติงาน)","ผิดปกติ / ควรตรวจสอบข้อมูล"]}); st.dataframe(expl,hide_index=True,use_container_width=True,height=285); st.info("หมายเหตุ: คำอธิบายแสดงตามตัวชี้วัดที่เลือก (น้ำหนัก)")
    with c:
        with st.container(border=True):
            st.markdown("### สัดส่วนกลุ่มการใช้งาน (รายเที่ยว)"); pie=px.pie(status,names="สถานะ",values="จำนวนเที่ยว",hole=.58); pie.update_traces(textposition="outside",textinfo="percent"); pie.update_layout(height=350,margin=dict(l=5,r=5,t=15,b=5),showlegend=True); st.plotly_chart(pie,use_container_width=True,config={"displayModeBar":False})
    d1,d2,d3=st.columns([1,1,1.35], gap="small")
    with d1:
        with st.container(border=True):
            st.markdown("### 10 อันดับ ชนิดรถ (เรียงตามจำนวนเที่ยว)"); vv=filtered.groupby("Trip Vehicle Model")["Trip Key Unique"].nunique().sort_values(ascending=False).head(10).reset_index(name="จำนวนเที่ยว"); st.dataframe(vv,hide_index=True,use_container_width=True,height=280)
    with d2:
        with st.container(border=True):
            st.markdown("### 10 อันดับ เส้นทาง (เรียงตามจำนวนเที่ยว)"); rr=filtered.groupby("_RouteDisplay")["Trip Key Unique"].nunique().sort_values(ascending=False).head(10).reset_index(name="จำนวนเที่ยว").rename(columns={"_RouteDisplay":"เส้นทาง (ต้นทาง - ปลายทาง)"}); st.dataframe(rr,hide_index=True,use_container_width=True,height=280)
    with d3:
        with st.container(border=True):
            st.markdown("### รายการเที่ยว (เลือกกลุ่มเพื่อดูรายละเอียด)")
            tabs=st.tabs(["ทั้งหมด","ใช้ความจุต่ำ","ใช้ความจุปานกลาง","ใช้ความจุสูง","เกินความสามารถบรรทุก","ผิดปกติ"]); groups=[None]+order
            cols=[c for c in ["Trip Date","Trip Key Unique","_RouteDisplay","Trip Vehicle Model","_WeightLF"] if c in filtered.columns]
            for tab,g in zip(tabs,groups):
                with tab:
                    x=filtered if g is None else filtered[filtered["_LFGroup"]==g]; show=x[cols].head(10).copy(); show["_WeightLF"]=show["_WeightLF"]*100; show=show.rename(columns={"Trip Date":"วันที่","Trip Key Unique":"เลขที่เที่ยว","_RouteDisplay":"เส้นทาง (ต้นทาง - ปลายทาง)","Trip Vehicle Model":"ชนิดรถ","_WeightLF":"อัตรา (น้ำหนัก)"}); st.dataframe(show,hide_index=True,use_container_width=True,height=210)
    st.caption("Source (Load Factor only): "+(" | ".join(source_labels) if source_labels else "ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่.xlsx"))

def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def existing_hashes():
    result = {}
    for file in DATA_FOLDER.glob("*.xlsx"):
        if file.name.startswith("~$"):
            continue
        try:
            result[file_hash(file.read_bytes())] = file.name
        except Exception:
            pass
    return result


def _lf_file_signature():
    """ลายเซ็นเฉพาะไฟล์ Load Factor (ชื่อ + เวลาแก้ไข + ขนาด)
    ใช้เป็น key ของ cache: ไฟล์อื่นเปลี่ยน จะไม่ทำให้ต้องอ่านไฟล์ Load Factor ใหม่"""
    target = "".join("ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่".split()).casefold()
    items = []
    for f in DATA_FOLDER.glob("*.xls*"):
        if f.name.startswith("~$"):
            continue
        if target in re.sub(r"[\s_\-]+", "", f.stem.casefold()):
            try:
                stat = f.stat()
                items.append((f.name, stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                continue
    return tuple(sorted(items))


def get_data_folder_signature():
    """
    ตรวจทุกไฟล์ Excel ในโฟลเดอร์ data
    ถ้ามีการเพิ่ม / ลบ / แก้ไขไฟล์ signature จะเปลี่ยน
    """
    items = []

    for file in sorted(
        [
            f
            for f in DATA_FOLDER.glob("*.xlsx")
            if not f.name.startswith("~$")
        ],
        key=lambda p: p.name.lower(),
    ):
        try:
            stat = file.stat()
            items.append(
                (
                    file.name,
                    stat.st_mtime_ns,
                    stat.st_size,
                )
            )
        except FileNotFoundError:
            # ไฟล์อาจกำลังถูก Excel เขียนใหม่พอดี
            continue

    return tuple(items)


def sync_signature_baseline():
    """
    เรียกหลัง Upload / Update / Delete ที่เราเป็นคนสั่งเอง
    เพื่อไม่ให้ตัว Auto Sync rebuild ซ้ำอีกรอบ
    """
    st.session_state[
        "_data_folder_signature"
    ] = get_data_folder_signature()


def auto_sync_data_folder():
    """
    ตรวจทั้งโฟลเดอร์ data
    เมื่อไฟล์ Excel เดิมถูก Save หรือมีไฟล์เพิ่ม/ลบจาก Explorer
    จะ rebuild DuckDB อัตโนมัติ
    """
    current_signature = get_data_folder_signature()

    previous_signature = st.session_state.get(
        "_data_folder_signature"
    )

    # ครั้งแรก: จำสถานะปัจจุบันไว้ก่อน
    if previous_signature is None:
        st.session_state[
            "_data_folder_signature"
        ] = current_signature
        return

    # ไม่มีอะไรเปลี่ยน
    if current_signature == previous_signature:
        return

    # อัปเดต signature ก่อน rerun เพื่อกัน loop
    st.session_state[
        "_data_folder_signature"
    ] = current_signature

    try:
        rebuild_database()
        st.cache_data.clear()

        st.session_state[
            "_auto_sync_message"
        ] = (
            "✅ ตรวจพบการเปลี่ยนแปลงไฟล์ Excel "
            "และอัปเดต Dashboard แล้ว"
        )

        st.rerun()

    except Exception as e:
        st.session_state[
            "_auto_sync_error"
        ] = str(e)


@st.cache_data(show_spinner=False)
def load_dashboard_data(db_mtime_ns: int) -> pd.DataFrame:
    if not DB_PATH.exists():
        try:
            rebuild_database()
        except Exception:
            return pd.DataFrame()

    def _read_trip_table():
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            # Prefer the stable joined view when it exists.
            try:
                return con.execute("SELECT * FROM trip_fuel").df()
            except Exception:
                return con.execute("SELECT * FROM trips").df()
        finally:
            con.close()

    try:
        return _read_trip_table()
    except Exception as first_error:
        # Self-heal after files were deleted/replaced:
        # rebuild the database from the CURRENT data/ folder, then retry.
        try:
            rebuild_database()
            return _read_trip_table()
        except Exception:
            # Keep the original failure context available to Streamlit logs,
            # but avoid a raw CatalogException on the page.
            print(f"Trip data reload failed: {first_error}")
            return pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_ar_data(db_mtime_ns: int) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()

    con = duckdb.connect(
        str(DB_PATH),
        read_only=True,
    )

    try:
        return con.execute(
            "SELECT * FROM ar_detail"
        ).df()
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()


@st.cache_data(show_spinner=False)
def load_ar_summary_data(db_mtime_ns: int) -> pd.DataFrame:
    """
    โหลดชีตสรุปลูกหนี้จาก Excel โดยตรง
    เพื่อใช้ค่า 'แบ่งชั้นลูกหนี้' ตามที่ไฟล์ต้นฉบับกำหนด
    """
    if not DB_PATH.exists():
        return pd.DataFrame()

    con = duckdb.connect(
        str(DB_PATH),
        read_only=True,
    )

    try:
        return con.execute(
            "SELECT * FROM ar_summary"
        ).df()
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()


def ar_numeric_series(
    df: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series(
            0.0,
            index=df.index,
            dtype=float,
        )

    cleaned = (
        df[column]
        .astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("฿", "", regex=False)
        .str.strip()
    )

    return pd.to_numeric(
        cleaned,
        errors="coerce",
    )


def ar_date_series(
    df: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series(
            pd.NaT,
            index=df.index,
            dtype="datetime64[ns]",
        )

    raw = df[column]

    # กรณี DuckDB เก็บเป็น datetime/string date อยู่แล้ว
    as_date = pd.to_datetime(
        raw,
        errors="coerce",
    )

    # กรณีเป็น Excel serial number เช่น 46031
    as_number = pd.to_numeric(
        raw,
        errors="coerce",
    )

    serial_date = pd.to_datetime(
        as_number,
        unit="D",
        origin="1899-12-30",
        errors="coerce",
    )

    return as_date.fillna(serial_date)


def prepare_ar_data(
    raw_df: pd.DataFrame,
) -> pd.DataFrame:
    ar = raw_df.copy()

    ar["_Amount"] = ar_numeric_series(
        ar,
        "จำนวนเงิน",
    ).fillna(0)

    ar["_InvoiceDate"] = ar_date_series(
        ar,
        "วันที่วางบิลได้",
    )

    ar["_PaymentDate"] = ar_date_series(
        ar,
        "วันที่จบ(วันที่จ่าย)",
    )

    ar["_DueDate"] = ar_date_series(
        ar,
        "วันครบกำหนด(Due Date)",
    )

    ar["_ReferenceDate"] = ar_date_series(
        ar,
        "วันที่ปัจจุบัน",
    )

    # ถ้าไฟล์ไม่มีวันที่อ้างอิง ให้ใช้วันที่ล่าสุดที่พบในชุดข้อมูล
    reference_candidates = ar[
        "_ReferenceDate"
    ].dropna()

    if not reference_candidates.empty:
        default_reference = reference_candidates.max()
    else:
        candidates = pd.concat(
            [
                ar["_InvoiceDate"],
                ar["_PaymentDate"],
                ar["_DueDate"],
            ]
        ).dropna()

        default_reference = (
            candidates.max()
            if not candidates.empty
            else pd.Timestamp.today().normalize()
        )

    ar["_ReferenceDate"] = ar[
        "_ReferenceDate"
    ].fillna(default_reference)

    ar["_Paid"] = ar[
        "_PaymentDate"
    ].notna()

    effective_date = ar[
        "_PaymentDate"
    ].where(
        ar["_Paid"],
        ar["_ReferenceDate"],
    )

    delay = (
        effective_date
        - ar["_DueDate"]
    ).dt.days

    ar["_DelayDays"] = (
        pd.to_numeric(
            delay,
            errors="coerce",
        )
        .fillna(0)
        .clip(lower=0)
    )

    ar["_Outstanding"] = ar[
        "_Amount"
    ].where(
        ~ar["_Paid"],
        0,
    )

    ar["_OverdueUnpaid"] = (
        (~ar["_Paid"])
        & (ar["_DelayDays"] > 0)
    )

    ar["_OverdueAmount"] = ar[
        "_Amount"
    ].where(
        ar["_OverdueUnpaid"],
        0,
    )

    def aging_bucket(row):
        if row["_Paid"]:
            return "ชำระแล้ว"

        days = row["_DelayDays"]

        if days <= 0:
            return "ยังไม่ครบกำหนด"
        if days <= 30:
            return "1-30 วัน"
        if days <= 60:
            return "31-60 วัน"
        if days <= 90:
            return "61-90 วัน"
        return "90+ วัน"

    ar["_Aging"] = ar.apply(
        aging_bucket,
        axis=1,
    )

    ar["_Branch"] = (
        ar.get(
            "สาขา",
            pd.Series("", index=ar.index),
        )
        .astype("string")
        .fillna("")
        .str.strip()
    )

    ar["_Debtor"] = (
        ar.get(
            "ชื่อลูกหนี้",
            pd.Series("", index=ar.index),
        )
        .astype("string")
        .fillna("")
        .str.strip()
    )

    ar["_InvoiceMonth"] = ar[
        "_InvoiceDate"
    ].dt.to_period("M").astype("string")

    return ar


def ar_customer_summary(
    ar: pd.DataFrame,
    source_summary: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    ใช้ค่าที่มีอยู่แล้วในชีต 'สรุปลูกหนี้' เป็นหลัก
    ไม่คำนวณ จำนวนบิล / บิลช้า / % บิลช้า / วันช้าสูงสุด /
    แบ่งชั้นลูกหนี้ ใหม่

    คำนวณเพิ่มเฉพาะ Outstanding AR และ Overdue AR
    จากรายละเอียด เพื่อให้เปลี่ยนตามตัวกรอง Dashboard ได้
    """
    if ar.empty:
        return pd.DataFrame()

    # ยอดคงค้าง/เกินกำหนดตามข้อมูลรายละเอียดปัจจุบัน
    amount_summary = (
        ar.groupby(
            "_Debtor",
            as_index=False,
            dropna=False,
        )
        .agg(
            Outstanding_AR=(
                "_Outstanding",
                "sum",
            ),
            Overdue_AR=(
                "_OverdueAmount",
                "sum",
            ),
        )
    )

    # ถ้ามีชีตสรุปลูกหนี้ ให้ใช้ค่าจากไฟล์โดยตรง
    if (
        source_summary is not None
        and not source_summary.empty
        and "ชื่อลูกหนี้" in source_summary.columns
    ):
        keep_cols = [
            c
            for c in [
                "ชื่อลูกหนี้",
                "จำนวนบิลทั้งหมด",
                "จำนวนบิลที่ช้า",
                "รวมวันช้า",
                "วันช้าสูงสุด",
                "เปอร์เซนต์บิลที่ช้า",
                "แบ่งชั้นลูกหนี้",
            ]
            if c in source_summary.columns
        ]

        src = source_summary[
            keep_cols
        ].copy()

        src["ชื่อลูกหนี้"] = (
            src["ชื่อลูกหนี้"]
            .astype("string")
            .fillna("")
            .str.strip()
        )

        src = (
            src[
                src["ชื่อลูกหนี้"] != ""
            ]
            .drop_duplicates(
                subset=["ชื่อลูกหนี้"],
                keep="last",
            )
            .rename(
                columns={
                    "ชื่อลูกหนี้": "_Debtor",
                    "จำนวนบิลทั้งหมด": "Total_Bills_Source",
                    "จำนวนบิลที่ช้า": "Late_Bills_Source",
                    "รวมวันช้า": "Total_Delay_Source",
                    "วันช้าสูงสุด": "Max_Delay_Source",
                    "เปอร์เซนต์บิลที่ช้า": "Late_Rate_Source",
                    "แบ่งชั้นลูกหนี้": "Customer_Class",
                }
            )
        )

        summary = amount_summary.merge(
            src,
            on="_Debtor",
            how="left",
        )

        if "Customer_Class" not in summary.columns:
            summary["Customer_Class"] = "ไม่ระบุ"

        summary["Customer_Class"] = (
            summary["Customer_Class"]
            .astype("string")
            .fillna("ไม่ระบุ")
            .str.strip()
            .replace("", "ไม่ระบุ")
        )

        return summary

    # ถ้าไม่มีชีตสรุปจริง ๆ จึงค่อยคืนเฉพาะยอด
    amount_summary["Customer_Class"] = "ไม่ระบุ"
    return amount_summary



def customer_class_display(val):
    """แสดงสีแบบที่ Streamlit dataframe เห็นแน่นอน"""
    if pd.isna(val):
        return ""

    val = str(val).strip()

    class_labels = {
        "ลูกหนี้ชั้นดี": "🟢 ลูกหนี้ชั้นดี",
        "ลูกหนี้เฝ้าติดตาม": "🟡 ลูกหนี้เฝ้าติดตาม",
        "ลูกหนี้ชั้นแย่": "🔴 ลูกหนี้ชั้นแย่",
    }

    return class_labels.get(val, val)


def color_customer_class(val):
    """
    สีสำหรับแบ่งชั้นลูกหนี้
    - ชั้นดี = เขียว
    - เฝ้าติดตาม = เหลือง/ส้ม
    - ชั้นแย่ = แดง
    """
    if pd.isna(val):
        return ""

    val = str(val).strip()

    if val == "ลูกหนี้ชั้นดี":
        return (
            "background-color: #E8F5E9; "
            "color: #1B5E20; "
            "font-weight: 700;"
        )

    if val == "ลูกหนี้เฝ้าติดตาม":
        return (
            "background-color: #FFF8E1; "
            "color: #E65100; "
            "font-weight: 700;"
        )

    if val == "ลูกหนี้ชั้นแย่":
        return (
            "background-color: #FFEBEE; "
            "color: #B71C1C; "
            "font-weight: 700;"
        )

    return ""


# =========================================================
# AR TABLE (HTML, โทนชมพู-ขาว)
# =========================================================

AR_TABLE_CSS = """<style>
.ar-table-wrap{overflow:auto;background:#fff;border:1px solid #F6DDE2;border-radius:14px;margin:6px 0 10px}
.ar-table{width:100%;border-collapse:separate;border-spacing:0;font-size:13.5px;margin:0!important}
.ar-table thead th{position:sticky;top:0;z-index:3;background:#FFF3F5;color:#475569;font-weight:700;font-size:12.5px;text-align:left;padding:11px 14px;border-bottom:1px solid #F6DDE2;white-space:nowrap}
.ar-table td{padding:10px 14px;border-bottom:1px solid #FBEFF1;color:#1E293B;white-space:nowrap}
.ar-table tbody tr:nth-child(even) td{background:#FFFBFC}
.ar-table tbody tr:hover td{background:#FFE8EC}
.ar-table .ar-num{text-align:right!important;font-variant-numeric:tabular-nums}
.ar-table .ar-over{color:#C23B53;font-weight:700}
.ar-table .ar-mono{font-family:ui-monospace,monospace;font-size:12px;color:#64748B;max-width:260px;overflow:hidden;text-overflow:ellipsis}
.ar-badge{display:inline-block;padding:3px 11px;border-radius:99px;font-size:12.5px;font-weight:700}
</style>"""

AR_CLASS_STYLE = {
    "ลูกหนี้ชั้นดี": ("#E8F5E9", "#1B5E20"),
    "ลูกหนี้เฝ้าติดตาม": ("#FFF3D6", "#B45309"),
    "ลูกหนี้ชั้นแย่": ("#FFE4E8", "#B71C1C"),
}


def ar_table_html(
    df,
    money_cols=(),
    pct_cols=(),
    day_cols=(),
    over_cols=(),
    class_col=None,
    max_height=360,
):
    """ตาราง HTML โทนชมพู-ขาว แทน st.dataframe (ซึ่งเปลี่ยนเป็นสีสว่างด้วย CSS ไม่ได้)"""
    num_cols = set(money_cols) | set(pct_cols) | set(day_cols)

    ths = "".join(
        f'<th class="{"ar-num" if c in num_cols else ""}">{esc(str(c))}</th>'
        for c in df.columns
    )

    rows = []
    for rec in df.to_dict("records"):
        tds = []
        for c in df.columns:
            v = rec[c]
            cls = "ar-num" if c in num_cols else ""
            if c in over_cols:
                cls += " ar-over"

            if pd.isna(v):
                txt = "—"
            elif c in money_cols:
                txt = f"฿{float(v):,.0f}"
            elif c in pct_cols:
                txt = f"{float(v) * 100:,.1f}%"
            elif c in day_cols:
                txt = f"{float(v):,.0f} วัน"
            elif c == class_col:
                bg, fg = AR_CLASS_STYLE.get(str(v).strip(), ("#F1F5F9", "#475569"))
                txt = (
                    f'<span class="ar-badge" style="background:{bg};color:{fg}">'
                    f"{esc(str(v))}</span>"
                )
            else:
                txt = esc(str(v))
                if c in ("ลูกหนี้", "ชื่อลูกหนี้") and len(str(v)) > 30:
                    cls += " ar-mono"

            tds.append(f'<td class="{cls.strip()}">{txt}</td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")

    return (
        f'<div class="ar-table-wrap" style="max-height:{max_height}px">'
        f'<table class="ar-table"><thead><tr>{ths}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def render_ar_dashboard(
    raw_ar: pd.DataFrame,
    raw_ar_summary: pd.DataFrame | None = None,
):
    """
    Executive AR & Collection Dashboard
    เป้าหมาย: เงินค้างเท่าไร -> เสี่ยงแค่ไหน -> อยู่ที่ใคร/สาขาไหน -> ต้องทำอะไรก่อน
    """
    ar = prepare_ar_data(raw_ar)

    # -----------------------------------------------------
    # CLASSIFICATION FROM SOURCE EXCEL
    # -----------------------------------------------------
    if (
        raw_ar_summary is not None
        and not raw_ar_summary.empty
        and "ชื่อลูกหนี้" in raw_ar_summary.columns
        and "แบ่งชั้นลูกหนี้" in raw_ar_summary.columns
    ):
        class_lookup = raw_ar_summary[
            ["ชื่อลูกหนี้", "แบ่งชั้นลูกหนี้"]
        ].copy()

        class_lookup["ชื่อลูกหนี้"] = (
            class_lookup["ชื่อลูกหนี้"]
            .astype("string")
            .fillna("")
            .str.strip()
        )
        class_lookup["แบ่งชั้นลูกหนี้"] = (
            class_lookup["แบ่งชั้นลูกหนี้"]
            .astype("string")
            .fillna("")
            .str.strip()
        )

        class_lookup = (
            class_lookup[class_lookup["ชื่อลูกหนี้"] != ""]
            .drop_duplicates(subset=["ชื่อลูกหนี้"], keep="last")
            .rename(
                columns={
                    "ชื่อลูกหนี้": "_Debtor",
                    "แบ่งชั้นลูกหนี้": "_CustomerClass",
                }
            )
        )

        ar = ar.merge(class_lookup, on="_Debtor", how="left")
    else:
        ar["_CustomerClass"] = "ไม่ระบุ"

    ar["_CustomerClass"] = (
        ar["_CustomerClass"]
        .astype("string")
        .fillna("ไม่ระบุ")
        .str.strip()
        .replace("", "ไม่ระบุ")
    )

    if ar.empty:
        st.warning("ยังไม่มีข้อมูลลูกหนี้สำหรับ Dashboard นี้")
        return

    THAI_MONTH_NAMES = {
        1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
        5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
        9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค.",
    }

    # -----------------------------------------------------
    # REFERENCE DATE
    # -----------------------------------------------------
    ref_dates = ar["_ReferenceDate"].dropna()

    if not ref_dates.empty:
        ref_date = ref_dates.max()
        thai_year = ref_date.year + 543 if ref_date.year < 2400 else ref_date.year

        st.caption(
            "ข้อมูลลูกหนี้อ้างอิงวันที่ "
            f"{ref_date.day} {THAI_MONTH_NAMES.get(ref_date.month, '')} {thai_year}"
        )

    # -----------------------------------------------------
    # FILTERS
    # -----------------------------------------------------
    st.markdown(
        '<div class="section-title">ตัวกรองข้อมูลลูกหนี้</div>',
        unsafe_allow_html=True,
    )

    filtered = ar.copy()

    f1, f2, f3, f4, f5 = st.columns(5)

    years = sorted(
        [int(y) for y in filtered["_InvoiceDate"].dt.year.dropna().unique()]
    )

    with f1:
        selected_year = st.selectbox(
            "ปีวางบิล",
            ["ทั้งหมด"] + [str(y + 543) for y in years],
            key="ar_year",
        )

    if selected_year != "ทั้งหมด":
        filtered = filtered[
            filtered["_InvoiceDate"].dt.year == int(selected_year) - 543
        ]

    month_options = sorted(
        [int(m) for m in filtered["_InvoiceDate"].dt.month.dropna().unique()]
    )

    with f2:
        selected_month = st.selectbox(
            "เดือนวางบิล",
            ["ทั้งหมด"] + [THAI_MONTH_NAMES[m] for m in month_options],
            key="ar_month",
        )

    if selected_month != "ทั้งหมด":
        month_num = next(
            m for m, label in THAI_MONTH_NAMES.items()
            if label == selected_month
        )
        filtered = filtered[
            filtered["_InvoiceDate"].dt.month == month_num
        ]

    branches = sorted(
        [
            x for x in filtered["_Branch"].dropna().astype(str).unique()
            if str(x).strip()
        ]
    )

    with f3:
        selected_branch = st.selectbox(
            "สาขา",
            ["ทั้งหมด"] + branches,
            key="ar_branch",
        )

    if selected_branch != "ทั้งหมด":
        filtered = filtered[filtered["_Branch"] == selected_branch]

    with f4:
        selected_status = st.selectbox(
            "สถานะการชำระ",
            ["ทั้งหมด", "ยังไม่ชำระ", "เกินกำหนด", "ชำระแล้ว"],
            key="ar_status",
        )

    if selected_status == "ยังไม่ชำระ":
        filtered = filtered[~filtered["_Paid"]]
    elif selected_status == "เกินกำหนด":
        filtered = filtered[filtered["_OverdueUnpaid"]]
    elif selected_status == "ชำระแล้ว":
        filtered = filtered[filtered["_Paid"]]

    class_order = [
        "ลูกหนี้ชั้นดี",
        "ลูกหนี้ชั้นแย่",
        "ลูกหนี้เฝ้าติดตาม",
    ]

    available_classes = [
        cls
        for cls in class_order
        if cls in set(filtered["_CustomerClass"].dropna().astype(str))
    ]

    with f5:
        selected_class = st.selectbox(
            "แบ่งชั้นลูกหนี้",
            ["ทั้งหมด"] + available_classes,
            key="ar_customer_class",
        )

    if selected_class != "ทั้งหมด":
        filtered = filtered[
            filtered["_CustomerClass"] == selected_class
        ]

    if filtered.empty:
        st.info("ไม่มีข้อมูลตามตัวกรองที่เลือก")
        return

    # -----------------------------------------------------
    # CUSTOMER SUMMARY
    # -----------------------------------------------------
    customer_summary = ar_customer_summary(
        filtered,
        raw_ar_summary,
    )

    # -----------------------------------------------------
    # EXECUTIVE KPIs
    # -----------------------------------------------------
    outstanding_ar = float(filtered["_Outstanding"].sum())
    overdue_ar = float(filtered["_OverdueAmount"].sum())

    overdue_pct = (
        overdue_ar / outstanding_ar
        if outstanding_ar > 0
        else 0
    )

    ar_90_plus = float(
        filtered.loc[
            (~filtered["_Paid"]) & (filtered["_DelayDays"] > 90),
            "_Outstanding",
        ].sum()
    )

    risky_customers = 0
    if not customer_summary.empty:
        risky_customers = int(
            customer_summary[
                customer_summary["Customer_Class"].isin(
                    ["ลูกหนี้ชั้นแย่", "ลูกหนี้เฝ้าติดตาม"]
                )
                & (customer_summary["Outstanding_AR"] > 0)
            ]["_Debtor"].nunique()
        )

    k1, k2, k3, k4, k5 = st.columns(5)

    k1.metric(
        "💰 ยอดลูกหนี้คงค้าง",
        fmt_money(outstanding_ar),
        help="ยอดเงินของบิลที่ยังไม่ได้รับชำระ",
    )
    k2.metric(
        "⚠️ Overdue AR",
        fmt_money(overdue_ar),
        help="ยอดที่ยังไม่ชำระและเลย Due Date แล้ว",
    )
    k3.metric(
        "📊 Overdue %",
        f"{overdue_pct:.1%}",
        help="Overdue AR ÷ Outstanding AR",
    )
    k4.metric(
        "⏳ ยอดค้างเกิน 90 วัน",
        fmt_money(ar_90_plus),
        help="ยอดคงค้างที่เลยกำหนดเกิน 90 วัน",
    )
    k5.metric(
        "🚨 ลูกหนี้เสี่ยง",
        f"{risky_customers:,} ราย",
        help="ลูกหนี้ชั้นแย่ + เฝ้าติดตาม ที่ยังมียอดคงค้าง",
    )

    # -----------------------------------------------------
    # ROW 1: AGING + AR BY CUSTOMER CLASS
    # -----------------------------------------------------
    row1_left, row1_right = st.columns([1, 1])

    with row1_left:
        with st.container(border=True):
            st.markdown("#### Aging ของยอดลูกหนี้คงค้าง")
            st.caption("ดูว่ายอดคงค้างอยู่ในช่วงอายุหนี้ใด")

            aging_order = [
                "ยังไม่ครบกำหนด",
                "1-30 วัน",
                "31-60 วัน",
                "61-90 วัน",
                "90+ วัน",
            ]

            aging = (
                filtered[~filtered["_Paid"]]
                .groupby("_Aging", as_index=False)["_Outstanding"]
                .sum()
            )

            aging["_Aging"] = pd.Categorical(
                aging["_Aging"],
                categories=aging_order,
                ordered=True,
            )

            aging = aging.sort_values("_Aging")

            if not aging.empty:
                fig = px.bar(
                    aging,
                    x="_Aging",
                    y="_Outstanding",
                    text="_Outstanding",
                )

                fig.update_traces(
                    texttemplate="฿%{y:,.0f}",
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(color="#334155", size=12),
                )

                fig.update_layout(
                    height=350,
                    margin=dict(l=15, r=25, t=20, b=45),
                    xaxis=dict(title="", tickfont=dict(color="#334155")),
                    yaxis=dict(
                        title="ยอดคงค้าง (บาท)",
                        tickformat=",.0f",
                        tickfont=dict(color="#334155"),
                        title_font=dict(color="#64748B"),
                    ),
                    paper_bgcolor="white",
                    plot_bgcolor="white",
                    showlegend=False,
                )

                st.plotly_chart(fig, width="stretch")
            else:
                st.info("ไม่มี Outstanding AR ตามตัวกรอง")

    with row1_right:
        with st.container(border=True):
            st.markdown("#### ยอดลูกหนี้คงค้างตามชั้นลูกหนี้")
            st.caption("ดูมูลค่าเงินค้าง แทนการดูเพียงจำนวนลูกค้า")

            class_value = (
                filtered[~filtered["_Paid"]]
                .groupby("_CustomerClass", as_index=False)["_Outstanding"]
                .sum()
            )

            class_order = [
                "ลูกหนี้ชั้นดี",
                "ลูกหนี้เฝ้าติดตาม",
                "ลูกหนี้ชั้นแย่",
            ]

            class_value["_CustomerClass"] = pd.Categorical(
                class_value["_CustomerClass"],
                categories=class_order,
                ordered=True,
            )

            class_value = (
                class_value[
                    class_value["_Outstanding"] > 0
                ]
                .sort_values("_CustomerClass")
            )

            if not class_value.empty:
                fig = px.bar(
                    class_value,
                    x="_Outstanding",
                    y="_CustomerClass",
                    orientation="h",
                    text="_Outstanding",
                    color="_CustomerClass",
                    category_orders={
                        "_CustomerClass": class_order
                    },
                    color_discrete_map={
                        "ลูกหนี้ชั้นดี": GOOD,
                        "ลูกหนี้เฝ้าติดตาม": WATCH,
                        "ลูกหนี้ชั้นแย่": BAD,
                    },
                )

                fig.update_traces(
                    texttemplate="฿%{x:,.0f}",
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(color="#334155", size=12),
                )

                fig.update_layout(
                    height=350,
                    margin=dict(l=15, r=45, t=20, b=40),
                    xaxis=dict(
                        title="Outstanding AR (บาท)",
                        tickformat=",.0f",
                        tickfont=dict(color="#334155"),
                        title_font=dict(color="#64748B"),
                    ),
                    yaxis=dict(title="", automargin=True, tickfont=dict(color="#334155")),
                    paper_bgcolor="white",
                    plot_bgcolor="white",
                    showlegend=False,
                )

                st.plotly_chart(fig, width="stretch")
            else:
                st.info("ไม่มี Outstanding AR แยกตามชั้นลูกหนี้")

    # -----------------------------------------------------
    # ROW 2: TOP CUSTOMERS TO ACT ON
    # -----------------------------------------------------
    with st.container(border=True):
        st.markdown("#### Top ลูกหนี้ที่ควรติดตามก่อน")
        st.caption(
            "เรียงจาก Overdue AR สูงสุด เพื่อช่วยจัดลำดับการติดตามหนี้"
        )

        top_controls_1, top_controls_2 = st.columns([1, 3])

        with top_controls_1:
            top_n = st.selectbox(
                "จำนวน Top",
                [5, 10, 15, 20],
                index=1,
                key="ar_exec_top_n",
            )

        branch_lookup = (
            filtered[["_Debtor", "_Branch"]]
            .drop_duplicates(subset=["_Debtor"], keep="last")
        )

        top_detail = customer_summary.merge(
            branch_lookup,
            on="_Debtor",
            how="left",
        )

        top_detail = top_detail[
            (top_detail["Outstanding_AR"] > 0)
            | (top_detail["Overdue_AR"] > 0)
        ].copy()

        top_detail = top_detail.sort_values(
            ["Overdue_AR", "Outstanding_AR"],
            ascending=[False, False],
        ).head(top_n)

        top_detail = top_detail.rename(
            columns={
                "_Debtor": "ลูกหนี้",
                "_Branch": "สาขา",
                "Outstanding_AR": "ยอดลูกหนี้คงค้าง",
                "Overdue_AR": "Overdue AR",
                "Max_Delay_Source": "วันช้าสูงสุด",
                "Customer_Class": "ชั้นลูกหนี้",
                "Late_Rate_Source": "% บิลที่ช้า",
            }
        )

        if not top_detail.empty:
            top_show = top_detail[
                [
                    "ลูกหนี้",
                    "สาขา",
                    "ยอดลูกหนี้คงค้าง",
                    "Overdue AR",
                    "% บิลที่ช้า",
                    "วันช้าสูงสุด",
                    "ชั้นลูกหนี้",
                ]
            ].copy()

            st.markdown(
                AR_TABLE_CSS
                + ar_table_html(
                    top_show,
                    money_cols=["ยอดลูกหนี้คงค้าง", "Overdue AR"],
                    pct_cols=["% บิลที่ช้า"],
                    day_cols=["วันช้าสูงสุด"],
                    over_cols=["Overdue AR"],
                    class_col="ชั้นลูกหนี้",
                    max_height=380,
                ),
                unsafe_allow_html=True,
            )
        else:
            st.info("ไม่มีลูกหนี้คงค้างตามตัวกรอง")

    # -----------------------------------------------------
    # ROW 3: BRANCH RISK + EXECUTIVE ALERTS
    # -----------------------------------------------------
    row3_left, row3_right = st.columns([1.25, 0.75])

    with row3_left:
        with st.container(border=True):
            st.markdown("#### Overdue AR ตามสาขา")
            st.caption(
                "ดูสาขาที่มียอดเกินกำหนดสูง เพื่อแยกจากสาขาที่มียอดขายสูงเฉย ๆ"
            )

            branch_risk = (
                filtered.groupby("_Branch", as_index=False)
                .agg(
                    Outstanding_AR=("_Outstanding", "sum"),
                    Overdue_AR=("_OverdueAmount", "sum"),
                )
            )

            branch_risk["Overdue_Pct"] = (
                branch_risk["Overdue_AR"]
                / branch_risk["Outstanding_AR"].replace(0, pd.NA)
            ).fillna(0)

            branch_risk = (
                branch_risk[branch_risk["Overdue_AR"] > 0]
                .sort_values("Overdue_AR", ascending=False)
                .head(10)
                .sort_values("Overdue_AR", ascending=True)
            )

            if not branch_risk.empty:
                fig = px.bar(
                    branch_risk,
                    x="Overdue_AR",
                    y="_Branch",
                    orientation="h",
                    text="Overdue_AR",
                    custom_data=["Outstanding_AR", "Overdue_Pct"],
                    color="_Branch",
                    color_discrete_sequence=PALETTE,
                )

                fig.update_traces(
                    texttemplate="฿%{x:,.0f}",
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(color="#334155", size=12),
                    hovertemplate=(
                        "%{y}<br>"
                        "Overdue AR: ฿%{x:,.0f}<br>"
                        "Outstanding AR: ฿%{customdata[0]:,.0f}<br>"
                        "Overdue %: %{customdata[1]:.1%}"
                        "<extra></extra>"
                    ),
                )

                fig.update_layout(
                    height=390,
                    margin=dict(l=15, r=55, t=20, b=40),
                    xaxis=dict(
                        title="Overdue AR (บาท)",
                        tickformat=",.0f",
                        tickfont=dict(color="#334155"),
                        title_font=dict(color="#64748B"),
                    ),
                    yaxis=dict(title="", automargin=True, tickfont=dict(color="#334155")),
                    paper_bgcolor="white",
                    plot_bgcolor="white",
                    showlegend=False,
                )

                st.plotly_chart(fig, width="stretch")
            else:
                st.info("ไม่มี Overdue AR ตามสาขา")

    with row3_right:
        with st.container(border=True):
            st.markdown("#### Executive Alerts")
            st.caption("ประเด็นที่ควรตรวจสอบ/ติดตามจากข้อมูลปัจจุบัน")

            overdue_90_customers = int(
                filtered.loc[
                    (~filtered["_Paid"]) & (filtered["_DelayDays"] > 90),
                    "_Debtor",
                ]
                .replace("", pd.NA)
                .dropna()
                .nunique()
            )

            # Branch with highest overdue
            branch_alert = (
                filtered.groupby("_Branch", as_index=False)["_OverdueAmount"]
                .sum()
                .sort_values("_OverdueAmount", ascending=False)
            )
            branch_alert = branch_alert[
                branch_alert["_OverdueAmount"] > 0
            ]

            # Customer with highest overdue
            customer_alert = (
                customer_summary.sort_values(
                    "Overdue_AR",
                    ascending=False,
                )
            )
            customer_alert = customer_alert[
                customer_alert["Overdue_AR"] > 0
            ]

            if overdue_ar > 0:
                st.warning(
                    f"Overdue AR คิดเป็น {overdue_pct:.1%} "
                    f"ของ Outstanding AR"
                )
            else:
                st.success("ไม่พบยอด Overdue AR ตามตัวกรอง")

            if ar_90_plus > 0:
                st.error(
                    f"ค้างเกิน 90 วัน {fmt_money(ar_90_plus)} "
                    f"จากลูกหนี้ {overdue_90_customers:,} ราย"
                )

            if not branch_alert.empty:
                top_branch = branch_alert.iloc[0]
                st.info(
                    f"สาขาที่มี Overdue สูงสุด: "
                    f"{top_branch['_Branch']} "
                    f"({fmt_money(float(top_branch['_OverdueAmount']))})"
                )

            if not customer_alert.empty:
                top_customer = customer_alert.iloc[0]
                class_text = top_customer.get(
                    "Customer_Class",
                    "ไม่ระบุ",
                )
                st.info(
                    f"ลูกหนี้ที่มี Overdue สูงสุด: "
                    f"{top_customer['_Debtor']} "
                    f"({fmt_money(float(top_customer['Overdue_AR']))}) "
                    f"• {class_text}"
                )

            if risky_customers > 0:
                st.warning(
                    f"มีลูกหนี้เสี่ยงที่ยังมียอดค้าง "
                    f"{risky_customers:,} ราย"
                )

    # -----------------------------------------------------
    # DETAIL
    # -----------------------------------------------------
    with st.expander("ดูตารางลูกหนี้ทั้งหมด"):
        detail = customer_summary.copy()

        branch_lookup = (
            filtered[["_Debtor", "_Branch"]]
            .drop_duplicates(subset=["_Debtor"], keep="last")
        )

        detail = detail.merge(
            branch_lookup,
            on="_Debtor",
            how="left",
        )

        detail = detail.rename(
            columns={
                "_Debtor": "ชื่อลูกหนี้",
                "_Branch": "สาขา",
                "Total_Bills_Source": "จำนวนบิลทั้งหมด",
                "Late_Bills_Source": "จำนวนบิลที่ช้า",
                "Total_Delay_Source": "รวมวันช้า",
                "Late_Rate_Source": "% บิลที่ช้า",
                "Max_Delay_Source": "วันช้าสูงสุด",
                "Outstanding_AR": "ยอดลูกหนี้คงค้าง",
                "Overdue_AR": "Overdue AR",
                "Customer_Class": "แบ่งชั้นลูกหนี้",
            }
        )

        detail = detail.sort_values(
            ["Overdue AR", "ยอดลูกหนี้คงค้าง"],
            ascending=False,
        )

        detail_show = detail[
            [
                "ชื่อลูกหนี้",
                "สาขา",
                "จำนวนบิลทั้งหมด",
                "จำนวนบิลที่ช้า",
                "รวมวันช้า",
                "% บิลที่ช้า",
                "วันช้าสูงสุด",
                "ยอดลูกหนี้คงค้าง",
                "Overdue AR",
                "แบ่งชั้นลูกหนี้",
            ]
        ].copy()

        st.markdown(
            AR_TABLE_CSS
            + ar_table_html(
                detail_show,
                money_cols=["ยอดลูกหนี้คงค้าง", "Overdue AR"],
                pct_cols=["% บิลที่ช้า"],
                day_cols=["วันช้าสูงสุด"],
                over_cols=["Overdue AR"],
                class_col="แบ่งชั้นลูกหนี้",
                max_height=430,
            ),
            unsafe_allow_html=True,
        )


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


# คอลัมน์ต้นทุนจาก data1.xlsx
# ใช้ชื่อคอลัมน์จริงเป็นหลัก ไม่รวมคอลัมน์เลขที่บิล/เลขที่เอกสาร
KNOWN_COST_COLUMNS = [
    "Total Cost",
    "รวมต้นทุนค่าเดินทาง",
    "รวมต้นทุนค่าซ่อม",
    "Total Cash",
    "Total Freight",
    "Fuel (Cash)",
    "Driver Allowance",
    "Backup Driver Allowance",
    "Off-Route",
    "Off-Route Fuel",
    "Tarpaulin Fee",
    "Goods Fuel",
    "Pickup Cost",
    "Police Fee",
    "โยกค่าน้ำมันขาขึ้น",
    "โยกต้นทุนเที่ยวยกเลิก",
    "ค่าน้ำมันตามจริง",
    "ยอดปันส่วนค่าน้ำมันตามจริง",
    "โยกค่าน้ำมันตามจริง",
    "ยอดปันส่วนโยกค่าน้ำมันตามจริง",
]


def get_cost_columns(df: pd.DataFrame):
    """
    คืนคอลัมน์ต้นทุนที่มีอยู่จริงใน DataFrame
    และมีค่าตัวเลขอย่างน้อย 1 ค่า
    """
    result = []

    for column in KNOWN_COST_COLUMNS:
        if column not in df.columns:
            continue

        numeric = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        if numeric.notna().any():
            result.append(column)

    return result


def get_component_cost_columns(df: pd.DataFrame):
    """
    คอลัมน์ต้นทุนย่อยสำหรับองค์ประกอบต้นทุน
    ตัดยอดรวม/ยอดสรุปออก เพื่อไม่ให้ Pie นับซ้ำ
    """
    excluded = {
        "Total Cost",
        "รวมต้นทุนค่าเดินทาง",
        "รวมต้นทุนค่าซ่อม",
        "Total Cash",
    }

    return [
        c
        for c in get_cost_columns(df)
        if c not in excluded
    ]


def find_column(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def fmt_money(value):
    value = float(value or 0)
    if abs(value) >= 1_000_000:
        return f"฿{value / 1_000_000:,.2f}M"
    return f"฿{value:,.0f}"


def make_route(df: pd.DataFrame) -> pd.Series:
    loading = (
        df["Loading"].fillna("").astype(str).str.strip()
        if "Loading" in df.columns
        else pd.Series("", index=df.index)
    )
    unloading = (
        df["Unloading"].fillna("").astype(str).str.strip()
        if "Unloading" in df.columns
        else pd.Series("", index=df.index)
    )

    route = loading + " → " + unloading
    route = route.where(
        (loading != "") | (unloading != ""),
        "ไม่ระบุเส้นทาง",
    )
    return route


def get_year_series(df: pd.DataFrame) -> pd.Series:
    if "Travel Req. Date" in df.columns:
        dt = pd.to_datetime(df["Travel Req. Date"], format="mixed", errors="coerce", dayfirst=True)
        year = dt.dt.year
        return year.apply(
            lambda x: (
                str(int(x + 543))
                if pd.notna(x) and x < 2400
                else (str(int(x)) if pd.notna(x) else None)
            )
        )

    if "Year" in df.columns:
        return df["Year"].astype(str)

    return pd.Series(None, index=df.index)



def render_empty_trip_dashboard(
    raw_df: pd.DataFrame,
):
    """
    Executive Dashboard:
    เที่ยวเปล่า + รถว่างไปสาขา

    แนวคิดสีใช้เหมือนกันทั้งหน้า:
    - เที่ยวเปล่า = แดงคอรัล
    - รถว่างไปสาขา = ส้ม
    - เที่ยวทั้งหมด = ม่วง
    """

    if raw_df.empty:
        st.warning("ยังไม่มีข้อมูลสำหรับ Dashboard นี้")
        return

    required = ["Manifest Type", "Total Cost"]

    missing = [
        c
        for c in required
        if c not in raw_df.columns
    ]

    if missing:
        st.warning(
            "ข้อมูลยังไม่พอสำหรับ Dashboard นี้: "
            + ", ".join(missing)
        )
        return

    # -----------------------------------------------------
    # COLOR SYSTEM
    # -----------------------------------------------------
    TRIP_COLORS = {
        "เที่ยวเปล่า": "#F07C8C",
        "รถว่างไปสาขา": "#F6AE6B",
        "เที่ยวทั้งหมด": "#BBA0E3",
    }

    TRIP_EMOJI = {
        "เที่ยวเปล่า": "🔴",
        "รถว่างไปสาขา": "🟠",
        "เที่ยวทั้งหมด": "🟣",
    }

    # สีสำหรับ "เที่ยว/เส้นทาง"
    # ใช้ hash ของชื่อเส้นทางเพื่อให้เส้นทางเดิมได้สีเดิมเสมอ
    ROUTE_PALETTE = PALETTE

    def route_color(route_name):
        """
        เที่ยว/เส้นทางชื่อเดิมจะได้สีเดิมเสมอ
        ใช้ MD5 เพื่อไม่ให้สีเปลี่ยนตามลำดับ Top
        """
        route_text = str(route_name or "")
        digest = hashlib.md5(
            route_text.encode("utf-8")
        ).hexdigest()

        color_index = (
            int(digest[:8], 16)
            % len(ROUTE_PALETTE)
        )

        return ROUTE_PALETTE[
            color_index
        ]

    work = raw_df.copy()

    # -----------------------------------------------------
    # NORMALIZE / CLASSIFY TRIP TYPE
    # -----------------------------------------------------
    manifest = (
        work["Manifest Type"]
        .astype("string")
        .fillna("")
        .str.strip()
    )

    is_empty = manifest.str.contains(
        r"ของเหมาตีเปล่า|เที่ยวเปล่า",
        regex=True,
        na=False,
    )

    is_branch_empty = manifest.str.contains(
        "รถว่างไปสาขา",
        regex=False,
        na=False,
    )

    work = work[
        is_empty | is_branch_empty
    ].copy()

    if work.empty:
        st.info(
            "ยังไม่พบ Manifest Type ที่เป็น "
            "'เที่ยวเปล่า' หรือ 'รถว่างไปสาขา'"
        )
        return

    work["_TripCategory"] = "เที่ยวเปล่า"

    work.loc[
        is_branch_empty.loc[work.index],
        "_TripCategory",
    ] = "รถว่างไปสาขา"

    work["_Cost"] = numeric_series(
        work,
        "Total Cost",
    ).fillna(0)

    if "_Route" not in work.columns:
        work["_Route"] = make_route(work)

    if "Travel Req. Date" in work.columns:
        work["_Date"] = pd.to_datetime(
            work["Travel Req. Date"],
            errors="coerce",
        )
    else:
        work["_Date"] = pd.NaT

    distance_col = find_column(
        work,
        [
            "ระยะทาง",
            "Distance",
            "Total Distance",
            "Distance (km)",
            "KM",
        ],
    )

    if distance_col:
        work["_Distance"] = pd.to_numeric(
            work[distance_col],
            errors="coerce",
        ).fillna(0)
    else:
        work["_Distance"] = 0.0

    # -----------------------------------------------------
    # FILTERS
    # -----------------------------------------------------
    st.markdown(
        '<div class="section-title">ตัวกรองข้อมูล</div>',
        unsafe_allow_html=True,
    )

    f1, f2, f3, f4, f5 = st.columns(5)

    filtered = work.copy()

    filtered["_Year"] = get_year_series(
        filtered
    )

    year_options = sorted(
        [
            str(x)
            for x in filtered["_Year"].dropna().unique()
            if str(x).strip()
        ]
    )

    with f1:
        selected_year = st.selectbox(
            "ปี",
            ["ทั้งหมด"] + year_options,
            key="empty_year",
        )

    if selected_year != "ทั้งหมด":
        filtered = filtered[
            filtered["_Year"] == selected_year
        ]

    month_map = {
        1: "ม.ค.",
        2: "ก.พ.",
        3: "มี.ค.",
        4: "เม.ย.",
        5: "พ.ค.",
        6: "มิ.ย.",
        7: "ก.ค.",
        8: "ส.ค.",
        9: "ก.ย.",
        10: "ต.ค.",
        11: "พ.ย.",
        12: "ธ.ค.",
    }

    month_options = sorted(
        [
            int(m)
            for m in filtered[
                "_Date"
            ].dt.month.dropna().unique()
        ]
    )

    with f2:
        selected_month = st.selectbox(
            "เดือน",
            ["ทั้งหมด"]
            + [
                month_map[m]
                for m in month_options
            ],
            key="empty_month",
        )

    if selected_month != "ทั้งหมด":
        month_num = next(
            k
            for k, v in month_map.items()
            if v == selected_month
        )

        filtered = filtered[
            filtered["_Date"].dt.month
            == month_num
        ]

    loading_col = find_column(
        filtered,
        [
            "Loading",
            "จุดขึ้น",
            "ต้นทาง",
        ],
    )

    loading_options = []

    if loading_col:
        loading_options = sorted(
            [
                x
                for x in (
                    filtered[loading_col]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .unique()
                )
                if x
            ]
        )

    with f3:
        selected_loading = st.selectbox(
            "ต้นทาง",
            ["ทั้งหมด"] + loading_options,
            key="empty_loading",
        )

    if (
        selected_loading != "ทั้งหมด"
        and loading_col
    ):
        filtered = filtered[
            (
                filtered[loading_col]
                .astype("string")
                .str.strip()
            )
            == selected_loading
        ]

    unloading_col = find_column(
        filtered,
        [
            "Unloading",
            "จุดลง",
            "ปลายทาง",
        ],
    )

    unloading_options = []

    if unloading_col:
        unloading_options = sorted(
            [
                x
                for x in (
                    filtered[unloading_col]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .unique()
                )
                if x
            ]
        )

    with f4:
        selected_unloading = st.selectbox(
            "ปลายทาง",
            ["ทั้งหมด"]
            + unloading_options,
            key="empty_unloading",
        )

    if (
        selected_unloading != "ทั้งหมด"
        and unloading_col
    ):
        filtered = filtered[
            (
                filtered[unloading_col]
                .astype("string")
                .str.strip()
            )
            == selected_unloading
        ]

    vehicle_col = find_column(
        filtered,
        [
            "Vehicle Model",
            "ประเภทรถ",
        ],
    )

    vehicle_options = []

    if vehicle_col:
        vehicle_options = sorted(
            [
                x
                for x in (
                    filtered[vehicle_col]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .unique()
                )
                if x
            ]
        )

    with f5:
        selected_vehicle = st.selectbox(
            "ประเภทรถ",
            ["ทั้งหมด"]
            + vehicle_options,
            key="empty_vehicle",
        )

    if (
        selected_vehicle != "ทั้งหมด"
        and vehicle_col
    ):
        filtered = filtered[
            (
                filtered[vehicle_col]
                .astype("string")
                .str.strip()
            )
            == selected_vehicle
        ]

    if filtered.empty:
        st.info(
            "ไม่มีข้อมูลตามตัวกรองที่เลือก"
        )
        return

    # -----------------------------------------------------
    # HELPERS
    # -----------------------------------------------------
    trip_id_col = (
        "Travel Req. No."
        if "Travel Req. No."
        in filtered.columns
        else None
    )

    def trip_count(df_part):
        if trip_id_col:
            return int(
                df_part[
                    trip_id_col
                ]
                .astype("string")
                .replace("", pd.NA)
                .dropna()
                .nunique()
            )

        return int(
            len(df_part)
        )

    empty_df = filtered[
        filtered["_TripCategory"]
        == "เที่ยวเปล่า"
    ]

    branch_df = filtered[
        filtered["_TripCategory"]
        == "รถว่างไปสาขา"
    ]

    total_trips = trip_count(
        filtered
    )

    empty_trips = trip_count(
        empty_df
    )

    branch_trips = trip_count(
        branch_df
    )

    empty_cost = float(
        empty_df["_Cost"].sum()
    )

    branch_cost = float(
        branch_df["_Cost"].sum()
    )

    total_loss_cost = (
        empty_cost
        + branch_cost
    )

    empty_pct = (
        empty_trips / total_trips
        if total_trips
        else 0
    )

    branch_pct = (
        branch_trips / total_trips
        if total_trips
        else 0
    )

    # -----------------------------------------------------
    # KPI ROW
    # เปลี่ยนชื่อจากเชิง "เส้นทาง" ให้เป็น "เที่ยวทั้งหมด"
    # -----------------------------------------------------
    k1, k2, k3, k4, k5, k6 = st.columns(
        6
    )

    k1.metric(
        "🚚 เที่ยวทั้งหมด",
        f"{total_trips:,}",
    )

    k2.metric(
        "🔴 เที่ยวเปล่า",
        f"{empty_trips:,}",
        f"{empty_pct:.1%} ของเที่ยวทั้งหมด",
        delta_color="inverse",
    )

    k3.metric(
        "🟠 รถว่างไปสาขา",
        f"{branch_trips:,}",
        f"{branch_pct:.1%} ของเที่ยวทั้งหมด",
        delta_color="inverse",
    )

    k4.metric(
        "💵 ต้นทุนเที่ยวเปล่า",
        fmt_money(
            empty_cost
        ),
    )

    k5.metric(
        "💵 ต้นทุนรถว่างไปสาขา",
        fmt_money(
            branch_cost
        ),
    )

    k6.metric(
        "💰 ต้นทุนสูญเสียรวม",
        fmt_money(
            total_loss_cost
        ),
    )

    # -----------------------------------------------------
    # COST COMPOSITION — 2 CARDS
    # -----------------------------------------------------
    st.markdown(
        '<div class="section-title">องค์ประกอบต้นทุนของแต่ละประเภทเที่ยว</div>',
        unsafe_allow_html=True,
    )

    def nonzero_cost_columns(
        df_source,
    ):
        """
        แสดงเฉพาะคอลัมน์ต้นทุนที่มีมูลค่าจริงในประเภทเที่ยวนั้น
        เพื่อไม่ให้เลือกคอลัมน์ที่เป็น 0 แล้วเข้าใจว่ากราฟไม่อัปเดต
        """
        result = []

        for c in get_cost_columns(
            df_source
        ):
            if c in {
                "Total Cost",
                "Total Cash",
            }:
                continue

            value = float(
                numeric_series(
                    df_source,
                    c,
                ).fillna(0).sum()
            )

            if abs(value) > 1e-9:
                result.append(c)

        return result

    def cost_composition_card(
        container,
        df_source,
        trip_label,
        key_prefix,
    ):
        with container:
            with st.container(
                   border=True, height="stretch"
            ):
                st.markdown(
                    f"#### {TRIP_EMOJI[trip_label]} "
                    f"องค์ประกอบต้นทุน — {trip_label}"
                )

                available_cols = (
                    nonzero_cost_columns(
                        df_source
                    )
                )

                st.caption(
                    "เลือกดูเฉพาะต้นทุนที่มีมูลค่าจริงในประเภทเที่ยวนั้น "
                    "กราฟจะคำนวณสัดส่วนใหม่ทันทีตามรายการที่เลือก"
                )

                if not available_cols:
                    st.info(
                        "ไม่พบองค์ประกอบต้นทุนที่มีมูลค่า"
                    )
                    return

                default_cols = [
                    c
                    for c in [
                        "รวมต้นทุนค่าเดินทาง",
                        "รวมต้นทุนค่าซ่อม",
                    ]
                    if c in available_cols
                ]

                if not default_cols:
                    default_cols = (
                        available_cols[:4]
                    )

                selected_cols = st.multiselect(
                    "เลือกต้นทุนที่ต้องการเปรียบเทียบ",
                    available_cols,
                    default=default_cols,
                    key=f"{key_prefix}_cost_components",
                )

                if not selected_cols:
                    st.info(
                        "เลือกอย่างน้อย 1 รายการเพื่อดูสัดส่วนต้นทุน"
                    )
                    return

                rows = []

                for col in selected_cols:
                    value = float(
                        numeric_series(
                            df_source,
                            col,
                        ).fillna(0).sum()
                    )

                    rows.append(
                        {
                            "ต้นทุน": col,
                            "มูลค่า": value,
                        }
                    )

                cost_df = pd.DataFrame(
                    rows
                )

                cost_df = cost_df[
                    cost_df["มูลค่า"] > 0
                ].copy()

                if cost_df.empty:
                    st.info(
                        "รายการที่เลือกไม่มีมูลค่าต้นทุน"
                    )
                    return

                fig = px.pie(
                    cost_df,
                    names="ต้นทุน",
                    values="มูลค่า",
                    hole=0.58,
                    color_discrete_sequence=(
                        px.colors.sequential.Reds[2:]
                        if trip_label == "เที่ยวเปล่า"
                        else px.colors.sequential.Oranges[2:]
                    ),
                )

                fig.update_traces(
                    textinfo="percent",
                    textposition="inside",
                    hovertemplate=(
                        "%{label}<br>"
                        "฿%{value:,.0f}<br>"
                        "%{percent}"
                        "<extra></extra>"
                    ),
                )

                selected_total = float(
                    cost_df["มูลค่า"].sum()
                )

                fig.update_layout(
                    height=390,
                    margin=dict(
                        l=10,
                        r=10,
                        t=15,
                        b=75,
                    ),
                    legend=dict(
                        orientation="h",
                        y=-0.13,
                    ),
                    annotations=[
                        dict(
                            text=(
                                "รวมที่เลือก<br>"
                                + fmt_money(
                                    selected_total
                                )
                            ),
                            x=0.5,
                            y=0.5,
                            showarrow=False,
                            font_size=14,
                        )
                    ],
                )

                st.plotly_chart(
                    fig,
                    width="stretch",
                )

                st.dataframe(
                    cost_df.rename(
                        columns={
                            "มูลค่า": "มูลค่า (บาท)"
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "มูลค่า (บาท)":
                            st.column_config.NumberColumn(
                                "มูลค่า (บาท)",
                                format="฿%,.0f",
                            )
                    },
                )

    cc1, cc2 = st.columns(
        [1, 1]
    )

    cost_composition_card(
        cc1,
        empty_df,
        "เที่ยวเปล่า",
        "empty_trip",
    )

    cost_composition_card(
        cc2,
        branch_df,
        "รถว่างไปสาขา",
        "branch_trip",
    )

    # -----------------------------------------------------
    # PROBLEM OVERVIEW BY TRIP — STACKED BAR
    # -----------------------------------------------------
    with st.container(
        border=True
    ):
        st.markdown(
            "#### ภาพรวมปัญหาตามเที่ยว"
        )

        st.caption(
            "แสดงเส้นทางที่มีเที่ยวเปล่าและรถว่างไปสาขามากที่สุด "
            "โดยแยกสีแต่ละประเภทเที่ยวให้ดูง่าย"
        )

        ov1, ov2 = st.columns(
            [1.2, 0.8]
        )

        with ov1:
            overview_metric = st.selectbox(
                "เลือกตัวชี้วัด",
                [
                    "จำนวนเที่ยว",
                    "ต้นทุนรวม",
                ],
                key="overview_metric",
            )

        with ov2:
            overview_top_n = st.selectbox(
                "จำนวน Top",
                [
                    5,
                    10,
                    15,
                    20,
                ],
                index=1,
                key="overview_top_n",
            )

        route_rows = []

        for route, group in filtered.groupby(
            "_Route",
            dropna=False,
        ):
            empty_group = group[
                group["_TripCategory"]
                == "เที่ยวเปล่า"
            ]

            branch_group = group[
                group["_TripCategory"]
                == "รถว่างไปสาขา"
            ]

            route_rows.append(
                {
                    "เที่ยว": route,
                    "เที่ยวเปล่า_จำนวน":
                        trip_count(
                            empty_group
                        ),
                    "รถว่างไปสาขา_จำนวน":
                        trip_count(
                            branch_group
                        ),
                    "เที่ยวเปล่า_ต้นทุน":
                        float(
                            empty_group[
                                "_Cost"
                            ].sum()
                        ),
                    "รถว่างไปสาขา_ต้นทุน":
                        float(
                            branch_group[
                                "_Cost"
                            ].sum()
                        ),
                }
            )

        route_overview = pd.DataFrame(
            route_rows
        )

        if not route_overview.empty:

            if overview_metric == "จำนวนเที่ยว":
                empty_col = "เที่ยวเปล่า_จำนวน"
                branch_col = "รถว่างไปสาขา_จำนวน"
                x_title = "จำนวนเที่ยว"
                value_suffix = ""
            else:
                empty_col = "เที่ยวเปล่า_ต้นทุน"
                branch_col = "รถว่างไปสาขา_ต้นทุน"
                x_title = "ต้นทุนรวม (บาท)"
                value_suffix = "฿"

            route_overview["_Total"] = (
                route_overview[
                    empty_col
                ]
                + route_overview[
                    branch_col
                ]
            )

            route_overview = (
                route_overview[
                    route_overview[
                        "_Total"
                    ] > 0
                ]
                .sort_values(
                    "_Total",
                    ascending=False,
                )
                .head(
                    overview_top_n
                )
                .sort_values(
                    "_Total",
                    ascending=True,
                )
            )

            if not route_overview.empty:

                fig = go.Figure()

                fig.add_trace(
                    go.Bar(
                        name="เที่ยวเปล่า",
                        y=route_overview[
                            "เที่ยว"
                        ],
                        x=route_overview[
                            empty_col
                        ],
                        orientation="h",
                        marker_color=TRIP_COLORS[
                            "เที่ยวเปล่า"
                        ],
                        text=(
                            route_overview[
                                empty_col
                            ].map(
                                lambda x:
                                f"฿{x:,.0f}"
                                if value_suffix == "฿"
                                else f"{x:,.0f}"
                            )
                        ),
                        textposition="inside",
                        hovertemplate=(
                            "%{y}<br>"
                            "เที่ยวเปล่า: "
                            + (
                                "฿%{x:,.0f}"
                                if value_suffix == "฿"
                                else "%{x:,.0f} เที่ยว"
                            )
                            + "<extra></extra>"
                        ),
                    )
                )

                fig.add_trace(
                    go.Bar(
                        name="รถว่างไปสาขา",
                        y=route_overview[
                            "เที่ยว"
                        ],
                        x=route_overview[
                            branch_col
                        ],
                        orientation="h",
                        marker_color=TRIP_COLORS[
                            "รถว่างไปสาขา"
                        ],
                        text=(
                            route_overview[
                                branch_col
                            ].map(
                                lambda x:
                                f"฿{x:,.0f}"
                                if value_suffix == "฿"
                                else f"{x:,.0f}"
                            )
                        ),
                        textposition="inside",
                        hovertemplate=(
                            "%{y}<br>"
                            "รถว่างไปสาขา: "
                            + (
                                "฿%{x:,.0f}"
                                if value_suffix == "฿"
                                else "%{x:,.0f} เที่ยว"
                            )
                            + "<extra></extra>"
                        ),
                    )
                )

                fig.update_layout(
                    barmode="stack",
                    height=max(
                        390,
                        38
                        * len(
                            route_overview
                        )
                        + 140,
                    ),
                    margin=dict(
                        l=15,
                        r=35,
                        t=20,
                        b=45,
                    ),
                    xaxis=dict(
                        title=x_title,
                        tickformat=",.0f",
                    ),
                    yaxis=dict(
                        title="",
                        automargin=True,
                        tickfont=dict(
                            size=10,
                        ),
                    ),
                    legend=dict(
                        orientation="h",
                        y=1.10,
                        x=0,
                    ),
                    paper_bgcolor="white",
                    plot_bgcolor="white",
                    hovermode="y unified",
                )

                st.plotly_chart(
                    fig,
                    width="stretch",
                )

            else:
                st.info(
                    "ไม่มีข้อมูลสำหรับตัวชี้วัดที่เลือก"
                )

        else:
            st.info(
                "ไม่มีข้อมูลเที่ยวตามตัวกรอง"
            )

    # -----------------------------------------------------
    # ROUTES TO WATCH — USER CAN CHOOSE TRIP TYPE
    # -----------------------------------------------------
    with st.container(
        border=True
    ):
        st.markdown(
            "#### เที่ยวที่ควรติดตาม"
        )

        st.caption(
            "เลือกประเภทเที่ยวและตัวชี้วัดที่ต้องการดู • "
            "สีในกราฟนี้แทน 'เที่ยว/เส้นทาง' โดยเที่ยวเดียวกันจะใช้สีเดิมเสมอ "
            "แม้เปลี่ยนตัวชี้วัดหรือจำนวน Top"
        )

        rc1, rc2, rc3 = st.columns(
            [1.2, 1.2, 0.8]
        )

        with rc1:
            selected_trip_type = st.selectbox(
                "เลือกประเภทเที่ยว",
                [
                    "เที่ยวทั้งหมด",
                    "เที่ยวเปล่า",
                    "รถว่างไปสาขา",
                ],
                key="watch_trip_type",
            )

        with rc2:
            selected_watch_metric = st.selectbox(
                "เลือกตัวชี้วัด",
                [
                    "จำนวนเที่ยว",
                    "ต้นทุนรวม",
                ],
                key="watch_metric",
            )

        with rc3:
            watch_top_n = st.selectbox(
                "จำนวน Top",
                [
                    5,
                    10,
                    15,
                    20,
                ],
                index=1,
                key="watch_top_n",
            )

        if (
            selected_trip_type
            == "เที่ยวเปล่า"
        ):
            watch_df = filtered[
                filtered["_TripCategory"]
                == "เที่ยวเปล่า"
            ].copy()

        elif (
            selected_trip_type
            == "รถว่างไปสาขา"
        ):
            watch_df = filtered[
                filtered["_TripCategory"]
                == "รถว่างไปสาขา"
            ].copy()

        else:
            watch_df = filtered.copy()

        watch_rows = []

        for route, group in watch_df.groupby(
            "_Route",
            dropna=False,
        ):
            watch_rows.append(
                {
                    "เที่ยว": route,
                    "จำนวนเที่ยว": trip_count(
                        group
                    ),
                    "ต้นทุนรวม": float(
                        group["_Cost"].sum()
                    ),
                }
            )

        watch_summary = pd.DataFrame(
            watch_rows
        )

        if not watch_summary.empty:
            watch_summary = (
                watch_summary
                .sort_values(
                    selected_watch_metric,
                    ascending=False,
                )
                .head(
                    watch_top_n
                )
                .sort_values(
                    selected_watch_metric,
                    ascending=True,
                )
            )

            # เที่ยว/เส้นทางเดียวกัน = สีเดียวกันเสมอ
            # ไม่เปลี่ยนสีเมื่อสลับ จำนวนเที่ยว/ต้นทุนรวม หรือ Top N
            route_color_map = {
                route: route_color(
                    route
                )
                for route in watch_summary[
                    "เที่ยว"
                ].astype(str).unique()
            }

            fig = px.bar(
                watch_summary,
                x=selected_watch_metric,
                y="เที่ยว",
                orientation="h",
                text=selected_watch_metric,
                color="เที่ยว",
                color_discrete_map=route_color_map,
            )

            fig.update_traces(
                texttemplate=(
                    "฿%{x:,.0f}"
                    if selected_watch_metric
                    == "ต้นทุนรวม"
                    else "%{x:,.0f}"
                ),
                textposition="outside",
                cliponaxis=False,
            )

            fig.update_layout(
                height=max(
                    360,
                    34
                    * len(
                        watch_summary
                    )
                    + 120,
                ),
                margin=dict(
                    l=15,
                    r=60,
                    t=15,
                    b=40,
                ),
                xaxis=dict(
                    title=(
                        "บาท"
                        if selected_watch_metric
                        == "ต้นทุนรวม"
                        else "จำนวนเที่ยว"
                    ),
                    tickformat=",.0f",
                ),
                yaxis=dict(
                    title="",
                    automargin=True,
                    tickfont=dict(
                        size=10
                    ),
                ),
                showlegend=False,
                paper_bgcolor="white",
                plot_bgcolor="white",
            )

            st.plotly_chart(
                fig,
                width="stretch",
            )
        else:
            st.info(
                "ไม่มีข้อมูลสำหรับประเภทเที่ยวที่เลือก"
            )

    # -----------------------------------------------------
    # DRILL-DOWN
    # -----------------------------------------------------
    with st.container(
        border=True
    ):
        st.markdown(
            "#### รายละเอียดเที่ยว (Drill-down)"
        )

        route_options = sorted(
            [
                x
                for x in (
                    filtered["_Route"]
                    .astype("string")
                    .fillna("")
                    .unique()
                )
                if x
            ]
        )

        dc1, dc2 = st.columns(
            [1.5, 1]
        )

        with dc1:
            selected_route = st.selectbox(
                "เลือกเที่ยว",
                [
                    "ทุกเที่ยว"
                ]
                + route_options,
                key="empty_detail_route",
            )

        with dc2:
            detail_trip_type = st.selectbox(
                "ประเภทเที่ยว",
                [
                    "ทั้งหมด",
                    "เที่ยวเปล่า",
                    "รถว่างไปสาขา",
                ],
                key="empty_detail_type",
            )

        detail = filtered.copy()

        if selected_route != "ทุกเที่ยว":
            detail = detail[
                detail["_Route"]
                == selected_route
            ]

        if detail_trip_type != "ทั้งหมด":
            detail = detail[
                detail["_TripCategory"]
                == detail_trip_type
            ]

        detail = detail.sort_values(
            "_Cost",
            ascending=False,
        )

        # สีประเภทเที่ยวแบบเดียวกันทั้งหน้า
        category_display = (
            detail["_TripCategory"]
            .map(
                {
                    "เที่ยวเปล่า":
                    "🔴 เที่ยวเปล่า",
                    "รถว่างไปสาขา":
                    "🟠 รถว่างไปสาขา",
                }
            )
            .fillna(
                detail[
                    "_TripCategory"
                ]
            )
        )

        display = pd.DataFrame(
            {
                "วันที่":
                    detail["_Date"],

                "Trip ID":
                    (
                        detail[
                            "Travel Req. No."
                        ]
                        if "Travel Req. No."
                        in detail.columns
                        else ""
                    ),

                "เที่ยว":
                    detail["_Route"],

                "ทะเบียนรถ":
                    (
                        detail[
                            "License Plate"
                        ]
                        if "License Plate"
                        in detail.columns
                        else ""
                    ),

                "ประเภทรถ":
                    (
                        detail[
                            vehicle_col
                        ]
                        if vehicle_col
                        else ""
                    ),

                "ประเภทเที่ยว":
                    category_display,

                "ระยะทาง (กม.)":
                    detail[
                        "_Distance"
                    ],

                "ต้นทุนรวม (บาท)":
                    detail[
                        "_Cost"
                    ],
            }
        )

        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            height=390,
            column_config={
                "วันที่":
                    st.column_config.DateColumn(
                        "วันที่",
                        format="DD/MM/YYYY",
                    ),

                "ระยะทาง (กม.)":
                    st.column_config.NumberColumn(
                        "ระยะทาง (กม.)",
                        format="%,.0f",
                    ),

                "ต้นทุนรวม (บาท)":
                    st.column_config.NumberColumn(
                        "ต้นทุนรวม (บาท)",
                        format="฿%,.0f",
                    ),
            },
        )


# =========================================================
# AUTO SYNC EXCEL FOLDER
# =========================================================

# Streamlit native fragment:
# ตรวจทุก 10 วินาที แต่ rebuild เฉพาะเมื่อไฟล์เปลี่ยนจริงเท่านั้น
if hasattr(st, "fragment") and not VIEWER_MODE:

    def _folder_watch():
        auto_sync_data_folder()

    _folder_watch = st.fragment(
        run_every="10s"
    )(_folder_watch)

    _folder_watch()

else:
    # สำหรับ Streamlit รุ่นเก่าที่ไม่มี st.fragment
    # ระบบ Upload/Update/Delete ยังทำงานตามปกติ
    # แต่การ Save Excel ตรงในโฟลเดอร์ data จะต้องกด Refresh หน้าเว็บ
    if "_data_folder_signature" not in st.session_state:
        sync_signature_baseline()


# =========================================================
# DATA
# =========================================================
# ยังไม่มีฐานข้อมูล (เช่น เปิดบน Streamlit Cloud ครั้งแรก หรือหลังแอปรีสตาร์ต)
# ให้สร้างจากไฟล์ Excel ในโฟลเดอร์ data อัตโนมัติ
if not DB_PATH.exists():
    try:
        with st.spinner("กำลังเตรียมข้อมูลจากไฟล์ Excel ครั้งแรก อาจใช้เวลาสักครู่..."):
            rebuild_database()
    except Exception as e:
        st.error(f"สร้างฐานข้อมูลไม่สำเร็จ: {e}")
if DB_PATH.exists():
    _db_mtime = DB_PATH.stat().st_mtime_ns

    df = load_dashboard_data(
        _db_mtime
    )

    ar_df = load_ar_data(
        _db_mtime
    )

    ar_summary_df = load_ar_summary_data(
        _db_mtime
    )
else:
    df = pd.DataFrame()
    ar_df = pd.DataFrame()
    ar_summary_df = pd.DataFrame()


# =========================================================
# SIDEBAR
# =========================================================

# โลโก้ + ชื่อบริษัท (โค้ดตกแต่งอยู่ใน sidebar_brand.py)
render_sidebar_top()

if st.session_state.pop(
    "_auto_sync_message",
    None,
):
    st.toast(
        "ตรวจพบ Excel เปลี่ยนและอัปเดต Dashboard แล้ว",
        icon="✅",
    )

auto_error = st.session_state.pop(
    "_auto_sync_error",
    None,
)

if auto_error:
    st.sidebar.error(
        f"Auto Sync ไม่สำเร็จ: {auto_error}"
    )

if VIEWER_MODE:
    # Viewer mode: แสดงเฉพาะ Dashboard
    page = "📊 Dashboard Summary"
    st.sidebar.caption("Viewer Mode • ดูข้อมูลอย่างเดียว")
else:
    # Admin mode: เปิดเมนูจัดการข้อมูล
    page = st.sidebar.radio(
        "เมนู",
        ["📊 Dashboard Summary", "📂 Data Management"],
    )

# ปุ่มโหลดข้อมูลจาก Excel ใหม่ทันที (ใช้เมื่อแก้ไฟล์แล้วแดชบอร์ดยังไม่เปลี่ยน)
if not VIEWER_MODE:
    if st.sidebar.button("🔄 โหลดข้อมูลจาก Excel ใหม่", key="sidebar_rebuild", use_container_width=True):
        with st.spinner("กำลังอ่านไฟล์ Excel และสร้างฐานข้อมูลใหม่..."):
            rebuild_database()
        st.cache_data.clear()
        sync_signature_baseline()
        st.rerun()

# ปุ่มส่งออกหน้าปัจจุบันเป็นไฟล์ HTML (ปุ่มจริงวาดตอนท้ายหน้า เพราะต้องรอให้หน้าแสดงผลครบก่อน)
export_slot = st.sidebar.empty()

EXPORT_SLUGS = {
    "🚛 Transportation Cost": "transportation_cost",
    "🚚 เที่ยวเปล่า & รถว่างไปสาขา": "empty_trip",
    "👥 Customer Profitability": "customer_profit",
    "💳 AR & Collection": "ar_collection",
    "📊 Load Factor": "load_factor",
    "🧭 ภาพรวมรายทิศทาง": "direction_overview",
}


def finish_export():
    """เรียกท้ายหน้าแดชบอร์ดทุกหน้า: กดเตรียมไฟล์ แล้วกดดาวน์โหลด"""
    choice = st.session_state.get("dashboard_selector", "")
    with export_slot.container():
        if not st.button("📄 เตรียมไฟล์ HTML ของหน้านี้", key="export_prepare", use_container_width=True):
            return
        now = datetime.now()
        with st.spinner("กำลังสร้างไฟล์ HTML..."):
            data = build_page_html(
                st._nss_export, title=choice or "Dashboard",
                generated_at=now.strftime("%d/%m/%Y %H:%M"),
            )
        kwargs = dict(
            label="⬇️ ดาวน์โหลด HTML", data=data,
            file_name=f"{EXPORT_SLUGS.get(choice, 'dashboard')}_{now:%Y%m%d_%H%M}.html",
            mime="text/html", key="export_download", use_container_width=True,
        )
        try:
            st.download_button(on_click="ignore", **kwargs)
        except TypeError:
            st.download_button(**kwargs)


# การ์ดสถานะข้อมูล + ถนนรถวิ่ง
render_sidebar_bottom(
    DB_PATH,
    DATA_FOLDER,
    trip_rows=len(df),
    auto_sync=hasattr(st, "fragment"),
)


# =========================================================
# DASHBOARD
# =========================================================


if page == "📊 Dashboard Summary":

    # Load Factor อ่านจากไฟล์ Excel ที่อยู่ในโฟลเดอร์ data โดยตรง
    # ไม่ต้อง Upload ซ้ำในหน้า Dashboard — ให้ Upload ผ่าน Data Management เท่านั้น
    # อ่านไฟล์ Load Factor (ไฟล์ใหญ่) เฉพาะตอนเปิดหน้า Load Factor เท่านั้น
    # หน้าอื่นจะได้ไม่ค้างรออ่านไฟล์นี้ทุกครั้งที่ข้อมูลในโฟลเดอร์ data เปลี่ยน
    lf_df, lf_sources = pd.DataFrame(), []
    if st.session_state.get("dashboard_selector") == "📊 Load Factor":
        lf_df, lf_sources = load_vehicle_performance_files(
            _lf_file_signature()
        )

    DASHBOARD_OPTIONS = {
        "🚛 Transportation Cost": {
            "title": "🚛 Transportation Cost Dashboard",
            "subtitle": "Better Data | Lower Cost | Higher Profitability",
            "ready": not df.empty,
        },
        "🚚 เที่ยวเปล่า & รถว่างไปสาขา": {
            "title": "🚚 สรุปภาพรวม เที่ยวเปล่าและรถว่างไปสาขา",
            "subtitle": "Empty Trip | Branch Repositioning | Cost Loss Control",
            "ready": (
                not df.empty
                and "Manifest Type" in df.columns
                and df["Manifest Type"]
                    .astype("string")
                    .fillna("")
                    .str.contains(
                        r"ของเหมาตีเปล่า|เที่ยวเปล่า|รถว่างไปสาขา",
                        regex=True,
                        na=False,
                    )
                    .any()
            ),
        },
        "👥 Customer Profitability": {
            "title": "👥 กำไรลูกค้าและประเภทสินค้า",
            "subtitle": "รายได้ · ต้นทุนปันส่วน · กำไร · อัตรากำไร รายลูกค้าและประเภทสินค้า",
            "ready": False,
        },
        "💳 AR & Collection": {
            "title": "💳 AR & Collection Dashboard",
            "subtitle": "Outstanding AR | Aging | Collection | Customer Risk",
            "ready": not ar_df.empty,
        },
        "📊 Load Factor": {
            "title": "📦 Load Factor Dashboard",
            "subtitle": "วิเคราะห์การใช้ความสามารถในการบรรทุก (น้ำหนัก และ ปริมาตร) · ใช้ข้อมูลจริง เพื่อการจัดรถที่คุ้มค่า",
            "ready": not lf_df.empty,
        },
        "🧭 ภาพรวมรายทิศทาง": {
            "title": "🧭 ภาพรวมรายทิศทาง",
            "subtitle": "รายได้ · ต้นทุน · กำไร · CM · Load Factor ของแต่ละทิศทางในหน้าเดียว",
            "ready": True,
        },
    }

    # อ่านค่าที่ผู้ใช้เลือกจาก session state ก่อน
    current_dashboard = st.session_state.get(
        "dashboard_selector",
        "🚛 Transportation Cost",
    )

    dashboard_meta = DASHBOARD_OPTIONS[
        current_dashboard
    ]

    st.markdown(
        f"""
        <div class="top-header">
            <h1>{dashboard_meta["title"]}</h1>
            <p>{dashboard_meta["subtitle"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df.empty and ar_df.empty and lf_df.empty and not _lf_file_signature():
        st.warning(
            "ยังไม่มีข้อมูลในระบบ กรุณาไปที่ Data Management และเพิ่มไฟล์ Excel ก่อน"
        )
        st.stop()

    df = df.copy()
    df["_DashboardYear"] = get_year_series(df)
    df["_Route"] = make_route(df)

    # ใช้เดือนจาก Travel Req. Date เป็นหลัก
    # เพราะคอลัมน์ Month ใน Excel บางไฟล์ถูกอ่านเป็นวันที่ปี 1900
    if "Travel Req. Date" in df.columns:
        _travel_date = pd.to_datetime(
            df["Travel Req. Date"], 
            errors="coerce", format="%d/%m/%Y"
        )
        df["_MonthNum"] = _travel_date.dt.month
    else:
        _month_raw = pd.to_numeric(
            df.get("Month", pd.Series(index=df.index, dtype=float)),
            errors="coerce",
        )
        df["_MonthNum"] = _month_raw.where(
            _month_raw.between(1, 12)
        )

    # Numeric cleanup
    for c in [
        "Total Cost",
        "รวมต้นทุนค่าเดินทาง",
        "รวมต้นทุนค่าซ่อม",
        "Total Freight",
        "fuel_actual_amount",
        "fuel_liters",
    ]:
        if c in df.columns:
            df[c] = numeric_series(df, c)

    distance_col = find_column(
        df,
        ["Distance", "Total Distance", "ระยะทาง", "Distance (km)", "KM"],
    )

    if distance_col:
        df[distance_col] = pd.to_numeric(df[distance_col], errors="coerce").fillna(0)

    # -----------------------------------------------------
    # GLOBAL FILTERS
    # -----------------------------------------------------

    st.markdown('<div class="section-title">ตัวกรองข้อมูล</div>', unsafe_allow_html=True)

    # -----------------------------------------------------
    # DASHBOARD SELECTOR
    # -----------------------------------------------------

    dashboard_choice = st.selectbox(
        "เลือก Dashboard ที่ต้องการดู",
        list(DASHBOARD_OPTIONS.keys()),
        key="dashboard_selector",
        help=(
            "เมื่อเพิ่มไฟล์ข้อมูลประเภทอื่นในอนาคต "
            "สามารถเชื่อมเข้ากับ Dashboard แต่ละหมวดได้"
        ),
    )

    # Route to each dashboard directly.
    # Do not use the old generic "ready" gate because it could stop the page
    # before the user can open a dashboard whose dataset is independent.
    if dashboard_choice == "🧭 ภาพรวมรายทิศทาง":
        # โค้ดหน้าภาพรวมรายทิศทาง อยู่ในไฟล์ direction_overview.py
        render_direction_overview_dashboard()
        finish_export()
        st.stop()

    if dashboard_choice == "📊 Load Factor":
        # โค้ดหน้า Load Factor อยู่ในไฟล์ load_factor.py
        if lf_df.empty:
            lf_df, lf_sources = load_vehicle_performance_files(_lf_file_signature())
        render_load_factor_dashboard(
            lf_df,
            lf_sources,
        )
        finish_export()
        st.stop()

    if dashboard_choice == "💳 AR & Collection":
        # [แก้ไข 2/2] ใช้หน้าลูกหนี้ใหม่จาก ar_dashboard.py
        # (อ่านไฟล์ที่ชื่อมีคำว่า "ลูกหนี้" ในโฟลเดอร์ data ตรง ๆ ไม่ผ่านฐานข้อมูล)
        # หน้าเก่า render_ar_dashboard(ar_df, ar_summary_df) ยังเก็บไว้ในไฟล์นี้ แต่ไม่ได้เรียกใช้
        render_ar_page()
        finish_export()
        st.stop()

    if dashboard_choice == "🚚 เที่ยวเปล่า & รถว่างไปสาขา":
        # โค้ดหน้าเที่ยวเปล่า & รถว่างไปสาขา อยู่ในไฟล์ empty_trip.py
        render_empty_trip_page(
            df
        )
        finish_export()
        st.stop()

    if dashboard_choice == "👥 Customer Profitability":
        # โค้ดหน้ากำไรลูกค้าและประเภทสินค้า อยู่ในไฟล์ customer_profit.py
        render_customer_profit_dashboard()
        finish_export()
        st.stop()

    if dashboard_choice == "🚛 Transportation Cost" and df.empty:
        st.error(
            "ยังไม่มีข้อมูล Transportation Cost ในฐานข้อมูลปัจจุบัน "
            "ระบบจะไม่ดึงข้อมูลจากไฟล์เก่าที่ถูกลบกลับมาอัตโนมัติ"
        )
        st.stop()

    # -----------------------------------------------------
    # TRANSPORTATION COST — มุมมองเส้นทาง (ไฟล์กล้วยไม้ / Total Cost)
    # โค้ดอยู่ในไฟล์ transport_cost_route.py
    # -----------------------------------------------------
    render_transport_cost_dashboard(df)
    finish_export()


# =========================================================
# DATA MANAGEMENT
# =========================================================

else:

    st.markdown(
        """
        <div class="top-header">
            <h1>📂 Data Management</h1>
            <p>นำเข้า Excel → สร้าง DuckDB → Dashboard อ่านจากฐานข้อมูลโดยตรง</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "หน้านี้ใช้สำหรับเพิ่มไฟล์ใหม่ อัปเดต/แทนที่ไฟล์เดิม และลบไฟล์ "
        "นอกจากนี้ ถ้าเปิด Excel ที่อยู่ในโฟลเดอร์ data แล้วแก้ข้อมูลและกด Save "
        "ระบบจะตรวจพบและอัปเดต DuckDB ให้อัตโนมัติ\n\n"
        "ไฟล์ Excel สามารถมีสูตรได้ แต่ควรเปิดใน Excel และกด Save ก่อนอัปโหลด "
        "เพื่อให้ค่าที่คำนวณล่าสุดถูกบันทึกไว้"
    )

    upload_mode = st.radio(
        "ต้องการทำอะไรกับไฟล์",
        [
            "➕ เพิ่มไฟล์ใหม่",
            "♻️ อัปเดต/แทนที่ไฟล์เดิม",
        ],
        horizontal=True,
    )

    uploaded_files = st.file_uploader(
        "เลือกไฟล์ Excel",
        type=["xlsx"],
        accept_multiple_files=True,
    )

    st.caption(
        "🔒 Load Factor ใช้ Source เฉพาะ `ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่.xlsx` เท่านั้น "
        "ไฟล์อื่นจะไม่ถูกนำมาใช้คำนวณ Load Factor"
    )

    if upload_mode == "➕ เพิ่มไฟล์ใหม่":

        if uploaded_files and st.button(
            "➕ เพิ่มข้อมูลเข้าสู่ระบบ",
            type="primary",
        ):
            hashes = existing_hashes()
            added = 0
            skipped = 0

            for uploaded in uploaded_files:
                content = uploaded.getvalue()
                current_hash = file_hash(content)

                # ---------------------------------------------------------
                # COST SOURCE REPLACEMENT
                # ---------------------------------------------------------
                # ไฟล์ต้นทุนใหม่จะ "แทนที่" Cost source เดิมอัตโนมัติ
                # โดยไม่แตะ Load Factor source ที่ล็อกไว้
                def _norm_filename(name):
                    return re.sub(r"[^a-z0-9ก-๙]+", "", str(name).casefold())

                def _looks_like_cost_source(path_or_name):
                    n = _norm_filename(path_or_name)
                    cost_words = [
                        "cost", "ต้นทุน", "ค่าเดินทาง", "transportationcost",
                        "travelcost", "costdashboard"
                    ]
                    lf_words = [
                        "loadfactor", "loadfactor", "ค่าเดินทางrevenue3ปีloadfactorใหม่"
                    ]
                    if any(x in n for x in lf_words):
                        return False
                    return any(x in n for x in cost_words)

                is_new_cost = _looks_like_cost_source(uploaded.name)

                if is_new_cost:
                    # ลบ Cost source เดิมเท่านั้น
                    # ห้ามลบไฟล์ Load Factor
                    for old_file in DATA_FOLDER.iterdir():
                        if not old_file.is_file():
                            continue
                        if old_file.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
                            continue
                        if old_file.name.startswith("~$"):
                            continue
                        if old_file.name == uploaded.name:
                            continue
                        if _looks_like_cost_source(old_file.name):
                            try:
                                old_file.unlink()
                            except Exception:
                                pass

                if current_hash in hashes:
                    st.warning(
                        f"⚠️ {uploaded.name} มีไฟล์ที่เหมือนกันอยู่แล้ว"
                    )
                    skipped += 1
                    continue

                save_path = DATA_FOLDER / uploaded.name

                # ถ้าชื่อซ้ำแต่เป็นคนละเนื้อหา ให้ตั้งชื่อใหม่
                if save_path.exists():
                    stem = save_path.stem
                    suffix = save_path.suffix
                    counter = 2

                    while save_path.exists():
                        save_path = (
                            DATA_FOLDER
                            / f"{stem}_{counter}{suffix}"
                        )
                        counter += 1

                save_path.write_bytes(content)
                hashes[current_hash] = save_path.name
                added += 1

            if added:
                with st.spinner(
                    "กำลังนำเข้าข้อมูลและสร้างฐานข้อมูลใหม่..."
                ):
                    rebuild_database()

                st.cache_data.clear()
                sync_signature_baseline()
                st.success(
                    f"✅ เพิ่มข้อมูลสำเร็จ {added} ไฟล์ "
                    "และ Dashboard อัปเดตแล้ว"
                )
                st.rerun()

            if skipped and not added:
                st.info("ไม่มีไฟล์ใหม่ที่ต้องเพิ่ม")

    else:

        existing_update_files = sorted(
            [
                f
                for f in DATA_FOLDER.glob("*.xlsx")
                if not f.name.startswith("~$")
            ],
            key=lambda p: p.name.lower(),
        )

        if not existing_update_files:
            st.warning(
                "ยังไม่มีไฟล์เดิมในระบบให้อัปเดต"
            )

        elif len(uploaded_files or []) > 1:
            st.warning(
                "โหมดอัปเดต/แทนที่ ให้เลือก Excel ใหม่เพียง 1 ไฟล์ต่อครั้ง"
            )

        else:
            target_file_name = st.selectbox(
                "เลือกไฟล์เดิมที่ต้องการอัปเดต",
                [f.name for f in existing_update_files],
            )

            st.caption(
                "ระบบจะเก็บชื่อไฟล์เดิมไว้ แต่แทนที่เนื้อหาด้วยไฟล์ที่อัปโหลดใหม่ "
                "จากนั้นสร้าง DuckDB ใหม่และอัปเดต Dashboard"
            )

            if uploaded_files and st.button(
                "♻️ อัปเดตไฟล์นี้",
                type="primary",
            ):
                uploaded = uploaded_files[0]
                target_path = (
                    DATA_FOLDER / target_file_name
                )

                try:
                    target_path.write_bytes(
                        uploaded.getvalue()
                    )

                    with st.spinner(
                        "กำลังอัปเดตไฟล์และสร้างฐานข้อมูลใหม่..."
                    ):
                        rebuild_database()

                    st.cache_data.clear()
                    sync_signature_baseline()

                    st.success(
                        f"✅ อัปเดต {target_file_name} สำเร็จ "
                        "และ Dashboard ใช้ข้อมูลล่าสุดแล้ว"
                    )

                    st.rerun()

                except Exception as e:
                    st.error(
                        f"อัปเดตไฟล์ไม่ได้: {e}"
                    )

    st.divider()
    st.markdown("### 📁 ไฟล์ข้อมูลที่มีอยู่ในระบบ")

    files = sorted(
        [
            f
            for f in DATA_FOLDER.glob("*.xlsx")
            if not f.name.startswith("~$")
        ],
        key=lambda p: p.name.lower(),
    )

    if not files:
        st.warning("ยังไม่มีไฟล์ Excel ในระบบ")
    else:
        for idx, file in enumerate(files, 1):
            c1, c2 = st.columns([6, 1])

            with c1:
                size_mb = file.stat().st_size / 1024 / 1024
                st.write(f"{idx}. ✅ {file.name}  —  {size_mb:.1f} MB")

            with c2:
                if st.button(
                    "🗑️ ลบ",
                    key=f"delete_{file.name}",
                ):
                    try:
                        file.unlink()

                        with st.spinner("กำลังอัปเดตฐานข้อมูล..."):
                            rebuild_database()

                        st.cache_data.clear()
                        sync_signature_baseline()
                        st.success(f"ลบ {file.name} สำเร็จ")
                        st.rerun()

                    except Exception as e:
                        st.error(f"ลบไฟล์ไม่ได้: {e}")

    st.divider()

    if st.button("🔄 สร้างฐานข้อมูลใหม่จากไฟล์ปัจจุบัน"):
        with st.spinner("กำลังสร้างฐานข้อมูล..."):
            rebuild_database()

        st.cache_data.clear()
        sync_signature_baseline()
        st.success("สร้างฐานข้อมูลใหม่เรียบร้อย — ใช้เฉพาะไฟล์ Excel ที่อยู่ใน data/ ปัจจุบัน")
        st.rerun()

    if DB_PATH.exists():
        st.caption(
            f"Database: {DB_PATH.name} | "
            f"แก้ไขล่าสุด {pd.Timestamp.fromtimestamp(DB_PATH.stat().st_mtime).strftime('%d/%m/%Y %H:%M')}"
        )