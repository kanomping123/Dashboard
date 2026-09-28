"""auth.py — หน้าใส่รหัสผ่านก่อนเข้าแดชบอร์ด (รหัสอยู่ใน st.secrets["APP_PASSWORD"])"""
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
