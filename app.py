import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import re 
import time

# ----------------------------------------------------------
# 1. 초기 설정 & 함수
# ----------------------------------------------------------
st.set_page_config(page_title="내 AI 프로젝트 매니저", page_icon="🤖", layout="wide")

# 세션 상태 초기화
if "first_visit" not in st.session_state:
    st.session_state.first_visit = True

# 사용 설명서 팝업
@st.dialog("📖 사용 설명서")
def show_guide():
    st.markdown("""
    ### 👋 환영합니다!
    **1. 💬 채팅 비서:** 작업 관리 & 물품 검색
    **2. 📊 작업 리스트:** 할 일 목록 ('작업' 시트)
    **3. 📦 물품 리스트:** 구매 목록 ('물품' 시트)
    **4. 📱 모바일 모드:** 사이드바 설정
    """)
    if st.button("닫기"):
        st.rerun()

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("API 키 설정 필요")

# ★ 모델 설정 (gemini-2.5-pro 고정)
model = genai.GenerativeModel('gemini-2.5-pro')

def get_spreadsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)
    return client.open("Safety_Project")

# 1. 작업 시트 연결
def connect_to_task_sheet():
    sh = get_spreadsheet()
    try: return sh.worksheet("작업")
    except: return sh.sheet1 

# 2. 공지 시트 연결
def connect_to_notice_sheet():
    sh = get_spreadsheet()
    try: return sh.worksheet("공지")
    except:
        # 없으면 자동 생성
        new = sh.add_worksheet("공지", 10, 2)
        new.update_cell(1,1,"공지없음")
        return new

# 3. ★ [수정됨] 물품 시트 연결 (자동 생성 기능 추가!)
def connect_to_item_sheet():
    sh = get_spreadsheet()
    try:
        return sh.worksheet("물품")
    except:
        # ★ 물품 시트가 없으면 자동으로 만들어줍니다!
        new_sheet = sh.add_worksheet(title="물품", rows="100", cols="6")
        # 헷갈리지 않게 첫 줄에 예시 제목도 넣어줍니다.
        new_sheet.append_row(["품목명", "수량", "가격", "구매처", "링크", "비고"])
        return new_sheet

def get_notice():
    try:
        sh = connect_to_notice_sheet()
        val = sh.cell(1,1).value
        return val if val else "공지없음"
    except: return "-"

def update_notice(txt):
    try:
        connect_to_notice_sheet().update_cell(1,1,txt)
        return True
    except: return False

def update_sheet_any(task, col, val):
    try:
        sh = connect_to_task_sheet()
        cell = sh.find(task)
        col_map = {"상태":3, "비고":4, "세부내용":2}
        idx = col_map.get(col)
        if idx: sh.update_cell(cell.row, idx, val)
        return True
    except: return False

def add_new_task(task):
    try:
        connect_to_task_sheet().append_row([task, "설정필요", "대기", "-"])
        return True
    except: return False

def delete_task(task):
    try:
        sh = connect_to_task_sheet()
        cell = sh.find(task)
        sh.delete_rows(cell.row)
        return True
    except: return False

# ----------------------------------------------------------
# 2. 데이터 로딩
# ----------------------------------------------------------
if st.session_state.first_visit:
    show_guide()
    st.session_state.first_visit = False

# (1) 작업 데이터
try:
    task_sheet = connect_to_task_sheet()
    data = task_sheet.get_all_records()
    df = pd.DataFrame(data)
    total = len(df)
    done = len(df[df['상태']=='완료']) if not df.empty else 0
    pending = len(df[df['상태']=='대기']) if not df.empty else 0
except:
    df = pd.DataFrame()
    total, done, pending = 0,0,0

# (2) 물품 데이터
try:
    item_sheet = connect_to_item_sheet()
    # 시트가 방금 만들어져서 비어있을 수 있으므로 예외 처리
    item_data = item_sheet.get_all_records()
    df_items = pd.DataFrame(item_data)
    if not df_items.empty:
        # 빈칸 채우기 (병합된 셀 대응)
        df_items = df_items.replace("", pd.NA).ffill()
        df_items = df_items.fillna("-")
except:
    df_items = pd.DataFrame()

current_notice = get_notice()

# ----------------------------------------------------------
# 3. 화면 구성
# ----------------------------------------------------------
st.title("🤖 든든한 프로젝트 매니저")

with st.sidebar:
    st.header("⚙️ 설정")
    is_mobile = st.checkbox("📱 모바일 모드", value=False)
    if st.button("❓ 도움말"): show_guide()
    st.link_button("📂 구글시트 바로가기", "https://docs.google.com/spreadsheets/")

# 통계 UI
st.markdown(f"""
    <div style="display:flex; justify-content:space-around; background-color:rgba(255,255,255,0.1); padding:10px; border-radius:10px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.2);">
        <div style="text-align:center;"><p style="margin:0; font-size:14px; opacity:0.8;">📌 전체</p><p style="margin:0; font-size:20px; font-weight:bold;">{total}</p></div>
        <div style="text-align:center;"><p style="margin:0; font-size:14px; opacity:0.8;">✅ 완료</p><p style="margin:0; font-size:20px; font-weight:bold;">{done}</p></div>
        <div style="text-align:center;"><p style="margin:0; font-size:14px; opacity:0.8;">⏳ 대기</p><p style="margin:0; font-size:20px; font-weight:bold;">{pending}</p></div>
    </div>
""", unsafe_allow_html=True)

# 탭 구성
if is_mobile:
    tab1, tab2, tab3 = st.tabs(["💬 채팅", "📊 작업", "📦 물품"])
    c_chat, c_sheet, c_items = tab1, tab2, tab3
else:
    col1, col2 = st.columns([1, 1.2])
    c_chat = col1
    with col2:
        sub_tab1, sub_tab2 = st.tabs(["📊 작업 리스트", "📦 물품 리스트"])
        c_sheet = sub_tab1
        c_items = sub_tab2

# [탭 2] 작업
with c_sheet:
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=500)
    else: st.info("작업 데이터가 없습니다.")

# [탭 3] 물품
with c_items:
    if not df_items.empty:
        st.dataframe(df_items, use_container_width=True, height=500)
    else:
        st.info("📦 물품 리스트가 비어있습니다. 구글 시트의 '물품' 탭에 엑셀 내용을 붙여넣어 주세요!")

# [탭 1] 채팅
with c_chat:
    if current_notice not in ["-", "공지없음"]:
        st.info(f"📢 **공지:** {current_notice}")
    
    st.subheader("💬 AI 비서")
    chat_con = st.container(height=400 if is_mobile else 550, border=True)
    
    if "messages" not in st.session_state: st.session_state.messages=[]
    with chat_con:
        for m in st.session_state.messages: st.chat_message(m["role"]).write(m["content"])

prompt = st.chat_input("명령 입력...")
if prompt:
    with chat_con: st.chat_message("user").write(prompt)
    st.session_state.messages.append({"role":"user", "content":prompt})

    csv_task = df.to_csv(index=False) if not df.empty else "없음"
    csv_item = df_items.to_csv(index=False) if not df_items.empty else "없음"
    
    sys_prompt = f"""
    너는 프로젝트 매니저야.
    [작업 목록]: {csv_task}
    [물품 목록]: {csv_item}
    
    규칙:
    1. 공지변경: {{"action":"notice", "value":"내용"}}
    2. 작업변경: {{"action":"update", "task":"이름", "target":"상태