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

# ★ 모델 설정 (gemini-2.5-pro 유지)
model = genai.GenerativeModel('gemini-2.5-pro')

def connect_to_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)
    return client.open("Safety_Project").sheet1

def get_notice():
    try:
        sheet = connect_to_sheet()
        notice = sheet.cell(2, 5).value 
        return notice if notice else "등록된 공지사항이 없습니다."
    except:
        return "공지사항 없음 (E2셀 확인필요)"

def update_notice(new_text):
    try:
        sheet = connect_to_sheet()
        sheet.update_cell(2, 5, new_text)
        return True
    except:
        return False

def update_sheet_any(task_name, target_col, new_value):
    try:
        sheet = connect_to_sheet()
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
        sheet = connect_to_sheet()
        sheet.append_row([task_name, "설정필요", "대기", "-"])
        return True
    except:
        return False

def delete_task(task_name):
    try:
        sheet = connect_to_sheet()
        cell = sheet.find(task_name)
        sheet.delete_rows(cell.row)
        return True
    except:
        return False

# ----------------------------------------------------------
# 2. 데이터 불러오기
# ----------------------------------------------------------
try:
    sheet = connect_to_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    current_notice = get_notice()
    
    # 지표 계산
    total = len(df)
    done = len(df[df['상태'] == '완료']) if not df.empty else 0
    pending = len(df[df['상태'] == '대기']) if not df.empty else 0
    
except:
    st.error("⚠️ 시트 연결 실패!")
    df = pd.DataFrame()
    current_notice = "-"
    total, done, pending = 0, 0, 0

# ----------------------------------------------------------
# 3. 화면 구성 (UI)
# ----------------------------------------------------------
st.title("🤖 든든한 프로젝트 매니저")

with st.sidebar:
    st.header("⚙️ 설정")
    is_mobile = st.checkbox("📱 모바일 모드 (탭 보기)", value=False)

# ★★★ [개선 1] 모바일 최적화 통계 (커스텀 HTML) ★★★
# st.metric 대신 HTML로 직접 그려서 강제로 가로 배치하고 글씨를 줄입니다.
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
        # 모바일에선 표를 조금 더 작게 보여줌
        st.dataframe(df, use_container_width=True, height=400 if is_mobile else 600)
    else:
        st.info("데이터 없음")

# [왼쪽/탭1] 채팅 화면
with container_chat:
    if current_notice != "-":
        st.info(f"📢 **공지:** {current_notice}")
        
    st.subheader("💬 AI 비서")
    
    # 채팅 내역 박스 (높이 조절)
    chat_box_height = 400 if is_mobile else 550
    chat_container = st.container(height=chat_box_height, border=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with chat_container:
        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])

# ★★★ [개선 2] 입력창 하단 고정 ★★★
# with 문 밖으로 빼내어 화면 전체의 맨 아래에 고정시킵니다.
prompt = st.chat_input("명령을 입력하세요... (예: 라즈베리파이 구매 완료)")

if prompt:
    # 1. 사용자 메시지 표시 (채팅 박스 안에)
    with chat_container:
        st.chat_message("user").write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. AI 로직 처리
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
            # AI 답변 표시 (채팅 박스 안에)
            with chat_container: 
                st.chat_message("assistant").write(text)
            st.session_state.messages.append({"role": "assistant", "content": text})
            
    except Exception as e:
        st.error(f"에러: {e}")