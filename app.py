import streamlit as st

from senad_app.ui import run

st.set_page_config(
    page_title="سیستم ثبت و چاپ سند کارپردازی",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

run()
