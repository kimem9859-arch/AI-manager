import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import re 

# ----------------------------------------------------------
# 1. 초기 설정
# ----------------------------------------------------------
st.set_page_config(page_title="내 AI 프로젝트 매니저", page_icon="🤖", layout="wide")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("API 키가 아직 설정되지 않았습니다. Streamlit 설정을 확인해주세요.")

model = genai.GenerativeModel('gemini-2.5-pro')

# 기존의 connect_to_sheet 함수를 지우고 이걸로 덮어쓰세요!
def connect_to_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # [수정된 부분] 파일이 아니라, Streamlit의 비밀 금고(Secrets)에서 정보를 가져옵니다.
    try:
        # 1. 스트림릿 클라우드에 저장된 비밀정보(gcp_service_account)를 사용
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        # (혹시 로컬에서 실행할 때를 대비해 기존 방식도 남겨둠)
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        
    client = gspread.authorize(creds)
    return client.open("Safety_Project").sheet1

def update_sheet_any(task_name, target_col, new_value):
    try:
        sheet = connect_to_sheet()
        cell = sheet.find(task_name)
        col_map = {"상태": 3, "비고": 4, "세부내용": 2}
        target_col_idx = col_map.get(target_col)
        
        if target_col_idx:
            sheet.update_cell(cell.row, target_col_idx, new_value)
            return True
        else:
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
    """★ [신규 기능] 작업을 시트에서 삭제하는 함수"""
    try:
        sheet = connect_to_sheet()
        cell = sheet.find(task_name)
        sheet.delete_rows(cell.row) # 해당 줄을 아예 삭제
        return True
    except:
        return False

# ----------------------------------------------------------
# 3. 화면 구성 (UI 레이아웃 변경)
# ----------------------------------------------------------
st.title("🤖 든든한 프로젝트 매니저")

# [데이터 불러오기]
try:
    sheet = connect_to_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    task_list = [str(row['작업명']) for row in data]
    
    # 지표 계산
    total_tasks = len(df)
    completed_tasks = len(df[df['상태'] == '완료'])
    pending_tasks = len(df[df['상태'] == '대기'])
    
except:
    st.error("시트 연결 대기중...")
    df = pd.DataFrame()
    task_list = []

# --- [UI 핵심 변경] 기기에 따라 레이아웃 선택 ---
with st.sidebar:
    st.header("⚙️ 화면 설정")
    # 모바일에서는 이 체크박스를 켜서 '탭' 모드로 봅니다.
    is_mobile = st.checkbox("📱 모바일 모드 (탭으로 보기)", value=False)
    
    st.divider()
    st.write(f"📌 전체 작업: {total_tasks}개")
    st.write(f"✅ 완료됨: {completed_tasks}개")
    st.write(f"⏳ 대기중: {pending_tasks}개")

# 레이아웃 결정 (모바일이면 탭, PC면 컬럼)
if is_mobile:
    # [모바일] 탭으로 나누기 (채팅 탭 / 시트 탭)
    container_chat, container_sheet = st.tabs(["💬 채팅 비서", "📊 프로젝트 시트"])
else:
    # [PC] 화면을 반으로 나누기 (왼쪽 채팅, 오른쪽 시트)
    col1, col2 = st.columns([1, 1.2])
    container_chat = col1
    container_sheet = col2

# ----------------------------------------------------------
# [화면 1] 시트 현황판 (container_sheet 안에 넣기)
# ----------------------------------------------------------
with container_sheet:
    st.subheader("📊 실시간 프로젝트 리스트")
    if not df.empty:
        # 모바일에서도 잘 보이게 높이 조정
        st.dataframe(df, use_container_width=True, height=400 if is_mobile else 600)
    else:
        st.info("데이터가 없습니다.")

# ----------------------------------------------------------
# [화면 2] 채팅창 (container_chat 안에 넣기)
# ----------------------------------------------------------
with container_chat:
    st.info("📢 공지사항: 오늘 밤 서버 점검이 있습니다.")
    
    st.subheader("💬 AI 작업 비서")
    
    # 채팅창 높이도 모바일에선 조금 작게, PC에선 크게
    chat_height = 400 if is_mobile else 600
    chat_container = st.container(height=chat_height, border=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

    prompt = st.chat_input("명령을 입력하세요...")

    if prompt:
        with chat_container:
            with st.chat_message("user"):
                st.write(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # --- AI 프롬프트 및 로직 (기존과 동일) ---
        current_data_context = df.to_csv(index=False) if not df.empty else "데이터 없음"

        system_prompt = f"""
        너는 유능한 프로젝트 매니저야.
        [현재 시트 데이터]
        {current_data_context}
        [수행 규칙]
        1. '추가', '수정', '삭제' 명령은 JSON으로 답해.
           - 수정: {{"action": "update", "task": "작업명", "target": "상태/비고/세부내용", "value": "변경할내용"}}
           - 추가: {{"action": "add", "task": "새로운작업명"}}
           - 삭제: {{"action": "delete", "task": "삭제할작업명"}}
        2. 그 외 질문은 자연스러운 한국어로 답해.
        """
        
        full_prompt = system_prompt + "\n사용자: " + prompt
        
        try:
            response = model.generate_content(full_prompt)
            ai_text = response.text.strip()
            
            clean_text = ai_text.replace("```json", "").replace("```", "").strip()
            json_objects = re.findall(r'\{.*?\}', clean_text, re.DOTALL)
            
            processed_count = 0
            
            if json_objects:
                for json_str in json_objects:
                    try:
                        command = json.loads(json_str)
                        if command.get("action") == "update":
                            if update_sheet_any(command['task'], command['target'], command['value']):
                                result_msg = f"✅ **'{command['task']}'** 수정 완료!"
                                st.session_state.messages.append({"role": "assistant", "content": result_msg})
                                processed_count += 1
                        elif command.get("action") == "add":
                            if add_new_task(command['task']):
                                result_msg = f"🆕 **'{command['task']}'** 추가 완료!"
                                st.session_state.messages.append({"role": "assistant", "content": result_msg})
                                processed_count += 1
                        elif command.get("action") == "delete":
                            if delete_task(command['task']):
                                result_msg = f"🗑️ **'{command['task']}'** 삭제 완료."
                                st.session_state.messages.append({"role": "assistant", "content": result_msg})
                                processed_count += 1
                    except:
                        continue 

                if processed_count > 0:
                    st.rerun()
                else:
                     with chat_container:
                        with st.chat_message("assistant"):
                            st.write(ai_text)
                     st.session_state.messages.append({"role": "assistant", "content": ai_text})
            else:
                with chat_container:
                    with st.chat_message("assistant"):
                        st.write(ai_text)
                st.session_state.messages.append({"role": "assistant", "content": ai_text})
                
        except Exception as e:
            st.error(f"에러: {e}")