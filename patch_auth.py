import json
from getpass import getpass
from pathlib import Path

AUTH = r'''"""auth.py — หน้าใส่รหัสผ่านก่อนเข้าแดชบอร์ด (รหัสอยู่ใน st.secrets["APP_PASSWORD"])"""
import hmac
import time

import streamlit as st


def _configured_password():
    try:
        value = str(st.secrets["APP_PASSWORD"])
    except Exception:
        return None
    return value or None


def require_login():
    """เรียกต้นไฟล์ app.py: ถ้ายังไม่ล็อกอิน จะแสดงหน้ารหัสผ่านแล้วหยุดหน้าที่เหลือทั้งหมด"""
    password = _configured_password()
    if password is None:
        st.error("ยังไม่ได้ตั้ง APP_PASSWORD ใน secrets — ระบบล็อกไว้เพื่อความปลอดภัย")
        st.stop()

    if st.session_state.get("_auth_ok"):
        return

    st.markdown(
        "<div style='max-width:420px;margin:12vh auto 0;text-align:center'>"
        "<div style='font-size:44px'>🚚</div>"
        "<h2 style='margin:6px 0 2px'>Transportation Dashboard</h2>"
        "<p style='color:#64748B'>กรุณาใส่รหัสผ่านเพื่อเข้าดูข้อมูล</p></div>",
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("login_form"):
            typed = st.text_input("รหัสผ่าน", type="password")
            submitted = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True)
        if submitted:
            if hmac.compare_digest(typed.encode("utf-8"), password.encode("utf-8")):
                st.session_state["_auth_ok"] = True
                st.rerun()
            else:
                time.sleep(1)
                st.error("รหัสผ่านไม่ถูกต้อง")
    st.stop()
'''

# ---------- auth.py ----------
Path("auth.py").write_text(AUTH, encoding="utf-8")
print("✓ auth.py: สร้างแล้ว")

# ---------- .streamlit/secrets.toml ----------
sec = Path(".streamlit/secrets.toml")
sec.parent.mkdir(exist_ok=True)
old = sec.read_text(encoding="utf-8") if sec.exists() else ""
if "APP_PASSWORD" in old:
    print("- secrets.toml: มีรหัสอยู่แล้ว ข้าม")
else:
    pw = getpass("ตั้งรหัสผ่านสำหรับเข้าแดชบอร์ด (พิมพ์แล้วไม่แสดงบนจอ): ").strip()
    if not pw:
        print("✗ ไม่ได้ใส่รหัส — รันสคริปต์ใหม่อีกครั้ง")
        raise SystemExit
    sep = "\n" if old and not old.endswith("\n") else ""
    sec.write_text(old + sep + f"APP_PASSWORD = {json.dumps(pw, ensure_ascii=False)}\n", encoding="utf-8")
    print("✓ .streamlit/secrets.toml: บันทึกรหัสแล้ว")

# ---------- .gitignore ----------
gi = Path(".gitignore")
lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
need = [".streamlit/secrets.toml", "*.bak", "__pycache__/", "dashboard.duckdb", "dashboard.duckdb.tmp"]
add = [x for x in need if x not in lines]
if add:
    gi.write_text("\n".join(lines + add) + "\n", encoding="utf-8")
    print("✓ .gitignore: เพิ่ม " + ", ".join(add))
else:
    print("- .gitignore: ครบแล้ว ข้าม")

# ---------- app.py ----------
p = Path("app.py")
if not p.exists():
    print("✗ ไม่พบ app.py")
else:
    text = p.read_text(encoding="utf-8")
    if "require_login" in text:
        print("- app.py: แก้ไว้แล้ว ข้าม")
    else:
        edits = [
            ("from database import rebuild_database\n",
             "from database import rebuild_database\nfrom auth import require_login\n"),
            ('apply_theme()\n\nDATA_FOLDER = Path("data")',
             'apply_theme()\n\n# ต้องใส่รหัสผ่านก่อนเห็นอะไรทั้งหมด\nrequire_login()\n\nDATA_FOLDER = Path("data")'),
        ]
        if all(text.count(o) == 1 for o, _ in edits):
            bak = p.with_name("app.py.auth.bak")
            if not bak.exists():
                bak.write_text(text, encoding="utf-8")
            for o, n in edits:
                text = text.replace(o, n)
            p.write_text(text, encoding="utf-8")
            print("✓ app.py: แก้แล้ว")
        else:
            print("✗ app.py: หาข้อความเดิมไม่เจอ (ต้องแก้มือ)")

# ---------- requirements.txt ----------
req = Path("requirements.txt")
if not req.exists():
    print("⚠ ไม่พบ requirements.txt (Streamlit Cloud ต้องใช้ไฟล์นี้)")
else:
    raw = req.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw:
        print("⚠ requirements.txt เป็นไฟล์ UTF-16 — Streamlit Cloud อ่านไม่ได้ ให้เปิดใน VS Code แล้ว Save with Encoding → UTF-8")
    else:
        low = raw.decode("utf-8", errors="ignore").lower()
        for name in ["streamlit", "pandas", "duckdb", "plotly", "openpyxl"]:
            if name not in low:
                print(f"⚠ requirements.txt ยังไม่มี {name}")
print("เสร็จ — หยุดแล้วรัน python -m streamlit run app.py ใหม่ ต้องเห็นหน้าใส่รหัสผ่านก่อน")
