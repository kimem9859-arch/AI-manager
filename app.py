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

# 세션 상태 초기화 (사용 설명서 팝업용)
if "first_visit" not in st.session_state:
    st.session_state.first_visit = True

# 사용 설명서 팝업
@st.dialog("📖 사용 설명서")
def show_guide():
    st.markdown("""
    ### 👋 환영합니다!
    **1. 💬 채팅 비서:** 작업 추가/수정 및 물품 검색 가능
    **2. 📊 프로젝트 시트:** 할 일 목록 관리
    **3. 📦 물품 리스트:** 엑셀로 정리한 물품 현황 확인
    **4. 📱 모바일 모드:** 사이드바에서 설정 가능
    """)
    if st.button("닫기"):
        st.rerun()

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("API 키 설정 필요")

model = genai.GenerativeModel('gemini-2.5-pro')

# [기본] 스프레드시트 연결
def get_spreadsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)
    return client.open("Safety_Project")

# 1. 작업 목록 시트
def connect_to_task_sheet():
    sh = get_spreadsheet()
    try: return sh.worksheet("작업")
    except: return sh.sheet1 

# 2. 공지 시트
def connect_to_notice_sheet():
    sh = get_spreadsheet()
    try: return sh.worksheet("공지")
    except:
        new = sh.add_worksheet("공지", 10, 2)
        new.update_cell(1,1,"공지없음")
        return new

# 3. ★ [신규] 물품 리스트 시트 연결
def connect_to_item_sheet():
    sh = get_spreadsheet()
    try:
        # 구글 시트에 '물품'이라는 탭이 있어야 합니다!
        return sh.worksheet("물품")
    except:
        return None # 물품 시트가 없으면 없는 대로 처리

# 공지 읽기/쓰기 함수들
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

# (2) 물품 데이터 (엑셀 파일 내용)
try:
    item_sheet = connect_to_item_sheet()
    if item_sheet:
        item_data = item_sheet.get_all_records()
        df_items = pd.DataFrame(item_data)
        # ★ 엑셀 호환성 처리: 빈칸(병합된 셀의 뒷부분)을 앞의 값으로 채움
        # (예: '센서류' 카테고리가 병합되어 있으면, 아래 칸들도 '센서류'로 인식하게 함)
        df_items = df_items.replace("", pd.NA).ffill()
        df_items = df_items.fillna("-") # 그래도 빈칸은 - 처리
    else:
        df_items = pd.DataFrame()
except:
    df_items = pd.DataFrame()

current_notice = get_notice()

# ----------------------------------------------------------
# 3. 화면 구성 (UI)
# ----------------------------------------------------------
st.title("🤖 든든한 프로젝트 매니저")

with st.sidebar:
    st.header("⚙️ 설정")
    is_mobile = st.checkbox("📱 모바일 모드", value=False)
    if st.button("❓ 도움말"): show_guide()
    # ★ 원본 엑셀 보러가기 링크 (자신의 구글시트 주소로 바꾸세요)
    st.link_button("📂 원본 엑셀(구글시트) 열기", "https://docs.google.com/spreadsheets/")

# 통계 (모바일/PC 공통)
st.markdown(f"""
    <div style="display:flex; justify-content:space-around; background-color:rgba(255,255,255,0.1); padding:10px; border-radius:10px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.2);">
        <div style="text-align:center;"><p style="margin:0; font-size:14px; opacity:0.8;">📌 전체</p><p style="margin:0; font-size:20px; font-weight:bold;">{total}</p></div>
        <div style="text-align:center;"><p style="margin:0; font-size:14px; opacity:0.8;">✅ 완료</p><p style="margin:0; font-size:20px; font-weight:bold;">{done}</p></div>
        <div style="text-align:center;"><p style="margin:0; font-size:14px; opacity:0.8;">⏳ 대기</p><p style="margin:0; font-size:20px; font-weight:bold;">{pending}</p></div>
    </div>
""", unsafe_allow_html=True)

# 탭 구성 (물품 리스트 추가!)
if is_mobile:
    tab1, tab2, tab3 = st.tabs(["💬 채팅", "📊 작업", "📦 물품"])
    c_chat, c_sheet, c_items = tab1, tab2, tab3
else:
    # PC에서는 2단 분리 (채팅 / 시트+물품)
    col1, col2 = st.columns([1, 1.2])
    c_chat = col1
    with col2:
        sub_tab1, sub_tab2 = st.tabs(["📊 작업 리스트", "📦 물품 리스트"])
        c_sheet = sub_tab1
        c_items = sub_tab2

# [탭 2] 작업 리스트
with c_sheet:
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=500)
    else: st.info("작업 데이터 없음")

# [탭 3] ★ 물품 리스트 (엑셀 데이터)
with c_items:
    if not df_items.empty:
        st.info("💡 엑셀의 색상/병합은 제외하고 '데이터'만 보여줍니다.")
        st.dataframe(df_items, use_container_width=True, height=500)
    else:
        st.warning("⚠️ '물품' 시트를 찾지 못했습니다. 구글 시트에 '물품' 탭을 만들고 데이터를 넣어주세요!")

# [탭 1] 채팅 비서
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

    # AI에게 물품 데이터도 같이 줌!
    csv_task = df.to_csv(index=False) if not df.empty else "없음"
    csv_item = df_items.to_csv(index=False) if not df_items.empty else "없음"
    
    sys_prompt = f"""
    너는 프로젝트 매니저야.
    [작업 목록]: {csv_task}
    [물품 목록(엑셀)]: {csv_item}
    
    규칙:
    1. 공지변경: {{"action":"notice", "value":"내용"}}
    2. 작업변경: {{"action":"update", "task":"이름", "target":"상태/비고/세부내용", "value":"값"}}
    3. 작업추가: {{"action":"add", "task":"이름"}}
    4. 작업삭제: {{"action":"delete", "task":"이름"}}
    
    * 사용자가 "물품"에 대해 물어보면 [물품 목록] 데이터를 보고 대답해. (예: 가격, 수량 등)
    """
    
    try:
        res = model.generate_content(sys_prompt + "\nUser:" + prompt)
        txt = res.text.strip()
        jsons = re.findall(r'\{.*?\}', txt.replace("```json","").replace("```",""), re.DOTALL)
        
        processed = False
        if jsons:
            for j in jsons:
                try:
                    cmd = json.loads(j)
                    act = cmd.get("action")
                    if act=="notice": update_notice(cmd['value']); processed=True
                    elif act=="update": update_sheet_any(cmd['task'], cmd['target'], cmd['value']); processed=True
                    elif act=="add": add_new_task(cmd['task']); processed=True
                    elif act=="delete": delete_task(cmd['task']); processed=True
                except: pass
        
        if processed: st.rerun()
        else:
            with chat_con: st.chat_message("assistant").write(txt)
            st.session_state.messages.append({"role":"assistant", "content":txt})
    except Exception as e: st.error(f"Error: {e}")