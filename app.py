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

# ★ [신규 기능] 사용 설명서 팝업 함수
@st.dialog("📖 사용 설명서")
def show_guide():
    st.markdown("""
    ### 👋 환영합니다! AI 프로젝트 매니저입니다.
    이곳은 **라즈베리파이 AI 비전 프로젝트**를 관리하는 공간입니다.
    
    #### 1. 🤖 AI 비서에게 말 걸기 (왼쪽/채팅탭)
    자연어로 명령하면 시트에 자동으로 반영됩니다.
    * **추가:** "라즈베리파이 쿨링팬 구매 작업 추가해줘"
    * **수정:** "쿨링팬 구매 완료로 바꿔줘"
    * **삭제:** "쿨링팬 작업 삭제해줘"
    * **공지:** "공지사항을 '다음 주 중간 발표'로 변경해줘"
    
    #### 2. 📊 실시간 현황판 (오른쪽/시트탭)
    * 구글 시트('작업' 탭)와 실시간으로 연동됩니다.
    * 전체 진행률과 대기 중인 작업을 한눈에 볼 수 있습니다.
    
    #### 3. 📱 모바일 모드
    * 핸드폰으로 접속하셨나요?
    * 왼쪽 사이드바(>)에서 **'모바일 모드'**를 체크하세요.
    * 화면이 탭(Tab) 방식으로 바뀌어 보기 편해집니다.
    """)
    if st.button("네, 알겠습니다! (닫기)"):
        st.rerun()

# 세션 상태 초기화 (처음 접속인지 확인)
if "first_visit" not in st.session_state:
    st.session_state.first_visit = True

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("API 키가 설정되지 않았습니다.")

# ★ 모델 설정
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

def connect_to_task_sheet():
    sh = get_spreadsheet()
    try:
        return sh.worksheet("작업")
    except:
        return sh.sheet1 

def connect_to_notice_sheet():
    sh = get_spreadsheet()
    try:
        return sh.worksheet("공지")
    except:
        new_sheet = sh.add_worksheet(title="공지", rows="10", cols="2")
        new_sheet.update_cell(1, 1, "공지사항 없음")
        return new_sheet

def get_notice():
    try:
        sheet = connect_to_notice_sheet()
        notice = sheet.cell(1, 1).value 
        return notice if notice else "공지사항 없음"
    except:
        return "-"

def update_notice(new_text):
    try:
        sheet = connect_to_notice_sheet()
        sheet.update_cell(1, 1, new_text)
        return True
    except:
        return False

def update_sheet_any(task_name, target_col, new_value):
    try:
        sheet = connect_to_task_sheet()
        cell = sheet.find(task_name)
        col_map = {"상태": 3, "비고": 4, "세부내용": 2}
        idx = col_map.get(target_col)
        if idx:
            sheet.update_cell(cell.row, idx, new_value)
            return True
        return False
    except:
        return False

def add_new_task(task_name):
    try:
        sheet = connect_to_task_sheet()
        sheet.append_row([task_name, "설정필요", "대기", "-"]) 
        return True
    except:
        return False

def delete_task(task_name):
    try:
        sheet = connect_to_task_sheet()
        cell = sheet.find(task_name)
        sheet.delete_rows(cell.row)
        return True
    except:
        return False

# ----------------------------------------------------------
# 2. 화면 구성 & 팝업 실행
# ----------------------------------------------------------

# ★ [핵심] 접속하자마자 팝업 띄우기 (맨 처음에만)
if st.session_state.first_visit:
    show_guide()
    st.session_state.first_visit = False

try:
    task_sheet = connect_to_task_sheet()
    data = task_sheet.get_all_records()
    df = pd.DataFrame(data)
    current_notice = get_notice()
    
    total = len(df)
    done = len(df[df['상태'] == '완료']) if not df.empty else 0
    pending = len(df[df['상태'] == '대기']) if not df.empty else 0
    
except:
    st.error("⚠️ 시트 연결 오류! 시트 이름('작업')과 헤더를 확인하세요.")
    df = pd.DataFrame()
    current_notice = "연결 실패"
    total, done, pending = 0, 0, 0

st.title("🤖 든든한 프로젝트 매니저")

with st.sidebar:
    st.header("⚙️ 설정")
    is_mobile = st.checkbox("📱 모바일 모드 (탭 보기)", value=False)
    
    st.divider()
    # ★ [신규] 언제든 다시 볼 수 있는 버튼
    if st.button("❓ 사용법 다시 보기"):
        show_guide()

# 모바일 최적화 통계
st.markdown(f"""
    <div style="
        display: flex; 
        justify-content: space-around; 
        align-items: center; 
        background-color: rgba(255, 255, 255, 0.1); 
        padding: 10px; 
        border-radius: 10px; 
        margin-bottom: 20px;
        border: 1px solid rgba(255, 255, 255, 0.2);">
        <div style="text-align: center;">
            <p style="margin: 0; font-size: 14px; opacity: 0.8;">📌 전체</p>
            <p style="margin: 0; font-size: 20px; font-weight: bold;">{total}</p>
        </div>
        <div style="text-align: center;">
            <p style="margin: 0; font-size: 14px; opacity: 0.8;">✅ 완료</p>
            <p style="margin: 0; font-size: 20px; font-weight: bold;">{done}</p>
        </div>
        <div style="text-align: center;">
            <p style="margin: 0; font-size: 14px; opacity: 0.8;">⏳ 대기</p>
            <p style="margin: 0; font-size: 20px; font-weight: bold;">{pending}</p>
        </div>
    </div>
""", unsafe_allow_html=True)

# 레이아웃 분기점
if is_mobile:
    tab1, tab2 = st.tabs(["💬 채팅 비서", "📊 프로젝트 시트"])
    container_chat = tab1
    container_sheet = tab2
else:
    col1, col2 = st.columns([1, 1.2])
    container_chat = col1
    container_sheet = col2

with container_sheet:
    st.subheader("📊 실시간 리스트")
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=400 if is_mobile else 600)
    else:
        st.info("데이터가 없습니다.")

with container_chat:
    if current_notice != "-" and current_notice != "공지사항 없음":
        st.info(f"📢 **공지:** {current_notice}")
        
    st.subheader("💬 AI 비서")
    
    chat_box_height = 400 if is_mobile else 550
    chat_container = st.container(height=chat_box_height, border=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with chat_container:
        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])

prompt = st.chat_input("명령을 입력하세요...")

if prompt:
    with chat_container:
        st.chat_message("user").write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # AI 로직
    data_context = df.to_csv(index=False) if not df.empty else "데이터 없음"
    system_prompt = f"""
    너는 매니저야. 데이터: {data_context}
    규칙:
    1. 공지변경: {{"action": "notice", "value": "내용"}}
    2. 수정: {{"action": "update", "task": "이름", "target": "상태/비고/세부내용", "value": "값"}}
    3. 추가: {{"action": "add", "task": "이름"}}
    4. 삭제: {{"action": "delete", "task": "이름"}}
    그 외는 자연어 답변.
    """
    
    try:
        res = model.generate_content(system_prompt + "\n사용자: " + prompt)
        text = res.text.strip()
        json_objs = re.findall(r'\{.*?\}', text.replace("```json","").replace("```",""), re.DOTALL)
        
        processed = False
        if json_objs:
            for j in json_objs:
                try:
                    cmd = json.loads(j)
                    act = cmd.get("action")
                    if act == "notice":
                        if update_notice(cmd['value']):
                            st.session_state.messages.append({"role": "assistant", "content": f"📢 공지 변경: {cmd['value']}"})
                            processed = True
                    elif act == "update":
                        if update_sheet_any(cmd['task'], cmd['target'], cmd['value']):
                            st.session_state.messages.append({"role": "assistant", "content": f"✅ {cmd['task']} 수정 완료"})
                            processed = True
                    elif act == "add":
                        if add_new_task(cmd['task']):
                            st.session_state.messages.append({"role": "assistant", "content": f"🆕 {cmd['task']} 추가 완료"})
                            processed = True
                    elif act == "delete":
                        if delete_task(cmd['task']):
                            st.session_state.messages.append({"role": "assistant", "content": f"🗑️ {cmd['task']} 삭제 완료"})
                            processed = True
                except: pass
        
        if processed:
            st.rerun()
        else:
            with chat_container: 
                st.chat_message("assistant").write(text)
            st.session_state.messages.append({"role": "assistant", "content": text})
            
    except Exception as e:
        st.error(f"에러: {e}")