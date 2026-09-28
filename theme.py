"""
theme.py
--------
ธีมสีแดง-ขาวพาสเทล ใช้ร่วมกันทุกแดชบอร์ด

เรียก apply_theme() ครั้งเดียวที่ต้นไฟล์ app.py (หลัง st.set_page_config) แล้ว:
- พื้นหลัง, หัวแดชบอร์ด, ตัวกรอง, แท็ก, แท็บ, ปุ่ม, การ์ดตัวเลข (st.metric) เป็นโทนเดียวกันทุกหน้า
- กล่อง st.container(border=True) ทุกอันกลายเป็นการ์ดสีขาวขอบมน
- กราฟ Plotly ทุกกราฟใช้ชุดสีพาสเทลเดียวกัน ฟอนต์ไทยเดียวกัน
- หน้า Load Factor เปลี่ยนจากโทนน้ำเงินเป็นโทนเดียวกับหน้าอื่น
"""

import inspect
import itertools

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

PALETTE = [
    "#F07C8C", "#7CC4D6", "#F6AE6B", "#95B8E6", "#E68FBF",
    "#86CFA3", "#BBA0E3", "#EFCB64", "#E98A7C", "#86B2C4",
    "#F4A6B6", "#AFD481", "#D9A47F", "#A3AAE6", "#EE9A9A",
    "#7FC9C0", "#F9C98A", "#CD99D6", "#8FC3EE", "#A5D6A7",
]
# สีสื่อความหมาย (ดี / เฝ้าระวัง / แย่) แบบพาสเทล
GOOD, WATCH, BAD = "#6CC49A", "#F2C45A", "#EC7F86"
FONT = "Noto Sans Thai, IBM Plex Sans Thai, sans-serif"

THEME_CSS = """
<style>
/* ---------- พื้นหลัง ---------- */
.stApp { background: linear-gradient(160deg, #FAD4DB 0%, #FCE4E8 38%, #FFF3F5 100%) fixed !important; }
[data-testid="stAppViewContainer"], [data-testid="stMain"] { background: transparent !important; }
[data-testid="stHeader"] { background: transparent !important; }
.block-container { padding-top: 1.6rem !important; max-width: 1480px; }
.stApp p, .stApp label { color: #1E293B; }
.stApp [data-testid="stCaptionContainer"] { color: #64748B !important; }

/* ---------- หัวแดชบอร์ด ---------- */
.top-header {
    background: linear-gradient(120deg, #E25A70 0%, #EE8193 55%, #F6AAB6 100%);
    border-radius: 20px; padding: 22px 28px; margin-bottom: 14px;
    box-shadow: 0 10px 30px rgba(226, 90, 112, .25);
}
.top-header h1 { color: #FFFFFF !important; margin: 0 !important; font-size: 28px !important; }
.top-header p { color: rgba(255, 255, 255, .88) !important; margin: 4px 0 0 !important; font-size: 14px; }

/* ---------- หัวข้อส่วน ---------- */
.section-title {
    font-size: 15px; font-weight: 700; color: #0F172A; margin: 14px 0 8px;
    padding-left: 10px; border-left: 4px solid #E8687C; line-height: 1.3;
}

/* ---------- การ์ด (st.container(border=True) และการ์ดของหน้า Transportation) ---------- */
div[class*="st-key-tccard_"] {
    background: #FFFFFF; border: 1px solid #F4D8DE; border-radius: 18px;
    padding: 18px 20px 16px; margin-top: 4px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .04), 0 8px 24px rgba(226, 90, 112, .08);
}
div[class*="st-key-tccard_"] h4, div[class*="st-key-tccard_"] h3 {
    font-size: 17px !important; font-weight: 700 !important; color: #0F172A !important;
    padding: 0 0 2px !important; margin: 0 !important;
}
div[class*="st-key-tccard_"] label p { color: #475569 !important; font-size: 12.5px !important; font-weight: 600 !important; }

/* ---------- การ์ดตัวเลข (st.metric) ---------- */
[data-testid="stMetric"] {
    background: #FFFFFF; border: 1px solid #F4D8DE; border-radius: 18px; padding: 14px 16px !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .04), 0 8px 24px rgba(226, 90, 112, .08);
}
[data-testid="stMetricLabel"] p { color: #64748B !important; font-weight: 600 !important; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div { color: #0F172A !important; }

/* ---------- ช่องเลือก / แท็ก / แท็บ / ปุ่ม ---------- */
div[data-baseweb="select"] > div { background: #FFFFFF !important; border-color: #F4D6DC !important; border-radius: 10px !important; }
div[data-baseweb="select"] * { color: #1E293B; }
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="textarea"],
[data-testid="stNumberInputContainer"], [data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input, [data-testid="stDateInput"] input {
    background: #FFFFFF !important; color: #1E293B !important; border-color: #F4D6DC !important;
}
[data-testid="stNumberInput"] button { background: #FFF1F4 !important; color: #C23B53 !important; }
div[data-baseweb="popover"] ul, div[data-baseweb="menu"] { background: #FFFFFF !important; }
div[data-baseweb="popover"] li { color: #1E293B !important; }
/* ---------- บังคับช่องเลือก/ช่องกรอกเป็นสีขาว แม้ Streamlit เปิดโหมดมืด ---------- */
div[data-baseweb="select"] div, div[data-baseweb="select"] input,
div[data-baseweb="input"], div[data-baseweb="input"] div, div[data-baseweb="input"] input,
div[data-baseweb="base-input"], div[data-baseweb="base-input"] input,
div[data-baseweb="textarea"], div[data-baseweb="textarea"] textarea,
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input, [data-testid="stDateInput"] input {
    background-color: #FFFFFF !important; color: #1E293B !important; -webkit-text-fill-color: #1E293B !important;
}
div[data-baseweb="select"] > div, div[data-baseweb="input"], div[data-baseweb="textarea"] {
    border: 1px solid #F4D6DC !important; border-radius: 10px !important;
}
div[data-baseweb="select"] input::placeholder, div[data-baseweb="input"] input::placeholder { color: #94A3B8 !important; -webkit-text-fill-color: #94A3B8 !important; }
div[data-baseweb="select"] svg, div[data-baseweb="input"] svg { color: #94A3B8 !important; fill: #94A3B8 !important; }
[data-testid="stNumberInput"] button { background: #FFF1F4 !important; color: #C23B53 !important; border: none !important; }
[data-testid="stNumberInput"] button svg { fill: #C23B53 !important; color: #C23B53 !important; }
/* รายการที่เด้งลงมา */
div[data-baseweb="popover"] > div, div[data-baseweb="popover"] ul, ul[role="listbox"],
div[data-baseweb="menu"] { background: #FFFFFF !important; border-radius: 12px !important; }
li[role="option"], div[data-baseweb="popover"] li { background: #FFFFFF !important; color: #1E293B !important; }
li[role="option"]:hover, li[role="option"][aria-selected="true"] { background: #FFF1F4 !important; color: #C23B53 !important; }
li[role="option"] * { color: inherit !important; }
/* แท็กในช่องเลือกหลายรายการ: คงสีชมพู */
div[data-baseweb="select"] span[data-baseweb="tag"] div, div[data-baseweb="select"] span[data-baseweb="tag"] span { background: transparent !important; color: #C23B53 !important; -webkit-text-fill-color: #C23B53 !important; }
div[data-baseweb="select"] span[data-baseweb="tag"] { background: #FFE8EC !important; }
/* ปุ่ม radio / checkbox ให้เป็นโทนชมพู */
label[data-baseweb="radio"] div:first-child, label[data-baseweb="checkbox"] span:first-child { border-color: #E8687C !important; }
span[data-baseweb="tag"] { background: #FFE8EC !important; color: #C23B53 !important; border-radius: 8px !important; }
span[data-baseweb="tag"] span { color: #C23B53 !important; }
button[data-baseweb="tab"] p { font-weight: 600 !important; color: #64748B !important; }
button[data-baseweb="tab"][aria-selected="true"] p { color: #E25A70 !important; }
div[data-baseweb="tab-highlight"] { background: #E25A70 !important; }
.stDownloadButton button, div[data-testid="stPopover"] button, .stButton button[kind="secondary"] {
    border-radius: 10px !important; border: 1px solid #FAD1D9 !important;
    background: #FFF3F5 !important; color: #C23B53 !important; font-weight: 600 !important;
}
.stButton button[kind="primary"] {
    border-radius: 10px !important; border: none !important; font-weight: 700 !important;
    background: linear-gradient(120deg, #E25A70, #EE8193) !important;
}
[data-testid="stExpander"] details {
    background: #FFFFFF; border: 1px solid #F4D8DE !important; border-radius: 14px !important;
}
[data-testid="stFileUploaderDropzone"] { background: #FFF7F8 !important; border: 1px dashed #F4A3B1 !important; border-radius: 14px !important; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
hr { border-color: #F4D6DC !important; }

/* ---------- หน้า Load Factor: เปลี่ยนจากน้ำเงินเป็นโทนเดียวกัน ---------- */
.lf-new-header {
    background: linear-gradient(120deg, #E25A70 0%, #EE8193 55%, #F6AAB6 100%) !important;
    border-radius: 20px !important; box-shadow: 0 10px 30px rgba(226, 90, 112, .25) !important;
}
.lf-filter-title { color: #0F172A !important; }
.lf-kpi { border: 1px solid #F4D8DE !important; border-radius: 16px !important;
          box-shadow: 0 1px 2px rgba(15, 23, 42, .04), 0 8px 24px rgba(226, 90, 112, .08) !important; }
.lf-kpi-icon { color: #E25A70 !important; }
.lf-kpi-label, .lf-kpi-unit { color: #64748B !important; }
.lf-kpi-value { color: #0F172A !important; }
</style>
"""


def _plotly_template() -> go.layout.Template:
    t = go.layout.Template(pio.templates["plotly_white"])
    t.layout.colorway = PALETTE
    t.layout.piecolorway = PALETTE
    t.layout.font = dict(family=FONT, color="#475569", size=12)
    t.layout.paper_bgcolor = "rgba(0,0,0,0)"
    t.layout.plot_bgcolor = "rgba(0,0,0,0)"
    t.layout.hoverlabel = dict(bgcolor="white", bordercolor="#F4D6DC",
                               font=dict(family=FONT, color="#1E293B", size=13))
    for axis in (t.layout.xaxis, t.layout.yaxis):
        axis.gridcolor = "#F6E6E9"
        axis.linecolor = "#F6E6E9"
        axis.zeroline = False
    return t


def _patch_streamlit():
    """ให้ st.container(border=True) เป็นการ์ดขาว และกราฟ Plotly ใช้ชุดสีของธีม"""
    st._nss_counter = itertools.count()  # รีเซ็ตทุกครั้งที่หน้ารันใหม่ ให้ key คงที่
    if getattr(st, "_nss_patched", False):
        return

    orig_container = st.container
    orig_plotly = st.plotly_chart
    supports_key = "key" in inspect.signature(orig_container).parameters

    def container(*args, **kwargs):
        if supports_key and kwargs.get("border") and not kwargs.get("key"):
            kwargs["border"] = False
            kwargs["key"] = f"tccard_auto_{next(st._nss_counter)}"
        if str(kwargs.get("key", "")).startswith("tccard_"):
            kwargs["height"] = "stretch"
        return orig_container(*args, **kwargs)

    def plotly_chart(*args, **kwargs):
        kwargs.setdefault("theme", None)          # ใช้สีของธีมนี้แทนสีมาตรฐาน Streamlit
        kwargs.setdefault("config", {"displayModeBar": False})
        return orig_plotly(*args, **kwargs)

    st.container = container
    st.plotly_chart = plotly_chart
    st._nss_patched = True


def apply_theme():
    if "nss" not in pio.templates:
        pio.templates["nss"] = _plotly_template()
    pio.templates.default = "nss"
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    _patch_streamlit()