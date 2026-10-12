import streamlit as st

from dashboard_app.ui import run_app

st.set_page_config(
    page_title="داشبورد مالی و عملیاتی لجستیک",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

run_app()
