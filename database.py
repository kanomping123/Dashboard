"""
database.py
-----------
อ่านไฟล์ Excel ทุกไฟล์ในโฟลเดอร์ data/ แล้วสร้างฐานข้อมูล dashboard.duckdb
ให้ app.py ใช้งาน

ตารางที่สร้าง (ชื่อตรงกับที่ app.py เรียกใช้):
    trips       ข้อมูลรายเที่ยว/ต้นทุนขนส่ง  -> หน้า Transportation Cost, เที่ยวเปล่า
    ar_detail   รายละเอียดลูกหนี้รายบิล       -> หน้า AR & Collection
    ar_summary  ชีตสรุปลูกหนี้ (แบ่งชั้นลูกหนี้) -> หน้า AR & Collection

วิธีทำงาน:
    - ไม่ยึดชื่อไฟล์หรือชื่อชีต แต่ดูจาก "หัวตาราง" ว่าชีตนั้นเป็นข้อมูลประเภทไหน
    - หาแถวหัวตารางเองใน 30 แถวแรก (รองรับชีตที่มีหัวรายงานอยู่ด้านบน)
    - เก็บเลขแถวใน Excel ของแต่ละรายการไว้ในคอลัมน์ _source_row
      เพื่อให้กลับไปหาแถวต้นฉบับในไฟล์ได้
    - ไฟล์ Load Factor (ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่) app.py อ่านเองโดยตรง
      จึงไม่ต้องเปิดอ่านที่นี่ (ประหยัดเวลา) ยกเว้นไม่มีไฟล์อื่นที่มีข้อมูลรายเที่ยวเลย

ทดสอบแยกได้ด้วยคำสั่ง:  python database.py
"""

import os
import re
import time
from pathlib import Path

import duckdb
import pandas as pd

DATA_FOLDER = Path("data")
DB_PATH = Path("dashboard.duckdb")

LOAD_FACTOR_FILE_KEY = "ค่าเดินทาง+Revenue3ปี=Loadfactorใหม่"
HEADER_SCAN_ROWS = 30


def _norm(value) -> str:
    """ตัดช่องว่าง/ขีด/ขีดล่าง และตัวพิมพ์ใหญ่เล็ก เพื่อเทียบชื่อคอลัมน์"""
    return re.sub(r"[\s_\-]+", "", str(value).strip().casefold())


# ---------------------------------------------------------------------------
# ชื่อคอลัมน์ที่ app.py ใช้จริง — ถ้าชื่อใน Excel ต่างแค่ช่องว่าง/ตัวพิมพ์
# จะถูกเปลี่ยนเป็นชื่อมาตรฐานนี้ให้อัตโนมัติ
# ---------------------------------------------------------------------------
CANONICAL_COLUMNS = [
    # รายเที่ยว
    "Travel Req. No.", "Travel Req. Date", "Manifest Type", "Loading", "Unloading",
    "Branch", "Vehicle Type", "Vehicle Model", "License Plate", "Year", "Month",
    "Distance", "Total Distance", "ระยะทาง", "Distance (km)", "KM",
    "fuel_actual_amount", "fuel_liters",
    # คอลัมน์ต้นทุน
    "Total Cost", "รวมต้นทุนค่าเดินทาง", "รวมต้นทุนค่าซ่อม", "รวมค่าเสื่อม", "Total Cash",
    "Total Freight", "Fuel (Cash)", "Driver Allowance", "Backup Driver Allowance",
    "Off-Route", "Off-Route Fuel", "Tarpaulin Fee", "Goods Fuel", "Pickup Cost",
    "Police Fee", "โยกค่าน้ำมันขาขึ้น", "โยกต้นทุนเที่ยวยกเลิก", "ค่าน้ำมันตามจริง",
    "ยอดปันส่วนค่าน้ำมันตามจริง", "โยกค่าน้ำมันตามจริง", "ยอดปันส่วนโยกค่าน้ำมันตามจริง",
    # ลูกหนี้
    "ชื่อลูกหนี้", "จำนวนเงิน", "สาขา", "วันที่วางบิลได้", "วันที่จบ(วันที่จ่าย)",
    "วันครบกำหนด(Due Date)", "วันที่ปัจจุบัน",
    "จำนวนบิลทั้งหมด", "จำนวนบิลที่ช้า", "รวมวันช้า", "วันช้าสูงสุด",
    "เปอร์เซนต์บิลที่ช้า", "แบ่งชั้นลูกหนี้",
]
_CANONICAL_LOOKUP = {_norm(c): c for c in CANONICAL_COLUMNS}

# คอลัมน์ที่ใช้ "จำแนก" ว่าชีตเป็นข้อมูลประเภทไหน
TRIP_KEYS = [
    "Travel Req. No.", "Travel Req. Date", "Total Cost", "Manifest Type",
    "Loading", "Unloading", "License Plate", "Vehicle Model", "Vehicle Type",
]
AR_DETAIL_KEYS = [
    "ชื่อลูกหนี้", "จำนวนเงิน", "วันครบกำหนด(Due Date)", "วันที่วางบิลได้",
    "วันที่จบ(วันที่จ่าย)", "สาขา",
]
AR_SUMMARY_KEYS = [
    "ชื่อลูกหนี้", "แบ่งชั้นลูกหนี้", "จำนวนบิลทั้งหมด", "จำนวนบิลที่ช้า",
    "วันช้าสูงสุด", "เปอร์เซนต์บิลที่ช้า",
]


def _count_matches(cells, keys) -> int:
    present = {_norm(c) for c in cells if pd.notna(c) and str(c).strip()}
    return sum(1 for k in keys if _norm(k) in present)


def _classify_row(cells):
    """คืน (ประเภท, คะแนน) ของแถวที่อาจเป็นหัวตาราง"""
    present = {_norm(c) for c in cells if pd.notna(c) and str(c).strip()}
    debtor = _norm("ชื่อลูกหนี้") in present

    summary = _count_matches(cells, AR_SUMMARY_KEYS)
    if debtor and _norm("แบ่งชั้นลูกหนี้") in present:
        return "ar_summary", summary

    detail = _count_matches(cells, AR_DETAIL_KEYS)
    if debtor and _norm("จำนวนเงิน") in present and detail >= 3:
        return "ar_detail", detail

    trip = _count_matches(cells, TRIP_KEYS)
    if trip >= 3:
        return "trips", trip

    return None, 0


def _clean_columns(columns):
    """ทำชื่อคอลัมน์ให้สะอาด เปลี่ยนเป็นชื่อมาตรฐาน และกันชื่อซ้ำ"""
    result, seen = [], {}
    for i, col in enumerate(columns):
        name = " ".join(str(col).strip().split()) if pd.notna(col) else ""
        if not name or name.lower().startswith("unnamed") or name.lower() == "nan":
            name = f"_col{i}"
        name = _CANONICAL_LOOKUP.get(_norm(name), name)
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        result.append(name)
    return result


def _prepare_for_duckdb(df: pd.DataFrame) -> pd.DataFrame:
    """
    DuckDB รับคอลัมน์ที่ชนิดข้อมูลปนกันไม่ได้
    คอลัมน์ตัวเลข/วันที่ปกติคงชนิดเดิม ส่วนคอลัมน์ที่ปนกันแปลงเป็นข้อความ
    (app.py แปลงกลับเป็นตัวเลข/วันที่เองอยู่แล้ว)
    """
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].map(
                lambda v: None if pd.isna(v) else str(v)
            ).astype("string")
    return out


def _read_sheet(excel: pd.ExcelFile, sheet: str):
    """หาแถวหัวตาราง จำแนกประเภท แล้วอ่านทั้งชีต"""
    try:
        preview = excel.parse(sheet, header=None, nrows=HEADER_SCAN_ROWS)
    except Exception:
        return None, None

    best_kind, best_score, best_row = None, 0, None
    for idx in range(len(preview)):
        kind, score = _classify_row(preview.iloc[idx].tolist())
        if kind and score > best_score:
            best_kind, best_score, best_row = kind, score, idx

    if best_kind is None:
        return None, None

    try:
        df = excel.parse(sheet, header=best_row)
    except Exception:
        return None, None

    df.columns = _clean_columns(df.columns)

    # เลขแถวจริงใน Excel: หัวตารางอยู่แถว best_row + 1 ข้อมูลแถวแรกจึงอยู่แถว best_row + 2
    df.insert(0, "_source_row", df.index + best_row + 2)

    data_cols = [c for c in df.columns if c != "_source_row"]
    df = df.dropna(how="all", subset=data_cols)
    df = df.loc[:, [c for c in df.columns if not (c.startswith("_col") and df[c].isna().all())]]
    return best_kind, df


def _excel_files():
    if not DATA_FOLDER.exists():
        return []
    return sorted(
        f for f in DATA_FOLDER.iterdir()
        if f.is_file()
        and f.suffix.lower() in {".xlsx", ".xlsm", ".xls"}
        and not f.name.startswith("~$")
    )


def _is_load_factor_file(path: Path) -> bool:
    return _norm(LOAD_FACTOR_FILE_KEY) in _norm(path.stem)


def _scan_file(file: Path, verbose: bool, skip_loadfactor_sheets: bool):
    """อ่านทุกชีตในไฟล์ แล้วคืน list ของ (ประเภท, DataFrame)"""
    try:
        excel = pd.ExcelFile(file)
    except Exception as e:
        if verbose:
            print(f"  ✗ เปิดไฟล์ไม่ได้: {file.name} ({e})")
        return []

    results = []
    for sheet in excel.sheet_names:
        # ชีต Load Factor app.py อ่านเองโดยตรง ไม่ต้องนำเข้าฐานข้อมูล
        if skip_loadfactor_sheets and "loadfactor" in _norm(sheet):
            continue

        kind, df = _read_sheet(excel, sheet)
        if kind is None or df is None or df.empty:
            continue

        df["_source_file"] = file.name
        df["_source_sheet"] = sheet
        results.append((kind, df))
        if verbose:
            print(f"  ✓ {file.name} • {sheet} -> {kind} ({len(df):,} แถว)")
    return results


def collect_tables(verbose: bool = False):
    """อ่านทุกไฟล์ใน data/ แล้วจัดกลุ่มเป็น trips / ar_detail / ar_summary"""
    found = {"trips": [], "ar_detail": [], "ar_summary": []}

    files = _excel_files()
    lf_files = [f for f in files if _is_load_factor_file(f)]
    other_files = [f for f in files if not _is_load_factor_file(f)]

    for file in other_files:
        if verbose:
            print(f"กำลังอ่าน {file.name} ...")
        for kind, df in _scan_file(file, verbose, skip_loadfactor_sheets=False):
            found[kind].append(df)

    # ไฟล์ Load Factor ใหญ่มาก จะเปิดอ่านเฉพาะเมื่อไม่มีไฟล์อื่นที่มีข้อมูลรายเที่ยว
    if not found["trips"] and lf_files:
        for file in lf_files:
            if verbose:
                print(f"ไม่พบข้อมูลรายเที่ยวในไฟล์อื่น — อ่านจาก {file.name} ...")
            for kind, df in _scan_file(file, verbose, skip_loadfactor_sheets=True):
                if kind == "trips":
                    found["trips"].append(df)
    elif lf_files and verbose:
        print(f"ข้าม {lf_files[0].name} (หน้า Load Factor อ่านไฟล์นี้เองโดยตรง)")

    return {
        k: pd.concat(v, ignore_index=True, sort=False) if v else pd.DataFrame()
        for k, v in found.items()
    }


def _write_database(path: Path, tables: dict):
    con = duckdb.connect(str(path))
    try:
        for name, df in tables.items():
            if df.empty:
                continue
            con.register("_incoming", _prepare_for_duckdb(df))
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _incoming')
            con.unregister("_incoming")
    finally:
        con.close()


def rebuild_database(verbose: bool = False):
    """
    สร้าง dashboard.duckdb ใหม่ทั้งหมดจากไฟล์ที่อยู่ใน data/ ตอนนี้
    (ข้อมูลจากไฟล์ที่ถูกลบไปแล้วจะไม่ค้างอยู่ในฐานข้อมูล)
    """
    tables = collect_tables(verbose=verbose)

    # เขียนลงไฟล์ชั่วคราวก่อน แล้วค่อยสลับ เพื่อให้หน้าเว็บไม่อ่านฐานข้อมูลที่เขียนไม่เสร็จ
    tmp_path = DB_PATH.with_name(DB_PATH.name + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    _write_database(tmp_path, tables)

    for attempt in range(5):
        try:
            os.replace(tmp_path, DB_PATH)
            break
        except PermissionError:
            # Windows: ไฟล์อาจถูกเปิดอ่านอยู่ชั่วขณะ รอแล้วลองใหม่
            time.sleep(0.5 * (attempt + 1))
    else:
        # สลับไฟล์ไม่ได้ ให้เขียนทับในไฟล์เดิมแทน
        tmp_path.unlink(missing_ok=True)
        con = duckdb.connect(str(DB_PATH))
        try:
            for name in ("trips", "ar_detail", "ar_summary"):
                con.execute(f'DROP TABLE IF EXISTS "{name}"')
        finally:
            con.close()
        _write_database(DB_PATH, tables)

    return {k: len(v) for k, v in tables.items()}


if __name__ == "__main__":
    print(f"กำลังอ่านไฟล์ใน {DATA_FOLDER.resolve()} ...")
    counts = rebuild_database(verbose=True)
    print("\nสร้างฐานข้อมูลเสร็จ:", DB_PATH.resolve())
    for name, n in counts.items():
        status = f"{n:,} แถว" if n else "ไม่พบข้อมูล"
        print(f"  {name:<11} {status}")