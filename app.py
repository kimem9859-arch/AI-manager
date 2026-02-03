import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import re 

# ----------------------------------------------------------
# 1. 초기 설정 & 함수
# ----------------------------------------------------------
st.set_page_config(page_title="내 AI 프로젝트 매니저", page_icon="🤖", layout="wide")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("API 키가 설정되지 않았습니다.")

# ★ 모델 설정 (사용자 지정)
model = genai.GenerativeModel('gemini-2.5-pro')

# [기본] 스프레드시트 파일 열기
def get_spreadsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)
    # 스프레드시트 파일 이름이 "Safety_Project"가 맞는지 확인하세요!
    return client.open("Safety_Project")

# [수정됨] ★ '작업'이라는 이름의 시트를 콕 집어서 가져오기
def connect_to_task_sheet():
    sh = get_spreadsheet()
    try:
        # 1순위: '작업'이라는 시트 찾기
        return sh.worksheet("작업")
    except:
        # 만약 '작업' 시트가 없으면 -> 첫 번째 시트라도 가져오기 (비상용)
        return sh.sheet1 

# [수정됨] ★ '공지'라는 이름의 시트 가져오기
def connect_to_notice_sheet():
    sh = get_spreadsheet()
    try:
        return sh.worksheet("공지")
    except:
        # 없으면 자동 생성
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
        col_map = {"상태": 3, "비고": 4, "세부내용": 2} # 열 번호 확인 필요 (상태가 C열이면 3)
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
        # 새 작업 추가 시 기본값
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
# 2. 데이터 불러오기
# ----------------------------------------------------------
try:
    task_sheet = connect_to_task_sheet()
    data = task_sheet.get_all_records()
    df = pd.DataFrame(data)
    current_notice = get_notice()
    
    # 지표 계산
    total = len(df)
    done = len(df[df['상태'] == '완료']) if not df.empty else 0
    pending = len(df[df['상태'] == '대기']) if not df.empty else 0
    
except:
    # 에러 발생 시 화면에 표시
    st.error("⚠️ 시트 연결 오류! 시트 이름이 '작업'인지, 제목 줄(1행)이 있는지 확인하세요.")
    df = pd.DataFrame()
    current_notice = "연결 실패"
    total, done, pending = 0, 0, 0

# ----------------------------------------------------------
# 3. 화면 구성 (UI)
# ----------------------------------------------------------
st.title("🤖 든든한 프로젝트 매니저")

with st.sidebar:
    st.header("⚙️ 설정")
    is_mobile = st.checkbox("📱 모바일 모드 (탭 보기)", value=False)

# 모바일 최적화 통계 (가로 배치)
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

# [오른쪽/탭2] 시트 화면
with container_sheet:
    st.subheader("📊 실시간 리스트")
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=400 if is_mobile else 600)
    else:
        st.info("데이터가 없습니다. (시트 이름을 '작업'으로 바꿨는지 확인해주세요!)")

# [왼쪽/탭1] 채팅 화면
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

# 입력창 하단 고정
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