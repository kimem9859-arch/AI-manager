"""App configuration: page config, session state, status options, Gemini API."""
import os
import streamlit as st
import google.generativeai as genai

# Page config (call once at startup)
def init_page_config():
    st.set_page_config(page_title="내 AI 프로젝트 매니저", page_icon="🤖", layout="wide")


def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_ai_response" not in st.session_state:
        st.session_state.last_ai_response = None


# Status options for task sheet
STATUS_OPTIONS = ["대기/보류", "진행", "수정/검토", "완료"]


def get_gemini_model():
    """Configure Gemini and return model instance, or None if no API key."""
    api_key = None
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    if not api_key:
        api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-2.5-pro")
    return None
